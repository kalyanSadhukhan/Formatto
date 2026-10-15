# API Contract (V2)

## POST /api/jobs
Multipart upload: source file, template file.
Response:
```json
{"job_id":"string","status":"CREATED"}
```

## GET /api/jobs/{job_id}/status
```json
{
  "job_id":"string",
  "status":"VALIDATING_DOCX",
  "progress":0.85,
  "stage":"docx_validation"
}
```

## GET /api/jobs/{job_id}/result
```json
{
  "job_id":"string",
  "status":"COMPLETED",
  "docx":"artifact-reference",
  "pdf":"artifact-reference",
  "compliance_score":94.2,
  "validation_coverage":80.0,
  "validation_report":"artifact-reference",
  "metadata": {}
}
```
Note: `pdf` may be `null` if the pipeline completed DOCX generation and validation successfully but encountered a `PDF_CONVERSION_FAILURE`.

## POST /api/jobs/{job_id}/correction
Input MUST be structured JSON. No natural language.
```json
{
  "target_id": "table_3",
  "operation": "FIT_TO_TEXT_WIDTH"
}
```

## GET /api/health
Service health endpoint.

## Error Handling
Standardized error envelope required for 4xx/5xx responses (see 13_ERROR_CONTRACTS.md).
