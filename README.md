# Foresight: Enterprise Industrial Safety Analytics Platform

[![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Django 5.x](https://img.shields.io/badge/django-5.x-green.svg)](https://www.djangoproject.com/)
[![PostgreSQL 14+](https://img.shields.io/badge/postgresql-14%2B-336791.svg)](https://www.postgresql.org/)
[![pgvector](https://img.shields.io/badge/pgvector-enabled-teal.svg)](https://github.com/pgvector/pgvector)
[![Celery](https://img.shields.io/badge/celery-enabled-brightgreen.svg)](https://docs.celeryq.dev/)
[![Status: Prototype Demonstration](https://img.shields.io/badge/status-demonstration%20prototype-orange.svg)]()

> **Important Demonstration & Engineering Disclaimer**: Foresight is an advanced analytical prototype built for industrial safety evaluation and demonstration. The machine learning models are trained using synthetic or human-reviewed synthetic incident records. **Human review of synthetic incidents denotes structural audit of generated examples; it is not equivalent to validation against proprietary, production oil & gas HSE archives.** Deterministic safety engines (Energy-Barrier analysis, IOGP Rule mapping, Data Quality gate, Recurrence detection) operate deterministically on provided records.

---

## Table of Contents

1. [Platform Overview & Core Concept](#1-platform-overview--core-concept)
2. [The 3-Stage Safety Information Hierarchy](#2-the-3-stage-safety-information-hierarchy)
3. [System Architecture](#3-system-architecture)
4. [Prerequisites](#4-prerequisites)
5. [Quickstart: Zero to Running in 5 Minutes](#5-quickstart-zero-to-running-in-5-minutes)
6. [Environment Variables (`.env`) Configuration](#6-environment-variables-env-configuration)
7. [Database Setup, Migrations & pgvector](#7-database-setup-migrations--pgvector)
8. [Data Seeding, ML Model Training & Embeddings](#8-data-seeding-ml-model-training--embeddings)
9. [Default Demo Credentials](#9-default-demo-credentials)
10. [Starting the Application Services](#10-starting-the-application-services)
11. [Platform Tour: Key Pages & Demonstration Walkthrough](#11-platform-tour-key-pages--demonstration-walkthrough)
12. [Running Automated Tests](#12-running-automated-tests)
13. [Troubleshooting & Common FAQs](#13-troubleshooting--common-faqs)
14. [Repository Structure](#14-repository-structure)

---

## 1. Platform Overview & Core Concept

**Foresight** is an enterprise-grade safety analytics platform designed to solve one of heavy industry's most critical challenges: **identifying Potential Serious Injury or Fatality (PSIF) precursors before catastrophic loss occurs.**

Most conventional incident reporting systems either bury safety teams in thousands of minor observations or rely on "black box" machine learning models that generate opaque risk scores without technical justification. Foresight replaces black-box scoring with a **True Decision Trace** architecture that bridges natural language processing, deterministic physics-based energy barrier modeling, and human-in-the-loop triage.

### Core Capabilities

- **NLP Precursor Modeling**: DistilBERT semantic embeddings combined with an XGBoost classifier trained to detect latent fatal precursor patterns in free-text event descriptions.
- **Deterministic Energy-Barrier Intelligence**: Evaluates high-energy sources (pressure, electrical, gravitational, mechanical) against physical barriers and line-of-fire worker exposures.
- **IOGP Life-Saving Rules Engine**: Deterministic classification of narratives against the 9 International Association of Oil & Gas Producers (IOGP) Life-Saving Rules.
- **Data Quality & Integrity Gate**: Detects contradictions (e.g., knee trauma mapped to eye injury), placeholder text, and missing operational fields *prior* to evaluation.
- **Cross-Site Recurrence & Similarity**: High-performance semantic vector search using PostgreSQL `pgvector` (`all-MiniLM-L6-v2` embeddings) to group systemic hazards across multiple geographic facilities within 90-day rolling windows.
- **Explainable Feature Attributions (SHAP)**: Explains *which semantic tokens and operational variables* influenced model attention without fabricating causal certainty.

---

## 2. The 3-Stage Safety Information Hierarchy

To prevent misunderstandings between statistical machine learning signals and final operational determinations, Foresight strictly enforces a **3-Stage Information Hierarchy**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. ML MODEL OUTPUT (Statistical Precursor Signal)                           │
│    • DistilBERT + XGBoost Semantic Classifier                              │
│    • Output: Precursor Signal Score (0.000 to 1.000)                        │
│    • Role: Identifies text patterns similar to historical fatalities.       │
│      (Note: This is an uncalibrated ranking score, not a probability).      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. EVIDENCE-BASED SAFETY ASSESSMENT (Deterministic Physical Controls)       │
│    • Energy Source: High-pressure line, suspended load, energized circuit?  │
│    • Worker Exposure: Was personnel in the physical line of fire?           │
│    • Barrier Status: Was the defense breached, degraded, or held intact?    │
│    • Rule Concordance: Was an IOGP Life-Saving Rule matched?                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. FINAL TRIAGE STATUS (Definitive Operational Classification)             │
│    • PSIF: High energy present + worker exposed + barrier failed.           │
│    • PSIF PRECURSOR: Significant precursor condition; near-miss pathway.   │
│    • NOT PSIF (Controls Held): High energy present, BUT barriers held.      │
│    • INSUFFICIENT EVIDENCE: Crucial facts missing; triage review needed.   │
└─────────────────────────────────────────────────────────────────────────────┘
```

> **Why this matters**: A high-pressure gas release might trigger a **0.850 ML Precursor Signal** because the narrative describes hazardous energy. However, if the engineering pressure relief valve activated as designed and the exclusion perimeter was empty, the **Evidence Assessment** confirms controls held, resulting in a **FINAL TRIAGE: NOT PSIF (Controls Held)**. This is correct safety engineering, not a contradiction.

---

## 3. System Architecture

```
                    ┌─────────────────────────┐
                    │  Web Browser / Client   │
                    └────────────┬────────────┘
                                 │ HTTP (8000)
                                 ▼
                     ┌───────────────────────┐
                     │     Django 5.x        │
                     │  (WSGI / Web App)     │
                     └───┬───────────────┬───┘
                         │               │
        ORM / SQL Query  │               │ Celery Async Task
                         ▼               ▼
        ┌───────────────────────┐    ┌───────────────────────┐
        │  PostgreSQL 14+       │    │     Redis Server      │
        │  • Relational Data    │    │  (Broker & Results)   │
        │  • pgvector Cosine Sim│    └───────────┬───────────┘
        └───────────────────────┘                │
                                                 ▼
                                     ┌───────────────────────┐
                                     │     Celery Worker     │
                                     │  • Batch Ingestion    │
                                     │  • Vector Embeddings  │
                                     │  • Model Retraining   │
                                     └───────────────────────┘
```

---

## 4. Prerequisites

Before installing Foresight, verify your environment meets these requirements:

| Component | Minimum Version | Recommended Version | Verification Command |
|---|---|---|---|
| **Python** | 3.12 | **3.14+** | `python3 --version` |
| **PostgreSQL** | 14+ | **15+ / 16+** | `psql --version` |
| **pgvector** | 0.4.0+ | **Latest** | `psql -c "SELECT * FROM pg_extension WHERE extname = 'vector';"` |
| **Redis** | 5.0+ | **7.0+** | `redis-cli ping` (returns `PONG`) |
| **Operating System**| Linux / macOS / WSL2 | macOS (Apple Silicon) or Ubuntu 22.04+ | `uname -s` |

> **Note for macOS Users**: Python 3.14 on macOS requires Celery workers to run with the `-P solo` pool option to avoid unsafe POSIX fork issues with PyTorch/OpenMP. This is already handled automatically in our configuration.

---

## 5. Quickstart: Zero to Running in 5 Minutes

Follow these step-by-step instructions in your terminal:

### Step 1: Clone the Repository & Enter Workspace
```bash
git clone <repository_url>
cd prototype_165
```

### Step 2: Create and Activate a Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```
*(On Windows WSL2 or Git Bash: `source venv/bin/activate`; on Windows PowerShell: `.\venv\Scripts\Activate.ps1`)*

### Step 3: Upgrade pip and Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Local Environment (`.env`)
Copy the template to create your local `.env`:
```bash
cp .env.example .env
```
*(Review [Section 6](#6-environment-variables-env-configuration) below if your database credentials differ from the defaults).*

### Step 5: Initialize PostgreSQL Database & pgvector
Ensure PostgreSQL is running locally, then create the database and enable the vector extension:
```bash
createdb psif_platform
psql -d psif_platform -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Step 6: Apply Database Migrations
```bash
python manage.py migrate
```

### Step 7: Seed Synthetic Demonstration Data
Populate the database with ~750 synthetically generated, domain-specific workplace incidents:
```bash
python manage.py seed_data
```

### Step 8: Train ML Pipeline & Generate Embeddings
Train the DistilBERT + XGBoost model, generate `pgvector` semantic embeddings, and run deterministic audits:
```bash
# 1. Train the PSIF model pipeline and export artifacts to ml_engine/artifacts/
python manage.py train_model

# 2. Compute 384-dimensional dense vector embeddings for similarity search
python manage.py backfill_incident_embeddings

# 3. Deterministically tag IOGP Life-Saving Rules and audit data quality
python manage.py backfill_iogp_tags
python manage.py validate_incident_quality
```

### Step 9: Launch the Application Server
```bash
python manage.py runserver 127.0.0.1:8000
```
Open your browser and navigate to **`http://127.0.0.1:8000/`**.

---

## 6. Environment Variables (`.env`) Configuration

Foresight reads settings via `django-environ`. Here is a reference configuration for local development:

```env
# ─────────────────────────────────────────────────────────────────────────────
# Django Core Settings
# ─────────────────────────────────────────────────────────────────────────────
SECRET_KEY=foresight-development-secret-key-change-in-production-12345
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL Database Connection
# ─────────────────────────────────────────────────────────────────────────────
# Option A: Single Database URL
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/psif_platform

# Option B: Discrete Parameters (Default)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=psif_platform
DB_USER=sas
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432

# ─────────────────────────────────────────────────────────────────────────────
# Redis & Celery (Asynchronous Tasks)
# ─────────────────────────────────────────────────────────────────────────────
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1

# Fast Local Dev Tip: Set to True to run Celery tasks synchronously in-process
# without needing a separate Celery worker terminal!
CELERY_TASK_ALWAYS_EAGER=False
DEV_SYNC_FALLBACK=False

# ─────────────────────────────────────────────────────────────────────────────
# ML & NLP Engine Configuration
# ─────────────────────────────────────────────────────────────────────────────
BERT_MODEL_NAME=distilbert-base-uncased
BERT_BATCH_SIZE=32
PSIF_THRESHOLD=0.5
RISK_LOW_MAX=0.25
RISK_MEDIUM_MAX=0.50
RISK_HIGH_MAX=0.75
ML_ARTIFACTS_DIR=ml_engine/artifacts

# ─────────────────────────────────────────────────────────────────────────────
# Media & Storage
# ─────────────────────────────────────────────────────────────────────────────
MEDIA_ROOT=media
MAX_UPLOAD_SIZE_MB=200
```

---

## 7. Database Setup, Migrations & pgvector

Foresight relies on PostgreSQL with the `pgvector` extension for cosine similarity search over incident narrative embeddings.

### Manual Setup via PostgreSQL CLI (`psql`)
```sql
-- Connect to Postgres
psql -U postgres

-- Create database
CREATE DATABASE psif_platform;

-- Connect to the newly created database
\c psif_platform

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify extension is installed
\dx vector
```

### Running Migrations
```bash
python manage.py migrate
```
If you make changes to models or reset your database, run:
```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 8. Data Seeding, ML Model Training & Embeddings

Foresight includes built-in Django management commands to bootstrap a complete analytical environment:

| Command | Purpose | Expected Runtime | Output / Effect |
|---|---|---|---|
| `python manage.py seed_data` | Generates ~750 realistic synthetic workplace incidents across 12 departments. | ~5 seconds | Populates `Incident` table with balanced PSIF positive/negative examples. |
| `python manage.py train_model` | Trains the DistilBERT tokenization + XGBoost classifier pipeline. | ~30–60 seconds | Writes `model.json`, `tfidf.joblib`, and `metadata.json` to `ml_engine/artifacts/`. |
| `python manage.py backfill_incident_embeddings` | Generates 384-dimensional dense vectors using `all-MiniLM-L6-v2`. | ~1–2 minutes | Populates `IncidentEmbedding` table for fast pgvector similarity queries. |
| `python manage.py backfill_iogp_tags` | Evaluates incident narratives against the 9 IOGP Life-Saving Rules. | ~5 seconds | Populates `iogp_rules` on incidents. |
| `python manage.py validate_incident_quality` | Audits data quality, flagging anatomical contradictions or missing fields. | ~3 seconds | Populates `quality_status` and `quality_flags`. |

---

## 9. Default Demo Credentials

When running the application with the pre-populated seed data, you can authenticate using any of the following accounts:

| Username / Email | Password | Role | Permissions / Purpose |
|---|---|---|---|
| **`admin`** | `admin123` | **Superuser / Platform Admin** | Full access to Django Admin (`/admin/`), all incident queues, models, and analytical tools. |
| **`admin_flow@foresight.app`** | `admin123` | **HSE Demonstration Lead** | Dedicated account for the HSE Administrative Demonstration Flow (`/admin-flow/`). |
| **`verifier_safety`** | `admin123` | **Safety Verifier** | Focused on incident triage review and human confirmation workflows. |

### Creating a Custom Superuser
To create your own custom administrative user:
```bash
python manage.py createsuperuser
```
Follow the interactive prompts to specify a username, email, and password.

---

## 10. Starting the Application Services

Depending on your workflow, you can run Foresight in **Single-Terminal Mode** (fastest) or **Standard Multi-Process Mode** (with Celery & Redis).

### Option A: Single-Terminal Mode (Zero Redis Setup)
If you do not have Redis installed or want the simplest possible setup:
1. In your `.env` file, set:
   ```env
   CELERY_TASK_ALWAYS_EAGER=True
   DEV_SYNC_FALLBACK=True
   ```
2. Start the Django web server:
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```
*All background tasks (file processing, embedding computation) will execute synchronously in-process.*

---

### Option B: Standard Multi-Process Mode (Full Async Stack)

Open two terminal windows:

#### Terminal 1: Background Worker (Redis + Celery)
Ensure Redis is running:
```bash
# Start Redis (macOS Homebrew)
brew services start redis
# Or run in foreground:
redis-server
```
Then start the Celery worker from the project root:
```bash
source venv/bin/activate
celery -A config worker --loglevel=info -P solo
```
> **Note**: The `-P solo` pool flag is critical on macOS to prevent OpenMP/PyTorch deadlocks during Celery worker execution.

#### Terminal 2: Web Server (Django)
```bash
source venv/bin/activate
python manage.py runserver 127.0.0.1:8000
```

---

## 11. Platform Tour: Key Pages & Demonstration Walkthrough

Once running, access `http://127.0.0.1:8000/` and log in with `admin` / `admin123`.

### 1. Executive Portfolio Risk Dashboard (`/` or `/dashboard/`)
- **Metric KPI Cards**: Real-time rollups of total incidents, prediction-eligible records, records with insufficient evidence, PSIF candidates, and non-PSIF records.
- **Systemic Recurrence Widget**: Live cross-site recurrence clusters surfacing identical failure patterns across different facilities within 90 days.
- **IOGP Life-Saving Rules Distribution**: Interactive breakdown of risk exposure by rule category.

### 2. Incident Queue & Triage Workbench (`/incidents/`)
- Filterable and searchable table of all reported safety events.
- Filter by department, location, severity, IOGP rule, or PSIF status.
- Direct indicators of data quality status (Verified vs Warnings).

### 3. Incident Deep-Dive & Reasoning Trace (`/incidents/<uuid>/`)
- Select any incident (e.g. from the top PSIF candidates).
- Inspect the **3-Stage Information Hierarchy**:
  1. **ML Model Precursor Signal** (with uncalibrated score gauge and SHAP feature contributions).
  2. **Evidence-Based Safety Assessment** (Energy source, worker exposure line-of-fire, barrier status, and verbatim quote anchor).
  3. **Final Triage Classification** (`PSIF`, `PSIF Precursor`, `NOT PSIF (Controls Held)`, etc.).
- Explore **Related Incidents (Vector Search)**: Real-time cosine similarity search retrieving historical precedents from `pgvector`.

### 4. Interactive Live PSIF Predictor (`/predictions/predict/`)
- Test the ML model in real-time by entering arbitrary incident narratives (e.g., *"Worker unbolting 4-inch high pressure gas line without locking out bleed valve; line vented with high force..."*).
- Click **Predict PSIF** to immediately receive:
  - Model Precursor Score
  - Energy Source Extraction
  - IOGP Life-Saving Rule Match
  - SHAP Token Attributions

### 5. HSE Demonstration Flow (`/admin-flow/`)
- A dedicated sequential walkthrough designed specifically for executive presentations and evaluators.
- Visit `/admin-flow/psif/` for the complete Energy-Barrier Workbench and `/admin-flow/patterns/` for cross-facility hazard analysis.

### 6. Django Administration Portal (`/admin/`)
- Direct low-level administrative inspection of database models, user roles, audit logs, and raw embeddings.

---

## 12. Running Automated Tests

Foresight includes an extensive test suite verifying:
- ML pipeline inference, tokenization, and SHAP explainability.
- Deterministic energy-barrier reasoning logic.
- Data quality validation and anomaly detection.
- Cross-site similarity and `pgvector` queries.
- API endpoints and authentication guards.

### Run the Full Test Suite
```bash
pytest
```

### Run Specific Test Modules
```bash
# Test the 3-Stage Information Hierarchy UI
pytest tests/test_psif_triage_hierarchy_ui.py

# Test Energy-Barrier Intelligence logic
pytest tests/test_barrier_intelligence.py

# Test Machine Learning pipeline inference
pytest tests/test_ml_pipeline.py

# Test Data Quality validation rules
pytest tests/test_data_integrity.py
```

---

## 13. Troubleshooting & Common FAQs

### 1. `django.db.utils.OperationalError: extension "vector" does not exist`
**Cause**: The PostgreSQL `pgvector` extension is not installed on your system.  
**Resolution**:
- **macOS (Homebrew)**: `brew install pgvector`
- **Ubuntu/Debian**: `sudo apt install postgresql-15-pgvector` (match your PG version)
- **Within Database**: Connect via `psql -d psif_platform` and run `CREATE EXTENSION vector;`.

### 2. Celery Worker crashes on macOS with `SIGABRT` or `+[__NSPlaceholderDate initialize]`
**Cause**: macOS security restrictions prohibit POSIX `fork()` in processes that initialize macOS Foundation or Accelerate libraries (used by PyTorch / NumPy / XGBoost).  
**Resolution**: Always specify the solo execution pool:
```bash
celery -A config worker --loglevel=info -P solo
```

### 3. Redis Connection Refused (`Error 61 connecting to 127.0.0.1:6379`)
**Cause**: Redis server is not running or port is blocked.  
**Resolution**:
- Start Redis via `brew services start redis` or `redis-server`.
- Alternatively, run without Redis by setting `CELERY_TASK_ALWAYS_EAGER=True` in `.env`.

### 4. `FileNotFoundError: No such file or directory: 'ml_engine/artifacts/model.json'`
**Cause**: The ML model artifacts have not yet been trained or generated.  
**Resolution**: Run the training management command:
```bash
python manage.py train_model
```

### 5. Port 8000 is already in use
**Cause**: Another process is occupying port 8000.  
**Resolution**: Bind Django to an alternative port:
```bash
python manage.py runserver 127.0.0.1:8080
```

---

## 14. Repository Structure

```
prototype_165/
├── apps/
│   ├── accounts/             # Authentication, user roles & permissions
│   ├── admin_flow/           # Dedicated HSE evaluation & demonstration flow
│   ├── datasets/             # Dataset management, ingestion & validation
│   ├── incidents/            # Core Incident models, pgvector embeddings & views
│   └── predictions/          # ML inference views, prediction models & SHAP engine
├── config/
│   ├── settings/
│   │   ├── base.py           # Core settings, database, celery & ML parameters
│   │   ├── dev.py            # Local development settings
│   │   └── prod.py           # Production-ready configuration
│   ├── urls.py               # Top-level URL routing table
│   ├── wsgi.py               # WSGI application entrypoint
│   └── celery.py             # Celery app initialization
├── ml_engine/
│   ├── artifacts/            # Trained XGBoost model, vectorizers & feature metadata
│   ├── model_inference.py    # Real-time scoring, confidence bounds & SHAP
│   ├── model_training.py     # Training routines (DistilBERT + XGBoost)
│   └── text_preprocessing.py # Narrative cleaning & composite tokenization
├── static/                   # Compiled CSS, JavaScript, icons & design system assets
├── templates/                # Server-rendered HTML templates with Tailwind styling
├── tests/                    # Comprehensive pytest test suite (100+ tests)
├── docs/                     # Architectural specs, runbooks & deployment assessments
├── manage.py                 # Django command-line utility
├── requirements.txt          # Pinned Python package dependencies
├── .env.example              # Environment variable configuration template
└── README.md                 # Project documentation (this file)
```

---

## License & Team

Developed by **Team Oblivion** for the **Smart India Hackathon (SIH)**.  
For technical support or architecture deep-dives, consult [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md).
