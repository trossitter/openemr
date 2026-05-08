"""Pydantic schemas for extracted clinical documents (Week 2).

BBox and Citation carry full provenance metadata so every clinical claim is
traceable to a specific pixel region in a specific rasterized page.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class BBox(BaseModel):
    """Bounding box for a citation region, with explicit coordinate space.

    Coordinates returned by Claude Vision are in image_px_300dpi space (top-left
    origin, integer pixels) because we send rasterized page images at 300 DPI.
    page_width and page_height record the canvas size so transforms are
    deterministic without re-opening the source document.
    """
    x0: float
    y0: float
    x1: float
    y1: float
    page: int                                           # 0-based page index
    coordinate_space: str = "image_px_300dpi"          # declared space
    page_width: Optional[int] = None                   # image width in that space
    page_height: Optional[int] = None                  # image height in that space


class Citation(BaseModel):
    """Machine-readable provenance record for a single extracted clinical claim.

    Minimum required fields match the Week 2 citation contract. Extended fields
    (transform_chain through content_hash) satisfy the visual audit spec without
    breaking existing schema validation — all are Optional with safe defaults.
    """
    # --- Core citation contract (required) ---
    source_type: str            # "pdf" | "ocr" | "embedded_text" | "hl7" | "fhir" | "guideline"
    source_id: str              # document UUID or SHA-256 prefix
    page_or_section: str        # human-readable page ref or section name
    field_or_chunk_id: str      # stable extraction identifier (e.g. "LDL-C_p1")
    quote_or_value: str         # exact extracted text or normalized value

    # --- Visual provenance extension ---
    bbox: Optional[BBox] = None

    # --- Coordinate + extraction lineage ---
    transform_chain: list[str] = Field(default_factory=list)
    ocr_confidence: Optional[float] = None       # 0.0–1.0; None when not applicable
    parser: Optional[str] = None                 # "claude_vision" | "tesseract" | etc.
    evidence_type: Optional[str] = None          # "native_pdf_text" | "ocr" | "table" | "handwriting"
    created_at: Optional[str] = None             # ISO 8601 timestamp
    content_hash: Optional[str] = None           # SHA-256 of quote_or_value

    @model_validator(mode="after")
    def _fill_derived(self) -> "Citation":
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if self.content_hash is None and self.quote_or_value:
            self.content_hash = hashlib.sha256(
                self.quote_or_value.encode()
            ).hexdigest()
        return self


class LabResult(BaseModel):
    test_name: str
    value: str
    unit: str
    reference_range: str
    collection_date: str        # YYYY-MM-DD
    abnormal_flag: bool
    source_citation: Citation


class Demographics(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None  # YYYY-MM-DD
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


class PertinentLab(BaseModel):
    """Inline lab reference within a fax/referral document."""
    test_name: str
    value: str
    unit: str = ""
    collection_date: Optional[str] = None
    abnormal_flag: bool = False


class FaxPacket(BaseModel):
    """Structured extraction from a multi-page TIFF fax packet.

    Fax packets contain mixed clinical content (cover sheets, referral letters,
    clinical notes, lab reports). This schema captures the common superset.
    All Optional fields may be absent depending on fax content.
    """
    detected_type: str              # "referral_letter" | "lab_report" | "clinical_note" | "mixed"
    patient_name: Optional[str] = None
    patient_dob: Optional[str] = None   # YYYY-MM-DD
    patient_mrn: Optional[str] = None
    referring_provider: Optional[str] = None
    referring_facility: Optional[str] = None
    receiving_provider: Optional[str] = None
    receiving_facility: Optional[str] = None
    fax_date: Optional[str] = None      # YYYY-MM-DD
    reason_for_referral: Optional[str] = None
    history_of_present_illness: Optional[str] = None
    diagnoses: list[str] = Field(default_factory=list)      # may include ICD codes
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    pertinent_labs: list[PertinentLab] = Field(default_factory=list)
    specific_question: Optional[str] = None
    clinical_notes: Optional[str] = None   # free-text from pages with no structure
    source_citation: Citation
    page_count: int
