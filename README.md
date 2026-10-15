# Formatto — AI-Powered Deterministic Document Formatting Platform

**Formatto** is a deterministic DOCX-to-DOCX document formatting platform that adapts raw, unformatted content documents into strict institutional templates and publication styles. Unlike simple style copy tools or LLM text rewrites, Formatto uses an intermediate representation (Document IR) and layout-aware constraints to preserve complex institutional structures (such as nested tables, merged cells, blank log sheets, signature blocks, and multi-section layouts) with mathematical fidelity.

---

## 1. Overview & Core Features

Formatto solves the challenge of adapting unstructured reports, project diaries, and manuscripts into strict institutional formats without losing content, mangling tables, or corrupting document hierarchy.

### MVP Features
- **Dual Document Processing**: Upload an unformatted source DOCX and a reference template DOCX.
- **7-Stage Deterministic Pipeline**:
  1. **Source Document Extraction**: Verbatim text, styling, paragraph hierarchy, and OpenXML table grid extraction.
  2. **Semantic Analysis**: Classifies document elements (titles, headings, paragraphs, bullet/numbered lists, tables, figures, captions) using deterministic heuristics with optional LLM fallback for ambiguous elements.
  3. **Template Extraction**: Extracts page geometry, margins, typographic hierarchies, headers/footers, and table constraints.
  4. **Content-to-Template Mapping**: Deterministically maps source elements to template slots with fallback tracking.
  5. **Document IR Validation**: Validates the Document IR against schema and invariant rules before generation.
  6. **Deterministic DOCX Generation**: Native OpenXML document assembly preserving complex tables, merged cells, blank entry rows, and typographic rules.
  7. **Structural Validation**: Post-generation quality gate verifying section preservation, table counts, and structural invariants (differentiating structured forms vs. flow reports).
- **Grid-Aware Table Merge Engine**: Accurately tracks `w:gridSpan` and `w:vMerge` coordinates across asymmetric rows.
- **Professional SaaS Frontend**: Drag-and-drop dual uploads, real-time pipeline status, metrics dashboard, structural quality gate reporting, unresolved mapping diagnostics, and one-click DOCX download.
- **Robust Error Contracts**: Clear separation between client validation errors (HTTP 400/422) and internal failures (HTTP 500) with correlation IDs and server-side tracing.

---

## 2. High-Level Architecture

```
┌────────────────────────────────────────────────────────┐
│                   Formatto Frontend                    │
│           (React 19, TypeScript, Vite SaaS UI)         │
└──────────────────────────┬─────────────────────────────┘
                           │ Multipart Upload / API
                           ▼
┌────────────────────────────────────────────────────────┐
│                   Formatto Backend                     │
│               (FastAPI / Python 3.10+)                 │
│                                                        │
│  Stage 1: Source DOCX Extractor (OpenXML / lxml)       │
│  Stage 2: Semantic Classifier (Deterministic + LLM)    │
│  Stage 3: Template Constraint Extractor                │
│  Stage 4: Content-to-Template Mapper                   │
│  Stage 5: Document IR Validator                        │
│  Stage 6: Deterministic DOCX Generator                 │
│  Stage 7: Post-Generation Structural Validator         │
└────────────────────────────────────────────────────────┘
```

---

## 3. Repository Structure

```
Formatto/
├── Antigravity_MVP_Specification_Pack/ # Complete architectural specifications (Docs 00-14)
├── ai-document-formatter/
│   └── apps/
│       ├── backend/                    # FastAPI application
│       │   ├── app/
│       │   │   ├── api/                # Endpoints (/api/jobs, /api/health)
│       │   │   ├── core/               # Configuration and structured logging
│       │   │   ├── domain/             # Schemas and canonical data contracts
│       │   │   ├── extraction/         # OpenXML DOCX extraction engine
│       │   │   ├── generation/         # Template-preserving DOCX generation
│       │   │   ├── ir/                 # Document IR models and validation
│       │   │   ├── mapping/            # Content-to-template mapping engine
│       │   │   ├── pipeline/           # 7-stage orchestrator and stage coordinators
│       │   │   ├── semantics/          # Semantic analysis and LLM provider fallback
│       │   │   ├── templates/          # Template extraction and constraints
│       │   │   └── validation/         # Structural validation quality gate
│       │   ├── tests/                  # 92 unit and regression tests
│       │   │   └── fixtures/           # Project Diary & Flow Report test documents
│       │   ├── requirements.txt        # Production dependencies
│       │   ├── requirements-dev.txt    # Development/testing dependencies
│       │   └── pytest.ini              # Pytest configuration
│       └── frontend/                   # React + TypeScript + Vite application
│           ├── src/                    # UI components, ErrorBoundary, Diagnostics
│           ├── public/                 # Static assets
│           ├── package.json            # Node dependencies
│           └── vite.config.ts          # Vite build and proxy configuration
├── .gitignore                          # Clean repository ignore rules
├── .gitattributes                      # Line-ending and binary file rules
├── .env.example                        # Root environment template
└── README.md                           # Platform documentation
```

---

## 4. Prerequisites

- **Python**: 3.10, 3.11, 3.12, or 3.14
- **Node.js**: v18.0.0 or higher
- **npm**: v9.0.0 or higher
- **Git**

---

## 5. Local Setup

### Clone the Repository
```bash
git clone https://github.com/kalyanSadhukhan/Formatto.git
cd Formatto
```

### Backend Setup
```bash
cd ai-document-formatter/apps/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
```

### Frontend Setup
```bash
cd ../frontend

# Install dependencies from lockfile
npm ci
```

---

## 6. Running the Application

### Start the Backend (Terminal 1)
```bash
cd ai-document-formatter/apps/backend
source venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
The FastAPI backend will start on `http://127.0.0.1:8000`. Swagger documentation is available at `http://127.0.0.1:8000/docs`.

### Start the Frontend (Terminal 2)
```bash
cd ai-document-formatter/apps/frontend
npm run dev
```
The Vite development server will open at `http://localhost:5173`. Requests to `/api/*` are automatically proxied to the backend on `http://127.0.0.1:8000`.

---

## 7. Environment Variables

Copy `.env.example` to `.env` in the backend directory or export them in your deployment environment:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `PROJECT_NAME` | Name of the platform | `"AI Document Formatting Platform"` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `"INFO"` |
| `STORAGE_PATH` | Base directory for temporary document generation | `"/tmp/formatto"` |
| `MAX_FILE_SIZE_BYTES` | Maximum allowed upload size per file (bytes) | `10485760` (10 MB) |
| `CORS_ORIGINS` | Permitted CORS origins for API requests | `["*"]` |
| `GEMINI_API_KEY` | *(Optional)* Google Gemini API key for ambiguous role classification | `""` |
| `OPENAI_API_KEY` | *(Optional)* OpenAI API key for ambiguous role classification | `""` |
| `VITE_API_BASE_URL` | *(Frontend)* Remote API base URL (empty uses current origin / proxy) | `""` |

> **Note on LLM Keys**: Formatto's pipeline operates fully deterministically. If no LLM API key is provided, the platform automatically applies its deterministic rule engine with zero downtime or exceptions.

---

## 8. Running Tests & Quality Checks

### Backend Test Suite
```bash
cd ai-document-formatter/apps/backend
source venv/bin/activate
pytest
```
*Executes all 92 tests across extraction, table merge handling, template extraction, semantic analysis, mapping, IR validation, DOCX generation, and regression suites.*

### Frontend Linter & Tests
```bash
cd ai-document-formatter/apps/frontend

# Run linter
npm run lint

# Run unit tests
npm test

# Build production bundle
npm run build
```

---

## 9. API Reference

### Health Check
- **`GET /api/health`**
  - Response: `{"status": "ok", "database": "ok"}`

### Create Formatting Job
- **`POST /api/jobs`**
  - Content-Type: `multipart/form-data`
  - Parameters:
    - `source_file`: Unformatted DOCX document (max 10 MB).
    - `template_file`: Reference template DOCX document (max 10 MB).
  - Responses:
    - `200 OK`: `{"job_id": "job_12345678", "status": "CREATED"}`
    - `400 Bad Request`: Validation failure (empty file, non-DOCX, corrupted file).
    - `422 Unprocessable Entity`: Document IR or structural invariant validation failure.
    - `500 Internal Server Error`: Unexpected internal error with safe correlation ID.

### Check Job Status
- **`GET /api/jobs/{job_id}/status`**
  - Response: `{"job_id": "job_12345678", "status": "COMPLETED", "progress": 1.0, "stage": "docx_generation"}`

### Retrieve Job Result & Diagnostics
- **`GET /api/jobs/{job_id}/result`**
  - Response: Complete metadata including duration, element counts, structural validation results, and download path.

### Download Generated Document
- **`GET /api/jobs/{job_id}/download`**
  - Response: Binary `application/vnd.openxmlformats-officedocument.wordprocessingml.document` download.

---

## 10. Document Generation Workflow

1. Navigate to `http://localhost:5173`.
2. Upload your unformatted document in **Step 1: Source Document** (supports Project Diaries, technical reports, manuscripts).
3. Upload your reference template in **Step 2: Reference Template** (supports institutional templates, university formats, journal templates).
4. Click **Generate Formatted Document**.
5. Inspect the generated metrics:
   - Processing duration and element counts.
   - Preserved section boundaries and table counts.
   - Structural Quality Gate status.
   - Pipeline Diagnostics & IR Trace.
6. Click **Download Formatted DOCX** to retrieve the formatted document.

---

## 11. Deployment Considerations

- **Platform Neutrality**: Formatto is designed to be hosted on standard containerized platforms (Docker, AWS ECS, Fly.io, Render, Google Cloud Run) or dedicated servers.
- **Storage**:
  - The MVP uses local/ephemeral filesystem storage (`/tmp/formatto`) for job execution and document generation.
  - In a horizontally scaled multi-worker deployment, configure an object store (e.g., AWS S3, Google Cloud Storage) or shared volume for job outputs and replace the in-memory `JOB_STORE` with a shared cache (Redis/database).
- **Reverse Proxy**:
  - When deploying with Nginx or Caddy, proxy `/api` requests to the FastAPI backend and serve `apps/frontend/dist` as static assets.
- **File Upload Limits**: Ensure reverse proxies (such as Nginx `client_max_body_size`) allow up to 10 MB uploads.

---

## 12. Known Limitations & Scope

- **Supported Formats**: Strictly Microsoft Word (.docx) OpenXML packages. Legacy binary `.doc` files, PDFs, and RTF documents are not supported for input.
- **Embedded Macros & OLE Objects**: Unsupported binary objects are safely extracted as placeholder unsupported blocks and omitted from output generation without breaking document integrity.
- **Equation Objects**: Native MathML equations within paragraphs are extracted as inline text runs; complex 3D charting objects adopt fallback styling.
