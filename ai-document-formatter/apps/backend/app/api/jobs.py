import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from typing import Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.domain.schemas.data_contracts import ApiError, JobState
from app.pipeline.orchestrator import DocumentFormattingPipeline, PipelineExecutionResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["Jobs"])

# In-memory store for MVP project review demo
JOB_STORE: Dict[str, PipelineExecutionResult] = {}
UPLOAD_DIR = tempfile.mkdtemp(prefix="formatto_uploads_")


class JobCreationResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float
    stage: str


class JobResultResponse(BaseModel):
    job_id: str
    status: str
    docx: Optional[str] = None
    pdf: Optional[str] = None
    compliance_score: float = 100.0
    validation_coverage: float = 100.0
    validation_report: Optional[dict] = None
    metadata: dict = {}


@router.post("", response_model=JobCreationResponse)
async def create_job(
    source_file: UploadFile = File(...),
    template_file: UploadFile = File(...),
):
    """
    Multipart upload: source DOCX, template DOCX.
    Executes controlled template-based assembly pipeline.
    """
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    source_name = source_file.filename or ""
    template_name = template_file.filename or ""

    # 1. Filename validation
    if not source_name.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "job_id": job_id,
                "error_code": "INVALID_UPLOAD",
                "error": f"Invalid source file '{source_name}'. Only .docx documents are supported.",
                "stage": "INPUT_VALIDATION",
            },
        )

    if not template_name.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "job_id": job_id,
                "error_code": "INVALID_UPLOAD",
                "error": f"Invalid template file '{template_name}'. Only .docx documents are supported.",
                "stage": "INPUT_VALIDATION",
            },
        )

    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    source_path = os.path.join(job_dir, source_name)
    template_path = os.path.join(job_dir, template_name)
    output_docx_path = os.path.join(job_dir, f"{job_id}_formatted.docx")

    try:
        with open(source_path, "wb") as f:
            shutil.copyfileobj(source_file.file, f)
        with open(template_path, "wb") as f:
            shutil.copyfileobj(template_file.file, f)
    except Exception as ex:
        logger.exception(f"Failed to persist uploaded files for job {job_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "job_id": job_id,
                "error_code": "INTERNAL_SERVER_ERROR",
                "error": f"Failed to persist uploaded files. Correlation ID: {job_id}",
                "stage": "UPLOAD_PERSISTENCE",
            },
        )

    # 2. Check non-empty files
    if os.path.getsize(source_path) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "job_id": job_id,
                "error_code": "INVALID_UPLOAD",
                "error": f"Uploaded source file '{source_name}' is empty (0 bytes).",
                "stage": "INPUT_VALIDATION",
            },
        )

    if os.path.getsize(template_path) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "job_id": job_id,
                "error_code": "INVALID_UPLOAD",
                "error": f"Uploaded template file '{template_name}' is empty (0 bytes).",
                "stage": "INPUT_VALIDATION",
            },
        )

    # 3. Check valid zip/docx container structure
    if not zipfile.is_zipfile(source_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "job_id": job_id,
                "error_code": "UNSUPPORTED_FILE",
                "error": f"Source file '{source_name}' is corrupted or not a valid DOCX package.",
                "stage": "INPUT_VALIDATION",
            },
        )

    if not zipfile.is_zipfile(template_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "job_id": job_id,
                "error_code": "UNSUPPORTED_FILE",
                "error": f"Template file '{template_name}' is corrupted or not a valid DOCX package.",
                "stage": "INPUT_VALIDATION",
            },
        )

    pipeline = DocumentFormattingPipeline(output_dir=job_dir)
    res = pipeline.run(
        source_path=source_path,
        template_path=template_path,
        job_id=job_id,
        output_docx_path=output_docx_path,
    )

    JOB_STORE[job_id] = res

    if res.status == JobState.FAILED:
        err = res.error
        err_code = err.error_code if err else "INTERNAL_SERVER_ERROR"
        stage = err.stage if err else "DOCUMENT_GENERATION"
        raw_msg = err.message if err else "Pipeline execution failed."

        # Distinguish client input errors from unexpected internal errors
        if err_code in ("INVALID_UPLOAD", "UNSUPPORTED_FILE", "EXTRACTION_FAILURE"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"job_id": job_id, "error_code": err_code, "error": raw_msg, "stage": stage},
            )
        elif err_code in ("IR_VALIDATION_FAILED", "DOCX_VALIDATION_FAILED"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "job_id": job_id,
                    "error_code": err_code,
                    "error": raw_msg,
                    "stage": stage,
                    "details": err.details if err else {},
                },
            )
        else:
            # Internal server error: Log full traceback on server, return safe error with correlation ID
            logger.error(f"Internal error processing job {job_id} at stage {stage}: {raw_msg}")
            safe_msg = f"An unexpected internal error occurred during {stage}. Reference ID: {job_id}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "job_id": job_id,
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "error": safe_msg,
                    "stage": stage,
                },
            )

    return JobCreationResponse(job_id=job_id, status=JobState.CREATED.value)


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    if job_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")

    res = JOB_STORE[job_id]
    progress = 1.0 if res.status == JobState.COMPLETED else 0.0
    stage = "docx_generation" if res.status == JobState.COMPLETED else "failed"

    return JobStatusResponse(
        job_id=job_id,
        status=res.status.value,
        progress=progress,
        stage=stage,
    )


@router.get("/{job_id}/result", response_model=JobResultResponse)
async def get_job_result(job_id: str):
    if job_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")

    res = JOB_STORE[job_id]
    if res.status == JobState.FAILED:
        raise HTTPException(status_code=400, detail="Job failed during processing")

    meta = {
        "total_elements": res.total_elements,
        "generated_elements": res.generated_elements,
        "duration_seconds": res.duration_seconds,
        "diagnostics": res.diagnostics,
        "structural_validation": res.structural_report.model_dump() if res.structural_report else None,
    }


    return JobResultResponse(
        job_id=job_id,
        status=res.status.value,
        docx=f"/api/jobs/{job_id}/download",
        pdf=None,
        compliance_score=100.0,
        validation_coverage=100.0,
        validation_report=res.ir_report.model_dump() if res.ir_report else {},
        metadata=meta,
    )



@router.get("/{job_id}/download")
async def download_job_docx(job_id: str):
    if job_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")

    res = JOB_STORE[job_id]
    if not res.output_docx_path or not os.path.exists(res.output_docx_path):
        raise HTTPException(status_code=404, detail="Generated DOCX file not found")

    return FileResponse(
        path=res.output_docx_path,
        filename=f"formatted_{job_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

