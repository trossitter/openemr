"""Tests for the LLM-as-judge factual consistency rubric.

Tests marked @pytest.mark.llm require a real ANTHROPIC_API_KEY (sk-ant-...) and
are automatically skipped in CI where only a stub key is present.

Run live:  ANTHROPIC_API_KEY=sk-ant-... python -m pytest evals/test_llm_judge.py -v
Run CI:    python -m pytest evals/test_llm_judge.py -m "not llm" -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from evals.llm_judge import MODEL, SYSTEM_PROMPT, _has_real_key, llm_factual_consistency

pytestmark = pytest.mark.llm

_skip_no_key = pytest.mark.skipif(
    not _has_real_key(),
    reason="No real ANTHROPIC_API_KEY — set sk-ant-... to run LLM judge tests",
)

_EXTRACTED_HBAIC = [
    {
        "test_name": "HbA1c",
        "value": "7.2",
        "unit": "%",
        "reference_range": "< 5.7% normal, 5.7–6.4% prediabetes, ≥ 6.5% diabetes",
        "collection_date": "2026-04-15",
        "abnormal_flag": True,
    }
]


@_skip_no_key
def test_llm_judge_passes_consistent_answer():
    """A correct answer citing the real extracted value should score 1."""
    answer = (
        "The patient's HbA1c is 7.2%, which is above the normal range "
        "and consistent with a diabetes diagnosis. (source: lab_pdf)"
    )
    passed, reason = llm_factual_consistency(answer, _EXTRACTED_HBAIC)
    assert passed, f"Expected PASS but LLM returned FAIL. Reason: {reason}"


@_skip_no_key
def test_llm_judge_fails_contradicting_answer():
    """An answer that states a wrong HbA1c value should score 0."""
    answer = (
        "The patient's HbA1c is 5.4%, which is within the normal range. "
        "No immediate intervention required."
    )
    passed, reason = llm_factual_consistency(answer, _EXTRACTED_HBAIC)
    assert not passed, (
        f"Expected FAIL (value 5.4 contradicts source 7.2) but LLM returned PASS. "
        f"Reason: {reason}"
    )


@_skip_no_key
def test_llm_judge_passes_empty_extracted():
    """With no source data, a guideline-only answer has nothing to contradict."""
    answer = (
        "ADA 2024 guidelines recommend HbA1c < 7% for most adults with diabetes. "
        "(source: ada_2024)"
    )
    passed, reason = llm_factual_consistency(answer, [])
    assert passed, (
        f"Expected PASS (no source data to contradict) but got FAIL. Reason: {reason}"
    )


# ---------------------------------------------------------------------------
# Tests that always run — no API key required
# ---------------------------------------------------------------------------

def test_llm_judge_raises_without_real_key(monkeypatch):
    """llm_factual_consistency must raise RuntimeError when key is a stub."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    with pytest.raises(RuntimeError, match="test stub"):
        llm_factual_consistency("some answer", [])


def test_llm_judge_prompt_and_model_documented():
    """Verify SYSTEM_PROMPT and MODEL are properly documented in llm_judge.py."""
    assert MODEL == "claude-haiku-4-5-20251001", f"Unexpected model: {MODEL}"
    assert "factually consistent" in SYSTEM_PROMPT.lower()
    assert '"score"' in SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) > 100, "SYSTEM_PROMPT looks truncated"
