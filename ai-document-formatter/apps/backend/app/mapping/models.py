from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.domain.schemas.data_contracts import ContentTemplateMapping, DocumentIR, IRElement
from app.semantics.models import EnrichedSourceElement, SemanticRole
from app.templates.models import TemplateProfile


class ElementMappingResult(BaseModel):
    """
    Rich mapping result for an individual document element.
    Combines the official ContentTemplateMapping contract with preserved source element data,
    applied constraint IDs partitioned by enforceability, and diagnostic tracing.
    """
    mapping: ContentTemplateMapping
    source_element: EnrichedSourceElement
    target_role: str
    target_style: Optional[str] = None
    fallback_applied: bool = False
    fallback_reason: Optional[str] = None
    enforceable_constraint_ids: List[str] = Field(default_factory=list)
    advisory_constraint_ids: List[str] = Field(default_factory=list)
    diagnostics: List[str] = Field(default_factory=list)


class DocumentMappingResult(BaseModel):
    """
    Overall result container for source-to-template mapping (Phase 5).
    """
    document_id: str
    template_id: str
    total_elements: int
    accepted_count: int
    ambiguous_count: int
    rejected_count: int
    fallback_count: int
    elements: List[ElementMappingResult] = Field(default_factory=list)
    mappings: List[ContentTemplateMapping] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)

    def to_document_ir(self) -> DocumentIR:
        """
        Convert the mapping result directly into a valid DocumentIR instance
        conforming to docs/03_DATA_CONTRACTS.md.
        """
        ir_elements: List[IRElement] = []

        for em in self.elements:
            src = em.source_element
            target_id = f"target_{src.id}"

            # Preserve children / metadata structure for tables and figures
            children: List[Any] = []
            if src.type == "table":
                children = src.metadata.get("cell_text", [])
            elif src.type == "figure":
                children = src.metadata.get("drawing_rids", [])

            # Build rich element metadata preserving source properties, runs, merges, and diagnostics
            elem_metadata = dict(src.metadata)
            elem_metadata.update({
                "source_element_id": src.id,
                "source_order": src.source_order,
                "mapping_status": em.mapping.status,
                "confidence": em.mapping.confidence,
                "fallback_applied": em.fallback_applied,
                "fallback_reason": em.fallback_reason,
                "diagnostics": em.diagnostics,
                "is_ambiguous": src.metadata.get("semantic", {}).get("is_ambiguous", False),
            })

            ir_elem = IRElement(
                id=f"ir_{src.id}",
                type=em.target_role,
                level=src.level,
                content=src.text,
                style_ref=em.target_style,
                children=children,
                target_id=target_id,
                metadata=elem_metadata,
            )
            ir_elements.append(ir_elem)

        meta = {
            "template_id": self.template_id,
            "total_elements": self.total_elements,
            "accepted_count": self.accepted_count,
            "ambiguous_count": self.ambiguous_count,
            "fallback_count": self.fallback_count,
        }
        meta.update(self.summary)

        return DocumentIR(
            document_id=self.document_id,
            metadata=meta,
            page_constraints=[],
            styles={},
            elements=ir_elements,
        )

