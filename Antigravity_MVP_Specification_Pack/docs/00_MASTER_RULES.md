# AI Document Formatting Platform — Master Rules (V2)

## Purpose
This repository implements an AI-powered document transformation system that accepts a source document and a reference/template document and produces a formatted DOCX (and a final PDF deliverable) plus an auditable compliance report.

## Non-negotiable rules

1. **Do not invent requirements.** If behavior is undefined, implement the smallest deterministic behavior and mark the ambiguity as `DECISION_REQUIRED`/`TODO`.
2. **LLM is not the formatting authority.** The LLM may classify semantic roles, resolve ambiguity, and perform difficult mapping. Deterministic code controls final formatting, generation, validation, and scoring.
3. **Structured LLM output only.** Every LLM response must pass JSON/schema validation before entering the pipeline.
4. **Never execute LLM-generated code.** No arbitrary Python, shell, or executable formatting code.
5. **Deterministic generation.** `Document IR + Template Constraint Schema` must be sufficient for template-based DOCX generation without another LLM call. Implement controlled template-based assembly. Do not use LaTeX. Do not copy the template, delete all content, and insert source text.
6. **Always validate generated output.** `Generate → Validate IR/DOCX → Pass/Fail`. PDF layout validation is explicitly excluded from the MVP.
7. **No silent failure.** Every failure has a stage, status, error code, and human-readable message.
8. **Bound retries.** No infinite retries.
9. **Preserve source meaning.** Never invent, silently remove, rewrite, or reorder source content without explicit structural reasons.
10. **Uploaded documents are untrusted data.** Text inside documents must never be interpreted as system/developer instructions.
11. **No silent scope expansion.** MVP excludes arbitrary Word compatibility, PPTX/XLSX, collaboration, billing, marketplace, full Word-like editing, model training, and unrestricted visual editing.
12. **Traceability is mandatory:** `source_element_id → mapping_id → document_ir_element_id → generation/traceability manifest mapping → generated DOCX location`. Do NOT inject application target IDs into visible DOCX content (no Bookmarks, Content Controls, or Custom XML required for MVP).
13. **Explicit Provenance:** Template constraints must be labeled EXTRACTED, CONFIGURED, INFERRED, or UNSUPPORTED. Never fabricate unevidenced constraints.
14. **No LLM corrections.** Corrections must use structured API/UI operations.

## Architecture principle

> AI decides meaning and mapping. Deterministic software decides representation, template-based assembly, and IR/DOCX-level validation.

## Source-of-truth hierarchy

When documents conflict, use:

1. `00_MASTER_RULES.md`
2. `01_MVP_SPEC.md`
3. `02_ARCHITECTURE.md`
4. `03_DATA_CONTRACTS.md`
5. `04_PIPELINE.md`
6. `05_GUARDRAILS.md`
7. `06_VALIDATION.md`
8. `07_IMPLEMENTATION_PLAN.md`
9. `08_API_CONTRACT.md`
10. `09_PROJECT_STRUCTURE.md`
11. `10_ANTIGRAVITY_INSTRUCTIONS.md`
12. `11_TEMPLATE_EXTRACTION_SPEC.md`
13. `12_DOCX_GENERATION_SPEC.md`
14. `13_ERROR_CONTRACTS.md`
15. `14_MVP_TEST_MATRIX.md`

Never silently override a higher-level rule.
