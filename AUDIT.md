# Clinical Co-Pilot — System Audit

**System:** OpenEMR 8.0.0, deployed on DigitalOcean (Ubuntu 22.04, 2 vCPU / 4GB RAM)
**Audit Date:** 2026-04-29
**Auditor:** Giorgio (Clinical Co-Pilot AI, Claude Code)
**Scope:** Security, Performance, Architecture, Data Quality, Compliance & Regulatory

---

## Executive Summary

OpenEMR 8.0.0 is a mature, feature-rich electronic health record system with a well-structured audit logging subsystem and a reasonable default security posture. However, as deployed today, this instance carries several findings that must be addressed before any PHI is treated as protected or before the Claude API integration is considered HIPAA-adjacent. The five most consequential findings are:

**1. Default credentials on a live public endpoint.** The system is reachable at `https://clinicalcopilot.org` with `admin / pass`. Any credential-stuffing bot will find this. This is the highest-priority fix before any real patient data is loaded.

**2. Session tokens logged in plaintext in Apache access logs.** Every page request logs a `token_main` value in the Referer header. These tokens authenticate a session with full admin access to all patient records. The log file is unencrypted on disk and has no retention or rotation policy configured.

**3. No Business Associate Agreement (BAA) with Anthropic.** The core purpose of this project is to send patient context to the Claude API. Under HIPAA, transmitting PHI to a third-party service provider requires a signed BAA. Anthropic offers a BAA only under its enterprise tier. Until one is in place, the system must not send real patient data to the Claude API — demo data only.

**4. InnoDB buffer pool severely undersized.** At 128 MB on a 4 GB server, the database cannot hold its working set in memory. The largest table (`lang_definitions`, 28 MB) alone approaches the limit. For an AI agent that must assemble full patient context in under two seconds, this is a hard latency blocker.

**5. No foreign key constraints on clinical tables.** `form_encounter`, `form_vitals`, `form_soap`, and `prescriptions` have no referential integrity enforcement linking them to `patient_data`. An agent querying patient context can silently return incomplete or mismatched records if a patient record is deleted or migrated without cascading.

The remaining findings are significant but lower urgency for a development deployment. The architecture is well-suited to the Co-Pilot integration: OpenEMR exposes a documented REST API and a PHP hook/module system that provides a clean insertion point for the agent panel. The data model is relational and straightforward to query. With the five issues above resolved and a proper BAA in place, the system is ready for Stage 5 implementation.

---

## 1. Security Audit

### 1.1 Authentication & Authorization

| Finding | Severity | Detail |
|---|---|---|
| Default credentials active on public URL | **Critical** | `admin / pass` is accessible at `https://clinicalcopilot.org`. No MFA configured. |
| Session timeout too long | **Medium** | `timeout = 7200` (2 hours). HIPAA guidance suggests 15 minutes of inactivity for workstation access. |
| Password expiration set | **Low** | `password_expiration_days = 180` and `password_history = 5` are configured — this is correct. |
| REST and FHIR APIs disabled | **Pass** | `rest_api`, `rest_fhir_api`, `rest_portal_api` all set to `0` in globals. No unauthenticated API surface. |
| Single admin account | **Medium** | All activity runs through one `admin` account. No role separation, no physician-specific accounts. |

### 1.2 PHI Exposure Vectors

| Finding | Severity | Detail |
|---|---|---|
| Session tokens in Apache access logs | **High** | `token_main` values appear in logged `Referer` headers (e.g., `?token_main=MunIM2HGiT0X2AFz2ONT1...`). These tokens grant authenticated session access. |
| Apache logs not rotated or encrypted | **Medium** | `/var/log/apache2/access.log` grows unbounded inside the container. No log rotation configured, no encryption at rest. |
| HTTPS between Cloudflare and server is opportunistic | **Medium** | Cloudflare SSL mode is not set to "Full (Strict)". The Cloudflare→server leg uses a self-signed cert without validation, meaning traffic could be intercepted at the network layer between Cloudflare's edge and the DigitalOcean droplet. |
| MariaDB accessible with root from any host | **High** | `SELECT host, user FROM mysql.user` shows `%` (any host) for both `openemr` and `root` users. The DB port (3306) is not exposed through the firewall, but this is defense-in-depth failure — any container breakout reaches the DB as root. |

### 1.3 Infrastructure

| Finding | Severity | Detail |
|---|---|---|
| Docker daemon ports removed | **Resolved** | UFW rules for 2375/2376 (Docker daemon API) were present on the DigitalOcean Docker droplet image. These have been removed during this audit. No daemon was actually listening, but the rules represented an unnecessary attack surface. |
| Firewall now minimal and correct | **Pass** | UFW allows only 22/tcp (rate-limited), 80/tcp, 443/tcp. |
| No intrusion detection | **Low** | No fail2ban, no Crowdsec, no login alerting beyond OpenEMR's built-in audit log. |

---

## 2. Performance Audit

### 2.1 Database Configuration

| Finding | Impact | Detail |
|---|---|---|
| InnoDB buffer pool: 128 MB | **High** | Default for MariaDB container. Server has 3.8 GB RAM. Should be set to ~1.5–2 GB. At current size, complex patient context queries will hit disk on every request. |
| Query cache disabled | **Medium** | `query_cache_type = OFF`. For repeated reads of the same patient's data during a visit, a query cache would meaningfully reduce latency. |
| Slow query log disabled | **Medium** | `slow_query_log = OFF`. No visibility into which queries degrade under load. Should be enabled with `long_query_time = 1` before Stage 5. |
| Max connections: 151 | **Low** | Default. Adequate for single-instance demo but would need tuning for concurrent physician usage. |

### 2.2 Index Coverage

| Table | Indexed Columns | Gap |
|---|---|---|
| `patient_data` | `pid` (unique), `uuid`, `lname+fname`, `DOB` | Well-indexed for lookup. |
| `form_encounter` | `pid+encounter` (composite), `date` | Good. Co-Pilot query by `pid` + date range is covered. |
| `prescriptions` | `patient_id` | Adequate for patient lookup. No index on `active` or `end_date` — filtering active meds requires a full scan per patient. |
| `form_vitals` | `pid` | Adequate. |
| `form_soap` | Primary key only — **no `pid` index** | **Gap.** Fetching SOAP notes by patient requires a full table scan. Will degrade linearly as records grow. |

### 2.3 Agent Response Latency Budget

A Co-Pilot context query must assemble: demographics + active meds + recent encounters + SOAP notes + latest vitals. Estimated query breakdown at current configuration:

| Query | Estimated Time (cold, 128MB buffer) | Estimated Time (warm, 2GB buffer) |
|---|---|---|
| Patient demographics | < 1 ms | < 1 ms |
| Active prescriptions | 2–5 ms | < 1 ms |
| Encounters (last 6 months) | 2–5 ms | < 1 ms |
| SOAP notes (last 3) | 10–30 ms (no pid index) | 1–2 ms |
| Vitals (last 3) | 2–5 ms | < 1 ms |
| Claude API round-trip (Sonnet) | 1,500–3,000 ms | 1,500–3,000 ms |
| **Total** | **~1,520–3,050 ms** | **~1,505–3,010 ms** |

**Key finding:** The Claude API latency dominates. Database tuning matters but the agent's perceived speed is determined by the LLM. Streaming responses will be the primary UX lever.

### 2.4 Server Resources

- **CPU:** 2 vCPU — adequate for demo load, insufficient for concurrent use by multiple physicians.
- **RAM:** 3.8 GB total, 551 MB used, 3.2 GB in buffer/cache — significant headroom to increase InnoDB buffer pool.
- **Disk:** 78 GB, 9.7 GB used — ample.
- **Swap:** None configured — a memory spike would OOM-kill containers rather than degrade gracefully.

---

## 3. Architecture Audit

### 3.1 System Overview

```
Browser
  │
  ▼
Cloudflare (DNS proxy, TLS termination, DDoS protection)
  │
  ▼
DigitalOcean Droplet (Ubuntu 22.04, 2 vCPU / 4 GB)
  │
  ├── Docker: openemr/openemr:8.0.0
  │     ├── Apache 2 (ports 80, 443)
  │     ├── PHP 8.x (mod_php)
  │     ├── OpenEMR application code (/var/www/localhost/htdocs/openemr/)
  │     └── Volume: /var/www/localhost/htdocs/openemr/sites (persistent)
  │
  └── Docker: mariadb:11.8.6
        └── Volume: databasevolume (persistent)
```

### 3.2 Application Layer Structure

```
openemr/
├── interface/          # All PHP UI pages (patient charts, encounters, admin)
│   ├── login/          # login.php — authentication entry point
│   ├── patient_file/   # Patient chart views (demographics, history)
│   ├── forms/          # Clinical form handlers (SOAP, vitals, etc.)
│   └── main/tabs/      # Main frame / navigation shell
├── src/                # Modern PHP namespaced classes (PSR-4)
│   ├── Common/Auth/    # Authentication, OAuth2 (PKCE)
│   ├── FHIR/           # FHIR R4 resource mappings
│   └── Services/       # Service layer for patient, encounter, prescription data
├── library/            # Legacy procedural PHP (globals.php, sql.inc.php)
│   ├── globals.php     # System-wide configuration constants
│   └── sql.inc.php     # Database abstraction layer (sqlQuery, sqlStatement)
├── sql/                # Schema migrations and seed data
├── modules/            # Third-party module mount point
└── custom/             # Local customizations (safe from upstream merges)
```

### 3.3 Data Flow for a Patient Chart Load

1. Physician authenticates → session created, `token_main` issued
2. `/interface/patient_file/summary/demographics.php` called with `pid`
3. PHP calls `sqlQuery()` from `library/sql.inc.php` → MariaDB
4. Multiple separate queries: demographics, encounters, meds, vitals (no single unified "patient context" endpoint)
5. HTML rendered server-side and returned

**Integration point for Co-Pilot:** The encounter view at `/interface/forms/` is the right insertion point. A sidebar panel injected via the hook system can load asynchronously alongside the existing chart, without blocking the page render.

### 3.4 REST API Architecture

OpenEMR implements a full OAuth2 + PKCE REST API under `/api/` and a FHIR R4 API under `/fhir/`. Both are currently disabled in globals. The REST API provides endpoints for:
- `GET /api/patient/{pid}` — demographics
- `GET /api/patient/{pid}/encounter` — encounters
- `GET /api/patient/{pid}/medication` — medications
- `GET /fhir/Patient/{pid}` — FHIR Patient resource

**Recommendation for Co-Pilot:** Enable the REST API with scoped tokens rather than querying MariaDB directly. This decouples the agent from the DB schema and uses OpenEMR's own authorization layer.

### 3.5 Extension / Hook System

OpenEMR supports PHP hooks via `src/Events/` (Symfony EventDispatcher). Key hooks:
- `PatientDemographicsEvent` — fires when a patient chart opens
- `RestApiEvent` — fires on API calls (logging, rate limiting)
- Custom modules in `interface/modules/custom_modules/` are auto-discovered

This is the cleanest integration path: a custom module that registers a hook on chart open, fires an async request to the Co-Pilot agent service, and renders a panel in the UI.

---

## 4. Data Quality Audit

### 4.1 Completeness

| Table | Total Records | Key Missing Fields |
|---|---|---|
| `patient_data` | 5 | No missing required fields in demo set. Real gap: `race`, `ethnicity`, `county` nullable with no defaults — SDOH fields will be empty for most patients. |
| `form_encounter` | 6 | Complete. `encounter_type_code` is empty on all records — agent cannot distinguish visit type (office, telehealth, ED) without this. |
| `prescriptions` | 16 | `end_date` is NULL on all 16 records. Agent cannot determine if a medication is still active vs. historically prescribed without this. |
| `form_vitals` | 6 | Complete. `oxygen_flow_rate` and `inhaled_oxygen_concentration` NULL — expected for non-ICU patients. |
| `form_soap` | 6 | Complete. High quality for demo purposes. |

### 4.2 Consistency Issues

- **Medication active status:** The `active` flag in `prescriptions` is a manual boolean. There is no automated deactivation when `end_date` passes. An agent must not assume `active=1` means the medication is current without checking `end_date`.
- **No labs or diagnostic results:** `procedure_result` table is empty. This is the most significant gap for a Co-Pilot — lab trends (HbA1c, BMP, lipid panels) are among the most clinically useful signals at the point of care.
- **No problem list:** The `lists` table (problem list / diagnoses) is empty. The Co-Pilot currently infers diagnoses only from prescription indications and SOAP assessment fields — fragile and incomplete.
- **No allergy records:** The `lists` table with `type='allergy'` is empty. Drug-allergy checking is unavailable.
- **Encounter–form linkage is weak:** The `forms` table links encounters to clinical forms by `form_id`, but the join is procedural (no FK). Fetching all forms for an encounter requires multiple lookups.

### 4.3 Structural Issues

- **No FK constraints** on any of the four main clinical tables. Referential integrity is enforced only at the application layer.
- **`form_soap` has no `pid` index.** Growing this table without adding the index will cause full table scans on every patient context assembly.
- **Duplicate schema patterns:** Some data exists in both structured fields (e.g., `form_vitals.bps`) and free-text SOAP notes. An agent must reconcile these, not treat them as independent sources.

---

## 5. Compliance & Regulatory Audit

### 5.1 HIPAA Technical Safeguards

| Requirement | Status | Gap |
|---|---|---|
| Access controls | Partial | Role-based access exists but single admin account in use. No physician-specific accounts. |
| Audit controls | **Enabled** | `enable_auditlog = 1`. Patient record, query, security, and scheduling events all logged. |
| Integrity controls | Partial | No file integrity monitoring on the application code. DB has no checksums. |
| Transmission security | Partial | Cloudflare→browser is TLS 1.3. Cloudflare→server leg is unverified TLS (opportunistic). |
| Automatic logoff | Partial | 2-hour timeout configured. NIST recommends ≤ 15 minutes for healthcare workstations. |

### 5.2 HIPAA Administrative Safeguards

| Requirement | Status | Gap |
|---|---|---|
| BAA with Anthropic | **Missing — Critical** | Sending any real PHI to the Claude API requires a signed BAA. Anthropic provides BAAs under enterprise agreements only. This project must operate on synthetic/demo data until a BAA is executed. |
| BAA with DigitalOcean | **Available** | DigitalOcean offers a HIPAA BAA under their Business or Professional plans. Not yet executed. |
| BAA with Cloudflare | **Available** | Cloudflare offers a HIPAA BAA under their Business or Enterprise plans. Not yet executed. |
| Workforce training records | Not applicable | Single-developer project at this stage. |
| Risk analysis documentation | Not present | This audit document constitutes an initial risk analysis. |

### 5.3 Data Retention

- OpenEMR has no built-in data retention or automated deletion policy.
- MariaDB data persists indefinitely in Docker volumes.
- Apache access logs are not rotated — unbounded growth and indefinite retention.
- **For the Co-Pilot:** any conversation history or prompt logs sent to Anthropic must be governed by a data retention policy. Claude API does not retain prompt data by default (per Anthropic's policies), but this must be confirmed and documented in any BAA.

### 5.4 Breach Notification

- Under HIPAA, a breach of unsecured PHI requires notification to affected individuals within 60 days and to HHS within 60 days (or annually for breaches < 500 individuals).
- Current deployment has no breach detection capability (no IDS, no anomaly detection, no alerting on unusual query volumes).
- Apache logs are the only forensic artifact available post-incident.

### 5.5 LLM-Specific Compliance Considerations

| Risk | Mitigation Required |
|---|---|
| PHI sent in prompts to Anthropic API | BAA required; use de-identified or synthetic data until signed |
| Prompt injection via patient-controlled fields (e.g., patient notes) | Sanitize all patient-supplied free-text before including in prompts |
| Model hallucination presenting as clinical fact | Agent responses must be clearly labeled as AI-generated; include disclaimer; never present output as a diagnosis |
| Conversation logs containing PHI | Log prompt/response pairs only to encrypted, access-controlled storage; apply same retention policy as EHR |
| Model training on PHI | Anthropic's zero-retention API option should be used; confirm in BAA that data is not used for training |

---

## Summary of Recommended Actions

### Immediate (before any real PHI)
1. Change `admin` password from default
2. Obtain Anthropic BAA (enterprise tier) before connecting real patient data to Claude API
3. Set Cloudflare SSL mode to "Full (Strict)"
4. Restrict MariaDB user hosts from `%` to `172.18.0.0/16` (Docker internal network)
5. Add `pid` index to `form_soap`

### Short-term (before Stage 5 build)
6. Increase InnoDB buffer pool to 1.5 GB
7. Enable slow query log (`long_query_time = 1`)
8. Reduce session timeout to 900 seconds (15 minutes)
9. Configure Apache log rotation (logrotate)
10. Populate `lists` table with problem list and allergy data for demo patients

### Before production with real PHI
11. Execute DigitalOcean and Cloudflare BAAs
12. Create physician-specific user accounts (no shared admin)
13. Configure swap on the server
14. Implement log shipping to encrypted, access-controlled storage
15. Add fail2ban for SSH and the OpenEMR login endpoint
