"""LLM-as-judge rubric: factual consistency scored by Claude Haiku.

Prompt design (documented for grading transparency):

  SYSTEM
  ------
  You are a strict medical-record auditor. Given structured lab data extracted
  from a clinical document and an agent answer, score whether the answer is
  factually consistent with the source data.

  Respond with JSON only (no markdown fences, no prose outside the JSON):
    {"score": 0 or 1, "reason": "one sentence"}

  Score 1 = answer is factually consistent (values and test names match source).
  Score 0 = answer contradicts or fabricates values not present in the source.

  Focus only on factual correctness of numeric values, test names, and units.
  Ignore hedging language and clinical recommendations.

  USER
  ----
  SOURCE DATA:
  <extracted JSON>

  AGENT ANSWER:
  <answer text>

Model: claude-haiku-4-5-20251001
Temperature: 0  (deterministic)
Max tokens: 128
"""
from __future__ import annotations

import json
import os
import re

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are a strict medical-record auditor. Given structured lab data extracted "
    "from a clinical document and an agent answer, score whether the answer is "
    "factually consistent with the source data.\n\n"
    "Respond with JSON only (no markdown fences, no prose outside the JSON):\n"
    '{"score": 0 or 1, "reason": "one sentence"}\n\n'
    "Score 1 = answer is factually consistent (values and test names match source).\n"
    "Score 0 = answer contradicts or fabricates values not present in the source.\n\n"
    "Focus only on factual correctness of numeric values, test names, and units. "
    "Ignore hedging language and clinical recommendations."
)

_REAL_KEY_RE = re.compile(r"^sk-ant-")


def _has_real_key() -> bool:
    return bool(_REAL_KEY_RE.match(os.environ.get("ANTHROPIC_API_KEY", "")))


def llm_factual_consistency(answer: str, extracted: list[dict]) -> tuple[bool, str]:
    """LLM-scored factual consistency check.

    Returns (pass: bool, reason: str).
    Raises RuntimeError when ANTHROPIC_API_KEY is absent or a test stub —
    callers should catch this and skip gracefully in CI.
    """
    if not _has_real_key():
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set or is a test stub; skipping LLM judge."
        )

    import anthropic

    client = anthropic.Anthropic()
    user_content = (
        "SOURCE DATA:\n"
        + json.dumps(extracted, indent=2)
        + "\n\nAGENT ANSWER:\n"
        + answer
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=128,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip()
    try:
        result = json.loads(raw)
        score = int(result["score"])
        reason = str(result.get("reason", ""))
        return score == 1, reason
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise RuntimeError(
            f"LLM judge returned unparseable response: {raw!r}"
        ) from exc
