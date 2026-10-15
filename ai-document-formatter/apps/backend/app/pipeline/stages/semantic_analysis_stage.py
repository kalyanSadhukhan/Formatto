import logging
from typing import List, Optional

from app.domain.schemas.data_contracts import SourceElement
from app.semantics.classifier import SemanticClassifier
from app.semantics.llm_provider import BaseLLMProvider, get_llm_provider
from app.semantics.models import EnrichedSourceElement, SemanticAnalysisResult

logger = logging.getLogger(__name__)


class SemanticAnalysisStage:
    """
    Pipeline stage for Phase 4: Source Semantic Analysis.
    Consumes extracted SourceElements and produces EnrichedSourceElements with semantic annotations.
    """

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None, threshold: float = 0.70):
        self.provider = llm_provider or get_llm_provider()
        self.classifier = SemanticClassifier(llm_provider=self.provider, confidence_threshold=threshold)

    def execute(self, elements: List[SourceElement], document_id: Optional[str] = None) -> SemanticAnalysisResult:
        logger.info(f"Starting semantic analysis stage for document {document_id or 'unknown'} ({len(elements)} elements)")
        result = self.classifier.analyze_document(elements, document_id=document_id)
        logger.info(
            f"Semantic analysis completed: {result.deterministic_classified_count} deterministic, "
            f"{result.ambiguous_elements_count} ambiguous ({result.llm_classified_count} LLM classified)"
        )
        return result
