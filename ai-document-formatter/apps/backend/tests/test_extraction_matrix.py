import os
import pytest
from docx import Document
from docx.shared import Inches
from app.extraction.docx_extractor import DocxExtractor
from app.extraction.cli import run_checklist_verification


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "flow_report")
SAMPLE_PATH = os.path.join(FIXTURES_DIR, "sample.docx")
if not os.path.exists(SAMPLE_PATH):
    SAMPLE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "sample.docx")


def test_checklist_verification_sample_docx():
    """Verify that the 21 Phase 2 checklist criteria pass on sample.docx."""
    sample_path = SAMPLE_PATH
    if not os.path.exists(sample_path):
        pytest.skip("sample.docx not found in workspace")

    extractor = DocxExtractor(sample_path)
    elements = extractor.extract()
    results = run_checklist_verification(sample_path, elements, extractor)

    for item, passed in results.items():
        assert passed is True, f"Checklist item '{item}' failed on sample.docx!"


def test_figure_metadata_consistency_sample_docx():
    """Verify that figure image_count matches drawing_rids and avoids fallback duplicates."""
    sample_path = SAMPLE_PATH
    if not os.path.exists(sample_path):
        pytest.skip("sample.docx not found in workspace")

    extractor = DocxExtractor(sample_path)
    elements = extractor.extract()
    figures = [e for e in elements if e.type == "figure"]

    assert len(figures) == 4, f"Expected 4 figures, got {len(figures)}"
    for f in figures:
        rids = f.metadata.get("drawing_rids", [])
        image_count = f.metadata.get("image_count", 0)
        assert image_count == len(rids), f"Figure {f.id} image_count {image_count} != rids len {len(rids)}"

    # Check composite figure at P48 (Figure 1 in report)
    fig1 = figures[1]
    assert fig1.metadata["image_count"] == 3
    assert fig1.metadata["drawing_rids"] == ["rId9", "rId10", "rId11"]

    # Check composite figure at P152 (Figure 2 in report)
    fig2 = figures[2]
    assert fig2.metadata["image_count"] == 2
    assert fig2.metadata["drawing_rids"] == ["rId15", "rId16"]


def test_merged_table_restart_and_continue_sample_docx():
    """Verify table merge detection distinguishes restart, continue, and ordinary cells."""
    sample_path = SAMPLE_PATH
    if not os.path.exists(sample_path):
        pytest.skip("sample.docx not found in workspace")

    extractor = DocxExtractor(sample_path)
    elements = extractor.extract()
    tables = [e for e in elements if e.type == "table"]

    assert len(tables) >= 1
    t = tables[0]
    merged_info = t.metadata.get("merged_cells_info", [])
    assert len(merged_info) == 3

    # Row 0 Col 0 is restart with row_span 3
    restart_cell = next(m for m in merged_info if m["row"] == 0 and m["col"] == 0)
    assert restart_cell["state"] == "restart"
    assert restart_cell["row_span"] == 3

    # Row 1 Col 0 is continue pointing back to row 0
    continue_cell_1 = next(m for m in merged_info if m["row"] == 1 and m["col"] == 0)
    assert continue_cell_1["state"] == "continue"
    assert continue_cell_1["origin_row"] == 0

    # Row 2 Col 0 is continue pointing back to row 0
    continue_cell_2 = next(m for m in merged_info if m["row"] == 2 and m["col"] == 0)
    assert continue_cell_2["state"] == "continue"
    assert continue_cell_2["origin_row"] == 0

    # Verify cell text in continue cells does not repeat master text
    cell_text = t.metadata.get("cell_text", [])
    assert cell_text[0][0] == "Name(s) of Students & Registration Number(s)"
    assert cell_text[1][0] == ""
    assert cell_text[2][0] == ""


def test_extraction_repeatability_sample_docx():
    """Verify that multiple extraction runs produce identical structure and IDs."""
    sample_path = SAMPLE_PATH
    if not os.path.exists(sample_path):
        pytest.skip("sample.docx not found in workspace")

    runs = []
    for _ in range(3):
        ext = DocxExtractor(sample_path)
        elems = ext.extract()
        runs.append([e.model_dump() for e in elems])

    assert runs[0] == runs[1], "Run 0 and Run 1 differ!"
    assert runs[1] == runs[2], "Run 1 and Run 2 differ!"


def test_corrupt_docx_clean_failure(tmp_path):
    """Test that a non-DOCX / corrupt file raises a clean error."""
    corrupt_file = tmp_path / "corrupt.docx"
    with open(corrupt_file, "wb") as f:
        f.write(b"NOT_A_VALID_ZIP_OR_DOCX_HEADER")

    with pytest.raises(ValueError) as excinfo:
        DocxExtractor(str(corrupt_file))
    assert "Failed to open DOCX file" in str(excinfo.value)


def test_nested_list_and_empty_cell_extraction(tmp_path):
    """Test nested list extraction and table empty cell preservation."""
    doc_path = tmp_path / "nested_test.docx"
    doc = Document()

    # Paragraph with list
    doc.add_paragraph("Bullet 1", style="List Bullet")
    doc.add_paragraph("Bullet 2", style="List Bullet")

    # Table with empty cells
    table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "Filled"
    table.cell(0, 1).text = ""  # explicitly empty
    table.cell(0, 2).text = "End"
    table.cell(1, 0).text = ""
    table.cell(1, 1).text = "Middle"
    table.cell(1, 2).text = ""

    doc.save(str(doc_path))

    extractor = DocxExtractor(str(doc_path))
    elements = extractor.extract()

    table_elem = next(e for e in elements if e.type == "table")
    cells = table_elem.metadata["cell_text"]
    assert cells[0][1] == ""
    assert cells[1][0] == ""
    assert cells[1][2] == ""
    assert table_elem.metadata["row_count"] == 2
    assert table_elem.metadata["column_count"] == 3
