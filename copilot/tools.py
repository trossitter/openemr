"""
Patient data retrieval tools for the Clinical Co-Pilot.

Each function queries OpenEMR's MariaDB directly using a read-only connection.
All tools enforce that queries are scoped to a single patient PID — there is
no mechanism for cross-patient data access.

Tool results are returned as structured dicts that are both passed to Claude
and retained for verification (to confirm the agent's claims are grounded).
"""
import time
from typing import Any

import pymysql
import pymysql.cursors

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS, MAX_ENCOUNTERS
from observability import log_tool_call, log_tool_error, timer


def _connect():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=10,
    )


def _run(trace_id: str, tool_name: str, args: dict, query: str, params: tuple) -> list[dict]:
    with timer() as t:
        try:
            conn = _connect()
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
            conn.close()
            log_tool_call(trace_id, tool_name, args, t.get("ms", 0), len(rows))
            return rows
        except Exception as e:
            log_tool_error(trace_id, tool_name, str(e))
            raise


# ---------------------------------------------------------------------------
# Tool definitions (schema passed to Claude)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "get_patient_demographics",
        "description": (
            "Retrieve patient demographics: name, date of birth, age, sex, "
            "contact information, and primary provider. Use this first to confirm "
            "you are looking at the correct patient."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "OpenEMR patient ID"}
            },
            "required": ["pid"],
        },
    },
    {
        "name": "get_active_medications",
        "description": (
            "Retrieve the patient's currently active medications, including drug name, "
            "dose, route, frequency, indication, and start date. "
            "Note: active status is manually managed — always report medications "
            "as 'active per chart as of [date]' not as confirmed current."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "OpenEMR patient ID"}
            },
            "required": ["pid"],
        },
    },
    {
        "name": "get_recent_encounters",
        "description": (
            "Retrieve the patient's most recent clinical encounters including "
            "visit date, reason, SOAP note (subjective, objective, assessment, plan), "
            "and vitals. Returns up to 5 most recent encounters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "OpenEMR patient ID"},
                "limit": {
                    "type": "integer",
                    "description": "Number of encounters to retrieve (1-10, default 3)",
                    "default": 3,
                },
            },
            "required": ["pid"],
        },
    },
    {
        "name": "get_vitals",
        "description": (
            "Retrieve the patient's most recent vital signs: blood pressure, "
            "heart rate, respiratory rate, temperature, oxygen saturation, "
            "weight, height, and BMI."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "OpenEMR patient ID"}
            },
            "required": ["pid"],
        },
    },
    {
        "name": "get_data_gaps",
        "description": (
            "Identify gaps in the patient's chart: missing demographics, "
            "no encounter history, no active medications, no recent vitals, "
            "missing allergy documentation, or missing problem list. "
            "Always run this when preparing a pre-visit briefing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "OpenEMR patient ID"}
            },
            "required": ["pid"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_patient_demographics(pid: int, trace_id: str) -> dict:
    rows = _run(
        trace_id, "get_patient_demographics", {"pid": pid},
        """
        SELECT pid, fname, lname, mname, DOB,
               TIMESTAMPDIFF(YEAR, DOB, CURDATE()) AS age,
               sex, phone_home, phone_cell, email,
               street, city, state, postal_code,
               providerID
        FROM patient_data
        WHERE pid = %s
        LIMIT 1
        """,
        (pid,),
    )
    if not rows:
        return {"error": f"No patient found with pid={pid}"}
    p = rows[0]
    return {
        "pid": p["pid"],
        "name": f"{p['fname']} {p['lname']}",
        "dob": str(p["DOB"]) if p["DOB"] else None,
        "age": p["age"],
        "sex": p["sex"],
        "phone": p["phone_cell"] or p["phone_home"],
        "email": p["email"],
        "address": f"{p['street']}, {p['city']}, {p['state']} {p['postal_code']}",
        "source": "patient_data table",
    }


def get_active_medications(pid: int, trace_id: str) -> dict:
    rows = _run(
        trace_id, "get_active_medications", {"pid": pid},
        """
        SELECT drug, dosage, route, indication,
               date_added, start_date, end_date,
               note, refills, active
        FROM prescriptions
        WHERE patient_id = %s AND active = 1
        ORDER BY date_added DESC
        """,
        (pid,),
    )
    meds = []
    for r in rows:
        meds.append({
            "drug": r["drug"],
            "dosage": r["dosage"],
            "route": r["route"],
            "indication": r["indication"],
            "start_date": str(r["start_date"]) if r["start_date"] else None,
            "note": r["note"],
        })
    return {
        "count": len(meds),
        "medications": meds,
        "caveat": "Active status is manually maintained in chart. Verify currency with patient.",
        "source": "prescriptions table",
    }


def get_recent_encounters(pid: int, trace_id: str, limit: int = 3) -> dict:
    limit = min(max(1, limit), MAX_ENCOUNTERS)
    enc_rows = _run(
        trace_id, "get_recent_encounters", {"pid": pid, "limit": limit},
        """
        SELECT fe.id AS encounter_id, fe.date, fe.reason,
               fs.subjective, fs.objective, fs.assessment, fs.plan,
               fv.bps, fv.bpd, fv.pulse, fv.respiration,
               fv.temperature, fv.oxygen_saturation,
               fv.weight, fv.height, fv.BMI
        FROM form_encounter fe
        LEFT JOIN form_soap fs ON fs.pid = fe.pid
            AND DATE(fs.date) = DATE(fe.date)
        LEFT JOIN form_vitals fv ON fv.pid = fe.pid
            AND DATE(fv.date) = DATE(fe.date)
        WHERE fe.pid = %s
        ORDER BY fe.date DESC
        LIMIT %s
        """,
        (pid, limit),
    )
    encounters = []
    seen = set()
    for r in enc_rows:
        eid = r["encounter_id"]
        if eid in seen:
            continue
        seen.add(eid)
        enc = {
            "date": str(r["date"])[:10] if r["date"] else None,
            "reason": r["reason"],
            "soap": None,
            "vitals": None,
            "source": f"form_encounter id={eid}",
        }
        if r["subjective"] or r["assessment"]:
            enc["soap"] = {
                "subjective": r["subjective"],
                "objective": r["objective"],
                "assessment": r["assessment"],
                "plan": r["plan"],
            }
        if r["bps"]:
            enc["vitals"] = {
                "bp": f"{r['bps']}/{r['bpd']} mmHg" if r["bpd"] else None,
                "hr": f"{r['pulse']} bpm" if r["pulse"] else None,
                "rr": f"{r['respiration']} /min" if r["respiration"] else None,
                "temp": f"{r['temperature']} °F" if r["temperature"] else None,
                "o2_sat": f"{r['oxygen_saturation']}%" if r["oxygen_saturation"] else None,
                "weight": f"{r['weight']} lbs" if r["weight"] else None,
                "bmi": str(r["BMI"]) if r["BMI"] else None,
            }
        encounters.append(enc)
    return {
        "count": len(encounters),
        "encounters": encounters,
        "source": "form_encounter + form_soap + form_vitals tables",
    }


def get_vitals(pid: int, trace_id: str) -> dict:
    rows = _run(
        trace_id, "get_vitals", {"pid": pid},
        """
        SELECT date, bps, bpd, pulse, respiration, temperature,
               oxygen_saturation, weight, height, BMI
        FROM form_vitals
        WHERE pid = %s
        ORDER BY date DESC
        LIMIT 1
        """,
        (pid,),
    )
    if not rows:
        return {"error": "No vitals on record", "source": "form_vitals table"}
    v = rows[0]
    return {
        "date": str(v["date"])[:10] if v["date"] else None,
        "bp": f"{v['bps']}/{v['bpd']} mmHg" if v["bps"] and v["bpd"] else None,
        "hr": f"{v['pulse']} bpm" if v["pulse"] else None,
        "rr": f"{v['respiration']} /min" if v["respiration"] else None,
        "temp": f"{v['temperature']} °F" if v["temperature"] else None,
        "o2_sat": f"{v['oxygen_saturation']}%" if v["oxygen_saturation"] else None,
        "weight": f"{v['weight']} lbs" if v["weight"] else None,
        "bmi": str(v["BMI"]) if v["BMI"] else None,
        "source": "form_vitals table",
    }


def get_data_gaps(pid: int, trace_id: str) -> dict:
    gaps = []

    # Check demographics
    demo_rows = _run(
        trace_id, "get_data_gaps:demographics", {"pid": pid},
        "SELECT pid, fname, lname, DOB, sex FROM patient_data WHERE pid = %s",
        (pid,),
    )
    if not demo_rows:
        gaps.append("CRITICAL: No patient record found for this PID")
    else:
        d = demo_rows[0]
        if not d["DOB"]:
            gaps.append("Missing date of birth")
        if not d["sex"]:
            gaps.append("Missing sex")

    # Check encounters
    enc_rows = _run(
        trace_id, "get_data_gaps:encounters", {"pid": pid},
        "SELECT COUNT(*) AS cnt FROM form_encounter WHERE pid = %s",
        (pid,),
    )
    if enc_rows[0]["cnt"] == 0:
        gaps.append("No encounter history in this system")

    # Check medications
    med_rows = _run(
        trace_id, "get_data_gaps:medications", {"pid": pid},
        "SELECT COUNT(*) AS cnt FROM prescriptions WHERE patient_id = %s AND active = 1",
        (pid,),
    )
    if med_rows[0]["cnt"] == 0:
        gaps.append("No active medications documented")

    # Check vitals
    vit_rows = _run(
        trace_id, "get_data_gaps:vitals", {"pid": pid},
        "SELECT COUNT(*) AS cnt FROM form_vitals WHERE pid = %s",
        (pid,),
    )
    if vit_rows[0]["cnt"] == 0:
        gaps.append("No vitals on record")

    # Check allergies (lists table with type='allergy')
    allergy_rows = _run(
        trace_id, "get_data_gaps:allergies", {"pid": pid},
        "SELECT COUNT(*) AS cnt FROM lists WHERE pid = %s AND type = 'allergy' AND activity = 1",
        (pid,),
    )
    if allergy_rows[0]["cnt"] == 0:
        gaps.append("No allergy documentation — NKDA not confirmed")

    # Check problem list
    problem_rows = _run(
        trace_id, "get_data_gaps:problems", {"pid": pid},
        "SELECT COUNT(*) AS cnt FROM lists WHERE pid = %s AND type = 'medical_problem' AND activity = 1",
        (pid,),
    )
    if problem_rows[0]["cnt"] == 0:
        gaps.append("No active problem list")

    return {
        "gap_count": len(gaps),
        "gaps": gaps if gaps else ["No critical gaps identified"],
        "source": "patient_data, form_encounter, prescriptions, form_vitals, lists tables",
    }


# ---------------------------------------------------------------------------
# Tool dispatcher — called by the agent loop
# ---------------------------------------------------------------------------

TOOL_MAP = {
    "get_patient_demographics": get_patient_demographics,
    "get_active_medications": get_active_medications,
    "get_recent_encounters": get_recent_encounters,
    "get_vitals": get_vitals,
    "get_data_gaps": get_data_gaps,
}


def dispatch_tool(tool_name: str, tool_input: dict, pid: int, trace_id: str) -> Any:
    """Execute a tool call, enforcing that the pid matches the session patient."""
    if tool_name not in TOOL_MAP:
        raise ValueError(f"Unknown tool: {tool_name}")

    # Enforce patient scoping — ignore any pid in tool_input, always use session pid
    fn = TOOL_MAP[tool_name]
    kwargs = {"pid": pid, "trace_id": trace_id}
    if tool_name == "get_recent_encounters" and "limit" in tool_input:
        kwargs["limit"] = tool_input["limit"]

    return fn(**kwargs)
