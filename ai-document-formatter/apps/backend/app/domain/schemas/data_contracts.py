from pydantic import BaseModel, Field
from typing import List, Optional, Any, Literal
from enum import Enum

class JobState(str, Enum):
    CREATED = "CREATED"
    UPLOADING = "UPLOADING"
    EXTRACTING_SOURCE = "EXTRACTING_SOURCE"
    ANALYZING_SOURCE = "ANALYZING_SOURCE"
    EXTRACTING_TEMPLATE = "EXTRACTING_TEMPLATE"
    MAPPING = "MAPPING"
    BUILDING_IR = "BUILDING_IR"
    VALIDATING_IR = "VALIDATING_IR"
    GENERATING_DOCX = "GENERATING_DOCX"
    VALIDATING_DOCX = "VALIDATING_DOCX"
    CONVERTING_PDF = "CONVERTING_PDF"
    COMPLETED = "COMPLETED"
    CORRECTION_PENDING = "CORRECTION_PENDING"
    CORRECTING = "CORRECTING"
    FAILED = "FAILED"

class SourceElement(BaseModel):
    id: str
    type: Literal["heading", "paragraph", "bullet_list", "numbered_list", "table", "figure", "caption", "reference", "unsupported"]
    level: int = 0
    text: Optional[str] = None
    source_order: int
    style_name: Optional[str] = None
    confidence: float
    metadata: dict = {}

class TemplateConstraint(BaseModel):
    id: str
    category: Literal["page", "typography", "paragraph", "structure", "object", "header_footer"]
    target: str
    property: str
    expected_value: Any
    provenance: Literal["EXTRACTED", "CONFIGURED", "INFERRED", "UNSUPPORTED"]
    confidence: float
    enforceable: bool
    evidence: Optional[dict] = None

class ContentTemplateMapping(BaseModel):
    source_element_id: str
    target_role: str
    target_style: Optional[str] = None
    constraint_ids: List[str] = []
    method: Literal["rule", "embedding", "llm"]
    confidence: float
    status: Literal["accepted", "ambiguous", "rejected"]

class IRElement(BaseModel):
    id: str
    type: str
    level: int = 0
    content: Optional[str] = None
    style_ref: Optional[str] = None
    children: List[Any] = []
    target_id: str
    metadata: dict = Field(default_factory=dict)


class DocumentIR(BaseModel):
    document_id: str
    metadata: dict = {}
    page_constraints: List[Any] = []
    styles: dict = {}
    elements: List[IRElement] = []

class Violation(BaseModel):
    constraint_id: str
    severity: Literal["error", "warning", "info"]
    actual: Any
    expected: Any
    message: str

class ValidationResult(BaseModel):
    job_id: str
    compliance_score: float = 0.0
    validation_coverage: float = 0.0
    passed_constraints: int = 0
    failed_constraints: int = 0
    not_measurable_constraints: int = 0
    unsupported_constraints: int = 0
    applicable_constraints: int = 0
    passed: bool
    violations: List[Violation] = []

class CorrectionOperation(BaseModel):
    target_id: str
    operation: Literal["FIT_TO_TEXT_WIDTH"]
    parameters: dict = {}

class MappingManifest(BaseModel):
    ir_target_id: str
    docx_location_reference: str
    status: Literal["mapped", "unmapped"]
    message: Optional[str] = None

class GenerationManifest(BaseModel):
    job_id: str
    mappings: List[MappingManifest] = []

class ApiError(BaseModel):
    error_code: str
    message: str
    stage: str
    details: dict = {}
