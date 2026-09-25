# TASK 1 — ADMIN FLOW DASHBOARD, NAVIGATION & DATASET-SCOPED COUNTERS

**Status**: COMPLETED, TESTED & VERIFIED  
**Date**: September 11, 2026  
**Scope**: Admin Flow Demonstration Shell, 7-Item Vertical Navbar, 6 Dataset-Scoped KPI Counters, Primary Actions, Scoped Upload Pipeline, Scoped Incident List & Clean Empty States  

---

## 1. Executive Summary

Task 1 completes the **Admin Flow demonstration shell** for Foresight (SIH Problem Statement 26165). This provides a dedicated environment for judges and evaluators to test real-time incident submissions, multi-record batch dataset uploads, live dual-threshold XGBoost + DistilBERT predictions, IOGP Life-Saving Rules matching, and expert human review adjudication.

All data, calculations, forms, uploads, and incident listings within Admin Flow are **strictly scoped to `workspace_id = 'admin_flow'`**. The 561,378 historical OIL enterprise records remain completely isolated, untouched, and unpolluted.

---

## 2. Admin Flow Navbar Contract

The vertical navbar for Admin Flow users contains **strictly and exclusively** the seven specified menu items:

1. **Dashboard** (`/admin-flow/dashboard/`)
2. **Submit Report** (`/admin-flow/submit/`)
3. **Upload dataset** (`/admin-flow/upload/`)
4. **Incidents** (`/admin-flow/incidents/`)
5. **PSIF Classification** (`/admin-flow/psif/`)
6. **IOGP classification** (`/admin-flow/iogp/`)
7. **Pattern Analysis** (`/admin-flow/patterns/`)

Non-admin logins (Safety Officers, Analysts, Executives, Viewers) retain their exact existing navbar links (`/dashboard/`, `/incidents/`, `/datasets/`, `/predictions/`, `/investigation/`, etc.) without any visual or functional regression.

---

## 3. Top KPI Section: Data-Source Logic for Every KPI

The Admin Flow Dashboard top section features **exactly six KPI metric cards**. All six are calculated via live SQL/ORM aggregations over `workspace_id = 'admin_flow'`. They start genuinely at `0` on a fresh clean baseline and react dynamically to user actions.

### Summary Table of KPI Data Sources

| KPI Metric Card | Database / ORM Aggregation Source | Eligibility / State Rule | Initial Value |
| :--- | :--- | :--- | :---: |
| **Total Incidents** | `Incident.objects.filter(workspace_id='admin_flow').count()` | All incidents created in or uploaded to Admin Flow | `0` |
| **Prediction Eligible** | `PredictionResult.objects.filter(incident__workspace_id='admin_flow', is_sparse_input=False).count()` | Non-sparse narratives ($\ge 10$ words) that underwent AI prediction | `0` |
| **PSIF Candidates** | `PredictionResult.objects.filter(incident__workspace_id='admin_flow', is_sparse_input=False, psif_predicted=True).count()` | Prediction eligible AND `psif_predicted=True` ($\text{probability} \ge \text{threshold}$) | `0` |
| **NOT PSIF** | `PredictionResult.objects.filter(incident__workspace_id='admin_flow', is_sparse_input=False, psif_predicted=False).count()` | Prediction eligible AND `psif_predicted=False` ($\text{probability} < \text{threshold}$) | `0` |
| **Insufficient Evidence**| `PredictionResult.objects.filter(incident__workspace_id='admin_flow', is_sparse_input=True).count()` | Input narrative was sparse ($< 10$ words) where model output is uninformative | `0` |
| **Human Reviewed** | `Incident.objects.filter(workspace_id='admin_flow').filter(Q(adjudication_status='ADJUDICATED') \| Q(is_psif_human_label__isnull=False) \| Q(reviews__isnull=False)).distinct().count()` | Incidents with recorded HSE expert human review or consensus adjudication | `0` |

### Detailed Metric Computation Rules

1. **Total Incidents** (`id="stat-total"`):
   - Evaluates: `Count("id", distinct=True)` on `Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE)`.
   - Behavior: Increments immediately whenever a single incident report is submitted or a batch dataset is ingested into Admin Flow.

2. **Prediction Eligible** (`id="stat-eligible"`):
   - Evaluates: Count of `PredictionResult` associated with Admin Flow incidents where `is_sparse_input=False`.
   - Behavior: Only increments if the incident narrative has sufficient semantic evidence ($\ge 10$ words) to produce a valid BERT embedding and calibrated prediction.

3. **PSIF Candidates** (`id="stat-psif"`):
   - Evaluates: Count of `PredictionResult` where `is_sparse_input=False` AND `psif_predicted=True`.
   - Denominator: PSIF Candidate percentage is computed against `prediction_eligible_count` ($(\text{PSIF} / \text{Eligible}) \times 100$), adhering strictly to the SIH Intelligence Foundation Contract.

4. **NOT PSIF** (`id="stat-not-psif"`):
   - Evaluates: Count of `PredictionResult` where `is_sparse_input=False` AND `psif_predicted=False`.
   - Confirms low precursor risk events that passed eligibility.

5. **Insufficient Evidence** (`id="stat-insufficient"`):
   - Evaluates: Count of `PredictionResult` where `is_sparse_input=True`.
   - Explicitly separates short/sparse observations (e.g. "hand slip") from model predictions, preventing low probabilities from falsely inflating "NOT PSIF" counts.

6. **Human Reviewed** (`id="stat-human-reviewed"`):
   - Evaluates: Count of Admin Flow `Incident` records with `adjudication_status = 'ADJUDICATED'`, an active `IncidentReview` record, or an adjudicated human ground truth label (`is_psif_human_label` is not null).
   - Behavior: Increments when an HSE evaluator submits consensus adjudication on the incident detail page.

---

## 4. Primary Dashboard Actions

Immediately below the six KPI metric cards, the dashboard displays two prominent action cards styled with the platform's industrial design language:

```
+-------------------------------------------------------------+-------------------------------------------------------------+
| SINGLE INCIDENT PREDICTION                                  | UPLOAD DATASET / MULTI INCIDENT PREDICTION                  |
| Live Report & Precursor Inference                           | Batch Ingestion & Pipeline                                  |
|                                                             |                                                             |
| Submit a live unsafe act, unsafe condition, or near-miss    | Upload CSV, JSON, or JSONL incident batches strictly into  |
| report to run real-time dual-threshold PSIF precursor       | the Admin Flow workspace for high-speed multi-incident      |
| inference, calibrated probability scoring, and IOGP rules.  | inference, automated DQ gating, and precursor clustering.   |
|                                                             |                                                             |
| [ Single Incident Prediction -> ]                           | [ Upload Dataset / Multi Incident Prediction -> ]           |
| (href="/admin-flow/submit/" id="btn-single-incident-pred")  | (href="/admin-flow/upload/" id="btn-multi-incident-pred")   |
+-------------------------------------------------------------+-------------------------------------------------------------+
```

---

## 5. Dataset Upload Pipeline & Auto-Scoping

When evaluators upload demonstration datasets (CSV, JSON, JSONL) via `/admin-flow/upload/`:
1. The `Dataset` record is created with `workspace_id = 'admin_flow'`.
2. Column mapping is automatically suggested with fallback to required narrative fields.
3. In [`apps/datasets/ingestion.py`](file:///Users/sas/Developer/prototype_165/apps/datasets/ingestion.py), `create_incident_from_row` propagates the dataset's workspace:
   ```python
   if dataset:
       if getattr(dataset, "workspace_id", None):
           incident.workspace_id = dataset.workspace_id
   ```
4. Full downstream processing executes seamlessly:
   - Data Quality (DQ) screening and validation.
   - Provenance tracking (`SYNTHETIC` / `REAL_EXTERNAL` / `REAL_HUMAN`).
   - DistilBERT 768-dimensional composite narrative embeddings.
   - Rule-based IOGP Life-Saving Rules tagging.
   - Batch XGBoost precursor probability scoring and SHAP factor attribution.
5. All ingested records are strictly tagged with `workspace_id = 'admin_flow'` and are invisible to standard users.

---

## 6. Admin Flow Incident List & Empty States

### Incident List Columns
The incident table at `/admin-flow/incidents/` strictly displays Admin Flow incidents and presents the 8 required fields:

1. **Incident ID**: Short formatted hash (e.g. `#92c71f1b`), linking directly to detail view.
2. **Date**: `YYYY-MM-DD` formatted incident occurrence date.
3. **Location**: Rig, facility, or department location.
4. **Activity**: Specific job task (e.g. "Wireline logging", "Mud pump liner replacement").
5. **PSIF**: Color-coded badge (`PSIF` in critical red, `NOT PSIF` in green, `Pending` in neutral).
6. **Model Score**: Calibrated 3-decimal PSIF probability score (e.g. `0.885`).
7. **IOGP**: Badges indicating matched IOGP Life-Saving Rules (e.g. `Energy Isolation`, `Line of Fire`).
8. **Evidence State**: Indicates narrative quality (`Sparse (< 10 words)` or `Strong` / `Moderate` / `Weak`).
9. **Action**: `View` button linking to `/admin-flow/incidents/<id>/`.

### Clean Empty State
When zero Admin Flow records exist, the page renders a clean empty state:
- Heading: **"No Admin Flow incidents yet."**
- Lead: "Submit a single incident observation or upload a demonstration dataset to populate this isolated workspace."
- Actions: Two prominent CTA buttons:
  - `Submit Report` (`id="btn-empty-submit"` -> `/admin-flow/submit/`)
  - `Upload Dataset` (`id="btn-empty-upload"` -> `/admin-flow/upload/`)
- **Zero Contamination**: No fake placeholder records are shown, and global incident counts are omitted.

---

## 7. Lifecycle & Counter Verification

The entire browser user journey was executed and verified via automated end-to-end integration testing:

```
[Baseline] Global Enterprise Incidents: 561,378
[Step 1] Fresh Admin Flow Login:
         Total: 0 | Eligible: 0 | PSIF: 0 | Not PSIF: 0 | Insufficient: 0 | Human Reviewed: 0
         -> ALL SIX BOXES DISPLAY 0
[Step 2] Submit 1 observation (submit_only):
         Total: 1 | Eligible: 0 | PSIF: 0 | Not PSIF: 0 | Insufficient: 0 | Human Reviewed: 0
         -> Total Incidents = 1, all others remain 0
[Step 3] Process observation via AI inference engine:
         Total: 1 | Eligible: 1 | PSIF: 1 | Not PSIF: 0 | Insufficient: 0 | Human Reviewed: 0
         -> Prediction Eligible = 1, PSIF Candidates = 1
[Step 4] Submit HSE expert human review adjudication:
         Total: 1 | Eligible: 1 | PSIF: 1 | Not PSIF: 0 | Insufficient: 0 | Human Reviewed: 1
         -> Human Reviewed = 1
[Step 5] Upload small multi-record CSV dataset (3 rows):
         Total: 4 | Eligible: 4 | PSIF: 3 | Not PSIF: 1 | Insufficient: 0 | Human Reviewed: 1
         -> Total Incidents grew from 1 to 4 strictly from uploaded records
         -> Incident list table renders all 8 required columns
[Step 6] Switch login to standard enterprise Safety Officer:
         Global Enterprise Incidents: 561,378
         -> GLOBAL ENTERPRISE VALUES REMAIN COMPLETELY UNCHANGED
```

---

## 8. Test Suite Summary

The complete automated test suite passed with **25/25 successful tests** across both isolation and dashboard contract suites:

```bash
$ ./venv/bin/pytest tests/test_task1_admin_flow_dashboard.py tests/test_admin_flow_isolation.py -v
============================= test session starts ==============================
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowDashboardCounters::test_initial_state_all_six_zero PASSED [  4%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowDashboardCounters::test_submit_one_incident_increments_total_incidents PASSED [  8%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowDashboardCounters::test_process_eligible_incident_updates_metrics PASSED [ 12%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowDashboardCounters::test_sparse_incident_increments_insufficient_evidence PASSED [ 16%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowDashboardCounters::test_human_review_adjudication_increments_counter PASSED [ 20%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowPrimaryDashboardActions::test_primary_actions_present_and_linked PASSED [ 24%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowNavbarContract::test_navbar_contains_only_seven_links PASSED [ 28%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowIncidentListScope::test_empty_state_when_no_records PASSED [ 32%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowIncidentListScope::test_table_headers_and_columns PASSED [ 36%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowIncidentListScope::test_global_incidents_never_appear_in_admin_flow_list PASSED [ 40%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowUploadDatasetScope::test_upload_csv_dataset_scoping PASSED [ 44%]
tests/test_task1_admin_flow_dashboard.py::TestAdminFlowGlobalRegression::test_standard_user_dashboard_unchanged PASSED [ 48%]
tests/test_admin_flow_isolation.py::TestAdminFlowAccessControl::test_anonymous_redirected_to_login PASSED [ 52%]
tests/test_admin_flow_isolation.py::TestAdminFlowAccessControl::test_standard_user_forbidden_on_admin_flow PASSED [ 56%]
tests/test_admin_flow_isolation.py::TestAdminFlowAccessControl::test_admin_flow_user_granted_access PASSED [ 60%]
tests/test_admin_flow_isolation.py::TestAdminFlowAccessControl::test_admin_flow_user_redirected_from_global_dashboard PASSED [ 64%]
tests/test_admin_flow_isolation.py::TestAdminFlowInitialCounters::test_genuine_zero_baseline PASSED [ 68%]
tests/test_admin_flow_isolation.py::TestAdminFlowInitialCounters::test_dashboard_renders_computed_zeros PASSED [ 72%]
tests/test_admin_flow_isolation.py::TestAdminFlowHardDataIsolation::test_two_way_dataset_isolation PASSED [ 76%]
tests/test_admin_flow_isolation.py::TestAdminFlowHardDataIsolation::test_object_id_bypass_prevention PASSED [ 80%]
tests/test_admin_flow_isolation.py::TestAdminFlowHardDataIsolation::test_admin_flow_incident_submission PASSED [ 84%]
tests/test_admin_flow_isolation.py::TestAdminFlowNavbarContract::test_admin_flow_navbar_contents PASSED [ 88%]
tests/test_admin_flow_isolation.py::TestAdminFlowNavbarContract::test_standard_user_navbar_unchanged PASSED [ 92%]
tests/test_admin_flow_isolation.py::TestAdminFlowAPIEndpoints::test_analytics_api_forbidden_for_standard_user PASSED [ 96%]
tests/test_admin_flow_isolation.py::TestAdminFlowAPIEndpoints::test_analytics_api_success_for_admin_flow_user PASSED [100%]
======================== 25 passed, 4 warnings in 7.21s ========================
```

---

## 9. Conclusion

Task 1 is 100% complete and rigorously verified. The Admin Flow demonstration shell is ready for judges with strict two-way data isolation, live computed KPI counters, dual primary action cards, scoped multi-record dataset uploading, and an 8-column incident list with a clean zero baseline.
