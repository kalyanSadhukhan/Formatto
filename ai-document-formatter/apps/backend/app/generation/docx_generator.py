import io
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt

from app.domain.schemas.data_contracts import DocumentIR, GenerationManifest, IRElement, MappingManifest
from app.generation.models import GenerationResult

logger = logging.getLogger(__name__)


class DocxGenerator:
    """
    Deterministic DOCX Generator using controlled template-based assembly.

    Consumes a DocumentIR and reference template DOCX, and generates a valid,
    styled DOCX output document conforming to Specification V2 (docs/12_DOCX_GENERATION_SPEC.md).

    Key Capabilities:
    1. Substrate preservation: Uses reference DOCX as the base, preserving its
       underlying page setup, margins, section properties, header/footer parts,
       styles, themes, and numbering definitions.
    2. Style resolution & fallback: Matches mapped styles canonically, falling back
       to 'Normal' or 'Table Grid' with explicit diagnostic logging when absent.
    3. Run-level formatting: Retains character-level bold, italic, and underline
       overlays without flattening rich text into a single unformatted run.
    4. List generation: Supports both bullet and numbered list styles, preserving
       nesting depth and Word numbering definitions.
    5. Table preservation: Reconstructs exact 2D cell grids, row/column dimensions,
       empty cells, and horizontal/vertical cell merges without text flattening.
    6. Figure reconstruction: Extracts embedded image binaries from the source
       package, re-establishing valid OpenXML relationship parts and scaling to page width.
    7. Unsupported content guardrail: Emits visible warnings and diagnostic records
       rather than silently dropping unhandled content.
    8. Traceability: Produces an internal GenerationManifest mapping IR target IDs
       to concrete DOCX body locations (body/p[i], body/tbl[j]).
    """

    def __init__(self, template_path: str, source_docx_path: Optional[str] = None):
        self.template_path = template_path
        self.source_docx_path = source_docx_path

        if not os.path.exists(template_path):
            raise ValueError(f"Template DOCX file not found: {template_path}")

        self.source_doc = None
        if source_docx_path and os.path.exists(source_docx_path):
            try:
                self.source_doc = Document(source_docx_path)
            except Exception as e:
                logger.warning(f"Could not load source DOCX for image extraction: {e}")

    def generate(self, ir: DocumentIR, output_path: str, job_id: Optional[str] = None) -> GenerationResult:
        """
        Execute controlled template-based assembly and write the generated DOCX.
        """
        jid = job_id or f"job_{ir.document_id}"
        logger.info(f"Generating DOCX for document {ir.document_id} into {output_path}")

        # 1. Load reference template as the formatting substrate
        doc = Document(self.template_path)

        # Check if template is structured (pre-existing tables / multi-section form template)
        is_structured = ir.metadata.get("is_structured_template", False)

        if is_structured:
            return self._generate_structured_template(doc, ir, output_path, jid)


        # 2. Controlled substrate clearing for flow documents: remove existing body paragraphs/tables,
        # preserving final sectPr and package parts (headers, footers, styles, numbering)
        body = doc._body._body
        for child in list(body):
            if not child.tag.endswith("sectPr"):
                body.remove(child)

        # Index available template styles
        paragraph_styles, table_styles = self._index_template_styles(doc)


        manifest_entries: List[MappingManifest] = []
        diagnostics: List[str] = []

        paragraph_index = 0
        table_index = 0
        generated_count = 0
        unmapped_count = 0

        # 3. Assemble document content element by element in strict monotonic order
        for elem in ir.elements:
            elem_type = elem.type.lower()
            meta = elem.metadata or {}

            # Handle explicit section or page breaks before element
            break_before = meta.get("break_before")
            if break_before == "section":
                doc.add_section()
            elif break_before == "page":
                doc.add_page_break()

            try:
                if elem_type in ("heading", "title", "document_title", "paragraph", "body_paragraph", "caption", "reference"):
                    resolved_style, style_diag = self._resolve_paragraph_style(doc, elem.style_ref, paragraph_styles)
                    if style_diag:
                        diagnostics.append(f"Element {elem.id}: {style_diag}")

                    p = doc.add_paragraph(style=resolved_style)
                    self._populate_runs(p, elem)

                    if elem_type in ("heading", "title", "document_title"):
                        p.paragraph_format.keep_with_next = True
                    elif elem_type == "caption":
                        p.paragraph_format.space_before = Pt(4)
                        p.paragraph_format.space_after = Pt(12)
                        p.paragraph_format.keep_with_next = False

                    paragraph_index += 1
                    loc_ref = f"body/p[{paragraph_index}]"
                    manifest_entries.append(
                        MappingManifest(
                            ir_target_id=elem.target_id,
                            docx_location_reference=loc_ref,
                            status="mapped",
                            message=None if not style_diag else style_diag,
                        )
                    )
                    generated_count += 1

                elif elem_type in ("bullet_list_item", "bullet_list"):
                    resolved_style, style_diag = self._resolve_list_style(doc, elem.style_ref, is_bullet=True, styles_map=paragraph_styles)
                    if style_diag:
                        diagnostics.append(f"Element {elem.id}: {style_diag}")

                    p = doc.add_paragraph(style=resolved_style)
                    self._apply_list_numbering(p, elem, is_bullet=True)
                    self._populate_runs(p, elem)

                    paragraph_index += 1
                    loc_ref = f"body/p[{paragraph_index}]"
                    manifest_entries.append(
                        MappingManifest(
                            ir_target_id=elem.target_id,
                            docx_location_reference=loc_ref,
                            status="mapped",
                            message=None if not style_diag else style_diag,
                        )
                    )
                    generated_count += 1

                elif elem_type in ("numbered_list_item", "numbered_list"):
                    resolved_style, style_diag = self._resolve_list_style(doc, elem.style_ref, is_bullet=False, styles_map=paragraph_styles)
                    if style_diag:
                        diagnostics.append(f"Element {elem.id}: {style_diag}")

                    p = doc.add_paragraph(style=resolved_style)
                    self._apply_list_numbering(p, elem, is_bullet=False)
                    self._populate_runs(p, elem)

                    paragraph_index += 1
                    loc_ref = f"body/p[{paragraph_index}]"
                    manifest_entries.append(
                        MappingManifest(
                            ir_target_id=elem.target_id,
                            docx_location_reference=loc_ref,
                            status="mapped",
                            message=None if not style_diag else style_diag,
                        )
                    )
                    generated_count += 1

                elif elem_type == "table":
                    tbl, tbl_diag = self._generate_table(doc, elem, table_styles)
                    if tbl_diag:
                        diagnostics.append(f"Element {elem.id}: {tbl_diag}")

                    table_index += 1
                    loc_ref = f"body/tbl[{table_index}]"
                    manifest_entries.append(
                        MappingManifest(
                            ir_target_id=elem.target_id,
                            docx_location_reference=loc_ref,
                            status="mapped",
                            message=None if not tbl_diag else tbl_diag,
                        )
                    )
                    generated_count += 1

                elif elem_type == "figure":
                    reconstructed, fig_diag = self._generate_figure(doc, elem)
                    if fig_diag:
                        diagnostics.append(f"Element {elem.id}: {fig_diag}")

                    paragraph_index += 1
                    loc_ref = f"body/p[{paragraph_index}]"
                    status = "mapped" if reconstructed else "unmapped"
                    manifest_entries.append(
                        MappingManifest(
                            ir_target_id=elem.target_id,
                            docx_location_reference=loc_ref,
                            status=status,
                            message=fig_diag,
                        )
                    )
                    if reconstructed:
                        generated_count += 1
                    else:
                        unmapped_count += 1

                else:
                    # Unsupported element type guardrail
                    diag_msg = f"Unsupported element type '{elem_type}'; inserted diagnostic placeholder."
                    diagnostics.append(f"Element {elem.id}: {diag_msg}")

                    content_str = elem.content or ""
                    p = doc.add_paragraph(f"[UNSUPPORTED CONTENT ({elem.type}): {content_str}]", style="Normal")
                    paragraph_index += 1
                    loc_ref = f"body/p[{paragraph_index}]"
                    manifest_entries.append(
                        MappingManifest(
                            ir_target_id=elem.target_id,
                            docx_location_reference=loc_ref,
                            status="unmapped",
                            message=diag_msg,
                        )
                    )
                    unmapped_count += 1

            except Exception as ex:
                err_msg = f"Failed to generate element {elem.id} ({elem_type}): {ex}"
                logger.error(err_msg, exc_info=True)
                diagnostics.append(err_msg)
                manifest_entries.append(
                    MappingManifest(
                        ir_target_id=elem.target_id,
                        docx_location_reference="none",
                        status="unmapped",
                        message=err_msg,
                    )
                )
                unmapped_count += 1

        # 4. Save generated DOCX file
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        doc.save(output_path)

        # 5. Verify generated document by reopening
        try:
            reopened = Document(output_path)
            logger.info(
                f"Generated DOCX verified: {len(reopened.paragraphs)} paragraphs, "
                f"{len(reopened.tables)} tables, {len(reopened.inline_shapes)} inline shapes."
            )
        except Exception as v_err:
            raise RuntimeError(f"Generated DOCX failed verification upon reopening: {v_err}")

        manifest = GenerationManifest(job_id=jid, mappings=manifest_entries)

        return GenerationResult(
            job_id=jid,
            output_path=output_path,
            manifest=manifest,
            total_elements=len(ir.elements),
            generated_elements=generated_count,
            unmapped_elements=unmapped_count,
            diagnostics=diagnostics,
        )

    def _index_template_styles(self, doc: Document) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Index available template paragraph and table styles for canonical matching."""
        para_styles: Dict[str, str] = {}
        tbl_styles: Dict[str, str] = {}

        for s in doc.styles:
            name = s.name
            c_key = self._canonical_key(name)
            if s.type == WD_STYLE_TYPE.PARAGRAPH:
                para_styles[c_key] = name
                para_styles[name.lower()] = name
            elif s.type == WD_STYLE_TYPE.TABLE:
                tbl_styles[c_key] = name
                tbl_styles[name.lower()] = name

        return para_styles, tbl_styles

    @staticmethod
    def _canonical_key(name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    def _resolve_paragraph_style(
        self,
        doc: Document,
        requested_style: Optional[str],
        styles_map: Dict[str, str],
    ) -> Tuple[str, Optional[str]]:
        """Resolve paragraph style canonically with fallback to 'Normal'."""
        if not requested_style:
            return "Normal", None

        # 1. Exact match in document styles
        if requested_style in doc.styles:
            return requested_style, None

        # 2. Canonical normalized match
        c_key = self._canonical_key(requested_style)
        if c_key in styles_map:
            return styles_map[c_key], None

        if requested_style.lower() in styles_map:
            return styles_map[requested_style.lower()], None

        # 3. Fallback to Normal
        fallback_style = "Normal"
        diag = f"Requested style '{requested_style}' not found in template; fell back to '{fallback_style}'."
        return fallback_style, diag

    def _resolve_list_style(
        self,
        doc: Document,
        requested_style: Optional[str],
        is_bullet: bool,
        styles_map: Dict[str, str],
    ) -> Tuple[str, Optional[str]]:
        """Resolve list style with tiered fallback sequence."""
        if requested_style:
            resolved, diag = self._resolve_paragraph_style(doc, requested_style, styles_map)
            if not diag:
                return resolved, None

        preferred_chain = ["List Bullet", "List Paragraph", "Normal"] if is_bullet else ["List Number", "List Paragraph", "Normal"]
        for pref in preferred_chain:
            c_key = self._canonical_key(pref)
            if c_key in styles_map:
                resolved = styles_map[c_key]
                diag = None if (requested_style and self._canonical_key(requested_style) == c_key) else (
                    f"List style '{requested_style}' fell back to '{resolved}'." if requested_style else None
                )
                return resolved, diag

        return "Normal", "List style not found; fell back to 'Normal'."

    def _resolve_table_style(
        self,
        doc: Document,
        requested_style: Optional[str],
        table_styles: Dict[str, str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Resolve table style canonically with fallback."""
        if requested_style:
            c_key = self._canonical_key(requested_style)
            if c_key in table_styles:
                return table_styles[c_key], None
            if requested_style.lower() in table_styles:
                return table_styles[requested_style.lower()], None

        # Try standard Table Grid or Normal Table
        for standard in ["Table Grid", "Normal Table"]:
            c_key = self._canonical_key(standard)
            if c_key in table_styles:
                return table_styles[c_key], None

        return None, None

    def _populate_runs(self, paragraph, elem: IRElement) -> None:
        """
        Populate paragraph text preserving run-level formatting overlays
        (bold, italic, underline) without flattening rich text into a single run.
        """
        meta = elem.metadata or {}
        runs_data = meta.get("runs")

        if runs_data and isinstance(runs_data, list):
            for r_info in runs_data:
                txt = r_info.get("text", "")
                if txt:
                    r = paragraph.add_run(txt)
                    if r_info.get("bold"):
                        r.bold = True
                    if r_info.get("italic"):
                        r.italic = True
                    if r_info.get("underline"):
                        r.underline = True
        else:
            txt = elem.content
            if txt:
                r = paragraph.add_run(txt)
                if meta.get("is_bold"):
                    r.bold = True

    def _apply_list_numbering(self, paragraph, elem: IRElement, is_bullet: bool) -> None:
        """Apply OpenXML list numbering properties (<w:numPr>) when metadata is present."""
        meta = elem.metadata or {}
        num_id = meta.get("num_id")
        nesting_level = meta.get("nesting_level", elem.level)

        if num_id is not None:
            try:
                num_pr_xml = (
                    f'<w:numPr {nsdecls("w")}>'
                    f'<w:ilvl w:val="{int(nesting_level)}"/>'
                    f'<w:numId w:val="{int(num_id)}"/>'
                    f'</w:numPr>'
                )
                paragraph._p.get_or_add_pPr().append(parse_xml(num_pr_xml))
            except Exception as e:
                logger.debug(f"Could not attach numPr XML: {e}")

    def _generate_table(
        self,
        doc: Document,
        elem: IRElement,
        table_styles: Dict[str, str],
    ) -> Tuple[object, Optional[str]]:
        """Reconstruct table with 2D cell text, dimensions, and merged cells."""
        meta = elem.metadata or {}
        cell_text = elem.children if isinstance(elem.children, list) else meta.get("cell_text", [])

        if not cell_text or not isinstance(cell_text, list):
            # Empty table fallback
            tbl = doc.add_table(rows=1, cols=1)
            return tbl, "Empty table structure reconstructed."

        row_count = len(cell_text)
        col_count = max(len(r) for r in cell_text) if row_count > 0 else 1

        tbl = doc.add_table(rows=row_count, cols=col_count)

        # Apply mapped or default table style
        resolved_style, style_diag = self._resolve_table_style(doc, elem.style_ref, table_styles)
        if resolved_style:
            try:
                tbl.style = resolved_style
            except Exception as e:
                logger.debug(f"Could not apply table style {resolved_style}: {e}")

        # Populate cell text
        for r_idx, row in enumerate(cell_text):
            for c_idx, val in enumerate(row):
                if c_idx < col_count:
                    tbl.cell(r_idx, c_idx).text = str(val) if val is not None else ""

        # Apply cell merges
        merged_info = meta.get("merged_cells_info", [])
        for m in merged_info:
            r = m.get("row")
            c = m.get("col")
            m_type = m.get("type")

            if r is None or c is None or r >= row_count or c >= col_count:
                continue

            try:
                master_cell = None
                if m_type == "horizontal":
                    span = m.get("col_span", 1)
                    end_col = min(c + span - 1, col_count - 1)
                    if end_col > c:
                        master_cell = tbl.cell(r, c).merge(tbl.cell(r, end_col))

                elif m_type == "vertical" and m.get("state") == "restart":
                    span = m.get("row_span", 1)
                    end_row = min(r + span - 1, row_count - 1)
                    if end_row > r:
                        master_cell = tbl.cell(r, c).merge(tbl.cell(end_row, c))

                if master_cell is not None:
                    master_val = cell_text[r][c] if r < len(cell_text) and c < len(cell_text[r]) else ""
                    master_cell.text = str(master_val) if master_val is not None else ""
            except Exception as m_err:
                logger.debug(f"Could not merge cell at ({r}, {c}): {m_err}")

        # Apply clean borders if table has borders or by default for structured tables
        has_borders = meta.get("has_borders", True)
        if has_borders:
            borders_xml = (
                f'<w:tblBorders {nsdecls("w")}>'
                f'<w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                f'<w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                f'<w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                f'</w:tblBorders>'
            )
            tbl._tbl.tblPr.append(parse_xml(borders_xml))

        # Cell margins (padding) so text is comfortably separated from cell borders
        pad_xml = (
            f'<w:tblCellMar {nsdecls("w")}>'
            f'<w:top w:w="120" w:type="dxa"/>'
            f'<w:bottom w:w="120" w:type="dxa"/>'
            f'<w:left w:w="160" w:type="dxa"/>'
            f'<w:right w:w="160" w:type="dxa"/>'
            f'</w:tblCellMar>'
        )
        tbl._tbl.tblPr.append(parse_xml(pad_xml))

        # Apply column widths if present
        col_widths = meta.get("col_widths_dxa", [])
        if col_widths and len(col_widths) == col_count:
            for c_idx, w_dxa in enumerate(col_widths):
                tbl.columns[c_idx].width = Inches(w_dxa / 1440.0)
            for r in tbl.rows:
                for c_idx, w_dxa in enumerate(col_widths):
                    r.cells[c_idx].width = Inches(w_dxa / 1440.0)

        # Apply clean paragraph formatting inside cells
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.space_before = Pt(2)
                    p.paragraph_format.space_after = Pt(2)
                    p.paragraph_format.line_spacing = 1.15

        return tbl, style_diag

    def _generate_figure(self, doc: Document, elem: IRElement) -> Tuple[bool, Optional[str]]:
        """
        Reconstruct figure element by extracting embedded image binaries from the source
        package and re-establishing clean OpenXML drawing relationships.
        Keeps composite images together in a single paragraph with keep_with_next set
        so that captions stay attached on the same page.
        """
        meta = elem.metadata or {}
        rids = elem.children or meta.get("drawing_rids", [])

        if not rids:
            p = doc.add_paragraph("[FIGURE: No drawing relationships found]", style="Normal")
            return False, "Figure element contains no drawing relationship IDs."

        if not self.source_doc:
            p = doc.add_paragraph(f"[FIGURE: Image relationships {rids}]", style="Normal")
            return False, f"Source DOCX package not provided to extract image bytes for {rids}."

        reconstructed_any = False
        diags: List[str] = []

        # Determine target image width based on single vs composite layout
        extent_dims = meta.get("extent_dims", [])
        if len(rids) == 1:
            orig_w = extent_dims[0].get("width_in") if extent_dims else None
            target_w = Inches(min(5.5, orig_w)) if orig_w else Inches(5.5)
        else:
            # Composite figure: lay out sub-images side-by-side in one row
            sub_w = round(min(5.8 / len(rids) - 0.1, 3.0), 2)
            target_w = Inches(max(1.5, sub_w))

        # Create single paragraph for the figure to keep all sub-images together
        p = doc.add_paragraph()
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(4)

        for rid_idx, rid in enumerate(rids):
            rel = self.source_doc.part.rels.get(rid)
            if not rel or not hasattr(rel.target_part, "blob"):
                diags.append(f"Image relationship '{rid}' not found in source document package.")
                continue

            try:
                blob = rel.target_part.blob
                run = p.add_run()
                run.add_picture(io.BytesIO(blob), width=target_w)
                if rid_idx < len(rids) - 1:
                    p.add_run("  ")  # horizontal spacing between composite images
                reconstructed_any = True
            except Exception as img_err:
                diags.append(f"Failed to embed image '{rid}': {img_err}")

        if not reconstructed_any:
            p.text = f"[FIGURE: {', '.join(rids)}]"

        combined_diag = "; ".join(diags) if diags else None
        return reconstructed_any, combined_diag

    def _set_cell_text(self, cell, text: str, font_size_pt: float = 12.0, bold: bool = False, italic: bool = False):
        """Set cell text with explicit high-fidelity typography and balanced cell padding."""
        cell.text = ""
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        run = p.add_run(text)
        run.font.name = "Calibri"
        run.font.size = Pt(font_size_pt)
        run.bold = bold
        run.italic = italic

    def _generate_structured_template(
        self,
        doc: Document,
        ir: DocumentIR,
        output_path: str,
        job_id: str,
    ) -> GenerationResult:
        """
        Template-Preserving Generation (Specification V2, Phase C & D).
        Preserves original template sections, tables, headers, footers, blank rows,
        and checkboxes in full, populating content slots from source metadata.
        """
        logger.info(f"Executing template-preserving generation for job {job_id}")
        manifest_entries: List[MappingManifest] = []
        diagnostics: List[str] = []

        fields = ir.metadata.get("template_fields", {})
        students = fields.get("students", [])
        batch_id = fields.get("project_batch_id")
        guide_name = fields.get("project_guide_name")
        proj_title = fields.get("project_title")
        domain = fields.get("domain")
        leader_name = fields.get("team_leader_name")
        abstract_paras = fields.get("abstract_paragraphs", [])
        weekly_meeting = fields.get("weekly_meeting", {})
        consent_details = fields.get("consent_details", {})
        unresolved = ir.metadata.get("unresolved_mappings", [])

        # 1. Populate Table 0 (Cover page metadata & student details)
        if len(doc.tables) > 0:
            t0 = doc.tables[0]
            if batch_id and len(t0.rows) > 0 and len(t0.rows[0].cells) > 1:
                self._set_cell_text(t0.rows[0].cells[1], batch_id, font_size_pt=12.0)
                manifest_entries.append(MappingManifest(ir_target_id="project_batch_id", docx_location_reference="body/tbl[0]/tr[0]/tc[1]", status="mapped"))
            if guide_name and len(t0.rows) > 1 and len(t0.rows[1].cells) > 1:
                self._set_cell_text(t0.rows[1].cells[1], guide_name, font_size_pt=12.0)
                manifest_entries.append(MappingManifest(ir_target_id="project_guide_name", docx_location_reference="body/tbl[0]/tr[1]/tc[1]", status="mapped"))
            if proj_title and len(t0.rows) > 2 and len(t0.rows[2].cells) > 1:
                self._set_cell_text(t0.rows[2].cells[1], proj_title, font_size_pt=12.0)
                manifest_entries.append(MappingManifest(ir_target_id="project_title", docx_location_reference="body/tbl[0]/tr[2]/tc[1]", status="mapped"))
            if domain and len(t0.rows) > 3 and len(t0.rows[3].cells) > 1:
                self._set_cell_text(t0.rows[3].cells[1], domain, font_size_pt=12.0)
                manifest_entries.append(MappingManifest(ir_target_id="domain", docx_location_reference="body/tbl[0]/tr[3]/tc[1]", status="mapped"))
            if leader_name and len(t0.rows) > 4 and len(t0.rows[4].cells) > 1:
                self._set_cell_text(t0.rows[4].cells[1], leader_name, font_size_pt=12.0)
                manifest_entries.append(MappingManifest(ir_target_id="team_leader_name", docx_location_reference="body/tbl[0]/tr[4]/tc[1]", status="mapped"))

            # Populate student details rows in Table 0 (rows 6..9)
            for idx, s in enumerate(students[:4]):
                row_idx = 6 + idx
                if row_idx < len(t0.rows):
                    r = t0.rows[row_idx]
                    s_name = s.get("name", "") if isinstance(s, dict) else getattr(s, "name", "")
                    s_reg = s.get("reg_no", "") if isinstance(s, dict) else getattr(s, "reg_no", "")
                    s_branch = s.get("branch", "") if isinstance(s, dict) else getattr(s, "branch", "")
                    if len(r.cells) > 1:
                        self._set_cell_text(r.cells[1], s_name, font_size_pt=11.5)
                    if len(r.cells) > 2:
                        self._set_cell_text(r.cells[2], s_reg, font_size_pt=11.5)
                    if len(r.cells) > 3:
                        self._set_cell_text(r.cells[3], s_branch, font_size_pt=11.5)
                    manifest_entries.append(MappingManifest(ir_target_id=f"student_{idx+1}", docx_location_reference=f"body/tbl[0]/tr[{row_idx}]", status="mapped"))
            diagnostics.append("Populated cover-page metadata table with student and project details.")

        # 2. Section 1: Project Details (Title and Abstract)
        title_idx = -1
        abstract_idx = -1
        for i, p in enumerate(doc.paragraphs):
            p_txt = p.text.strip()
            if p_txt == "Title of the Project:":
                title_idx = i
            elif p_txt.startswith("Abstract:"):
                abstract_idx = i
                break

        if title_idx != -1 and proj_title:
            if title_idx + 1 < len(doc.paragraphs):
                p_title = doc.paragraphs[title_idx + 1]
                p_title.text = ""
                p_title.paragraph_format.space_before = Pt(3)
                p_title.paragraph_format.space_after = Pt(6)
                r_t = p_title.add_run(proj_title)
                r_t.font.name = "Calibri"
                r_t.font.size = Pt(13)
                r_t.bold = True
                manifest_entries.append(MappingManifest(ir_target_id="title_slot", docx_location_reference=f"body/p[{title_idx+2}]", status="mapped"))

        if abstract_idx != -1 and abstract_paras:
            # Clean up the extra empty placeholder paragraphs between title and abstract to preserve single-page layout
            if title_idx != -1 and abstract_idx > title_idx + 2:
                for empty_p in doc.paragraphs[title_idx + 2 : abstract_idx]:
                    if not empty_p.text.strip() and empty_p._p.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sectPr') is None:
                        empty_p._p.getparent().remove(empty_p._p)

            # Re-locate abstract paragraph after removal
            for i, p in enumerate(doc.paragraphs):
                if p.text.strip().startswith("Abstract:"):
                    abstract_idx = i
                    break

            if abstract_idx + 1 < len(doc.paragraphs):
                p_abs = doc.paragraphs[abstract_idx + 1]
                p_abs.text = ""
                p_abs.paragraph_format.space_before = Pt(3)
                p_abs.paragraph_format.space_after = Pt(4)
                p_abs.paragraph_format.line_spacing = 1.15
                r_a = p_abs.add_run("\n\n".join(abstract_paras))
                r_a.font.name = "Calibri"
                r_a.font.size = Pt(11)
                manifest_entries.append(MappingManifest(ir_target_id="abstract_slot", docx_location_reference=f"body/p[{abstract_idx+2}]", status="mapped"))

        # 3. Section 2: Attendance Table (Table 1) and Header
        for i, p in enumerate(doc.paragraphs):
            p_txt = p.text.strip()
            if p_txt.startswith("Student Name:") and students:
                s0 = students[0]
                s0_name = s0.get("name", "") if isinstance(s0, dict) else getattr(s0, "name", "")
                s0_reg = s0.get("reg_no", "") if isinstance(s0, dict) else getattr(s0, "reg_no", "")
                p.text = ""
                r1 = p.add_run("Student Name: ")
                r1.font.name = "Calibri"
                r1.font.size = Pt(13)
                r1.bold = True
                r2 = p.add_run(f"{s0_name}\t\t")
                r2.font.name = "Calibri"
                r2.font.size = Pt(12)
                r3 = p.add_run("Reg. No: ")
                r3.font.name = "Calibri"
                r3.font.size = Pt(13)
                r3.bold = True
                r4 = p.add_run(f"{s0_reg}\t")
                r4.font.name = "Calibri"
                r4.font.size = Pt(12)
                break

        if len(doc.tables) > 1:
            manifest_entries.append(MappingManifest(ir_target_id="attendance_table", docx_location_reference="body/tbl[1]", status="mapped", message="Preserved 26-row attendance table intact with 25 blank entry rows."))
            diagnostics.append("Preserved Daily Attendance Record table intact with all 25 blank entry rows.")

        # 4. Section 3: Weekly Meeting Record
        for i, p in enumerate(doc.paragraphs):
            p_txt = p.text.strip()
            if p_txt.startswith("Week No:") and weekly_meeting.get("week_no"):
                p.text = f"Week No: {weekly_meeting['week_no']}"
                manifest_entries.append(MappingManifest(ir_target_id="week_no", docx_location_reference=f"body/p[{i+1}]", status="mapped"))
            elif p_txt.startswith("Date:") and "to" in p_txt and weekly_meeting.get("date"):
                p.text = f"Date: {weekly_meeting['date']}"
            elif p_txt.startswith("Capstone Project Title:") and proj_title:
                p.text = f"Capstone Project Title: {proj_title}\t Group Members:"
            elif p_txt.startswith("Name:") and "Reg. No." in p_txt and "☐ Present" in p_txt:
                for s_idx, s in enumerate(students[:4]):
                    s_name = s.get("name", "") if isinstance(s, dict) else getattr(s, "name", "")
                    s_reg = s.get("reg_no", "") if isinstance(s, dict) else getattr(s, "reg_no", "")
                    if i + s_idx < len(doc.paragraphs):
                        target_p = doc.paragraphs[i + s_idx]
                        if "Meeting Venue:" in target_p.text:
                            venue = weekly_meeting.get("meeting_venue", "OF 211")
                            target_p.text = f"Name: {s_name}\tReg. No.: {s_reg}\t\t☐ Present  Meeting Venue: {venue}\t\t☐ On Time"
                        else:
                            target_p.text = f"Name: {s_name}\tReg. No.: {s_reg}\t\t☐ Present"
                break

        # 5. Review evaluation forms & checklist (Table 2, 3, 4)
        for t_idx in [2, 3, 4]:
            if len(doc.tables) > t_idx:
                manifest_entries.append(MappingManifest(ir_target_id=f"table_{t_idx}", docx_location_reference=f"body/tbl[{t_idx}]", status="mapped", message="Preserved evaluation/checklist table intact."))
        diagnostics.append("Preserved Review evaluation tables and submission checklist intact.")

        # 6. Section 7: Student Consent Form
        for i, p in enumerate(doc.paragraphs):
            p_txt = p.text.strip()
            if p_txt.startswith("Academic Year:") and consent_details.get("academic_year"):
                sem = consent_details.get("semester", "")
                p.text = f"Academic Year: {consent_details['academic_year']}\t\t Semester: {sem}\t"
            elif p_txt.startswith("Degree Program:") and consent_details.get("degree_program"):
                p.text = f"Degree Program: {consent_details['degree_program']}\t"
            elif p_txt.startswith("Project Title:") and (proj_title or guide_name):
                t_val = proj_title or ""
                g_val = guide_name or ""
                p.text = f"Project Title: {t_val}\t\t Project Guide Name: {g_val}\t"
            elif p_txt.startswith("Guide’s Designation:") and consent_details.get("guide_designation"):
                p.text = f"Guide’s Designation: {consent_details['guide_designation']}\t"

        # Table 5: Consent Students table
        if len(doc.tables) > 5:
            t5 = doc.tables[5]
            for idx, s in enumerate(students[:4]):
                row_idx = 1 + idx
                if row_idx < len(t5.rows):
                    r = t5.rows[row_idx]
                    s_name = s.get("name", "") if isinstance(s, dict) else getattr(s, "name", "")
                    s_reg = s.get("reg_no", "") if isinstance(s, dict) else getattr(s, "reg_no", "")
                    if len(r.cells) > 0:
                        self._set_cell_text(r.cells[0], f"{idx + 1}.", font_size_pt=11.0)
                    if len(r.cells) > 1:
                        self._set_cell_text(r.cells[1], s_name, font_size_pt=11.0)
                    if len(r.cells) > 2:
                        self._set_cell_text(r.cells[2], s_reg, font_size_pt=11.0)
            manifest_entries.append(MappingManifest(ir_target_id="consent_students_table", docx_location_reference="body/tbl[5]", status="mapped"))

        # Table 6: Consent Signatures table
        if len(doc.tables) > 6:
            t6 = doc.tables[6]
            for idx, s in enumerate(students[:4]):
                row_idx = 1 + idx
                if row_idx < len(t6.rows):
                    r = t6.rows[row_idx]
                    s_name = s.get("name", "") if isinstance(s, dict) else getattr(s, "name", "")
                    if len(r.cells) > 0:
                        self._set_cell_text(r.cells[0], f"{idx + 1}.", font_size_pt=11.0)
                    if len(r.cells) > 1:
                        self._set_cell_text(r.cells[1], s_name, font_size_pt=11.0)
                    if len(r.cells) > 2:
                        r.cells[2].text = ""  # Explicitly blank for manual physical signature
            manifest_entries.append(MappingManifest(ir_target_id="consent_signatures_table", docx_location_reference="body/tbl[6]", status="mapped", message="Preserved signature slots blank for manual signing."))

        # 7. Unresolved mappings
        for u in unresolved:
            manifest_entries.append(MappingManifest(
                ir_target_id=u.get("element_id", "unresolved"),
                docx_location_reference="unplaced",
                status="unmapped",
                message=f"No template slot identified for source content: {u.get('preview', '')}",
            ))
            diagnostics.append(f"Unresolved mapping: Element {u.get('element_id')} not placed in template.")

        # Save output document
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        doc.save(output_path)

        manifest = GenerationManifest(job_id=job_id, mappings=manifest_entries)
        return GenerationResult(
            job_id=job_id,
            output_path=output_path,
            manifest=manifest,
            total_elements=len(manifest_entries),
            generated_elements=len([m for m in manifest_entries if m.status == "mapped"]),
            unmapped_elements=len([m for m in manifest_entries if m.status == "unmapped"]),
            diagnostics=diagnostics,
        )



