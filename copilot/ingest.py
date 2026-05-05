"""Document ingestion: vision extraction → schema validation → FHIR write.

attach_and_extract(patient_id, file_path, doc_type) is the single entry point.
PHI never leaves the FHIR layer — no vector DB writes.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Literal, Union

import anthropic
import httpx

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE
from schemas import Citation, Demographics, IntakeForm, LabResult

OPENEMR_BASE_URL = os.environ.get("OPENEMR_BASE_URL", "http://openemr:80")
OPENEMR_CLIENT_ID = os.environ.get("OPENEMR_CLIENT_ID", "")
OPENEMR_CLIENT_SECRET = os.environ.get("OPENEMR_CLIENT_SECRET", "")

_EXTRACT_PROMPTS: dict[str, str] = {
    "lab_pdf": (
        "Extract every lab result from this document. "
        "Return a JSON array. Each element must have exactly these keys: "
        "test_name (string), value (string), unit (string), "
        "reference_range (string), collection_date (YYYY-MM-DD string), "
        "abnormal_flag (boolean), "
        "source_citation (object: source_type, source_id, page_or_section, "
        "field_or_chunk_id, quote_or_value; plus optional bbox with x0/y0/x1/y1/page). "
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
        "source_citation (object: source_type, source_id, page_or_section, "
        "field_or_chunk_id, quote_or_value; plus optional bbox with x0/y0/x1/y1/page). "
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


def _call_claude_vision(path: Path, doc_type: str) -> str:
    """Send the file to Claude and return the raw text reply."""
    media_type = _media_type(path)
    data = base64.standard_b64encode(path.read_bytes()).decode()

    if media_type == "application/pdf":
        file_block: dict = {
            "type": "document",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }
    else:
        file_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [file_block, {"type": "text", "text": _EXTRACT_PROMPTS[doc_type]}],
            }
        ],
    )
    return msg.content[0].text


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that models occasionally add."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


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
    """PATCH the Patient resource with demographics from the intake form."""
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


def attach_and_extract(
    patient_id: int,
    file_path: str,
    doc_type: Literal["lab_pdf", "intake_form"],
) -> Union[list[LabResult], IntakeForm]:
    """Extract structured data from a clinical document and write to OpenEMR FHIR.

    Sends the file to Claude vision, validates the response against the schema,
    writes FHIR resources (Observation for labs, Patient update for intake),
    and returns the validated schema object(s).

    Raises:
        ValueError: unknown doc_type or DEMO_MODE is on and PHI write is blocked.
        FileNotFoundError: file_path does not exist.
        pydantic.ValidationError: Claude's response doesn't match the schema.
        httpx.HTTPStatusError: FHIR write failed.
    """
    if doc_type not in _EXTRACT_PROMPTS:
        raise ValueError(f"doc_type must be 'lab_pdf' or 'intake_form', got {doc_type!r}")

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if DEMO_MODE:
        raise ValueError(
            "COPILOT_DEMO_MODE is enabled — FHIR writes are blocked. "
            "Set COPILOT_DEMO_MODE=false after executing a BAA with Anthropic."
        )

    raw = _call_claude_vision(path, doc_type)
    payload = json.loads(_strip_fences(raw))

    token = _get_openemr_token()

    if doc_type == "lab_pdf":
        results = [LabResult.model_validate(item) for item in payload]
        for lab in results:
            _write_observation(patient_id, lab, token)
        return results

    intake = IntakeForm.model_validate(payload)
    _write_patient_update(patient_id, intake, token)
    return intake
