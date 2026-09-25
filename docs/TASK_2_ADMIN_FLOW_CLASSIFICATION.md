# TASK 2 — ADMIN FLOW PSIF CLASSIFICATION & IOGP CLASSIFICATION VISUAL PAGES

**Status**: COMPLETED, TESTED & VERIFIED  
**Date**: September 11, 2026  
**Scope**: Dedicated Admin Flow PSIF & IOGP Classification Visual Summary Pages, Explicit Denominator Logic, Semantic Delineations, Terminology Compliance, Chart.js Visualizations, 9 Canonical IOGP Rules, and REST APIs  

---

## 1. Executive Summary

Task 2 delivers the two visual intelligence and classification pages for **Admin Flow**:
1. **PSIF Classification** (`/admin-flow/psif/`): Visual summary and precursor workbench displaying PSIF candidates, NOT PSIF events, and Insufficient Information records with an explicit denominator definition, score distribution bands, and strict terminology enforcement.
2. **IOGP Classification** (`/admin-flow/iogp/`): Visual barrier intelligence page featuring the 9 canonical IOGP Life-Saving Rules ranked descending by observation frequency, horizontal comparative bar chart (matching the established platform style), and prominent operational semantics disclaimers.

Both pages exist **strictly inside the Admin Flow workspace (`workspace_id = 'admin_flow'`)**. The existing global PSIF and IOGP classification pages (`/dashboard/barriers/`, `/dashboard/reports/`, etc.) and the 561,378 historical enterprise records remain completely untouched.

---

## 2. Admin Flow PSIF Classification Page (`/admin-flow/psif/`)

### 2.1 KPI Metric Cards & Data Sources

The top section of the page presents six KPI cards computed via live aggregation over `workspace_id = 'admin_flow'`:

| KPI Card | Aggregation Source | Semantics & Eligibility | Zero State Display |
| :--- | :--- | :--- | :---: |
| **Total Incidents** | `Incident.objects.filter(workspace_id='admin_flow').count()` | All incidents created in or uploaded to Admin Flow | `0` |
| **Prediction Eligible** | `PredictionResult.objects.filter(incident__workspace_id='admin_flow', is_sparse_input=False).count()` | Substantive narratives ($\ge 10$ words) evaluated by AI model | `0` |
| **PSIF Candidates** | `PredictionResult.objects.filter(incident__workspace_id='admin_flow', is_sparse_input=False, psif_predicted=True).count()` | Eligible observations with high SIF precursor probability | `0` |
| **NOT PSIF** | `PredictionResult.objects.filter(incident__workspace_id='admin_flow', is_sparse_input=False, psif_predicted=False).count()` | Eligible observations evaluated as routine/low precursor risk | `0` |
| **Insufficient Information** | `PredictionResult.objects.filter(incident__workspace_id='admin_flow', is_sparse_input=True).count()` | Sparse text ($< 10$ words) where model output is uninformative | `0` |
| **PSIF Rate (Eligible)** | `(psif_count / prediction_eligible_count) * 100` if eligible > 0 else `None` | Precursor prevalence strictly among prediction-eligible records | `—` |

### 2.2 Explicit Denominator Scoping
- **Formula**: $\text{PSIF Rate} = \frac{\text{PSIF Candidates}}{\text{Prediction-Eligible Observations}} \times 100$
- **Denominator Rule**: Insufficient-evidence (sparse) observations are **explicitly excluded from the denominator**. Sparse text does not constitute evidence of either precursor risk or safety, and including it would falsely dilute precursor prevalence.
- **Zero Denominator Handling**: When the denominator is 0, the UI renders `—` rather than `0.0%` or `NaN`, and displays an explicit explanatory label: `Denominator is 0 (no eligible observations)`.

### 2.3 Semantic Distinction: NOT PSIF &ne; INSUFFICIENT INFORMATION
A prominent callout banner reinforces the analytical distinction:
- **NOT PSIF**: Represents observations containing sufficient operational context evaluated by the model and found to lack high-consequence precursor mechanisms.
- **INSUFFICIENT INFORMATION**: Represents sparse observations ($< 10$ words) quarantined from model inference. Lacking evidence of hazard does **not** imply the presence of safety.

### 2.4 Terminology & Methodology Compliance
- **Approved Terminology**: All references strictly use **"PSIF Model Score"**.
- **Forbidden Terminology**: Phrases such as "Probability of fatality" or "Chance of death" are strictly banned and absent from all templates, labels, and code.
- **Mandatory Methodology Note**:
  > *"The PSIF Model Score is a model output and is not presented as a calibrated probability."*

### 2.5 Visual Charts
In accordance with the specification emphasizing clean visual charts over dense tables:
1. **PSIF vs NOT PSIF Distribution**: Donut chart comparing PSIF Candidates vs NOT PSIF among prediction-eligible records.
2. **Evidence-State Distribution**: Donut chart illustrating the ratio of Prediction-Eligible (non-sparse) observations to Insufficient Information (sparse) records.
3. **PSIF Model Score Distribution**: Bar chart displaying score concentration across four calibrated bands:
   - Low ($< 0.20$)
   - Medium ($0.20 - 0.49$)
   - High ($0.50 - 0.74$)
   - Critical ($\ge 0.75$)
4. **Adjudication & Review Progress**: Donut chart comparing Human Reviewed/Adjudicated observations against Pending Review.

---

## 3. Admin Flow IOGP Classification Page (`/admin-flow/iogp/`)

### 3.1 9 Canonical IOGP Life-Saving Rules
The page monitors all 9 standard IOGP safety domains:
1. `Bypassing Safety Controls`
2. `Confined Space`
3. `Driving`
4. `Energy Isolation`
5. `Hot Work`
6. `Line of Fire`
7. `Safe Mechanical Lifting`
8. `Work Authorization`
9. `Working at Height`

### 3.2 Descending Frequency Sorting
The canonical rules are dynamically sorted **from highest to lowest matched incident count**, with alphabetical tie-breaking for visual stability.

### 3.3 Comparative Analysis Chart (`adminFlowIOGPChart`)
The horizontal comparative bar chart matches the visual style and ergonomics of `barrierComparisonChart` in `templates/dashboard/barriers.html`:
- **Chart Type**: Horizontal bar (`indexAxis: 'y'`)
- **Dataset 1**: *Matched Observations* (`backgroundColor: #5C7C8A`)
- **Dataset 2**: *PSIF-Linked Candidates* (`backgroundColor: #9C3B32`)
- **Scale**: Linear with rounded bar geometry, tabular num callbacks, and responsive container.

### 3.4 Operational Semantics Notice
A prominent callout banner clarifies critical operational semantics:
- **Rule-matched / Rule-derived candidate**: Indicates narrative keyword correlation with that rule domain.
- **NOT a confirmed violation**: Does not prove an intentional breach or procedural non-compliance.
- **NOT a failed barrier**: Does not imply physical barrier breakdown without dedicated engineering audit.
- **NOT automatically a PSIF**: Observations matching an IOGP rule must undergo independent dual-threshold precursor evaluation.

---

## 4. REST API Endpoints Scoped to Admin Flow

Two new endpoints provide clean JSON access to Admin Flow classification data:

### 1. `GET /admin-flow/api/psif/metrics/`
- **Permissions**: Requires active `AdminFlow` authenticated user.
- **Response**:
  ```json
  {
    "total_incidents": 4,
    "total_predictions": 4,
    "prediction_eligible_count": 3,
    "psif_count": 1,
    "not_psif_count": 2,
    "insufficient_evidence_count": 1,
    "has_eligible": true,
    "has_data": true,
    "psif_rate": 33.3,
    "psif_rate_display": "33.3%",
    "denominator_definition": "Prediction-eligible non-sparse observations (excludes insufficient evidence)",
    "binary_distribution": { "PSIF": 1, "NOT_PSIF": 2 },
    "evidence_distribution": { "eligible": 3, "insufficient": 1 },
    "score_distribution": { "low": 1, "medium": 1, "high": 0, "critical": 1 },
    "review_distribution": { "reviewed": 1, "unreviewed": 3 },
    "methodology_note": "The PSIF Model Score is a model output and is not presented as a calibrated probability.",
    "semantic_note": "NOT PSIF ≠ INSUFFICIENT INFORMATION...",
    "recent_incidents": [...]
  }
  ```

### 2. `GET /admin-flow/api/iogp/metrics/`
- **Permissions**: Requires active `AdminFlow` authenticated user.
- **Response**:
  ```json
  {
    "rules": [
      {
        "rule": "Working at Height",
        "slug": "working-at-height",
        "matched_observations": 2,
        "formatted_matched": "2",
        "psif_linked_observations": 1,
        "formatted_psif_linked": "1",
        "affected_sites": 2,
        "formatted_affected_sites": "2",
        "psif_linkage_rate": 50.0,
        "has_matches": true
      },
      ...
    ],
    "total_rule_matches": 4,
    "total_psif_linked": 3,
    "chart_labels": ["Working at Height", "Confined Space", ...],
    "chart_matched": [2, 1, ...],
    "chart_psif": [1, 1, ...],
    "has_data": true,
    "semantic_disclaimer": "Rule-matched / Rule-derived candidate: An IOGP rule match does NOT automatically mean a confirmed violation...",
    "recent_rule_tags": [...]
  }
  ```

---

## 5. Clean Empty State & Hard Isolation Contract

1. **Zero Baseline**: When no demonstration incidents have been submitted or uploaded into Admin Flow, all counts start at `0`.
2. **No Fake Demonstrations**: Empty states render informative placeholders with clear calls to action (`+ Submit Test Observation`, `Upload Test Dataset`) without injecting artificial dummy data.
3. **Global Record Isolation**:
   - `Incident.objects.filter(workspace_id='admin_flow')` isolates all Admin Flow database queries.
   - Global enterprise incidents (`workspace_id IS NULL`) are completely excluded from Admin Flow calculations.
   - Global pages (`/dashboard/reports/`, `/dashboard/barriers/`) exclude Admin Flow demonstration records.

---

## 6. Automated Test Suite Results

The comprehensive test suite in [`tests/test_task2_admin_flow_classification.py`](file:///Users/sas/Developer/prototype_165/tests/test_task2_admin_flow_classification.py) validates all Task 2 requirements:

```bash
$ ./venv/bin/pytest tests/test_task2_admin_flow_classification.py tests/test_task1_admin_flow_dashboard.py tests/test_admin_flow_isolation.py -v
============================= test session starts ==============================
tests/test_task2_admin_flow_classification.py::TestTask2ZeroRecordsBaseline::test_psif_page_zero_state PASSED [  3%]
tests/test_task2_admin_flow_classification.py::TestTask2ZeroRecordsBaseline::test_iogp_page_zero_state PASSED [  6%]
tests/test_task2_admin_flow_classification.py::TestTask2PSIFMetricsAndCalculations::test_single_psif_record PASSED [  9%]
tests/test_task2_admin_flow_classification.py::TestTask2PSIFMetricsAndCalculations::test_multiple_records_with_sparse_exclusion PASSED [ 12%]
tests/test_task2_admin_flow_classification.py::TestTask2IOGPClassification::test_iogp_rule_sorting_and_linkage PASSED [ 15%]
tests/test_task2_admin_flow_classification.py::TestTask2WorkspaceIsolation::test_global_records_excluded_from_admin_flow PASSED [ 18%]
tests/test_task2_admin_flow_classification.py::TestTask2APIs::test_psif_metrics_api PASSED [ 21%]
tests/test_task2_admin_flow_classification.py::TestTask2APIs::test_iogp_metrics_api PASSED [ 24%]
tests/test_task1_admin_flow_dashboard.py::... PASSED (12 tests) [ 60%]
tests/test_admin_flow_isolation.py::... PASSED (13 tests) [100%]
======================== 33 passed, 4 warnings in 7.72s ========================
```

---

## 7. Responsive CSS Architecture

Both pages are built with responsive grid systems adapting cleanly across:
- **Desktop ($\ge 1200\text{px}$)**: 2-column chart grid, 3-column barrier cards, 6-card KPI strip.
- **Tablet ($768\text{px} - 1199\text{px}$)**: 2-column layouts, table horizontal scrolling with preserved headers, scaled typography.
- **Mobile ($< 768\text{px}$)**: Single-column stacked cards, full-width charts with responsive touch tooltips, tabular numeric alignment.
