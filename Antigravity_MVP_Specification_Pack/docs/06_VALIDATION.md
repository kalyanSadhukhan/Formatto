# Validation and Evaluation (V2)

## Validation targets
Validation operates ONLY on the Document IR and the generated DOCX (OpenXML structure). PDF visual validation is excluded from the MVP.

## Validation categories
### Structural (IR & DOCX)
- title presence
- heading hierarchy
- required sections
- numbering
- captions
- references

### Formatting (DOCX measurable)
- page size (if accessible)
- margins (if accessible)
- applied style names (paragraph, character)
- alignment (if accessible)

## Constraint statuses
- `PASS`
- `FAIL`
- `WARNING`
- `NOT_MEASURABLE`
- `UNSUPPORTED`

## Compliance metrics
`Compliance score = passed / (passed + failed)`
`Validation coverage = (passed + failed) / total applicable constraints`

`NOT_MEASURABLE` is never counted as `PASS`.

## Report
Expose:
- compliance score
- validation coverage
- total constraints
- passed, failed, not measurable, unsupported
- violations (with severity, actual, expected, message)

## Research evaluation
Measure semantic classification accuracy, mapping accuracy, generated DOCX compliance score, and runtime.
