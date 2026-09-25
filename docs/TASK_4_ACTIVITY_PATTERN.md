# TASK 4 — ADMIN FLOW ACTIVITY-BASED PATTERN ANALYSIS SPECIFICATION & IMPLEMENTATION

**Foresight PSIF Platform — Ministry of Petroleum & Natural Gas (SIH Problem Statement 26165)**  
**Workspace Scope:** Admin Flow (`workspace_id = 'admin_flow'`)  
**URL Routes:** `/admin-flow/patterns/` & `/admin-flow/patterns/activity/`  
**API Route:** `/admin-flow/api/patterns/activity/`  
**Test Suite:** `tests/test_task4_admin_flow_activity_patterns.py` (9 tests, 51/51 regression passing)

---

## 1. Executive Summary

Task 4 completes the user-facing **Activity Pattern Analysis** page in the dedicated Admin Flow workspace. Operating exclusively over the demonstration dataset (`workspace_id = 'admin_flow'`) for the single-site operational context (*Duliajan Operational Complex*), this analytical view surfaces recurring precursor activities and their association with Potential Serious Injury and Fatality (PSIF) events without conflating raw occurrence volume with intrinsic hazard risk.

All global enterprise datasets (561,378 incidents) remain completely isolated and inaccessible from this workspace.

---

## 2. Architectural & Operational Principles

1. **Strict Admin Flow Scoping:**
   - Evaluates only observations where `workspace_id = 'admin_flow'`.
   - Bounded to single-site operational context (*Duliajan Operational Complex*) with internal work locations.
2. **Frequency vs. Risk Transparency:**
   - Occurrence frequency is separated from risk. The primary view displays occurrence volume.
   - Dual toggle provides immediate access to PSIF-linked precursor volume without asserting ungrounded causality.
3. **Explicit Denominator Contract:**
   - Every rate and percentage provides its explicit calculation formula and exact denominator:
     - **Activity Share of Dataset:** `incident_count / total_filtered_admin_flow_incidents` (e.g., `45.2% (42/93)`).
     - **PSIF-Linkage Rate:** `psif_linked_count / activity_incident_count` (e.g., `35.7% (15/42)`).
4. **Defensible Semantics:**
   - Top pattern callout strictly identifies the **"Most frequently observed activity in the current Admin Flow dataset."**
   - The phrase *"Most dangerous activity"* is strictly prohibited unless supported by defensible physical risk metrics.

---

## 3. Visual Layout & UI Components

### 3.1 Primary Visual: Ranked Horizontal Bar Chart
- **Visual Design Language:** Aligned directly with the *IOGP Barrier Risk Distribution Comparison* standard:
  - Ranked horizontal bars (`indexAxis: 'y'`) sorted descending by total incident volume.
  - Highest activity = longest bar at top; lowest activity = shortest bar at bottom.
  - Interactive Chart.js rendering with rounded bar ends (`borderRadius: 4`).
  - Bar Colors:
    - **Incident Volume:** Industrial Slate-Blue `#5C7C8A` (hover: `#47626e`).
    - **PSIF-Linked Volume:** Critical Crimson `#9C3B32` (hover: `#7d2e27`).
  - Dynamic responsive container height (`Math.max(340, labels.length * 44)px`) preventing bar crowding.

### 3.2 Dual View Toggle
- Seamless client-side button group in chart header:
  - `[Incident Volume]` (active by default, displaying total observations per activity).
  - `[PSIF-Linked Volume]` (switches dataset to show counts of model-predicted or human-adjudicated PSIF precursors).
- Smooth Chart.js re-render without page reload.

### 3.3 Top Pattern Callout Panel
- Prominent insight card styled with subtle olive gradient and solid brand accent:
  - **Header:** `MOST FREQUENT ACTIVITY`
  - **Category Name:** e.g., `Safe Mechanical Lifting`
  - **Metrics:**
    - Total occurrences with percentage share of current dataset.
    - PSIF linkage count with linkage rate percentage.
  - **Mandated Caption:** *"Most frequently observed activity in the current Admin Flow dataset."*

### 3.4 Ranked Secondary Breakdown Table
A comprehensive tabular summary positioned directly beneath the primary chart:
| Column Header | Type | Description |
| :--- | :--- | :--- |
| **Rank** | Badge | Numerical rank (1 = gold/olive `#1E4D2B`, 2–3 = slate `#5C7C8A`, 4+ = neutral). |
| **Activity** | Text + Tag | Canonical activity category with recurring pattern indicator (`● Recurring Pattern (>=2)`). |
| **Incidents** | Integer (Mono) | Total incident volume matching the activity. |
| **PSIF-Linked** | Integer (Mono) | High-risk precursor count linked to PSIF events (`#9C3B32`). |
| **PSIF-Linkage Rate** | Progress + % | Explicit `psif_linked / activity_incidents` percentage. |
| **Percentage of Admin Flow incidents** | Progress + % + Fraction | Explicit formula: `X.X% (incident_count / total_filtered_incidents)`. |

### 3.5 Operational Filters
Compact, non-intrusive filter toolbar:
- **Date Range:** `date_from` and `date_to` date inputs.
- **PSIF Status:** All Observations, PSIF Only, NOT PSIF Only, Insufficient Information.
- **Activity Search:** Text input querying job tasks and narrative descriptions (`q`).
- **Actions:** Primary `Filter` button and dynamic `Reset` button when filters are active.

### 3.6 Empty State (Zero Data Baseline)
When no records are available in the Admin Flow workspace:
- Dedicated empty-state placeholder card.
- Heading: **"No activity patterns available yet."**
- Explanation: Ingestion instructions for demonstration dataset.
- Action Buttons:
  - `Upload Dataset` -> `/admin-flow/upload/`
  - `Submit Report` -> `/admin-flow/submit/`

---

## 4. Backend Engine Implementation

### 4.1 View Data Builder (`apps/admin_flow/pattern_engine.py`)
```python
def get_admin_flow_activity_pattern_view_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    psif_filter: Optional[str] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
```
Key outputs:
- `workspace_id`: `"admin_flow"`
- `site_context`: `"Duliajan Operational Complex"`
- `total_workspace_incidents`: Total unfiltered records in workspace.
- `total_filtered_incidents`: Total records meeting current filter criteria.
- `activities`: Ranked list of activity dictionaries enriched with `rank`, `share_of_total`, and `share_label`.
- `top_activity`: Top pattern dictionary with compliant callout caption.
- `chart_labels`: Array of categories sorted descending.
- `chart_incident_counts`: Array of total counts sorted descending.
- `chart_psif_counts`: Array of PSIF-linked counts matching the sorted categories.

### 4.2 Views & URLs
- **View:** `AdminFlowPatternAnalysisView` in `apps/admin_flow/views.py`.
- **URLs:**
  - `path("patterns/", views.AdminFlowPatternAnalysisView.as_view(), name="patterns")`
  - `path("patterns/activity/", views.AdminFlowPatternAnalysisView.as_view(), name="patterns_activity")`
- **REST API:**
  - `GET /admin-flow/api/patterns/activity/` (`AdminFlowActivityPatternsAPI`) supports query parameters `?date_from=...&date_to=...&psif=...&q=...`.

---

## 5. Verification & Test Suite

The dedicated test suite `tests/test_task4_admin_flow_activity_patterns.py` validates all functional and boundary specifications:

| Test Name | Verified Specification | Result |
| :--- | :--- | :---: |
| `test_empty_state_zero_records` | Displays "No activity patterns available yet." with action buttons. | **PASS** |
| `test_single_record_pattern` | Top pattern callout displays "MOST FREQUENT ACTIVITY", "1 incidents", correct caption, and no forbidden wording. | **PASS** |
| `test_multiple_activities_ranked_descending` | 42 lifting, 28 vehicle, 18 hot work, 5 confined space sorted descending with explicit denominators. | **PASS** |
| `test_dual_view_toggle_elements` | Button group attributes (`data-metric="volume"` and `"psif"`) and canvas exist. | **PASS** |
| `test_filtering_date_psif_query` | Date range, PSIF status, and query filtering recompute denominators dynamically. | **PASS** |
| `test_unknown_activity_handling` | Gracefully categorizes unmapped records into `UNKNOWN ACTIVITY` without errors. | **PASS** |
| `test_workspace_isolation_hard_segregation` | Global enterprise records (561,378 incidents) are completely excluded. | **PASS** |
| `test_role_based_access_control` | Non-admin flow users receive 403 Forbidden; anonymous users receive 302 login redirect. | **PASS** |
| `test_activity_patterns_api` | REST API returns JSON with ranked activities, top_activity, and chart datasets. | **PASS** |

### Regression Suite Status
- Task 0 (Authentication & Isolation): **PASS**
- Task 1 (Dashboard, Counters, Nav): **PASS**
- Task 2 (PSIF & IOGP Classification): **PASS**
- Task 3 (Pattern Engine Core): **PASS**
- Task 4 (Activity Pattern Analysis): **PASS**
- **Total:** **51 / 51 tests passing** in 8.20s.
