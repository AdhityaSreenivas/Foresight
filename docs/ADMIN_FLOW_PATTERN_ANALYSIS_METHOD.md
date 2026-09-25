# Admin Flow Pattern Analysis Methodology & Engine Architecture

**Document**: `docs/ADMIN_FLOW_PATTERN_ANALYSIS_METHOD.md`  
**Status**: COMPLETED, TESTED & VERIFIED  
**Date**: September 11, 2026  
**Scope**: 3-Dimensional Pattern Engine (Activity, Barrier/Control, Internal Location), Transparent Frequency-Based Recurrence, Defensible Barrier Semantics, Single-Site Operational Context, REST APIs, and Scoped Caching  

---

## 1. Executive Summary & Purpose

The **Admin Flow Pattern Analysis Engine** delivers on the core user requirement:
> *“Surfaces recurring precursor patterns (activity, location, barrier failure) via a dashboard.”*

### Core Architectural Decision
- **Strict Demonstration Scoping**: The pattern analysis engine **does not** execute across the 561,378 historical training records. It executes **strictly and exclusively** over the Admin Flow demonstration dataset (`workspace_id = 'admin_flow'`).
- **Demonstration Purpose**: To demonstrate how Foresight surfaces actionable precursor accumulation patterns after a focused operational dataset is collected, submitted, or uploaded by evaluators.

---

## 2. Core Operational Assumptions

### 2.1 Single-Site Operational Context
All uploaded or submitted incidents within Admin Flow are assumed to belong to **one operational site** (default: *Duliajan Operational Complex*).

The engine analyzes **internal locations** within that site, such as:
- *Compressor Area*
- *Wellhead Area*
- *Workshop / Maintenance Bay*
- *Tank Farm*
- *Pipe Rack / Manifold*
- *Drilling Area / Rig Floor*
- *Warehouse / Storage Yard*
- *Process Area / Refining Unit*
- *Electrical Substation*
- *Control Room*
- *Flare Area*
- *Produced Water Treatment*

**Cross-site comparisons are explicitly excluded** within Admin Flow pattern analysis.

---

## 3. The Three Pattern Dimensions

The engine extracts, normalizes, and aggregates data across three dimensions:

### 3.1 Dimension 1: Activity Normalization
- **Layer**: Reuses the platform's deterministic safety entity normalization layer (`apps.incidents.services.normalization`).
- **Canonical Activity Taxonomy**: Maps raw activity strings and job tasks into verified canonical safety activities (e.g. *Hot Work in Classified Area*, *Work at Height / Scaffold Work*, *Safe Mechanical Lifting*, *Energy Isolation / LOTO*, *Confined Space Vessel Entry*).
- **Explicit Alias Mappings**:
  - `lifting operation` $\rightarrow$ `Safe Mechanical Lifting`
  - `material lifting` $\rightarrow$ `Safe Mechanical Lifting`
  - `crane lifting` $\rightarrow$ `Safe Mechanical Lifting`
  - `welding` $\rightarrow$ `Hot Work in Classified Area`
  - `tank entry` $\rightarrow$ `Confined Space Vessel Entry`
- **Fallback to Unknown**: If raw text is missing or cannot be reliably matched to a canonical activity with high confidence, it is labeled as:
  $$\text{UNKNOWN ACTIVITY}$$
  Unknowns are never forced into an arbitrary category.

### 3.2 Dimension 2: Barrier / Control Representation
- **Analytical Truthfulness**: The system **does not** state that a barrier “caused” an incident unless underlying verified evidence proves causality.
- **Defensible Terminology**:
  - **`BARRIER / CONTROL-DEFICIENCY ASSOCIATED OBSERVATION`**
  - **`BARRIER-LINKED OBSERVATION`**
- **Evidence-Supported Control States**:
  Uses the platform's reasoning engine control states.
  1. **Deficiency-Linked States (Counted in Barrier Failure / Deficiency Patterns)**:
     - `ABSENT`: Required control was missing or omitted.
     - `FAILED`: Physical barrier failed mechanically or structurally under load.
     - `BYPASSED`: Safety interlock or procedural barrier was bypassed or overridden.
     - `NOT_VERIFIED`: Isolation or zero-energy state was not tested or confirmed.
     - `INCORRECTLY_ASSUMED`: Hazard protection was assumed in place but was not.
     - `PARTIALLY_EFFECTIVE`: Control reduced exposure but did not fully contain release.
  2. **Non-Deficiency States (Strictly EXCLUDED from Failure Counts)**:
     - `EFFECTIVE`: Control held and performed as designed.
     - `CONTROLLED`: Exposure was interrupted or prevented by the control.
     - `UNKNOWN`: No explicit control performance evidence exists in source data.
  3. **Hindsight Bias Prevention**:
     - Corrective-action text (post-incident remedial actions) is **never** used to infer barrier failure.

### 3.3 Dimension 3: Internal Location Extraction
- **Extraction Hierarchy**:
  1. *Structured Location*: Normalized from `incident.location` via `INTERNAL_LOCATION_ALIASES`.
  2. *Metadata Structure*: Checked for `metadata.work_area`, `metadata.zone`, `metadata.facility_component`, `metadata.operating_area`.
  3. *Narrative Extraction*: Exact regex word-boundary keyword search across canonical internal locations.
  4. *Fallback*: Labeled as `UNKNOWN LOCATION`.
- **No Coordinate Invention**: Real industrial facility areas are normalized; synthetic geographic coordinates are never fabricated.
- **Heatmap Preparation**: Computes `incident_count`, `psif_linked_count`, `psif_linkage_rate`, and a relative intensity index ($0.0 - 1.0$) for site operational heatmap rendering.

---

## 4. Reusable Internal Representation: `PatternObservation`

Every evaluated incident dimension yields an in-memory `PatternObservation`:

```python
@dataclass
class PatternObservation:
    incident_id: str
    workspace: str                    # "admin_flow"
    dimension: str                    # "activity" | "barrier" | "location"
    normalized_value: str
    date: Optional[str] = None        # "YYYY-MM-DD"
    psif_state: str = "NOT_PSIF"      # "PSIF" | "NOT_PSIF" | "INSUFFICIENT_INFORMATION"
    evidence_state: str = "ELIGIBLE"  # "ELIGIBLE" | "INSUFFICIENT_EVIDENCE"
    source_field: str = ""
    normalization_method: str = "unknown"
    # Barrier-specific attributes:
    control_state: Optional[str] = None
    control: Optional[str] = None
    iogp_rule: Optional[str] = None
```

---

## 5. Aggregation, Sorting & Explicit Denominators

### 5.1 Recurring Pattern Definition
A recurring pattern is defined transparently as:
$$\text{A normalized category appearing across } \ge 2 \text{ distinct Admin Flow incidents.}$$
No opaque, uninterpretable "pattern confidence" score is used.

### 5.2 Explicit Denominator Principle
Percentages are never presented ambiguously as "risk" or "probability":
- **Activity Rate**:
  $$\text{PSIF Linkage Rate} = \frac{\text{PSIF-Linked Distinct Incidents}}{\text{Matched Incidents in Category}} \times 100$$
  *Label*: `"64.3% PSIF-linked among matched Admin Flow observations (denominator: 42)"`
- **Barrier Deficiency Rate**:
  $$\text{PSIF Linkage Rate} = \frac{\text{PSIF-Linked Deficiency Incidents}}{\text{Total Deficiency-Associated Incidents}} \times 100$$
  *Label*: `"62.5% PSIF-linked among deficiency-associated observations (denominator: 8)"`

### 5.3 Dimension Sorting Contracts
1. **Activity Patterns**: Sorted strictly descending by `incident_count`.
2. **Barrier Patterns**: Sorted strictly descending by `deficiency_linked_count`.
3. **Location Patterns**: Sorted strictly descending by `incident_count`.

---

## 6. Temporal Recurrence View

- Aggregates distinct incident and PSIF-linked counts by period (`YYYY-MM`).
- Provides historical monthly recurrence without speculative or ungrounded predictive forecasting.

---

## 7. Performance & Scoped Caching

- **Targeted Querying**: Only `Incident.objects.filter(workspace_id='admin_flow')` is queried.
- **Cache Namespace**: `admin_flow:pattern_analysis:<version>`.
- **Cache Invalidation**:
  - `invalidate_admin_flow_pattern_cache()` increments `admin_flow:pattern_analysis:version`.
  - Triggered automatically whenever an incident report is submitted, a batch dataset is ingested, or an adjudication decision is recorded in Admin Flow.
  - Global analytics caches are completely isolated and never affected.

---

## 8. REST API Reference

All endpoints derive the Admin Flow scope strictly from the authenticated user's session (`IsAdminFlowUser`). Workspace parameters supplied in request bodies or query parameters are never trusted.

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/admin-flow/api/patterns/` | `GET` | Consolidated summary across Activity, Barrier, Location, and Temporal dimensions. |
| `/admin-flow/api/patterns/activity/` | `GET` | Activity categories ranked descending by incident frequency with PSIF linkage. |
| `/admin-flow/api/patterns/barrier/` | `GET` | Barrier categories ranked descending by deficiency-linked incident frequency. |
| `/admin-flow/api/patterns/location/` | `GET` | Internal locations ranked descending by frequency, including heatmap intensity. |

### Sample JSON Response (`/admin-flow/api/patterns/`)
```json
{
  "workspace_id": "admin_flow",
  "site_context": "Duliajan Operational Complex",
  "total_incidents": 21,
  "has_data": true,
  "recurring_counts": {
    "activities": 3,
    "barriers": 2,
    "locations": 3
  },
  "activity_patterns": [
    {
      "category": "Safe Mechanical Lifting",
      "incident_count": 10,
      "psif_linked_count": 6,
      "psif_linkage_rate": 60.0,
      "rate_label": "60.0% PSIF-linked among matched Admin Flow observations (denominator: 10)",
      "is_recurring": true,
      "sample_incident_ids": ["..."]
    }
  ],
  "barrier_patterns": [
    {
      "barrier_domain": "Energy Isolation",
      "deficiency_linked_count": 8,
      "total_matched_count": 8,
      "psif_linked_count": 5,
      "psif_linkage_rate": 62.5,
      "rate_label": "62.5% PSIF-linked among deficiency-associated observations (denominator: 8)",
      "is_recurring": true,
      "state_breakdown": {
        "BYPASSED": 8,
        "FAILED": 0,
        "ABSENT": 0
      }
    }
  ],
  "location_patterns": [
    {
      "internal_location": "Tank Farm",
      "site_context": "Duliajan Operational Complex",
      "incident_count": 12,
      "psif_linked_count": 4,
      "psif_linkage_rate": 33.3,
      "heatmap_intensity": 1.0,
      "is_recurring": true
    }
  ],
  "temporal_patterns": [
    {
      "period": "2026-08",
      "incident_count": 14,
      "psif_linked_count": 7
    }
  ]
}
```

---

## 9. Automated Test Suite

Tested in [`tests/test_task3_admin_flow_pattern_analysis.py`](file:///Users/sas/Developer/prototype_165/tests/test_task3_admin_flow_pattern_analysis.py):
- Mandated fixture counts (Activities: 10, 7, 3; Barriers: 8, 5; Locations: 12, 7, 2).
- Strict descending sort verification.
- Control state filtering (`EFFECTIVE` and `UNKNOWN` excluded from failure counts).
- Normalization and fallback to `UNKNOWN ACTIVITY` and `UNKNOWN LOCATION`.
- Rate calculation and explicit denominator labeling.
- Two-way workspace isolation against global production records.
- REST API permission gating and payload validation.
- Cache invalidation lifecycle.

All 9 tests pass cleanly with zero warnings or regressions.
