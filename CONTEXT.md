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

## Week 2 New Surface Area
All new code lives in copilot-service unless noted.

### 1. Document Ingestion (attach_and_extract)
- Tool: attach_and_extract(patient_id, file_path, doc_type)
- doc_type: "lab_pdf" | "intake_form"
- Flow: receive file → call Claude vision API → validate against Pydantic schema
  → write FHIR resources to OpenEMR → return structured JSON with citations
- Patient data NEVER enters vector DB. FHIR only.

### 2. Pydantic Schemas
LabResult: test_name, value, unit, reference_range, collection_date,
           abnormal_flag, source_citation
IntakeForm: demographics, chief_concern, medications, allergies,
            family_history, source_citation
Citation:   source_type, source_id, page_or_section, field_or_chunk_id,
            quote_or_value, bbox (Optional — x0, y0, x1, y1, page — do not
            implement overlay at MVP but include the field)

### 3. Hybrid RAG (guideline corpus only)
- Index: ChromaDB (local, persistent volume on droplet)
- Retrieval: BM25 (sparse) + embeddings (dense) → Cohere Rerank (free tier)
- Corpus: 3 curated guideline documents (see Corpus section)
- Feed only top-3 reranked chunks to answer model
- Patient data NEVER enters this index

### 4. LangGraph Supervisor + 2 Workers
- supervisor: reads query, routes to worker(s), assembles final answer
- intake-extractor: calls attach_and_extract(), returns structured facts
- evidence-retriever: calls RAG retriever, returns cited guideline snippets
- All handoffs logged as structured dicts:
  {timestamp, from_node, to_node, reason, input_summary}

### 5. Eval Gate (MVP: 10 cases — expand to 50 by Thursday)
- Boolean rubrics: schema_valid, citation_present, safe_refusal
- Pytest runner
- Cases built around demo patients

## Corpus (MVP — 3 docs, section-level chunks only)
1. ADA Standards of Care 2024 — recommendations/summary sections
   https://diabetesjournals.org/care/issue/47/Supplement_1
   Relevant to: Ted Shaw (T2DM, HbA1c)
2. JNC 8 Hypertension Guidelines — Tables 1-5 only (JAMA 2014, public)
   Relevant to: Ted Shaw, Jim Moses (HTN)
3. USPSTF Recommendations Summary Table
   https://www.uspreventiveservicestaskforce.org/uspstf/recommendation-topics
   Relevant to: broad intake flag coverage across all patients

## Hard Constraints
- No raw PHI in logs
- No patient data in vector DB — FHIR only
- Every clinical claim must carry citation shape above (including optional bbox)
- COPILOT_DEMO_MODE must remain respected
- MVP only — do not build: critic agent, PDF bounding box overlay,
  third doc type, lab trend chart, PR-blocking CI, cost/latency report,
  demo video

## Environment Variables Needed (Week 2 additions)
COHERE_API_KEY          # free tier at cohere.com
CHROMA_PERSIST_DIR      # local path for ChromaDB persistent storage
