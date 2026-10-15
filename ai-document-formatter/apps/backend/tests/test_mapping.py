import json
import os
import pytest

from app.domain.schemas.data_contracts import ContentTemplateMapping, DocumentIR, SourceElement, TemplateConstraint
from app.mapping.mapper import ContentTemplateMapper
from app.mapping.models import DocumentMappingResult, ElementMappingResult
from app.pipeline.stages.mapping_stage import MappingStage
from app.semantics.classifier import SemanticClassifier
from app.semantics.models import (
    ClassificationMethod,
    ClassificationProvenance,
    EnrichedSourceElement,
    SemanticRole,
)
from app.templates.models import SectionSettings, StyleDefinition, StylePropertyModel, TableStyleDefinition, TemplateProfile


@pytest.fixture
def mock_template_profile() -> TemplateProfile:
    """Create a controlled mock template profile with explicit heading levels and styles."""
    styles = {
        "Normal": StyleDefinition(
            style_id="Normal",
            style_name="Normal",
            style_type="paragraph",
            direct_properties=StylePropertyModel(font_name="Calibri", font_size_pt=11.0),
        ),
        "Title": StyleDefinition(
            style_id="Title",
            style_name="Title",
            style_type="paragraph",
            direct_properties=StylePropertyModel(font_name="Calibri Light", font_size_pt=24.0, bold=True),
        ),
        "Heading 1": StyleDefinition(
            style_id="Heading 1",
            style_name="Heading 1",
            style_type="paragraph",
            direct_properties=StylePropertyModel(font_name="Calibri Light", font_size_pt=16.0, bold=True, outline_level=1),
        ),
        "Heading 2": StyleDefinition(
            style_id="Heading 2",
            style_name="Heading 2",
            style_type="paragraph",
            direct_properties=StylePropertyModel(font_name="Calibri Light", font_size_pt=13.0, bold=True, outline_level=2),
        ),
        "List Bullet": StyleDefinition(
            style_id="List Bullet",
            style_name="List Bullet",
            style_type="paragraph",
            direct_properties=StylePropertyModel(font_name="Calibri", font_size_pt=11.0),
        ),
        "List Number": StyleDefinition(
            style_id="List Number",
            style_name="List Number",
            style_type="paragraph",
            direct_properties=StylePropertyModel(font_name="Calibri", font_size_pt=11.0),
        ),
        "Caption": StyleDefinition(
            style_id="Caption",
            style_name="Caption",
            style_type="paragraph",
            direct_properties=StylePropertyModel(font_name="Calibri", font_size_pt=9.0, italic=True),
        ),
    }

    table_styles = {
        "Table Grid": TableStyleDefinition(
            style_id="Table Grid",
            style_name="Table Grid",
            has_borders=True,
        )
    }

    constraints = [
        TemplateConstraint(
            id="tc_sec_0_page_size",
            category="page",
            target="section.0",
            property="page_size_name",
            expected_value="Letter",
            provenance="EXTRACTED",
            confidence=1.0,
            enforceable=True,
        ),
        TemplateConstraint(
            id="tc_Heading1_font_size",
            category="typography",
            target="style.Heading1",
            property="font_size_pt",
            expected_value=16.0,
            provenance="EXTRACTED",
            confidence=1.0,
            enforceable=True,
        ),
        TemplateConstraint(
            id="tc_Heading1_inherited_line_spacing",
            category="paragraph",
            target="style.Heading1",
            property="line_spacing",
            expected_value=1.15,
            provenance="INFERRED",
            confidence=0.85,
            enforceable=False,
        ),
    ]

    return TemplateProfile(
        template_id="tpl_mock_001",
        sections=[
            SectionSettings(
                section_index=0,
                page_width_pt=612.0,
                page_height_pt=792.0,
                margins_pt={"top": 72.0, "bottom": 72.0, "left": 72.0, "right": 72.0},
            )
        ],
        styles=styles,
        table_styles=table_styles,
        constraints=constraints,
    )


def test_title_and_heading_mapping(mock_template_profile):
    """Verify that document title maps to Title, and headings map to available levels."""
    elements = [
        EnrichedSourceElement(
            id="el_title",
            type="paragraph",
            text="Technical Architecture Report",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.DOCUMENT_TITLE,
            semantic_confidence=0.95,
            semantic_method=ClassificationMethod.STYLE_EVIDENCE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
        EnrichedSourceElement(
            id="el_h1",
            type="heading",
            level=1,
            text="1. Introduction",
            source_order=2,
            confidence=1.0,
            semantic_role=SemanticRole.HEADING,
            semantic_confidence=0.98,
            semantic_method=ClassificationMethod.STYLE_EVIDENCE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
        EnrichedSourceElement(
            id="el_h2",
            type="heading",
            level=2,
            text="1.1 Overview",
            source_order=3,
            confidence=1.0,
            semantic_role=SemanticRole.HEADING,
            semantic_confidence=0.98,
            semantic_method=ClassificationMethod.STYLE_EVIDENCE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    assert res.total_elements == 3
    assert res.accepted_count == 3
    assert res.elements[0].target_role == "document_title"
    assert res.elements[0].target_style == "Title"
    assert res.elements[0].fallback_applied is False

    assert res.elements[1].target_role == "heading"
    assert res.elements[1].target_style == "Heading 1"
    assert res.elements[1].fallback_applied is False

    assert res.elements[2].target_role == "heading"
    assert res.elements[2].target_style == "Heading 2"
    assert res.elements[2].fallback_applied is False


def test_heading_level_fallback(mock_template_profile):
    """
    Verify that if source requires 'Heading 5' but template only has up to 'Heading 2',
    it deterministically falls back to closest available heading (Heading 2) and logs a warning.
    """
    elements = [
        EnrichedSourceElement(
            id="el_h5",
            type="heading",
            level=5,
            text="1.1.1.1.1 Deep Subsection",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.HEADING,
            semantic_confidence=0.95,
            semantic_method=ClassificationMethod.STYLE_EVIDENCE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    m = res.elements[0]
    assert m.target_role == "heading"
    assert m.target_style == "Heading 2"  # Closest available heading <= 5
    assert m.fallback_applied is True
    assert "Heading level 5 not defined in template" in m.fallback_reason
    assert len(m.diagnostics) >= 1
    assert m.mapping.status == "accepted"


def test_body_paragraph_mapping(mock_template_profile):
    """Verify standard body paragraph mapping to Normal style."""
    elements = [
        EnrichedSourceElement(
            id="el_p",
            type="paragraph",
            text="Narrative body text explaining system behavior.",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.BODY_PARAGRAPH,
            semantic_confidence=0.95,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.INFERRED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    assert res.elements[0].target_role == "body_paragraph"
    assert res.elements[0].target_style == "Normal"
    assert res.elements[0].mapping.status == "accepted"


def test_bullet_and_numbered_list_mapping(mock_template_profile):
    """Verify bullet and numbered list mapping to template list styles."""
    elements = [
        EnrichedSourceElement(
            id="el_b",
            type="bullet_list",
            text="Bullet item",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.BULLET_LIST_ITEM,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
        EnrichedSourceElement(
            id="el_n",
            type="numbered_list",
            text="Numbered item",
            source_order=2,
            confidence=1.0,
            semantic_role=SemanticRole.NUMBERED_LIST_ITEM,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    assert res.elements[0].target_role == "bullet_list_item"
    assert res.elements[0].target_style == "List Bullet"

    assert res.elements[1].target_role == "numbered_list_item"
    assert res.elements[1].target_style == "List Number"


def test_table_and_figure_preservation(mock_template_profile):
    """Verify that table cells, rows, merges, and figure relationships are completely preserved."""
    table_meta = {
        "row_count": 2,
        "column_count": 2,
        "cell_text": [["Header 1", "Header 2"], ["Data 1", "Data 2"]],
        "merged_cells_info": [{"row": 0, "col": 0, "state": "restart", "row_span": 2}],
    }
    figure_meta = {
        "image_count": 2,
        "drawing_rids": ["rId10", "rId11"],
        "caption_id": "el_cap",
    }

    elements = [
        EnrichedSourceElement(
            id="el_tbl",
            type="table",
            source_order=1,
            confidence=1.0,
            metadata=table_meta,
            semantic_role=SemanticRole.TABLE,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
        EnrichedSourceElement(
            id="el_fig",
            type="figure",
            source_order=2,
            confidence=1.0,
            metadata=figure_meta,
            semantic_role=SemanticRole.FIGURE,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    # Table verification
    t_res = res.elements[0]
    assert t_res.target_role == "table"
    assert t_res.target_style == "Table Grid"
    assert t_res.source_element.metadata["row_count"] == 2
    assert t_res.source_element.metadata["cell_text"] == [["Header 1", "Header 2"], ["Data 1", "Data 2"]]
    assert len(t_res.source_element.metadata["merged_cells_info"]) == 1

    # Figure verification
    f_res = res.elements[1]
    assert f_res.target_role == "figure"
    assert f_res.source_element.metadata["image_count"] == 2
    assert f_res.source_element.metadata["drawing_rids"] == ["rId10", "rId11"]


def test_caption_and_reference_mapping(mock_template_profile):
    """Verify caption and reference mapping to template styles."""
    elements = [
        EnrichedSourceElement(
            id="el_cap",
            type="caption",
            text="Figure 1: Diagram of architecture",
            source_order=1,
            confidence=0.98,
            semantic_role=SemanticRole.CAPTION,
            semantic_confidence=0.98,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
            metadata={"figure_id": "el_fig"},
        ),
        EnrichedSourceElement(
            id="el_ref",
            type="reference",
            text="Smith, A. (2022). Document Systems.",
            source_order=2,
            confidence=0.98,
            semantic_role=SemanticRole.REFERENCE,
            semantic_confidence=0.98,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    assert res.elements[0].target_role == "caption"
    assert res.elements[0].target_style == "Caption"
    assert res.elements[0].source_element.metadata["figure_id"] == "el_fig"

    assert res.elements[1].target_role == "reference"
    assert res.elements[1].target_style == "Normal"


def test_ambiguous_semantic_elements_handling(mock_template_profile):
    """Verify that ambiguous elements preserve their ambiguity status and confidence without fabrication."""
    elements = [
        EnrichedSourceElement(
            id="el_amb",
            type="paragraph",
            text="Uncertain role heading or paragraph",
            source_order=1,
            confidence=0.60,
            semantic_role=SemanticRole.HEADING,
            semantic_confidence=0.60,
            semantic_method=ClassificationMethod.LLM,
            semantic_provenance=ClassificationProvenance.AMBIGUOUS,
            is_ambiguous=True,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    m = res.elements[0]
    assert m.mapping.status == "ambiguous"
    assert m.mapping.confidence == 0.60
    assert any("ambiguous" in d for d in m.diagnostics)


def test_missing_template_styles_fallback():
    """Verify fallback when template has only 'Normal' style and lacks custom styles."""
    minimal_profile = TemplateProfile(
        template_id="tpl_minimal",
        styles={
            "Normal": StyleDefinition(style_id="Normal", style_name="Normal", style_type="paragraph")
        },
    )

    elements = [
        EnrichedSourceElement(
            id="el_title",
            type="paragraph",
            text="My Document Title",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.DOCUMENT_TITLE,
            semantic_confidence=0.95,
            semantic_method=ClassificationMethod.STYLE_EVIDENCE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
        EnrichedSourceElement(
            id="el_cap",
            type="caption",
            text="Figure 1: Caption",
            source_order=2,
            confidence=1.0,
            semantic_role=SemanticRole.CAPTION,
            semantic_confidence=0.95,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(minimal_profile)
    res = mapper.map_document(elements)

    assert res.fallback_count == 2
    assert res.elements[0].target_style == "Normal"
    assert res.elements[0].fallback_applied is True
    assert res.elements[1].target_style == "Normal"
    assert res.elements[1].fallback_applied is True


def test_unsupported_elements_reporting(mock_template_profile):
    """Verify that unsupported elements are rejected, diagnosed, and NOT silently dropped."""
    elements = [
        EnrichedSourceElement(
            id="el_unsup",
            type="unsupported",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.UNSUPPORTED,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
            metadata={"raw_tag": "w:customXml"},
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    assert res.rejected_count == 1
    m = res.elements[0]
    assert m.mapping.status == "rejected"
    assert m.target_style is None
    assert any("Unsupported source element" in d for d in m.diagnostics)


def test_deterministic_repeated_mapping(mock_template_profile):
    """Verify that repeat mapping runs produce byte-identical JSON serialization."""
    elements = [
        EnrichedSourceElement(
            id="el_1",
            type="heading",
            level=1,
            text="Chapter 1",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.HEADING,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.STYLE_EVIDENCE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
        EnrichedSourceElement(
            id="el_2",
            type="paragraph",
            text="Paragraph body.",
            source_order=2,
            confidence=1.0,
            semantic_role=SemanticRole.BODY_PARAGRAPH,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.INFERRED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    run1 = mapper.map_document(elements)
    run2 = mapper.map_document(elements)

    assert run1.model_dump_json() == run2.model_dump_json()


def test_template_constraints_provenance_association(mock_template_profile):
    """Verify that enforceable constraints (EXTRACTED) and advisory constraints (INFERRED) are partitioned correctly."""
    elements = [
        EnrichedSourceElement(
            id="el_h1",
            type="heading",
            level=1,
            text="Heading with constraints",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.HEADING,
            semantic_confidence=0.98,
            semantic_method=ClassificationMethod.STYLE_EVIDENCE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements)

    m = res.elements[0]
    assert "tc_Heading1_font_size" in m.enforceable_constraint_ids
    assert "tc_Heading1_inherited_line_spacing" in m.advisory_constraint_ids
    assert "tc_sec_0_page_size" in m.enforceable_constraint_ids


def test_document_ir_generation_compatibility(mock_template_profile):
    """Verify that mapped output directly produces a valid DocumentIR instance adhering to contracts."""
    elements = [
        EnrichedSourceElement(
            id="el_1",
            type="heading",
            level=1,
            text="Heading IR Test",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.HEADING,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.STYLE_EVIDENCE,
            semantic_provenance=ClassificationProvenance.EXTRACTED,
            is_ambiguous=False,
        ),
    ]

    mapper = ContentTemplateMapper(mock_template_profile)
    res = mapper.map_document(elements, document_id="doc_ir_test")
    ir = res.to_document_ir()

    assert isinstance(ir, DocumentIR)
    assert ir.document_id == "doc_ir_test"
    assert len(ir.elements) == 1
    ir_elem = ir.elements[0]
    assert ir_elem.id == "ir_el_1"
    assert ir_elem.type == "heading"
    assert ir_elem.content == "Heading IR Test"
    assert ir_elem.style_ref == "Heading 1"
    assert ir_elem.target_id == "target_el_1"


def test_mapping_stage_pipeline_wrapper(mock_template_profile):
    """Verify that MappingStage pipeline stage executes cleanly."""
    elements = [
        EnrichedSourceElement(
            id="el_1",
            type="paragraph",
            text="Pipeline stage text.",
            source_order=1,
            confidence=1.0,
            semantic_role=SemanticRole.BODY_PARAGRAPH,
            semantic_confidence=1.0,
            semantic_method=ClassificationMethod.DETERMINISTIC_RULE,
            semantic_provenance=ClassificationProvenance.INFERRED,
            is_ambiguous=False,
        ),
    ]

    stage = MappingStage(mock_template_profile)
    res = stage.execute(elements, document_id="doc_pipeline_test")

    assert res.document_id == "doc_pipeline_test"
    assert res.total_elements == 1
    assert res.accepted_count == 1


def test_real_sample_docx_end_to_end_mapping():
    """Integration test: full end-to-end mapping on real 143-element sample.docx and its template profile."""
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures", "flow_report")
    sample_json = os.path.join(fixtures_dir, "semantic_elements.json")
    if not os.path.exists(sample_json):
        sample_json = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "semantic_elements.json")

    tpl_json = os.path.join(fixtures_dir, "template_profile.json")
    if not os.path.exists(tpl_json):
        tpl_json = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "template_profile.json")

    if not os.path.exists(sample_json) or not os.path.exists(tpl_json):
        pytest.skip("sample artifacts not found in workspace")

    with open(sample_json, "r", encoding="utf-8") as f:
        sem_data = json.load(f)
    with open(tpl_json, "r", encoding="utf-8") as f:
        tpl_data = json.load(f)

    elements = [EnrichedSourceElement(**e) for e in sem_data["elements"]]
    template_profile = TemplateProfile(**tpl_data)

    assert len(elements) == 143

    mapper = ContentTemplateMapper(template_profile)
    res = mapper.map_document(elements)

    assert res.total_elements == 143
    assert res.accepted_count == 143
    assert len(res.mappings) == 143

    # Verify 100% preservation of source IDs, text, and order
    for orig, mapped in zip(elements, res.elements):
        assert orig.id == mapped.source_element.id
        assert orig.text == mapped.source_element.text
        assert orig.source_order == mapped.source_element.source_order
        assert orig.type == mapped.source_element.type

    # Verify DocumentIR generation
    ir = res.to_document_ir()
    assert isinstance(ir, DocumentIR)
    assert len(ir.elements) == 143
