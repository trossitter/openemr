# Clinical Co-Pilot — Week 2

AI agent embedded in OpenEMR. Two primary capabilities:

1. **Document ingestion** — upload a lab PDF or intake form, extract structured data with Claude Vision, validate against Pydantic schemas, import to patient chart
2. **Hybrid RAG** — physician asks a clinical question, agent searches ADA 2024 / JNC 8 / USPSTF corpus and returns a cited answer

Both return source citations in every response.

---

## Live demo

**API:** `https://clinicalcopilot.org/copilot/`
**Secret:** `copilot-prod-559a98e9a9a7d479dfb99e16`

### Requirement 1 — Document ingestion

```bash
# Lab PDF
curl -X POST https://clinicalcopilot.org/copilot/v2/ingest \
  -H "X-Copilot-Secret: copilot-prod-559a98e9a9a7d479dfb99e16" \
  -F "file=@p01-chen-lipid-panel.pdf" \
  -F "doc_type=lab_pdf" \
  -F "pid=1"

# Intake form
curl -X POST https://clinicalcopilot.org/copilot/v2/ingest \
  -H "X-Copilot-Secret: copilot-prod-559a98e9a9a7d479dfb99e16" \
  -F "file=@p01-chen-intake-typed.pdf" \
  -F "doc_type=intake_form" \
  -F "pid=1"
```

These were tested against the example documents provided with the assignment (`lab-results/` and `intake-forms/`). The grader can substitute any file from that set — all 8 files extract correctly.

### Requirement 2 — Hybrid RAG with citations

```bash
curl -X POST https://clinicalcopilot.org/copilot/v2/query \
  -H "Content-Type: application/json" \
  -H "X-Copilot-Secret: copilot-prod-559a98e9a9a7d479dfb99e16" \
  -d '{"session_id":"grading","pid":1,"query":"What does JNC 8 recommend for blood pressure targets in diabetic patients?"}'
```

Returns `final_answer` with inline citations, `handoffs` (logged supervisor → worker transitions), and `evidence_chunks_count`.

---

## Eval gate

```bash
cd copilot
pip install -r requirements.txt pytest
python -m pytest evals/test_eval.py -v
```

50 cases, 5 boolean rubrics. CI-blocking via `.github/workflows/copilot-eval-gate.yml`.
All 5 regression gates enforce ≥ 90% pass rate.

---

## Architecture

| File | Role |
|------|------|
| `schemas.py` | Pydantic v2 — LabResult, IntakeForm, Citation, BBox |
| `ingest.py` | Claude Vision extraction + FHIR chart import |
| `retriever.py` | BM25 + ChromaDB + Cohere rerank |
| `graph.py` | LangGraph supervisor + intake_extractor + evidence_retriever |
| `main.py` | FastAPI — /chat (SSE), /v2/query, /v2/ingest |
| `corpus/` | ADA 2024, JNC 8, USPSTF guideline text |
| `evals/` | 50-case golden set + 5 rubric functions + CI gate |
