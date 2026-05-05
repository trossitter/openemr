"""Unit tests for copilot schema validation."""
import pytest
from pydantic import ValidationError

from schemas import BBox, Citation, Demographics, IntakeForm, LabResult


def _citation(**overrides) -> dict:
    base = dict(
        source_type="pdf",
        source_id="doc-001",
        page_or_section="page 1",
        field_or_chunk_id="field-0",
        quote_or_value="Glucose: 95 mg/dL",
    )
    base.update(overrides)
    return base


def test_lab_result_valid():
    lab = LabResult(
        test_name="Glucose",
        value="95",
        unit="mg/dL",
        reference_range="70-99 mg/dL",
        collection_date="2024-06-01",
        abnormal_flag=False,
        source_citation=Citation(**_citation()),
    )
    assert lab.test_name == "Glucose"
    assert lab.abnormal_flag is False
    assert lab.source_citation.bbox is None


def test_citation_bbox_optional():
    without_bbox = Citation(**_citation())
    assert without_bbox.bbox is None

    with_bbox = Citation(
        **_citation(quote_or_value="HbA1c: 7.2%"),
        bbox=BBox(x0=10.5, y0=22.0, x1=180.0, y1=38.5, page=2),
    )
    assert with_bbox.bbox is not None
    assert with_bbox.bbox.page == 2


def test_intake_form_missing_required_raises():
    with pytest.raises(ValidationError) as exc_info:
        IntakeForm(
            demographics=Demographics(name="John Doe"),
            # chief_concern intentionally omitted
            medications=["Metformin 500mg"],
            allergies=["Penicillin"],
            family_history=["T2DM"],
            source_citation=Citation(**_citation()),
        )
    assert "chief_concern" in str(exc_info.value)
