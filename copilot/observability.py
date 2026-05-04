"""
Observability for the Clinical Co-Pilot service.

Every request gets a trace_id. Structured JSON log lines are written for:
  - request_start       : who asked what, for which patient
  - tool_call           : tool name, args, duration_ms, row_count
  - tool_error          : tool name, error message
  - llm_call            : model, input_tokens, output_tokens, cost_usd, duration_ms
  - verification_result : passed/failed, violations list
  - request_complete    : total duration_ms, final status

All lines share the same trace_id so they can be correlated in any log viewer.
"""
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from config import LOG_FILE, COST_PER_INPUT_TOKEN, COST_PER_OUTPUT_TOKEN


def _ensure_log_dir():
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)


def _write(record: dict):
    _ensure_log_dir()
    record["ts"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        # Never let observability failures break the request
        pass


def new_trace() -> str:
    return str(uuid.uuid4())


def log_request_start(trace_id: str, pid: int, question: str, turn: int):
    _write({
        "event": "request_start",
        "trace_id": trace_id,
        "pid": pid,
        "question_preview": question[:120],
        "turn": turn,
    })


def log_tool_call(trace_id: str, tool_name: str, args: dict,
                  duration_ms: float, row_count: int):
    _write({
        "event": "tool_call",
        "trace_id": trace_id,
        "tool": tool_name,
        "args": args,
        "duration_ms": round(duration_ms, 1),
        "row_count": row_count,
    })


def log_tool_error(trace_id: str, tool_name: str, error: str):
    _write({
        "event": "tool_error",
        "trace_id": trace_id,
        "tool": tool_name,
        "error": error,
    })


def log_llm_call(trace_id: str, model: str,
                 input_tokens: int, output_tokens: int, duration_ms: float):
    cost = (input_tokens * COST_PER_INPUT_TOKEN) + (output_tokens * COST_PER_OUTPUT_TOKEN)
    _write({
        "event": "llm_call",
        "trace_id": trace_id,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "duration_ms": round(duration_ms, 1),
    })


def log_verification(trace_id: str, passed: bool, violations: list[str]):
    _write({
        "event": "verification_result",
        "trace_id": trace_id,
        "passed": passed,
        "violations": violations,
    })


def log_request_complete(trace_id: str, total_ms: float, status: str):
    _write({
        "event": "request_complete",
        "trace_id": trace_id,
        "total_ms": round(total_ms, 1),
        "status": status,
    })


@contextmanager
def timer():
    """Context manager that yields a dict with a 'ms' key set on exit."""
    result = {}
    t0 = time.perf_counter()
    try:
        yield result
    finally:
        result["ms"] = (time.perf_counter() - t0) * 1000
