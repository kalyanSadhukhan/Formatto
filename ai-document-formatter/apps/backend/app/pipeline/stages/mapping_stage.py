import logging
from typing import List, Optional

from app.mapping.mapper import ContentTemplateMapper
from app.mapping.models import DocumentMappingResult
from app.mapping.template_preservation import TemplatePreservationMapper
from app.semantics.models import EnrichedSourceElement
from app.templates.models import TemplateProfile

logger = logging.getLogger(__name__)


class MappingStage:
    """
    Pipeline stage for Phase 5: Content-to-Template Mapping.
    Consumes EnrichedSourceElements and a TemplateProfile to produce a DocumentMappingResult
    that maps each source element to target template roles, styles, and constraints.
    """

    def __init__(self, template_profile: TemplateProfile):
        self.template_profile = template_profile
        self.mapper = ContentTemplateMapper(template_profile)
        self.preservation_mapper = TemplatePreservationMapper()

    def execute(
        self,
        elements: List[EnrichedSourceElement],
        document_id: Optional[str] = None,
        source_docx_path: Optional[str] = None,
    ) -> DocumentMappingResult:
        logger.info(
            f"Starting mapping stage for document {document_id or 'unknown'} "
            f"against template {self.template_profile.template_id} ({len(elements)} elements)"
        )
        result = self.mapper.map_document(elements, document_id=document_id)

        # If the template is structured (has tables/forms/multi-sections), extract field-slot mappings
        if self.template_profile.is_structured_template and source_docx_path:
            logger.info("Extracting structured template content-slot mappings...")
            extraction = self.preservation_mapper.extract_source_fields(source_docx_path, elements)
            result.summary["is_structured_template"] = True
            result.summary["template_fields"] = extraction.model_dump()
            result.summary["unresolved_mappings"] = extraction.unresolved_elements
            result.summary["template_tables_count"] = len(self.template_profile.template_tables)

        logger.info(
            f"Mapping completed: {result.accepted_count} accepted, "
            f"{result.ambiguous_count} ambiguous, {result.rejected_count} rejected, "
            f"{result.fallback_count} fallbacks applied."
        )
        return result

