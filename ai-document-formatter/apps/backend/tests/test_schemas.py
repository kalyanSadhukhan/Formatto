import pytest
from pydantic import ValidationError
from app.domain.schemas.data_contracts import JobState, SourceElement, TemplateConstraint, ApiError

def test_source_element_valid():
    elem = SourceElement(id="1", type="paragraph", source_order=1, confidence=0.9)
    assert elem.id == "1"
    assert elem.type == "paragraph"

def test_source_element_invalid_type():
    with pytest.raises(ValidationError):
        SourceElement(id="1", type="invalid_type", source_order=1, confidence=0.9)

def test_template_constraint_valid():
    tc = TemplateConstraint(id="1", category="page", target="document", property="margins", expected_value="1in", provenance="EXTRACTED", confidence=1.0, enforceable=True)
    assert tc.provenance == "EXTRACTED"

def test_template_constraint_invalid_provenance():
    with pytest.raises(ValidationError):
         TemplateConstraint(id="1", category="page", target="document", property="margins", expected_value="1in", provenance="MADE_UP", confidence=1.0, enforceable=True)

def test_api_error_schema():
    err = ApiError(error_code="INVALID_UPLOAD", message="File too large", stage="upload", details={"max": 10})
    assert err.error_code == "INVALID_UPLOAD"
