"""
Clinical Co-Pilot Evaluation Suite

Runs all test cases against the live Co-Pilot service and reports pass/fail.

Usage:
    python eval/run_evals.py                          # run all suites
    python eval/run_evals.py --suite happy_path       # one suite
    python eval/run_evals.py --url http://localhost:8400 --secret mysecret

Each test case checks:
  - must_contain:     all these strings appear in the response (case-insensitive)
  - must_not_contain: none of these strings appear in the response
  - must_cite_source: response includes "(source:" attribution

Results are printed to stdout and written to eval/results/latest.json.
"""
import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Run Co-Pilot eval suite")
    p.add_argument("--url", default="http://localhost:8400", help="Co-Pilot service base URL")
    p.add_argument("--secret", default=os.environ.get("COPILOT_SECRET", "dev-secret-change-in-production"))
    p.add_argument("--suite", default=None, help="Run only this suite (happy_path|edge_cases|security)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def send_chat(base_url: str, secret: str, session_id: str, pid: int, question: str) -> str:
    """Send a chat request and collect the full streamed response."""
    import urllib.request
    payload = json.dumps({"session_id": session_id, "pid": pid, "question": question}).encode()
    req = urllib.request.Request(
        f"{base_url}/chat",
        data=payload,
        headers={"Content-Type": "application/json", "X-Copilot-Secret": secret},
        method="POST",
    )
    response_text = ""
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw_line in resp:
                # rstrip only newline chars — preserve trailing spaces (they separate words)
                line = raw_line.decode().rstrip('\r\n')
                if line.startswith("data: token:"):
                    response_text += line[len("data: token:"):]
                elif line.rstrip() == "data: done":
                    break
                elif line.startswith("data: error:"):
                    return f"ERROR: {line[len('data: error:'):]}"
    except Exception as e:
        return f"ERROR: {e}"
    return response_text


def run_case(case: dict, base_url: str, secret: str, verbose: bool) -> dict:
    session_id = f"eval_{uuid.uuid4().hex[:8]}"
    pid = case["pid"]
    question = case["question"]

    t0 = time.perf_counter()
    response = send_chat(base_url, secret, session_id, pid, question)
    duration_ms = (time.perf_counter() - t0) * 1000

    # Multi-turn followup
    if "followup" in case and not response.startswith("ERROR"):
        response2 = send_chat(base_url, secret, session_id, pid, case["followup"])
        response = response + "\n\n[FOLLOWUP]\n" + response2

    failures = []
    response_lower = response.lower()

    # Check must_contain
    for term in case.get("must_contain", []):
        if term.lower() not in response_lower:
            failures.append(f"missing expected term: '{term}'")

    # Check must_not_contain
    for term in case.get("must_not_contain", []):
        if term.lower() in response_lower:
            failures.append(f"contains prohibited term: '{term}'")

    # Check source citation — accept any form of "source:" attribution
    if case.get("must_cite_source") and "source:" not in response_lower:
        failures.append("no source attribution found")

    passed = len(failures) == 0 and not response.startswith("ERROR")

    result = {
        "id": case["id"],
        "description": case["description"],
        "pid": pid,
        "passed": passed,
        "failures": failures,
        "duration_ms": round(duration_ms),
        "response_length": len(response),
    }
    if verbose or not passed:
        result["response_preview"] = response[:400]

    return result


def run_suite(suite_name: str, base_url: str, secret: str, verbose: bool) -> dict:
    cases_path = Path(__file__).parent / "cases" / f"{suite_name}.json"
    if not cases_path.exists():
        print(f"  Suite file not found: {cases_path}")
        return {"suite": suite_name, "results": [], "passed": 0, "failed": 0}

    with open(cases_path) as f:
        cases = json.load(f)

    results = []
    for case in cases:
        print(f"  [{case['id']}] {case['description'][:60]}...", end=" ", flush=True)
        result = run_case(case, base_url, secret, verbose)
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"{status} ({result['duration_ms']}ms)")
        if not result["passed"]:
            for f in result["failures"]:
                print(f"       → {f}")
        results.append(result)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    return {"suite": suite_name, "results": results, "passed": passed, "failed": failed}


def main():
    args = parse_args()

    # Verify service is up
    import urllib.request
    try:
        with urllib.request.urlopen(f"{args.url}/health", timeout=5) as r:
            health = json.loads(r.read())
            print(f"✓ Co-Pilot service is up | demo_mode={health.get('demo_mode')}\n")
    except Exception as e:
        print(f"✗ Cannot reach Co-Pilot service at {args.url}: {e}")
        print("  Start it with: docker compose up -d copilot-service")
        sys.exit(1)

    suites = ["happy_path", "edge_cases", "security"]
    if args.suite:
        suites = [args.suite]

    all_results = []
    total_passed = total_failed = 0

    for suite_name in suites:
        print(f"\n{'='*60}")
        print(f"Suite: {suite_name.upper()}")
        print('='*60)
        suite_result = run_suite(suite_name, args.url, args.secret, args.verbose)
        all_results.append(suite_result)
        total_passed += suite_result["passed"]
        total_failed += suite_result["failed"]
        print(f"  → {suite_result['passed']} passed, {suite_result['failed']} failed")

    print(f"\n{'='*60}")
    print(f"TOTAL: {total_passed} passed, {total_failed} failed")
    print('='*60)

    # Write results (use /tmp if the eval dir is read-only)
    results_dir = Path(__file__).parent / "results"
    try:
        results_dir.mkdir(exist_ok=True)
    except PermissionError:
        results_dir = Path("/tmp/eval_results")
        results_dir.mkdir(exist_ok=True)
    out_path = results_dir / "latest.json"
    with open(out_path, "w") as f:
        json.dump({
            "run_at": datetime.utcnow().isoformat() + "Z",
            "service_url": args.url,
            "suites": all_results,
            "total_passed": total_passed,
            "total_failed": total_failed,
        }, f, indent=2)
    print(f"\nResults written to {out_path}")

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
