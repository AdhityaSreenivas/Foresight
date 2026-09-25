# TASK 7 — Admin Flow Pattern Analysis Hub + Full Judge Demonstration Flow

## Overview & Objectives

**Task 7** culminates the Admin Flow development by integrating all demonstration modules created across Tasks 0 through 6 into a cohesive, judge-facing demonstration workflow:

- **Pattern Analysis Landing Page (Hub)** (`/admin-flow/patterns/`): An intuitive entry point that allows evaluators to choose between three primary pattern analysis dimensions:
  1. `ACTIVITY PATTERNS` ("Which activities occur most frequently?")
  2. `BARRIER / CONTROL PATTERNS` ("Which control-deficiency signals recur?")
  3. `LOCATION PATTERNS` ("Where are observations concentrated?")
- **Top-Level Pattern Summary**: Neutral metrics for total incidents, most frequent activity, most frequent barrier signal, and highest observation-concentration location.
- **Relationship Visual**: A clean connected pathway showing $\text{Activity} \rightarrow \text{Location} \rightarrow \text{Barrier / Control Signal} \rightarrow \text{PSIF Observations}$.
- **Dashboard Integration**: A compact **PATTERN SNAPSHOT** card on the Admin Flow Dashboard below the dual action cards with a direct `View Pattern Analysis` button.
- **Genuine Zero-Baseline Verification**: The workspace starts at strictly `0 / 0 / 0 / 0 / 0 / 0` upon initial evaluator login with no synthetic auto-generated rows.
- **Hard Two-Way Workspace Isolation**: Strict filtering on `workspace_id = 'admin_flow'` preventing any leakage between demonstration records and the 561,378 global records.
- **Full 25-Step Judge Demonstration Lifecycle**: End-to-end operational verification from login to zero baseline, single submission, batch dataset upload, classification, multi-dimensional pattern analysis, and logout/enterprise regression check.

---

## Architectural Route Map

```
/admin-flow/
├── dashboard/               [AdminFlowDashboardView] (KPI Grid + Actions + Pattern Snapshot)
├── submit/                  [AdminFlowSubmitReportView] (Single Incident Submission)
├── upload/                  [AdminFlowUploadDatasetView] (Batch Dataset Ingestion)
├── incidents/               [AdminFlowIncidentListView] (Demonstration Records Table)
│   └── <uuid:pk>/           [AdminFlowIncidentDetailView] (Forensic Evidence & Energy Analysis)
├── psif/                    [AdminFlowPSIFClassificationView] (PSIF Metrics & Model Predictions)
├── iogp/                    [AdminFlowIOGPClassificationView] (IOGP Life-Saving Rules Matrix)
└── patterns/                [AdminFlowPatternHubView] (Pattern Analysis Landing Page)
    ├── activity/            [AdminFlowActivityPatternAnalysisView] (Activity Bar Distribution)
    ├── barrier/             [AdminFlowBarrierPatternAnalysisView] (Control Deficiencies & Rules)
    └── location/            [AdminFlowLocationPatternAnalysisView] (3x3 Facility Heatmap)
```

### REST API Endpoints

```
/admin-flow/api/
├── analytics/overview/      [AdminFlowAnalyticsOverviewAPI] (Dashboard KPI Counters)
├── psif/metrics/            [AdminFlowPSIFMetricsAPI] (PSIF Metrics & Model Reliability)
├── iogp/metrics/            [AdminFlowIOGPMetricsAPI] (IOGP Rules Linkage & Distribution)
├── patterns/                [AdminFlowPatternsOverviewAPI] (Cross-Dimensional Aggregations)
├── patterns/activity/       [AdminFlowActivityPatternsAPI] (Ranked Activity Distributions)
├── patterns/barrier/        [AdminFlowBarrierPatternsAPI] (Control State Breakdowns)
└── patterns/location/       [AdminFlowLocationPatternsAPI] (Heatmap & Zone Drill-Downs)
```

---

## Key Components Implemented

### 1. Pattern Analysis Landing Page (`templates/admin_flow/pattern_hub.html`)
- **Visual Decision Cards**: Three high-contrast cards providing immediate navigation to Activity, Barrier, and Location detailed analyses.
  - **Activity Card**: Includes an embedded mini-ranked bar preview with frequency counts.
  - **Barrier Card**: Includes embedded control-status signal badges with counts.
  - **Location Card**: Includes a mini 3x3 layout schematic preview highlighting the highest concentration area.
- **Top Summary Metrics**:
  - `Total Admin Flow Incidents`
  - `Most Frequent Activity`
  - `Most Frequent Barrier Signal`
  - `Highest Concentration Location`
  *(Framed strictly in terms of observation frequency rather than ungrounded "risk" statements).*
- **Empirical Relationship Flow Visual**:
  - A clean 4-stage horizontal diagram mapping:
    $$\text{Activity} \longrightarrow \text{Location} \longrightarrow \text{Barrier / Control Signal} \longrightarrow \text{PSIF Observations}$$
  - Clearly captioned: *"Observed relationship in Admin Flow data. Displays historical co-occurrence across demonstration observations."*
- **Four-Tab Sub-Navigation**: Seamless navigation between **Pattern Hub**, **Activity Patterns**, **Barrier Patterns**, and **Location Patterns**.

### 2. Admin Flow Dashboard Enhancement (`templates/admin_flow/dashboard.html`)
- Positioned directly below the six KPI boxes and dual action cards (**Single Incident Prediction** and **Upload Dataset / Multi-Incident Prediction**).
- **Pattern Snapshot Card**:
  - Renders Top Activity, Top Barrier-Linked Signal, and Top Location with observation counts and badge styling.
  - Displays empty state indicators (`No observations recorded yet`) when incident count is 0.
  - Primary CTA button: `View Pattern Analysis →` linking to `/admin-flow/patterns/`.

### 3. Engine Functions (`apps/admin_flow/pattern_engine.py`)
- `get_admin_flow_pattern_hub_view_data()`:
  - Computes top-level summary metrics with safe zero-state defaults.
  - Generates lightweight preview structures for the 3 decision cards.
  - Extracts the top empirical relationship chain across demonstration records.
  - Supplies standardized methodology notices.

---

## Workspace Isolation Contract

1. **Zero Baseline**:
   - `get_admin_flow_incidents()` and `get_admin_flow_datasets()` strictly query `workspace_id = 'admin_flow'`.
   - On new evaluator login, all counters compute strictly from DB count (evaluating to `0 / 0 / 0 / 0 / 0 / 0`).
2. **Hard Database Segregation**:
   - Global enterprise queries filter `workspace_id = 'default'` (or exclude `admin_flow`).
   - Admin Flow queries strictly filter `workspace_id = 'admin_flow'`.
   - Even direct object ID lookups on `/admin-flow/incidents/<pk>/` return `404 Not Found` if `<pk>` belongs to a global incident.
3. **Role-Based Access Control**:
   - `AdminFlowRequiredMixin` and `IsAdminFlowUser` deny access with **HTTP 403 Forbidden** to standard users (`is_admin_flow = False`).
   - Standard user dashboards and navigation have zero Admin Flow links.

---

## Verification & Test Results

### 1. Full Automated Regression Suite
The complete Admin Flow test suite (Tasks 0 through 7) was executed using `pytest`:

```bash
./venv/bin/pytest \
  tests/test_task7_admin_flow_integration.py \
  tests/test_task6_admin_flow_location_patterns.py \
  tests/test_task5_admin_flow_barrier_patterns.py \
  tests/test_task4_admin_flow_activity_patterns.py \
  tests/test_task3_admin_flow_pattern_analysis.py \
  tests/test_task2_admin_flow_classification.py \
  tests/test_task1_admin_flow_dashboard.py \
  tests/test_admin_flow_isolation.py -v
```

**Result: 79 passed, 0 failed, 5 warnings in 11.18s.**

### 2. Live 25-Step Judge Demonstration Script
The authoritative 25-step evaluator flow was verified live against the local server (`http://127.0.0.1:8000`):

| Step | Operation | Result | Verification Detail |
| :---: | :--- | :---: | :--- |
| **1** | Open Login Page | **PASSED** | HTTP 200, CSRF token extracted |
| **2** | Log in as Admin Flow | **PASSED** | Authenticated as `admin_flow@foresight.app` |
| **3** | Dashboard Appears | **PASSED** | Scoped banner and header verified |
| **4** | Verify All Six KPIs = 0 | **PASSED** | Genuine baseline: `0 / 0 / 0 / 0 / 0 / 0` |
| **5** | Click Submit Report | **PASSED** | `/admin-flow/submit/` loaded |
| **6** | Submit One Incident | **PASSED** | Precursor recorded with `workspace_id='admin_flow'` |
| **7** | Return to Dashboard | **PASSED** | Redirected to `/admin-flow/dashboard/` |
| **8** | Verify Counters Updated | **PASSED** | Total incidents incremented to `1` |
| **9** | Open Incidents | **PASSED** | Table displays single submitted record |
| **10** | Open Incident Detail | **PASSED** | Forensic evidence and energy analysis rendered |
| **11** | Show PSIF Classification | **PASSED** | Precursor classification view loaded |
| **12** | Show IOGP Classification | **PASSED** | Life-Saving Rules matrix loaded |
| **13** | Upload Multi-Incident Dataset | **PASSED** | 2-row batch CSV uploaded via `/admin-flow/upload/` |
| **14** | Wait for Processing | **PASSED** | Bulk parsing and ingestion completed |
| **15** | Verify Counters Update | **PASSED** | Total incidents counter updated to `3` |
| **16** | Open Pattern Analysis | **PASSED** | Landing Page loaded with 3 visual decision cards |
| **17** | Open Activity Analysis | **PASSED** | Ranked bar charts and dual-view toggle verified |
| **18** | Open Barrier Analysis | **PASSED** | Control-deficiency signals rendered |
| **19** | Open Location Analysis | **PASSED** | 3x3 Schematic Facility Heatmap rendered |
| **20** | Click a Location | **PASSED** | Location API returns top zone details |
| **21** | Inspect Linked Information | **PASSED** | Multi-dimensional chain ($\text{Loc} \rightarrow \text{Act} \rightarrow \text{Barrier}$) verified |
| **22** | Return to Dashboard | **PASSED** | Pattern Snapshot reflects updated top items |
| **23** | Log Out | **PASSED** | Session ended cleanly |
| **24** | Log In as Non-Admin-Flow | **PASSED** | Authenticated as `admin@foresight.app` |
| **25** | Verify Global Dashboard | **PASSED** | 561,378 global records intact; Admin Flow returns 403 |

---

## Conclusion

Task 7 successfully unifies the Admin Flow into an evaluator-ready showcase. A judge can log in, see a pristine zero-baseline workspace, add precursor observations via single-form submission or batch CSV upload, observe live updates to dashboard counters, and immediately discover actionable systemic patterns across operational activities, control-deficiency barriers, and internal facility locations—without any disruption or cross-contamination to the production environment.
