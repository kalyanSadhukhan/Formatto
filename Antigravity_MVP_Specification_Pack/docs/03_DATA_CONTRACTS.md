# Data Contracts (V2)

All major cross-module objects and all LLM outputs require strict schemas.

## SourceElement
```json
{
  "id": "string",
  "type": "heading|paragraph|bullet_list|numbered_list|table|figure|caption|reference",
  "level": 0,
  "text": "string|null",
  "source_order": 0,
  "style_name": "string|null",
  "confidence": 0.0
}
```

## TemplateConstraint
```json
{
  "id": "string",
  "category": "page|typography|paragraph|structure|object|header_footer",
  "target": "string",
  "property": "string",
  "expected_value": "any",
  "provenance": "EXTRACTED|CONFIGURED|INFERRED|UNSUPPORTED",
  "confidence": 0.0,
  "enforceable": true
}
```
`provenance` must be explicitly set. Do not fabricate unevidenced constraints.

## ContentTemplateMapping
```json
{
  "source_element_id": "string",
  "target_role": "string",
  "target_style": "string|null",
  "constraint_ids": [],
  "method": "rule|embedding|llm",
  "confidence": 0.0,
  "status": "accepted|ambiguous|rejected"
}
```

## DocumentIR
```json
{
  "document_id": "string",
  "metadata": {},
  "page_constraints": [],
  "styles": {},
  "elements": [
    {
      "id": "string",
      "type": "string",
      "level": 0,
      "content": "string|null",
      "style_ref": "string|null",
      "children": [],
      "target_id": "string"
    }
  ]
}
```

## GenerationManifest
```json
{
  "job_id": "string",
  "mappings": [
    {
      "ir_target_id": "string",
      "docx_location_reference": "string",
      "status": "mapped|unmapped",
      "message": "string|null"
    }
  ]
}
```
Used to trace elements without physical OpenXML ID injection.

## ValidationResult
```json
{
  "job_id": "string",
  "compliance_score": 0.0,
  "validation_coverage": 0.0,
  "passed_constraints": 0,
  "failed_constraints": 0,
  "not_measurable_constraints": 0,
  "unsupported_constraints": 0,
  "applicable_constraints": 0,
  "passed": true,
  "violations": [
    {
      "constraint_id": "string",
      "severity": "error|warning|info",
      "actual": "any",
      "expected": "any",
      "message": "string"
    }
  ]
}
```

## CorrectionOperation
Only allowlisted operations may execute via structured input:
```json
{
  "target_id": "table_3",
  "operation": "FIT_TO_TEXT_WIDTH",
  "parameters": {}
}
```

## Job states
```text
CREATED
UPLOADING
EXTRACTING_SOURCE
ANALYZING_SOURCE
EXTRACTING_TEMPLATE
MAPPING
BUILDING_IR
VALIDATING_IR
GENERATING_DOCX
VALIDATING_DOCX
CONVERTING_PDF
COMPLETED
CORRECTION_PENDING
CORRECTING
FAILED
```
