# Clinical Co-Pilot — Week 2

AI agent embedded in OpenEMR. Extracts structured clinical data from uploaded
documents, retrieves evidence from a guideline corpus, and returns grounded
responses with machine-readable citations and a visual PDF bounding-box overlay.

**API:** `https://clinicalcopilot.org/copilot/`  
**Secret:** `copilot-prod-559a98e9a9a7d479dfb99e16`

---

## Walkthrough — one command

The fastest way to see everything is the demo script. It runs against the live
site, covers all 7 requirements, and opens the annotated overlay in Preview.

```bash
cd ~/openemr/copilot
python3 fixtures/make_fixtures.py   # generate synthetic test documents
./demo.sh
```

What the script demonstrates, in order:

| Step | What happens | Requirement |
|------|-------------|-------------|
| 0 | Health check | — |
| 1a | Lab PDF ingested, 8 LabResult objects returned with bbox citations | 1, 2, 5 |
| 1b | Annotated overlay PNG opened — each result cell boxed on source page | 5 |
| 1c | Intake form extracted — demographics, chief concern, meds, allergies | 1, 2 |
| 1d | HL7v2 ORU-R01 parsed deterministically — LOINC citations, no LLM call | 1, 2 |
| 2 | Clinical query — supervisor routes to evidence_retriever, cites JNC 8 | 3, 4 |
| 3 | Eval gate — 51 cases, 5 rubrics, all regression gates pass | 6 |
| 4 | Observability log — tool sequence, latency, token cost, PHI-safe | 7 |

---

## Manual curl reference

### Requirement 1 — Document ingestion

```bash
SECRET="copilot-prod-559a98e9a9a7d479dfb99e16"
BASE="https://clinicalcopilot.org/copilot"

# Lab PDF → list[LabResult] with Pydantic validation + FHIR Observation write
curl -X POST $BASE/v2/ingest \
  -H "X-Copilot-Secret: $SECRET" \
  -F "file=@fixtures/p01-chen-lipid-panel.pdf" \
  -F "doc_type=lab_pdf" -F "pid=1"

# Intake form → IntakeForm with demographics, medications, allergies
curl -X POST $BASE/v2/ingest \
  -H "X-Copilot-Secret: $SECRET" \
  -F "file=@fixtures/p01-chen-intake.pdf" \
  -F "doc_type=intake_form" -F "pid=1"

# TIFF fax packet (multi-page raster) → FaxPacket
curl -X POST $BASE/v2/ingest \
  -H "X-Copilot-Secret: $SECRET" \
  -F "file=@fixtures/tiff/p01-chen-fax-packet.tiff" \
  -F "doc_type=fax_packet" -F "pid=1"

# HL7v2 ORU-R01 → list[LabResult], LOINC citations, no Claude call
curl -X POST $BASE/v2/ingest \
  -H "X-Copilot-Secret: $SECRET" \
  -F "file=@fixtures/hl7v2/p01-chen-oru-r01.hl7" \
  -F "doc_type=hl7_oru" -F "pid=1"

# HL7v2 ADT-A08 → IntakeForm from PID + EVN + NK1 segments
curl -X POST $BASE/v2/ingest \
  -H "X-Copilot-Secret: $SECRET" \
  -F "file=@fixtures/hl7v2/p01-chen-adt-a08.hl7" \
  -F "doc_type=hl7_adt" -F "pid=1"
```

All five doc_types return `doc_id`, `extracted` (validated schema), and
`overlay_metadata`. PDF and TIFF types also return `preview_b64` (base64 PNG
of the first annotated page).

### Requirement 5 — Visual bbox overlay

The ingest response includes `doc_id`. Use it to fetch the annotated page:

```bash
DOC_ID=<doc_id from ingest response>

# Annotated PNG — each extracted value boxed at its exact source location
curl "$BASE/v2/overlay/$DOC_ID/0" \
  -H "X-Copilot-Secret: $SECRET" -o overlay.png && open overlay.png

# Machine-readable overlay metadata (coordinate space, page geometry, annotations)
curl "$BASE/v2/overlay/$DOC_ID/metadata" \
  -H "X-Copilot-Secret: $SECRET" | python3 -m json.tool
```

Coordinates are anchored to the 300-DPI rasterized image. For native-text PDFs,
bboxes are resolved via PyMuPDF word-cluster search (exact); for raster
documents (TIFF, scanned), Claude Vision estimates are used.

### Requirements 3 + 4 — Hybrid RAG + LangGraph routing

```bash
curl -X POST $BASE/v2/query \
  -H "Content-Type: application/json" \
  -H "X-Copilot-Secret: $SECRET" \
  -d '{
    "session_id": "grading",
    "pid": 1,
    "query": "What does JNC 8 recommend for blood pressure targets in diabetic patients?"
  }'
```

Response fields:

| Field | What it shows |
|---|---|
| `final_answer` | Grounded response with inline citations |
| `handoffs` | LangGraph supervisor → worker transitions with timestamps |
| `evidence_chunks_count` | Chunks retrieved from ADA 2024 / JNC 8 / USPSTF |

### Requirement 7 — Observability

```bash
curl "$BASE/logs?n=20" -H "X-Copilot-Secret: $SECRET" | python3 -m json.tool
```

Every encounter logs: tool sequence, latency by step, token usage, cost
estimate, retrieval hits, extraction confidence, and eval outcome. No raw PHI
appears in any log field.

---

## Eval gate

```bash
cd copilot
pip3 install -r requirements.txt pytest
python3 -m pytest evals/test_eval.py evals/test_hl7.py evals/test_coords.py -v
```

| Suite | Cases | Coverage |
|---|---|---|
| `test_eval.py` | 51 golden cases | schema_valid · citation_present · factually_consistent · safe_refusal · no_phi_in_logs |
| `test_hl7.py` | 58 unit tests | HL7v2 tokenizer · ORU-R01 · ADT-A08 · fixture integration |
| `test_coords.py` | 19 unit tests | coordinate transforms · round-trips · edge cases |

CI gate: `.github/workflows/copilot-eval-gate.yml` — PR-blocking, fails if any
rubric drops below 90% or regresses more than 5%.

**Hard gate test:** introduce a regression, confirm CI fails before merging.

---

## Architecture

| File | Role |
|------|------|
| `schemas.py` | Pydantic v2 — LabResult, IntakeForm, FaxPacket, Citation, BBox (with full provenance fields) |
| `coords.py` | Coordinate transforms — image_px_300dpi ↔ normalized ↔ pdf_pts, invertible, logged |
| `ingest.py` | Rasterize-first pipeline → Claude Vision → schema validation → bbox refinement → FHIR write |
| `render.py` | PyMuPDF rasterization + PIL overlay renderer → raw pages, annotated pages, OverlayMetadata |
| `hl7.py` | HL7v2 parser — ORU-R01 → LabResult[], ADT-A08 → IntakeForm, no external deps |
| `retriever.py` | BM25 + ChromaDB + Cohere rerank |
| `graph.py` | LangGraph supervisor + intake_extractor + evidence_retriever |
| `agent.py` | Tool-use agent loop with verification layer |
| `main.py` | FastAPI — /v2/ingest, /v2/query, /v2/overlay/{doc_id}/{page}, /chat (SSE), /logs |
| `observability.py` | Structured JSON logging — PHI-safe, per-trace |
| `corpus/` | ADA 2024, JNC 8, USPSTF guideline text |
| `fixtures/` | Synthetic test documents + HL7v2 fixtures + make_fixtures.py |
| `evals/` | 51-case golden set + rubric functions + coord tests + HL7 tests + CI gate |
