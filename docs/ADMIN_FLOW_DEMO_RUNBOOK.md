# Foresight PSIF Platform — Admin Flow Judge Demonstration Runbook

## Executive Summary

The **Admin Flow** is an isolated, evaluator-facing demonstration workspace embedded within Foresight. It allows judges, evaluators, and safety leaders to experience the full operational lifecycle of Foresight:

$$\text{Ingest} \longrightarrow \text{Classify} \longrightarrow \text{Explain} \longrightarrow \text{Aggregate} \longrightarrow \text{Surface Recurrent Patterns} \longrightarrow \text{Visualize Activity, Barrier \& Location Dimensions}$$

All operations execute inside an isolated demonstration scope (`workspace_id = 'admin_flow'`) without modifying or contaminating the 561,378 enterprise production records.

---

## Demonstration Credentials & Environment Setup

| Parameter | Demonstration Value | Description |
| :--- | :--- | :--- |
| **Server URL** | `http://127.0.0.1:8000/` | Local development server |
| **Admin Flow User** | `admin_flow@foresight.app` | Evaluator demonstration account (`is_admin_flow = True`) |
| **Admin Flow Password** | `foresight2026` | Unified demonstration password |
| **Standard Enterprise User** | `admin@foresight.app` | Global administrator account (`is_admin_flow = False`) |
| **Standard Password** | `foresight2026` | Unified demonstration password |
| **Demonstration Scope** | `workspace_id = 'admin_flow'` | Isolated tenant tag |
| **Production Baseline** | `561,378` records | Unaltered enterprise dataset |

---

## 25-Step Guided Judge Demonstration Flow

```
[1. Login] ──> [2-4. Baseline 0/0/0/0/0/0] ──> [5-8. Single Submit (1)] ──> [9-12. Review & Classifications]
                                                                                      │
[24-25. Global Isolation] <── [22-23. Logout] <── [16-21. Pattern Analysis Hub] <── [13-15. Batch Upload (3+)]
```

### Phase A: Authentication & Initial Zero-Baseline Verification

#### Step 1: Open Login Page
- **Action**: Navigate to `http://127.0.0.1:8000/accounts/login/` (or click "Login" from the landing page).
- **Expected Visual**: The Foresight enterprise login page loads with industrial safety imagery.

#### Step 2: Log in as Admin Flow Evaluator
- **Action**: Enter `admin_flow@foresight.app` and password `foresight2026`, then click **Sign In**.
- **Expected Visual**: Immediate redirect to the dedicated Admin Flow dashboard (`/admin-flow/dashboard/`).

#### Step 3: Dashboard Layout Appears
- **Action**: Inspect the top navigation bar and header.
- **Expected Visual**:
  - Top banner confirms: `Admin Flow Demonstration Workspace — Scoped to isolated demonstration data`.
  - Clean 7-item navigation: **Dashboard**, **Submit Report**, **Upload Dataset**, **Incidents**, **PSIF Classification**, **IOGP Classification**, **Pattern Analysis**.

#### Step 4: Verify Genuine Zero Baseline
- **Action**: Review the 6 primary metric cards at the top of the dashboard.
- **Expected Visual**: All six metric cards strictly display **0**:
  - `TOTAL INCIDENTS`: **0**
  - `PREDICTION ELIGIBLE`: **0**
  - `PSIF PRECURSORS`: **0**
  - `NON-PSIF INCIDENTS`: **0**
  - `INSUFFICIENT EVIDENCE`: **0**
  - `HUMAN REVIEWED`: **0**
  - *No synthetic or fake records are seeded automatically.*

---

### Phase B: Single Incident Ingestion & Forensics

#### Step 5: Click Submit Report
- **Action**: Click the **Submit Report** link in the navigation bar or the **Single Incident Prediction** action card.
- **Expected Visual**: The *Submit Demonstration Report* form loads at `/admin-flow/submit/`.

#### Step 6: Submit One Incident Precursor
- **Action**: Fill in a high-consequence precursor narrative:
  - **Report Type**: Near Miss
  - **Incident Date**: Today's date (e.g. `2026-09-10`)
  - **Location**: `Compressor Area`
  - **Department**: `Operations`
  - **Activity / Job Task**: `Hot Work in Classified Area`
  - **High Energy Present**: `Yes` (Energy Type: `Pressure`)
  - **Direct Control Present**: `Yes` (Control Condition: `Failed`)
  - **Description**: `Worker observed high-pressure gas leaking from compressor discharge flange while preparing hot work cutting torch nearby.`
  - **Action**: Click **Submit & Process Precursor Prediction**.

#### Step 7: Return to Dashboard
- **Action**: Click **Dashboard** in the navigation header.

#### Step 8: Verify Dashboard Counters Increment
- **Action**: Observe the KPI cards.
- **Expected Visual**:
  - `TOTAL INCIDENTS`: **1**
  - `PREDICTION ELIGIBLE`: **1**
  - `PSIF PRECURSORS`: **1**
  - The live counter increments dynamically from real ingestion.

#### Step 9: Open Incidents Table
- **Action**: Click **Incidents** in the navbar (`/admin-flow/incidents/`).
- **Expected Visual**: A single record appears in the table showing `Compressor Area`, `Operations`, `Hot Work in Classified Area`, and `CRITICAL` risk indicator.

#### Step 10: Open Incident Detail View
- **Action**: Click on the incident ID or description.
- **Expected Visual**: The detailed forensic view opens (`/admin-flow/incidents/<id>/`), displaying the full incident narrative, physical energy context, and control condition.

#### Step 11: Show PSIF Classification
- **Action**: Click **PSIF Classification** in the navbar (`/admin-flow/psif/`).
- **Expected Visual**: The PSIF Precursor Classification analytics page displays the single classified incident, model confidence metrics, and evidence strength distribution.

#### Step 12: Show IOGP Classification
- **Action**: Click **IOGP Classification** in the navbar (`/admin-flow/iogp/`).
- **Expected Visual**: The IOGP Life-Saving Rules matrix highlights matched rules (e.g., *Hot Work*, *Energy Isolation*) linked to the newly ingested incident.

---

### Phase C: Multi-Incident Batch Upload & Pattern Emergence

#### Step 13: Upload Multi-Incident Dataset
- **Action**: Click **Upload Dataset** in the navbar (`/admin-flow/upload/`).
- **Action**: Choose a demonstration CSV file (or use the sample format):
  ```csv
  Date,Department,Activity,Description,Location,HighEnergy,ControlStatus
  2026-09-09,Rigging,Safe Mechanical Lifting,Heavy lift crane sling slipped while hoisting drill pipe in Workshop.,Workshop,yes,failed
  2026-09-08,Logistics,Hazardous Material Handling,Chemical drum drain valve overflowed in Tank Farm.,Tank Farm,no,effective
  ```
- **Action**: Click **Upload Demonstration Dataset**.

#### Step 14: Automated Processing Completes
- **Action**: The platform ingests, validates, tokens, and scopes the dataset records to `workspace_id = 'admin_flow'`.

#### Step 15: Verify Counters & Pattern Snapshot on Dashboard
- **Action**: Return to `/admin-flow/dashboard/`.
- **Expected Visual**:
  - `TOTAL INCIDENTS` increases from **1** to **3+**.
  - Directly under the action cards, the new **PATTERN SNAPSHOT** section appears:
    - **Top Activity**: e.g., *Hot Work in Classified Area*
    - **Top Barrier-Linked Signal**: e.g., *Energy Isolation (Failed/Bypassed)*
    - **Top Location**: e.g., *Compressor Area*
    - **CTA Button**: `View Pattern Analysis →`

---

### Phase D: Pattern Analysis Hub & Multi-Dimensional Deep Dives

#### Step 16: Open Pattern Analysis Landing Page (Hub)
- **Action**: Click **Pattern Analysis** in the navbar or **View Pattern Analysis** on the dashboard (`/admin-flow/patterns/`).
- **Expected Visual**:
  - **Top-Level Pattern Summary**: Total Incidents, Most frequent activity, Most frequent barrier-linked signal, Highest observation concentration.
  - **Three Visual Decision Cards**:
    1. `ACTIVITY PATTERNS`: *"Which activities occur most frequently?"*
    2. `BARRIER / CONTROL PATTERNS`: *"Which control-deficiency signals recur?"*
    3. `LOCATION PATTERNS`: *"Where are observations concentrated?"*
  - **Empirical Relationship Pathway**:
    $$\text{Activity} \longrightarrow \text{Location} \longrightarrow \text{Barrier / Control Signal} \longrightarrow \text{PSIF Observations}$$
  - **Methodology Disclaimers**: Clarifies historical association vs causation.

#### Step 17: Explore Activity Pattern Analysis
- **Action**: Click the `ACTIVITY PATTERNS` card (`/admin-flow/patterns/activity/`).
- **Expected Visual**:
  - Ranked horizontal bar chart of normalized operational activities.
  - Dual-view toggle (Ranked Activity Bar Distribution vs Detailed Comparative Data Table).
  - PSIF Precursor Linkage Rates per activity category.

#### Step 18: Explore Barrier / Control Pattern Analysis
- **Action**: Click **Barrier Patterns** in the sub-tab bar (`/admin-flow/patterns/barrier/`).
- **Expected Visual**:
  - Control-deficiency signals derived strictly from evidence-supported failed/bypassed states.
  - IOGP Life-Saving Rule control linkage and confidence distributions.
  - Filterable by date, PSIF status, and query term.

#### Step 19: Explore Location Pattern Analysis & Site Heatmap
- **Action**: Click **Location Patterns** in the sub-tab bar (`/admin-flow/patterns/location/`).
- **Expected Visual**:
  - **3x3 Schematic Site Heatmap**: Visualizes the single operational site's internal facility layout:
    - *Wellhead Area*, *Process Area*, *Compressor Area*
    - *Tank Farm*, *Pipe Rack*, *Drilling Area*
    - *Warehouse*, *Workshop*, *Main Gate*
  - Intensity coloring reflects incident observation density (not fabricated GPS coordinates).

#### Step 20: Click an Internal Location (Drill-Down)
- **Action**: Click on `Compressor Area` or `Workshop` in the grid or rankings table.
- **Expected Visual**: Interactive detail drawer updates dynamically to show the specific location profile.

#### Step 21: Inspect Linked Activity & Barrier Signals
- **Action**: Review the drill-down panel for the selected location.
- **Expected Visual**:
  - Top linked operational activities for this location.
  - Top recurring barrier failure signals in this specific zone.
  - Observed multi-dimensional pattern chain: $\text{Location} \rightarrow \text{Activity} \rightarrow \text{Barrier Deficiency}$.

---

### Phase E: Verification of Enterprise Workspace Isolation

#### Step 22: Return to Dashboard
- **Action**: Click **Dashboard** in the top navigation bar.
- **Expected Visual**: All metric cards reflect the demonstration data accrued during the session.

#### Step 23: Log Out
- **Action**: Click **Sign Out** in the user menu.
- **Expected Visual**: Session terminates cleanly and redirects to the login screen.

#### Step 24: Log In as Standard Enterprise Administrator
- **Action**: Enter `admin@foresight.app` with password `foresight2026`.
- **Expected Visual**: Redirects to the global platform dashboard at `/dashboard/`.

#### Step 25: Verify Global Dashboard & Navigation Are Unaltered
- **Action**: Inspect the enterprise global view.
- **Expected Visual**:
  - Top navigation displays enterprise menus (**Dashboard**, **Datasets**, **Incidents**, **Predictions**, **Model Assurance**, **Data Quality**).
  - No Admin Flow banners or links exist.
  - Incident count remains the intact enterprise count (**561,378 incidents**). None of the Admin Flow demonstration records leaked into enterprise reports.
  - **Direct Access Prevention**: Attempting to navigate directly to `/admin-flow/patterns/` or `/admin-flow/dashboard/` immediately returns **HTTP 403 Forbidden**.

---

## Methodology Reference

Throughout the Admin Flow experience, subtle methodology badges remind evaluators:
1. *"Pattern analysis is based on the current Admin Flow demonstration dataset."*
2. *"Patterns represent historical observation frequency and association."*
3. *"Barrier-linked observations are based on evidence-supported control states."*
4. *"Pattern analysis does not establish causation or predict future incidents."*
