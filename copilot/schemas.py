"""Pydantic schemas for extracted clinical documents (Week 2)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class BBox(BaseModel):
    """Bounding-box coordinates for a citation region inside a PDF page."""
    x0: float
    y0: float
    x1: float
    y1: float
    page: int


class Citation(BaseModel):
    source_type: str
    source_id: str
    page_or_section: str
    field_or_chunk_id: str
    quote_or_value: str
    bbox: Optional[BBox] = None


class LabResult(BaseModel):
    test_name: str
    value: str
    unit: str
    reference_range: str
    collection_date: str  # YYYY-MM-DD
    abnormal_flag: bool
    source_citation: Citation


class Demographics(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None   # YYYY-MM-DD
    sex: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class IntakeForm(BaseModel):
    demographics: Demographics
    chief_concern: str
    medications: list[str]
    allergies: list[str]
    family_history: list[str]
    source_citation: Citation
