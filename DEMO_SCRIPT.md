# Clinical Co-Pilot — Demo Script
**Format:** Loom screen recording  
**Length:** 3–5 minutes  
**Audience:** Newcomer — no prior context assumed

---

## Setup Before You Hit Record

- Browser tabs open and ready (in order):
  1. `https://github.com/trossitter/openemr` — repo root
  2. `https://clinicalcopilot.org` — live site
  3. OpenEMR logged in as `admin / pass` — patient list visible
  4. Ted Shaw's chart open (pid 1) — or ready to click
- Terminal hidden — nothing sensitive visible
- ARCHITECTURE.md open in a second browser tab or VS Code

---

## The Script

---

### [0:00–0:30] — The Problem

**[SCREEN: clinicalcopilot.org — OpenEMR login page]**

> "This is a live deployment of OpenEMR — an open-source electronic health record system used by clinics worldwide. I want to show you something before I log in.
>
> A primary care physician sees 20 patients a day. Each appointment is 15 minutes. By the time the patient is in the room, the physician has about 60 seconds to re-orient to that person's chart — their medications, their last visit, what was left unresolved. 60 seconds across 20 patients, every day.
>
> That's what this project is about. Not a chatbot that answers medical trivia. An agent that knows *this* patient, surfaces what matters, and has it ready before the physician needs to ask."

---

### [0:30–1:15] — The Live System

**[SCREEN: Log in — admin / pass — land on dashboard]**

> "This is a real OpenEMR instance, deployed on DigitalOcean, proxied through Cloudflare. Let me show you what's in here."

**[SCREEN: Navigate to Patient Finder]**

> "We have a set of demo patients — all synthetic — seeded specifically for this project. These aren't random names. Each one represents a different clinical scenario a primary care physician actually faces."

**[SCREEN: Click into Ted Shaw]**

> "Ted Shaw is 79 years old. He has uncontrolled hypertension and Type 2 diabetes. Six weeks ago his blood pressure was 162 over 100 — the physician added a new antihypertensive. Today he's back for follow-up.
>
> To understand what matters about today's visit, a physician right now has to click through: medications tab, last encounter, SOAP note, look for the HbA1c that was ordered — was it ever resulted? That's four clicks and 45 seconds on a good day. On a 20-patient day, that attention cost adds up."

**[SCREEN: Browse the SOAP note and medications tabs briefly]**

> "The data is all here. The problem isn't access. The problem is assembly time and cognitive load. That's the gap the Co-Pilot fills."

---

### [1:15–2:00] — The Repo and the Documents

**[SCREEN: Switch to GitHub — trossitter/openemr repo root]**

> "This is a fork of OpenEMR's public repository. Everything I've built lives here. Before writing a line of Co-Pilot code, the project required three foundational documents."

**[SCREEN: Click into AUDIT.md]**

> "The first is an audit. Security, performance, architecture, data quality, and HIPAA compliance — five sections, all grounded in what I found running on this actual server. The most important finding: there is no Business Associate Agreement with Anthropic. That means this system cannot legally send real patient data to the Claude API yet. The architecture is designed around that constraint."

**[SCREEN: Click into USERS.md]**

> "The second is the user definition. I chose a primary care physician — 20-patient day, 15-minute appointments. I defined four specific use cases. Not 'answer questions about patients' — but things like: in the 60 seconds before a patient walks in, surface what's changed and what's still pending. Every capability in the architecture has to trace back to one of these use cases. Nothing is built speculatively."

**[SCREEN: Click into ARCHITECTURE.md]**

> "The third is the architecture document. This is the roadmap — not aspirational, but defensible."

---

### [2:00–3:30] — The Five Architecture Questions

**[SCREEN: Stay on ARCHITECTURE.md — scroll to Section 1 diagram]**

> "Let me answer the five questions a newcomer would ask."

---

**"Where does the agent live?"**

> "It lives as a separate service — a Python FastAPI container running inside the same Docker stack as OpenEMR, but isolated from it. It is not embedded in OpenEMR's PHP code. It's reachable only from within the Docker network — never from the public internet. The physician's browser communicates with it through a reverse proxy path on the OpenEMR container, which means the Co-Pilot inherits OpenEMR's existing session authentication automatically."

---

**"How does it access patient data?"**

> "Through OpenEMR's own REST API — not directly from the database. This adds a small latency cost, about 100 milliseconds per call. That cost is invisible against a two-to-three second Claude API round-trip. What it buys is the audit trail and access control that OpenEMR already provides. Every data access is logged. The agent reads demographics, active medications, recent encounters, SOAP notes, and latest vitals — in parallel, in under 300 milliseconds."

---

**"What are the authorization boundaries?"**

> "The Co-Pilot holds a read-only service account token scoped to five data types. It has no write access. It can only request data for the patient currently open in the physician's session — there is no mechanism to enumerate patients. It cannot be reached without an active OpenEMR login. And the agent itself has no knowledge of who the physician is — it only knows what's in the current patient context it was handed."

---

**"What are the risks?"**

> "The risk register has four categories. The most critical is compliance: no BAA, no real PHI. Full stop. Second is security: the system currently runs with default credentials — that's a known issue, documented, and first on the hardening list. Third is clinical: a model that hallucinates a lab value or a drug interaction is not a UX problem, it's a patient safety problem. The system prompt forces source citation and prohibits the model from inferring anything not explicitly in the chart. Fourth is performance: Claude API latency is the dominant factor, and streaming is the mitigation — the physician sees the first tokens within two seconds."

---

**"How do you handle HIPAA?"**

> "There is a hard environment flag: `COPILOT_DEMO_MODE=true`. When it's set, the service will not send real patient data to the Claude API. It blocks at the service layer, not the prompt layer. Disabling it requires a deliberate configuration change — not just removing a comment. The system is fully functional for development and demonstration on synthetic data. The transition to real PHI is a compliance step, not an engineering step. Sign the BAA, flip the flag."

---

### [3:30–4:00] — Close

**[SCREEN: Back to ARCHITECTURE.md — Section 6, Roadmap]**

> "Phase 1 is what you've seen today: the system is live, the data layer is designed, the authorization model is defined, and the guard rails are in place. Phase 1 implementation is the Co-Pilot service itself — context assembly, Claude integration, the UI panel, all tracing back to the four use cases in USERS.md.
>
> The goal is not to replace clinical judgment. It is to eliminate the 60-second assembly tax on 20 patients, every day, so that attention goes to the patient instead of the chart.
>
> That's the Clinical Co-Pilot."

---

## Timing Guide

| Section | Duration | What's on Screen |
|---|---|---|
| The Problem | 0:00–0:30 | clinicalcopilot.org login page |
| The Live System | 0:30–1:15 | OpenEMR — Patient Finder → Ted Shaw → SOAP / Meds |
| The Repo and Docs | 1:15–2:00 | GitHub — AUDIT.md → USERS.md → ARCHITECTURE.md |
| The Five Questions | 2:00–3:30 | ARCHITECTURE.md — diagram, sections 2–8 |
| Close | 3:30–4:00 | ARCHITECTURE.md — roadmap section |

---

## Tips

- **Don't rush the problem statement.** The 60-second framing is what makes everything else make sense. If they don't feel the problem, the solution looks like a chatbot.
- **When navigating Ted Shaw's chart**, pause for a half-beat on the medication list and the SOAP note. Let the viewer see the data before you explain why it's hard to use.
- **For the five questions**, use a slightly slower, more deliberate pace — these are the answers you're being graded on.
- **You don't need to scroll through every line of the documents.** Show the structure, then speak to it.
- **End on the roadmap section**, not on a blank page. It signals there's more coming.
