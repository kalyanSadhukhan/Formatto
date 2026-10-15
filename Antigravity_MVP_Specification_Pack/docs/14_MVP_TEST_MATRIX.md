# MVP Test Matrix (V2)

## 1. End-to-End Happy Path
- Source: Standard DOCX with headings, lists, tables.
- Template: Standard DOCX with distinct styles.
- Expected: Complete pipeline runs, generates DOCX and PDF, compliance score > 0, validation report returned.

## 2. File Upload Failures
- Test: Upload non-DOCX files, encrypted DOCX, files over size limit.
- Expected: Job rejected immediately with `INVALID_UPLOAD` or `UNSUPPORTED_FILE`.

## 3. Template Extraction Limits
- Test: Template with unreadable custom margins or complex floating objects.
- Expected: Properties marked `UNSUPPORTED` or `NOT_MEASURABLE`. Pipeline continues.

## 4. Semantic Ambiguity
- Test: Source with manual bolding acting as headings.
- Expected: LLM resolves role. `confidence` metrics reflect ambiguity handling.

## 5. Style Fallback
- Test: IR requires "Heading 5", but template only has up to "Heading 3".
- Expected: Generator falls back to "Normal" (or closest), logs a warning.

## 6. PDF Conversion Failure
- Test: Mock LibreOffice failure.
- Expected: Status `FAILED`, error `PDF_CONVERSION_FAILURE`.

## 7. Structured Correction
- Test: Submit valid `target_id` and `FIT_TO_TEXT_WIDTH`.
- Expected: IR updated, DOCX/PDF regenerated.
- Test: Submit invalid `target_id`.
- Expected: `UNSUPPORTED_CORRECTION`.
