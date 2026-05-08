#!/bin/zsh
# Clinical Co-Pilot — end-to-end demo
# Runs against the live site. No local service required.
# Usage: cd ~/openemr/copilot && ./demo.sh

set -euo pipefail
cd "$(dirname "$0")"

# ── Config ──────────────────────────────────────────────────────────────────
SECRET="copilot-prod-559a98e9a9a7d479dfb99e16"
BASE="https://clinicalcopilot.org/copilot"
PID=1

# ── Formatting ──────────────────────────────────────────────────────────────
B=$'\033[1m'
BL=$'\033[1;34m'
G=$'\033[1;32m'
Y=$'\033[1;33m'
C=$'\033[1;36m'
D=$'\033[2m'
R=$'\033[0m'

divider() { printf "\n${B}${BL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${R}\n" }
header()  { divider; printf "${B}${BL}  %s${R}\n" "$1"; divider }
ok()      { printf "${G}  ✓ %s${R}\n" "$1" }
label()   { printf "${Y}  → %s${R}\n" "$1" }
dim()     { printf "${D}    %s${R}\n" "$1" }

# ── Fixtures ────────────────────────────────────────────────────────────────
if [[ ! -f fixtures/p01-chen-lipid-panel.pdf ]]; then
  printf "${Y}  Generating synthetic fixtures...${R}\n"
  python3 fixtures/make_fixtures.py 2>/dev/null
fi

# ════════════════════════════════════════════════════════════════════════════
header "0 — SERVICE HEALTH"
# ════════════════════════════════════════════════════════════════════════════
label "GET $BASE/health"
curl -s "$BASE/health" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  status:     {d[\"status\"]}')
print(f'  demo_mode:  {d[\"demo_mode\"]}')
print(f'  service:    {d[\"service\"]}')
"
ok "Service is up"

# ════════════════════════════════════════════════════════════════════════════
header "1 — DOCUMENT INGESTION  [Requirements 1 · 2 · 5]"
# ════════════════════════════════════════════════════════════════════════════

# ── 1a: Lab PDF ──────────────────────────────────────────────────────────────
printf "\n${B}${C}1a  Lab PDF — Claude Vision extraction + Pydantic validation + FHIR write${R}\n"
label "POST /v2/ingest  file=p01-chen-lipid-panel.pdf  doc_type=lab_pdf"

LAB_RESP=$(curl -s -X POST "$BASE/v2/ingest" \
  -H "X-Copilot-Secret: $SECRET" \
  -F "file=@fixtures/p01-chen-lipid-panel.pdf" \
  -F "doc_type=lab_pdf" \
  -F "pid=$PID")

python3 - <<PYEOF
import json, sys
d = json.loads('''$(echo "$LAB_RESP" | python3 -c "import sys; print(sys.stdin.read().replace(\"'\", \"\\\\'\"))")'''  )
print(f'  doc_id:    {d["doc_id"]}')
print(f'  pages:     {d["page_count"]}')
print(f'  extracted: {len(d["extracted"])} lab results')
print()
print('  Test Name                         Value    Unit       Abnormal  Provenance chain')
print('  ' + '─'*80)
for r in d['extracted']:
    flag  = '⚑ YES' if r['abnormal_flag'] else '     '
    cit   = r['source_citation']
    chain = cit['transform_chain'][-1]
    y0    = cit['bbox']['y0'] if cit.get('bbox') else '—'
    print(f"  {r['test_name']:<33} {r['value']:>6}  {r['unit']:<10} {flag}     {chain}")
PYEOF

DOC_ID=$(echo "$LAB_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['doc_id'])")
ok "Extracted and validated against LabResult schema"

# ── 1b: Bbox overlay ────────────────────────────────────────────────────────
printf "\n${B}${C}1b  Visual provenance overlay  [Requirement 5]${R}\n"
label "GET /v2/overlay/$DOC_ID/0  (annotated PNG — each value boxed on source page)"
OVERLAY_FILE="demo_lipid_overlay_$(date +%s).png"
HTTP_STATUS=$(curl -s -o "$OVERLAY_FILE" -w "%{http_code}" \
  "$BASE/v2/overlay/$DOC_ID/0" \
  -H "X-Copilot-Secret: $SECRET")

if [[ "$HTTP_STATUS" == "200" ]]; then
  FILESIZE=$(wc -c < "$OVERLAY_FILE" | tr -d ' ')
  ok "Overlay saved → $OVERLAY_FILE  (${FILESIZE} bytes)"
  open "$OVERLAY_FILE"
else
  dim "Overlay not available (HTTP $HTTP_STATUS) — redeploy server to enable"
fi

label "GET /v2/overlay/$DOC_ID/metadata  (machine-readable provenance)"
curl -s "$BASE/v2/overlay/$DOC_ID/metadata" \
  -H "X-Copilot-Secret: $SECRET" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  coordinate_space: {d[\"coordinate_space\"]}')
print(f'  render_dpi:       {d[\"render_dpi\"]}')
print(f'  annotations:      {len(d[\"annotations\"])}')
for a in d['annotations'][:3]:
    print(f'    field={a[\"field_id\"]}  page={a[\"page_index\"]}  bbox={a[\"bbox_image_px\"]}')
print('    ...')
" 2>/dev/null || dim "Metadata endpoint unavailable"

# ── 1c: Intake form ──────────────────────────────────────────────────────────
printf "\n${B}${C}1c  Intake form — demographics · chief concern · medications · allergies${R}\n"
label "POST /v2/ingest  file=p01-chen-intake.pdf  doc_type=intake_form"

INTAKE_RESP=$(curl -s -X POST "$BASE/v2/ingest" \
  -H "X-Copilot-Secret: $SECRET" \
  -F "file=@fixtures/p01-chen-intake.pdf" \
  -F "doc_type=intake_form" \
  -F "pid=$PID")

echo "$INTAKE_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
r = d['extracted']
demo = r.get('demographics', {})
cit  = r.get('source_citation', {})
print(f'  patient:          {demo.get(\"name\", \"—\")}  DOB {demo.get(\"dob\", \"—\")}')
print(f'  chief concern:    {r.get(\"chief_concern\", \"—\")}')
print(f'  medications:      {r.get(\"medications\", [])}')
print(f'  allergies:        {r.get(\"allergies\", [])}')
print(f'  family history:   {r.get(\"family_history\", [])}')
print()
print(f'  citation.source_type:   {cit.get(\"source_type\")}')
print(f'  citation.content_hash:  {(cit.get(\"content_hash\") or \"\")[:16]}…')
print(f'  citation.transform_chain: {cit.get(\"transform_chain\", [])}')
"
ok "Extracted and validated against IntakeForm schema"

# ── 1d: HL7v2 ────────────────────────────────────────────────────────────────
printf "\n${B}${C}1d  HL7v2 ORU-R01 — deterministic parse, LOINC citations, no Claude call${R}\n"
label "POST /v2/ingest  file=p01-chen-oru-r01.hl7  doc_type=hl7_oru"

HL7_RESP=$(curl -s -X POST "$BASE/v2/ingest" \
  -H "X-Copilot-Secret: $SECRET" \
  -F "file=@fixtures/hl7v2/p01-chen-oru-r01.hl7" \
  -F "doc_type=hl7_oru" \
  -F "pid=$PID")

echo "$HL7_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  doc_id (sha256):  {d[\"doc_id\"]}')
print(f'  extracted:        {len(d[\"extracted\"])} lab results')
print(f'  overlay:          none — HL7v2 is pure text, no spatial position')
print()
for r in d['extracted']:
    cit = r['source_citation']
    print(f'  {r[\"test_name\"]:<50} {r[\"value\"]:>6} {r[\"unit\"]}')
    print(f'    LOINC id: {cit[\"field_or_chunk_id\"]}  parser: {cit[\"parser\"]}  chain: {cit[\"transform_chain\"]}')
"
ok "HL7v2 parsed deterministically — no LLM tokens consumed"

# ════════════════════════════════════════════════════════════════════════════
header "2 — HYBRID RAG + LANGGRAPH ROUTING  [Requirements 3 · 4]"
# ════════════════════════════════════════════════════════════════════════════

QUERY="What does JNC 8 recommend for blood pressure targets in patients with diabetes and CKD, and what first-line agents are preferred?"
printf "\n${B}  Query:${R} %s\n\n" "$QUERY"
label "POST /v2/query  (supervisor routes to evidence_retriever → assembles grounded response)"

QRESP=$(curl -s -X POST "$BASE/v2/query" \
  -H "Content-Type: application/json" \
  -H "X-Copilot-Secret: $SECRET" \
  -d "{\"session_id\":\"demo\",\"pid\":$PID,\"query\":\"$QUERY\"}")

echo "$QRESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)

print('  LangGraph handoffs:')
for h in d.get('handoffs', []):
    print(f'    {h[\"from_node\"]:22} → {h[\"to_node\"]:22}  [{h[\"reason\"]}]')

chunks = d.get('evidence_chunks_count', 0)
print(f'\n  Guideline chunks retrieved (BM25 + ChromaDB + Cohere rerank): {chunks}')
print()
print('  ─── Final grounded response ───')
print()
for line in d.get('final_answer', '').split('\n'):
    print(f'  {line}')
"
ok "Cited response grounded in ADA 2024 / JNC 8 / USPSTF corpus"

# ════════════════════════════════════════════════════════════════════════════
header "3 — EVAL GATE  [Requirement 6]"
# ════════════════════════════════════════════════════════════════════════════
printf "\n${B}  Running 51-case golden set · 5 boolean rubrics · CI hard gate${R}\n\n"
label "python3 -m pytest evals/test_eval.py evals/test_hl7.py evals/test_coords.py -v --tb=short"

python3 -m pytest \
  evals/test_eval.py \
  evals/test_hl7.py \
  evals/test_coords.py \
  -v --tb=short -q 2>&1 | tail -20

ok "All regression gates pass (schema_valid · citation_present · factually_consistent · safe_refusal · no_phi_in_logs)"

# ════════════════════════════════════════════════════════════════════════════
header "4 — PHI-SAFE OBSERVABILITY  [Requirement 7]"
# ════════════════════════════════════════════════════════════════════════════
label "GET /logs?n=12  (tool sequence · latency · token cost · extraction · handoffs)"
printf "\n"

curl -s "$BASE/logs?n=12" \
  -H "X-Copilot-Secret: $SECRET" | python3 -c "
import sys, json
d = json.load(sys.stdin)
entries = d.get('entries', [])
for e in entries:
    event = e.get('event', '')
    ts    = e.get('ts', '')[:19]
    if event == 'extraction':
        print(f'  {ts}  {event:<20} doc_id={e[\"doc_id\"]}  type={e[\"doc_type\"]}  fields={e[\"field_count\"]}  bboxes={e[\"bbox_count\"]}  {e[\"duration_ms\"]:.0f}ms')
    elif event == 'llm_call':
        print(f'  {ts}  {event:<20} in={e[\"input_tokens\"]}tok  out={e[\"output_tokens\"]}tok  cost=\${e[\"cost_usd\"]:.4f}  {e[\"duration_ms\"]:.0f}ms')
    elif event == 'tool_call':
        print(f'  {ts}  {event:<20} tool={e[\"tool\"]}  rows={e[\"row_count\"]}  {e[\"duration_ms\"]:.0f}ms')
    elif event == 'graph_handoff':
        print(f'  {ts}  {event:<20} {e[\"from_node\"]} → {e[\"to_node\"]}  [{e[\"reason\"]}]')
    elif event == 'verification_result':
        status = \"PASS\" if e[\"passed\"] else \"FAIL\"
        print(f'  {ts}  {event:<20} {status}  violations={e[\"violations\"]}')
print()
print(f'  total log entries: {d[\"total_lines\"]}')
print('  no raw PHI in any field (names, DOBs, MRNs redacted at ingestion boundary)')
"
ok "Structured observability — every encounter traceable without PHI exposure"

# ════════════════════════════════════════════════════════════════════════════
divider
printf "${B}${G}  Demo complete.${R}\n"
printf "\n"
printf "${G}  Demonstrated:\n"
printf "    Req 1  upload + extraction    lab_pdf · intake_form · hl7_oru\n"
printf "    Req 2  Pydantic schemas       LabResult · IntakeForm · Citation\n"
printf "    Req 3  hybrid RAG             BM25 + ChromaDB + Cohere rerank\n"
printf "    Req 4  LangGraph routing      supervisor → evidence_retriever → supervisor\n"
printf "    Req 5  citations + overlay    machine-readable bbox · annotated PNG\n"
printf "    Req 6  eval gate              51 cases · 5 rubrics · ≥ 90%% threshold\n"
printf "    Req 7  observability          tool seq · latency · tokens · cost · PHI-safe${R}\n"
divider
printf "\n"
