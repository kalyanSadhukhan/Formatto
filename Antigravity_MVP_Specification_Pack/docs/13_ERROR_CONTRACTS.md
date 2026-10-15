# Error Contracts (V2)

All API errors must follow this structured schema:

```json
{
  "error_code": "string",
  "message": "string",
  "stage": "string",
  "details": {}
}
```

## Standard Error Codes

1. `INVALID_UPLOAD`
   - Description: File size exceeded, wrong MIME type, missing files.
2. `UNSUPPORTED_FILE`
   - Description: File is encrypted or corrupted.
3. `EXTRACTION_FAILURE`
   - Description: Failed to parse source DOCX.
4. `SEMANTIC_ANALYSIS_FAILURE`
   - Description: LLM parsing failed after retries, or rule engine crashed.
5. `TEMPLATE_EXTRACTION_FAILURE`
   - Description: Failed to parse template DOCX.
6. `MAPPING_FAILURE`
   - Description: Unable to resolve mapping for critical elements.
7. `IR_VALIDATION_FAILURE`
   - Description: Document IR violates structural schema.
8. `DOCX_GENERATION_FAILURE`
   - Description: Failed to assemble the DOCX natively.
9. `DOCX_VALIDATION_FAILURE`
   - Description: Generated DOCX failed formatting checks critically.
10. `PDF_CONVERSION_FAILURE`
    - Description: LibreOffice conversion failed. Note: The generated DOCX artifact should still be retained if it passed `DOCX_VALIDATION_FAILURE`.
11. `UNSUPPORTED_CORRECTION`
    - Description: The structured correction payload requests an unknown target or operation.
12. `INTERNAL_SERVER_ERROR`
    - Description: Unhandled exceptions.
