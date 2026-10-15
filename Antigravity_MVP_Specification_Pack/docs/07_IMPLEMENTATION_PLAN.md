# 20-Day Implementation Plan (V2)

## Days 1–2 — Foundation
- repo setup, frontend/backend skeleton
- DB, logging, job state machine
- domain schemas (IR, errors)

## Days 3–4 — Input & Setup
- upload API with validation
- storage abstraction
- explicit error handling boundaries

## Days 5–6 — Source extraction
- DOCX extraction (`python-docx`)
- normalized SourceDocument (with stable IDs)
- tests

## Days 7–8 — Semantic understanding
- deterministic semantic rules
- LLM structured classification (for ambiguity)
- schema validation

## Days 9–10 — Template understanding
- DOCX template extraction
- constraint normalization (provenance: EXTRACTED, UNSUPPORTED, etc.)

## Days 11–12 — Mapping + IR
- deterministic mapping
- embeddings for ambiguity
- Document IR generation

## Days 13–15 — DOCX Generation
- template-based DOCX assembly
- inject IR into template copy
- preserve headers/footers/styles

## Days 16–17 — Validation & PDF Conversion
- IR validation
- DOCX structure validation
- Headless PDF conversion integration
- score/report calculation

## Day 18 — Correction
- structured API for deterministic correction operations
- regenerate DOCX -> PDF pipeline

## Day 19 — Hardening
- end-to-end tests (MVP test matrix)
- failure tests, security review, cleanup

## Day 20 — Deployment
- deployment, documentation, demo flow
