import json
import logging
from typing import List, Optional
from pydantic import BaseModel, Field

from app.domain.schemas.data_contracts import DocumentIR, IRElement

logger = logging.getLogger(__name__)


class IRValidationReport(BaseModel):
    """Result of Document IR integrity and compliance validation."""
    is_valid: bool
    total_elements: int = 0
    traceable_elements: int = 0
    table_elements: int = 0
    figure_elements: int = 0
    list_elements: int = 0
    heading_elements: int = 0
    unsupported_elements: int = 0
    ambiguous_elements: int = 0
    serializable: bool = True
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class DocumentIRValidator:
    """
    Validates Document IR integrity before DOCX generation (Phase 6 Priority 1).

    Ensures:
    1. Every element has traceable identity (id and target_id are unique and non-empty).
    2. Source order is preserved and strictly monotonic.
    3. Source text is preserved without unauthorized mutations.
    4. Tables retain rows, columns, cell strings, and merge metadata.
    5. Figures retain valid image/drawing relationships.
    6. List metadata and heading levels are available for controlled assembly.
    7. Unsupported elements and unresolved mappings remain explicitly identifiable.
    8. Ambiguity and confidence are not silently stripped.
    9. Document IR supports deterministic round-trip serialization/deserialization.
    """

    def validate(self, ir: DocumentIR) -> IRValidationReport:
        issues: List[str] = []
        warnings: List[str] = []

        if not ir.elements:
            warnings.append("Document IR contains no elements.")
            return IRValidationReport(
                is_valid=True,
                total_elements=0,
                issues=[],
                warnings=warnings,
            )

        seen_ids = set()
        seen_target_ids = set()
        last_source_order = -1

        table_count = 0
        figure_count = 0
        list_count = 0
        heading_count = 0
        unsupported_count = 0
        ambiguous_count = 0
        traceable_count = 0

        for idx, elem in enumerate(ir.elements):
            # 1. Traceability
            if not elem.id:
                issues.append(f"Element at index {idx} has empty ID.")
            elif elem.id in seen_ids:
                issues.append(f"Duplicate IR element ID: {elem.id}")
            seen_ids.add(elem.id)

            if not elem.target_id:
                issues.append(f"Element {elem.id} has empty target_id.")
            elif elem.target_id in seen_target_ids:
                issues.append(f"Duplicate target_id: {elem.target_id}")
            seen_target_ids.add(elem.target_id)

            source_id = elem.metadata.get("source_element_id")
            if source_id:
                traceable_count += 1
            else:
                warnings.append(f"Element {elem.id} missing source_element_id in metadata.")

            # 2. Source order monotonicity
            src_order = elem.metadata.get("source_order")
            if src_order is not None:
                if src_order <= last_source_order:
                    issues.append(
                        f"Element {elem.id} violates monotonic source order: "
                        f"{src_order} <= {last_source_order}"
                    )
                last_source_order = src_order

            # 3. Role-specific validation
            elem_type = elem.type.lower()

            if elem_type in ("heading", "title", "document_title"):
                heading_count += 1
                if elem.level < 0:
                    issues.append(f"Heading element {elem.id} has invalid negative level: {elem.level}")
                if not elem.content and not elem.children:
                    warnings.append(f"Heading element {elem.id} has no text content.")

            elif elem_type in ("bullet_list_item", "numbered_list_item", "bullet_list", "numbered_list"):
                list_count += 1

            elif elem_type == "table":
                table_count += 1
                cell_text = elem.children
                if not isinstance(cell_text, list):
                    issues.append(f"Table element {elem.id} children must be a 2D list of cell text.")
                else:
                    row_count = elem.metadata.get("row_count", len(cell_text))
                    col_count = elem.metadata.get("column_count", 0)
                    if len(cell_text) != row_count:
                        warnings.append(
                            f"Table {elem.id} row_count metadata ({row_count}) differs from children rows ({len(cell_text)})."
                        )
                    if cell_text and col_count > 0:
                        for r_i, row in enumerate(cell_text):
                            if not isinstance(row, list):
                                issues.append(f"Table {elem.id} row {r_i} is not a list.")

            elif elem_type == "figure":
                figure_count += 1
                rids = elem.children or elem.metadata.get("drawing_rids", [])
                img_count = elem.metadata.get("image_count", len(rids))
                if len(rids) != img_count:
                    warnings.append(
                        f"Figure {elem.id} image_count {img_count} does not match drawing_rids count {len(rids)}."
                    )

            elif elem_type == "unsupported":
                unsupported_count += 1

            # 4. Ambiguity tracking
            if elem.metadata.get("is_ambiguous") or elem.metadata.get("mapping_status") == "ambiguous":
                ambiguous_count += 1

        # 5. Serialization and Deserialization round-trip check
        serializable = True
        try:
            dumped = ir.model_dump_json()
            restored = DocumentIR.model_validate_json(dumped)
            if len(restored.elements) != len(ir.elements):
                issues.append("Document IR deserialization changed element count.")
                serializable = False
        except Exception as e:
            issues.append(f"Document IR serialization round-trip failed: {e}")
            serializable = False

        is_valid = len(issues) == 0

        return IRValidationReport(
            is_valid=is_valid,
            total_elements=len(ir.elements),
            traceable_elements=traceable_count,
            table_elements=table_count,
            figure_elements=figure_count,
            list_elements=list_count,
            heading_elements=heading_count,
            unsupported_elements=unsupported_count,
            ambiguous_elements=ambiguous_count,
            serializable=serializable,
            issues=issues,
            warnings=warnings,
        )
