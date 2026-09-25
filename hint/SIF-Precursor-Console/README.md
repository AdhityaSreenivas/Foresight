# SIF Precursor Console

A Django-based AI-powered **Safety Incident Classification System** that analyses industrial safety reports and identifies **Serious Injury or Fatality (SIF) Precursors** using a multi-model ML pipeline built on RoBERTa embeddings and XGBoost classifiers.

---

## What the System Does

The SIF Precursor Console allows safety professionals to:

1. **Submit free-text safety incident reports** via a web interface.
2. **Automatically classify** each report as `SIF-POTENTIAL`, `NON-SIF`, or `ACTUAL FATAL EVENT`.
3. **Identify Life-Saving Rules (LSR)** violated in the incident (e.g., Energy Isolation, Confined Space, Working at Height).
4. **Detect hazardous activity type** (e.g., Lifting Operation, Hot Work, Driving).
5. **Highlight precursor signals and barrier failures** extracted from the report text.
6. **Assign a risk level** (`CRITICAL`, `HIGH`, `MEDIUM`, or `LOW`).
7. **Generate recommendations** for corrective action.
8. **Store all reports** in a PostgreSQL database for historical review and pattern analytics.
9. **Batch upload** reports via `.txt`, `.csv`, `.docx`, or `.pdf` files.
10. **Pattern analytics dashboard** – aggregates top precursors, barrier failures, LSR distributions, and activity trends from stored reports.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Web Framework | Django 5.2 |
| Database | PostgreSQL (via psycopg 3) |
| Embedding Model | `roberta-base` (HuggingFace Transformers) |
| ML Classifiers | XGBoost (via scikit-learn pipeline) |
| Model Serialisation | joblib |
| Numeric Computing | NumPy |
| File Parsing | pypdf, python-docx |
| Python Version | **3.14** |

---

## Project Structure

```
SIF-Precursor-Console/
│
├── manage.py                    # Django entry point
├── requirements.txt             # All Python dependencies
├── .python-version              # Python 3.14 (used by pyenv/uv)
├── .env.example                 # Template for environment variables (copy to .env)
├── train.py                     # Root-level SIF classifier training script
│
├── config/                      # Django project settings
│   ├── settings.py              # ⚠️  Requires environment variable configuration (see below)
│   ├── urls.py                  # Root URL dispatcher
│   ├── wsgi.py
│   └── asgi.py
│
├── core/                        # Main Django application
│   ├── models.py                # DB models: Organization, Site, Report, Prediction, SafetyReport
│   ├── views.py                 # All request handlers (home, analyze, upload, history, analytics)
│   ├── urls.py                  # App URL patterns
│   ├── admin.py                 # Django admin registrations
│   ├── apps.py
│   ├── file_parser.py           # Handles TXT / CSV / DOCX / PDF upload parsing
│   ├── ai_model.py              # Rule-based SIF classification fallback
│   ├── tests.py                 # Django test placeholder
│   │
│   ├── migrations/              # All Django DB migrations (run these to set up schema)
│   │   ├── 0001_initial.py
│   │   ├── 0002_...
│   │   ├── 0003_...
│   │   ├── 0004_safetyreport.py
│   │   └── 0005_safetyreport_activity_and_more.py
│   │
│   ├── templates/core/          # Django HTML templates
│   │   ├── index.html           # Main SIF console UI (~50 KB)
│   │   └── register.html        # User registration page
│   │
│   └── ml/                      # ML pipeline modules
│       ├── pipeline.py          # Orchestrates all ML steps (main entry point)
│       ├── embed.py             # RoBERTa mean-pooled embedding (768D)
│       ├── classify.py          # SIF binary classifier (sif_classifier.joblib)
│       ├── lsr_classifier.py    # LSR multi-class classifier (lsr_classifier.joblib)
│       ├── activity_classifier.py  # Activity classifier (activity_classifier.joblib)
│       ├── precursor.py         # Keyword-based precursor + barrier failure detection
│       ├── evidence.py          # Evidence sentence extraction
│       ├── lsr.py               # LSR keyword mapping fallback
│       ├── ner.py               # Named-entity / barrier NER rules
│       ├── preprocess.py        # Text cleaning utility
│       ├── train_all_models.py  # Training script: LSR + Activity classifiers
│       ├── train_model.py       # Training script: SIF binary classifier (detailed)
│       └── data/
│           └── training_data.jsonl   # Full labelled training dataset (~9 MB, ~10k records)
│
├── models_store/                # Trained ML model artifacts (required at runtime)
│   ├── sif_classifier.joblib    # SIF binary classifier (~306 KB)
│   ├── lsr_classifier.joblib    # LSR multi-class classifier (~2 MB)
│   └── activity_classifier.joblib  # Activity classifier (~8 MB)
│
└── test_*.py                    # Standalone test scripts (not Django test suite)
```

---

## ⚠️  Important Security Notice

The `.env` file is **intentionally NOT included** in this package.

The original `config/settings.py` currently contains **hardcoded PostgreSQL credentials** (developer's local database). Before running this project, you **must** update `settings.py` to read from environment variables, or directly replace the database block with your own credentials.

**Required environment / configuration values:**

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key (must be a long random string) |
| `DEBUG` | `True` for development, `False` for production |
| `DB_NAME` | PostgreSQL database name (e.g. `sif_console_db`) |
| `DB_USER` | PostgreSQL username |
| `DB_PASSWORD` | PostgreSQL password |
| `DB_HOST` | PostgreSQL host (e.g. `localhost`) |
| `DB_PORT` | PostgreSQL port (default `5432`) |

---

## Setup Guide

### 1. Python Version

This project uses **Python 3.14**. Install it via [pyenv](https://github.com/pyenv/pyenv):

```bash
pyenv install 3.14
pyenv local 3.14
```

Or use [uv](https://docs.astral.sh/uv/) which reads `.python-version` automatically.

---

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> **Note on PyTorch:** The `torch==2.13.0` listed is the CPU build. If you have an NVIDIA GPU and want CUDA acceleration for the RoBERTa embedding step, install the appropriate CUDA-enabled wheel from https://pytorch.org/get-started/locally/.

> **Note on `roberta-base`:** The model is downloaded automatically from HuggingFace on first run (~500 MB). Ensure internet access or pre-download it.

---

### 4. PostgreSQL Setup

Install PostgreSQL 14+ and create the database:

```sql
CREATE DATABASE sif_console_db;
CREATE USER your_db_user WITH PASSWORD 'your_db_password';
GRANT ALL PRIVILEGES ON DATABASE sif_console_db TO your_db_user;
```

---

### 5. Configure Environment Variables

**Option A – Edit `settings.py` directly (quick start):**

Open `config/settings.py` and replace the `DATABASES` block and `SECRET_KEY` with your own values.

**Option B – Use environment variables (recommended):**

Install `python-decouple` or `django-environ`, then update `settings.py` to read from `.env`:

```bash
cp .env.example .env
# Edit .env and fill in your database credentials and secret key
```

---

### 6. Run Migrations

```bash
python manage.py migrate
```

This creates all tables for `Organization`, `Site`, `Report`, `Prediction`, and `SafetyReport` models.

---

### 7. Create a Django Superuser (optional)

```bash
python manage.py createsuperuser
```

---

### 8. Start the Django Development Server

```bash
python manage.py runserver
```

Open your browser at: **http://127.0.0.1:8000/**

---

## Where the Trained Models Are Located

All models are stored in the `models_store/` directory:

| File | Purpose | Size |
|---|---|---|
| `sif_classifier.joblib` | Binary SIF / NON-SIF classifier | ~306 KB |
| `lsr_classifier.joblib` | Multi-class Life-Saving Rule classifier | ~2 MB |
| `activity_classifier.joblib` | Activity type classifier (16 classes) | ~8 MB |

The models are loaded at Django startup time (when `core/ml/classify.py`, `lsr_classifier.py`, and `activity_classifier.py` are imported). They are kept in memory for the lifetime of the server process.

---

## How the AI Pipeline Works

Each report text submitted via the API goes through the following steps inside `core/ml/pipeline.py`:

```
Report Text (string)
        │
        ▼
 1. RoBERTa Embedding (roberta-base)
    Mean-pooled 768-dimensional vector
        │
        ├──▶ 2. SIF Classifier (XGBoost)
        │       → classification: SIF-POTENTIAL / NON-SIF
        │       → sif_probability, non_sif_probability, confidence
        │
        ├──▶ 3. LSR Classifier (XGBoost)
        │       → life_saving_rule (8 classes)
        │       → Falls back to keyword matching if ML confidence < 0.50
        │
        ├──▶ 4. Activity Classifier (XGBoost)
        │       → activity (16 classes, e.g. "Confined Space Entry", "Hot Work")
        │       → Falls back to "General Operations" if confidence < 0.20
        │
        ├──▶ 5. Precursor Detection (rule-based NLP)
        │       → Keyword pattern matching against 9 precursor categories
        │       → Returns list with severity: CRITICAL / HIGH / MEDIUM
        │
        ├──▶ 6. Evidence Extraction
        │       → Finds sentences containing precursor keywords
        │
        ├──▶ 7. Barrier Failure Extraction
        │       → Regex + phrase matching for missing controls
        │
        └──▶ 8. Risk Level Aggregation
                → CRITICAL > HIGH > MEDIUM > LOW
                → Based on precursor severity and SIF probability
```

The final result is returned as a JSON object and stored in the `SafetyReport` PostgreSQL table.

---

## Reproducing / Retraining the Models

### Retrain SIF Binary Classifier

```bash
python train.py
# Uses: core/ml/data/training_data.jsonl
# Saves: models_store/sif_classifier.joblib
```

### Retrain LSR + Activity Classifiers

```bash
python core/ml/train_all_models.py
# Uses: core/ml/data/training_data.jsonl
# Saves: models_store/lsr_classifier.joblib
#        models_store/activity_classifier.joblib
```

> Training generates RoBERTa embeddings for the full dataset (~10k records). This step is slow on CPU (30–60 min). Embeddings are cached to `models_store/embeddings/` automatically for subsequent runs.

---

## API Endpoints

| URL | Method | Description |
|---|---|---|
| `/` | GET/POST | Main console UI |
| `/analyze/` | POST | Submit report text → JSON analysis result |
| `/upload-reports/` | POST | Upload .txt/.csv/.docx/.pdf for batch analysis |
| `/history/` | GET | Retrieve all stored SafetyReport records as JSON |
| `/analytics/` | GET | Pattern analytics aggregated from all reports |
| `/register/` | GET/POST | User registration |
| `/login/` | GET/POST | User login |
| `/logout/` | GET | Log out |
| `/admin/` | GET | Django admin panel |

---

## Known Notes

- The **`roberta-base`** model (~500 MB) is downloaded from HuggingFace on first startup if not cached locally. Set `TRANSFORMERS_CACHE` or `HF_HOME` environment variable to control cache location.
- The project uses **`psycopg` v3** (not the older `psycopg2`). Ensure your PostgreSQL server is version 10+.
- `test_pipeline.py` in the root references an older API (`analyze_report`) that no longer exists in `pipeline.py`. It is kept as historical reference. Use `run_pipeline()` from `core.ml.pipeline` for current usage.
- The original `requirements.txt` in the source repository only listed LangChain packages (not used by the current application). The `requirements.txt` in this share package is the **corrected, complete version** derived from the active virtual environment.
