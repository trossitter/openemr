# Clinical Co-Pilot — Week 2 Context

## Repo & Deployment
- GitHub: https://github.com/trossitter/openemr
- Live: https://clinicalcopilot.org (admin / pass)
- Stack: Docker Compose on DigitalOcean (2vCPU/4GB), Ubuntu 22.04
- Services: openemr container (Apache/PHP), copilot-service (FastAPI/Python), mariadb

## Week 1 Baseline
- copilot-service: FastAPI app, internal only, communicates via OpenEMR REST API
- Patient data access: OpenEMR REST API (read-only, scoped) — never direct DB
- Claude API: streaming via SSE, zero-retention, COPILOT_DEMO_MODE flag gates PHI
- Demo patients: Ted Shaw (HTN/T2DM), Eduardo Perez (COPD), Farrah Rolle (OB),
  Nora Cohen (Anxiety/Migraine), Jim Moses (post-MI) — use these for evals

---

## Week 2 Assignment (Authoritative)

### Scenario
A primary care physician preps for a follow-up visit. Structured OpenEMR data exists but
important recent information is buried in a scanned lab PDF and a patient intake form uploaded
by the front desk. The physician asks: What changed, what should I pay attention to, and what
evidence supports the recommendation?

The Week 2 agent must ingest the lab PDF and intake form, extract structured facts with
citations, retrieve relevant guideline evidence, and return a grounded answer — useful even
when the scan is imperfect, the patient record is incomplete, or the user asks a follow-up.

### Hard Problems
- **Vision extraction without invention** — VLM can hallucinate; schema + source links +
  verification must make unsupported facts visible.
- **Evidence grounding** — every answer must separate patient-record facts from guideline
  evidence. A medication or lab claim is not acceptable without a traceable source.
- **Multi-agent architecture** — multiple workers with clear responsibilities; supervisor routing
  decisions must be inspectable.
- **Eval-driven development** — 50-case golden set, boolean rubrics, CI gate catches
  regressions.
- **FHIR and OpenEMR integrity** — documents and derived observations must round-trip
  without duplicates or untraceable records.
- **HIPAA-minded development** — demo/synthetic data only; no raw PHI in logs, prompts,
  extracted fields, traces, or screenshots.

---

## Project Schedule (Central time)
| Checkpoint | Deadline | Focus |
|---|---|---|
| Architecture Defense | 4 hours | Document schemas, RAG and eval design, security concerns |
| MVP | Tuesday @ 11:59PM | Lab PDF + intake form ingestion working locally; first extraction + first evidence retrieval demo |
| Early Submission | Thursday @ 11:59PM | Supervisor + 2 workers, 50-case eval suite, PR-blocking CI, deployed app, demo video |
| Final | Sunday @ Noon | Production-ready agent, source-grounded demo, cost/latency report, interview readiness |

---

## Core Deliverables (Graded)

### 1. Document Ingestion
- `attach_and_extract(patient_id, file_path, doc_type)` — supports `lab_pdf` and `intake_form`
- Store source document in OpenEMR
- Return strict-schema JSON
- Persist derived facts as FHIR Observation (lab) or Patient update (intake)
- Link every derived fact back to its source

### 2. Pydantic Schemas (strict)
**LabResult:** test_name, value, unit, reference_range, collection_date, abnormal_flag, source_citation

**IntakeForm:** demographics, chief_concern, medications, allergies, family_history, source_citation

**Citation:** source_type, source_id, page_or_section, field_or_chunk_id, quote_or_value, bbox (x0, y0, x1, y1, page)
- Note: per assignment text, a **visual PDF bounding-box overlay is required** (not MVP-optional)

### 3. Hybrid RAG + Rerank
- Index a small clinical-guideline corpus (keyword + vector retrieval)
- Rerank with Cohere Rerank (free tier) or equivalent
- Feed only top reranked chunks to answer model
- Return evidence snippets with source metadata

### 4. Supervisor + 2 Workers (LangGraph)
- **supervisor** — routes query, decides when extraction/retrieval/answer is ready
- **intake-extractor** — calls attach_and_extract(), returns structured facts
- **evidence-retriever** — calls RAG retriever, returns cited guideline snippets
- Handoffs logged as structured dicts: `{timestamp, from_node, to_node, reason, input_summary}`

### 5. Citation Contract
Every clinical claim in the final response must include machine-readable citation metadata.
Minimum shape: `{source_type, source_id, page_or_section, field_or_chunk_id, quote_or_value}`
Bounding-box overlay on the source PDF is required (not stretch).

### 6. Eval Gate (CI-blocking — HARD GATE)
- 50-case golden set (synthetic/demo patients)
- Boolean rubrics: `schema_valid`, `citation_present`, `factually_consistent`, `safe_refusal`, `no_phi_in_logs`
- PR-blocking Git Hook
- Build must fail if any category regresses >5% or drops below pass threshold
- **Graders will introduce a regression and confirm the gate fails. If it doesn't, Week 2 does not pass.**

### 7. Observability + Cost Tracking
Per-encounter logs must include: tool sequence, latency by step, token usage, cost estimate,
retrieval hits, extraction confidence, eval outcome. No raw PHI in logs.

---

## Extension Work (Not Core)
- Critic agent that rejects uncited claims or unsafe action suggestions
- Click-to-source UI for citation snippets with document preview
- Third document type (referral fax or medication list)
- Lab trend chart widget using extracted Observation data
- Contextual retrieval: better chunking, query rewriting, domain-specific filters

---

## Guideline Corpus (MVP — 3 docs)
1. **ADA Standards of Care 2024** — recommendations/summary sections
   (Relevant to: Ted Shaw — T2DM, HbA1c)
2. **JNC 8 Hypertension Guidelines** — Tables 1–5 only (JAMA 2014, public)
   (Relevant to: Ted Shaw, Jim Moses — HTN)
3. **USPSTF Recommendations Summary Table**
   (Relevant to: broad intake flag coverage across all patients)

---

## Hard Constraints
- No raw PHI in logs
- No patient data in vector DB — FHIR only
- Every clinical claim must carry citation shape (including bbox)
- COPILOT_DEMO_MODE must remain respected (gates PHI writes)
- Do NOT build: PR-blocking CI by skipping tests, cost/latency report shortcuts, demo video shortcuts

## Week 2 Environment Variables Needed
```
COHERE_API_KEY          # free tier at cohere.com
CHROMA_PERSIST_DIR      # local path for ChromaDB persistent storage
OPENEMR_BASE_URL        # e.g. http://openemr:80 (Docker internal)
OPENEMR_CLIENT_ID       # OAuth2 client for FHIR writes
OPENEMR_CLIENT_SECRET   # OAuth2 secret for FHIR writes
```
