from typing import List, Optional
from pydantic import BaseModel, Field
from app.domain.schemas.data_contracts import GenerationManifest


class GenerationResult(BaseModel):
    """Result of deterministic DOCX document generation."""
    job_id: str
    output_path: str
    manifest: GenerationManifest
    total_elements: int = 0
    generated_elements: int = 0
    unmapped_elements: int = 0
    diagnostics: List[str] = Field(default_factory=list)
