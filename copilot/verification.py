"""
Verification layer for Clinical Co-Pilot responses.

Two checks run on every agent response before it reaches the physician:

1. DOMAIN CONSTRAINT ENFORCEMENT
   Rule-based scan for prohibited response patterns:
   - Diagnostic conclusions presented as fact
   - Treatment recommendations or prescribing suggestions
   - Medication changes (increase/decrease/stop/start)
   - Prognosis statements

2. SOURCE ATTRIBUTION CHECK
   Structural check that the response does not contain clinical claims
   that were not present in the tool results retrieved during this request.
   This is a keyword-match heuristic — not exhaustive, but catches the
   most common hallucination pattern: numeric values (lab results, doses,
   vitals) that appear in the response but not in the tool results.

The verification result is logged for every request. If violations are found,
the response is NOT blocked (to avoid breaking the physician's workflow) but
IS annotated with a visible warning, and the violation is logged for review.

Known limitations:
- Does not catch hallucinated qualitative statements (e.g., fabricated history)
- Does not verify drug interaction claims
- Source attribution check is heuristic, not semantic

These limitations are documented intentionally. A second LLM verification pass
would improve semantic coverage but adds ~1-2s latency — deferred to Phase 2.
"""
import re
from typing import NamedTuple

from observability import log_verification


class VerificationResult(NamedTuple):
    passed: bool
    violations: list[str]
    annotated_response: str


# Patterns that indicate the agent has overstepped its role
PROHIBITED_PATTERNS = [
    (r"\byou should\b", "directive language ('you should')"),
    (r"\bI recommend\b", "recommendation language ('I recommend')"),
    (r"\bI suggest\b", "suggestion language ('I suggest')"),
    (r"\bconsider (?:increasing|decreasing|stopping|starting|adding|changing)\b",
     "medication change suggestion"),
    (r"\b(?:increase|decrease|titrate|uptitrate|discontinue)\s+(?:the\s+)?(?:dose|dosage|medication)\b",
     "dose adjustment directive"),
    (r"\blikely (?:has|have|is|are)\b.{0,40}(?:diagnosis|condition|disease)",
     "diagnostic conclusion"),
    (r"\bdiagnosis (?:is|appears to be)\b", "diagnosis statement"),
    (r"\bprognosis\b", "prognosis statement"),
    (r"\bprescribe\b", "prescribing directive"),
    (r"\border (?:a |an )?(?:lab|test|imaging|scan|x-ray|CT|MRI)\b",
     "ordering directive"),
]

# Numbers that appear in the response should be traceable to tool results
# We extract numeric values from tool results and check coverage
NUMBER_PATTERN = re.compile(r'\b(\d+(?:\.\d+)?)\s*(?:mg|mcg|mmHg|bpm|lbs|kg|%|mmol|mEq)\b')


def _extract_numbers_with_units(text: str) -> set[str]:
    return set(m.group(0).lower() for m in NUMBER_PATTERN.finditer(text))


def verify(
    response: str,
    tool_results: list[dict],
    trace_id: str,
) -> VerificationResult:
    violations = []

    # --- Check 1: Domain constraint enforcement ---
    response_lower = response.lower()
    for pattern, label in PROHIBITED_PATTERNS:
        if re.search(pattern, response_lower, re.IGNORECASE):
            violations.append(f"Prohibited pattern detected: {label}")

    # --- Check 2: Numeric source attribution ---
    # Flatten all tool results to a single string for comparison
    tool_text = " ".join(str(v) for result in tool_results for v in _flatten(result))

    response_numbers = _extract_numbers_with_units(response)
    tool_numbers = _extract_numbers_with_units(tool_text)

    unsourced = response_numbers - tool_numbers
    if unsourced:
        violations.append(
            f"Numeric values in response not found in tool results: {unsourced}. "
            "Possible hallucination — verify against chart."
        )

    passed = len(violations) == 0
    log_verification(trace_id, passed, violations)

    if not passed:
        warning = (
            "\n\n---\n⚠️ **Verification note:** This response was flagged during "
            "automated review. Please verify the highlighted information directly "
            f"in the chart. Flags: {'; '.join(violations)}"
        )
        return VerificationResult(False, violations, response + warning)

    return VerificationResult(True, [], response)


def _flatten(obj, depth=0) -> list:
    """Recursively flatten a dict/list to its string values."""
    if depth > 5:
        return [str(obj)]
    if isinstance(obj, dict):
        result = []
        for v in obj.values():
            result.extend(_flatten(v, depth + 1))
        return result
    if isinstance(obj, (list, tuple)):
        result = []
        for item in obj:
            result.extend(_flatten(item, depth + 1))
        return result
    return [str(obj)] if obj is not None else []
