import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.domain.schemas.data_contracts import SourceElement
from app.semantics.llm_provider import (
    BaseLLMProvider,
    LLMMalformedResponseError,
    LLMProviderError,
    LLMTimeoutError,
    MockLLMProvider,
    get_llm_provider,
)
from app.semantics.models import (
    ClassificationMethod,
    ClassificationProvenance,
    EnrichedSourceElement,
    LLMSemanticClassification,
    SemanticAnalysisResult,
    SemanticAnnotation,
    SemanticRole,
)

logger = logging.getLogger(__name__)


class SemanticClassifier:
    """
    Deterministic & LLM-Assisted Semantic Classifier (Specification V2, Phase 4).

    Enriches extracted SourceElements with semantic roles needed for downstream mapping.
    Uses deterministic rules first; invokes the LLM provider adapter only for genuinely
    ambiguous elements (confidence < 0.70). Strictly preserves original source text,
    element order, IDs, and extraction classifications without rewriting or hallucination.
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        confidence_threshold: float = 0.70,
    ):
        self.llm_provider = llm_provider or get_llm_provider()
        self.confidence_threshold = confidence_threshold

    def _classify_deterministic(
        self,
        element: SourceElement,
        preceding_role: Optional[SemanticRole] = None,
    ) -> Tuple[SemanticRole, int, float, ClassificationMethod, ClassificationProvenance, bool, Dict[str, Any]]:
        """
        Evaluate deterministic rules and style evidence for an element.
        Returns:
            (role, level, confidence, method, provenance, is_ambiguous, evidence)
        """
        el_type = element.type
        style = (element.style_name or "").strip()
        style_lower = style.lower()
        text = (element.text or "").strip()
        meta = element.metadata or {}

        # 1. Structural elements directly extracted by docx_extractor
        if el_type == "table":
            return (
                SemanticRole.TABLE,
                0,
                1.0,
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "structural_table", "row_count": meta.get("row_count")},
            )

        if el_type == "figure":
            return (
                SemanticRole.FIGURE,
                0,
                1.0,
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "structural_figure", "image_count": meta.get("image_count")},
            )

        if el_type == "caption":
            return (
                SemanticRole.CAPTION,
                0,
                0.98,
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "caption_pairing", "figure_id": meta.get("figure_id")},
            )

        if el_type == "bullet_list":
            return (
                SemanticRole.BULLET_LIST_ITEM,
                element.level,
                1.0,
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "numPr_bullet", "num_id": meta.get("num_id")},
            )

        if el_type == "numbered_list":
            return (
                SemanticRole.NUMBERED_LIST_ITEM,
                element.level,
                1.0,
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "numPr_numbered", "num_id": meta.get("num_id")},
            )

        if el_type == "reference" or meta.get("section") == "references":
            return (
                SemanticRole.REFERENCE,
                0,
                0.98,
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "bibliography_section", "section": meta.get("section")},
            )

        if el_type == "unsupported":
            return (
                SemanticRole.UNSUPPORTED,
                0,
                1.0,
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "unsupported_openxml_structure", "raw_tag": meta.get("raw_tag")},
            )

        # 2. Explicit Word Heading Styles ("Heading 1", "Heading 2", etc.)
        if el_type == "heading" or style_lower.startswith("heading"):
            lvl = element.level or 1
            if "heading" in style_lower:
                match = re.search(r"heading\s*(\d+)", style_lower)
                if match:
                    lvl = int(match.group(1))
            return (
                SemanticRole.HEADING,
                lvl,
                0.98,
                ClassificationMethod.STYLE_EVIDENCE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "heading_style", "style": style, "level": lvl},
            )

        # 3. Document Title heuristic (source order 1, title style, or prominent header text)
        if style_lower == "title" or (element.source_order == 1 and len(text) < 100 and not text.endswith(".")):
            return (
                SemanticRole.DOCUMENT_TITLE,
                0,
                0.95,
                ClassificationMethod.STYLE_EVIDENCE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "document_title", "source_order": element.source_order, "style": style},
            )

        # 4. Custom Heading Styles (e.g. "ExecutiveHeading", "SectionHeader", outline level > 0)
        if "head" in style_lower or "header" in style_lower or element.level > 0:
            lvl = element.level or 1
            return (
                SemanticRole.HEADING,
                lvl,
                0.92,
                ClassificationMethod.STYLE_EVIDENCE,
                ClassificationProvenance.EXTRACTED,
                False,
                {"rule": "custom_heading_style", "style": style, "level": lvl},
            )

        # 5. Genuinely Ambiguous Cases: Manual Bolding or Short Unstyled Text acting as Headings
        is_bold = meta.get("is_bold", False) or meta.get("all_bold", False)
        has_num_prefix = bool(re.match(r"^(\d+(\.\d+)*|[A-Z]\.|\([a-z]\))\s+", text))
        is_short = len(text) < 90
        has_period = text.endswith(".") or text.endswith(";") or text.endswith(":")

        if (is_bold or has_num_prefix) and is_short and not has_period:
            # Genuine ambiguity: could be a section heading or an emphasis paragraph
            return (
                SemanticRole.HEADING if has_num_prefix or is_bold else SemanticRole.BODY_PARAGRAPH,
                1 if has_num_prefix else 2,
                0.60,  # Below threshold -> triggers LLM
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.AMBIGUOUS,
                True,
                {"ambiguity_reason": "manual_bold_or_numbered_heading", "is_bold": is_bold, "has_prefix": has_num_prefix},
            )

        # 6. Narrative Body Paragraph
        if len(text) > 100 or text.count(".") >= 2:
            return (
                SemanticRole.BODY_PARAGRAPH,
                0,
                0.95,
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.INFERRED,
                False,
                {"rule": "narrative_body_paragraph", "char_count": len(text)},
            )

        # 7. Short unstyled text without clear markers
        if len(text) < 60 and not has_period:
            return (
                SemanticRole.BODY_PARAGRAPH,
                0,
                0.65,  # Below threshold -> triggers LLM
                ClassificationMethod.DETERMINISTIC_RULE,
                ClassificationProvenance.AMBIGUOUS,
                True,
                {"ambiguity_reason": "short_unstyled_non_punctuated_text"},
            )

        # Default fallback: Body paragraph
        return (
            SemanticRole.BODY_PARAGRAPH,
            0,
            0.85,
            ClassificationMethod.DETERMINISTIC_RULE,
            ClassificationProvenance.INFERRED,
            False,
            {"rule": "default_paragraph_fallback"},
        )

    def analyze_document(
        self,
        elements: List[SourceElement],
        document_id: Optional[str] = None,
    ) -> SemanticAnalysisResult:
        """
        Execute full semantic analysis on a list of extracted SourceElements.
        Preserves original element text, count, order, and identifiers unconditionally.
        """
        doc_id = document_id or (elements[0].id.split("_")[1] if elements and "_" in elements[0].id else "doc_001")
        enriched_elements: List[EnrichedSourceElement] = []

        ambiguous_count = 0
        llm_count = 0
        deterministic_count = 0
        role_counts: Dict[str, int] = {}
        method_counts: Dict[str, int] = {}

        last_role: Optional[SemanticRole] = None

        for idx, elem in enumerate(elements):
            # 1. Deterministic classification
            role, level, conf, method, prov, is_ambiguous, evidence = self._classify_deterministic(
                element=elem,
                preceding_role=last_role,
            )

            # 2. Ambiguity resolution via LLM provider adapter
            if is_ambiguous or conf < self.confidence_threshold:
                ambiguous_count += 1
                try:
                    ctx = {
                        "preceding_role": last_role.value if last_role else "none",
                        "next_snippet": elements[idx + 1].text[:40] if idx + 1 < len(elements) and elements[idx + 1].text else None,
                    }
                    llm_res = self.llm_provider.classify_element(elem, ctx)

                    # Validate response with strict schema
                    if isinstance(llm_res, LLMSemanticClassification):
                        llm_count += 1
                        role = llm_res.semantic_role
                        level = llm_res.level
                        conf = llm_res.confidence
                        method = ClassificationMethod.LLM
                        evidence["llm_reasoning"] = llm_res.reasoning
                        evidence["llm_role"] = llm_res.semantic_role.value

                        if conf >= self.confidence_threshold:
                            is_ambiguous = False
                            prov = ClassificationProvenance.INFERRED
                        else:
                            # Low-confidence LLM output remains flagged as ambiguous
                            is_ambiguous = True
                            prov = ClassificationProvenance.AMBIGUOUS
                            evidence["low_confidence_note"] = "LLM returned confidence below threshold"

                except (LLMTimeoutError, LLMProviderError, LLMMalformedResponseError, Exception) as err:
                    logger.warning(f"LLM classification fallback for {elem.id}: {err}")
                    method = ClassificationMethod.FALLBACK
                    prov = ClassificationProvenance.FALLBACK
                    conf = 0.50
                    is_ambiguous = True
                    evidence["llm_error"] = str(err)
                    evidence["error_type"] = type(err).__name__
            else:
                deterministic_count += 1

            last_role = role

            # Update stats
            role_counts[role.value] = role_counts.get(role.value, 0) + 1
            method_counts[method.value] = method_counts.get(method.value, 0) + 1

            # 3. Assemble EnrichedSourceElement
            enriched_meta = dict(elem.metadata)
            enriched_meta["semantic"] = {
                "role": role.value,
                "level": level,
                "confidence": conf,
                "method": method.value,
                "provenance": prov.value,
                "is_ambiguous": is_ambiguous,
            }

            enriched = EnrichedSourceElement(
                id=elem.id,
                type=elem.type,
                level=elem.level,
                text=elem.text,
                source_order=elem.source_order,
                style_name=elem.style_name,
                confidence=elem.confidence,
                metadata=enriched_meta,
                semantic_role=role,
                semantic_confidence=conf,
                semantic_method=method,
                semantic_provenance=prov,
                is_ambiguous=is_ambiguous,
                semantic_evidence=evidence,
            )
            enriched_elements.append(enriched)

        # 4. Enforce strict invariants
        assert len(enriched_elements) == len(elements), "Element count modified during semantic analysis!"
        assert [e.id for e in enriched_elements] == [e.id for e in elements], "Element IDs altered!"
        assert [e.text for e in enriched_elements] == [e.text for e in elements], "Source text modified!"
        assert [e.source_order for e in enriched_elements] == [e.source_order for e in elements], "Element order modified!"

        return SemanticAnalysisResult(
            document_id=doc_id,
            total_elements=len(enriched_elements),
            ambiguous_elements_count=ambiguous_count,
            llm_classified_count=llm_count,
            deterministic_classified_count=deterministic_count,
            role_counts=role_counts,
            method_counts=method_counts,
            elements=enriched_elements,
            processing_metadata={
                "threshold": self.confidence_threshold,
                "llm_provider": type(self.llm_provider).__name__,
            },
        )
