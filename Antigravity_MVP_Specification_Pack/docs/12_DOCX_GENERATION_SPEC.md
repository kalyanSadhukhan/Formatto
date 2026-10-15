# DOCX Generation Specification (V2)

## Objective
Generate the final formatted DOCX by deterministically injecting Document IR content using controlled template-based assembly.

## Explicit MVP Supported Element Set
The generator must explicitly support:
- paragraph
- heading
- bullet list
- numbered list
- table
- figure/image
- caption
- references

The generator must NOT claim support for arbitrary Word/OpenXML features. Complex SmartArt, macros, arbitrary fields, complex drawing objects, and unsupported OpenXML structures are explicitly outside the MVP.

## Core Directives

1. **How the template is loaded (Controlled Assembly):**
   The reference template is the formatting substrate. Do NOT implement a process that copies the template, deletes everything, and inserts source text. Instead, implement controlled template-based assembly where supported structures are preserved natively.

2. **How template styles are preserved:**
   By using the template as the base and carefully assembling content, internal style definitions, theme colors, document defaults, page setup, margins, sections, headers, footers, and numbering remain intact.

3. **How source semantic elements map to template styles:**
   The IR dictates which template style name applies to each element. The generator applies this `style_name` structurally.

4. **How paragraphs are created:**
   Append new paragraphs using the target style defined in the IR.

5. **How headings are created:**
   Append paragraphs with heading styles corresponding to the IR hierarchy.

6. **How lists are handled:**
   Apply the appropriate list style. Maintain list continuation IDs if required by OpenXML.

7. **How tables are handled:**
   Create tables with the specified column counts. Apply the template's default table style or the mapped style from IR.

8. **How figures/images are handled:**
   Insert image binaries into the new DOCX. Scale them deterministically based on IR constraints or default text width.

9. **How captions are handled:**
   Insert text immediately following tables/figures with the mapped caption style.

10. **How headers/footers are preserved:**
    Because the base document is the template, existing headers and footers are preserved implicitly.

11. **How page setup is preserved:**
    Page setup (margins, size, sections) remains untouched from the template base.

12. **How numbering is preserved:**
    Numbering linked to styles will auto-increment natively within the generated DOCX.

13. **Missing Template Styles:**
    If the IR requires a style not present in the template, fall back to "Normal" and log a warning in the validation report.

14. **Unsupported Source Elements:**
    If an element is unsupported, append it as plain text with a visible warning prefix, or log an error based on configuration.

15. **Stable Element IDs (Traceability):**
    DO NOT inject application target IDs into visible DOCX content. Do not make Word Bookmarks, Content Controls, or Custom XML a mandatory dependency for the MVP.
    Instead, produce an internal `GenerationManifest` that maps IR element IDs to their generated DOCX locations using application-level tracking. If a generated element cannot be reliably mapped back to its IR element, the generation stage must report this in the manifest rather than inventing a mapping.

16. **Generated DOCX Validation:**
    Post-generation, the document is re-parsed to confirm that elements were successfully written and that applied styles match the IR requirements.
