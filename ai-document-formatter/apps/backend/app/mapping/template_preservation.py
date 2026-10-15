import logging
import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

import docx
from app.domain.schemas.data_contracts import SourceElement
from app.semantics.models import EnrichedSourceElement

logger = logging.getLogger(__name__)


class PreservedStudent(BaseModel):
    name: str
    reg_no: str
    branch: str = ""


class PreservedFieldExtraction(BaseModel):
    """
    Extracted source content fields intended for deterministic template-slot mapping (Phase D).
    """
    project_batch_id: Optional[str] = None
    project_guide_name: Optional[str] = None
    project_title: Optional[str] = None
    domain: Optional[str] = None
    team_leader_name: Optional[str] = None
    students: List[PreservedStudent] = Field(default_factory=list)
    abstract_paragraphs: List[str] = Field(default_factory=list)
    weekly_meeting: Dict[str, Any] = Field(default_factory=dict)
    consent_details: Dict[str, Any] = Field(default_factory=dict)
    attendance_status: str = "unfilled"
    unresolved_elements: List[Dict[str, Any]] = Field(default_factory=list)
    field_locations: Dict[str, str] = Field(default_factory=dict)


class TemplatePreservationMapper:
    """
    Deterministic Content-to-Template Mapper for Structured Templates (Specification V2, Phase D).
    Extracts high-confidence structured fields from source documents and maps them to concrete
    template slots while preserving unfilled forms, empty cells, and unchanged template substrate.
    """

    def extract_source_fields(
        self,
        source_docx_path: str,
        elements: Optional[List[EnrichedSourceElement]] = None,
    ) -> PreservedFieldExtraction:
        extraction = PreservedFieldExtraction()

        if not os.path.exists(source_docx_path):
            logger.warning(f"Source file not found for preservation mapping: {source_docx_path}")
            return extraction

        try:
            doc = docx.Document(source_docx_path)
        except Exception as e:
            logger.warning(f"Failed to read source document for template preservation: {e}")
            return extraction

        mapped_source_texts = set()

        # 1. Extract from Source Tables (Key-Value metadata and Student lists)
        for tbl in doc.tables:
            rows = [[c.text.strip() for c in r.cells] for r in tbl.rows]
            if not rows:
                continue

            # Check if 2-column key-value table
            if len(rows[0]) == 2:
                for r in rows:
                    if len(r) == 2 and r[0] and r[1]:
                        k = r[0].lower().replace("/", " ").replace("_", " ").strip()
                        val = r[1].strip()
                        mapped_source_texts.add(r[0])
                        mapped_source_texts.add(val)
                        if "batch" in k or "project/batch" in k:
                            extraction.project_batch_id = val
                            extraction.field_locations["project_batch_id"] = "body/tbl[0]/tr[0]/tc[1]"
                        elif "guide name" in k or "guide" in k:
                            extraction.project_guide_name = val
                            extraction.field_locations["project_guide_name"] = "body/tbl[0]/tr[1]/tc[1]"
                        elif "title" in k:
                            extraction.project_title = val
                            extraction.field_locations["project_title"] = "body/tbl[0]/tr[2]/tc[1]"
                        elif "domain" in k:
                            extraction.domain = val
                            extraction.field_locations["domain"] = "body/tbl[0]/tr[3]/tc[1]"
                        elif "leader" in k:
                            extraction.team_leader_name = val
                            extraction.field_locations["team_leader_name"] = "body/tbl[0]/tr[4]/tc[1]"

            # Check if Student Details table
            header_lower = [c.lower() for c in rows[0]]
            if any("name" in c for c in header_lower) and any("reg" in c for c in header_lower):
                name_col = next((i for i, c in enumerate(header_lower) if "name" in c), 0)
                reg_col = next((i for i, c in enumerate(header_lower) if "reg" in c), 1)
                branch_col = next((i for i, c in enumerate(header_lower) if "branch" in c), -1)

                for r in rows[1:]:
                    if len(r) > max(name_col, reg_col):
                        s_name = r[name_col]
                        s_reg = r[reg_col]
                        s_branch = r[branch_col] if branch_col != -1 and len(r) > branch_col else ""
                        mapped_source_texts.add(s_name)
                        mapped_source_texts.add(s_reg)
                        if s_name and s_name.lower() not in ("name", "sl. no.", "signature"):
                            if not any(s.reg_no == s_reg for s in extraction.students if s_reg):
                                extraction.students.append(
                                    PreservedStudent(name=s_name, reg_no=s_reg, branch=s_branch)
                                )

        # 2. Extract from Paragraphs (Key-Value patterns, Abstract, Weekly Meeting, Consent Form)
        in_abstract = False
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        for p_idx, text in enumerate(paras):
            t_lower = text.lower()

            # Abstract detection
            if t_lower == "abstract":
                in_abstract = True
                mapped_source_texts.add(text)
                continue

            if in_abstract:
                if any(t_lower.startswith(k) for k in ["daily attendance", "weekly meeting", "student consent", "review"]):
                    in_abstract = False
                else:
                    extraction.abstract_paragraphs.append(text)
                    mapped_source_texts.add(text)
                    continue

            # Key-Value regex match
            kv_match = re.match(r"^([^:]+):\s*(.+)$", text)
            if kv_match:
                k = kv_match.group(1).lower().replace("/", " ").replace("_", " ").strip()
                v = kv_match.group(2).strip()

                if "academic year" in k and not v.startswith("___"):
                    extraction.consent_details["academic_year"] = v
                    mapped_source_texts.add(text)
                elif "semester" in k and not v.startswith("___"):
                    extraction.consent_details["semester"] = v
                    mapped_source_texts.add(text)
                elif "degree program" in k and not v.startswith("___"):
                    extraction.consent_details["degree_program"] = v
                    mapped_source_texts.add(text)
                elif "guide’s designation" in k or "designation" in k:
                    extraction.consent_details["guide_designation"] = v
                    mapped_source_texts.add(text)
                elif "week no" in k:
                    extraction.weekly_meeting["week_no"] = v
                    mapped_source_texts.add(text)
                elif "meeting venue" in k:
                    v_clean = v.split("|")[0].strip()
                    extraction.weekly_meeting["meeting_venue"] = v_clean
                    mapped_source_texts.add(text)
                elif "project title" in k and not extraction.project_title:
                    extraction.project_title = v
                    mapped_source_texts.add(text)

            # Weekly meeting member line: e.g. "1. Name: ... | Reg. No.: ... | Present: [ ]"
            if "name:" in t_lower and "reg. no" in t_lower:
                mapped_source_texts.add(text)
                m_name = re.search(r"name:\s*([^|]+)", text, re.IGNORECASE)
                m_reg = re.search(r"reg\.?\s*no\.?:\s*([^|]+)", text, re.IGNORECASE)
                if m_name and m_reg:
                    s_name = m_name.group(1).strip()
                    s_reg = m_reg.group(1).strip()
                    if not any(s.reg_no == s_reg for s in extraction.students if s_reg):
                        extraction.students.append(PreservedStudent(name=s_name, reg_no=s_reg))

            # Attendance status note
            if "no attendance entries" in t_lower or "attendance record" in t_lower:
                extraction.attendance_status = "unfilled"
                mapped_source_texts.add(text)

        # Ensure title / guide in consent details if present
        if extraction.project_title:
            extraction.consent_details["project_title"] = extraction.project_title
        if extraction.project_guide_name:
            extraction.consent_details["guide_name"] = extraction.project_guide_name

        # 3. Identify Unresolved Source Elements (Elements with content not mapped to template slots)
        if elements:
            for elem in elements:
                content = elem.text.strip() if elem.text else ""
                if not content or content in mapped_source_texts:
                    continue
                # Ignore institutional headers or boilerplate already in template
                if any(k in content.lower() for k in [
                    "alliance school", "bengaluru", "department of cse", "capstone project",
                    "student details", "project details", "general rules", "declaration",
                    "evaluation form", "signatures"
                ]):
                    continue
                extraction.unresolved_elements.append({
                    "element_id": elem.id,
                    "type": elem.type,
                    "preview": content[:80],
                })

        return extraction
