# Foresight API Documentation

All primary API interactions with the Foresight platform are authenticated. Unauthenticated requests will return `403 Forbidden`.

## Base URLs
- All UI routes follow `/<module>/...`
- All API routes follow `/api/<module>/...`

---

## 1. Datasets

### Upload Dataset
- **Method**: `POST`
- **URL**: `/api/datasets/upload/`
- **Permissions**: Admin only.
- **Request**: `multipart/form-data` with a `file` field (CSV, JSON, JSONL).
- **Response**: `201 Created`
  ```json
  {
    "id": 1,
    "name": "sample_incidents.csv",
    "status": "pending_mapping"
  }
  ```

### Suggest Column Mapping
- **Method**: `GET`
- **URL**: `/api/datasets/<id>/suggest_mapping/`
- **Permissions**: Admin only.
- **Response**: `200 OK`
  Returns a suggested map linking CSV headers to Canonical fields (e.g. `Incident Date` -> `date`).

### Start Processing
- **Method**: `POST`
- **URL**: `/api/datasets/<id>/process/`
- **Permissions**: Admin only.
- **Request**: JSON payload containing `column_mapping`.
  ```json
  {
    "column_mapping": {
      "Narrative": "narrative_content",
      "Severity": "severity_level"
    }
  }
  ```
- **Response**: `202 Accepted`
  Indicates the Celery processing task has been dispatched.

### Dataset Status
- **Method**: `GET`
- **URL**: `/api/datasets/<id>/status/`
- **Permissions**: Admin, Safety Officer, Analyst.
- **Response**: `200 OK`
  ```json
  {
    "status": "processing",
    "total_rows": 1000,
    "processed_rows": 500,
    "error_rows": 0,
    "progress_percentage": 50
  }
  ```

---

## 2. Predictions & Models

### Manual Single Prediction
- **Method**: `POST`
- **URL**: `/api/predict/`
- **Permissions**: Admin, Safety Officer, Analyst.
- **Request**: JSON containing incident details.
  ```json
  {
    "date": "2026-09-01",
    "department": "Maintenance",
    "severity_level": "Serious",
    "incident_type": "Fall",
    "narrative_content": "Worker fell from scaffold..."
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "psif_predicted": true,
    "psif_score": 0.89,
    "prioritization_band": "critical",
    "top_factors": [
      {"feature": "severity_level_Serious", "contribution": 1.2, "direction": "positive"}
    ],
    "model_version": "v_20260901_072752",
    "incident_id": 42
  }
  ```

### Retrain Model
- **Method**: `POST`
- **URL**: `/api/models/retrain/`
- **Permissions**: Admin only.
- **Response**: `202 Accepted`
  Indicates the async retraining task has started.

---

## 3. Common Error Responses

- **400 Bad Request**: Invalid JSON payload, malformed mapping, or missing required fields.
- **403 Forbidden**: Lacking permissions or unauthenticated.
- **404 Not Found**: Attempting to query an object ID that doesn't exist.
- **500 Internal Server Error**: Unhandled backend exception (usually logged).
