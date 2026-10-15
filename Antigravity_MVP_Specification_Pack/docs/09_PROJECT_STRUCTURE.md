# Proposed Repository Structure (V2)

```text
ai-document-formatter/
├── apps/
│   ├── frontend/
│   │   └── src/
│   └── backend/
│       ├── app/
│       │   ├── api/
│       │   ├── core/
│       │   ├── domain/
│       │   │   ├── models/
│       │   │   ├── schemas/
│       │   │   └── services/
│       │   ├── pipeline/
│       │   │   ├── stages/
│       │   │   └── orchestrator.py
│       │   ├── extraction/
│       │   ├── semantics/
│       │   ├── templates/
│       │   ├── mapping/
│       │   ├── ir/
│       │   ├── generation/
│       │   ├── validation/
│       │   ├── conversion/
│       │   ├── correction/
│       │   ├── infrastructure/
│       │   └── main.py
│       │
│       └── tests/
├── docs/
├── tests/
├── scripts/
├── docker/
├── .env.example
├── .gitignore
└── README.md
```
