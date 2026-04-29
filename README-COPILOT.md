# Clinical Co-Pilot — Development Setup

This repo is a fork of [OpenEMR](https://github.com/openemr/openemr) extended with an AI Clinical Co-Pilot: an agent embedded directly in the physician workflow that surfaces patient-specific context (history, medications, recent labs, SOAP notes) at the moment of care.

---

## Prerequisites

| Tool | Version tested | Install |
|---|---|---|
| Git | 2.43+ | `brew install git` |
| Docker Desktop | 25+ | https://www.docker.com/products/docker-desktop |
| GitHub CLI | 2.92+ | `brew install gh` |

---

## 1. Fork & Clone

```bash
gh auth login          # authenticate with your GitHub account
gh repo fork openemr/openemr --clone=true
cd openemr
```

---

## 2. Start the Development Stack

```bash
cd docker/development-easy
docker compose up -d
```

This pulls and starts six services:

| Service | URL | Purpose |
|---|---|---|
| **OpenEMR** | https://localhost:9300 | Main application (HTTPS) |
| OpenEMR (HTTP) | http://localhost:8300 | Alternate plaintext access |
| PHPMyAdmin | http://localhost:8310 | Database browser |
| MariaDB | localhost:8320 | Database (internal) |
| Mailpit | http://localhost:8025 | Catches outbound email |
| Selenium | http://localhost:4444 | Browser automation / testing |

**First boot takes 3–5 minutes** while the database initializes. Wait until the container is healthy:

```bash
until docker inspect development-easy-openemr-1 \
  --format '{{.State.Health.Status}}' | grep -q "healthy"; do
  sleep 10 && echo "Still starting..."
done && echo "Ready."
```

---

## 3. Log In

Navigate to **https://localhost:9300**

> Your browser will show a certificate warning (self-signed cert in dev mode).  
> Click **Advanced → Proceed to localhost** to continue.

| Field | Value |
|---|---|
| Username | `admin` |
| Password | `pass` |

---

## 4. Load Sample Patient Data

OpenEMR ships with demographic data for 14 sample patients. Load it:

```bash
# Patient demographics
docker exec -i development-easy-mysql-1 mariadb -u openemr -popenemr openemr \
  < sql/example_patient_data.sql

# Patient portal user accounts
docker exec -i development-easy-mysql-1 mariadb -u openemr -popenemr openemr \
  < sql/example_patient_users.sql
```

Then load the richer clinical data (encounters, vitals, SOAP notes, medications) created for Co-Pilot development:

```bash
docker exec -i development-easy-mysql-1 mariadb -u openemr -popenemr openemr \
  < sql/demo_clinical_data.sql
```

---

## 5. Verify

```bash
docker exec development-easy-mysql-1 mariadb -u openemr -popenemr openemr -e "
SELECT 'patients'      as table_name, COUNT(*) as count FROM patient_data
UNION ALL SELECT 'encounters',    COUNT(*) FROM form_encounter
UNION ALL SELECT 'vitals',        COUNT(*) FROM form_vitals
UNION ALL SELECT 'soap_notes',    COUNT(*) FROM form_soap
UNION ALL SELECT 'prescriptions', COUNT(*) FROM prescriptions;"
```

Expected output:

```
table_name      count
patients        14
encounters      6
vitals          6
soap_notes      6
prescriptions   16
```

In the browser, go to **Patient Finder** and confirm you can see patients including Ted Shaw, Eduardo Perez, Farrah Rolle, Nora Cohen, and Jim Moses.

---

## Demo Patients

Five patients have complete clinical records for Co-Pilot testing:

| Patient | Conditions | Active Meds |
|---|---|---|
| Ted Shaw (M, 79) | Hypertension, Type 2 Diabetes | Lisinopril, Metformin, Amlodipine |
| Eduardo Perez (M, 69) | COPD | Tiotropium, Albuterol, Azithromycin, Prednisone |
| Farrah Rolle (F, 52) | OB — 28 weeks pregnant | Prenatal vitamins, Folic Acid |
| Nora Cohen (F, 58) | Anxiety, Chronic Migraine | Sertraline, Propranolol, Sumatriptan |
| Jim Moses (M, 81) | Post-MI, Ischemic Cardiomyopathy | Aspirin, Atorvastatin, Metoprolol, Lisinopril |

---

## Stopping & Restarting

```bash
# Stop (preserves data)
cd docker/development-easy && docker compose down

# Restart
cd docker/development-easy && docker compose up -d

# Full reset (destroys all data — re-run seed steps after)
cd docker/development-easy && docker compose down -v
```

---

## Project Structure

```
openemr/
├── docker/development-easy/   # Docker Compose dev stack
├── sql/
│   ├── example_patient_data.sql    # OpenEMR sample demographics
│   ├── example_patient_users.sql   # Sample portal users
│   └── demo_clinical_data.sql      # Co-Pilot demo encounters/meds/vitals
├── interface/                 # PHP frontend (where Co-Pilot UI will live)
├── src/                       # PHP backend / services
└── README-COPILOT.md          # This file
```

---

## Next Steps

- [ ] Step 2: Build the Co-Pilot data layer — API endpoints to query patient context
- [ ] Step 3: Build the Co-Pilot UI panel embedded in the encounter view
- [ ] Step 4: Wire the Claude API to synthesize patient summaries
