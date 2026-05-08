"""Unit tests for the HL7v2 parser (hl7.py).

Tests cover:
  - Segment tokenizer (CR-only, LF-only, CRLF)
  - Field and component accessors
  - Date parsing (YYYYMMDD, YYYYMMDDHHMMSS, timezone suffixes)
  - ORU-R01 → LabResult: LOINC extraction, abnormal flags, collection date,
    multiple OBR groups, missing values, fallback dates
  - ADT-A08 → IntakeForm: name, DOB, sex, phone, address, EVN chief concern,
    NK1 family history, empty-field robustness
  - detect_message_type router
  - Citation shape: source_type, transform_chain, no bbox, no PHI in field_id

Run with: python -m pytest evals/test_hl7.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from hl7 import (
    Segment,
    _parse_date,
    _parse_name,
    _parse_phone,
    _parse_address,
    detect_message_type,
    parse_oru_r01,
    parse_adt_a08,
    tokenize,
)
from schemas import IntakeForm, LabResult


# ---------------------------------------------------------------------------
# Fixtures — raw HL7 messages
# ---------------------------------------------------------------------------

ORU_CHEN = (
    "MSH|^~\\&|BHS-LIS|BERKELEY HLTH SYS LAB|EHR^^L|EHR|20260506143215||"
    "ORU^R01^ORU_R01|MSG-p01-20260506143215-ORU|P|2.5.1\r"
    "PID|1||BHS-2847163^^^MRN^MR||CHEN^MARGARET^L||19680312|F\r"
    "OBR|1|ORD-p01-0001|FIL-p01-0001|57698-3^Lipid panel^LN|||20260412093000\r"
    "OBX|1|NM|2093-3^Cholesterol [Mass/volume] in Serum^LN||218|mg/dL|<200|H|||F|||20260412093000\r"
    "OBX|2|NM|2089-1^LDL Cholesterol^LN||142|mg/dL|<100|H|||F|||20260412093000\r"
    "OBX|3|NM|2085-9^HDL Cholesterol^LN||48|mg/dL|>=40|N|||F|||20260412093000\r"
    "OBX|4|NM|2571-8^Triglycerides^LN||168|mg/dL|<150|H|||F|||20260412093000\r"
    "NTE|1|L|Repeat lipid panel in 6 weeks.\r"
)

# Multi-panel ORU (two OBR groups)
ORU_MULTI_PANEL = (
    "MSH|^~\\&|LIS|LAB|EHR||20260425||ORU^R01|MSG-MP-001|P|2.5.1\r"
    "PID|1||PT-001^^^MRN||SMITH^JOHN||19540208|M\r"
    "OBR|1|ORD-001|FIL-001|24320-4^BMP^LN|||20260425100000\r"
    "OBX|1|NM|2951-2^Sodium^LN||138|mmol/L|136-145|N|||F|||20260425100000\r"
    "OBX|2|NM|2160-0^Creatinine^LN||1.6|mg/dL|0.70-1.30|H|||F|||20260425100000\r"
    "OBR|2|ORD-002|FIL-002|30934-4^BNP^LN|||20260425101500\r"
    "OBX|1|NM|30934-4^BNP^LN||842|pg/mL|<100|HH|||F|||20260425101500\r"
)

ADT_CHEN = (
    "MSH|^~\\&|REGISTRATION|BERKELEY HLTH SYS|EHR^^L|EHR|20260506143215||"
    "ADT^A08^ADT_A01|MSG-p01-20260506143215-ADT|P|2.5.1\r"
    # EVN: 3 pipes after datetime → operator at [5], reason at [6] (matches real files)
    "EVN|A08|20260506143215|||1618829315^PARK^HELEN|"
    "Medication change recorded — atorvastatin titration; ezetimibe added\r"
    "PID|1||BHS-2847163^^^MRN^MR||CHEN^MARGARET^L||19680312|F||"
    "2028-9^Asian^HL70005|2418 CHANNING WAY^^BERKELEY^CA^94704^USA||"
    "^PRN^PH^^^510^5550142|||M\r"
    "NK1|1|CHEN^DAVID|SPO^Spouse|||^PRN^PH^^^510^5550199\r"
)

ADT_WHITAKER = (
    "MSH|^~\\&|REGISTRATION|NM MEDICAL GROUP|EHR^^L|EHR|20260506||"
    "ADT^A08^ADT_A01|MSG-p02-ADT|P|2.5.1\r"
    "EVN|A08|20260506|||1636814596^ORTEGA^DANIEL|"
    "GI consult requested; insurance and PCP info updated\r"
    "PID|1||NMM-9912448^^^MRN^MR||WHITAKER^JAMES^R||19581122|M||"
    "2106-3^White^HL70005|4127 COMANCHE RD NE^^ALBUQUERQUE^NM^87110^USA||"
    "^PRN^PH^^^505^5550281\r"
)


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class TestTokenizer:
    def test_cr_only(self):
        segs = tokenize("MSH|a|b\rPID|1|2\r")
        assert len(segs) == 2
        assert segs[0].name == "MSH"
        assert segs[1].name == "PID"

    def test_lf_only(self):
        segs = tokenize("MSH|a|b\nPID|1|2\n")
        assert len(segs) == 2

    def test_crlf(self):
        segs = tokenize("MSH|a|b\r\nPID|1|2\r\n")
        assert len(segs) == 2

    def test_blank_lines_skipped(self):
        segs = tokenize("MSH|a\r\r\rPID|1\r")
        assert len(segs) == 2

    def test_segment_name(self):
        segs = tokenize("OBX|1|NM|2093-3^Chol^LN||218|mg/dL|<200|H\r")
        assert segs[0].name == "OBX"

    def test_field_access(self):
        seg = tokenize("OBX|1|NM|code^name^LN||218|mg/dL\r")[0]
        assert seg.field(5) == "218"
        assert seg.field(6) == "mg/dL"
        assert seg.field(99) == ""   # out of range → empty default

    def test_component_access(self):
        seg = tokenize("OBX|1|NM|2093-3^Cholesterol^LN||218\r")[0]
        assert seg.component(3, 0) == "2093-3"
        assert seg.component(3, 1) == "Cholesterol"
        assert seg.component(3, 2) == "LN"
        assert seg.component(3, 9) == ""   # out of range


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

class TestDateParsing:
    def test_yyyymmdd(self):
        assert _parse_date("19680312") == "1968-03-12"

    def test_yyyymmddhhmmss(self):
        assert _parse_date("20260412093000") == "2026-04-12"

    def test_with_negative_timezone(self):
        assert _parse_date("20260412093000-0500") == "2026-04-12"

    def test_with_positive_timezone(self):
        assert _parse_date("20260412093000+0100") == "2026-04-12"

    def test_empty(self):
        assert _parse_date("") == ""

    def test_non_date_passthrough(self):
        result = _parse_date("unknown")
        assert result == "unknown"


# ---------------------------------------------------------------------------
# Name / phone / address helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_parse_name_full(self):
        assert _parse_name("CHEN^MARGARET^L") == "Margaret L Chen"

    def test_parse_name_no_middle(self):
        assert _parse_name("WHITAKER^JAMES^") == "James Whitaker"

    def test_parse_name_last_only(self):
        assert _parse_name("JONES") == "Jones"

    def test_parse_phone_standard(self):
        result = _parse_phone("^PRN^PH^^^510^5550142")
        assert result == "(510) 555-0142"

    def test_parse_phone_missing_components(self):
        # Should not raise; returns empty or partial
        result = _parse_phone("^PRN^PH")
        assert isinstance(result, str)

    def test_parse_address_full(self):
        result = _parse_address("2418 CHANNING WAY^^BERKELEY^CA^94704^USA")
        assert "CHANNING" in result
        assert "BERKELEY" in result
        assert "CA" in result

    def test_parse_address_missing_components(self):
        result = _parse_address("123 MAIN ST")
        assert "MAIN" in result


# ---------------------------------------------------------------------------
# ORU-R01 → list[LabResult]
# ---------------------------------------------------------------------------

class TestOruR01:
    def test_result_count(self):
        results = parse_oru_r01(ORU_CHEN)
        assert len(results) == 4

    def test_first_result_fields(self):
        results = parse_oru_r01(ORU_CHEN)
        r = results[0]
        assert "Cholesterol" in r.test_name
        assert r.value == "218"
        assert r.unit == "mg/dL"
        assert r.reference_range == "<200"
        assert r.abnormal_flag is True
        assert r.collection_date == "2026-04-12"

    def test_normal_flag(self):
        results = parse_oru_r01(ORU_CHEN)
        hdl = next(r for r in results if "HDL" in r.test_name)
        assert hdl.abnormal_flag is False

    def test_loinc_in_field_id(self):
        results = parse_oru_r01(ORU_CHEN)
        assert "2093-3" in results[0].source_citation.field_or_chunk_id

    def test_citation_source_type(self):
        results = parse_oru_r01(ORU_CHEN)
        for r in results:
            assert r.source_citation.source_type == "hl7"

    def test_citation_no_bbox(self):
        results = parse_oru_r01(ORU_CHEN)
        for r in results:
            assert r.source_citation.bbox is None

    def test_citation_transform_chain(self):
        results = parse_oru_r01(ORU_CHEN)
        tc = results[0].source_citation.transform_chain
        assert "hl7v2_source" in tc
        assert "segment_OBX" in tc
        assert "deterministic_parse" in tc

    def test_citation_parser(self):
        results = parse_oru_r01(ORU_CHEN)
        assert results[0].source_citation.parser == "hl7v2_parser"

    def test_msg_id_in_source_id(self):
        results = parse_oru_r01(ORU_CHEN)
        assert "MSG-p01" in results[0].source_citation.source_id

    def test_multi_panel_two_obr_groups(self):
        results = parse_oru_r01(ORU_MULTI_PANEL)
        assert len(results) == 3

    def test_multi_panel_collection_dates_per_group(self):
        results = parse_oru_r01(ORU_MULTI_PANEL)
        sodium = next(r for r in results if "Sodium" in r.test_name)
        bnp    = next(r for r in results if "BNP" in r.test_name)
        assert sodium.collection_date == "2026-04-25"
        assert bnp.collection_date == "2026-04-25"   # same day, different time

    def test_hh_flag_is_abnormal(self):
        results = parse_oru_r01(ORU_MULTI_PANEL)
        bnp = next(r for r in results if "BNP" in r.test_name)
        assert bnp.abnormal_flag is True

    def test_skips_empty_value(self):
        raw = (
            "MSH|^~\\&|LIS|LAB|EHR||20260101||ORU^R01|MSG-X|P|2.5.1\r"
            "OBX|1|NM|1234-5^Test^LN||||mg/dL|N|||F\r"  # empty value field
        )
        results = parse_oru_r01(raw)
        assert len(results) == 0

    def test_pydantic_validation(self):
        results = parse_oru_r01(ORU_CHEN)
        for r in results:
            assert isinstance(r, LabResult)


# ---------------------------------------------------------------------------
# ADT-A08 → IntakeForm
# ---------------------------------------------------------------------------

class TestAdtA08:
    def test_returns_intake_form(self):
        result = parse_adt_a08(ADT_CHEN)
        assert isinstance(result, IntakeForm)

    def test_demographics_name(self):
        result = parse_adt_a08(ADT_CHEN)
        assert result.demographics.name == "Margaret L Chen"

    def test_demographics_dob(self):
        result = parse_adt_a08(ADT_CHEN)
        assert result.demographics.dob == "1968-03-12"

    def test_demographics_sex(self):
        result = parse_adt_a08(ADT_CHEN)
        assert result.demographics.sex == "Female"

    def test_demographics_phone(self):
        result = parse_adt_a08(ADT_CHEN)
        assert result.demographics.phone == "(510) 555-0142"

    def test_demographics_address(self):
        result = parse_adt_a08(ADT_CHEN)
        addr = result.demographics.address or ""
        assert "CHANNING" in addr
        assert "BERKELEY" in addr

    def test_chief_concern_from_evn(self):
        result = parse_adt_a08(ADT_CHEN)
        assert "atorvastatin" in result.chief_concern

    def test_family_history_from_nk1(self):
        result = parse_adt_a08(ADT_CHEN)
        assert len(result.family_history) == 1
        assert "Chen" in result.family_history[0] or "CHEN" in result.family_history[0]

    def test_medications_empty(self):
        result = parse_adt_a08(ADT_CHEN)
        assert result.medications == []

    def test_allergies_empty(self):
        result = parse_adt_a08(ADT_CHEN)
        assert result.allergies == []

    def test_citation_source_type(self):
        result = parse_adt_a08(ADT_CHEN)
        assert result.source_citation.source_type == "hl7"

    def test_citation_no_bbox(self):
        result = parse_adt_a08(ADT_CHEN)
        assert result.source_citation.bbox is None

    def test_citation_transform_chain(self):
        result = parse_adt_a08(ADT_CHEN)
        tc = result.source_citation.transform_chain
        assert "hl7v2_source" in tc
        assert "segment_PID" in tc
        assert "deterministic_parse" in tc

    def test_whitaker_male_sex(self):
        result = parse_adt_a08(ADT_WHITAKER)
        assert result.demographics.sex == "Male"

    def test_whitaker_chief_concern(self):
        result = parse_adt_a08(ADT_WHITAKER)
        assert "GI consult" in result.chief_concern

    def test_no_nk1_empty_family_history(self):
        raw = (
            "MSH|^~\\&|REG|HOSP|EHR||20260101||ADT^A08|MSG-X|P|2.5.1\r"
            "EVN|A08|20260101\r"
            "PID|1||PT-001|||JONES^BOB||19700101|M\r"
        )
        result = parse_adt_a08(raw)
        assert result.family_history == []

    def test_missing_evn_default_chief_concern(self):
        raw = (
            "MSH|^~\\&|REG|HOSP|EHR||20260101||ADT^A08|MSG-X|P|2.5.1\r"
            "PID|1||PT-001|||JONES^BOB||19700101|M\r"
        )
        result = parse_adt_a08(raw)
        assert "no specific reason" in result.chief_concern.lower()


# ---------------------------------------------------------------------------
# detect_message_type
# ---------------------------------------------------------------------------

class TestDetectMessageType:
    def test_oru_r01(self):
        assert detect_message_type(ORU_CHEN) == "ORU_R01"

    def test_adt_a08(self):
        assert detect_message_type(ADT_CHEN) == "ADT_A08"

    def test_unknown(self):
        raw = "MSH|^~\\&|SYS|FAC|EHR||20260101||SIU^S12|MSG-X|P|2.5.1\r"
        result = detect_message_type(raw)
        assert result not in ("ORU_R01", "ADT_A08")

    def test_no_msh_returns_unknown(self):
        assert detect_message_type("OBX|1|NM|code||value\r") == "UNKNOWN"


# ---------------------------------------------------------------------------
# Integration: parse actual fixture files
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "hl7v2"


@pytest.mark.skipif(not FIXTURE_DIR.exists(), reason="fixture files not present")
class TestFixtureFiles:
    def test_all_oru_files_parse(self):
        for f in sorted(FIXTURE_DIR.glob("*oru*.hl7")):
            results = parse_oru_r01(f.read_bytes().decode("utf-8", errors="replace"), f.name)
            assert len(results) > 0, f"{f.name} produced no LabResults"
            for r in results:
                assert isinstance(r, LabResult)
                assert r.test_name
                assert r.value

    def test_all_adt_files_parse(self):
        for f in sorted(FIXTURE_DIR.glob("*adt*.hl7")):
            result = parse_adt_a08(f.read_bytes().decode("utf-8", errors="replace"), f.name)
            assert isinstance(result, IntakeForm)
            assert result.demographics.name   # must extract a name
            assert result.demographics.dob    # must extract a DOB

    def test_no_phi_in_field_ids(self):
        """Citation field_or_chunk_id must not contain raw patient names or DOBs."""
        import re
        dob_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
        for f in FIXTURE_DIR.glob("*oru*.hl7"):
            results = parse_oru_r01(f.read_bytes().decode("utf-8", errors="replace"), f.name)
            for r in results:
                fid = r.source_citation.field_or_chunk_id
                assert not dob_pattern.search(fid), f"DOB in field_id: {fid}"
