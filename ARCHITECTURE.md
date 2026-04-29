# Clinical Co-Pilot — Architecture

**Document version:** 1.0  
**Date:** 2026-04-29  
**Status:** Pre-implementation roadmap  
**Source documents:** [AUDIT.md](./AUDIT.md), [USERS.md](./USERS.md)

---

## Executive Summary

The Clinical Co-Pilot is a physician-facing AI agent embedded in the OpenEMR encounter workflow. Its job is narrow and specific: when a physician opens a patient chart, the agent assembles that patient's relevant clinical context and surfaces it — before the physician has to ask. It also answers direct questions during the visit. The target user is a primary care physician with a 20-patient day and a 60-second window between clicking a patient's name and the patient walking in the door.

**The core architectural decision** is to run the Co-Pilot as a separate service rather than embedding logic inside OpenEMR's PHP application. A Co-Pilot service — a lightweight Python application running in its own Docker container — communicates with OpenEMR via its own REST API, assembles patient context, constructs a prompt, and streams a response from the Claude API back to the physician's browser. OpenEMR's existing PHP code is touched only to inject a JavaScript panel into the encounter view. This keeps the AI integration decoupled from OpenEMR's release cycle, independently deployable and testable, and written in a language with mature async and streaming primitives suited to LLM integration.

**How data flows:** When a physician opens an encounter, a JavaScript panel fires an async request to the Co-Pilot service, passing the patient ID and encounter ID. The service authenticates with OpenEMR using a scoped service-account token and calls the REST API to retrieve demographics, active medications, recent encounters with SOAP notes, and latest vitals — in parallel. It assembles this into a structured context block, constructs a prompt with the physician's question or the visit reason, and calls the Claude API with streaming enabled. The first token arrives at the physician's panel within two to three seconds of opening the chart.

**The three decisions that shape everything else:**

First, patient data is accessed through OpenEMR's own REST API, not directly from the database. This adds one network hop but preserves OpenEMR's authorization layer, creates a natural audit trail in OpenEMR's `api_log` table, and decouples the Co-Pilot from the database schema. Direct DB access would be faster but would bypass every access control and audit mechanism the system has.

Second, the Co-Pilot service is not exposed to the public internet. It runs bound to the Docker internal network. The browser communicates with it through a reverse proxy path on the OpenEMR container, meaning all Co-Pilot traffic inherits OpenEMR's existing session authentication. A physician who is not logged in to OpenEMR cannot reach the Co-Pilot.

Third, the system is designed as demo-data-only until a Business Associate Agreement is executed with Anthropic. This is not a preference — it is a HIPAA requirement. Sending PHI to the Claude API without a BAA constitutes an impermissible disclosure. The architecture is fully functional on synthetic data, and the transition to real patient data is a compliance step, not an engineering step.

**The primary tradeoff** accepted in this design is latency for correctness. Fetching patient context through the REST API rather than a single optimized SQL query adds 50–150ms to each assembly. That cost is invisible against a two-to-three second Claude API round-trip, but it is a real cost at scale. If the system grows to support concurrent users, the REST API path becomes a bottleneck before the database does. A caching layer between the Co-Pilot service and the OpenEMR API is the designed mitigation, not yet implemented.

---

## 1. System Architecture

### 1.1 Deployment Topology

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (Physician's workstation)                              │
│  ┌─────────────────────┐  ┌────────────────────────────────┐   │
│  │  OpenEMR Encounter  │  │  Co-Pilot Panel (JavaScript)   │   │
│  │  View (existing)    │  │  · Pre-visit briefing          │   │
│  │                     │  │  · Typed questions             │   │
│  │                     │  │  · Streaming response display  │   │
│  └─────────────────────┘  └────────────────────────────────┘   │
└──────────────────────┬──────────────────────┬───────────────────┘
                       │ HTTPS                │ HTTPS (SSE stream)
                       ▼                      ▼
           ┌───────────────────────────────────────────┐
           │  Cloudflare (DNS proxy, TLS termination)  │
           └───────────────────────────────────────────┘
                       │
                       ▼
           ┌───────────────────────────────────────────┐
           │  DigitalOcean Droplet (Ubuntu 22.04)       │
           │  2 vCPU / 4 GB RAM                         │
           │                                           │
           │  ┌─────────────────────────────────────┐  │
           │  │  Docker: openemr/openemr:8.0.0       │  │
           │  │  · Apache (ports 80, 443)            │  │
           │  │  · OpenEMR PHP application           │  │
           │  │  · /copilot/* → proxy to copilot svc │  │
           │  └──────────────────┬──────────────────┘  │
           │                     │ Docker network       │
           │  ┌──────────────────▼──────────────────┐  │
           │  │  Docker: copilot-service (new)        │  │
           │  │  · Python / FastAPI                  │  │
           │  │  · Internal port 8400                │  │
           │  │  · NOT exposed to public internet    │  │
           │  └───────────┬──────────────────────────┘  │
           │              │ Docker network               │
           │  ┌───────────▼──────────────────────────┐  │
           │  │  Docker: mariadb:11.8.6               │  │
           │  │  · InnoDB buffer pool: 1.5 GB         │  │
           │  │  · Internal only, no public port      │  │
           │  └──────────────────────────────────────┘  │
           └───────────────────────────────────────────┘
                                    │
                                    │ HTTPS (Claude API)
                                    ▼
                       ┌────────────────────────┐
                       │  Anthropic Claude API  │
                       │  (BAA required for PHI)│
                       └────────────────────────┘
```

### 1.2 New Components

| Component | Technology | Responsibility |
|---|---|---|
| `copilot-service` | Python 3.12, FastAPI | Context assembly, prompt construction, Claude API calls, streaming |
| Co-Pilot panel | Vanilla JS (injected via OpenEMR custom module) | UI rendering, SSE stream consumption, physician input |
| OpenEMR proxy path | Apache `ProxyPass` directive | Routes `/copilot/*` from OpenEMR to `copilot-service:8400` internally |
| OpenEMR REST API | Existing (enabled, scoped) | Patient data access layer |

### 1.3 What Is Not Changed

- OpenEMR's PHP application code (except one proxy directive and one module registration)
- The database schema
- The Cloudflare configuration
- The Docker network or volume structure

---

## 2. Data Access Architecture

### 2.1 Why the REST API, Not Direct Database Access

The audit identified that OpenEMR's clinical tables have no foreign key constraints and no centralized access control at the database layer. Any query issued directly to MariaDB bypasses every HIPAA technical safeguard the application provides: no audit logging, no role enforcement, no access controls. A physician account with read-only access in OpenEMR would offer no protection against a Co-Pilot service that queries the DB directly.

The REST API is the correct access layer because:
- Every call is logged to OpenEMR's `api_log` table (audit requirement)
- Scopes enforce what data types can be read
- The API is versioned and stable against minor schema changes
- Patient access is bound to UUIDs, not integer PIDs (prevents enumeration)

The tradeoff is latency: ~50–100ms per API call vs. ~1–5ms for a direct DB query. At one Claude API round-trip of 1,500–3,000ms, this cost is absorbed. At scale with caching, it becomes negligible.

### 2.2 Context Assembly Query Plan

For each Co-Pilot request, the service executes these calls **in parallel** against the OpenEMR REST API:

```
┌─ GET /api/patient/:puuid                           (demographics)
├─ GET /api/patient/:puuid/medication                (active meds)
├─ GET /api/patient/:puuid/encounter?limit=5         (recent encounters)
│    └─ [for most recent encounter]:
│         ├─ GET /api/.../encounter/:euuid/soap_note
│         └─ GET /api/.../encounter/:euuid/vital
└─ [assembled in < 300ms target]
```

SOAP notes and vitals for encounters beyond the most recent are included in the encounter payload. This limits total API calls to 4–5 regardless of chart depth.

**What is intentionally excluded from context:**
- Encounters older than 12 months (reducible in code if needed)
- Billing records
- Administrative notes unrelated to clinical care
- Documents (scanned records, imaging reports) — not yet parseable in v1

Exclusion is a deliberate design choice. Sending the full chart to Claude does not improve clinical usefulness — it increases prompt cost, increases latency, and gives the model more surface area on which to confabulate. The agent is useful because it is targeted, not because it is comprehensive.

### 2.3 Context Structure Passed to Claude

```json
{
  "patient": {
    "name": "Ted Shaw",
    "age": 79,
    "sex": "Male",
    "dob": "1947-03-11"
  },
  "visit": {
    "date": "2026-04-29",
    "reason": "Follow-up: hypertension and Type 2 diabetes",
    "encounter_id": "enc_1002"
  },
  "active_medications": [
    { "drug": "Lisinopril", "dose": "20mg", "route": "Oral", "indication": "Hypertension" },
    { "drug": "Metformin", "dose": "1000mg BID", "route": "Oral", "indication": "Type 2 Diabetes" },
    { "drug": "Amlodipine", "dose": "5mg", "route": "Oral", "indication": "Hypertension", "added": "2026-04-10" }
  ],
  "recent_encounters": [
    {
      "date": "2026-04-10",
      "reason": "Chest pain and shortness of breath",
      "soap": {
        "subjective": "...",
        "objective": "BP 162/100, HR 92, O2 sat 95%...",
        "assessment": "Atypical chest pain. Possible hypertensive urgency.",
        "plan": "EKG normal. Troponin x2 negative. Added amlodipine 5mg. Cardiology referral."
      },
      "vitals": { "bp_sys": 162, "bp_dia": 100, "hr": 92, "o2_sat": 95.0 }
    }
  ],
  "data_gaps": ["HbA1c ordered 2026-03-15 — result not in chart", "Cardiology referral status unknown"]
}
```

The `data_gaps` field is populated by the context assembly layer, not by Claude. The service identifies pending orders without results and flags them explicitly so the model can surface them without having to infer their absence.

---

## 3. Authorization Architecture

### 3.1 The Authorization Chain

```
Physician browser session
  → OpenEMR session cookie (validates physician is authenticated)
  → Apache proxy (passes session context to Co-Pilot service)
  → Co-Pilot service verifies session is valid before proceeding
  → Co-Pilot service uses its own scoped service-account token for REST API
  → REST API enforces patient UUID binding (no cross-patient access)
  → Claude API receives assembled context (no credentials)
```

### 3.2 Service Account Token

The Co-Pilot service authenticates to OpenEMR's REST API using a dedicated service account with the minimum required scopes:

| Scope | Purpose | Write? |
|---|---|---|
| `patient/Patient.read` | Demographics | No |
| `patient/Medication.read` | Active medications | No |
| `patient/Encounter.read` | Encounter list | No |
| `patient/Observation.read` | Vitals | No |

The service account has no write access. The Co-Pilot cannot create, modify, or delete any record. This is an architectural constraint, not a configuration — it is enforced by the scopes issued to the service token, not by trust in the Co-Pilot code.

### 3.3 Patient Binding

Every Co-Pilot request includes the patient UUID from the currently open chart. The Co-Pilot service passes this UUID directly to the OpenEMR REST API. OpenEMR's API layer validates that the requesting session has access to that specific patient. The Co-Pilot service cannot request data for a patient not currently open in the physician's session — it has no mechanism to enumerate patients.

### 3.4 What the Co-Pilot Cannot Do

This is as important as what it can do:

- Cannot write to any OpenEMR record
- Cannot access patients not currently open in the physician's session
- Cannot be reached from the public internet (Docker internal only)
- Cannot retain or log PHI beyond the immediate request/response cycle
- Cannot access the database directly
- Cannot impersonate a physician or act on their behalf

---

## 4. Claude API Integration

### 4.1 Model Selection

**Claude Sonnet 4.6** (`claude-sonnet-4-6`) is the target model for production.

| Consideration | Decision |
|---|---|
| Latency | Sonnet balances capability and speed; Opus is too slow for a 3-second UX target |
| Clinical reasoning | Sonnet is sufficient for context synthesis; this is retrieval + summarization, not diagnosis |
| Cost | Sonnet is ~5x cheaper than Opus per token — relevant at 20 visits/day × repeated queries |
| Context window | 200k tokens — more than sufficient for any patient chart in this system |

### 4.2 Prompt Architecture

The system prompt is fixed and defines the agent's role, constraints, and refusal policy. The user prompt is constructed per-request from the assembled patient context. They are kept strictly separate to prevent prompt injection from patient-controlled fields (e.g., free-text notes).

**System prompt (abridged):**
```
You are a Clinical Co-Pilot embedded in an outpatient primary care EHR.
Your role is to help physicians quickly orient to a patient's relevant
clinical context before and during a visit.

CONSTRAINTS — YOU MUST FOLLOW THESE WITHOUT EXCEPTION:
- Only use information explicitly present in the provided patient context.
  If information is not in the context, say "not documented in chart."
  Never infer, extrapolate, or draw on general medical knowledge to fill gaps.
- Never suggest, recommend, or imply a diagnosis, treatment, or clinical decision.
  You surface information. The physician decides.
- Always cite the source of each clinical fact (e.g., "per SOAP note, Apr 10").
- When data gaps are present in the context block, surface them explicitly.
- Never present your output as a substitute for a full chart review.

REFUSAL POLICY:
- If asked to provide medical advice, diagnose, or prescribe: decline and redirect.
- If asked about a patient not present in the context block: decline.
- If the context block is empty or malformed: surface the error, do not proceed.
```

**User prompt structure:**
```
PATIENT CONTEXT:
[structured JSON from context assembly, sanitized]

PHYSICIAN REQUEST:
[either: "Pre-visit briefing for today's visit" (UC1)
 or: the physician's typed question (UC3)]
```

### 4.3 Streaming

All Claude API calls use streaming (`stream=True`). The Co-Pilot service pipes the stream directly to the browser via Server-Sent Events. The physician sees the first tokens within 1.5–2 seconds of triggering the request. This is the primary UX lever — the Claude API latency cannot be reduced, but it can be made invisible through streaming.

### 4.4 PHI Handling at the API Layer

| Requirement | Implementation |
|---|---|
| Zero retention | Use Anthropic's zero-data-retention API option (requires enterprise tier) |
| No training on PHI | Confirmed by BAA terms — data not used for model training |
| Prompt logging | Prompts and responses logged to encrypted file on the Droplet only; not shipped to third parties |
| BAA prerequisite | System operates on demo data only until BAA is signed; enforced by environment flag `COPILOT_DEMO_MODE=true` |

---

## 5. Risk Register

### 5.1 Compliance Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Sending real PHI without Anthropic BAA | High (if rushed) | Critical — HIPAA violation | `COPILOT_DEMO_MODE` env flag blocks real patient data; must be explicitly disabled after BAA |
| DigitalOcean BAA not executed | Medium | High — PHI at rest on unprotected server | Execute before any real patient data is loaded |
| Physician screenshot of Co-Pilot panel | Low | Medium — PHI outside system | Cannot be prevented technically; addressed in user policy |
| Anthropic model training on PHI | Low (with BAA) | High | Zero-retention API + BAA terms |

### 5.2 Security Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Default credentials compromised | High (currently) | Critical | Change immediately; create physician accounts |
| Session token harvested from Apache logs | Medium | High | Apache log sanitization (strip Referer headers containing tokens) |
| Prompt injection via patient free-text | Medium | Medium | System/user prompt separation; patient content passed as data, not instructions |
| Co-Pilot service container breakout | Low | High | Service runs as non-root; no host volume mounts; no capabilities |
| Anthropic API key exposed | Medium | High | Stored as Docker secret, not environment variable; rotated quarterly |

### 5.3 Clinical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Model hallucinates clinical fact | Medium | Critical | Strict system prompt grounding; source citation required; clear "AI-generated" labeling |
| Physician over-relies on Co-Pilot briefing | Medium | High | UI design: panel is supplementary, chart review remains primary; explicit disclaimer |
| Stale context (data changed between assembly and display) | Low | Medium | Context includes assembly timestamp; physician prompted to refresh if > 5 min old |
| Missing allergy data causes drug suggestion to appear safe | Medium | High | Co-Pilot will not suggest medications; allergy gap surfaced explicitly in context block |

### 5.4 Performance Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Claude API latency spike | Medium | Medium (UX) | Streaming makes latency invisible; 10s timeout with graceful degradation |
| MariaDB query slow under load | Low (current scale) | Medium | Indexes in place; buffer pool tuned; slow query log active for monitoring |
| OpenEMR REST API rate limit | Low | Medium | No rate limit currently configured — add before multi-user deployment |
| Context assembly exceeds 300ms | Low | Low | Parallel API calls; 5-minute cache on patient context keyed by pid+encounter_date |

---

## 6. Implementation Roadmap

### Phase 1 — Foundation (Early Submission)

These are the minimum pieces required for a working demonstration.

| Task | Description | File / Location |
|---|---|---|
| Enable OpenEMR REST API | Set `rest_api=1` in globals; create service account with read scopes | OpenEMR admin UI |
| `copilot/` service directory | FastAPI app, Dockerfile, requirements.txt | `copilot/` |
| Context assembly endpoint | `POST /copilot/context` — calls OpenEMR API in parallel, returns structured JSON | `copilot/main.py` |
| Claude API integration | Streaming chat endpoint `POST /copilot/ask` | `copilot/main.py` |
| OpenEMR proxy directive | Route `/copilot/*` to internal service | OpenEMR Apache config |
| Co-Pilot panel JS module | Inject sidebar panel into encounter view on chart open | `interface/modules/custom_modules/copilot/` |
| docker-compose update | Add `copilot-service` container to production stack | `docker/development-easy/docker-compose.yml`, `/opt/clinicalcopilot/docker-compose.yml` |
| Demo mode guard | `COPILOT_DEMO_MODE=true` blocks real PHI until BAA | `copilot/config.py` |

### Phase 2 — Hardening (Post-Submission)

| Task | Description |
|---|---|
| Credential rotation | Change admin password; create physician accounts |
| BAA execution | Anthropic enterprise + DigitalOcean + Cloudflare |
| Apache log sanitization | Strip `token_main` from logged Referer headers |
| Cloudflare SSL → Full Strict | Enforce verified TLS between Cloudflare and origin |
| Patient context cache | Redis container; 5-minute TTL keyed by pid+encounter_date |
| Prompt injection hardening | Sanitize patient free-text fields before context insertion |

### Phase 3 — Scale (Future)

| Task | Description |
|---|---|
| Lab results integration | Connect `procedure_result` table once populated; surface HbA1c trends |
| Problem list integration | `lists` table (diagnoses, allergies); currently empty in demo |
| Multi-physician support | Per-physician session isolation; audit log per user |
| Bigger Droplet | Upgrade to 4 vCPU / 8 GB when concurrent use exceeds 3 physicians |

---

## 7. Traceability to USERS.md

Every capability maps to a use case. Nothing is built speculatively.

| Use Case (USERS.md) | Architecture Element |
|---|---|
| UC1: Pre-visit briefing | Context assembly on chart open trigger; streaming response; 3s latency target |
| UC2: Medication safety check | Active medication list in context block; Claude grounding constraint; no write access |
| UC3: Between-visit chart question | Conversational endpoint; physician typed input; same context assembly path |
| UC4: End-of-day chart completion | Context assembly on demand; vitals + last SOAP prioritized in output |

---

## 8. Decisions and Tradeoffs Log

This section documents choices made and the reasoning behind them. It exists to be defended on Tuesday.

| Decision | Alternative Considered | Why This Choice |
|---|---|---|
| Separate Co-Pilot service (Python) | PHP module inside OpenEMR | Python has mature async, streaming, and LLM SDK support. Separation means OpenEMR upgrades don't break the agent. |
| REST API data access | Direct MariaDB queries | REST API preserves audit trail and authorization layer. ~100ms latency cost is absorbed by Claude API latency. |
| Claude Sonnet over Opus | Claude Opus | Sonnet meets the clinical reasoning bar for summarization; Opus latency breaks the 3s UX target. |
| Streaming via SSE | Polling / complete response | Streaming makes Claude latency invisible. A 2.5s wait for a complete response fails the 60-second visit prep window. |
| Demo-mode guard | Trust BAA is in place | HIPAA impermissible disclosure is not recoverable. The guard is a hard constraint, not a best practice. |
| Context scoping (last 5 encounters, 12 months) | Full chart dump | Targeted context reduces cost, reduces latency, and reduces hallucination surface. The physician's full chart review is not replaced. |
| Apache reverse proxy (not public service port) | Exposing copilot-service on a public port | Co-Pilot traffic inherits OpenEMR's session auth. No separate auth layer to implement or secure. |
