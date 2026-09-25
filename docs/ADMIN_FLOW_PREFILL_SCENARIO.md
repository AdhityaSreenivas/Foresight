# Admin Flow Pre-fill SIF Precursor Scenario Documentation

## 1. Scenario Purpose & Overview

The **Admin Flow Submit Report** page (`/admin-flow/submit/`) includes a convenience button:
> **"Pre-fill SIF Precursor Scenario"** (`#btn-prefill-scenario`)

Its objective is to populate the incident submission form with a single, highly coherent, realistic, and internally consistent Near Miss report. The incident is designed to naturally exercise the canonical Foresight SIF precursor (PSIF) pipeline and deterministic reasoning engine without bypassing, weakening, or hardcoding any classifier rules.

### Key Tenets
1. **No Classifier Modifications**: No model thresholds, rule sets, or IOGP matching dictionaries were artificially weakened.
2. **Single IOGP Match**: Naturally resolves to **Rule 4: Energy Isolation** and **ONLY** Energy Isolation.
3. **Deterministic Reasoning Pathway**: Exercises `PSIF-R-03` (*Stored Pressure Line Breaking Without Verified Isolation*) under EEI SCL 2021 Section 2.1 (*Stored Energy Release*).
4. **Pattern Analysis Integration**: Populates standardized Activity (*Pressure-Line Maintenance / Flange Breaking*), Location (*Compressor Area*), and Barrier Deficiency (*Energy Isolation: NOT_VERIFIED*).
5. **Idempotent & Safe**: Clicking the pre-fill button multiple times refreshes the values without appending text or corrupting inputs.

---

## 2. Exact Field Mapping

| Form Field | Element ID / Name | Populated Value | Design Rationale |
| :--- | :--- | :--- | :--- |
| **Report Type** | `id_report_type` | `near_miss` | Represents an event where an open pathway existed but serious injury was narrowly avoided. |
| **Date of Event** | `id_incident_date` | Dynamic current date (`YYYY-MM-DD`) | Uses the current date (`new Date().toISOString().split("T")[0]`) to ensure freshness. |
| **Site / Location** | `id_location` | `Compressor Area` | Standardized high-energy compressor process area recognized by pattern analysis. |
| **Department / Asset**| `id_department` | `Mechanical Maintenance / Gas Compressor Train` | Mechanical maintenance operational domain. |
| **Activity / Job Task**| `id_job_task` | `Pressure-Line Maintenance / Flange Breaking` | Explicit activity that links to line breaking and flange opening. |
| **Equipment Involved**| `id_equipment_involved` | `Gas compressor discharge line and isolation valves` | Establishes pressurized gas piping and manual isolation barriers. |
| **Description / Narrative**| `id_description` | Detailed narrative (see below) | Contains high energy, direct worker line-of-fire exposure, unverified isolation, and release. |
| **Immediate Action Taken / Observed Cause**| `id_immediate_cause` | Action narrative (see below) | Concise (241 chars, within `max_length=255`), reinforces zero-energy verification deficiency. |
| **Witness Statement** | `id_witness_statement` | Supporting account (see below) | Confirms technician had not received zero-energy confirmation before loosening bolts. |
| **Corrective Action Suggestion**| `id_corrective_actions` | Evidence-linked action (see below) | Documents verification-before-touch requirement; purely action-oriented (not predictive). |
| **High-Energy Present**| `id_high_energy_present` | `yes` | Explicit structured affirmation of high-energy hazard. |
| **High-Energy Type** | `id_energy_type` | `pressure` | Mapped to canonical `pressure_stored` energy hazard. |
| **Direct Control Present**| `id_direct_control_present` | `yes` | Confirms an engineered barrier (isolation valve) was conceptually present. |
| **Direct Control Status**| `id_control_condition` | `unknown` (*Unknown / Not Determined*) | Uses the canonical enum choice on `IncidentReportForm`; narrative provides explicit evidence of `NOT_VERIFIED`. |

---

## 3. Narrative Text & Semantic Construction

### 3.1 Description / Event Narrative (`id_description`)
> *"During maintenance on the gas compressor discharge line, the maintenance crew prepared to break containment at a flange after shutting the upstream isolation valve. The required zero-energy verification had not been completed and energy isolation was not verified before breaking flange. Residual pressure remained in the line. One technician was positioned directly in the release path adjacent to the flange while unbolting the connection. A sudden release of pressurized hydrocarbon gas occurred from the flange toward the technician. The technician was directly exposed to the release path before moving clear. The incident was identified as a near miss involving unverified energy isolation and direct worker exposure to the potential release path."*

#### Semantic Structure & Pipeline Fit:
- **Temporal Sequence**:
  - *Before Work*: Upstream valve was shut (planned barrier).
  - *Verification Step*: Zero-energy verification not completed; energy isolation was not verified.
  - *Exposure*: Worker positioned directly adjacent in release path during unbolting.
  - *Physical Event*: Pressurized hydrocarbon gas released toward worker.
  - *Intervention*: Worker exposed in release path before moving clear.
- **Exposure Avoidance Trap**: Phrased as *"The technician was directly exposed to the release path before moving clear"* so as not to trigger `EXPOSURE_INTERRUPTED_PATTERNS` (which would otherwise prematurely force a non-PSIF decision).

### 3.2 Immediate Cause (`id_immediate_cause`)
> *"Work stopped immediately upon release. Line was re-isolated, residual pressure safely relieved, and isolation confirmed. Immediate precursor: failure to complete and independently confirm zero-energy verification before breaking containment."*
- **Length**: 241 characters (complies with PostgreSQL `VARCHAR(255)` constraint on `Incident.immediate_cause`).
- **Function**: Re-affirms energy isolation failure without introducing extraneous hazards.

### 3.3 Witness Statement (`id_witness_statement`)
> *"Before the flange was loosened, the technician had not received confirmation that zero energy had been verified. A residual release was observed when the connection was opened."*

### 3.4 Corrective Action Suggestion (`id_corrective_actions`)
> *"Require documented zero-energy verification and independent confirmation of isolation before breaking containment on pressurized lines. Reinforce verification-before-touch requirements for maintenance activities."*

---

## 4. Canonical IOGP Life-Saving Rules Evaluation

### Audit of Competing Life-Saving Rules
To ensure **one and ONLY one** IOGP Life-Saving Rule matches:
- **Energy Isolation (MATCH)**: Triggered naturally by `"isolated"`, `"isolation"`, and verified line breaking context across composite fields.
- **Line of Fire (EXCLUDED)**: The narrative avoids consecutive noun phrases like `"pressure release"` or `"line of fire"`, and avoids vehicle / falling object contexts.
- **Hot Work (EXCLUDED)**: Avoids terms like `"fire"`, `"hot work"`, `"welding"`, `"cutting"`, `"grinding"`.
- **Safe Mechanical Lifting (EXCLUDED)**: Avoids words containing `"lift"`, `"crane"`, `"hoist"`, `"rigging"`, `"drop"`.
- **Work Authorization (EXCLUDED)**: Avoids `"permit"`, `"ptw"`, `"jsa"`, `"toolbox"`.
- **Confined Space (EXCLUDED)**: Avoids `"confined space"`, `"tank"`, `"vessel entry"`.
- **Working at Height (EXCLUDED)**: Avoids `"scaffold"`, `"fall"`, `"height"`, `"ladder"`.

**Observed Result**:
- `inc.iogp_rules.all()`: `['Energy Isolation']` (Count: 1).

---

## 5. PSIF Reasoning Pathway (`PSIF-R-03`)

The canonical reasoning engine evaluates the incident across the four core dimensions:

1. **Hazard**: `PRESSURE_STORED` (from structured `energy_type='pressure'` and narrative piping discharge context).
2. **Worker Exposure**: `DIRECT_EXPOSURE` / `IN_RELEASE_PATH` (worker actively loosening flange in direct gas trajectory).
3. **Control State**: `NOT_VERIFIED` (extracted from `"energy isolation was not verified before breaking flange"`).
4. **Consequence**: `SEVERE_TRAUMA` / `PRESSURE_RELEASE` (high-velocity gas release pathway open).

### Reconciled Deterministic Output
- **Rule ID**: `PSIF-R-03` (*Stored Pressure Line Breaking Without Verified Isolation*)
- **Rule Decision**: `PSIF_PATHWAY_OPEN`
- **User-Facing Decision**: `PSIF` (Precursor Candidate)
- **Why PSIF Explanation**:
  > *"The incident presents an open PSIF precursor pathway under rule 'Stored Pressure Line Breaking Without Verified Isolation' [EEI SCL 2021 Section 2.1 Stored Energy Release]. High energy (pressure_stored) was present, worker exposure was direct exposure, and critical barrier condition was evaluated as not verified. Consequence pathway to serious injury was physically supported with direct line-of-fire exposure."*

---

## 6. Admin Flow Pattern Analysis Integration

When evaluated by `apps/admin_flow/pattern_engine.py`:
- **Activity**: `normalize_admin_flow_activity()` maps `"Pressure-Line Maintenance / Flange Breaking"` to canonical activity `"Pressure-Line Maintenance / Flange Breaking"`.
- **Location**: `normalize_admin_flow_location()` maps `"Compressor Area"` to `"Compressor Area"`.
- **Barrier Observation**:
  - `control`: `"Energy Isolation"`
  - `control_state`: `"NOT_VERIFIED"`
  - `is_deficiency`: `True`
  - `source_field`: `"composite_narrative"`

This ensures that repeated demonstrations in Admin Flow increment the recurrence counts for **Compressor Area**, **Pressure-Line Maintenance**, and **Energy Isolation** deficiencies.

---

## 7. Verification & Automated Test Suite

A comprehensive test suite was added in `tests/test_admin_flow_prefill_scenario.py`:
- `test_prefill_button_rendered_in_submit_report_page`: Asserts DOM elements and JavaScript prefill payloads.
- `test_canonical_iogp_classifier_produces_only_energy_isolation`: Confirms exactly 1 IOGP match.
- `test_reasoning_pipeline_exercises_psif_pathway`: Confirms `PSIF-R-03` triggers with `NOT_VERIFIED` control condition.
- `test_end_to_end_submission_and_detail_view`: Submits through Admin Flow HTTP view, verifies model execution, barrier observation extraction, and detail page rendering.

**Full Test Suite Run**: 50/50 tests passed (`pytest tests/test_admin_flow*.py`).
