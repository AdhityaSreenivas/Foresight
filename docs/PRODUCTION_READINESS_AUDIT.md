# Foresight — Production Readiness Audit

**Project:** Foresight  
**Team:** Team Oblivion  
**Date:** September 2026  
**Audit Purpose:** Full repository architecture inventory, dependency catalog, asset audit, and artifact preservation classification.

---

## 1. Complete Architecture Inventory

### 1.1 Django Applications (`apps/`)

| Application | Core Responsibility | Key Services & Engines | Primary Models |
| :--- | :--- | :--- | :--- |
| **`apps.accounts`** | User authentication, RBAC, workspace tenancy flags (`is_admin_flow`). | Authentication backends, session decorators. | `User` (custom `AbstractUser`) |
| **`apps.datasets`** | File ingestion (CSV, JSON, JSONL), column mapping, normalization, chunked Celery ingestion. | `DatasetIngestionService`, `estimate_row_count`, `DataQualityReportService`. | `Dataset`, `ColumnMapping` |
| **`apps.incidents`** | Incident records, data quality audit, baseline analytics, filtering. | `DQAuditService`, `IncidentValidationService`. | `Incident`, `DataQualityAudit` |
| **`apps.predictions`**| ML inference (DistilBERT + XGBoost), SHAP explainability, model retraining orchestration, model assurance. | `get_active_predictor()`, `ModelRetrainer`, `SHAPExplainer`. | `Prediction`, `ModelVersion`, `AssuranceMetric` |
| **`apps.dashboard`** | Enterprise executive dashboard, cross-site intelligence, recurrence analysis, HSE review workflows. | `CrossSiteIntelligenceEngine`, `RecurrenceService`, `HSEReviewWorkflow`. | `ReviewAction`, `InvestigationNote` |
| **`apps.admin_flow`**| Self-contained evaluator demonstration workspace, live processing dashboard, deterministic pattern intelligence. | `ActivityEngine`, `BarrierEngine`, `LocationEngine`, `IOGPClassifier`. | Isolated records using `workspace_id="admin_flow"` |

---

### 1.2 Deterministic Pattern Engines vs. ML PSIF Engine

- **PSIF ML Engine (`apps/predictions/` & `ml_engine/`):**
  - **Model:** DistilBERT embeddings (`distilbert-base-uncased`) + Structured Features + XGBoost Classifier (`xgboost_model.json`).
  - **Explainability:** TreeSHAP (`shap.TreeExplainer`).
  - **Semantics:** 3-state output (`PSIF`, `NOT PSIF`, `INSUFFICIENT INFORMATION`).
  - **Artifacts:** `ml_engine/artifacts/` (`xgboost_model.json`, `label_encoders.joblib`, `scaler.joblib`, `feature_names.json`).

- **Pattern Engines (`apps/admin_flow/`):**
  - **Activity Pattern Engine (`activity_engine.py`):** Deterministic extraction of operational activities from structured fields with fallback to narrative regex matching.
  - **Barrier Intelligence Engine (`barrier_engine.py`):** Deterministic control extraction with strict partition between **Deficient/Failed** controls (flagged for intervention) and **Effective** safeguards (prevented escalation).
  - **Location Pattern Engine (`location_engine.py`):** Hierarchical facility/unit extraction and normalization across physical sites.
  - **IOGP Life-Saving Rules Engine (`iogp_engine.py`):** 9 canonical IOGP rules mapped via deterministic keyword/pattern dictionaries.

---

### 1.3 Asynchronous Processing & Celery Architecture

- **Broker:** Redis (`CELERY_BROKER_URL`, default DB 0).
- **Backend:** Redis (`CELERY_RESULT_BACKEND`, default DB 1).
- **Tasks (`apps/datasets/tasks.py`, `apps/predictions/tasks.py`):**
  - `process_dataset_task`: Chunks incoming CSV/JSON uploads, streams records via `ijson` / `pandas`, updates progress bars, handles cooperative cancellation (`cancel_requested`).
  - `retrain_model_task`: Asynchronously trains candidate XGBoost models, computes assurance metrics, updates `ModelVersion`.
- **Worker Configuration:** Dedicated persistent worker service using `celery -A config worker --loglevel=info --concurrency=2 -P solo`.

---

## 2. Inventory Classification (A through E)

### A. Definitely Used (Core Runtime Components)
- `apps/accounts/` (all models, views, templates, URLs, migrations)
- `apps/datasets/` (all models, tasks, ingestion pipeline, views, migrations)
- `apps/incidents/` (all models, views, DQ services, migrations)
- `apps/predictions/` (all models, tasks, ML inference pipeline, SHAP services, migrations)
- `apps/dashboard/` (all models, views, cross-site analytics, migrations)
- `apps/admin_flow/` (all models, engines, services, views, URLs, migrations)
- `config/` (`settings/base.py`, `settings/dev.py`, `settings/prod.py`, `urls.py`, `wsgi.py`, `asgi.py`, `celery.py`, `views.py`)
- `templates/` (all HTML templates in `accounts/`, `admin_flow/`, `dashboard/`, `datasets/`, `incidents/`, `predictions/`)
- `static/` (`css/main.css`, `css/admin_flow_reference.css`, `js/chart.umd.min.js`)
- `ml_engine/` (`model_inference.py`, `artifacts/`)
- `tests/` (all frozen test suites in `tests/`)
- `manage.py`, `pytest.ini`, `requirements.txt`, `pyrightconfig.json`, `.gitignore`, `.env.example`
- Deployment descriptors: `vercel.json`, `build_files.sh`, `.python-version`

### B. Probably Used / Supporting Assets
- `sample_incidents.csv`: Baseline benchmark incident data used for seeding and demonstrations.
- `docs/`: Reference specifications and runbooks for evaluation and operational continuity.
- `scripts/`: Benchmark runners, verification harnesses, and measurement tools (`measure_reasoning_performance.py`, `generate_golden_fixtures.py`, `forensic_auditor.py`).

### C. Reference Artifacts Retained for Traceability (Not Imported at Runtime)
- `live-counting-and-iogp-dashboard/`: Upstream reference UI prototypes from which `apps/admin_flow` views and stylesheets were adapted. Retained intact for design lineage; excluded from static collection.
- `scratch/`: Diagnostic forensic records from initial architecture verification (`verify_pipeline_repair_e2e.py`).

### D. Definitely Dead (Safely Removed)
- `FORESIGHT_FRONTEND_ONLY.zip`: Temporary export bundle (deleted).
- `foresight_frontend.zip`: Temporary export bundle (deleted).
- `foresight_frontend_all_templates.zip`: Temporary export bundle (deleted).
- `foresight_frontend_single.zip`: Temporary export bundle (deleted).
- `test_est.py`, `test_est2.py`, `test_est3.py`: Scratch estimation tests (deleted).
- `extract_tasks.py`: Scratch AST parsing script (deleted).
- `inspect_repo.py`: Scratch model inspector (deleted).
- `list_models.py`: Scratch DB query script (deleted).
- `run_explainability_debug.py`: Scratch SHAP debug harness (deleted).
- `test_24.csv`, `test_24_no_newline.csv`, `test_24_trailing.csv`, `test_cancel_disposable.csv`, `test_mixed.csv`, `test_quoted.csv`, `test_r.csv`: Scratch CSV test files (deleted).
- Local `.DS_Store` OS metadata files (deleted).

### E. Preserved Intentionally Under Preservation Rules
- All existing migrations across all 6 applications.
- All pre-trained ML model artifacts (`ml_engine/artifacts/`).
- All test fixtures (`tests/fixtures/`).
- Database schema definitions (no migrations added, squashed, or altered).
