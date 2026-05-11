# Week 2 Architecture — Clinical Co-Pilot

## Overview

The Week 2 build extends the Week 1 agent with multimodal document ingestion,
a hybrid RAG retriever, an inspectable LangGraph worker graph, a 51-case eval
gate, and end-to-end observability. Every clinical claim in the UI traces back
to a pixel region in a source document or a chunk in the guideline corpus.

---

## 1. Document Ingestion Flow

```
Browser upload
     │
     ▼
POST /v2/ingest  (FastAPI — main.py)
     │
     ▼
attach_and_extract(patient_id, file, doc_type)   ← ingest.py
     │
     ├── Rasterize PDF to 300 DPI PNG pages       ← render.py / PyMuPDF
     │
     ├── Claude Vision (claude-sonnet-4-6)
     │     prompt: structured JSON extraction with bbox coordinates
     │     output: raw dict with fields + bounding boxes
     │
     ├── Pydantic validation                      ← schemas.py
     │     LabResult: test_name, value, unit, reference_range,
     │                collection_date, abnormal_flag, source_citation
     │     IntakeForm: demographics, chief_concern, medications,
     │                 allergies, family_history, source_citation
     │
     ├── FHIR write (gated by COPILOT_DEMO_MODE)  ← ingest.py
     │     Observation resource for lab results
     │     Condition / AllergyIntolerance for intake fields
     │
     └── Overlay render                           ← render.py
           Draw bbox rectangles on rasterized pages
           Persist annotated PNGs + overlay_metadata.json
           Served at GET /v2/overlay/{doc_id}/{page}
```

**Supported document types:** `lab_pdf`, `intake_form` (core); `hl7_oru`,
`fax_tiff`, `xlsx_labs` (extension, deterministic parsers — no Vision).

**Citation shape** (all five required fields populated for every extracted fact):

```json
{
  "source_type": "lab_pdf",
  "source_id": "sha256-prefix-of-file",
  "page_or_section": "page 1",
  "field_or_chunk_id": "LDL-C_p1",
  "quote_or_value": "LDL-C: 142 mg/dL"
}
```

---

## 2. Worker Graph (LangGraph)

```
         ┌─────────────┐
  query ─►  supervisor  ◄──────────────────────┐
         └──────┬──────┘                        │
                │  routes to:                   │
        ┌───────┴────────┐                      │
        ▼                ▼                      │
 intake_extractor  evidence_retriever           │
        │                │                      │
        └───────┬─────────┘                     │
                │  handoff back                 │
                └───────────────────────────────┘
                         │ stop_reason == end
                         ▼
                   final_answer
```

**Supervisor** (`graph.py:62`) inspects the query for extraction vs. retrieval
signals and sets `next_node`. It logs every handoff with timestamp, from/to
node, routing reason, and input summary.

**intake-extractor worker** (`graph.py:115`) calls `attach_and_extract` if a
file is attached, or returns cached extraction results. Returns structured JSON
conforming to `LabResult` or `IntakeForm`.

**evidence-retriever worker** (`graph.py:140`) calls `search_guidelines` on the
hybrid retriever and returns ranked evidence chunks with citations.

Handoffs are recorded in `GraphState["handoffs"]` and returned in the API
response — visible in the UI status updates and in `/logs`.

---

## 3. Hybrid RAG Design

```
query
  │
  ├── BM25 sparse retrieval (rank-bm25)
  │     tokenized in-memory index over ChromaDB documents
  │     returns top CANDIDATE_K/2 = 10 candidates
  │
  ├── Dense vector retrieval (ChromaDB, cosine similarity)
  │     all-MiniLM-L6-v2 embeddings (pre-baked in Docker image)
  │     returns top CANDIDATE_K/2 = 10 candidates
  │
  ├── Merge + deduplicate by chunk_id
  │
  ├── Cohere Rerank (rerank-english-v3.0)
  │     scores all merged candidates, returns top RERANK_TOP_N = 3
  │
  └── Top 3 chunks fed to answer model with citation metadata
```

**Corpus:** ADA 2024 Standards of Care, JNC8 hypertension guidelines, USPSTF
preventive care recommendations — 3 indexed documents, chunked at 200 words
with 40-word overlap.

**Fallback:** If Cohere key is absent, reranking falls back to score-sorted
dense results. BM25 handles zero-shot queries where dense embeddings underfit.

---

## 4. Eval Gate

```
evals/
├── cases.py          — 51 golden EvalCase objects
├── rubrics.py        — 5 boolean rubric functions (rule-based)
├── llm_judge.py      — LLM-as-judge (claude-haiku-4-5-20251001, temp=0)
├── test_eval.py      — per-case tests + regression gate
├── test_llm_judge.py — judge prompt documentation + stub-key tests
├── test_hl7.py       — HL7v2 deterministic parser tests
├── test_coords.py    — bbox coordinate transform tests
├── conftest.py       — writes results.json on every run
└── results.json      — committed artifact (148 passed, 0 failed)
```

**Rubric categories:** `schema_valid`, `citation_present`,
`factually_consistent`, `safe_refusal`, `no_phi_in_logs`.

**CI hard gate** (`test_regression_gate`): each rubric must score ≥ 90% across
all relevant cases. A regression of more than 5% in any single category causes
the workflow to exit non-zero and block the PR.

**LLM judge:** `llm_factual_consistency()` calls claude-haiku-4-5-20251001 at
temperature 0. Full system prompt is documented in `evals/llm_judge.py`. Live
tests skip automatically when no real API key is present; two structural checks
always run in CI.

---

## 5. Observability

Every request produces a structured JSONL trace at `LOG_FILE`. Fields per event:

| Event | Key fields |
|---|---|
| `request_start` | trace_id, pid, question_preview, turn |
| `llm_call` | model, input_tokens, output_tokens, cost_usd, duration_ms |
| `tool_call` | tool, args (pid only, no names), row_count, duration_ms |
| `graph_handoff` | from_node, to_node, reason, input_summary |
| `extraction` | doc_id, doc_type, field_count, bbox_count, duration_ms |
| `verification_result` | passed, violations |
| `request_complete` | total_ms, status |

PHI redaction: patient names, DOBs, MRNs, and SSNs are stripped at the
ingestion boundary. Tool call args log only `pid` (integer), never the resolved
name or demographics. The `no_phi_in_logs` rubric in CI enforces this contract.

---

## 6. Risks and Tradeoffs

**Vision extraction latency (p95 ≈ 22 s):** Claude Vision on a 2-page PDF at
300 DPI takes 18–22 seconds. This is acceptable for async document upload but
would block a synchronous consultation flow. Mitigation: the UI shows a
streaming status indicator; the extracted result persists so re-queries are
instant.

**Corpus size:** The three-document corpus is intentionally narrow. Larger
corpora improve recall but increase reranking latency and cost. The hybrid
approach (BM25 + dense) handles the small corpus well — BM25 recovers
keyword-exact matches that dense embeddings miss at this scale.

**Demo mode FHIR gate:** FHIR writes are gated by `COPILOT_DEMO_MODE=true` to
prevent accidental writes to the live OpenEMR database during development. Set
`COPILOT_DEMO_MODE=false` and restart the copilot service to enable the full
round-trip. The health endpoint confirms the current mode.

**Single-node graph:** The LangGraph graph is deliberately flat — one supervisor
and two workers. A critic node that rejects uncited claims is the natural next
extension but was scoped out of the Week 2 core to keep the graph legible and
the eval gate focused.

**Cost at scale:** At the observed $0.012 average per LLM call and 3 LLM calls
per chat turn, a 100-provider deployment doing 20 consultations/day would cost
approximately $72/day in inference alone. Caching repeated guideline retrievals
and batching extraction would reduce this by an estimated 40–60%.
