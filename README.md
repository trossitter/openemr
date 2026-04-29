# Clinical Co-Pilot

**An AI agent embedded in OpenEMR that gives a physician the context they need, the moment they need it.**

Live demo: **[clinicalcopilot.org](https://clinicalcopilot.org)** — login: `admin` / `pass`

Forked from [openemr/openemr](https://github.com/openemr/openemr) (OpenEMR 8.0.0)

---

## What This Is

A primary care physician sees 20 patients a day. Each appointment is 15 minutes. Between clicking a patient's name and the patient walking in the door, the physician has about 60 seconds to re-orient to that person's chart — their medications, their last visit, what was left unresolved.

The Clinical Co-Pilot is an AI agent that assembles that context automatically and surfaces it before the physician has to ask. It knows this patient's history, their active medications, their recent labs, and what was flagged at the last visit. It does not give medical advice. It does not replace chart review. It eliminates the attention tax of context-switching 20 times a day.

---

## Project Documents

| Document | Description |
|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System design: where the agent lives, how it accesses data, authorization boundaries, risk register, and implementation roadmap |
| [AUDIT.md](./AUDIT.md) | Full system audit — security, performance, architecture, data quality, and HIPAA/compliance findings |
| [USERS.md](./USERS.md) | Target user profile (Dr. Sarah Chen, primary care), workflow analysis, and 4 concrete use cases with agent-vs-dashboard justification |
| [README-COPILOT.md](./README-COPILOT.md) | Local development setup guide |
| [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) | Walkthrough script for the recorded demo |

---

## Demo Patients

Five patients with complete clinical records seeded for demonstration:

| Patient | Age | Conditions | Active Medications |
|---|---|---|---|
| Ted Shaw | 79M | Hypertension, Type 2 Diabetes | Lisinopril, Metformin, Amlodipine |
| Eduardo Perez | 69M | COPD | Tiotropium, Albuterol, Azithromycin, Prednisone |
| Farrah Rolle | 52F | OB — 28 weeks pregnant | Prenatal vitamins, Folic Acid |
| Nora Cohen | 58F | Anxiety, Chronic Migraine | Sertraline, Propranolol, Sumatriptan |
| Jim Moses | 81M | Post-MI, Ischemic Cardiomyopathy | Aspirin, Atorvastatin, Metoprolol, Lisinopril |

---

## Architecture Overview

```
Browser (Co-Pilot panel, JavaScript)
  ↓ HTTPS
Cloudflare (TLS, DNS proxy)
  ↓
DigitalOcean Droplet
  ├── openemr container     (Apache + PHP, ports 80/443)
  ├── copilot-service       (Python/FastAPI, internal only)  ← new
  └── mariadb container     (1.5 GB InnoDB buffer pool)
              ↓ OpenEMR REST API (scoped, read-only)
              ↓ Claude API (streaming, zero-retention)
```

The Co-Pilot runs as a separate service. Patient data is accessed through OpenEMR's own REST API — not the database directly — preserving the audit trail and authorization layer. All Claude API calls stream back to the browser via Server-Sent Events. A `COPILOT_DEMO_MODE` flag blocks real PHI from reaching the Claude API until a BAA with Anthropic is in place.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full design.

---

## Running Locally

```bash
# 1. Clone
gh repo clone trossitter/openemr && cd openemr

# 2. Start the stack
cd docker/development-easy && docker compose up -d

# 3. Wait for healthy (~5 minutes on first boot)
until docker inspect development-easy-openemr-1 \
  --format '{{.State.Health.Status}}' | grep -q "healthy"; do
  sleep 10 && echo "Starting..."
done

# 4. Load demo data
cd ../..
docker exec -i development-easy-mysql-1 mariadb -u openemr -popenemr openemr < sql/example_patient_data.sql
docker exec -i development-easy-mysql-1 mariadb -u openemr -popenemr openemr < sql/example_patient_users.sql
docker exec -i development-easy-mysql-1 mariadb -u openemr -popenemr openemr < sql/demo_clinical_data.sql

# 5. Open https://localhost:9300  (accept the self-signed cert warning)
#    Login: admin / pass
```

See [README-COPILOT.md](./README-COPILOT.md) for the full setup guide and verification steps.

---

## Infrastructure

| | |
|---|---|
| Compute | DigitalOcean Droplet, NYC3, Ubuntu 22.04, 2 vCPU / 4 GB RAM |
| DNS & Proxy | Cloudflare (proxied, TLS termination) |
| Database | MariaDB 11.8.6, 1.5 GB InnoDB buffer pool |
| Application | OpenEMR 8.0.0 |

---

## Stage Completion

| Stage | Description | Status |
|---|---|---|
| 1 | OpenEMR running locally with sample data | ✅ Complete |
| 2 | Deployed to DigitalOcean + Cloudflare DNS | ✅ Complete |
| 3 | Full system audit (AUDIT.md) | ✅ Complete |
| 4 | User profiles and use cases (USERS.md) | ✅ Complete |
| 5 | Architecture plan (ARCHITECTURE.md) | ✅ Complete |
[![Rector](https://github.com/openemr/openemr/actions/workflows/rector.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/rector.yml)
[![ShellCheck](https://github.com/openemr/openemr/actions/workflows/shellcheck.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/shellcheck.yml)
[![Docker Compose Linting](https://github.com/openemr/openemr/actions/workflows/docker-compose-lint.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/docker-compose-lint.yml)
[![Dockerfile Linting](https://github.com/openemr/openemr/actions/workflows/hadolint.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/hadolint.yml)
[![Isolated Tests](https://github.com/openemr/openemr/actions/workflows/isolated-tests.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/isolated-tests.yml)
[![Inferno Certification Test](https://github.com/openemr/openemr/actions/workflows/inferno-test.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/inferno-test.yml)
[![Composer Checks](https://github.com/openemr/openemr/actions/workflows/composer.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/composer.yml)
[![Composer Require Checker](https://github.com/openemr/openemr/actions/workflows/composer-require-checker.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/composer-require-checker.yml)
[![API Docs Freshness Checks](https://github.com/openemr/openemr/actions/workflows/api-docs.yml/badge.svg)](https://github.com/openemr/openemr/actions/workflows/api-docs.yml)
[![codecov](https://codecov.io/gh/openemr/openemr/graph/badge.svg?token=7Eu3U1Ozdq)](https://codecov.io/gh/openemr/openemr)

[![Backers on Open Collective](https://opencollective.com/openemr/backers/badge.svg)](#backers) [![Sponsors on Open Collective](https://opencollective.com/openemr/sponsors/badge.svg)](#sponsors)

# OpenEMR

[OpenEMR](https://open-emr.org) is a Free and Open Source electronic health records and medical practice management application. It features fully integrated electronic health records, practice management, scheduling, electronic billing, internationalization, free support, a vibrant community, and a whole lot more. It runs on Windows, Linux, Mac OS X, and many other platforms.

### Contributing

OpenEMR is a leader in healthcare open source software and comprises a large and diverse community of software developers, medical providers and educators with a very healthy mix of both volunteers and professionals. [Join us and learn how to start contributing today!](https://open-emr.org/wiki/index.php/FAQ#How_do_I_begin_to_volunteer_for_the_OpenEMR_project.3F)

> Already comfortable with git? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for quick setup instructions and requirements for contributing to OpenEMR by resolving a bug or adding an awesome feature 😊.

### Support

Community and Professional support can be found [here](https://open-emr.org/wiki/index.php/OpenEMR_Support_Guide).

Extensive documentation and forums can be found on the [OpenEMR website](https://open-emr.org) that can help you to become more familiar about the project 📖.

### Reporting Issues and Bugs

Report these on the [Issue Tracker](https://github.com/openemr/openemr/issues). If you are unsure if it is an issue/bug, then always feel free to use the [Forum](https://community.open-emr.org/) and [Chat](https://www.open-emr.org/chat/) to discuss about the issue 🪲.

### Reporting Security Vulnerabilities

Check out [SECURITY.md](.github/SECURITY.md)

### API

Check out [API_README.md](API_README.md)

### Docker

Check out [DOCKER_README.md](DOCKER_README.md)

### FHIR

Check out [FHIR_README.md](FHIR_README.md)

### For Developers

If using OpenEMR directly from the code repository, then the following commands will build OpenEMR (Node.js version 24.* is required) :

```shell
composer install --no-dev
npm install
npm run build
composer dump-autoload -o
```

### Contributors

This project exists thanks to all the people who have contributed. [[Contribute]](CONTRIBUTING.md).
<a href="https://github.com/openemr/openemr/graphs/contributors"><img src="https://opencollective.com/openemr/contributors.svg?width=890" /></a>


### Sponsors

Thanks to our [ONC Certification Major Sponsors](https://www.open-emr.org/wiki/index.php/OpenEMR_Certification_Stage_III_Meaningful_Use#Major_sponsors)!


### License

[GNU GPL](LICENSE)
