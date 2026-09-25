# Current State Architecture Audit — PSIF Platform

*Date: September 2026*
*Scope: Full System Audit verifying existing architecture, schema, APIs, ML pipeline, RBAC, and Test Coverage.*

## 1. System Architecture & Dependency Stack
- **Web Framework**: Django 5.x with Django Rest Framework (DRF).
- **Asynchronous Tasks**: Celery (using Redis as the implied broker) for dataset ingestion and model retraining.
- **ML Engine**: XGBoost classifier integrated with HuggingFace `transformers` (`distilbert-base-uncased`) for text embeddings.
- **Frontend**: Server-side rendered Django templates augmented with Vanilla JavaScript (`static/js/main.js`, `upload.js`, `status.js`).

## 2. Database Schema & Models
Verified against actual `models.py` files:
- **`accounts`**: Implements custom User model.
- **`datasets`**: Defines `Dataset` model tracking lifecycle statuses (`PENDING`, `PROCESSING`, `COMPLETED`).
- **`incidents`**: Defines `Incident` model. **Confirmed**: `is_psif_human_label` exists. The label policy (human > heuristic > unlabeled) is implemented natively on the model.
- **`predictions`**: Defines `ModelVersion` to track XGBoost artifacts, metrics, and `is_active` flags.
- **`dashboard`**: No database models exist; views aggregate data dynamically from `incidents`.

## 3. Backend API Surface
The system heavily utilizes DRF. Verified endpoints:
- **Datasets** (`/api/datasets/`): `GET` list, `POST upload/`, `GET <pk>/status/`, `POST <pk>/column-mapping/`, `POST <pk>/process/`.
- **Incidents** (`/api/incidents/`): `GET` list, `GET <pk>/`.
- **Predictions** (`/api/predictions/`): `POST` manual inference endpoint.
- **Models** (`/api/predictions/models/`): `GET` list, `POST retrain/`.
- **Dashboard** (`/api/dashboard/`): `GET summary/`, `GET trend/`.

## 4. Auth, RBAC, and "Login Confusion"
Investigation into the reported "three login types" reveals:
- There are exactly **two** functional login flows:
  1. User Login: `templates/accounts/login.html` (routed at `/accounts/login/`).
  2. Admin Login: Standard Django admin portal (routed at `/admin/login/`).
- A third route `api/auth/` is defined in `config/urls.py`, but it is currently an empty stub (`[]` in `apps.accounts.api_urls.py`).
- **Conclusion**: The confusion is likely due to the split between Django Admin, standard user views, and the unimplemented DRF authentication endpoints.

## 5. ML Pipeline & Explainability
- **Preprocessing**: `text_preprocessing.py` correctly concatenates `description`, `corrective_actions`, and `witness_statement`.
- **Feature Fusion**: 
  - *Training* (`ml_engine/training/trainer.py:578`): `X_fused_train = np.hstack([X_bert_train, X_struct_train])`
  - *Inference* (`ml_engine/model_inference.py:212`): `fused = np.concatenate([bert_vec, struct_vec])`
  - **Conclusion**: The fusion order is guaranteed to match (`[BERT, Structured]`).
- **Explainability Bug (Phase 10 Audit)**:
  - The feature arrays passed to SHAP are in the correct order.
  - The root cause of the silent explainability failure is a broad exception handler in `ml_engine/model_inference.py:148` (`except Exception as exc: return []`) inside `_compute_shap_top_factors`. When SHAP encounters a `ValueError` (due to feature name mismatch between the numpy-trained XGBoost booster and the explicitly named `DMatrix` used for inference), it silently swallows the error and returns an empty list, resulting in a blank explainability panel.
- **Demo Calibration**: A prominent "SIH DEMO CALIBRATION" block exists in `ml_engine/model_inference.py` (lines 217-257), aggressively overriding model output probabilities using hardcoded keyword heuristics.

## 6. Test Coverage
- **Total Tests**: `115` tests collected via `pytest`.
- **Coverage Areas**: Comprehensive coverage of API endpoints, serializers, celery ingestion, model training (run in isolated subprocesses to avoid FFI segfaults), and security policies.
- **Explainability Test**: An explicit regression test **does exist** (`tests/test_explainability_regression.py::test_explainability_regression`) which asserts that different incidents produce different SHAP `top_factors`. 
- **Status**: This test is currently **FAILING** (`AssertionError: Identical top factors!`), correctly catching the bug described above.

## 7. Frontend Integration
- Templates are modularized by app within the `templates/` directory (e.g., `templates/dashboard/home.html`, `templates/incidents/list.html`).
- Frontend logic correctly fetches from the DRF API using standard Vanilla JS `fetch()` requests without relying on heavyweight frontend frameworks.
