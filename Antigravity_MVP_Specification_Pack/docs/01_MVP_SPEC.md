# MVP Specification (V2)

## Product
**AI-Powered Intelligent Document Formatting and Template Adaptation Platform**

## Core objective
Transform a source document into the structure and formatting of a reference template using AI for semantic understanding and deterministic code for template-based DOCX generation and validation.

## Inputs
Primary MVP:
- Source: DOCX
- Reference template: DOCX

## Output
Primary:
- DOCX (Generated)
- PDF (Converted final deliverable via LibreOffice headless)

Metadata:
- job ID
- status
- compliance score
- validation coverage
- validation report
- warnings
- processing metadata

## Supported source elements
The generator must explicitly support:
- paragraph
- heading
- bullet list
- numbered list
- table
- figure/image
- caption
- references

Unsupported structures must be reported, not silently discarded.

## Supported template constraints
### Page
- page size
- margins
- orientation where reliably detectable

### Typography
- font family
- font size
- bold/italic
- underline where supported
- alignment

### Paragraph
- line spacing
- paragraph spacing
- indentation
- alignment

### Structure
- heading hierarchy
- numbering
- list formatting

### Objects
- table width
- figure width
- caption style

### Page furniture
- header
- footer
- page numbering

Only reliably extracted or explicitly configured constraints may be enforced.

## Compliance score
Calculated on measurable constraints against IR or DOCX structure:

`Compliance score = passed constraints / applicable measurable constraints`
`Validation coverage = applicable measurable constraints / total constraints`

NOT_MEASURABLE must never count as PASS.

## Correction MVP
Only allowlisted deterministic correction operations may execute via structured API. LLM natural-language parsing is excluded.

Example structured payload:
```json
{
  "target_id": "table_3",
  "operation": "FIT_TO_TEXT_WIDTH"
}
```

Unsupported requests return structured error `UNSUPPORTED_CORRECTION`.

## Explicit exclusions
- arbitrary Word compatibility
- PPTX/XLSX
- collaboration
- marketplace/billing
- custom model training
- full Word-like editor
- unrestricted visual editing
- LaTeX generation
- PDF layout validation
- LLM natural language correction
- perfect reproduction of every Word-specific feature
- complex SmartArt, macros, arbitrary fields, complex drawing objects, and unsupported OpenXML structures
- Physical OpenXML ID injection (Bookmarks, Content Controls, Custom XML are OUT OF SCOPE)

## Success criterion
A user uploads source DOCX + template DOCX and receives a valid generated DOCX and PDF whose supported structure/formatting can be audited through the IR/DOCX validation report.
