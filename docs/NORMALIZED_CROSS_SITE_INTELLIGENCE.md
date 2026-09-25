# Normalized Cross-Site Safety Intelligence Specification

> **Prototype Demonstration Architecture**  
> *Demonstration prototype architecture requiring validation on human-reviewed real-world OIL data before operational deployment.*  
> *Never characterized as production-ready, OIL-validated, or calibrated probability estimation.*

---

## 1. Executive Summary & Objective

Cross-facility safety pattern analysis in upstream and downstream oil & gas environments is frequently undermined by divergent site nomenclature, inconsistent activity descriptions, and fragmented hazard terminology.

The **Normalized Cross-Site Intelligence Layer** provides an automated, defensible architecture that transforms heterogeneous historical incident reports into verified canonical concepts:

$$\text{Raw Source Data} \longrightarrow \text{Normalized Entities} \longrightarrow \text{Canonical Concepts} \longrightarrow \text{Cross-Site Comparison} \longrightarrow \text{Recurrence Overlap}$$

### Core Analytical Invariants
1. **Deterministic Normalization**: Source text is matched against verified domain taxonomies and explicit alias lookup tables. No probabilistic or hallucinatory AI entity fabrication is permitted.
2. **Traceability & No Synthetic Confidence**: Every normalized entity preserves its `raw_value`, `canonical_value`, `normalization_method`, `source_field`, `normalization_version`, and standardized status (`EXACT`, `ALIAS`, `NORMALIZED`, `UNKNOWN`, `UNCERTAIN`). Probabilistic "confidence percentages" are strictly prohibited unless computed by calibrated mathematical models.
3. **Unknown Preservation**: Records lacking site or facility provenance remain `UNKNOWN`. Missing attributes are never guessed or silently merged into nearby operating units.
4. **Explicit Denominators**: Every rate, proportion, and ratio declares both its numerator and its exact operational denominator (e.g. $n = \text{prediction-eligible observations with composite narrative}$).
5. **Neutral Analytical Wording**: Facility reporting volumes reflect organizational scale, workforce density, and reporting culture rather than inherent safety risk. Wording strictly employs neutral phrases such as *"Observed safety-signal volume"* and *"PSIF-linked observation count"*, explicitly avoiding pejorative characterizations (*"Site X is unsafe"*).
6. **IOGP Life-Saving Rule Disclaimer**: Matches are designated **RULE-DERIVED CANDIDATES** derived from deterministic keyword patterns; they do not by themselves establish a confirmed barrier failure, regulatory violation, or PSIF incident.
7. **Non-Causal Recurrence**: Pattern overlap identifies historical observations across facilities using the standardized disclosure: *"Similar observations have been recorded across multiple sites."* The system explicitly disclaims future incident prediction or common root-cause proof.

---

## 2. Canonical Entity Taxonomies & Normalization Rules

### 2.1 Operational Sites Taxonomy (`CANONICAL_OPERATIONAL_SITES`)
Foresight registers 15 canonical operational field installations and major pipelines representing Oil India Limited (OIL) operational regions:

| Canonical Operational Site | Common Aliases & Normalization Mappings |
| :--- | :--- |
| **`DULIAJAN`** | `duliajan`, `Duliajan Site`, `duliajan-site`, `site duliajan`, `ctf duliajan`, `central tank farm duliajan`, `field hq duliajan` |
| **`NUMALIGARH`** | `numaligarh`, `numaligarh refinery`, `numaligarh site`, `numaligarh refinery tank farm` |
| **`MORAN`** | `moran`, `moran site`, `moran-site`, `ggs moran`, `group gathering station moran` |
| **`NAHARKATIYA`** | `naharkatiya`, `naharkatiya site`, `nhk` |
| **`KUMCHAI`** | `kumchai`, `kumchai field`, `kumchai site` |
| **`BAGHJAN`** | `baghjan`, `baghjan site`, `eps baghjan`, `early production system baghjan` |
| **`TENGAKHAT`** | `tengakhat`, `tengakhat site` |
| **`MAKUM`** | `makum`, `makum field`, `makum ggs` |
| **`SILCHAR`** | `silchar`, `silchar exploration`, `cachar project` |
| **`DIGBOI`** | `digboi`, `digboi refinery`, `digboi oilfield` |
| **`GUWAHATI`** | `guwahati`, `guwahati pumping station`, `ps guwahati` |
| **`JORAJAN`** | `jorajan`, `jorajan oilfield` |
| **`UPPER ASSAM FIELD`** | `upper assam`, `upper assam fields` |
| **`DULIAJAN-DIGBOI PIPELINE`** | `duliajan digboi pipeline`, `digboi pipeline` |
| **`DULIAJAN-BARAUNI PIPELINE`** | `duliajan barauni pipeline`, `barauni pipeline`, `crude oil pipeline` |

#### Adversarial Rule: Distinct Facilities Must Not Collapse
- **Principle**: Facilities sharing geographic proximity or name fragments but serving distinct functions (e.g. workshops vs general fields, specific drilling rigs) must **never** be merged.
- **Verification**: `"Duliajan Workshop"` retains `status="UNCERTAIN"` and does **not** map to canonical `DULIAJAN`. `"Drilling Rig 9"` and `"Drilling Rig 14"` remain strictly distinct.
- **Missing Data**: Inputs such as `""`, `None`, `"unknown"`, `"n/a"`, `"unspecified"`, or `"generic area"` deterministically evaluate to canonical `"UNKNOWN"`.

---

### 2.2 Activity Normalization Taxonomy (`CANONICAL_ACTIVITIES`)
Normalizes operational tasks and work authorizations while maintaining crucial functional distinctions:

| Canonical Activity | Scope & Raw Mappings | Boundary Distinctions |
| :--- | :--- | :--- |
| **`Safe Mechanical Lifting`** | `lifting operation`, `material lifting`, `lifting materials`, `safe mechanical lifting` | Distinguished from manual material handling and generic rigging |
| **`Vehicle Operation / Road Transport`** | `driving`, `road haulage`, `vehicle transport` | **Strictly separated** from fleet maintenance & mechanical repair |
| **`Vehicle Maintenance / Servicing`** | `vehicle maintenance`, `fleet maintenance`, `truck servicing` | **Strictly separated** from operating/driving |
| **`Permit to Work / Work Authorization`** | `permit to work`, `work permit`, `ptw`, `work authorization` | Administrative barrier control, distinct from physical maintenance |
| **`Internal Pressure Vessel Cleaning`** | `internal cleaning of a pressure vessel`, `vessel descaling`, `tank cleaning` | Confined space physical intervention |
| **`Hot Work in Classified Area`** | `hot work`, `welding`, `cutting and welding`, `torch cutting` | Classified hydrocarbon zone ignition hazard |
| **`Energy Isolation / LOTO`** | `loto`, `lockout tagout`, `isolation and de energization` | Primary zero-energy barrier application |
| **`Wellhead Pressure Control Intervention`** | `wellhead pressure control intervention`, `bop testing` | Well control barriers |
| **`Pipeline Tie-In / Hot Tap`** | `pipeline tie in`, `hot tap operation` | Live hydrocarbon line intervention |

---

### 2.3 Hazard Normalization Taxonomy (`CANONICAL_HAZARDS`)
Categorizes hazards into **15 canonical high-energy hazard families** grounded in the Energy Wheel and IOGP Life-Saving Rules:

1. **`Working at Height`** (`Gravity`)
2. **`Suspended Loads / Mechanical Lifting`**
3. **`Line of Fire`**
4. **`Pressure / Stored Energy Release`** (`Pressure`, `high pressure release`)
5. **`Electrical Energy / Arc Flash`** (`Electrical`)
6. **`Vehicle & Mobile Equipment`** (`Kinetic (vehicle)`, `Kinetic (moving object/vehicle)`)
7. **`Rotating Equipment / Mechanical In-Running Nips`** (`Mechanical`, `Mechanical (rotating equipment)`)
8. **`Hot Work & Ignition Sources`**
9. **`Confined Space / Engulfment`** (`Atmospheric (oxygen deficiency)`)
10. **`Hydrocarbon & Flammable Chemical Release`** (`Hydrocarbon`, `Hydrocarbon (flammable atmosphere)`)
11. **`Toxic & Asphyxiant Atmosphere`** (`Chemical (toxic/H2S)`)
12. **`Thermal Energy (Extreme Heat / Cryogenic)`** (`Thermal`)
13. **`Stored Mechanical Energy (Springs / Tension)`**
14. **`Excavation & Ground Collapse`**
15. **`Dropped Objects (Dynamic Gravity Impact)`** (`Gravity (dropped object)`)

#### Preservation of Equipment vs Hazard Release
- An equipment mention (e.g. `"pressure vessel"`) represents an asset class (`Chemical Pump / Pressure Vessel`).
- It is **not** conflated with an uncontrolled energy discharge (`"Pressure / Stored Energy Release"`).

---

### 2.4 IOGP Life-Saving Rules (`CANONICAL_IOGP_RULES`)
The 9 official canonical rules:
1. **Bypassing Safety Controls**
2. **Confined Space**
3. **Driving**
4. **Energy Isolation**
5. **Hot Work**
6. **Line of Fire**
7. **Safe Mechanical Lifting**
8. **Work Authorization**
9. **Working at Height**

*Status Disclaimer*: Every IOGP rule occurrence across the platform is explicitly labeled **"RULE-DERIVED CANDIDATE (keyword rule matches, not confirmed violations)"**.

---

## 3. Normalization Traceability Contract

Every entity normalized by the platform emits a structured metadata payload:

```json
{
  "raw_value": "Duliajan Site",
  "canonical_value": "DULIAJAN",
  "normalized_value": "DULIAJAN",
  "entity_type": "operational_site",
  "method": "exact_alias",
  "normalization_method": "exact_alias",
  "status": "mapped",
  "status_code": "ALIAS",
  "is_exact": false,
  "is_alias": true,
  "is_normalized": true,
  "confidence": 1.0,
  "source_field": "raw_row.region_field",
  "version": "deterministic_taxonomy_v1",
  "normalization_version": "deterministic_taxonomy_v1"
}
```

### Standardized Status Codes:
- **`EXACT`**: Input precisely matched canonical term (case/whitespace sanitized).
- **`ALIAS`**: Input verified in deterministic domain alias table.
- **`NORMALIZED`**: Syntax or structural formatting normalized.
- **`UNKNOWN`**: Missing, null, empty, or generic non-specific input.
- **`UNCERTAIN`**: Preserved as identity string; below similarity threshold or ambiguous.

---

## 4. Cross-Site Analytics Engine Architecture

The analytics engine (`apps/dashboard/cross_site_service.py`) operates through high-performance batch ingestion and in-memory indexing:

```
PostgreSQL Database (560,574 rows)
       │
       ├── Filter: raw_row__has_key='region_field' (10,500 real OIL incidents) [0.55s]
       └── Filter: IOGPRuleTag.objects.filter(incident_id__in=...) (13,512 tags) [0.08s]
       │
       ▼
In-Memory Real Incident Bundle Cache (_get_real_incident_bundle)
       ├── In-memory grouping & indexing [0.024s]
       └── Redis / Django Cache layer (1-hour TTL, force_refresh support)
       │
       ├── get_cross_site_overview()            [< 0.05s]
       ├── get_site_comparison_table()          [< 0.05s]
       ├── get_site_detail(site_id)             [< 0.02s]
       ├── get_site_iogp_matrix()               [< 0.01s]
       ├── get_site_hazard_matrix()             [< 0.01s]
       ├── get_normalized_activities_cross_site()[< 0.01s]
       ├── get_normalized_hazards_cross_site()   [< 0.01s]
       ├── get_normalized_iogp_cross_site()     [< 0.01s]
       ├── compare_sites(site_ids)              [< 0.02s]
       └── get_cross_site_recurrence_signals()  [< 0.01s]
```

### Performance Optimization Result
By replacing per-row unindexed JSONB joins across 560,574 records with two indexed primary-key queries followed by Python dictionary indexing, total analytics runtime dropped from **>22 seconds to 1.05 seconds** on cold start, and **<2 milliseconds** on cached requests.

---

## 5. REST API Specifications

Base URL: `/api/cross-site/` (Authenticated via Session or Token Authentication)

### 5.1 Endpoints Summary

| Endpoint | Method | Query Parameters | Description |
| :--- | :--- | :--- | :--- |
| `/api/cross-site/overview/` | GET | `refresh=true` | System-wide cross-site safety KPIs & denominators |
| `/api/cross-site/sites/` | GET | `refresh=true` | Comparative metrics table for all 15 operational sites |
| `/api/cross-site/sites/<site_id>/` | GET | `refresh=true` | In-depth operational safety trace for a single site |
| `/api/cross-site/activities/` | GET | `refresh=true` | Normalized activity aggregates across sites |
| `/api/cross-site/hazards/` | GET | `refresh=true` | 15 canonical hazard family distributions across sites |
| `/api/cross-site/iogp/` | GET | `refresh=true` | 9 canonical IOGP Life-Saving Rules with candidate disclosures |
| `/api/cross-site/compare/` | GET | `sites=DULIAJAN,NUMALIGARH` | Head-to-head multi-site comparison profile |
| `/api/cross-site/recurrence/` | GET | `window_days=180`, `min_sites=2` | Historical recurrence patterns across $\ge 2$ sites |

### 5.2 Mandatory Response Metadata
Every API endpoint returns an explicit metadata payload:

```json
{
  "normalization_version": "deterministic_taxonomy_v1",
  "data_scope": "Historical incident records across operational sites and facilities",
  "generated_at": "2026-09-10T21:40:00.000000+05:30",
  "methodology_notice": "Cross-site analysis uses deterministic normalization of source fields and historical record aggregation. Similarity or recurrence does not establish causality, future risk, or identical underlying causes. IOGP labels are rule-derived candidates based on deterministic matching and do not by themselves establish a confirmed control violation.",
  "limitations": [
    "Demonstration prototype architecture requiring validation on human-reviewed real-world OIL data before operational deployment.",
    "Observed reporting frequency differences reflect facility scale, workforce size, and reporting culture, not inherent hazard level.",
    "IOGP Life-Saving Rules are rule-matched candidates derived from text patterns, not verified regulatory violations.",
    "Records without operational site provenance are retained as UNKNOWN to prevent erroneous cross-site attribution.",
    "Cross-site recurrence identifies historical pattern overlap; it does not predict future incidents or prove common root causes."
  ],
  "denominators": {
    "psif_rate": "Prediction-eligible observations with composite narrative (n = eligible observations)",
    "site_volumes": "Total recorded observations mapped to canonical operational facility"
  }
}
```

---

## 6. UI Implementation & Methodology Disclosures

The Cross-Site Safety Intelligence page (`/dashboard/cross-site/`) provides a unified, glassmorphism-accented workspace adhering to Foresight's industrial design system:

1. **Hero Banner & Disclaimers**: Prominently highlights the Prototype Architecture and Methodology Disclosure notices.
2. **KPI Summary Bar**: Displays system volume, active sites, prediction-eligible denominator, PSIF candidate count, active IOGP rules, and multi-site recurrence signals.
3. **Tab 1 — Site Comparison Table**:
   - Lists all 15 operational sites + UNKNOWN bucket.
   - Neutral volume labels (*"Observed safety-signal volume"*).
   - Rate calculations with explicit inline denominators (`n = eligible observations`).
   - Normalization status badges (`EXACT`, `ALIAS`, `NORMALIZED`, `UNKNOWN`).
   - Interactive AJAX "Inspect" button launching deep site operational modal.
   - Interactive Head-to-Head Site Compare selector.
4. **Tab 2 — Site × IOGP Matrix**:
   - 2D cross-tabulation of facilities against 9 canonical rules.
   - Heatmap cell shading.
   - Explicit disclaimer: *"RULE-DERIVED CANDIDATE (keyword rule matches, not confirmed violations)"*.
5. **Tab 3 — Site × Hazard Matrix**:
   - 2D cross-tabulation of facilities against 15 canonical hazard families.
6. **Tab 4 — Normalized Signals**:
   - Activities table distinguishing driving vs servicing vs lifting vs permits.
   - Hazard families table mapping high-energy releases.
7. **Tab 5 — Cross-Site Recurrence Patterns**:
   - Recurrence cards displaying rules matched across $\ge 2$ distinct sites.
   - Guidance statement: *"Similar observations have been recorded across multiple sites."*
   - Explicit non-causal disclaimer.

---

## 7. Verification Evidence & Test Coverage

The cross-site intelligence layer is validated by 40 dedicated unit and integration tests (`tests/test_cross_site_intelligence.py`), along with 34 normalization regression tests (`tests/test_normalization_and_evidence.py`):

- **Site Normalization**: Validated exact, alias, and casing normalizations.
- **Adversarial Integrity**: Confirmed `"Duliajan Workshop"` does **not** merge into `"DULIAJAN"`, and `"Drilling Rig 9"` does not merge into `"Drilling Rig 14"`.
- **Unknown Handling**: Validated missing or generic sites map to canonical `"UNKNOWN"`.
- **Activity Distinction**: Validated driving vs vehicle maintenance vs permit vs hot work.
- **Hazard Distinctions**: Validated equipment vs energy release.
- **IOGP Candidate Badging**: Validated rule candidate labels.
- **REST APIs**: Validated all 8 endpoints for authentication, schema, denominators, and 404 behavior.
- **Performance**: Validated full pipeline execution in $\le 1.05\text{s}$ on cold start and $< 0.05\text{s}$ on cached queries.

All 74 normalization and cross-site tests pass with 0 regressions.
