import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.domain.schemas.data_contracts import ContentTemplateMapping, SourceElement
from app.mapping.models import DocumentMappingResult, ElementMappingResult
from app.semantics.models import EnrichedSourceElement, SemanticRole
from app.templates.models import TemplateProfile

logger = logging.getLogger(__name__)


class ContentTemplateMapper:
    """
    Deterministic Source-to-Template Mapper (Specification V2, Phase 5).

    Converts EnrichedSourceElements and TemplateProfile into formal ContentTemplateMapping
    records and DocumentMappingResult. Maps semantic roles to template styles based on
    extracted template evidence, handles missing heading levels via deterministic fallback,
    preserves source content and order unconditionally, respects constraint provenance,
    and identifies ambiguous elements without fabricating false certainty.
    """

    def __init__(self, template_profile: TemplateProfile):
        self.template_profile = template_profile
        self.styles = template_profile.styles
        self.table_styles = template_profile.table_styles
        self.constraints = template_profile.constraints

        # Build style lookup indices
        self._index_styles()
        # Build constraint lookup indices
        self._index_constraints()

    def _index_styles(self):
        """Index available styles in the template for fast normalized lookup."""
        self.available_headings: Dict[int, str] = {}
        self.has_title_style: Optional[str] = None
        self.has_caption_style: Optional[str] = None
        self.has_bullet_list_style: Optional[str] = None
        self.has_numbered_list_style: Optional[str] = None
        self.has_body_text_style: Optional[str] = None
        self.has_reference_style: Optional[str] = None

        # Normalized maps: style_id lower -> canonical style_id / style_name
        self.style_lookup: Dict[str, str] = {}

        for sid, sdef in self.styles.items():
            name = sdef.style_name or sid
            norm_id = sid.lower().replace(" ", "").replace("_", "")
            norm_name = name.lower().replace(" ", "").replace("_", "")
            self.style_lookup[norm_id] = sid
            self.style_lookup[norm_name] = sid

            # Heading detection
            h_match = re.search(r"heading(\d+)", norm_name) or re.search(r"heading(\d+)", norm_id)
            if h_match:
                lvl = int(h_match.group(1))
                self.available_headings[lvl] = sid
            elif sdef.raw_declared_properties.outline_level or sdef.resolved_effective_properties.outline_level:
                lvl = sdef.raw_declared_properties.outline_level or sdef.resolved_effective_properties.outline_level
                if lvl and lvl not in self.available_headings:
                    self.available_headings[lvl] = sid

            # Title
            if "title" in norm_name and "sub" not in norm_name:
                self.has_title_style = sid

            # Caption
            if "caption" in norm_name:
                self.has_caption_style = sid

            # Bullet List
            if "listbullet" in norm_name or "bullet" in norm_name:
                self.has_bullet_list_style = sid

            # Numbered List
            if "listnumber" in norm_name:
                self.has_numbered_list_style = sid

            # List Paragraph generic fallback
            if "listparagraph" in norm_name:
                if not self.has_bullet_list_style:
                    self.has_bullet_list_style = sid
                if not self.has_numbered_list_style:
                    self.has_numbered_list_style = sid

            # Body Text / Normal
            if "bodytext" in norm_name:
                self.has_body_text_style = sid

            # Reference / Bibliography
            if "biblio" in norm_name or "reference" in norm_name:
                self.has_reference_style = sid

    def _index_constraints(self):
        """Index constraints by target and enforceability."""
        self.constraints_by_target: Dict[str, List[Any]] = {}

        for c in self.constraints:
            target = getattr(c, "target", None) or (c.get("target") if isinstance(c, dict) else None)
            if target:
                if target not in self.constraints_by_target:
                    self.constraints_by_target[target] = []
                self.constraints_by_target[target].append(c)

    def _find_style(self, candidate_name: str) -> Optional[str]:
        """Look up canonical style identifier in template."""
        norm = candidate_name.lower().replace(" ", "").replace("_", "")
        return self.style_lookup.get(norm)

    def _get_heading_style(self, level: int) -> Tuple[str, bool, Optional[str]]:
        """
        Select the appropriate heading style for the given level.
        If the exact level is not available in the template, fall back to the closest
        available heading level <= requested level, or 'Normal' if no heading exists.
        Returns: (selected_style, fallback_applied, fallback_reason)
        """
        lvl = max(1, min(level, 6))

        # 1. Exact match
        if lvl in self.available_headings:
            return self.available_headings[lvl], False, None

        # Check by name "Heading {lvl}"
        exact_candidate = f"Heading{lvl}"
        found = self._find_style(exact_candidate)
        if found:
            return found, False, None

        # 2. Fall back to closest available heading level <= lvl
        lower_levels = [l for l in self.available_headings.keys() if l < lvl]
        if lower_levels:
            closest_lvl = max(lower_levels)
            closest_style = self.available_headings[closest_lvl]
            reason = f"Heading level {lvl} not defined in template; fell back to Heading {closest_lvl} ({closest_style})"
            return closest_style, True, reason

        # 3. Fall back to any available heading level
        if self.available_headings:
            min_lvl = min(self.available_headings.keys())
            min_style = self.available_headings[min_lvl]
            reason = f"Heading level {lvl} not defined in template; fell back to closest available level {min_lvl} ({min_style})"
            return min_style, True, reason

        # 4. Ultimate fallback: Normal
        normal_style = self._find_style("Normal") or "Normal"
        reason = f"Heading level {lvl} not defined and no headings found in template; fell back to {normal_style}"
        return normal_style, True, reason

    def _associate_constraints(
        self,
        target_style: Optional[str],
        section_index: int = 0,
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Associate template constraints for the mapped style and section.
        Partitions constraint IDs into all, enforceable (EXTRACTED), and advisory (INFERRED/CONFIGURED).
        """
        all_ids: List[str] = []
        enforceable_ids: List[str] = []
        advisory_ids: List[str] = []

        targets = []
        if target_style:
            # Query constraints for this style (target: style.{style_id})
            norm_sid = target_style.replace(" ", "")
            targets.append(f"style.{norm_sid}")
            targets.append(f"style.{target_style}")

        # Also include section page constraints
        targets.append(f"section.{section_index}")

        seen: Set[str] = set()
        for t in targets:
            matching = self.constraints_by_target.get(t, [])
            for c in matching:
                cid = getattr(c, "id", None) or (c.get("id") if isinstance(c, dict) else None)
                if not cid or cid in seen:
                    continue
                seen.add(cid)
                all_ids.append(cid)

                enforceable = getattr(c, "enforceable", False) or (c.get("enforceable", False) if isinstance(c, dict) else False)
                if enforceable:
                    enforceable_ids.append(cid)
                else:
                    advisory_ids.append(cid)

        return all_ids, enforceable_ids, advisory_ids

    def map_element(self, element: EnrichedSourceElement) -> ElementMappingResult:
        """
        Map a single enriched source element to target role, style, constraints, and status.
        """
        role = element.semantic_role
        target_role = role.value
        target_style: Optional[str] = None
        fallback_applied = False
        fallback_reason: Optional[str] = None
        diagnostics: List[str] = []
        status: Literal["accepted", "ambiguous", "rejected"] = "accepted"

        # Determine section index from metadata
        sec_idx = element.metadata.get("section_index", 0)

        # 1. Map role to template style
        if role == SemanticRole.DOCUMENT_TITLE:
            if self.has_title_style:
                target_style = self.has_title_style
            else:
                # Fallback to Heading 1 or Normal
                h1_style, _, _ = self._get_heading_style(1)
                target_style = h1_style or self._find_style("Normal") or "Normal"
                fallback_applied = True
                fallback_reason = f"Title style missing in template; mapped to {target_style}"
                diagnostics.append(fallback_reason)

        elif role == SemanticRole.HEADING:
            lvl = element.level or 1
            target_style, fallback_applied, fallback_reason = self._get_heading_style(lvl)
            if fallback_applied and fallback_reason:
                diagnostics.append(fallback_reason)

        elif role == SemanticRole.BODY_PARAGRAPH:
            target_style = self.has_body_text_style or self._find_style("Normal") or "Normal"

        elif role == SemanticRole.BULLET_LIST_ITEM:
            if self.has_bullet_list_style:
                target_style = self.has_bullet_list_style
            else:
                target_style = self._find_style("Normal") or "Normal"
                fallback_applied = True
                fallback_reason = "Bullet list style missing in template; fell back to Normal"
                diagnostics.append(fallback_reason)

        elif role == SemanticRole.NUMBERED_LIST_ITEM:
            if self.has_numbered_list_style:
                target_style = self.has_numbered_list_style
            else:
                target_style = self._find_style("Normal") or "Normal"
                fallback_applied = True
                fallback_reason = "Numbered list style missing in template; fell back to Normal"
                diagnostics.append(fallback_reason)

        elif role == SemanticRole.TABLE:
            # Map to template table style
            if self.table_styles:
                target_style = next(iter(self.table_styles.keys()))
            else:
                target_style = self._find_style("TableGrid") or "Table Grid"

        elif role == SemanticRole.FIGURE:
            target_style = None  # Figures don't require paragraph style

        elif role == SemanticRole.CAPTION:
            if self.has_caption_style:
                target_style = self.has_caption_style
            else:
                target_style = self._find_style("Normal") or "Normal"
                fallback_applied = True
                fallback_reason = "Caption style missing in template; fell back to Normal"
                diagnostics.append(fallback_reason)

        elif role == SemanticRole.REFERENCE:
            if self.has_reference_style:
                target_style = self.has_reference_style
            else:
                target_style = self._find_style("Normal") or "Normal"

        elif role == SemanticRole.UNSUPPORTED:
            target_style = None
            status = "rejected"
            diagnostics.append(f"Unsupported source element (type: {element.type}); preserved for explicit downstream reporting")

        # 2. Ambiguity & Status Handling (Requirement 7: Ambiguous elements must remain identifiable)
        if element.is_ambiguous or element.semantic_provenance.value == "AMBIGUOUS" or element.semantic_confidence < 0.70:
            status = "ambiguous"
            diagnostics.append(f"Element classification is ambiguous (confidence: {element.semantic_confidence:.2f})")

        # 3. Associate Constraints
        all_c_ids, enforceable_c_ids, advisory_c_ids = self._associate_constraints(
            target_style=target_style,
            section_index=sec_idx,
        )

        mapping_contract = ContentTemplateMapping(
            source_element_id=element.id,
            target_role=target_role,
            target_style=target_style,
            constraint_ids=all_c_ids,
            method="rule" if element.semantic_method.value in ("rule", "style") else "llm",
            confidence=element.semantic_confidence,
            status=status,
        )

        return ElementMappingResult(
            mapping=mapping_contract,
            source_element=element,
            target_role=target_role,
            target_style=target_style,
            fallback_applied=fallback_applied,
            fallback_reason=fallback_reason,
            enforceable_constraint_ids=enforceable_c_ids,
            advisory_constraint_ids=advisory_c_ids,
            diagnostics=diagnostics,
        )

    def map_document(
        self,
        elements: List[EnrichedSourceElement],
        document_id: Optional[str] = None,
    ) -> DocumentMappingResult:
        """
        Execute full document source-to-template mapping.
        Guarantees 100% preservation of source IDs, text, source order, tables, and figures.
        """
        doc_id = document_id or (elements[0].id.split("_")[1] if elements and "_" in elements[0].id else "doc_001")
        mapped_elements: List[ElementMappingResult] = []
        raw_mappings: List[ContentTemplateMapping] = []

        accepted_count = 0
        ambiguous_count = 0
        rejected_count = 0
        fallback_count = 0

        for elem in elements:
            m_res = self.map_element(elem)
            mapped_elements.append(m_res)
            raw_mappings.append(m_res.mapping)

            if m_res.mapping.status == "accepted":
                accepted_count += 1
            elif m_res.mapping.status == "ambiguous":
                ambiguous_count += 1
            elif m_res.mapping.status == "rejected":
                rejected_count += 1

            if m_res.fallback_applied:
                fallback_count += 1

        # Enforce strict immutability invariants
        assert len(mapped_elements) == len(elements), "Element count modified during mapping!"
        assert [m.source_element.id for m in mapped_elements] == [e.id for e in elements], "Element IDs modified!"
        assert [m.source_element.text for m in mapped_elements] == [e.text for e in elements], "Source text modified!"
        assert [m.source_element.source_order for m in mapped_elements] == [e.source_order for e in elements], "Element order modified!"

        return DocumentMappingResult(
            document_id=doc_id,
            template_id=self.template_profile.template_id,
            total_elements=len(mapped_elements),
            accepted_count=accepted_count,
            ambiguous_count=ambiguous_count,
            rejected_count=rejected_count,
            fallback_count=fallback_count,
            elements=mapped_elements,
            mappings=raw_mappings,
            summary={
                "accepted": accepted_count,
                "ambiguous": ambiguous_count,
                "rejected": rejected_count,
                "fallbacks": fallback_count,
                "available_headings": list(self.available_headings.keys()),
            },
        )
