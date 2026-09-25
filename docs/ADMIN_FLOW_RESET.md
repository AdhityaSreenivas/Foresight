# Admin Flow Clean-Sheet Demonstration Reset Specification

**Document Version:** 1.0  
**Status:** Canonical & Implemented  
**Scope:** Admin Flow Demonstration Workspace (`workspace_id = 'admin_flow'`)  
**Target Audience:** Evaluators, Demonstration Presenters, System Architects  

---

## 1. Executive Summary

Admin Flow is a dedicated, judge-facing demonstration workflow within the Foresight SIF AI/NLP platform (Problem Statement 26165). To ensure live evaluation sessions can be presented from a pristine starting state repeatedly without requiring server restarts, manual database truncation, or shell intervention, the system provides an authoritative **Clean-Sheet Demonstration Reset**.

The Reset operation purges all demonstration records, predictions, rule tags, human reviews, embeddings, and cached aggregations created within the Admin Flow workspace, while guaranteeing 100% data and artifact preservation for all global datasets, canonical ML models, and regular login users.

---

## 2. Reset Scope & Data Architecture Contract

### 2.1 Canonical Workspace Scope
All demonstration data created, submitted, or uploaded through the Admin Flow interface is explicitly tagged with:
```python
ADMIN_FLOW_WORKSPACE = "admin_flow"
```

The reset operation operates strictly through this scope boundary:
- **Server-Derived Identity:** The backend inspects `request.user.is_admin_flow` (and `request.user.role == "admin_flow"`).
- **Zero Client Trust:** Query parameters such as `?workspace_id=...` or POST form parameters like `workspace_id=...` are completely ignored for scope determination. Spoofing global or other workspace IDs is impossible.

### 2.2 Records Affected (Cascading Reset)
When the Admin Flow Reset is triggered, all records matching `workspace_id = 'admin_flow'` are atomically removed:
1. **Incidents:** All demonstration records (`Incident` where `workspace_id='admin_flow'`).
2. **Predictions:** All model inference results (`PredictionResult` where `incident__workspace_id='admin_flow'`).
3. **IOGP Life-Saving Rules:** All matched rule tags (`IOGPRuleTag` where `incident__workspace_id='admin_flow'`).
4. **Human Review Records:** All demonstration review judgments (`IncidentReview` where `incident__workspace_id='admin_flow'`).
5. **Vector Embeddings:** Semantic representation records (`IncidentEmbedding` where `incident__workspace_id='admin_flow'`).
6. **Data Quality Checks:** Ingestion DQ audit tags (`IncidentDataQuality` where `incident__workspace_id='admin_flow'`).
7. **Datasets & Staged Files:** Admin Flow batch uploads (`Dataset` where `workspace_id='admin_flow'`), including safe disk deletion of uploaded temporary CSV/JSON files.

### 2.3 Records Protected (Immutable Global Infrastructure)
Under NO circumstances does the reset touch or modify:
- **Global Incidents:** All production/historical incidents (`Incident` where `workspace_id__isnull=True` or other enterprise workspaces).
- **Global Datasets:** Historical enterprise dataset uploads (`Dataset` where `workspace_id__isnull=True`).
- **Global Predictions & Analytics:** Historical baseline inferences and metrics.
- **Canonical Model Registry:** Active and archived models (`ModelVersion`), weights, serialized XGBoost JSON artifacts, encoders, and BERT backbones.
- **Knowledge Base & Normalization Rules:** Standard IOGP rules, site aliases, activity taxonomy, and barrier definitions.
- **Regular User Accounts & Dashboards:** Regular login credentials (`admin@foresight.app`, safety officers, analysts) and their dashboard views.

---

## 3. Concurrency, Async Safety & Cooperative Cancellation

### 3.1 Upload & Reset Race Condition Protection
To prevent race conditions where a reset occurs simultaneously with an upload, the system enforces:
1. **Redis Reset Lock:** Before deletion, `reset_admin_flow_workspace()` sets `admin_flow:reset_lock` with a 30-second lease.
2. **Ingestion Gate:** Both `AdminFlowUploadDatasetView` and `AdminFlowSubmitReportView` call `is_admin_flow_reset_in_progress()`. If a reset is active, incoming uploads are rejected immediately with HTTP 409 Conflict.

### 3.2 In-Flight Celery Task Cancellation
If a background Celery pipeline (e.g. `process_dataset_task`) is processing an Admin Flow dataset when a reset occurs:
1. The reset service locates active Admin Flow `Dataset`s (`status__in=[QUEUED, PROCESSING]`).
2. It sets `dataset.cancel_requested = True` and writes Redis cooperative cancel keys: `dataset:cancel:{dataset_id}`.
3. In `apps/datasets/tasks.py`, workers check `is_cancellation_requested()` before processing each batch of 100 incidents.
4. When cancellation is detected, the Celery task halts cleanly without writing orphaned predictions or phantom incidents.
5. In addition, workers check `is_admin_flow_reset_in_progress()` for `workspace_id="admin_flow"` and gracefully terminate.
6. The reset service never uses `revoke(terminate=True)` to avoid SIGKILL corruption of Celery process pools.

---

## 4. Cache Invalidation & Generation Token Architecture

### 4.1 Pattern Cache Invalidation
The Admin Flow pattern analysis engine caches aggregated statistics with versioned keys. Upon reset:
- `invalidate_admin_flow_pattern_cache()` increments `admin_flow:pattern_cache_version`.
- All cached pattern aggregates (activity patterns, barrier signals, location heatmaps, multi-dimensional pipelines) are invalidated atomically.

### 4.2 Workspace Generation Token
Each reset increments a monotonically increasing generation counter:
```python
ADMIN_FLOW_GENERATION_KEY = "admin_flow:generation"
```
Any asynchronous job or delayed response stamped with an older generation is rejected, guaranteeing that stale records can never reappear.

---

## 5. Security & Authorization Matrix

| Endpoint | HTTP Method | Allowed Roles | CSRF Required | Behavior on Violation |
|---|---|---|---|---|
| `/admin-flow/reset/` | `POST` | `admin_flow` | Yes | HTTP 403 Forbidden |
| `/admin-flow/reset/` | `GET` | Any | N/A | HTTP 405 Method Not Allowed |
| `/admin-flow/reset/` | `POST` | Standard User (`admin`, `analyst`, `viewer`) | Yes | HTTP 403 Forbidden |
| `/admin-flow/reset/` | `POST` | Anonymous | N/A | HTTP 302 Redirect to `/accounts/login/` |

---

## 6. Audit Logging

Every reset action is recorded in both application structured logs and a dedicated memory-backed audit trail (`ADMIN_FLOW_AUDIT_LOG_KEY`):
- **Event Type:** `ADMIN_FLOW_RESET`
- **User:** Authenticated user email / username
- **Timestamp:** ISO 8601 UTC timestamp
- **Generation:** Monotonic workspace generation token
- **Deleted Counts:** Tally of incidents, datasets, predictions, rule tags, and reviews purged
- **Remaining Counts:** Verified to be 0
- **Result:** `SUCCESS`

Audit records can be inspected via `get_admin_flow_reset_audit_log(limit=25)` or standard Django logging at `INFO` level under logger `apps.admin_flow.services`.

---

## 7. User Interface & Demonstration Flow

### 7.1 Vertical Navbar Reset Item
- Located in the left sidebar exclusively for authenticated Admin Flow users (`{% if user.is_admin_flow %}`).
- Rendered with a red refresh/reset SVG icon and distinct styling (`color: var(--risk-critical, #ef4444)`).
- Never visible to regular login users or viewers.

### 7.2 Confirmation Modal
Clicking "Reset Demo" triggers a high-contrast modal dialog:
- **Title:** "Reset Admin Flow?"
- **Message:** "This will remove all Admin Flow demonstration data and return the workspace to a clean starting state. Existing Foresight/global data will not be affected."
- **Isolation Notice:** "Safe Isolation Scope: Only records tagged with `workspace_id = 'admin_flow'` will be deleted. The canonical model registry, global incidents, and regular login accounts remain 100% intact."
- **Action Buttons:** `CANCEL` (dismisses modal) and `RESET DEMO` (submits POST form with CSRF token).

---

## 8. Step-by-Step Judge Demonstration Procedure

Follow this standard operating procedure during judge evaluations:

```
1. PRE-DEMO PREPARATION
   - Open browser to http://127.0.0.1:8000/accounts/login/
   - Authenticate as:
     Email: admin_flow@foresight.app
     Password: foresight2026

2. CLEAN-SHEET RESET (VERIFICATION)
   - Click "Reset Demo" at the bottom of the Admin Flow vertical navbar.
   - Confirmation modal appears: "Reset Admin Flow?".
   - Click "RESET DEMO".
   - Confirm Dashboard displays all 6 KPI cards at zero:
     * Total Incidents: 0
     * Prediction Eligible: 0
     * PSIF Candidates: 0
     * Not PSIF: 0
     * Insufficient Evidence: 0
     * Human Reviewed: 0

3. SINGLE REPORT EVALUATION
   - Click "Submit Report" in the navbar.
   - Enter an operational observation:
     * Description: "High pressure gas leak detected near flange during hot work pipe cutting on rig floor."
     * Activity / Job Task: "Pipe Cutting"
     * Location: "Drill Floor"
     * Direct Control: "Failed"
   - Click "Submit & Run Inference".
   - Observe immediate dual-threshold classification, PSIF precursor score, and IOGP Hot Work rule linkage.
   - Return to Dashboard: Total Incidents = 1, PSIF Candidates = 1.

4. BATCH DATASET DEMONSTRATION
   - Click "Upload Dataset".
   - Upload a test demonstration CSV file (e.g. 50 benchmark records).
   - Watch real-time processing and dynamic distribution updating.

5. PATTERN & INTELLIGENCE INSPECTION
   - Navigate to "Pattern Analysis".
   - Explore Activity Patterns, Barrier Signals, and Location Heatmaps dynamically calculated from the batch.
   - Navigate to "PSIF Classification" and "IOGP Classification".

6. RE-RESET (REPEATABILITY PROOF)
   - Click "Reset Demo" -> Confirm.
   - All six KPI cards instantly return to 0.
   - All pattern pages, incident lists, and classification summaries return to clean empty states.
   - Conclude demonstration showing that Foresight is 100% stable, repeatable, and non-destructive.
```
