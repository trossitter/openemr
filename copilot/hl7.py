"""HL7v2 message parser — ORU-R01 (lab results) and ADT-A08 (patient updates).

Parses pipe-delimited HL7v2 messages without external dependencies.
All segment separators are handled: CR-only, LF-only, and CRLF.

Supported message types:
  ORU^R01 — Unsolicited Observation Result  → list[LabResult]
  ADT^A08 — Patient Update Information      → IntakeForm

Each extracted record carries a Citation with:
  source_type = "hl7"
  source_id   = MSH message control ID
  field_or_chunk_id = LOINC code (ORU) or segment+field (ADT)
  transform_chain   = ["hl7v2_source", "segment_X", "field_N", "deterministic_parse"]
  bbox = None  (HL7v2 is text — no visual position exists)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from coords import TransformChain
from schemas import Citation, Demographics, FaxPacket, IntakeForm, LabResult, PertinentLab


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """One HL7v2 segment with random-access field and component lookup."""
    name: str
    fields: list[str]   # fields[0] = segment name, fields[1] = first data field

    def field(self, idx: int, default: str = "") -> str:
        """Return the field at 1-based HL7 position idx (= fields[idx])."""
        try:
            return self.fields[idx] or default
        except IndexError:
            return default

    def component(self, field_idx: int, comp_idx: int, default: str = "") -> str:
        """Return component comp_idx (0-based) within the field at field_idx."""
        f = self.field(field_idx)
        parts = f.split("^")
        try:
            return parts[comp_idx] or default
        except IndexError:
            return default


def tokenize(raw: str) -> list[Segment]:
    """Split HL7v2 text into Segment objects.

    Handles CR-only (\\r), LF-only (\\n), and CRLF (\\r\\n) terminators.
    Blank lines and MACOSX noise are silently skipped.
    """
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    segments: list[Segment] = []
    for line in normalized.split("\n"):
        line = line.strip()
        if not line:
            continue
        fields = line.split("|")
        name = fields[0].upper().strip()
        if len(name) < 2 or len(name) > 4:
            continue   # not a valid segment name
        segments.append(Segment(name=name, fields=fields))
    return segments


def _get(segments: list[Segment], name: str) -> Optional[Segment]:
    for s in segments:
        if s.name == name:
            return s
    return None


def _get_all(segments: list[Segment], name: str) -> list[Segment]:
    return [s for s in segments if s.name == name]


# ---------------------------------------------------------------------------
# Message type detection
# ---------------------------------------------------------------------------

def detect_message_type(raw: str) -> str:
    """Return 'ORU_R01', 'ADT_A08', or 'UNKNOWN' from MSH-9.

    MSH is special in HL7v2: MSH-1 is the field separator character itself
    (absorbed by the split), so MSH-9 (message type) lives at fields[8] in
    our 0-based list, not fields[9].
    """
    msh = _get(tokenize(raw), "MSH")
    if not msh:
        return "UNKNOWN"
    # fields[8] = MSH-9 message type, e.g. "ORU^R01^ORU_R01"
    msg_type = msh.field(8).upper()
    if msg_type.startswith("ORU"):
        return "ORU_R01"
    if msg_type.startswith("ADT"):
        trigger = msh.component(8, 1)   # component 1 = trigger event, e.g. "A08"
        return f"ADT_{trigger}" if trigger else "ADT"
    return msg_type.replace("^", "_")


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_date(dt_str: str) -> str:
    """Parse HL7 datetime (YYYYMMDDHHMMSS or YYYYMMDD) → YYYY-MM-DD string.

    Returns the raw string unchanged if it cannot be parsed.
    """
    s = dt_str.strip()
    # Strip timezone offset if present (e.g. "20260412093000-0500")
    for sep in ("-", "+"):
        if sep in s[8:]:
            s = s[:s.index(sep, 8)]
    s = s[:8]   # take YYYYMMDD portion
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return dt_str


# ---------------------------------------------------------------------------
# Citation builder
# ---------------------------------------------------------------------------

def _citation(
    msg_id: str,
    segment_name: str,
    field_idx: int,
    field_or_chunk_id: str,
    quote_or_value: str,
) -> Citation:
    tc = TransformChain.for_hl7_field(segment_name, field_idx)
    return Citation(
        source_type="hl7",
        source_id=msg_id,
        page_or_section=f"{segment_name}-{field_idx}",
        field_or_chunk_id=field_or_chunk_id,
        quote_or_value=quote_or_value[:500],   # cap length; no PHI in logs
        bbox=None,
        transform_chain=tc.to_list(),
        parser="hl7v2_parser",
        evidence_type="native_hl7v2_text",
    )


# ---------------------------------------------------------------------------
# ORU-R01 parser → list[LabResult]
# ---------------------------------------------------------------------------

# Abnormal flags that indicate a result outside reference range
_ABNORMAL_FLAGS = frozenset(
    "H HH L LL A AA U D B W HU LU".split()
)


def parse_oru_r01(raw: str, source_filename: str = "") -> list[LabResult]:
    """Parse an HL7v2 ORU-R01 message into LabResult objects.

    OBX segment field mapping (1-based HL7 positions):
      OBX[1]  = set_id
      OBX[2]  = value_type  (NM=numeric, ST=string, …)
      OBX[3]  = observation_identifier  (LOINC^name^LN)
      OBX[4]  = observation_sub_id
      OBX[5]  = observation_value
      OBX[6]  = units
      OBX[7]  = reference_range
      OBX[8]  = abnormal_flags  (H/HH/L/LL/A/N …)
      OBX[11] = observation_result_status  (F = final)
      OBX[14] = date_time_of_observation  (YYYYMMDDHHMMSS)

    OBR[7] is used as a fallback collection date when OBX[14] is absent.
    Multiple OBR groups (multiple panels in one message) are supported.
    """
    segs = tokenize(raw)
    msh = _get(segs, "MSH")
    msg_id = msh.field(9) if msh else (source_filename or str(uuid.uuid4())[:12])

    results: list[LabResult] = []
    current_obr_date = ""

    for seg in segs:
        if seg.name == "OBR":
            # OBR[7] = observation_date_time
            raw_date = seg.field(7)
            if raw_date:
                current_obr_date = _parse_date(raw_date)

        elif seg.name == "OBX":
            value = seg.field(5).strip()
            if not value:
                continue   # skip results with no value

            loinc       = seg.component(3, 0)     # "2093-3"
            test_name   = seg.component(3, 1)     # "Cholesterol [Mass/volume]..."
            if not test_name:
                test_name = loinc or seg.field(3)

            unit        = seg.field(6)
            ref_range   = seg.field(7)
            flag_raw    = seg.field(8).strip().upper()
            obs_dt      = seg.field(14) or seg.field(12)
            coll_date   = _parse_date(obs_dt) if obs_dt else current_obr_date

            abnormal    = flag_raw in _ABNORMAL_FLAGS

            set_id = seg.field(1)
            field_id = f"{loinc}_OBX{set_id}" if loinc else f"OBX_{set_id}"

            citation = _citation(msg_id, "OBX", 5, field_id, value)

            results.append(LabResult(
                test_name=test_name,
                value=value,
                unit=unit,
                reference_range=ref_range,
                collection_date=coll_date or "unknown",
                abnormal_flag=abnormal,
                source_citation=citation,
            ))

    return results


# ---------------------------------------------------------------------------
# ADT-A08 parser → IntakeForm
# ---------------------------------------------------------------------------

def _parse_name(hl7_name: str) -> str:
    """Parse HL7 XPN name 'LAST^FIRST^MIDDLE^SUFFIX^PREFIX' → 'First Middle Last'."""
    parts = hl7_name.split("^")
    last   = parts[0].strip().title() if len(parts) > 0 else ""
    first  = parts[1].strip().title() if len(parts) > 1 else ""
    middle = parts[2].strip().title() if len(parts) > 2 and parts[2].strip() else ""
    tokens = [p for p in [first, middle, last] if p]
    return " ".join(tokens)


def _parse_phone(hl7_phone: str) -> str:
    """Parse HL7 XTN phone '^PRN^PH^^^{area}^{local}' → '(area) xxx-xxxx'.

    XTN component indices (0-based after splitting on ^):
      [0] = unused / whole-number fallback
      [1] = use code (PRN = primary residence)
      [2] = equipment type (PH = phone)
      [3] = email (unused here)
      [4] = country code
      [5] = area/city code
      [6] = local number
    """
    parts = hl7_phone.split("^")
    area  = parts[5].strip() if len(parts) > 5 else ""
    local = parts[6].strip() if len(parts) > 6 else ""

    if area and local:
        # Format local as xxx-xxxx if 7 digits
        loc_fmt = f"{local[:3]}-{local[3:]}" if len(local) >= 7 else local
        return f"({area}) {loc_fmt}"

    # Fallback: whole-number in component 0
    whole = parts[0].strip()
    return whole if whole else ""


def _parse_address(hl7_addr: str) -> str:
    """Parse HL7 XAD address 'STREET^^CITY^STATE^ZIP^COUNTRY' → readable string."""
    parts = hl7_addr.split("^")
    street = parts[0].strip() if len(parts) > 0 else ""
    city   = parts[2].strip() if len(parts) > 2 else ""
    state  = parts[3].strip() if len(parts) > 3 else ""
    postal = parts[4].strip() if len(parts) > 4 else ""
    state_zip = f"{state} {postal}".strip()
    tokens = [t for t in [street, city, state_zip] if t]
    return ", ".join(tokens)


def parse_adt_a08(raw: str, source_filename: str = "") -> IntakeForm:
    """Parse an HL7v2 ADT-A08 message into an IntakeForm.

    PID field mapping (1-based):
      PID[3]  = patient_id_list (MRN in component 0)
      PID[5]  = patient_name (XPN: LAST^FIRST^MIDDLE)
      PID[7]  = date_of_birth (YYYYMMDD)
      PID[8]  = administrative_sex (F/M/O/U)
      PID[11] = patient_address (XAD)
      PID[13] = phone_home (XTN)

    EVN[6]  = event_reason_code / operator note → chief_concern
    NK1     = next_of_kin → family_history entries

    Note: ADT-A08 does not carry medication or allergy lists.
    Those fields are populated as empty and should be sourced from
    a separate RDE/OMP or AL1 message.
    """
    segs = tokenize(raw)
    msh = _get(segs, "MSH")
    msg_id = msh.field(9) if msh else (source_filename or str(uuid.uuid4())[:12])

    pid = _get(segs, "PID")
    evn = _get(segs, "EVN")

    # --- Demographics ---
    demo = Demographics()
    if pid:
        demo.name    = _parse_name(pid.field(5))
        raw_dob      = pid.field(7)
        demo.dob     = _parse_date(raw_dob) if raw_dob else None
        sex_code     = pid.field(8).strip().upper()
        demo.sex     = {"F": "Female", "M": "Male", "O": "Other", "U": "Unknown"}.get(
                           sex_code, sex_code or None
                       )
        demo.phone   = _parse_phone(pid.field(13)) or None
        demo.address = _parse_address(pid.field(11)) or None

    # --- Chief concern from EVN reason text ---
    chief_concern = "Patient update — no specific reason recorded."
    if evn:
        # EVN-6 = event occurred / operator note (free text reason).
        # EVN-5 = operator ID (structured XCN field — skip if it looks like one).
        # We prefer the last non-empty field that doesn't look like an XCN.
        for field_idx in (6, 7):
            candidate = evn.field(field_idx).strip()
            if candidate and "^" not in candidate:
                chief_concern = candidate
                break
        else:
            # Fallback: any non-empty non-XCN field after EVN-3
            for field_idx in range(3, len(evn.fields)):
                candidate = evn.field(field_idx).strip()
                if candidate and "^" not in candidate:
                    chief_concern = candidate
                    break

    # --- Family history from NK1 segments ---
    family_history: list[str] = []
    for nk1 in _get_all(segs, "NK1"):
        nk_name = _parse_name(nk1.field(2))
        # NK1[3] = relationship code (e.g. "SPO" = spouse, "FTH" = father)
        rel_code = nk1.component(3, 0)
        rel_text = nk1.component(3, 1) or rel_code  # component 1 may have display text
        entry = nk_name if nk_name else "(unknown)"
        if rel_text:
            entry = f"{entry} ({rel_text})"
        family_history.append(entry)

    # --- Citation: anchored to PID[5] (patient name field) ---
    pid_name_raw = pid.field(5) if pid else ""
    citation = _citation(msg_id, "PID", 5, "demographics", pid_name_raw)

    return IntakeForm(
        demographics=demo,
        chief_concern=chief_concern,
        medications=[],      # not carried in ADT-A08
        allergies=[],        # not carried in ADT-A08
        family_history=family_history,
        source_citation=citation,
    )
