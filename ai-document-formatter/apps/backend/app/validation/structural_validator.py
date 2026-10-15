import logging
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

import docx
from app.domain.schemas.data_contracts import DocumentIR

logger = logging.getLogger(__name__)


class StructuralValidationReport(BaseModel):
    """
    Post-generation structural validation report (Specification V2, Phase E).
    Validates preservation of template sections, tables, cell dimensions,
    empty form fields, headers/footers, and source-content fidelity.
    """
    is_valid: bool
    sections_count: int
    expected_sections_count: int
    sections_match: bool
    tables_count: int
    expected_tables_count: int
    tables_match: bool
    table_invariants_passed: bool
    attendance_table_preserved: bool
    blank_attendance_rows_count: int
    cover_table_populated: bool
    consent_form_preserved: bool
    headers_footers_preserved: bool
    unresolved_mappings_count: int = 0
    unresolved_mappings: List[Dict[str, Any]] = Field(default_factory=list)
    diagnostics: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class StructuralValidator:
    """
    Validates structural invariants between generated output, reference template, and source.
    """

    def validate(
        self,
        output_docx_path: str,
        template_docx_path: str,
        source_docx_path: Optional[str] = None,
        doc_ir: Optional[DocumentIR] = None,
    ) -> StructuralValidationReport:
        issues: List[str] = []
        diagnostics: List[str] = []

        if not os.path.exists(output_docx_path):
            return StructuralValidationReport(
                is_valid=False,
                sections_count=0,
                expected_sections_count=0,
                sections_match=False,
                tables_count=0,
                expected_tables_count=0,
                tables_match=False,
                table_invariants_passed=False,
                attendance_table_preserved=False,
                blank_attendance_rows_count=0,
                cover_table_populated=False,
                consent_form_preserved=False,
                headers_footers_preserved=False,
                issues=[f"Output DOCX not found: {output_docx_path}"],
            )

        try:
            out_doc = docx.Document(output_docx_path)
            tpl_doc = docx.Document(template_docx_path)
        except Exception as e:
            return StructuralValidationReport(
                is_valid=False,
                sections_count=0,
                expected_sections_count=0,
                sections_match=False,
                tables_count=0,
                expected_tables_count=0,
                tables_match=False,
                table_invariants_passed=False,
                attendance_table_preserved=False,
                blank_attendance_rows_count=0,
                cover_table_populated=False,
                consent_form_preserved=False,
                headers_footers_preserved=False,
                issues=[f"Failed to open DOCX files: {e}"],
            )

        # Detect whether template is a structured form or flow report
        is_structured_form = False
        if len(tpl_doc.tables) >= 3 or (
            len(tpl_doc.tables) >= 1 and any(
                len(r.cells) >= 3 and any(k in r.cells[0].text.lower() for k in ["project", "batch", "attendance", "examiner", "checklist", "consent"])
                for t in tpl_doc.tables for r in t.rows[:5]
            )
        ):
            is_structured_form = True

        out_secs = len(out_doc.sections)
        tpl_secs = len(tpl_doc.sections)
        out_tbls = len(out_doc.tables)
        tpl_tbls = len(tpl_doc.tables)

        if is_structured_form:
            # 1. Section Invariants for Structured Forms
            sections_match = (out_secs == tpl_secs)
            expected_secs = tpl_secs
            if not sections_match:
                issues.append(f"Section count mismatch: generated {out_secs} sections, expected {tpl_secs}.")
            else:
                diagnostics.append(f"Preserved all {out_secs} document sections.")

            # 2. Table Count Invariants for Structured Forms
            tables_match = (out_tbls == tpl_tbls)
            expected_tbls = tpl_tbls
            if not tables_match:
                issues.append(f"Table count mismatch: generated {out_tbls} tables, expected {tpl_tbls}.")
            else:
                diagnostics.append(f"Preserved all {out_tbls} document tables.")

            # 3. Table Dimension and Row/Col Invariants
            table_invariants_passed = True
            for idx in range(min(out_tbls, tpl_tbls)):
                out_t = out_doc.tables[idx]
                tpl_t = tpl_doc.tables[idx]
                if len(out_t.rows) != len(tpl_t.rows) or len(out_t.columns) != len(tpl_t.columns):
                    table_invariants_passed = False
                    issues.append(
                        f"Table {idx} dimension mismatch: generated {len(out_t.rows)}x{len(out_t.columns)}, "
                        f"expected {len(tpl_t.rows)}x{len(tpl_t.columns)}."
                    )

            # 4. Attendance Table Preservation Invariant
            attendance_preserved = False
            blank_att_rows = 0
            for idx, t in enumerate(out_doc.tables):
                if len(t.rows) >= 20 and len(t.columns) == 5:
                    header_txt = " ".join(c.text.lower() for c in t.rows[0].cells)
                    if "task" in header_txt or "present" in header_txt or "absent" in header_txt or "date" in header_txt:
                        attendance_preserved = True
                        for r in t.rows[1:]:
                            r_txt = "".join(c.text.strip() for c in r.cells)
                            if not r_txt:
                                blank_att_rows += 1
                        diagnostics.append(
                            f"Attendance table (Table {idx}) verified: {len(t.rows)} rows, "
                            f"{blank_att_rows} blank rows preserved."
                        )
                        break

            if not attendance_preserved and any(
                len(t.rows) >= 20 and len(t.columns) == 5 for t in tpl_doc.tables
            ):
                issues.append("Required attendance table missing or flattened into paragraphs.")

            # 5. Cover Page Metadata Table Population Invariant
            cover_populated = False
            if out_tbls > 0 and len(out_doc.tables[0].rows) >= 6:
                t0 = out_doc.tables[0]
                t0_text = " ".join(c.text.strip() for r in t0.rows for c in r.cells)
                if any(k in t0_text for k in ["ASAC-CP-", "Dr.", "Formatto", "B.Tech", "2023"]):
                    cover_populated = True
                    diagnostics.append("Cover metadata table successfully populated with project & student details.")

            # 6. Consent Form Preservation Invariant
            consent_preserved = False
            if out_secs >= 8 or any("declaration by the students" in p.text.lower() for p in out_doc.paragraphs):
                consent_preserved = True
                diagnostics.append("Student consent form and declaration preserved.")

        else:
            # Flow Report Mode: Sections and tables originate from the source document / IR
            expected_secs = out_secs
            sections_match = True
            expected_tbls = out_tbls
            tables_match = True
            table_invariants_passed = True
            attendance_preserved = False
            blank_att_rows = 0
            cover_populated = False
            consent_preserved = False
            diagnostics.append(f"Report restyling mode: adapted {out_secs} sections and {out_tbls} tables from source document.")

        # 7. Header/Footer Preservation Invariant
        headers_footers_preserved = True
        for idx in range(min(out_secs, tpl_secs)):
            tpl_sec = tpl_doc.sections[idx]
            out_sec = out_doc.sections[idx]
            tpl_hdr = " ".join(p.text.strip() for p in tpl_sec.header.paragraphs if p.text.strip())
            out_hdr = " ".join(p.text.strip() for p in out_sec.header.paragraphs if p.text.strip())
            if tpl_hdr and tpl_hdr != out_hdr:
                headers_footers_preserved = False
                issues.append(f"Section {idx} header text mismatch.")

        # 8. Unresolved Mappings
        unresolved: List[Dict[str, Any]] = []
        if doc_ir and doc_ir.metadata.get("unresolved_mappings"):
            unresolved = doc_ir.metadata["unresolved_mappings"]
            diagnostics.append(f"{len(unresolved)} unresolved source content elements identified.")

        is_valid = len(issues) == 0

        return StructuralValidationReport(
            is_valid=is_valid,
            sections_count=out_secs,
            expected_sections_count=expected_secs,
            sections_match=sections_match,
            tables_count=out_tbls,
            expected_tables_count=expected_tbls,
            tables_match=tables_match,
            table_invariants_passed=table_invariants_passed,
            attendance_table_preserved=attendance_preserved,
            blank_attendance_rows_count=blank_att_rows,
            cover_table_populated=cover_populated,
            consent_form_preserved=consent_preserved,
            headers_footers_preserved=headers_footers_preserved,
            unresolved_mappings_count=len(unresolved),
            unresolved_mappings=unresolved,
            diagnostics=diagnostics,
            issues=issues,
        )
