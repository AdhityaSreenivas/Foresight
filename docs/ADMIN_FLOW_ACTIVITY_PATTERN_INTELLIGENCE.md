# Admin Flow Activity Pattern Intelligence System

## 1. System Overview & Core Philosophy

The **Admin Flow Activity Pattern Intelligence System** provides operational task and work activity pattern recognition across the Foresight platform workspace for industrial complexes (such as the Duliajan Operational Complex).

Historically, the Activity Pattern view inadvertently conflated **IOGP Life-Saving Rules** (e.g., *Energy Isolation*, *Safe Mechanical Lifting*, *Driving*, *Working at Height*, *Hot Work*, *Confined Space*) with actual work activities. This implementation completely rebuilds the system around a strict, multi-dimensional semantic separation:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                      5 DECOUPLED OPERATIONAL DIMENSIONS                          │
├───────────────────────┬──────────────────────────────────────────────────────────┤
│ DIMENSION             │ FUNDAMENTAL QUESTION ANSWERED                            │
├───────────────────────┼──────────────────────────────────────────────────────────┤
│ 1. ACTIVITY           │ "What work or operational task was being performed?"     │
│ 2. LOCATION           │ "Where on site did the incident or exposure occur?"      │
│ 3. BARRIER / CONTROL  │ "What physical safeguard or control was in place/failed?"│
│ 4. IOGP RULE          │ "Which Life-Saving Rule domain applied to the work?"     │
│ 5. PSIF RESULT        │ "Did evidence support a Potential SIF (Serious Injury)?" │
└───────────────────────┴──────────────────────────────────────────────────────────┘
```

> **Core Principle:** An incident may have `Activity = Painting`, `Location = Process Area`, `Barrier = Gas Detector`, `IOGP = Hot Work`, and `PSIF = NOT PSIF`. The Activity Pattern page aggregates and ranks **Painting**, completely independently of whether Hot Work or another rule applied.

---

## 2. Activity Definition & Canonical Taxonomy

### Activity Definition
An **Activity** is strictly defined as:
> **The work being performed or operational task taking place at the time of the event.**

It represents "what workers were doing" rather than "which safety rule governed it" or "what equipment was involved".

### Canonical Operational Taxonomy (20 Categories)

The system normalizes raw text and job tasks into 20 canonical operational categories defined in `ActivityCategory`:

| Category Enum Key | Canonical Display Name | Representative Industrial Work Tasks |
|:---|:---|:---|
| `PAINTING` | Painting & Surface Coating | Spray painting, brush painting, abrasive blasting, grit blasting, primer application |
| `CLEANING` | Cleaning & Housekeeping | Floor scrubbing, degreasing, workshop housekeeping, spill cleanup, vacuuming |
| `DIGGING_EXCAVATION` | Digging / Excavation | Trench excavation, backhoe trenching, earthmoving, potholing, shoring installation |
| `LABORATORY_RESEARCH` | Laboratory / Research | Chemical sampling analysis, titration, lab testing, glassware handling, spectrometry |
| `VEHICLE_PARKING_OPERATIONS` | Vehicle / Parking Operations | Forklift staging, light vehicle parking, truck maneuvering, reversing in yard |
| `EQUIPMENT_MAINTENANCE` | Equipment Maintenance & Servicing | Pump overhaul, compressor servicing, filter replacement, gearbox maintenance |
| `LIFTING_OPERATION` | Lifting Operation / Crane Work | Mobile crane rigging, overhead hoist lift, winch pull, tandem lift, sling positioning |
| `WELDING_CUTTING` | Welding, Cutting & Hot Work | TIG/MIG welding, oxy-acetylene torch cutting, beveling, plasma gouging |
| `INSPECTION_AUDITING` | Inspection & Quality Auditing | NDT inspection, visual weld audit, thickness gauging, pre-startup safety review |
| `ELECTRICAL_MAINTENANCE` | Electrical Maintenance & Troubleshooting | Switchgear wiring, breaker rack-out, transformer testing, cable pulling |
| `HOUSEKEEPING` | Housekeeping & Area Upkeep | Yard clearance, scrap bin emptying, walkway sweeping, debris clearing |
| `LOADING_UNLOADING` | Loading / Unloading Operations | Flatbed truck offloading, bulk tanker connection, ISO container stuffing |
| `DRILLING_OPERATIONS` | Drilling & Rig Floor Operations | Pipe tripping, casing running, drilling fluid mixing, BOP testing |
| `PIPELINE_MAINTENANCE` | Pipeline Maintenance & Valve Work | Flange makeup, valve greasing, pig launching/receiving, pipe spool replacement |
| `ELEVATED_WORK_SCAFFOLDING` | Work at Height / Scaffolding | Scaffold erection, grating modification, ladder access, roof maintenance |
| `CONSTRUCTION_FABRICATION` | Structural Construction & Fabrication | Rebar tying, concrete pour, formwork assembly, steel structural erection |
| `SAMPLING_TESTING` | Sampling, Testing & Calibration | Hydrostatic pressure testing, gas sample draw, relief valve bench test |
| `CHEMICAL_HANDLING` | Chemical Handling & Transfer | Biocide injection, acid tote transfer, corrosion inhibitor drum dispensing |
| `INTERNAL_VESSEL_WORK` | Internal Vessel Cleaning & Inspection | Tank sludge cleanout, column tray inspection, reactor vessel entry |
| `UNKNOWN_ACTIVITY` | UNKNOWN ACTIVITY | Genuine absence of task information in structured and narrative data |

---

## 3. Extraction, Normalization & Source Priority Hierarchy

Activity identification follows a deterministic 4-tier precedence hierarchy:

```
[1. Structured Job Task / Activity Field]
                   │
                   ▼ (Check for anti-contamination / forbidden values)
        Contaminated / Missing?
        ├── NO  ──► Map through ACTIVITY_ALIASES ──► Canonical Activity
        └── YES ──► Fallback to Tier 2
                   │
[2. Narrative Grammar & Temporal Extraction]
                   │
                   ├── Temporal Sequence ("After completing welding, workers began cleaning")
                   ├── Active Prepositional Grammar ("While painting the vessel...")
                   └── Domain Keyword Regex ("flange breaking", "pump overhaul")
                   │
        Extracted successfully?
        ├── YES ──► Canonical Activity
        └── NO  ──► Fallback to Tier 3
                   │
[3. Operational Remapping (for contaminated aliases)]
                   │
                   └── Driving ──► Vehicle / Parking Operations
                   └── Lifting ──► Lifting Operation / Crane Work
                   └── Isolation ──► Equipment Maintenance & Servicing
                   │
[4. UNKNOWN ACTIVITY] (Legitimate unknown sentinel)
```

### Strict Anti-Contamination Guardrails
The system explicitly rejects terms that conflate other dimensions with activity:
1. **Forbidden IOGP Rule Names**: `energy isolation`, `safe mechanical lifting`, `hot work`, `driving`, `confined space`, `working at height`, `bypassing safety controls`, `line of fire`, `work authorization`.
2. **Forbidden Barrier Names**: `safety harness`, `gas detector`, `interlock`, `relief valve`, `trench shoring`, `machine guard`.
3. **Forbidden Hazard Names**: `gravity`, `stored pressure`, `flammable vapor`, `toxic gas`, `electricity`.
4. **Forbidden Equipment Alone**: `pump`, `compressor`, `crane`, `forklift`, `tank`.

---

## 4. Object vs. Activity Separation & Temporal Parsing

### Object vs. Activity Separation
Industrial narratives frequently mention an equipment object alongside a task:
- *"Centrifugal pump maintenance in compressor station"*
  - **Activity**: `Equipment Maintenance & Servicing`
  - **Equipment Involved**: `Centrifugal Pump`
  - **Location**: `Compressor Area`

### Temporal Role Parsing
When incidents document a sequence of activities, safety pattern analysis must identify the activity underway **at the time of the hazardous event or precursor**, not an earlier completed task:
- *"After completing welding, workers began cleaning the workshop floor when an oily rag caught fire."*
  - **Activity**: `Cleaning & Housekeeping` (active at event time)
  - **Associated IOGP**: `Hot Work` (remains linked via historical association)

---

## 5. Aggregation Metrics & Recurrence Semantics

For each canonical activity $A$ within the scoped workspace incidents ($N_{\text{total}}$):

1. **Incident Count ($N_A$)**: Distinct incidents whose primary activity is $A$.
2. **PSIF-Linked Count ($S_A$)**: Incidents in $A$ where canonical prediction has `psif_predicted = True` and `is_sparse_input = False`.
3. **PSIF Linkage Rate**:
   $$\text{Rate}_A = \frac{S_A}{N_A} \times 100\%$$
   Always accompanied by explicit denominator labels (e.g., `66.7% (20/30)`).
4. **Dataset Share**:
   $$\text{Share}_A = \frac{N_A}{N_{\text{total}}} \times 100\%$$
5. **Recurring Pattern Semantics**:
   - An activity pattern is designated **Recurring** if and only if $N_A \ge 2$.
   - Activities with $N_A = 1$ are designated **Single Observation**.
   - The term "risk score" or "probability of activity risk" is strictly avoided in favor of observed empirical counts.

---

## 6. Multi-Dimensional Observed Associations

The engine surfaces cross-dimensional correlations while maintaining linguistic and conceptual independence:
- **Activity × Location Matrix**: 2D grid correlating activities across site locations (Process Area, Workshop, Tank Farm, Wellhead Area, etc.) with 0-to-4 heat intensities.
- **Activity × Barrier Associations**: Empirically observed physical safeguards (e.g., *Painting* $\rightarrow$ Gas Detector; *Excavation* $\rightarrow$ Trench Shoring).
- **Activity × IOGP Associations**: Life-Saving Rules active during the activity (e.g., *Painting* $\rightarrow$ Hot Work; *Cleaning* $\rightarrow$ Energy Isolation).
- **Labeling Standard**: Always explicitly labeled as `"Observed historical association"` or `"Observed correlation"`—never as "causation" or "risk probability".

---

## 7. Performance, Caching & Invalidation

1. **Deterministic Version-Controlled Caching**:
   - Key: `admin_flow:activity_patterns:{version}:{hash}`
   - Default TTL: 300 seconds.
2. **Atomic Lifecycle Invalidation**:
   - Cache version bumps atomically upon incident submission, dataset upload, or workspace reset via `invalidate_admin_flow_activity_cache()` and `invalidate_admin_flow_pattern_cache()`.
3. **Database Aggregation**: Zero NLP re-parsing during view loads; pre-indexed SQL selections and single-pass Python aggregation ensure sub-50ms query times across 1,000+ incidents.

---

## 8. REST API Specification

### Endpoint: `GET /admin-flow/api/patterns/activity/`

#### Query Parameters:
- `date_from` (YYYY-MM-DD): Earliest incident date filter.
- `date_to` (YYYY-MM-DD): Latest incident date filter.
- `psif` (`all` | `psif` | `not_psif`): PSIF subset filter.
- `q` (string): Text filter matching activity name or keywords.

#### Sample Response Structure:
```json
{
  "summary": {
    "total_incidents": 1000,
    "known_activity_incidents": 1000,
    "unknown_activity_incidents": 0,
    "activity_coverage_rate": 100.0,
    "recurring_pattern_count": 14,
    "unique_activities_count": 14
  },
  "top_activity": {
    "activity": "Vehicle / Parking Operations",
    "display_name": "Vehicle / Parking Operations",
    "incident_count": 140,
    "psif_linked_count": 27,
    "psif_linkage_rate": 19.3,
    "dataset_share": 14.0,
    "top_location": "Workshop / Maintenance Bay",
    "top_barrier": "Segregation Barrier / Wheel Chock",
    "top_iogp_rule": "Driving"
  },
  "activities": [
    {
      "activity": "Vehicle / Parking Operations",
      "display_name": "Vehicle / Parking Operations",
      "rank": 1,
      "incident_count": 140,
      "psif_linked_count": 27,
      "psif_linkage_rate": 19.3,
      "dataset_share": 14.0,
      "is_recurring": true,
      "top_locations": [{"name": "Workshop / Maintenance Bay", "count": 52}],
      "top_barriers": [{"name": "Segregation Barrier / Wheel Chock", "count": 68}],
      "associated_iogp": [{"name": "Driving", "count": 140}]
    }
  ],
  "location_matrix": {
    "columns": ["Process Area / Refining Unit", "Workshop / Maintenance Bay", "Tank Farm", "Compressor Area", "Pipe Rack / Manifold", "Wellhead Area"],
    "rows": [...]
  }
}
```

---

## 9. Limitations & Guardrails
- **Scope Boundary**: Strictly applies to `workspace_id = 'admin_flow'`. Regular user dashboards, global IOGP classifiers, and canonical PSIF ML models are completely unmodified.
- **Genuine Unknowns**: If an incident narrative provides no clue of the operational task (e.g. *"Near miss recorded during shift change without task details"*), it is classified as `UNKNOWN ACTIVITY` to prevent false attribution.
