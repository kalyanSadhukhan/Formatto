import logging
import os
import time
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.domain.schemas.data_contracts import ApiError, DocumentIR, GenerationManifest, JobState
from app.extraction.docx_extractor import DocxExtractor
from app.generation.models import GenerationResult
from app.ir.validator import IRValidationReport
from app.pipeline.stages.docx_generation_stage import DocxGenerationStage
from app.pipeline.stages.ir_validation_stage import IRValidationStage
from app.pipeline.stages.mapping_stage import MappingStage
from app.pipeline.stages.semantic_analysis_stage import SemanticAnalysisStage
from app.semantics.classifier import SemanticClassifier
from app.templates.models import TemplateProfile
from app.templates.template_extractor import TemplateExtractor
from app.validation.structural_validator import StructuralValidationReport, StructuralValidator

logger = logging.getLogger(__name__)


class PipelineExecutionResult(BaseModel):
    """Structured result returned by the end-to-end document formatting pipeline."""
    job_id: str
    status: JobState
    source_path: str
    template_path: str
    output_docx_path: Optional[str] = None
    manifest: Optional[GenerationManifest] = None
    total_elements: int = 0
    generated_elements: int = 0
    ir_report: Optional[IRValidationReport] = None
    structural_report: Optional[StructuralValidationReport] = None
    duration_seconds: float = 0.0
    diagnostics: list[str] = Field(default_factory=list)
    error: Optional[ApiError] = None




class DocumentFormattingPipeline:
    """
    End-to-end pipeline orchestrator for Specification V2.
    Connects Phases 1 through 6 into a single, unified backend operation.
    """

    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or "/tmp/formatto_output"
        os.makedirs(self.output_dir, exist_ok=True)

    def run(
        self,
        source_path: str,
        template_path: str,
        job_id: Optional[str] = None,
        output_docx_path: Optional[str] = None,
    ) -> PipelineExecutionResult:
        jid = job_id or f"job_{uuid.uuid4().hex[:8]}"
        start_time = time.time()
        logger.info(f"Starting formatting pipeline for job {jid}")

        if not os.path.exists(source_path):
            err = ApiError(error_code="INVALID_UPLOAD", message=f"Source file not found: {source_path}", stage="EXTRACTING_SOURCE")
            return PipelineExecutionResult(job_id=jid, status=JobState.FAILED, source_path=source_path, template_path=template_path, error=err)


        if not os.path.exists(template_path):
            err = ApiError(error_code="INVALID_UPLOAD", message=f"Template file not found: {template_path}", stage="EXTRACTING_TEMPLATE")
            return PipelineExecutionResult(job_id=jid, status=JobState.FAILED, source_path=source_path, template_path=template_path, error=err)

        diagnostics: list[str] = []
        current_stage = "INITIALIZATION"

        try:
            # Stage 1: Source Document Extraction
            current_stage = "SOURCE_EXTRACTION"
            logger.info("Executing Stage 1: Source Document Extraction")
            extractor = DocxExtractor(source_path)
            source_elements = extractor.extract()

            # Stage 2: Source Semantic Analysis
            current_stage = "SEMANTIC_ANALYSIS"
            logger.info("Executing Stage 2: Source Semantic Analysis")
            semantic_stage = SemanticAnalysisStage()
            enriched_result = semantic_stage.execute(source_elements)
            enriched_elements = enriched_result.elements

            # Stage 3: Template Extraction & Constraint Construction
            current_stage = "TEMPLATE_EXTRACTION"
            logger.info("Executing Stage 3: Template Extraction")
            tmpl_extractor = TemplateExtractor(template_path)
            tmpl_dict = tmpl_extractor.extract_template()
            template_profile = TemplateProfile(**tmpl_dict)

            # Stage 4: Content-to-Template Mapping
            current_stage = "CONTENT_MAPPING"
            logger.info("Executing Stage 4: Content-to-Template Mapping")
            mapping_stage = MappingStage(template_profile)
            mapping_result = mapping_stage.execute(
                enriched_elements,
                document_id=enriched_result.document_id,
                source_docx_path=source_path,
            )
            if mapping_result.fallback_count > 0:
                diagnostics.append(f"{mapping_result.fallback_count} style fallbacks applied during mapping.")

            # Stage 5: Document IR Construction & Validation
            current_stage = "IR_VALIDATION"
            logger.info("Executing Stage 5: Document IR Construction & Validation")
            doc_ir = mapping_result.to_document_ir()
            ir_validation_stage = IRValidationStage()
            ir_report = ir_validation_stage.execute(doc_ir)

            if not ir_report.is_valid:
                err = ApiError(
                    error_code="IR_VALIDATION_FAILED",
                    message="Document IR failed validation checks.",
                    stage="IR_VALIDATION",
                    details={"issues": ir_report.issues},
                )
                return PipelineExecutionResult(
                    job_id=jid,
                    status=JobState.FAILED,
                    source_path=source_path,
                    template_path=template_path,
                    ir_report=ir_report,
                    diagnostics=diagnostics,
                    error=err,
                )

            # Stage 6: Deterministic DOCX Generation
            current_stage = "DOCX_GENERATION"
            logger.info("Executing Stage 6: Deterministic DOCX Generation")
            final_output_path = output_docx_path or os.path.join(self.output_dir, f"{jid}_formatted.docx")
            generation_stage = DocxGenerationStage(template_path=template_path, source_docx_path=source_path)
            gen_result = generation_stage.execute(doc_ir, output_path=final_output_path, job_id=jid)

            diagnostics.extend(gen_result.diagnostics)

            # Stage 7: Post-Generation Structural Validation (Phase E)
            current_stage = "STRUCTURAL_VALIDATION"
            logger.info("Executing Stage 7: Post-Generation Structural Validation")
            structural_validator = StructuralValidator()
            structural_report = structural_validator.validate(
                output_docx_path=final_output_path,
                template_docx_path=template_path,
                source_docx_path=source_path,
                doc_ir=doc_ir,
            )
            diagnostics.extend(structural_report.diagnostics)
            if not structural_report.is_valid:
                for issue in structural_report.issues:
                    diagnostics.append(f"Structural Validation Issue: {issue}")

            duration = round(time.time() - start_time, 2)
            logger.info(f"Pipeline successfully completed for job {jid} -> {final_output_path} in {duration}s")
            return PipelineExecutionResult(
                job_id=jid,
                status=JobState.COMPLETED,
                source_path=source_path,
                template_path=template_path,
                output_docx_path=final_output_path,
                manifest=gen_result.manifest,
                total_elements=gen_result.total_elements,
                generated_elements=gen_result.generated_elements,
                ir_report=ir_report,
                structural_report=structural_report,
                duration_seconds=duration,
                diagnostics=diagnostics,
            )

        except Exception as ex:
            duration = round(time.time() - start_time, 2)
            logger.exception(f"Pipeline execution failed for job {jid} at stage {current_stage}: {ex}")
            ex_name = type(ex).__name__
            if ex_name in ("BadZipFile", "PackageNotFoundError") or "not a Word file" in str(ex):
                err_code = "UNSUPPORTED_FILE"
                msg = f"Document is corrupted or not a valid Word (.docx) file during {current_stage}."
            else:
                err_code = "INTERNAL_SERVER_ERROR"
                msg = f"Internal error during {current_stage}: {ex_name}: {str(ex)}"

            err = ApiError(
                error_code=err_code,
                message=msg,
                stage=current_stage,
                details={"exception_type": ex_name, "raw_error": str(ex)},
            )
            return PipelineExecutionResult(
                job_id=jid,
                status=JobState.FAILED,
                source_path=source_path,
                template_path=template_path,
                duration_seconds=duration,
                diagnostics=diagnostics,
                error=err,
            )

