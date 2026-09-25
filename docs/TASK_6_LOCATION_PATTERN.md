# TASK 6 — ADMIN FLOW LOCATION PATTERN ANALYSIS + SCHEMATIC SITE HEATMAP

**Foresight PSIF Platform — AI-Powered Operational Safety Precursor Intelligence**  
**Problem Statement ID**: 26165  
**Component**: Admin Flow Location Pattern Analysis  
**Route**: `/admin-flow/patterns/location/`  
**API Endpoint**: `/admin-flow/api/patterns/location/`  
**Date**: September 2026  

---

## 1. Executive Summary

Task 6 implements the **Location-Based Pattern Analysis** module and visual **Schematic Site Heatmap** within the Admin Flow operational intelligence pipeline. 

Operating strictly within the isolated demonstration workspace (`workspace_id = 'admin_flow'`), this module surfaces where precursor observations are concentrated across internal facility zones (e.g., *Compressor Area*, *Process Area*, *Workshop*, *Tank Farm*, *Wellhead*, *Drilling Area*, *Warehouse*, *Pipe Rack*, *Main Gate*).

Key highlights:
- **Zero Coordinate Fabrication**: Real geographic GPS coordinates are not invented. Instead, an architectural schematic site layout maps internal facility zones.
- **Continuous Observation Density**: Heat intensity is derived directly from incident observation frequency and labeled **`INCIDENT OBSERVATION DENSITY`** (never *"danger probability"*).
- **Interactive Click Drill-Down**: Selecting any facility zone on the map or ranking table immediately populates an interactive drill-down drawer with top activities, top barrier signals, and recent incident observations.
- **Pattern Relationship Chain**: Renders the historical sequence:  
  $$\text{Location} \longrightarrow \text{Dominant Activity} \longrightarrow \text{Barrier-Linked Signal}$$  
  Explicitly captioned: *"Observed relationship in Admin Flow data."*
- **Complete Workspace Segregation**: Scoped exclusively to Admin Flow. The 561,378 global records and existing global intelligence pages remain completely untouched.

---

## 2. Why a Schematic Internal-Site Heatmap Instead of a Geographic GIS Map

A central architectural decision of Foresight is the strict prohibition against fabricating data. In industrial safety operations:

### 2.1 The Operational Reality of Safety Records
Incident reports, safety observations, and work permits recorded on an operating plant almost never contain survey-grade latitude and longitude coordinates. Instead, they specify **internal operational entities**:
- *"Flange leak on 2nd stage suction line at Compressor Bay 3"*
- *"Hot work without permit at Central Workshop lathe station"*
- *"Pressure relief valve chatter on Separator Unit in Process Area"*

### 2.2 The Dangers of Fabricated GIS Coordinates
Attempting to display such data on a world map (e.g., OpenStreetMap, Google Maps, or Leaflet) requires inventing artificial latitude and longitude points. In high-reliability organizations (oil & gas, chemicals, mining), doing so introduces severe operational fallacies:
1. **Misleading Precision**: Pins placed arbitrarily within a facility boundary imply that an incident occurred at an exact physical GPS coordinate when it was only recorded at a process unit level.
2. **False Spatial Clustering**: Standard GIS heatmaps apply radial Gaussian blurring around arbitrary coordinates, creating false hotspots in buffer zones, access roads, or empty ground.
3. **Loss of Process Context**: Operational risk in industrial plants is governed by process unit boundaries, hazard classifications, and barrier envelopes—not by geographic radius.

### 2.3 The Architectural Solution: Schematic Site Heatmap
Foresight's schematic site heatmap represents the operational complex as an **architectural facility grid**:
- Each zone represents a functional unit (*Workshop*, *Process Area*, *Tank Farm*, *Compressor Area*, *Pipe Rack*, *Wellhead*, etc.).
- Heat intensity represents **actual incident observation density** within that operational boundary.
- The interface provides immediate executive comprehension of which plant units experience the highest concentration of precursor signals without fabricating misleading GIS coordinates.

---

## 3. Heat Intensity Derivation & Semantic Legend

Heat intensity is calculated relative to the maximum observed incident count in the current filtered Admin Flow scope:

$$\text{Intensity} = \frac{\text{Incident Count at Location}}{\text{Maximum Incident Count Among All Locations}}$$

### Continuous Scale & Color Taxonomy
| Heat Level | Intensity Threshold | Color Code | Visual Meaning |
| :--- | :--- | :--- | :--- |
| **`Critical`** | $\ge 0.75$ | Red (`#C62828`) | Highest Observation Density |
| **`Elevated`** | $0.50 \le \text{intensity} < 0.75$ | Orange (`#E65100`) | Elevated Observation Density |
| **`Moderate`** | $0.25 \le \text{intensity} < 0.50$ | Yellow (`#F57F17`) | Moderate Observation Density |
| **`Low`** | $0.0 < \text{intensity} < 0.25$ | Green (`#2E7D32`) | Low Observation Density |
| **`Zero`** | $= 0.0$ (0 incidents) | Slate Gray (`#9E9E9E`) | No Observations in Scope |

### Semantic Legend Rule
The legend prominently and explicitly displays:
$$\mathbf{INCIDENT\ OBSERVATION\ DENSITY}$$
The methodology note clarifies:
> *"Intensity represents incident observation density within the single-site operational perimeter. Does not establish intrinsic operational risk or future incident likelihood."*

---

## 4. Visual Architecture & Component Breakdown

The page layout (`templates/admin_flow/location_pattern_analysis.html`) is structured into four core visual sections:

### 4.1 Top Location Callout Card
Positioned at the top of the workbench:
- **Header**: `HIGHEST OBSERVATION CONCENTRATION`
- **Location Name**: e.g., `Process Area / Refining Unit`
- **Key Metrics Grid**:
  - `INCIDENTS`: Total count (e.g., `42`)
  - `PSIF-LINKED`: High-consequence count (e.g., `18`)
  - `TOP ACTIVITY`: Most frequent activity in this unit (e.g., `Hot Work in Classified Area`)
  - `TOP BARRIER SIGNAL`: Most frequent barrier deficiency (e.g., `Work Authorization`)
- **Caption**: *"Highest observation concentration in the current Admin Flow dataset."* (Strictly neutral phrasing).

### 4.2 Schematic Site Heatmap (Left Column)
- **Outer Box**: `OPERATIONAL PERIMETER — MAIN SITE (Duliajan Operational Complex)`
- **3x3 Facility Zones Grid**:
  - Row 1: `Workshop / Maintenance Bay` (`Z-01`), `Process Area / Refining Unit` (`Z-02`), `Tank Farm` (`Z-03`)
  - Row 2: `Warehouse / Storage Yard` (`Z-04`), `Compressor Area` (`Z-05`), `Pipe Rack / Manifold` (`Z-06`)
  - Row 3: `Main Gate / Access Control` (`Z-07`), `Wellhead Area` (`Z-08`), `Drilling Area / Rig Floor` (`Z-09`)
- **Zone Cards**: Each zone displays its code, title, role, heat-colored top border, observation count badge, PSIF sub-badge, and percentage share.
- **Auxiliary Zones Tray**: Dynamically renders any additional observed locations (e.g., *Electrical Substation*, *Flare Area*, *Water Treatment*, or custom locations).
- **Interactive Selection**: Clicking any zone applies a visual highlight and instantly populates the detail panel.

### 4.3 Location Ranking Table (Right Column)
- **Descending Sort**: Sorted by incident observation count.
- **Columns**:
  1. `Rank`: `#1`, `#2`, `#3`...
  2. `Internal Location`: Formatted name with heat color dot.
  3. `Incidents`: Total count with explicit share denominator: `share% (count/total_filtered_incidents)`.
  4. `PSIF`: Precursor count with PSIF linkage rate.
  5. `Top Activity`: Dominant job task in this area.
  6. `Top Barrier Signal`: Dominant control deficiency.
- **Interactive Row Selection**: Clicking a row highlights the location on the schematic map and synchronizes the drill-down panel.

### 4.4 Interactive Click Drill-Down Detail Panel
Appears beneath the grid/table:
- **Location Title & Breadcrumb**: Operational unit context and density status badge.
- **Pattern Relationship Chain**:
  $$\text{Location} \longrightarrow \text{Top Activity} \longrightarrow \text{Barrier-Linked Signal}$$
  $$\text{Process Area} \longrightarrow \text{Hot Work in Classified Area} \longrightarrow \text{Gas Testing / Atmospheric Monitoring}$$
  *Caption: "Observed relationship in Admin Flow data."*
- **Observed Activities Breakdown**: Frequency-ordered list of job tasks at this location.
- **Recent Observations Sample**: Chronological list of recent incident cards with narrative excerpts, dates, and PSIF tags.

---

## 5. Responsive Layout Specifications

- **Desktop ($\ge 1080\text{px}$)**:
  - Schematic Heatmap and Location Ranking Table display side-by-side in a `1.15fr : 0.85fr` grid.
  - Drill-down detail panel spans full width below.
- **Tablet ($681\text{px} - 1079\text{px}$)**:
  - Stacked layout: Schematic Heatmap on top, Location Ranking Table directly below.
- **Mobile ($\le 680\text{px}$)**:
  - Schematic Heatmap on top, facility zones adapt to a single column.
  - All text labels have explicit minimum heights and flexible word wrapping to guarantee zero overlapping.

---

## 6. Empty State Handling

When no location observations exist in Admin Flow:
- Displays clean empty card:
  > *"No location patterns available yet."*
- Direct workflow action buttons:
  - `[Upload Dataset]` $\rightarrow$ `/admin-flow/upload/`
  - `[Submit Report]` $\rightarrow$ `/admin-flow/submit/`
- Zero is never presented as an operational failure.

---

## 7. Verification & Regression Coverage

The Task 6 test suite (`tests/test_task6_admin_flow_location_patterns.py`) provides 100% automated test coverage across all specifications:

| Test Case | Objective | Result |
| :--- | :--- | :--- |
| `test_empty_state_zero_records` | Verifies *"No location patterns available yet."* and action buttons. | **PASSED** |
| `test_same_site_assumption_and_single_location` | Confirms Duliajan single-site context, callout headers, 100% share, and legend. | **PASSED** |
| `test_multiple_locations_ranked_descending` | Recreates 42/30/18/10 prompt distribution; verifies descending sort order and explicit denominators. | **PASSED** |
| `test_heat_intensity_derivation_and_scale` | Validates relative heat intensity ($1.0$ down to $0.1$) and continuous color scale (`critical`, `elevated`, `moderate`, `low`). | **PASSED** |
| `test_pattern_relationship_chain_view` | Asserts Location $\rightarrow$ Activity $\rightarrow$ Barrier relationship chain and neutral wording. | **PASSED** |
| `test_unknown_location_handling` | Graceful normalization of missing location to `UNKNOWN LOCATION` without crash. | **PASSED** |
| `test_schematic_site_grid_and_no_fabricated_coordinates` | Validates 9 canonical grid zones (`Z-01` to `Z-09`) and asserts absence of GPS coordinates. | **PASSED** |
| `test_filtering_psif_and_query` | Tests dynamic filtering by PSIF status and text query with denominator updates. | **PASSED** |
| `test_workspace_isolation_hard_segregation` | Confirms global incidents (`workspace_id IS NULL`) are completely excluded. | **PASSED** |
| `test_role_based_access_control` | Verifies RBAC: admin flow allowed (200), standard forbidden (403), anonymous redirected (302). | **PASSED** |
| `test_location_patterns_api` | Verifies REST API `GET /admin-flow/api/patterns/location/` JSON payload structure. | **PASSED** |

---

## 8. Summary of Created and Modified Files

1. **`apps/admin_flow/pattern_engine.py`**:
   - Added `Main Gate / Access Control` to canonical locations and aliases.
   - Enhanced `PatternObservation` dataclass with `description` and `job_task`.
   - Upgraded `compute_location_patterns()` to calculate top activities, top barrier signals, pattern chains, continuous heat scale, and recent observations.
   - Implemented `get_admin_flow_location_pattern_view_data()` with 3x3 schematic grid generation and auxiliary zone mapping.
2. **`apps/admin_flow/views.py`**:
   - Added `AdminFlowLocationPatternAnalysisView` (`/admin-flow/patterns/location/`).
   - Updated `AdminFlowLocationPatternsAPI` (`/admin-flow/api/patterns/location/`) to return full location view data with filter support.
3. **`apps/admin_flow/urls.py`**:
   - Registered `patterns/location/` web view route.
4. **`templates/admin_flow/location_pattern_analysis.html`**:
   - Complete responsive HTML template with scope banner, methodology notice, 3-dimension tabs, top callout, schematic site heatmap, location ranking table, click drill-down detail panel, and empty state.
5. **`templates/admin_flow/pattern_analysis.html` & `templates/admin_flow/barrier_pattern_analysis.html`**:
   - Updated dimension navigation tabs to cross-link to `{% url 'admin_flow:patterns_location' %}`.
6. **`tests/test_task6_admin_flow_location_patterns.py`**:
   - 11 comprehensive automated tests.
7. **`docs/TASK_6_LOCATION_PATTERN.md`**:
   - Complete technical and architectural documentation.
