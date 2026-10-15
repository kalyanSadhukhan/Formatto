import logging
from typing import Optional

from app.domain.schemas.data_contracts import DocumentIR
from app.ir.validator import DocumentIRValidator, IRValidationReport

logger = logging.getLogger(__name__)


class IRValidationStage:
    """
    Pipeline stage for Phase 6: Document IR Validation.
    Validates integrity, traceability, order, tables, figures, and serialization.
    """

    def __init__(self, validator: Optional[DocumentIRValidator] = None):
        self.validator = validator or DocumentIRValidator()

    def execute(self, doc_ir: DocumentIR) -> IRValidationReport:
        logger.info(f"Validating Document IR for document {doc_ir.document_id} ({len(doc_ir.elements)} elements)")
        report = self.validator.validate(doc_ir)
        if not report.is_valid:
            logger.error(f"Document IR validation failed: {report.issues}")
        else:
            logger.info("Document IR validated successfully.")
        return report
