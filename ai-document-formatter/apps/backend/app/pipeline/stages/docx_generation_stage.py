import logging
from typing import Optional

from app.domain.schemas.data_contracts import DocumentIR
from app.generation.docx_generator import DocxGenerator
from app.generation.models import GenerationResult

logger = logging.getLogger(__name__)


class DocxGenerationStage:
    """
    Pipeline stage for Phase 6: Deterministic DOCX Generation.
    Executes controlled template-based assembly and outputs the styled DOCX.
    """

    def __init__(self, template_path: str, source_docx_path: Optional[str] = None):
        self.generator = DocxGenerator(template_path=template_path, source_docx_path=source_docx_path)

    def execute(self, doc_ir: DocumentIR, output_path: str, job_id: Optional[str] = None) -> GenerationResult:
        logger.info(f"Executing DOCX generation stage for job {job_id} -> {output_path}")
        return self.generator.generate(doc_ir, output_path=output_path, job_id=job_id)
