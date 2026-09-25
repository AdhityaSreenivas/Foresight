# TASK 5 — ADMIN FLOW BARRIER / CRITICAL-CONTROL PATTERN ANALYSIS

**Foresight PSIF Platform — AI-Powered Operational Safety Precursor Intelligence**  
**Problem Statement ID**: 26165  
**Component**: Admin Flow Barrier Pattern Analysis  
**Route**: `/admin-flow/patterns/barrier/`  
**API Endpoint**: `/admin-flow/api/patterns/barrier/`  
**Date**: September 2026  

---

## 1. Executive Summary

Task 5 implements the **Barrier / Critical-Control Pattern Analysis** module within the Admin Flow operational intelligence pipeline. Operating strictly within the isolated demonstration workspace (`workspace_id = 'admin_flow'`), this module extracts and aggregates evidence-supported barrier and control-deficiency observations across single-site operations (e.g., Duliajan site).

Critically, this implementation adheres to **strict semantic and methodological rules**:
- Control associations are explicitly framed as **"Barrier / Control-Deficiency Associated Observations"** or **"Barrier-Linked Observations"**.
- Graphs and analytical tables **never** attribute causal fault (e.g., avoiding *"Barriers causing incidents"* or *"Worst barrier"*).
- Counts strictly represent evidence-supported deficiencies, and the methodology note emphasizes that **they do not establish causal responsibility**.
- The existing global enterprise Barrier Intelligence page (`/barrier-intelligence/`) remains entirely **unmodified and isolated**.

---

## 2. Strict Semantic & Methodological Rules

In high-reliability industrial operations (oil & gas, chemical processing, heavy manufacturing), attributing incident causality solely to a barrier without exhaustive root-cause investigation is methodologically unsound. Foresight enforces rigorous semantic guardrails:

| Rule | Approved Presentation | Strictly Prohibited Phrasing |
| :--- | :--- | :--- |
| **Primary Visual Heading** | `Barrier / Control-Deficiency Associated Observations` or `Barrier-Linked Observations` | `Barriers causing incidents`, `Barrier Failures Causing Accidents` |
| **Top Barrier Callout** | `MOST FREQUENT BARRIER-LINKED SIGNAL`<br>*"Most frequently observed control-deficiency association."* | `Worst barrier`, `Barrier responsible for most accidents`, `Top killer barrier` |
| **IOGP Cross-Link** | `IOGP Rule-derived candidate` | `confirmed IOGP violation`, `rule violation` |
| **Methodology Note** | *"Counts represent observations linked to evidence-supported control deficiencies. They do not establish causal responsibility."* | Any claim of definitive causal liability |

---

## 3. Supported Control States & Deficiency Evaluation

The barrier pattern engine (`apps/admin_flow/pattern_engine.py`) evaluates control conditions against the standardized PSIF control-state taxonomy.

### 3.1 Deficiencies Counted
Observations are counted as control deficiencies **only** when supported by explicit record evidence:
1. **`ABSENT`**: Physical or procedural control was missing or not in place (e.g., interlock missing).
2. **`FAILED`**: Installed barrier failed to perform its intended safety function under demand (e.g., relief valve did not lift).
3. **`BYPASSED`**: Control was intentionally overridden, bypassed, or jumpered (e.g., interlock bypassed during startup).
4. **`NOT_VERIFIED`**: Isolation or zero-energy state was not positively confirmed prior to commencing work.
5. **`INCORRECTLY_ASSUMED`**: Control integrity was presumed without physical verification (e.g., assumed isolated based on handle orientation).
6. **`PARTIALLY_EFFECTIVE`**: Barrier provided partial mitigation but allowed breach or leakage.

### 3.2 Non-Deficiencies Strictly Excluded
The following states are **never** counted as control failures:
- **`EFFECTIVE`**: Barrier successfully arrested or mitigated hazard energy.
- **`UNKNOWN`**: Insufficient evidence to establish barrier state.
- **`RECOMMENDATION_ONLY`**: Audit suggestion or future recommendation; not a failure during operation.
- **`PLANNED_ONLY`**: Future barrier planned for turnaround or retrofit; not in service.

If an operational dataset contains only `EFFECTIVE` or `UNKNOWN` controls, the system displays a clean empty state rather than mischaracterizing zero counts as operational failure.

---

## 4. Visual Architecture & Design Language

The Barrier Pattern Analysis view (`/admin-flow/patterns/barrier/`) utilizes the same clean, executive design language as the **IOGP Barrier Risk Distribution Comparison** chart.

### 4.1 Primary Visual: Ranked Horizontal Bar Chart
- **Descending Sort**: Highest barrier-associated observation count has the longest bar at the top (`#5C7C8A`).
- **Interactive Dual View Toggle**:
  - `[Associated Observations]`: Displays total evidence-supported deficiency counts (`#5C7C8A`).
  - `[PSIF-Linked Volume]`: Displays high-consequence precursor counts (`#9C3B32`, critical risk).
- **Responsive Canvas**: Chart.js 4.4 horizontal bar chart with custom tooltip formatting and 8px border radius.

### 4.2 Top Barrier Callout Card
Positioned prominently above the primary visual:
- **Header**: `MOST FREQUENT BARRIER-LINKED SIGNAL`
- **Primary Value**: Top barrier domain name (e.g., `Energy Isolation`)
- **Key Metrics Grid**:
  - `ASSOCIATED OBSERVATIONS`: Total deficiency count (e.g., `31`)
  - `PSIF-LINKED`: High-consequence count (e.g., `19`)
  - `AFFECTED LOCATIONS`: Number of distinct internal site areas (e.g., `6 locations`)
  - `DOMINANT STATE`: Most frequent control deficiency state (e.g., `NOT_VERIFIED`)
- **Methodology Caption**: *"Most frequently observed control-deficiency association."*

### 4.3 Secondary Information Table
Provides granular evidence breakdown per barrier domain:
1. **Rank**: Descending ordinal position (`#1`, `#2`, ...).
2. **Barrier / Control**: Canonical safety control domain with optional `IOGP Rule-derived candidate` badge.
3. **Associated Observations**: Total evidence-supported deficiency count.
4. **PSIF-linked Observations**: Observations classified as Potential Serious Injury or Fatality.
5. **Affected Internal Locations**: Count and list of operational zones (e.g., `Compressor Area`, `Wellhead`, `Workshop`).
6. **Dominant Control State**: Monospace badge indicating the most common deficiency state (only rendered if calculated from evidence; otherwise `—`).
7. **Percentage of Admin Flow incidents**: Explicit formula `count / total_filtered_incidents` (e.g., `47.0% (31/66)`).

---

## 5. Filtering & Denominator Integrity

The interface provides focused, simple operational filters without complex UI overhead:
- **PSIF Status**: `All Incidents`, `PSIF Only`, `Non-PSIF Only`.
- **Control State**: Filter by specific deficiency state (`ABSENT`, `FAILED`, `BYPASSED`, `NOT_VERIFIED`, `INCORRECTLY_ASSUMED`, `PARTIALLY_EFFECTIVE`).
- **Internal Location**: Single-site areas (`Compressor Area / Gas Station`, `Wellhead / Production Manifold`, `Workshop / Maintenance Bay`, etc.).

### Denominator Integrity Rule
Whenever filters are applied, denominators dynamically recompute:
$$\text{Barrier Share (\%)} = \frac{\text{Deficiency-Linked Incident Count}}{\text{Total Incidents in Filtered Admin Flow Scope}} \times 100$$
The exact denominator is explicitly stated in the UI (e.g., *"Percentage denominator: observation count / 66 total Admin Flow incidents"*).

---

## 6. Empty State Handling

When no Admin Flow incidents exist or no evidence-supported barrier deficiencies can be established:
- The view displays:
  > *"No barrier-linked patterns could be established from the available Admin Flow evidence."*
- Action buttons:
  - `[Upload Dataset]` $\rightarrow$ `/admin-flow/upload/`
  - `[Submit Report]` $\rightarrow$ `/admin-flow/submit/`
- Zero is never presented as an operational failure.

---

## 7. Verification & Regression Coverage

The Task 5 test suite (`tests/test_task5_admin_flow_barrier_patterns.py`) provides 100% test coverage across all specifications:

| Test Case | Objective | Result |
| :--- | :--- | :--- |
| `test_empty_state_zero_records` | Verifies clean empty state text and action buttons when 0 records exist. | **PASSED** |
| `test_single_record_pattern_and_semantic_rules` | Verifies top callout header, caption, methodology notice, and strictly forbids banned phrases. | **PASSED** |
| `test_every_control_state_deficiency_vs_non_deficiency` | Asserts all 6 deficiency states are counted and all 4 non-deficiency states are excluded. | **PASSED** |
| `test_effective_unknown_only_results_in_clean_empty_state` | Asserts datasets with only EFFECTIVE/UNKNOWN controls produce clean empty state. | **PASSED** |
| `test_multiple_barriers_ranked_descending` | Recreates 31 / 20 / 15 prompt distribution; verifies descending sort order and denominators. | **PASSED** |
| `test_affected_locations_and_dominant_control_state` | Verifies location counts and dominant state calculation from evidence without guessing. | **PASSED** |
| `test_iogp_crosslink_candidate_badge` | Asserts `IOGP Rule-derived candidate` badge and forbids `confirmed IOGP violation`. | **PASSED** |
| `test_filtering_psif_control_state_and_location` | Tests dynamic filtering by PSIF, control state, and operational location. | **PASSED** |
| `test_workspace_isolation_hard_segregation` | Asserts global records (`workspace_id IS NULL`) are completely excluded. | **PASSED** |
| `test_role_based_access_control` | Verifies RBAC: admin flow user allowed (200), standard user denied (403), anonymous redirected (302). | **PASSED** |
| `test_barrier_patterns_api` | Verifies REST API `GET /admin-flow/api/patterns/barrier/` JSON payload structure. | **PASSED** |

---

## 8. Summary of Created and Modified Files

1. **`apps/admin_flow/pattern_engine.py`**:
   - Added `location` tracking to `PatternObservation`.
   - Updated `extract_admin_flow_barrier_observations` to support all 6 deficiency states and 4 non-deficiency states.
   - Updated `compute_barrier_patterns` to compute affected locations, dominant control states, and IOGP cross-links.
   - Implemented `get_admin_flow_barrier_pattern_view_data` with dynamic filtering and Chart.js payloads.
2. **`apps/admin_flow/views.py`**:
   - Added `AdminFlowBarrierPatternAnalysisView` (`/admin-flow/patterns/barrier/`).
   - Updated `AdminFlowBarrierPatternsAPI` with query filter support.
3. **`apps/admin_flow/urls.py`**:
   - Registered `patterns/barrier/` route.
4. **`templates/admin_flow/barrier_pattern_analysis.html`**:
   - Complete template featuring isolation banner, methodology notice, 3-dimension tabs, top barrier card, filter bar, horizontal bar chart, secondary breakdown table, and empty state.
5. **`templates/admin_flow/pattern_analysis.html`**:
   - Linked Barrier Patterns tab to `{% url 'admin_flow:patterns_barrier' %}`.
6. **`tests/test_task5_admin_flow_barrier_patterns.py`**:
   - 11 comprehensive automated tests.
7. **`docs/TASK_5_BARRIER_PATTERN.md`**:
   - Complete technical and methodological documentation.
