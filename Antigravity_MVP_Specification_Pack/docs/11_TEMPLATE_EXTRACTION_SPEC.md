# Template Extraction Specification (V2)

## Objective
Extract styling and constraint rules from the reference DOCX template to govern DOCX generation and IR validation.

## Limitations & Principles
- Do not assume `python-docx` can perfectly expose every Word feature.
- If a property cannot be reliably extracted, label it `UNSUPPORTED` or `NOT_MEASURABLE`. Do not invent its value.
- Do not use LLMs to guess template constraints.

## Extraction Targets

### 1. Document Level (Page Setup)
- Margins (Top, Bottom, Left, Right)
- Page size and orientation
- Default font family and size

### 2. Styles
- Extract all named paragraph and character styles.
- Capture font size, weight, alignment, and indentation where exposed.

### 3. Headers and Footers
- Detect presence of headers and footers.
- Retain them structurally within the template file (since the generator will use the template as a base).

### 4. Lists & Numbering
- Extract list templates and numbering hierarchies.

## Provenance
Every constraint output by this module must include a provenance label:
- `EXTRACTED`: Reliably pulled from OpenXML properties.
- `UNSUPPORTED`: Feature exists but cannot be extracted reliably.
