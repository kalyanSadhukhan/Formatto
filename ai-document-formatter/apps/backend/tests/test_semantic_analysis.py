import json
import pytest
from app.domain.schemas.data_contracts import SourceElement
from app.semantics.classifier import SemanticClassifier
from app.semantics.llm_provider import (
    LLMMalformedResponseError,
    LLMProviderError,
    LLMTimeoutError,
    MockLLMProvider,
)
from app.semantics.models import (
    ClassificationMethod,
    ClassificationProvenance,
    EnrichedSourceElement,
    LLMSemanticClassification,
    SemanticRole,
)


def test_reliable_deterministic_classifications():
    """Verify that tables, figures, lists, captions, and references are classified deterministically."""
    elements = [
        SourceElement(id="el_1", type="table", source_order=1, confidence=1.0, metadata={"row_count": 3}),
        SourceElement(id="el_2", type="figure", source_order=2, confidence=1.0, metadata={"image_count": 1}),
        SourceElement(id="el_3", type="caption", text="Figure 1: Test diagram", source_order=3, confidence=0.95),
        SourceElement(id="el_4", type="bullet_list", text="Bullet item", source_order=4, confidence=1.0),
        SourceElement(id="el_5", type="numbered_list", text="Numbered item", source_order=5, confidence=1.0),
        SourceElement(id="el_6", type="reference", text="Doe, J. (2020). Test Paper.", source_order=6, confidence=1.0),
        SourceElement(id="el_7", type="unsupported", source_order=7, confidence=1.0, metadata={"raw_tag": "w:object"}),
        SourceElement(
            id="el_8",
            type="paragraph",
            text="This is a long narrative paragraph describing the background of the study in great detail. It contains multiple sentences and provides clear context.",
            source_order=8,
            style_name="Normal",
            confidence=1.0,
        ),
    ]

    classifier = SemanticClassifier()
    result = classifier.analyze_document(elements)

    assert result.total_elements == 8
    assert result.elements[0].semantic_role == SemanticRole.TABLE
    assert result.elements[1].semantic_role == SemanticRole.FIGURE
    assert result.elements[2].semantic_role == SemanticRole.CAPTION
    assert result.elements[3].semantic_role == SemanticRole.BULLET_LIST_ITEM
    assert result.elements[4].semantic_role == SemanticRole.NUMBERED_LIST_ITEM
    assert result.elements[5].semantic_role == SemanticRole.REFERENCE
    assert result.elements[6].semantic_role == SemanticRole.UNSUPPORTED
    assert result.elements[7].semantic_role == SemanticRole.BODY_PARAGRAPH

    for i in range(7):
        assert result.elements[i].semantic_method == ClassificationMethod.DETERMINISTIC_RULE
        assert result.elements[i].semantic_confidence >= 0.95


def test_ambiguous_headings_and_body_paragraphs_resolution():
    """Verify that ambiguous short bold paragraphs trigger the LLM provider for role resolution."""
    elements = [
        # Ambiguous element: "Normal" style, but short, bold, unpunctuated
        SourceElement(
            id="el_ambiguous_1",
            type="paragraph",
            text="2.3 Experimental Setup",
            source_order=10,
            style_name="Normal",
            confidence=0.8,
            metadata={"is_bold": True},
        ),
        # Unambiguous narrative body paragraph
        SourceElement(
            id="el_body_1",
            type="paragraph",
            text="The experimental setup consisted of three distinct testing rigs operated under controlled ambient conditions for forty-eight hours.",
            source_order=11,
            style_name="Normal",
            confidence=1.0,
        ),
    ]

    mock_llm = MockLLMProvider()
    classifier = SemanticClassifier(llm_provider=mock_llm)
    result = classifier.analyze_document(elements)

    ambiguous_res = result.elements[0]
    assert ambiguous_res.semantic_role == SemanticRole.HEADING
    assert ambiguous_res.semantic_method == ClassificationMethod.LLM
    assert ambiguous_res.semantic_confidence >= 0.85
    assert ambiguous_res.is_ambiguous is False  # Successfully resolved by LLM
    assert "llm_reasoning" in ambiguous_res.semantic_evidence

    body_res = result.elements[1]
    assert body_res.semantic_role == SemanticRole.BODY_PARAGRAPH
    assert body_res.semantic_method == ClassificationMethod.DETERMINISTIC_RULE


def test_custom_word_styles_classification():
    """Verify handling of custom heading styles and document title styles."""
    elements = [
        SourceElement(
            id="el_title",
            type="paragraph",
            text="Annual Engineering Assessment 2026",
            source_order=1,
            style_name="Title",
            confidence=0.9,
        ),
        SourceElement(
            id="el_custom_head",
            type="heading",
            text="Executive Summary",
            level=1,
            source_order=2,
            style_name="ExecutiveHeaderStyle",
            confidence=0.95,
        ),
    ]

    classifier = SemanticClassifier()
    result = classifier.analyze_document(elements)

    assert result.elements[0].semantic_role == SemanticRole.DOCUMENT_TITLE
    assert result.elements[1].semantic_role == SemanticRole.HEADING
    assert result.elements[1].level == 1


def test_invalid_llm_response_handling():
    """Verify that malformed LLM responses fall back cleanly without terminating execution."""
    elements = [
        SourceElement(
            id="el_ambiguous",
            type="paragraph",
            text="Project Findings",
            source_order=5,
            style_name="Normal",
            confidence=0.8,
            metadata={"is_bold": True},
        ),
    ]

    # Provider simulating malformed JSON / schema violation
    mock_llm = MockLLMProvider(simulate_malformed=True)
    classifier = SemanticClassifier(llm_provider=mock_llm)

    result = classifier.analyze_document(elements)

    res = result.elements[0]
    assert res.semantic_method == ClassificationMethod.FALLBACK
    assert res.semantic_provenance == ClassificationProvenance.FALLBACK
    assert res.is_ambiguous is True
    assert "llm_error" in res.semantic_evidence
    assert res.text == "Project Findings"  # Content intact!


def test_provider_timeout_and_failure():
    """Verify that LLM timeouts and provider connection failures fall back cleanly."""
    elements = [
        SourceElement(
            id="el_ambiguous",
            type="paragraph",
            text="Important Note",
            source_order=3,
            style_name="Normal",
            confidence=0.7,
            metadata={"is_bold": True},
        ),
    ]

    # Test timeout
    timeout_provider = MockLLMProvider(simulate_timeout=True)
    classifier = SemanticClassifier(llm_provider=timeout_provider)
    result_timeout = classifier.analyze_document(elements)
    assert result_timeout.elements[0].semantic_method == ClassificationMethod.FALLBACK
    assert result_timeout.elements[0].semantic_evidence["error_type"] == "LLMTimeoutError"

    # Test provider failure
    failure_provider = MockLLMProvider(simulate_failure=True)
    classifier_failure = SemanticClassifier(llm_provider=failure_provider)
    result_failure = classifier_failure.analyze_document(elements)
    assert result_failure.elements[0].semantic_method == ClassificationMethod.FALLBACK
    assert result_failure.elements[0].semantic_evidence["error_type"] == "LLMProviderError"


def test_low_confidence_results():
    """Verify that low-confidence LLM outputs preserve low confidence and remain flagged ambiguous."""
    elements = [
        SourceElement(
            id="el_ambiguous",
            type="paragraph",
            text="Uncertain Block",
            source_order=4,
            style_name="Normal",
            confidence=0.6,
            metadata={"is_bold": True},
        ),
    ]

    low_conf_provider = MockLLMProvider(simulate_low_confidence=True)
    classifier = SemanticClassifier(llm_provider=low_conf_provider, confidence_threshold=0.70)
    result = classifier.analyze_document(elements)

    res = result.elements[0]
    assert res.semantic_confidence == 0.55
    assert res.is_ambiguous is True
    assert res.semantic_provenance == ClassificationProvenance.AMBIGUOUS
    assert "low_confidence_note" in res.semantic_evidence


def test_unicode_content_preservation():
    """Verify that Unicode content (Hindi, Japanese, accented characters) is preserved 100% byte-for-byte."""
    unicode_text = "दिल्ली में ई-अपशिष्ट संकट — 東京の廃棄物 — Modèle d'évaluation €45,000"
    elements = [
        SourceElement(
            id="el_unicode",
            type="paragraph",
            text=unicode_text,
            source_order=1,
            style_name="Normal",
            confidence=1.0,
        ),
    ]

    classifier = SemanticClassifier()
    result = classifier.analyze_document(elements)

    assert result.elements[0].text == unicode_text


def test_source_content_and_order_preservation():
    """Verify that element count, ordering, and text are strictly immutable."""
    elements = [
        SourceElement(id="el_1", type="heading", text="Heading 1", level=1, source_order=1, confidence=1.0),
        SourceElement(id="el_2", type="paragraph", text="Paragraph text here.", source_order=2, confidence=1.0),
        SourceElement(id="el_3", type="table", source_order=3, confidence=1.0),
        SourceElement(id="el_4", type="figure", source_order=4, confidence=1.0),
    ]

    classifier = SemanticClassifier()
    result = classifier.analyze_document(elements)

    assert len(result.elements) == len(elements)
    assert [e.id for e in result.elements] == ["el_1", "el_2", "el_3", "el_4"]
    assert [e.source_order for e in result.elements] == [1, 2, 3, 4]
    assert [e.text for e in result.elements] == ["Heading 1", "Paragraph text here.", None, None]


def test_repeatability_and_determinism():
    """Verify that repeating semantic analysis on the same input produces identical output."""
    elements = [
        SourceElement(id="el_1", type="heading", text="Chapter 1", level=1, source_order=1, confidence=1.0),
        SourceElement(id="el_2", type="paragraph", text="Body text.", source_order=2, confidence=1.0),
        SourceElement(id="el_3", type="paragraph", text="Short Bold", source_order=3, confidence=0.7, metadata={"is_bold": True}),
    ]

    classifier = SemanticClassifier()
    run1 = classifier.analyze_document(elements)
    run2 = classifier.analyze_document(elements)

    assert run1.model_dump_json() == run2.model_dump_json()


def test_real_sample_docx_semantic_analysis():
    """Integration test: Semantic analysis on the full real-world report extraction.json (143 elements)."""
    import os
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "flow_report")
    sample_json_path = os.path.join(fixtures_dir, "extraction.json")
    if not os.path.exists(sample_json_path):
        sample_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "extraction.json")
    if not os.path.exists(sample_json_path):
        pytest.skip("extraction.json not found")

    with open(sample_json_path, "r", encoding="utf-8") as f:
        raw_elements = json.load(f)

    elements = [SourceElement(**item) for item in raw_elements]
    assert len(elements) == 143

    classifier = SemanticClassifier()
    result = classifier.analyze_document(elements)

    assert result.total_elements == 143
    assert result.elements[0].semantic_role == SemanticRole.FIGURE
    assert result.role_counts[SemanticRole.TABLE.value] == 1
    assert result.role_counts[SemanticRole.FIGURE.value] == 4
    assert result.role_counts[SemanticRole.CAPTION.value] == 2
    assert result.role_counts[SemanticRole.BULLET_LIST_ITEM.value] == 30
    assert result.role_counts[SemanticRole.NUMBERED_LIST_ITEM.value] == 11
    assert result.role_counts[SemanticRole.REFERENCE.value] == 2
    assert result.role_counts[SemanticRole.HEADING.value] >= 26
    assert result.role_counts[SemanticRole.BODY_PARAGRAPH.value] >= 50

    # Verify 100% text preservation
    for orig, enriched in zip(elements, result.elements):
        assert orig.id == enriched.id
        assert orig.text == enriched.text
        assert orig.source_order == enriched.source_order


def test_semantic_analysis_stage_execution():
    """Verify that SemanticAnalysisStage pipeline wrapper executes cleanly."""
    from app.pipeline.stages.semantic_analysis_stage import SemanticAnalysisStage

    elements = [
        SourceElement(id="el_1", type="heading", text="Introduction", level=1, source_order=1, confidence=1.0),
        SourceElement(id="el_2", type="paragraph", text="Body text.", source_order=2, confidence=1.0),
    ]

    stage = SemanticAnalysisStage()
    result = stage.execute(elements, document_id="doc_stage_test")

    assert result.document_id == "doc_stage_test"
    assert result.total_elements == 2
    assert result.elements[0].semantic_role == SemanticRole.HEADING
