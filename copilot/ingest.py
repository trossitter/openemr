"""Document ingestion: extraction → schema validation → FHIR write → overlay render.

attach_and_extract(patient_id, file_path, doc_type) is the single entry point.

Supported doc_types and their pipelines:
  lab_pdf      — PDF lab report    → rasterize → Claude Vision → LabResult[]
  intake_form  — PDF intake form   → rasterize → Claude Vision → IntakeForm
  fax_packet   — multi-page TIFF   → rasterize → Claude Vision → FaxPacket
  hl7_oru      — HL7v2 ORU-R01    → deterministic parse       → LabResult[]
  hl7_adt      — HL7v2 ADT-A08    → deterministic parse       → IntakeForm

Coordinate invariant: all bbox values returned by Claude are in image_px_{dpi}dpi
space anchored to the rasterized image that was sent. HL7 extractions carry no
bbox (text has no spatial position).

PHI never reaches the vector DB or log files — raw values stay in FHIR only.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union

import anthropic
import httpx

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE
from coords import PageGeometry, TransformChain
from hl7 import detect_message_type, parse_adt_a08, parse_oru_r01
from observability import log_extraction
from render import OverlayResult, page_to_b64, persist_overlay, render_document_overlay, rasterize_pdf, rasterize_tiff
from schemas import Citation, Demographics, FaxPacket, IntakeForm, LabResult, PertinentLab

OPENEMR_BASE_URL = os.environ.get("OPENEMR_BASE_URL", "http://openemr:80")
OPENEMR_CLIENT_ID = os.environ.get("OPENEMR_CLIENT_ID", "")
OPENEMR_CLIENT_SECRET = os.environ.get("OPENEMR_CLIENT_SECRET", "")

# ---------------------------------------------------------------------------
# Extraction result — returned by attach_and_extract
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """Full output of attach_and_extract: extracted data + visual provenance."""
    doc_id: str
    doc_type: str
    data: Union[list[LabResult], IntakeForm, FaxPacket]
    overlay_metadata: dict          # OverlayMetadata.to_dict() or {} for HL7
    preview_b64: Optional[str]      # base64 PNG of first annotated page; None for HL7
    page_count: int

    def data_as_dicts(self) -> Union[list[dict], dict]:
        if isinstance(self.data, list):
            return [r.model_dump() for r in self.data]
        return self.data.model_dump()


# ---------------------------------------------------------------------------
# Extraction prompts — declare coordinate space explicitly
# ---------------------------------------------------------------------------

_COORD_PREAMBLE = (
    "Bounding box coordinates (x0, y0, x1, y1) MUST be integer pixel coordinates "
    "in the page image you were given. Coordinate origin is top-left. "
    "For a multi-page document where several images are provided, set bbox.page "
    "to the 0-based index of the image the coordinates refer to (first image = 0). "
    "bbox is required for every field — do your best to locate it."
)

ALL_DOC_TYPES = frozenset({"lab_pdf", "intake_form", "fax_packet", "hl7_oru", "hl7_adt"})
VISION_DOC_TYPES = frozenset({"lab_pdf", "intake_form", "fax_packet"})
HL7_DOC_TYPES = frozenset({"hl7_oru", "hl7_adt"})

_EXTRACT_PROMPTS: dict[str, str] = {
    "lab_pdf": (
        "Extract every lab result from this document. "
        "Return a JSON array. Each element must have exactly these keys: "
        "test_name (string), value (string), unit (string), "
        "reference_range (string), collection_date (YYYY-MM-DD string), "
        "abnormal_flag (boolean), "
        "source_citation (object with keys: source_type [use 'pdf'], source_id, "
        "page_or_section [e.g. 'page 1'], "
        "field_or_chunk_id [short stable ID e.g. 'LDL-C_p1'], "
        "quote_or_value [exact extracted text], "
        "bbox [object with x0, y0, x1, y1 as integers, page as 0-based integer], "
        "ocr_confidence [float 0-1, your confidence in the extraction], "
        "parser ['claude_vision'], "
        "evidence_type ['native_pdf_text' or 'ocr' or 'table']). "
        f"{_COORD_PREAMBLE} "
        "Return ONLY the JSON array, no prose or markdown."
    ),
    "intake_form": (
        "Extract the intake form data from this document. "
        "Return a single JSON object with exactly these keys: "
        "demographics (object with optional keys: name, dob [YYYY-MM-DD], sex, phone, address), "
        "chief_concern (string), "
        "medications (array of strings), "
        "allergies (array of strings), "
        "family_history (array of strings), "
        "source_citation (object with keys: source_type [use 'pdf'], source_id, "
        "page_or_section [e.g. 'page 1'], "
        "field_or_chunk_id ['intake_form_p1'], "
        "quote_or_value [patient's chief concern verbatim], "
        "bbox [object with x0, y0, x1, y1 as integers, page as 0-based integer, "
        "covering the chief concern region], "
        "ocr_confidence [float 0-1], "
        "parser ['claude_vision'], "
        "evidence_type ['native_pdf_text' or 'ocr' or 'handwriting']). "
        f"{_COORD_PREAMBLE} "
        "Return ONLY the JSON object, no prose or markdown."
    ),
    "fax_packet": (
        "This is a multi-page fax packet. Examine all pages carefully. "
        "Return a single JSON object with exactly these keys: "
        "detected_type (string: 'referral_letter', 'lab_report', 'clinical_note', or 'mixed'), "
        "patient_name (string or null), "
        "patient_dob (YYYY-MM-DD string or null), "
        "patient_mrn (string or null), "
        "referring_provider (string or null), "
        "referring_facility (string or null), "
        "receiving_provider (string or null), "
        "receiving_facility (string or null), "
        "fax_date (YYYY-MM-DD string or null), "
        "reason_for_referral (string or null), "
        "history_of_present_illness (string or null — verbatim HPI text), "
        "diagnoses (array of strings — include ICD codes if present), "
        "medications (array of strings), "
        "allergies (array of strings), "
        "pertinent_labs (array of objects with keys: test_name, value, unit, collection_date [YYYY-MM-DD or null], abnormal_flag [boolean]), "
        "specific_question (string or null — the clinical question or action requested), "
        "clinical_notes (string or null — any free text not captured above), "
        "source_citation (object with keys: source_type ['pdf'], source_id, "
        "page_or_section ['page 1'], field_or_chunk_id ['fax_cover'], "
        "quote_or_value [patient name or chief identifying text], "
        "bbox [object with x0, y0, x1, y1 as integers, page as 0-based integer — "
        "point to the patient name or header on the cover page], "
        "ocr_confidence [float 0-1], parser ['claude_vision'], "
        "evidence_type ['native_pdf_text' or 'ocr']), "
        "page_count (integer — total pages you examined). "
        f"{_COORD_PREAMBLE} "
        "Return ONLY the JSON object, no prose or markdown."
    ),
}

_MEDIA_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _media_type(path: Path) -> str:
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


# ---------------------------------------------------------------------------
# Rasterize + extract
# ---------------------------------------------------------------------------

_TIFF_SUFFIXES = frozenset({".tif", ".tiff"})


def _rasterize_path(path: Path) -> tuple[list, list[PageGeometry], int]:
    """Return (pil_images, geometries, native_dpi).

    Routing:
      .pdf                  → rasterize_pdf (PyMuPDF, 300 DPI)
      .tif / .tiff          → rasterize_tiff (PIL, DPI-aware, resample to 300)
      .jpg/.png/.webp/etc.  → single-page PIL load
    """
    from PIL import Image as PILImage

    ext = path.suffix.lower()

    if ext == ".pdf":
        images, geoms = rasterize_pdf(path)
        return images, geoms, 300

    if ext in _TIFF_SUFFIXES:
        images, geoms, native_dpi = rasterize_tiff(path)
        return images, geoms, native_dpi

    # Single raster image — treat as a one-page document
    img = PILImage.open(path).convert("RGB")
    dpi_info = img.info.get("dpi", (72, 72))
    dpi = int(dpi_info[0]) if isinstance(dpi_info, (tuple, list)) else 72
    geom = PageGeometry(
        page_index=0,
        pdf_width_pts=img.width * 72.0 / max(dpi, 72),
        pdf_height_pts=img.height * 72.0 / max(dpi, 72),
        image_width_px=img.width,
        image_height_px=img.height,
        render_dpi=dpi,
    )
    return [img], [geom], dpi


def _images_to_content_blocks(images: list) -> list[dict]:
    """Convert PIL Images to Claude API image content blocks (base64 PNG)."""
    blocks: list[dict] = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.standard_b64encode(buf.getvalue()).decode()
        blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64},
        })
    return blocks


def _call_claude_vision(images: list, doc_type: str) -> str:
    """Send rasterized page images to Claude and return the raw text reply."""
    assert doc_type in VISION_DOC_TYPES, f"HL7 types must not call Claude Vision: {doc_type}"
    content: list[dict] = _images_to_content_blocks(images)
    content.append({"type": "text", "text": _EXTRACT_PROMPTS[doc_type]})

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )
    return msg.content[0].text


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def _inject_provenance(citation_dict: dict, geom_map: dict[int, PageGeometry]) -> dict:
    """Add transform_chain and page geometry to a citation dict returned by Claude."""
    bbox = citation_dict.get("bbox")
    if not bbox or not isinstance(bbox, dict):
        return citation_dict

    page_idx = bbox.get("page", 0)
    geom = geom_map.get(page_idx)

    # Ensure coordinate_space is declared
    citation_dict["bbox"]["coordinate_space"] = "image_px_300dpi"
    if geom:
        citation_dict["bbox"]["page_width"] = geom.image_width_px
        citation_dict["bbox"]["page_height"] = geom.image_height_px

    # Build transform chain if not already present
    if not citation_dict.get("transform_chain"):
        tc = TransformChain.for_extraction(
            geom or PageGeometry(page_idx, 0, 0, 0, 0),
            parser=citation_dict.get("parser", "claude_vision"),
        )
        citation_dict["transform_chain"] = tc.to_list()

    return citation_dict


def _cluster_words_into_rows(words: list, y_tolerance: float = 4.0) -> list[list]:
    """Group PyMuPDF word tuples into horizontal rows by y-midpoint proximity.

    Each word tuple: (x0, y0, x1, y1, text, block_no, line_no, word_no).
    Words whose y-midpoints are within y_tolerance PDF points of an existing
    cluster are added to it; otherwise a new cluster is started.
    Clusters are returned in top-to-bottom order.
    """
    clusters: list[list] = []
    for w in words:
        wy_mid = (w[1] + w[3]) / 2
        placed = False
        for cluster in clusters:
            cy_mid = sum((c[1] + c[3]) / 2 for c in cluster) / len(cluster)
            if abs(wy_mid - cy_mid) <= y_tolerance:
                cluster.append(w)
                placed = True
                break
        if not placed:
            clusters.append([w])
    clusters.sort(key=lambda c: min(w[1] for w in c))
    return clusters


def _find_row_by_name_and_value(
    clusters: list[list],
    test_name: str,
    value: str,
) -> "Optional[fitz.Rect]":
    """Find the value-cell bbox in the row that contains both test_name and value.

    Matching rules:
    - value must appear as a STANDALONE word token in the row (not a substring
      of another number — PyMuPDF word-tokenises by whitespace so this is exact).
    - Every significant word from test_name must appear somewhere in the row text
      (punctuation-stripped, case-insensitive).

    Returns the fitz.Rect of the value word, or None if no unambiguous row found.
    """
    import fitz
    import re

    value_norm = value.strip().lower()

    # Significant name tokens: drop single chars, strip punctuation
    def _tok(s: str) -> str:
        return re.sub(r"[^\w/.-]", "", s).lower()

    name_tokens = [_tok(w) for w in test_name.split() if len(w) > 1]

    for cluster in clusters:
        word_texts_lower = [w[4].strip().lower() for w in cluster]

        # 1. Value must be a standalone word in this row
        if value_norm not in word_texts_lower:
            continue

        # 2. All significant name tokens must appear in the row text
        row_text = " ".join(_tok(w[4]) for w in cluster)
        if not all(nt in row_text for nt in name_tokens):
            continue

        # Matched — return the value word's exact bbox
        for w in cluster:
            if w[4].strip().lower() == value_norm:
                return fitz.Rect(w[0], w[1], w[2], w[3])

    return None


def _refine_bboxes_via_native_text(
    path: Path,
    citations: list[Citation],
    geom_map: dict[int, PageGeometry],
    field_names: Optional[list[str]] = None,
    field_values: Optional[list[str]] = None,
) -> list[Citation]:
    """Replace Claude's estimated bboxes with PyMuPDF native text positions.

    For PDFs with a native text layer, uses word-level row clustering:
    each citation is matched to the row whose text contains BOTH the
    field name (test name, section label, etc.) AND the extracted value
    as a standalone word. This eliminates false positives where the same
    numeric value appears in reference ranges, dates, or other metadata.

    field_names, when supplied, is parallel to citations and provides the
    human-readable label to anchor the row search (e.g. "Total Cholesterol").

    field_values, when supplied, is parallel to citations and provides the
    standalone result value for the word-level match (e.g. "241"). This must
    be the actual extracted value, not quote_or_value which Claude often fills
    with the full row text.

    Falls back to Claude's estimate for non-PDF files or unmatched rows.
    """
    import fitz

    if path.suffix.lower() != ".pdf":
        return citations

    doc = fitz.open(str(path))
    refined: list[Citation] = []

    try:
        # Pre-cluster words per page so we don't re-extract on every citation
        page_clusters: dict[int, list[list]] = {}

        for i, cit in enumerate(citations):
            page_idx = cit.bbox.page if cit.bbox else 0
            geom = geom_map.get(page_idx)

            if geom is None or page_idx >= len(doc):
                refined.append(cit)
                continue

            if page_idx not in page_clusters:
                page = doc[page_idx]
                page_clusters[page_idx] = _cluster_words_into_rows(
                    page.get_text("words")
                )

            clusters = page_clusters[page_idx]
            scale = geom.scale

            field_name = (field_names[i] if field_names and i < len(field_names) else "") or ""
            # Use the explicit field_value (e.g. LabResult.value = "241") for the
            # word-level match. Claude often puts the full row text in quote_or_value,
            # which will never equal a single word token.
            value = (field_values[i] if field_values and i < len(field_values) else None) or cit.quote_or_value.strip()

            matched_rect = _find_row_by_name_and_value(clusters, field_name, value)

            # Fallback: if row search fails, try bare value search
            if matched_rect is None and value:
                hits = doc[page_idx].search_for(value)
                if hits:
                    matched_rect = hits[0]

            if matched_rect is None:
                refined.append(cit)
                continue

            from schemas import BBox
            new_bbox = BBox(
                x0=matched_rect.x0 * scale,
                y0=matched_rect.y0 * scale,
                x1=matched_rect.x1 * scale,
                y1=matched_rect.y1 * scale,
                page=page_idx,
                coordinate_space="image_px_300dpi",
                page_width=geom.image_width_px,
                page_height=geom.image_height_px,
            )
            refined.append(cit.model_copy(update={
                "bbox": new_bbox,
                "transform_chain": list(cit.transform_chain) + ["pymupdf_row_cluster_search"],
                "evidence_type": "native_pdf_text",
            }))

    finally:
        doc.close()

    return refined


# ---------------------------------------------------------------------------
# FHIR write helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _get_openemr_token() -> str:
    resp = httpx.post(
        f"{OPENEMR_BASE_URL}/oauth2/default/token",
        data={
            "grant_type": "client_credentials",
            "client_id": OPENEMR_CLIENT_ID,
            "client_secret": OPENEMR_CLIENT_SECRET,
            "scope": "system/Observation.write system/Patient.write",
        },
        timeout=10,
        verify=False,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _fhir_headers(token: str, content_type: str = "application/fhir+json") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": content_type}


def _write_observation(patient_id: int, lab: LabResult, token: str) -> None:
    resource = {
        "resourceType": "Observation",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                    }
                ]
            }
        ],
        "code": {"text": lab.test_name},
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": lab.collection_date,
        "valueQuantity": {"value": lab.value, "unit": lab.unit},
        "referenceRange": [{"text": lab.reference_range}],
    }
    if lab.abnormal_flag:
        resource["interpretation"] = [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                        "code": "A",
                        "display": "Abnormal",
                    }
                ]
            }
        ]
    resp = httpx.post(
        f"{OPENEMR_BASE_URL}/apis/default/fhir/Observation",
        json=resource,
        headers=_fhir_headers(token),
        timeout=15,
        verify=False,
    )
    resp.raise_for_status()


def _write_patient_update(patient_id: int, intake: IntakeForm, token: str) -> None:
    d = intake.demographics
    ops: list[dict] = []
    if d.name:
        parts = d.name.split(" ", 1)
        ops.append(
            {
                "op": "add",
                "path": "/name",
                "value": [
                    {
                        "use": "official",
                        "family": parts[1] if len(parts) > 1 else "",
                        "given": [parts[0]],
                    }
                ],
            }
        )
    if d.dob:
        ops.append({"op": "add", "path": "/birthDate", "value": d.dob})
    if d.sex:
        ops.append({"op": "add", "path": "/gender", "value": d.sex.lower()})
    if not ops:
        return
    resp = httpx.patch(
        f"{OPENEMR_BASE_URL}/apis/default/fhir/Patient/{patient_id}",
        json=ops,
        headers=_fhir_headers(token, "application/json-patch+json"),
        timeout=15,
        verify=False,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def attach_and_extract(
    patient_id: int,
    file_path: str,
    doc_type: Literal["lab_pdf", "intake_form"],
) -> ExtractionResult:
    """Extract structured data from a clinical document, write to FHIR, render overlay.

    Returns an ExtractionResult containing:
      - validated Pydantic objects (.data)
      - visual overlay metadata (.overlay_metadata)
      - base64 preview of the first annotated page (.preview_b64)

    Raises:
        ValueError: unknown doc_type
        FileNotFoundError: file_path does not exist
        pydantic.ValidationError: Claude's response doesn't match the schema
        httpx.HTTPStatusError: FHIR write failed
    """
    if doc_type not in ALL_DOC_TYPES:
        raise ValueError(
            f"doc_type must be one of {sorted(ALL_DOC_TYPES)}, got {doc_type!r}"
        )

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_bytes = path.read_bytes()
    trace_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    # -----------------------------------------------------------------------
    # HL7v2 path — deterministic parse, no Claude, no overlay
    # -----------------------------------------------------------------------
    if doc_type in HL7_DOC_TYPES:
        return _extract_hl7(
            patient_id, path, file_bytes, doc_type, trace_id, t0
        )

    # -----------------------------------------------------------------------
    # Vision path — rasterize → Claude Vision → overlay
    # -----------------------------------------------------------------------

    # Step 1 — rasterize (PDF → 300 DPI, TIFF → native DPI → resample, image → as-is)
    images, geometries, native_dpi = _rasterize_path(path)
    geom_map = {g.page_index: g for g in geometries}

    # Step 2 — extract via Claude Vision (image blocks anchored to rasterized pages)
    raw = _call_claude_vision(images, doc_type)
    payload = json.loads(_strip_fences(raw))

    # Step 3 — inject provenance, validate schema
    data: Union[list[LabResult], IntakeForm, FaxPacket]
    citations: list[Citation]

    if doc_type == "lab_pdf":
        if isinstance(payload, list):
            for item in payload:
                if "source_citation" in item:
                    item["source_citation"] = _inject_provenance(
                        item["source_citation"], geom_map
                    )
        results = [LabResult.model_validate(item) for item in payload]
        citations = [r.source_citation for r in results]
        data = results

    elif doc_type == "fax_packet":
        if "source_citation" in payload:
            payload["source_citation"] = _inject_provenance(
                payload["source_citation"], geom_map
            )
        # Validate nested pertinent_labs entries
        if "pertinent_labs" in payload and isinstance(payload["pertinent_labs"], list):
            payload["pertinent_labs"] = [
                PertinentLab.model_validate(lab).model_dump()
                for lab in payload["pertinent_labs"]
            ]
        payload.setdefault("page_count", len(images))
        fax = FaxPacket.model_validate(payload)
        citations = [fax.source_citation]
        data = fax

    else:  # intake_form
        if "source_citation" in payload:
            payload["source_citation"] = _inject_provenance(
                payload["source_citation"], geom_map
            )
        intake = IntakeForm.model_validate(payload)
        citations = [intake.source_citation]
        data = intake

    # Step 3b — refine bboxes via PyMuPDF row-cluster search (PDF only).
    # For each lab result, rows are identified by the co-presence of the test
    # name AND the value as a standalone word — eliminating false positives from
    # integer values that appear in reference ranges, dates, or other columns.
    if doc_type == "lab_pdf" and isinstance(data, list):
        field_names: Optional[list[str]] = [r.test_name for r in data]
        field_values: Optional[list[str]] = [r.value for r in data]
    else:
        field_names = None
        field_values = None

    citations = _refine_bboxes_via_native_text(path, citations, geom_map, field_names, field_values)

    # Write refined citations back into the schema objects so the API response
    # also carries the corrected coordinates.
    if doc_type == "lab_pdf" and isinstance(data, list):
        data = [
            r.model_copy(update={"source_citation": c})
            for r, c in zip(data, citations)
        ]
    elif doc_type in ("intake_form", "fax_packet") and not isinstance(data, list):
        data = data.model_copy(update={"source_citation": citations[0]})

    # Step 4 — FHIR write (skipped in DEMO_MODE and for fax_packet)
    if not DEMO_MODE and doc_type != "fax_packet":
        token = _get_openemr_token()
        if doc_type == "lab_pdf":
            for lab in results:  # type: ignore[possibly-undefined]
                _write_observation(patient_id, lab, token)
        elif doc_type == "intake_form":
            _write_patient_update(patient_id, intake, token)  # type: ignore[possibly-undefined]

    # Step 5 — render overlay (annotated PNG per page + machine-readable metadata)
    overlay_result: OverlayResult = render_document_overlay(path, file_bytes, citations)
    persist_overlay(overlay_result)

    preview_b64: Optional[str] = None
    if overlay_result.annotated_pages:
        preview_b64 = page_to_b64(overlay_result.annotated_pages[0])

    # Step 6 — PHI-safe extraction log
    bbox_count = sum(1 for c in citations if c.bbox is not None)
    log_extraction(
        trace_id=trace_id,
        doc_id=overlay_result.doc_id,
        doc_type=doc_type,
        page_count=len(images),
        field_count=len(citations),
        bbox_count=bbox_count,
        duration_ms=(time.perf_counter() - t0) * 1000,
    )

    return ExtractionResult(
        doc_id=overlay_result.doc_id,
        doc_type=doc_type,
        data=data,
        overlay_metadata=overlay_result.overlay_metadata.to_dict(),
        preview_b64=preview_b64,
        page_count=len(images),
    )


def _extract_hl7(
    patient_id: int,
    path: Path,
    file_bytes: bytes,
    doc_type: str,
    trace_id: str,
    t0: float,
) -> ExtractionResult:
    """HL7v2 extraction — deterministic parse, no Claude, no visual overlay."""
    import hashlib
    raw_text = file_bytes.decode("utf-8", errors="replace")
    source_filename = path.name
    doc_id = hashlib.sha256(file_bytes).hexdigest()[:16]

    if doc_type == "hl7_oru":
        records = parse_oru_r01(raw_text, source_filename)
        data: Union[list[LabResult], IntakeForm] = records
        field_count = len(records)
        # FHIR write
        if not DEMO_MODE and records:
            token = _get_openemr_token()
            for lab in records:
                _write_observation(patient_id, lab, token)
    else:  # hl7_adt
        intake = parse_adt_a08(raw_text, source_filename)
        data = intake
        field_count = 1
        if not DEMO_MODE:
            token = _get_openemr_token()
            _write_patient_update(patient_id, intake, token)

    log_extraction(
        trace_id=trace_id,
        doc_id=doc_id,
        doc_type=doc_type,
        page_count=1,
        field_count=field_count,
        bbox_count=0,       # HL7v2 has no spatial position
        duration_ms=(time.perf_counter() - t0) * 1000,
    )

    return ExtractionResult(
        doc_id=doc_id,
        doc_type=doc_type,
        data=data,
        overlay_metadata={},    # no overlay for text-only HL7
        preview_b64=None,
        page_count=1,
    )
