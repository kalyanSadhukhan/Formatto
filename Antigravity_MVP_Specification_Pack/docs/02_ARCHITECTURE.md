# System Architecture (V2)

```text
React + TypeScript
       |
       v
FastAPI API
       |
       v
Job Manager
       |
       +-----------------------------+
       |                             |
       v                             v
Source Processing              Template Processing
       |                             |
       v                             v
Source Semantic Model       Template Constraint Schema
       |                             |
       +-------------+---------------+
                     |
                     v
             Content-Template Mapping
                     |
                     v
                Document IR
                     |
                     v
               IR Validator
                     |
                     v
        Deterministic DOCX Assembly (Template-Based)
                     |       (Creates Generation Manifest)
                     v
             DOCX Validator
                     |
               +------+------+
               |             |
              PASS          FAIL
               |             |
               v             v
         Generated DOCX    Violations
               |             |
               v             v
         PDF Converter   Correction API (Structured)
        (LibreOffice)        |
               |             |
               v             v
           Final PDF     Update IR/Regenerate
```

## Technology baseline

### Frontend
React + TypeScript

### Backend
Python + FastAPI

### DOCX processing
`python-docx` (or `docx-template`), used for both extraction and deterministic template-based assembly.

### AI
LLM API with structured JSON output behind a provider adapter.

### Matching
Embeddings + cosine similarity initially; LLM only for ambiguous cases.

### IR
Strict JSON/Pydantic models. Traced via an internal generation manifest without injecting physical OpenXML IDs.

### Generation
Deterministic DOCX generation utilizing controlled template-based assembly. No LaTeX.

### PDF Conversion
LibreOffice headless isolated behind an abstraction layer to convert the generated DOCX to PDF. Do not introduce Gotenberg or third-party PDF APIs for the MVP. A successful validated DOCX must remain available even if PDF conversion fails.

### Persistence & Storage
PostgreSQL and S3-compatible object storage.

## Layer boundaries

- **API:** HTTP/contracts only.
- **Orchestration:** pipeline order, states, retries, failure handling.
- **Domain:** source model, constraints, mappings, IR, validation, generation.
- **Infrastructure:** database, storage, LLM provider, PDF converter abstraction.

## Critical boundary
The LLM is never the system of record. The system of record is the validated source model, validated template constraints (with provenance), validated mapping, and validated Document IR.

## Observability
Every stage records stage, start/end time, status, error code, and structured metadata. Never log secrets or raw sensitive document content.
