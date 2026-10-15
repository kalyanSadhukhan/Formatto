from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.domain.schemas.data_contracts import SourceElement


class SemanticRole(str, Enum):
    DOCUMENT_TITLE = "document_title"
    HEADING = "heading"
    BODY_PARAGRAPH = "body_paragraph"
    BULLET_LIST_ITEM = "bullet_list_item"
    NUMBERED_LIST_ITEM = "numbered_list_item"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    REFERENCE = "reference"
    UNSUPPORTED = "unsupported"


class ClassificationMethod(str, Enum):
    DETERMINISTIC_RULE = "rule"
    STYLE_EVIDENCE = "style"
    LLM = "llm"
    FALLBACK = "fallback"


class ClassificationProvenance(str, Enum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"
    FALLBACK = "FALLBACK"


class SemanticAnnotation(BaseModel):
    element_id: str
    semantic_role: SemanticRole
    level: int = 0
    confidence: float = Field(ge=0.0, le=1.0)
    method: ClassificationMethod
    provenance: ClassificationProvenance
    is_ambiguous: bool = False
    evidence: Dict[str, Any] = Field(default_factory=dict)
    original_type: str
    original_style: Optional[str] = None


class EnrichedSourceElement(SourceElement):
    """
    Enriched SourceElement representing an extracted document block with semantic role annotation.
    Preserves all original extracted fields (id, type, level, text, source_order, style_name,
    confidence, metadata) without mutation.
    """
    semantic_role: SemanticRole
    semantic_confidence: float = Field(ge=0.0, le=1.0)
    semantic_method: ClassificationMethod
    semantic_provenance: ClassificationProvenance
    is_ambiguous: bool = False
    semantic_evidence: Dict[str, Any] = Field(default_factory=dict)


class LLMSemanticClassification(BaseModel):
    """
    Strict validation schema for LLM semantic classification output.
    Any response from the LLM provider must parse and validate against this model.
    """
    element_id: str
    semantic_role: SemanticRole
    level: int = Field(default=0, ge=0, le=6)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="Evidence or reasoning justifying the semantic classification")


class SemanticAnalysisResult(BaseModel):
    """
    Output artifact for Phase 4 semantic analysis.
    """
    document_id: str
    total_elements: int
    ambiguous_elements_count: int
    llm_classified_count: int
    deterministic_classified_count: int
    role_counts: Dict[str, int] = Field(default_factory=dict)
    method_counts: Dict[str, int] = Field(default_factory=dict)
    elements: List[EnrichedSourceElement] = Field(default_factory=list)
    processing_metadata: Dict[str, Any] = Field(default_factory=dict)
