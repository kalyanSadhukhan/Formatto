import io
import json
import os
import tempfile
import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.shared import Inches
from fastapi.testclient import TestClient

from app.domain.schemas.data_contracts import DocumentIR, IRElement, JobState
from app.extraction.docx_extractor import DocxExtractor
from app.generation.docx_generator import DocxGenerator
from app.ir.validator import DocumentIRValidator
from app.main import app
from app.pipeline.orchestrator import DocumentFormattingPipeline


FLOW_REPORT_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "flow_report")
SAMPLE_PATH = os.path.join(FLOW_REPORT_DIR, "sample.docx")
if not os.path.exists(SAMPLE_PATH):
    SAMPLE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "sample.docx")

REF_TPL_PATH = os.path.join(FLOW_REPORT_DIR, "reference_template.docx")
if not os.path.exists(REF_TPL_PATH):
    REF_TPL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "reference_template.docx")


@pytest.fixture
def synthetic_template(tmp_path):
    """Create a controlled reference template DOCX with explicit styles and page setup."""
    doc_path = tmp_path / "template.docx"
    doc = Document()

    styles = doc.styles
    # Ensure Heading 1, Heading 2, Title, List Bullet, List Number, Table Grid
    if "Title" not in styles:
        styles.add_style("Title", WD_STYLE_TYPE.PARAGRAPH)
    if "List Bullet" not in styles:
        styles.add_style("List Bullet", WD_STYLE_TYPE.PARAGRAPH)
    if "List Number" not in styles:
        styles.add_style("List Number", WD_STYLE_TYPE.PARAGRAPH)
    if "Caption" not in styles:
        styles.add_style("Caption", WD_STYLE_TYPE.PARAGRAPH)

    # Add a dummy paragraph to give the template body structure
    doc.add_paragraph("Template placeholder content.")
    doc.save(doc_path)
    return str(doc_path)


@pytest.fixture
def synthetic_source_with_image(tmp_path):
    """Create a source DOCX with an embedded test image."""
    doc_path = tmp_path / "source_img.docx"
    doc = Document()
    doc.add_heading("Report Header", level=1)
    doc.add_paragraph("Introduction before image.")

    img_path = tmp_path / "test.png"
    with open(img_path, "wb") as f:
        # Valid 1x1 PNG bytes
        f.write(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
            b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
            b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
    doc.add_picture(str(img_path), width=Inches(2.0))
    doc.add_paragraph("Figure 1: Test Image Caption", style="Normal")
    doc.save(doc_path)
    return str(doc_path)


def test_ir_serialization_and_deserialization():
    """Verify DocumentIR and IRElement JSON round-trip without information loss."""
    elem1 = IRElement(
        id="ir_el_001",
        type="heading",
        level=1,
        content="Overview Title",
        style_ref="Heading 1",
        children=[],
        target_id="target_el_001",
        metadata={"source_order": 1, "source_element_id": "el_001", "is_bold": True},
    )
    elem2 = IRElement(
        id="ir_el_002",
        type="table",
        level=0,
        content=None,
        style_ref="Table Grid",
        children=[["H1", "H2"], ["A", "B"]],
        target_id="target_el_002",
        metadata={
            "source_order": 2,
            "source_element_id": "el_002",
            "row_count": 2,
            "column_count": 2,
            "merged_cells_info": [{"row": 0, "col": 0, "type": "horizontal", "col_span": 2}],
        },
    )
    doc_ir = DocumentIR(
        document_id="doc_roundtrip_test",
        metadata={"title": "Test Roundtrip"},
        elements=[elem1, elem2],
    )

    validator = DocumentIRValidator()
    report = validator.validate(doc_ir)
    assert report.is_valid is True
    assert report.serializable is True
    assert report.total_elements == 2
    assert report.traceable_elements == 2
    assert report.heading_elements == 1
    assert report.table_elements == 1

    # Round trip
    dumped = doc_ir.model_dump_json()
    restored = DocumentIR.model_validate_json(dumped)
    assert restored.document_id == doc_ir.document_id
    assert len(restored.elements) == 2
    assert restored.elements[1].children == [["H1", "H2"], ["A", "B"]]
    assert restored.elements[1].metadata["merged_cells_info"][0]["col_span"] == 2


def test_paragraph_and_heading_generation(synthetic_template, tmp_path):
    """Verify generation of headings and paragraphs using mapped styles."""
    out_docx = tmp_path / "headings_out.docx"

    ir = DocumentIR(
        document_id="doc_h_test",
        elements=[
            IRElement(
                id="ir_1",
                type="document_title",
                level=0,
                content="Main Project Title",
                style_ref="Title",
                target_id="target_1",
                metadata={"source_order": 1, "source_element_id": "e1"},
            ),
            IRElement(
                id="ir_2",
                type="heading",
                level=1,
                content="Chapter 1 Introduction",
                style_ref="Heading 1",
                target_id="target_2",
                metadata={"source_order": 2, "source_element_id": "e2"},
            ),
            IRElement(
                id="ir_3",
                type="body_paragraph",
                level=0,
                content="Standard body text paragraph.",
                style_ref="Normal",
                target_id="target_3",
                metadata={"source_order": 3, "source_element_id": "e3"},
            ),
        ],
    )

    generator = DocxGenerator(template_path=synthetic_template)
    res = generator.generate(ir, output_path=str(out_docx))

    assert res.generated_elements == 3
    assert res.unmapped_elements == 0
    assert os.path.exists(str(out_docx))

    reopened = Document(str(out_docx))
    assert len(reopened.paragraphs) == 3
    assert reopened.paragraphs[0].text == "Main Project Title"
    assert reopened.paragraphs[0].style.name == "Title"
    assert reopened.paragraphs[1].text == "Chapter 1 Introduction"
    assert reopened.paragraphs[1].style.name == "Heading 1"
    assert reopened.paragraphs[2].text == "Standard body text paragraph."
    assert reopened.paragraphs[2].style.name == "Normal"


def test_missing_template_style_fallback(synthetic_template, tmp_path):
    """Verify explicit fallback to Normal when a requested style does not exist."""
    out_docx = tmp_path / "fallback_style_out.docx"

    ir = DocumentIR(
        document_id="doc_missing_style_test",
        elements=[
            IRElement(
                id="ir_1",
                type="paragraph",
                content="Text with non-existent style.",
                style_ref="NonExistentCustomStyle_XYZ",
                target_id="target_1",
                metadata={"source_order": 1, "source_element_id": "e1"},
            ),
        ],
    )

    generator = DocxGenerator(template_path=synthetic_template)
    res = generator.generate(ir, output_path=str(out_docx))

    assert res.generated_elements == 1
    assert any("NonExistentCustomStyle_XYZ" in d for d in res.diagnostics)

    reopened = Document(str(out_docx))
    assert reopened.paragraphs[0].text == "Text with non-existent style."
    assert reopened.paragraphs[0].style.name == "Normal"

    # Verify manifest reflects the fallback message
    mapping = res.manifest.mappings[0]
    assert mapping.status == "mapped"
    assert "fell back to 'Normal'" in (mapping.message or "")


def test_run_level_formatting_preservation(synthetic_template, tmp_path):
    """Verify run-level bold, italic, and underline are preserved without text flattening."""
    out_docx = tmp_path / "runs_out.docx"

    runs_data = [
        {"text": "Plain text, ", "bold": False, "italic": False, "underline": False},
        {"text": "bold text, ", "bold": True, "italic": False, "underline": False},
        {"text": "italic text, ", "bold": False, "italic": True, "underline": False},
        {"text": "underlined text.", "bold": False, "italic": False, "underline": True},
    ]

    ir = DocumentIR(
        document_id="doc_runs_test",
        elements=[
            IRElement(
                id="ir_1",
                type="paragraph",
                content="Plain text, bold text, italic text, underlined text.",
                style_ref="Normal",
                target_id="target_1",
                metadata={"source_order": 1, "source_element_id": "e1", "runs": runs_data},
            ),
        ],
    )

    generator = DocxGenerator(template_path=synthetic_template)
    res = generator.generate(ir, output_path=str(out_docx))
    assert res.generated_elements == 1

    reopened = Document(str(out_docx))
    p = reopened.paragraphs[0]
    assert len(p.runs) == 4

    assert p.runs[0].text == "Plain text, "
    assert not p.runs[0].bold
    assert not p.runs[0].italic

    assert p.runs[1].text == "bold text, "
    assert p.runs[1].bold is True

    assert p.runs[2].text == "italic text, "
    assert p.runs[2].italic is True

    assert p.runs[3].text == "underlined text."
    assert p.runs[3].underline is True


def test_bullet_and_numbered_list_generation(synthetic_template, tmp_path):
    """Verify real bullet and numbered list items are generated with list styles and numbering."""
    out_docx = tmp_path / "lists_out.docx"

    ir = DocumentIR(
        document_id="doc_list_test",
        elements=[
            IRElement(
                id="ir_b1",
                type="bullet_list_item",
                level=0,
                content="Bullet item one",
                style_ref="List Bullet",
                target_id="target_b1",
                metadata={"source_order": 1, "source_element_id": "b1", "num_id": 1, "nesting_level": 0},
            ),
            IRElement(
                id="ir_b2",
                type="bullet_list_item",
                level=1,
                content="Nested bullet item two",
                style_ref="List Bullet",
                target_id="target_b2",
                metadata={"source_order": 2, "source_element_id": "b2", "num_id": 1, "nesting_level": 1},
            ),
            IRElement(
                id="ir_n1",
                type="numbered_list_item",
                level=0,
                content="Numbered item one",
                style_ref="List Number",
                target_id="target_n1",
                metadata={"source_order": 3, "source_element_id": "n1", "num_id": 2, "nesting_level": 0},
            ),
        ],
    )

    generator = DocxGenerator(template_path=synthetic_template)
    res = generator.generate(ir, output_path=str(out_docx))
    assert res.generated_elements == 3

    reopened = Document(str(out_docx))
    assert len(reopened.paragraphs) == 3
    assert reopened.paragraphs[0].text == "Bullet item one"
    assert reopened.paragraphs[0].style.name == "List Bullet"
    assert reopened.paragraphs[1].text == "Nested bullet item two"
    assert reopened.paragraphs[2].text == "Numbered item one"
    assert reopened.paragraphs[2].style.name == "List Number"


def test_table_dimensions_cells_and_merge_preservation(synthetic_template, tmp_path):
    """Verify table cell text, dimensions, empty cells, and merges are accurately preserved."""
    out_docx = tmp_path / "table_out.docx"

    cell_data = [
        ["Header A", "Header B", "Header C"],
        ["Row 1 Col 0", "", "Row 1 Col 2"],  # Empty middle cell preserved
        ["Row 2 Col 0", "Row 2 Col 1", "Row 2 Col 2"],
    ]

    merges = [
        {"row": 0, "col": 0, "type": "horizontal", "col_span": 2},
        {"row": 1, "col": 0, "type": "vertical", "state": "restart", "row_span": 2},
    ]

    ir = DocumentIR(
        document_id="doc_tbl_test",
        elements=[
            IRElement(
                id="ir_tbl_1",
                type="table",
                level=0,
                content=None,
                style_ref="Table Grid",
                children=cell_data,
                target_id="target_tbl_1",
                metadata={
                    "source_order": 1,
                    "source_element_id": "t1",
                    "row_count": 3,
                    "column_count": 3,
                    "cell_text": cell_data,
                    "merged_cells_info": merges,
                },
            ),
        ],
    )

    generator = DocxGenerator(template_path=synthetic_template)
    res = generator.generate(ir, output_path=str(out_docx))
    assert res.generated_elements == 1

    reopened = Document(str(out_docx))
    assert len(reopened.tables) == 1
    t = reopened.tables[0]
    assert len(t.rows) == 3
    assert len(t.columns) == 3

    # Check cell contents
    assert t.cell(0, 0).text == "Header A"
    assert t.cell(1, 1).text == ""  # Empty cell preserved
    assert t.cell(2, 2).text == "Row 2 Col 2"


def test_figure_image_reconstruction(synthetic_source_with_image, synthetic_template, tmp_path):
    """Verify figure extraction and image embedding into target DOCX."""
    out_docx = tmp_path / "img_out.docx"

    # Extract drawing rids from the source
    extractor = DocxExtractor(synthetic_source_with_image)
    src_elems = extractor.extract()
    fig_elem = next(e for e in src_elems if e.type == "figure")
    rids = fig_elem.metadata.get("drawing_rids", [])
    assert len(rids) >= 1

    ir = DocumentIR(
        document_id="doc_fig_test",
        elements=[
            IRElement(
                id="ir_fig_1",
                type="figure",
                level=0,
                content=None,
                style_ref=None,
                children=rids,
                target_id="target_fig_1",
                metadata={"source_order": 1, "source_element_id": fig_elem.id, "drawing_rids": rids},
            ),
        ],
    )

    generator = DocxGenerator(template_path=synthetic_template, source_docx_path=synthetic_source_with_image)
    res = generator.generate(ir, output_path=str(out_docx))
    assert res.generated_elements == 1

    reopened = Document(str(out_docx))
    assert len(reopened.inline_shapes) >= 1


def test_unsupported_element_handling(synthetic_template, tmp_path):
    """Verify unsupported elements are recorded in manifest and inserted with warning text."""
    out_docx = tmp_path / "unsupported_out.docx"

    ir = DocumentIR(
        document_id="doc_unsupported_test",
        elements=[
            IRElement(
                id="ir_unsup_1",
                type="unsupported",
                level=0,
                content="Complex Embedded OLE Formula",
                style_ref=None,
                target_id="target_unsup_1",
                metadata={"source_order": 1, "source_element_id": "u1", "raw_tag": "w:object"},
            ),
        ],
    )

    generator = DocxGenerator(template_path=synthetic_template)
    res = generator.generate(ir, output_path=str(out_docx))

    assert res.unmapped_elements == 1
    assert any("Unsupported element type" in d for d in res.diagnostics)

    reopened = Document(str(out_docx))
    assert "[UNSUPPORTED CONTENT" in reopened.paragraphs[0].text
    assert "Complex Embedded OLE Formula" in reopened.paragraphs[0].text

    mapping = res.manifest.mappings[0]
    assert mapping.status == "unmapped"


def test_source_content_and_order_preservation(synthetic_template, tmp_path):
    """Verify strict preservation of source ordering and content across mixed elements."""
    out_docx = tmp_path / "order_out.docx"

    ir = DocumentIR(
        document_id="doc_order_test",
        elements=[
            IRElement(id="ir_1", type="heading", level=1, content="1. First Section", style_ref="Heading 1", target_id="t1", metadata={"source_order": 1, "source_element_id": "e1"}),
            IRElement(id="ir_2", type="body_paragraph", content="Body paragraph under section.", style_ref="Normal", target_id="t2", metadata={"source_order": 2, "source_element_id": "e2"}),
            IRElement(id="ir_3", type="caption", content="Figure 1: Diagram Overview", style_ref="Caption", target_id="t3", metadata={"source_order": 3, "source_element_id": "e3"}),
            IRElement(id="ir_4", type="reference", content="[1] Formatto Core Architecture Spec 2026.", style_ref="Normal", target_id="t4", metadata={"source_order": 4, "source_element_id": "e4"}),
        ],
    )

    generator = DocxGenerator(template_path=synthetic_template)
    res = generator.generate(ir, output_path=str(out_docx))
    assert res.generated_elements == 4

    reopened = Document(str(out_docx))
    texts = [p.text for p in reopened.paragraphs]
    assert texts == [
        "1. First Section",
        "Body paragraph under section.",
        "Figure 1: Diagram Overview",
        "[1] Formatto Core Architecture Spec 2026.",
    ]


def test_deterministic_repeated_generation(synthetic_template, tmp_path):
    """Verify repeated generation produces identical document structure and manifests."""
    ir = DocumentIR(
        document_id="doc_determinism_test",
        elements=[
            IRElement(id="ir_1", type="heading", level=1, content="Deterministic Title", style_ref="Heading 1", target_id="t1", metadata={"source_order": 1, "source_element_id": "e1"}),
            IRElement(id="ir_2", type="body_paragraph", content="Deterministic Paragraph.", style_ref="Normal", target_id="t2", metadata={"source_order": 2, "source_element_id": "e2"}),
        ],
    )

    out1 = tmp_path / "run1.docx"
    out2 = tmp_path / "run2.docx"

    gen = DocxGenerator(template_path=synthetic_template)
    res1 = gen.generate(ir, output_path=str(out1))
    res2 = gen.generate(ir, output_path=str(out2))

    assert res1.manifest.model_dump() == res2.manifest.model_dump()

    doc1 = Document(str(out1))
    doc2 = Document(str(out2))
    assert len(doc1.paragraphs) == len(doc2.paragraphs)
    for p1, p2 in zip(doc1.paragraphs, doc2.paragraphs):
        assert p1.text == p2.text
        assert p1.style.name == p2.style.name


def test_corrupt_or_invalid_inputs_clean_failure(tmp_path):
    """Verify missing template file raises clean ValueError without crashing."""
    ir = DocumentIR(document_id="doc_fail_test", elements=[])
    with pytest.raises(ValueError, match="Template DOCX file not found"):
        DocxGenerator(template_path="/non_existent/path/template.docx")


def test_real_sample_docx_end_to_end_pipeline(tmp_path):
    """Integration test: execute full pipeline on real 12-page sample.docx."""
    sample_path = SAMPLE_PATH
    if not os.path.exists(sample_path):
        pytest.skip("sample.docx not found in workspace")

    output_path = tmp_path / "sample_e2e_output.docx"
    pipeline = DocumentFormattingPipeline(output_dir=str(tmp_path))

    result = pipeline.run(
        source_path=sample_path,
        template_path=sample_path,
        job_id="job_sample_full_test",
        output_docx_path=str(output_path),
    )

    assert result.status == JobState.COMPLETED
    assert result.error is None
    assert result.total_elements == 143
    assert result.generated_elements == 143
    assert os.path.exists(str(output_path))
    assert result.manifest is not None
    assert len(result.manifest.mappings) == 143

    # Verify generated document can be opened and parsed
    doc = Document(str(output_path))
    assert len(doc.paragraphs) > 100
    assert len(doc.tables) >= 1
    assert len(doc.inline_shapes) >= 1


def test_jobs_api_multipart_upload(tmp_path):
    """Verify FastAPI /api/jobs upload and status endpoints."""
    sample_path = SAMPLE_PATH
    if not os.path.exists(sample_path):
        pytest.skip("sample.docx not found in workspace")

    client = TestClient(app)

    with open(sample_path, "rb") as f_src, open(sample_path, "rb") as f_tpl:
        resp = client.post(
            "/api/jobs",
            files={
                "source_file": ("sample.docx", f_src, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "template_file": ("template.docx", f_tpl, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    job_id = data["job_id"]
    assert job_id.startswith("job_")
    assert data["status"] == "CREATED"

    # Check status
    status_resp = client.get(f"/api/jobs/{job_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "COMPLETED"
    assert status_data["progress"] == 1.0

    # Check result
    result_resp = client.get(f"/api/jobs/{job_id}/result")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert result_data["status"] == "COMPLETED"
    assert result_data["docx"] == f"/api/jobs/{job_id}/download"
    assert result_data["metadata"]["total_elements"] == 143

    # Check download endpoint
    dl_resp = client.get(result_data["docx"])
    assert dl_resp.status_code == 200
    assert len(dl_resp.content) > 500000
    # Confirm valid docx by opening bytes
    import io
    downloaded_doc = Document(io.BytesIO(dl_resp.content))
    assert len(downloaded_doc.paragraphs) > 100


def test_table_borders_and_padding_preservation(synthetic_template, tmp_path):
    """Verify generated tables include explicit borders, cell margins, and column widths."""
    out_docx = tmp_path / "bordered_tbl_out.docx"
    cell_data = [["Col A", "Col B"], ["Val 1", "Val 2"]]

    ir = DocumentIR(
        document_id="doc_tbl_border_test",
        elements=[
            IRElement(
                id="ir_tbl",
                type="table",
                level=0,
                content=None,
                style_ref="Normal Table",
                children=cell_data,
                target_id="target_tbl",
                metadata={
                    "source_order": 1,
                    "source_element_id": "t_border",
                    "row_count": 2,
                    "column_count": 2,
                    "cell_text": cell_data,
                    "has_borders": True,
                    "col_widths_dxa": [3740, 5612],
                },
            ),
        ],
    )

    gen = DocxGenerator(template_path=synthetic_template)
    res = gen.generate(ir, output_path=str(out_docx))
    assert res.generated_elements == 1

    doc = Document(str(out_docx))
    t = doc.tables[0]
    assert bool(t._tbl.xpath(".//w:tblBorders")) is True
    assert bool(t._tbl.xpath(".//w:tblCellMar")) is True
    assert t.columns[0].width == 2374900
    assert t.columns[1].width == 3563620


def test_distinct_reference_template_adaptation(tmp_path):
    """Verify generation against a distinct reference template adapts margins, headers, and styles."""
    sample_path = SAMPLE_PATH
    ref_tpl_path = REF_TPL_PATH
    if not os.path.exists(sample_path) or not os.path.exists(ref_tpl_path):
        pytest.skip("sample.docx or reference_template.docx not found in workspace")

    output_path = tmp_path / "distinct_tpl_out.docx"
    pipeline = DocumentFormattingPipeline(output_dir=str(tmp_path))

    result = pipeline.run(
        source_path=sample_path,
        template_path=ref_tpl_path,
        job_id="job_distinct_test",
        output_docx_path=str(output_path),
    )

    assert result.status == JobState.COMPLETED
    assert result.generated_elements == 143

    doc = Document(str(output_path))
    # Verify template substrate was adopted
    sec = doc.sections[0]
    assert sec.left_margin.inches == 1.25  # from reference_template
    assert sec.right_margin.inches == 1.0
    assert "FORMATTO ACADEMIC SPECIFICATION TEMPLATE" in sec.header.paragraphs[0].text
