"""Pytest plugin: write evals/results.json after every test run.

The committed results.json makes eval scores reviewable without re-running CI.
Regenerate it locally with:

    cd copilot && python -m pytest evals/ -m "not llm" -q
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

_summary: dict[str, int] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
_cases: list[dict] = []


def pytest_runtest_logreport(report) -> None:
    if report.when != "call":
        return
    outcome: str = report.outcome
    _summary["total"] += 1
    _summary[outcome] = _summary.get(outcome, 0) + 1
    entry: dict = {
        "test_id": report.nodeid,
        "outcome": outcome,
        "duration_s": round(report.duration, 3),
    }
    if outcome == "failed":
        entry["message"] = str(report.longrepr)[:500]
    _cases.append(entry)


def pytest_sessionfinish(session, exitstatus) -> None:
    rubric_scores: dict[str, str] = {}
    for c in _cases:
        if "test_regression_gate[" in c["test_id"]:
            rubric = c["test_id"].split("[")[-1].rstrip("]")
            rubric_scores[rubric] = c["outcome"]

    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exit_code": int(exitstatus),
        "note": "Static rule-based evals — no live API calls required. LLM judge tests skipped (mark: llm).",
        "summary": _summary,
        "rubric_gate_outcomes": rubric_scores,
        "cases": _cases,
    }
    out = Path(__file__).parent / "results.json"
    out.write_text(json.dumps(report, indent=2))
