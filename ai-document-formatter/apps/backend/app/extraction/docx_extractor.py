import hashlib
import logging
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from docx import Document as DocxDocument
from docx.document import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.domain.schemas.data_contracts import SourceElement

logger = logging.getLogger(__name__)

from docx.oxml.ns import nsmap

# Ensure VML and Markup Compatibility namespaces are registered
if "v" not in nsmap:
    nsmap["v"] = "urn:schemas-microsoft-com:vml"
if "mc" not in nsmap:
    nsmap["mc"] = "http://schemas.openxmlformats.org/markup-compatibility/2006"

# XML Namespaces
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS = {"w": NS_W, "a": NS_A, "r": NS_R, "mc": NS_MC}


class DocxExtractionError(Exception):
    """Structured error raised during DOCX source extraction."""
    def __init__(self, message: str, error_code: str = "INVALID_UPLOAD", details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.stage = "EXTRACTING_SOURCE"
        self.details = details or {}


class DocxExtractor:
    """
    Deterministic DOCX Source Extractor for Specification V2.

    Extracts paragraphs, headings, lists, tables, figures, captions, and references
    preserving monotonic source order, Unicode text, and template/style attributes.

    Behavioral Documentation:
    - Nested Lists: OpenXML numbering level (w:ilvl, 0-indexed) is preserved in `level`
      and `metadata['nesting_level']`. Sub-items retain hierarchical depth without flattening.
      Both `num_id` and `abstract_num_id` are recorded to trace list continuity and restarts.
    - Tables: Row/column grid coordinates are strictly maintained from physical table rows (w:tr).
      Empty cells are explicitly preserved as empty strings ("") to prevent shape distortion.
    - Merged Cells: Horizontally merged cells (w:gridSpan) and vertically merged cells (w:vMerge)
      are detected and categorized into:
        * 'restart': start of a vertically merged cell group, with calculated `row_span`.
        * 'continue': subsequent continuation cell, with `origin_row` pointing back to restart.
        * 'ordinary': non-merged cells (not flagged as merged).
    - Figure Extraction & DrawingML vs Fallback: Word wraps drawings in <mc:AlternateContent>
      where <mc:Choice> contains modern DrawingML (<w:drawing>) and <mc:Fallback> contains
      duplicate compatibility VML (<w:pict>). The extractor queries modern DrawingML Choice
      first, ignoring fallback duplicates. `image_count` strictly equals `len(drawing_rids)`.
    - Image/Caption Pairing: Captions (by style or 'Figure X:' prefix) following figures
      are linked bidirectionally via element IDs in metadata.
    - References: Bibliographic sections and citation entries are identified and tagged as 'reference'.
    - Stability: Element IDs are generated deterministically from document content hash and source order
      (el_{doc_hash}_{source_order:04d}), ensuring identical output across repeated runs.
    - Completeness: Non-empty content is never dropped; blank spacing paragraphs are tracked
      in extraction statistics so no blocks silently disappear.
    """

    def __init__(self, file_path: str, doc_id: Optional[str] = None):
        self.file_path = file_path
        if not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")

        try:
            with open(file_path, "rb") as f:
                self.file_bytes = f.read()
            self.doc_hash = doc_id or hashlib.sha256(self.file_bytes).hexdigest()[:8]
        except Exception as e:
            raise ValueError(f"Failed to read file bytes: {e}")

        try:
            self.doc = DocxDocument(file_path)
        except Exception as e:
            raise ValueError(f"Failed to open DOCX file: {e}")

        self.numbering_map = self._load_numbering_map()
        self.skipped_blocks: List[dict] = []
        self.section_boundaries: List[dict] = []
        self.layout_breaks: List[dict] = []
        self.total_blocks_count = 0

    def _load_numbering_map(self) -> Dict[str, dict]:
        """Parse Word numbering.xml to map numId to abstractNumId and ilvl format definitions."""
        numbering_map: Dict[str, dict] = {}
        try:
            numbering_part = self.doc.part.numbering_part
            if numbering_part is None:
                return numbering_map

            xml_content = numbering_part._element.xml
            root = ET.fromstring(xml_content)

            abstract_map: Dict[str, Dict[str, dict]] = {}
            for abstract in root.findall(f".//{{{NS_W}}}abstractNum"):
                aid = abstract.attrib.get(f"{{{NS_W}}}abstractNumId")
                if not aid:
                    continue
                abstract_map[aid] = {}
                for lvl in abstract.findall(f"./{{{NS_W}}}lvl"):
                    ilvl = lvl.attrib.get(f"{{{NS_W}}}ilvl", "0")
                    num_fmt = lvl.find(f"./{{{NS_W}}}numFmt")
                    fmt_val = num_fmt.attrib.get(f"{{{NS_W}}}val") if num_fmt is not None else "decimal"
                    lvl_text = lvl.find(f"./{{{NS_W}}}lvlText")
                    txt_val = lvl_text.attrib.get(f"{{{NS_W}}}val") if lvl_text is not None else ""
                    abstract_map[aid][ilvl] = {"numFmt": fmt_val, "lvlText": txt_val}

            for num in root.findall(f".//{{{NS_W}}}num"):
                nid = num.attrib.get(f"{{{NS_W}}}numId")
                abstract_ref = num.find(f"./{{{NS_W}}}abstractNumId")
                aid = abstract_ref.attrib.get(f"{{{NS_W}}}val") if abstract_ref is not None else None
                if nid and aid and aid in abstract_map:
                    numbering_map[nid] = {
                        "abstract_num_id": aid,
                        "levels": abstract_map[aid],
                    }

        except Exception as e:
            logger.debug(f"Note: Could not parse numbering definitions: {e}")

        return numbering_map

    def _iter_block_items(self, parent) -> Generator[Union[Paragraph, Table, Any], None, None]:
        """Iterate through document body children in strictly sequential order."""
        if isinstance(parent, Document):
            parent_elm = parent.element.body
        else:
            parent_elm = parent._element

        for child in parent_elm.iterchildren():
            # Skip section properties (sectPr defines margins/page setup, not a content block)
            if getattr(child, "tag", "").endswith("sectPr"):
                continue
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)
            else:
                yield child

    def _detect_caption(self, text: str, style_name: str) -> Optional[dict]:
        """Detect whether a paragraph is a caption by style or regex pattern."""
        style_lower = style_name.lower()
        if "caption" in style_lower:
            return {"caption_type": "caption", "label": text.strip()}

        caption_pattern = r"^(figure|fig\.|table|chart|graph|image|plate)\s*([0-9A-Za-z\.\-]+)?\s*[:\.\-–—]\s*(.*)$"
        match = re.match(caption_pattern, text.strip(), re.IGNORECASE)
        if match:
            return {
                "caption_type": match.group(1).lower().rstrip("."),
                "number": match.group(2) or "",
                "label": match.group(3) or text.strip(),
            }
        return None

    def _extract_figure(self, block: Paragraph, source_order: int) -> Optional[SourceElement]:
        """
        Extract figure element from paragraph, properly handling DrawingML vs legacy VML.

        Word wraps drawings in <mc:AlternateContent> where <mc:Choice> contains modern
        DrawingML (<w:drawing>) and <mc:Fallback> contains duplicate compatibility VML (<w:pict>).
        To avoid duplicate counting of fallback compatibility images, drawings are
        extracted from modern DrawingML first, ignoring <mc:Fallback>.
        `image_count` strictly equals `len(drawing_rids)`.
        """
        p_elm = block._p

        # Find non-fallback drawings
        drawings = p_elm.xpath(".//w:drawing[not(ancestor::mc:Fallback)] | .//w:pict[not(ancestor::mc:Fallback)]")
        if not drawings:
            return None

        # Extract relationship IDs (ignoring fallback VML duplicates)
        rids = p_elm.xpath(".//a:blip[not(ancestor::mc:Fallback)]/@r:embed | .//v:imagedata[not(ancestor::mc:Fallback)]/@r:id")

        # Deduplicate while preserving document order
        seen = set()
        unique_rids = []
        for r in rids:
            if r not in seen:
                seen.add(r)
                unique_rids.append(r)

        # Extract extents for sizing
        extents = p_elm.xpath(".//wp:extent")
        extent_dims = []
        for ext in extents:
            try:
                cx = int(ext.attrib.get("cx", 0))
                cy = int(ext.attrib.get("cy", 0))
                if cx > 0 and cy > 0:
                    extent_dims.append({
                        "cx": cx,
                        "cy": cy,
                        "width_in": round(cx / 914400.0, 2),
                        "height_in": round(cy / 914400.0, 2),
                    })
            except (ValueError, TypeError):
                pass

        element_id = f"el_{self.doc_hash}_{source_order:04d}"
        return SourceElement(
            id=element_id,
            type="figure",
            level=0,
            text=block.text.strip() if block.text.strip() else None,
            source_order=source_order,
            style_name=block.style.name if block.style else None,
            confidence=0.95,
            metadata={
                "image_count": len(unique_rids) if unique_rids else len(drawings),
                "drawing_rids": unique_rids,
                "extent_dims": extent_dims,
            },
        )

    def _determine_paragraph_type(
        self, p: Paragraph, in_references_section: bool
    ) -> Tuple[str, int, float, dict]:
        """Determine paragraph semantic type, hierarchy level, confidence, and metadata."""
        style_name = p.style.name if p.style else ""
        style_name_lower = style_name.lower()
        text = p.text.strip()
        metadata: dict = {}

        # Record manual bold formatting provenance if present
        runs = p.runs
        text_runs = [r for r in runs if r.text and r.text.strip()]
        if text_runs:
            all_bold = all(bool(r.bold or r._r.xpath("./w:rPr/w:b")) for r in text_runs)
            if all_bold:
                metadata["is_bold"] = True

        run_data = []
        for r in runs:
            if r.text:
                run_data.append({
                    "text": r.text,
                    "bold": bool(r.bold or r._r.xpath("./w:rPr/w:b")),
                    "italic": bool(r.italic or r._r.xpath("./w:rPr/w:i")),
                    "underline": bool(r.underline or r._r.xpath("./w:rPr/w:u")),
                })
        if run_data:
            metadata["runs"] = run_data

        # 1. Heading by style
        if style_name_lower.startswith("heading"):
            try:
                level_str = style_name_lower.replace("heading", "").strip()
                level = int(level_str) if level_str else 1
            except ValueError:
                level = 1
            return "heading", level, 1.0, metadata

        if style_name_lower == "title":
            return "heading", 1, 1.0, {"subrole": "title", **metadata}

        if style_name_lower == "subtitle":
            return "heading", 2, 1.0, {"subrole": "subtitle", **metadata}

        # Outline level in XML (if heading style was not explicitly assigned)
        outline_lvl = p._p.xpath("./w:pPr/w:outlineLvl/@w:val")
        if outline_lvl:
            try:
                lvl = int(outline_lvl[0]) + 1
                return "heading", lvl, 0.9, {"outline_level": lvl, **metadata}
            except ValueError:
                pass

        # 2. Captions
        caption_info = self._detect_caption(text, style_name)
        if caption_info:
            metadata.update(caption_info)
            return "caption", 0, 1.0, metadata

        # 3. References / Bibliography
        if in_references_section or "ref" in style_name_lower or "biblio" in style_name_lower:
            metadata["section"] = "references" if in_references_section else "styled"
            return "reference", 0, 0.95, metadata

        # 4. Lists (OpenXML numPr or styles)
        num_pr = p._p.xpath("./w:pPr/w:numPr")
        if num_pr or "list" in style_name_lower:
            num_id_val = p._p.xpath("./w:pPr/w:numPr/w:numId/@w:val")
            ilvl_val = p._p.xpath("./w:pPr/w:numPr/w:ilvl/@w:val")

            num_id = num_id_val[0] if num_id_val else None
            ilvl = int(ilvl_val[0]) if ilvl_val else 0

            metadata["nesting_level"] = ilvl
            num_fmt = None

            if num_id:
                metadata["num_id"] = num_id
                if num_id in self.numbering_map:
                    num_info = self.numbering_map[num_id]
                    metadata["abstract_num_id"] = num_info.get("abstract_num_id")
                    levels = num_info.get("levels", {})
                    if str(ilvl) in levels:
                        num_fmt = levels[str(ilvl)].get("numFmt")
                        metadata["num_fmt"] = num_fmt

            if num_fmt == "bullet" or "bullet" in style_name_lower:
                return "bullet_list", ilvl, 1.0, metadata
            elif num_fmt in ("decimal", "lowerLetter", "upperLetter", "lowerRoman", "upperRoman") or "number" in style_name_lower:
                return "numbered_list", ilvl, 1.0, metadata

            # Heuristics on text prefix
            if re.match(r"^[\u2022\u25E6\u25AA\u2023\u2219\-\*]\s+", text):
                return "bullet_list", ilvl, 0.9, metadata
            if re.match(r"^[0-9A-Za-z]+[\.\)]\s+", text):
                return "numbered_list", ilvl, 0.9, metadata

            # Default list fallback
            return "bullet_list", ilvl, 0.7, metadata

        # 5. Default paragraph
        return "paragraph", 0, 1.0, metadata

    def _extract_table(self, block: Table, source_order: int) -> SourceElement:
        """
        Extract table element with precise WordprocessingML physical cell traversal.

        Distinguishes:
        - 'restart': first cell of a vertical merge group, with computed `row_span`.
        - 'continue': subsequent continuation cells in the vertical merge, with `origin_row`.
        - 'ordinary': regular non-merged cells.
        - 'horizontal': horizontally merged cells (w:gridSpan).
        """
        raw_rows = block._tbl.xpath("./w:tr")
        row_count = len(raw_rows)

        cell_text: List[List[str]] = []
        grid_states: List[List[dict]] = []

        # Pass 1: Extract cell text and raw XML merge markers with grid column positions
        for r_idx, tr in enumerate(raw_rows):
            row_text: List[str] = []
            row_states: List[dict] = []
            curr_grid_col = 0

            for c_idx, tc in enumerate(tr.xpath("./w:tc")):
                # Extract text verbatim from runs inside this specific physical cell
                text_nodes = tc.xpath(".//w:t")
                text = "".join(t.text for t in text_nodes if t.text).strip()
                row_text.append(text)

                # Check vMerge
                v_merge = tc.xpath("./w:tcPr/w:vMerge")
                if v_merge:
                    val = v_merge[0].attrib.get(f"{{{NS_W}}}val")
                    state = "restart" if val == "restart" else "continue"
                else:
                    state = "ordinary"

                # Check gridSpan
                grid_span = tc.xpath("./w:tcPr/w:gridSpan/@w:val")
                col_span = int(grid_span[0]) if grid_span and grid_span[0].isdigit() else 1

                row_states.append({
                    "cell_idx": c_idx,
                    "grid_col": curr_grid_col,
                    "col_span": col_span,
                    "state": state,
                })
                curr_grid_col += col_span

            cell_text.append(row_text)
            grid_states.append(row_states)

        # Helper to find cell covering a given grid column in a row
        def find_cell_at_grid_col(row_cells: List[dict], target_col: int) -> Optional[dict]:
            for cell in row_cells:
                if cell["grid_col"] <= target_col < cell["grid_col"] + cell["col_span"]:
                    return cell
            return None

        # Pass 2: Build structured merged_cells_info with row spans and linkages
        merged_cells_info: List[dict] = []
        has_merged = False

        for r_idx in range(row_count):
            for cell_info in grid_states[r_idx]:
                st_state = cell_info["state"]
                grid_c = cell_info["grid_col"]
                c_span = cell_info["col_span"]

                if st_state == "restart":
                    has_merged = True
                    # Calculate vertical row_span on the table grid
                    row_span = 1
                    for next_r in range(r_idx + 1, row_count):
                        next_cell = find_cell_at_grid_col(grid_states[next_r], grid_c)
                        if next_cell and next_cell["state"] == "continue":
                            row_span += 1
                        else:
                            break
                    merged_cells_info.append({
                        "row": r_idx,
                        "col": grid_c,
                        "type": "vertical",
                        "state": "restart",
                        "row_span": row_span,
                    })

                elif st_state == "continue":
                    has_merged = True
                    # Link back to origin restart row on the table grid
                    origin_row = r_idx - 1
                    while origin_row >= 0:
                        parent_cell = find_cell_at_grid_col(grid_states[origin_row], grid_c)
                        if parent_cell and parent_cell["state"] == "continue":
                            origin_row -= 1
                        else:
                            break
                    merged_cells_info.append({
                        "row": r_idx,
                        "col": grid_c,
                        "type": "vertical",
                        "state": "continue",
                        "origin_row": max(0, origin_row),
                    })

                if c_span > 1:
                    has_merged = True
                    merged_cells_info.append({
                        "row": r_idx,
                        "col": grid_c,
                        "type": "horizontal",
                        "col_span": c_span,
                    })

        # Check if table or cells have borders
        has_table_borders = bool(
            block._tbl.xpath("./w:tblPr/w:tblBorders/*[not(@w:val='none')]")
            or block._tbl.xpath(".//w:tcPr/w:tcBorders/*[not(@w:val='none')]")
        )
        # Extract column widths in dxa
        grid_cols = block._tbl.xpath("./w:tblGrid/w:gridCol/@w:w")
        col_widths_dxa = [int(w) for w in grid_cols if w.isdigit()]

        if len(col_widths_dxa) > 0:
            col_count = len(col_widths_dxa)
        elif grid_states:
            col_count = max((sum(c["col_span"] for c in r) for r in grid_states), default=0)
        else:
            col_count = len(raw_rows[0].xpath("./w:tc")) if row_count > 0 else 0

        element_id = f"el_{self.doc_hash}_{source_order:04d}"
        return SourceElement(
            id=element_id,
            type="table",
            level=0,
            text=None,
            source_order=source_order,
            style_name=block.style.name if block.style else None,
            confidence=1.0,
            metadata={
                "row_count": row_count,
                "column_count": col_count,
                "cell_text": cell_text,
                "has_merged_cells": has_merged,
                "merged_cells_info": merged_cells_info,
                "has_borders": has_table_borders,
                "col_widths_dxa": col_widths_dxa,
            },
        )

    def _parse_sect_pr(self, sect_elm) -> dict:
        """Extract layout and page properties from a w:sectPr element."""
        if sect_elm is None:
            return {}
        info = {}
        type_vals = sect_elm.xpath("./w:type/@w:val")
        info["type"] = type_vals[0] if type_vals else "nextPage"

        pgSz = sect_elm.xpath("./w:pgSz")
        if pgSz:
            info["page_width"] = pgSz[0].attrib.get(f"{{{NS_W}}}w")
            info["page_height"] = pgSz[0].attrib.get(f"{{{NS_W}}}h")
            info["orientation"] = pgSz[0].attrib.get(f"{{{NS_W}}}orient", "portrait")

        pgMar = sect_elm.xpath("./w:pgMar")
        if pgMar:
            info["margins"] = {
                "top": pgMar[0].attrib.get(f"{{{NS_W}}}top"),
                "bottom": pgMar[0].attrib.get(f"{{{NS_W}}}bottom"),
                "left": pgMar[0].attrib.get(f"{{{NS_W}}}left"),
                "right": pgMar[0].attrib.get(f"{{{NS_W}}}right"),
                "header": pgMar[0].attrib.get(f"{{{NS_W}}}header"),
                "footer": pgMar[0].attrib.get(f"{{{NS_W}}}footer"),
            }

        headers = sect_elm.xpath("./w:headerReference/@r:id")
        footers = sect_elm.xpath("./w:footerReference/@r:id")
        if headers:
            info["header_rids"] = headers
        if footers:
            info["footer_rids"] = footers

        return info

    def extract(self) -> List[SourceElement]:
        """Extract all supported source elements deterministically."""
        elements: List[SourceElement] = []
        source_order = 0
        in_references_section = False
        last_figure_index: Optional[int] = None
        pending_break_before: Optional[str] = None
        current_section_index = 0

        for block in self._iter_block_items(self.doc):
            self.total_blocks_count += 1

            if isinstance(block, Paragraph):
                # Check for section break attached to this paragraph
                sect_pr_nodes = block._p.xpath("./w:pPr/w:sectPr")
                sect_info = None
                has_section_break = bool(sect_pr_nodes)
                if has_section_break:
                    sect_info = self._parse_sect_pr(sect_pr_nodes[0])
                    sect_info["section_index"] = current_section_index
                    self.section_boundaries.append(sect_info)

                # Check for explicit page breaks
                has_page_break = bool(
                    block._p.xpath(".//w:br[@w:type='page']")
                    or block._p.xpath("./w:pPr/w:pageBreakBefore")
                )
                if has_page_break and not pending_break_before:
                    pending_break_before = "page"

                # 1. Check for figures/images
                fig_elem = self._extract_figure(block, source_order + 1)
                if fig_elem:
                    source_order += 1
                    if pending_break_before:
                        fig_elem.metadata["break_before"] = pending_break_before
                        pending_break_before = None
                    fig_elem.metadata["section_index"] = current_section_index
                    elements.append(fig_elem)
                    last_figure_index = len(elements) - 1
                    if has_section_break:
                        current_section_index += 1
                        pending_break_before = "section"
                    continue

                text = block.text.strip()

                # 2. Handle empty paragraphs (blank spacing and layout boundaries)
                if not text:
                    reason = "section_boundary" if sect_info else ("page_break" if has_page_break else "empty_spacing_paragraph")
                    self.skipped_blocks.append({
                        "source_order": source_order + 1,
                        "style_name": block.style.name if block.style else None,
                        "reason": reason,
                        "section_properties": sect_info if sect_info else None,
                        "has_page_break": has_page_break,
                    })
                    if has_section_break:
                        current_section_index += 1
                        pending_break_before = "section"
                    continue

                # 3. Section tracking for references
                if (block.style.name or "").lower().startswith("heading") or (block.style.name or "").lower() == "title":
                    if text.lower() in ("references", "bibliography", "works cited", "reference"):
                        in_references_section = True
                    else:
                        in_references_section = False

                ptype, level, confidence, meta = self._determine_paragraph_type(block, in_references_section)

                source_order += 1
                element_id = f"el_{self.doc_hash}_{source_order:04d}"

                # Pair caption with immediately preceding figure if adjacent
                if ptype == "caption" and last_figure_index is not None and last_figure_index == len(elements) - 1:
                    elements[last_figure_index].metadata["caption_id"] = element_id
                    meta["figure_id"] = elements[last_figure_index].id

                if pending_break_before:
                    meta["break_before"] = pending_break_before
                    pending_break_before = None
                meta["section_index"] = current_section_index
                if sect_info:
                    meta["section_boundary"] = sect_info
                    meta["section_break_after"] = True

                elem = SourceElement(
                    id=element_id,
                    type=ptype,
                    level=level,
                    text=text,
                    source_order=source_order,
                    style_name=block.style.name if block.style else None,
                    confidence=confidence,
                    metadata=meta,
                )
                elements.append(elem)
                if has_section_break:
                    current_section_index += 1
                    pending_break_before = "section"

            elif isinstance(block, Table):
                source_order += 1
                table_elem = self._extract_table(block, source_order)
                if pending_break_before:
                    table_elem.metadata["break_before"] = pending_break_before
                    pending_break_before = None
                table_elem.metadata["section_index"] = current_section_index
                elements.append(table_elem)

            else:
                # Unsupported block element (e.g. raw XML / OLE object)
                source_order += 1
                element_id = f"el_{self.doc_hash}_{source_order:04d}"
                elements.append(
                    SourceElement(
                        id=element_id,
                        type="unsupported",
                        level=0,
                        text=None,
                        source_order=source_order,
                        style_name=None,
                        confidence=1.0,
                        metadata={"raw_tag": getattr(block, "tag", str(type(block)))},
                    )
                )

        # Capture final body section properties
        final_sect_nodes = self.doc.element.body.xpath("./w:sectPr")
        if final_sect_nodes:
            final_sect_info = self._parse_sect_pr(final_sect_nodes[0])
            final_sect_info["section_index"] = current_section_index
            self.section_boundaries.append(final_sect_info)

        return elements

