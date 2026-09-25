# System Architecture

Foresight is built on a robust, asynchronous Python stack designed to ingest bulk safety reports, perform heavy machine learning inference, and store the results for dashboard analytics.

## Component Flow Overview

```text
Browser (HTML/JS/CSS)
       │
       ▼
Django / DRF (Web Server)
       │
       ▼
PostgreSQL (Transactional Store & pgvector) ──► ML Artifacts (Local/Volume)
       │
       ▼
Celery (Task Queue)
       │
       ▼
Redis (Message Broker & Result Backend)
```

## Analytical Modules

Foresight consists of several distinct analytical modules working in sequence (The **True Decision Trace**):

1. **Data Quality Layer**: Deterministic validation engine (`apps/incidents/services/data_quality.py`) catching logical contradictions in raw inputs before model inference.
2. **IOGP Classification**: Rule-based engine (`apps/incidents/services/iogp_classifier.py`) identifying potential Life-Saving Rule violations.
3. **PSIF Prediction**: Fused DistilBERT + XGBoost pipeline for PSIF scoring.
4. **Evidence & Explainability**: `shap.TreeExplainer` providing feature attribution.
5. **Similarity Search**: `all-MiniLM-L6-v2` embeddings in PostgreSQL (`pgvector`) returning highly similar historical incidents.
6. **Recurrence Detection**: Analytical engine mapping temporal and multi-site patterns based on similarity thresholds.

## Dataset Ingestion & Batch Prediction Path

Handling bulk uploads synchronously is impossible due to memory constraints and HTTP timeouts. The workflow is:

1. **Upload**: User uploads a CSV/JSON/JSONL dataset via Django.
2. **Dispatch**: Django validates the schema, maps columns, and dispatches a parent processing task to Celery.
3. **Chunking**: The Celery task (`process_dataset_task`) chunks the dataset using streaming parsers (like `ijson` or pandas chunking) to prevent memory exhaustion.
4. **Encoding**:
   - The ML Pipeline utilizes a pre-trained **DistilBERT** encoder to mean-pool narrative text.
   - Categorical/numerical features are processed by a fitted structured encoder.
5. **Inference**: Both representations are fused and fed into an **XGBoost** classifier.
6. **Persistence**: The resulting `PredictionResult` objects, containing the PSIF Model Score and structured explanations from **SHAP (TreeExplainer)**, are persisted to PostgreSQL.
7. **Analytics**: The Dashboard queries PostgreSQL to aggregate these results.

## Manual Prediction Path

For real-time triage of a single incident:

1. User enters incident data into the Manual Prediction UI.
2. Django triggers `_predict_single()` synchronously against the active `ModelVersion` loaded in memory.
3. The response returns immediately with PSIF Model Score, Prioritization Band, and SHAP top contributing factors.
4. The result is optionally persisted as a real `PredictionResult` tying back to the manual submission.

## Model Lifecycle & Persistence

1. **ModelVersion**: A Django model tracking the metadata, active state, and file paths of ML artifacts.
2. **Artifacts**: Stored physically on disk (e.g., `ml_engine/artifacts/v_20260901_072752/`). Contains:
   - `model.json` (XGBoost weights)
   - `encoder.joblib` (Scikit-Learn fitted scaler/encoder)
   - `metadata.json` (Thresholds, feature lists, BERT dims)
3. **Reloading**: The application lazily caches the loaded models in-memory. Only one `ModelVersion` can be `is_active=True` at any time.

## Retry and Idempotency

Celery chunk processors are inherently designed to resume gracefully. If a batch fails, standard Celery retry mechanics can engage. Errors during parsing are gracefully recorded in a `JSONField` error log on the Dataset object, preventing one bad row from failing the entire batch.

## Security & Permissions

Django handles session authentication, backed by role-level restrictions:
- Admin routes are protected by `@role_required('admin')` logic (or DRF Permission classes).
- Bulk modifications ensure tenants cannot view each other's datasets (though currently, it is a single-tenant architecture with global visibility based on Role).
