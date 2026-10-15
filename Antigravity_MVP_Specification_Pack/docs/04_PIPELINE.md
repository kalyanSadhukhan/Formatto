# End-to-End Pipeline (V2)

## 0. Upload
Validate file type, MIME where available, size, readability.

## 1. Source extraction
Deterministically extract paragraphs, styles, headings, lists, tables, images, captions, and source order.

## 2. Source semantic analysis
Use deterministic rules first. Use LLM only for ambiguity. The LLM classifies/structures; it does not rewrite or reorder content.

## 3. Template extraction
Extract page dimensions, margins, styles, fonts, heading/list styles, header/footer. Label unextractable constraints as `UNSUPPORTED`.

## 4. Constraint construction
Normalize extracted properties into `TemplateConstraint`. Set explicit provenance (`EXTRACTED`, `CONFIGURED`, `INFERRED`, `UNSUPPORTED`).

## 5. Content-template mapping
Decision order:
1. deterministic rule
2. style-name evidence
3. embedding similarity
4. LLM for ambiguous cases

Record method, confidence, and ambiguity.

## 6. Document IR
Build renderer-independent normalized representation with stable `target_id`s for traceability.

## 7. IR Validation
Validate the Document IR against the `TemplateConstraint` schema to ensure logical compliance before generation.

## 8. Deterministic DOCX generation
Assemble the target DOCX using controlled template-based assembly. Preserve template styles, page setup, margins, sections, headers, footers, numbering, and paragraph styles. Do not copy template, delete all, and insert.
Produce an internal `GenerationManifest` mapping IR elements to their generated DOCX locations. Do not inject physical OpenXML IDs into visible content.

## 9. DOCX Validation
Validate the generated DOCX structure and measurable formatting properties. Do not claim to validate unmeasurable properties.

## 10. Scoring
Calculate compliance score and validation coverage based on measurable constraints. `NOT_MEASURABLE` is not a `PASS`.

## 11. PDF Conversion
Convert the valid DOCX to PDF using LibreOffice headless (isolated behind an abstraction). If PDF conversion fails, report `PDF_CONVERSION_FAILURE` but retain the successfully validated DOCX artifact.

## 12. Correction
```text
Structured API payload
→ validate operation/target_id
→ update Document IR
→ regenerate DOCX
→ validate DOCX
→ convert PDF
```

## 13. Completion
Return generated DOCX, PDF (if successful), validation report, score, warnings, and processing metadata.
