# PSIF Platform — Shared Intelligence Foundation Contract

**Document Version:** 1.0  
**Status:** Frozen & Hardened  
**Date:** 2026-09-10  
**Scope:** Authoritative Contract for Safety Entity Normalization, Analytical Methodology Disclosures, Evidence Representation, Provenance Tracking, Runtime Versioning, Data Quality Gating, and IOGP Separation.

---

## 1. Safety Entity Normalization Contract

### 1.1 Architecture & Pipeline
Every safety entity processed by analytical pipelines conforms strictly to the canonical flow:
```
Raw Value
  → Normalized / Canonical Value
  → Normalization Method
  → Alias (where matched)
  → Status
  → Provenance
```

**Traceability Guarantee:** Raw values are **NEVER overwritten or discarded**. They remain perpetually accessible on `.raw_value` and in the incident database records.

### 1.2 Canonical Controlled Vocabularies

#### Normalization Methods (`NormalizationMethod`)
| Method Code | Canonical Meaning |
| :--- | :--- |
| `exact_alias` | Raw string matched an entry in the verified domain alias dictionary table. |
| `normalized` | Raw string matches canonical entry directly after whitespace, case, and syntax sanitization. |
| `bounded_fuzzy` | Explicit similarity suggestion against canonical vocabulary with ratio $\ge 0.88$ (always non-authoritative). |
| `identity` | Raw string unmapped or ambiguous; preserved verbatim as-is to avoid false merging. |
| `unknown` | Missing, empty, or whitespace-only input value. |

*Backward Compatibility:* `EXACT_CANONICAL` and `NORMALIZED_SYNTAX` alias to `normalized`; `UNMAPPED` aliases to `unknown`.

#### Normalization Statuses (`NormalizationStatus`)
| Status Code | Canonical Meaning |
| :--- | :--- |
| `canonical` | The input is already the authoritative canonical standard term. |
| `mapped` | The input was mapped with certainty via exact canonical alias table. |
| `suggested` | High-confidence bounded fuzzy candidate; human/expert review advised. |
| `uncertain` | Ambiguous or unmatched string retained as identity without merging. |
| `unknown` | Input was null, empty string, or unpopulated. |

*Backward Compatibility:* `RESOLVED` aliases to `mapped`; `UNMAPPED` aliases to `unknown`.

### 1.3 Strict Conservative Normalization Rules
1. **Never Silent Fuzzy Merging:** Bounded fuzzy matching **NEVER** promotes an entity to `mapped` or `canonical`. Fuzzy matches always receive `status = suggested` and require explicit human review.
2. **Ambiguity Preservation:** When multiple canonical candidates score within $0.03$ of each other above the fuzzy threshold, the normalizer rejects candidate selection. It preserves the sanitized raw value as `identity`, tags `status = uncertain`, and logs candidates in `metadata["ambiguous_candidates"]`.
3. **Supported Entity Categories:**
   - `site` / `location`
   - `department`
   - `activity` / `job_task`
   - `equipment` / `asset` (with automated regex asset-tag extraction into `metadata["asset_tag"]`)
   - `energy_source`
   - `barrier` / `control_type`
   - `control_condition`
   - `iogp_rule`

---

## 2. Centralized Analytical Methodology Disclosure Contract

### 2.1 Principle of Centralized Disclosure
Every analytical, statistical, or predictive component must have one single authoritative methodology disclosure in `apps.incidents.services.methodology.METHODOLOGY_NOTICES`. Hardcoded disclaimers across templates or duplicate helper functions are prohibited.

### 2.2 Mandated Standard Disclosures
| Component Key | Badge Label | Mandated Summary String | Category |
| :--- | :--- | :--- | :--- |
| `psif_model` | PSIF Model Score | *"PSIF Model Score from the active model; score is not a calibrated probability."* | Predictive Model |
| `iogp` | Rule-Derived | *"Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure."* | Deterministic Rule |
| `similarity` | Semantic Vector | *"Semantic similarity between incident narratives; not causal evidence or duplicate identity."* | Vector Similarity |
| `recurrence` | Historical Pattern | *"Historical recurrence based on normalized entities and time-window matching; not causal/systemic prediction."* | Historical Aggregation |
| `shap` | Feature Attribution | *"SHAP values show mathematical model contribution, not causality."* | Interpretability |
| `human_review` | Human Adjudication | *"Human adjudication is shown separately from model prediction."* | Human Governance |
| `data_quality` | Data Quality | *"Data-quality rules indicate analytical suitability; they do not establish PSIF status."* | Data Governance |
| `barrier` | Barrier Intelligence | *"Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure."* | Rule-Based |
| `cross_site` | Cross-Site Intelligence | *"Cross-site findings use normalized safety entities and historical occurrence data. They indicate recurrence patterns, not causal relationships or future-risk predictions."* | Cross-Site Recurrence |

### 2.3 Forbidden Terminology
- **Confidence:** Must NEVER be used for deterministic keyword/pattern matching.
- **Probability / Likelihood:** Must NEVER be used to describe the PSIF Model Score (which is an uncalibrated ranking signal).
- **Causality / Cause:** Must NEVER be claimed for SHAP feature weights, semantic embeddings, or recurrence clusters.

---

## 3. Analytical Evidence Contract

### 3.1 Data Structure (`AnalyticalEvidence`)
```python
@dataclass
class AnalyticalEvidence:
    source: str                                # Member of EvidenceSource
    evidence_type: str                         # Member of EvidenceType
    label: str                                 # Human-readable label
    value: Any                                 # Metric, status, string, or numeric score
    strength: str = EvidenceStrength.INFO      # STRONG, MODERATE, WEAK, INFO
    supporting_text: Optional[str] = None      # Verbatim text excerpt or keyword phrase
    field_name: Optional[str] = None           # Source field in database if applicable
    caveat: Optional[str] = None               # Mandated methodology disclosure
    provenance: str = "analytical_evidence_v1" # Provenance / ruleset identifier
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 3.2 Canonical Backlink Properties
Every `AnalyticalEvidence` instance provides properties pointing back to source data:
- `.incident_field`: Database attribute or input field.
- `.narrative_span`: Specific sentence or phrase extracted from text.
- `.analytical_component`: Generating subsystem or pipeline stage.
- `.model_version`: Associated active predictive model identifier.
- `.ruleset_version`: Authoritative ruleset version for rule-derived evidence.
- `.source_document`: Originating incident report, standard, or regulatory code.

### 3.3 Deterministic Serialization
`.to_dict()` produces ordered, alphabetically sorted dictionary keys and explicitly serializes all backlink properties.

---

## 4. Provenance Contract

### 4.1 Strict Hierarchy of Origins
```
REAL_HUMAN (Expert HSE field review on genuine industrial incident)
  ↑
REAL_EXTERNAL (Unlabeled field incident from external operator/regulator)
  ↑
HUMAN_APPROVED_SYNTHETIC (Synthetic benchmark reviewed & signed off by genuine human)
  ↑
SYNTHETIC (Synthetic benchmark, unreviewed, or automated simulation)
```

### 4.2 Non-Negotiable Governance Rules
1. **Simulation Guard:** Automated reviewer simulations, heuristic rules, and LLM evaluations remain permanently tagged as `SYNTHETIC` (`is_synthetic_adjudication = True`). They are **NEVER** promoted to `HUMAN_APPROVED_SYNTHETIC` or `REAL_HUMAN`.
2. **Zero Fictitious Counts:** If `REAL_HUMAN` has zero records in the current database, the user interface and API report strictly `0`. Fictitious counts or placeholder human validations are strictly prohibited.
3. **Traceable Attribution:** Genuine human adjudications require reviewer identity (`adjudicated_by`), timestamp (`adjudicated_at`), and recorded rationale.

---

## 5. Runtime Versioning Contract

All intelligence features must dynamically inspect version identifiers from runtime objects:

| Version Dimension | Accessor Function | Canonical Active Version |
| :--- | :--- | :--- |
| `model_version` | `ModelVersion.objects.filter(is_active=True).first().version_label` | Dynamic (e.g. `v_20260906_202052`) |
| `knowledge_base_version` | `get_knowledge_base_version()` | `psif_kb_v1.0` |
| `reasoning_ruleset_version` | `get_reasoning_ruleset_version()` | `psif_ruleset_v1.0` |
| `action_library_version` | `get_action_library_version()` | `action_library_v1` |
| `data_quality_version` | `get_data_quality_version()` | `incident_quality_v1` |
| `normalization_version` | `get_normalization_version()` | `deterministic_taxonomy_v1` |

Central runtime introspection:
`apps.incidents.services.get_intelligence_foundation_versions() -> Dict[str, str]`

---

## 6. Data Quality Integration Contract

The foundation enforces a strict 3-tier Data Quality gate:
1. **CRITICAL:** Materially corrupted, empty, placeholder, or contradictory narrative.
   - Blocks automated PSIF inference.
   - `AgreementState = DATA_QUALITY_BLOCKED`.
   - Reason: `"Data quality is insufficient for analysis."`
   - **Never convert `CRITICAL` or `INSUFFICIENT_INFORMATION` to `NOT_PSIF`**.
2. **WARNING:** Minor omissions (e.g. missing optional equipment or secondary date).
   - Proceeds with explicit warning badge and DQ finding.
3. **VALID:** Meets all syntactic and domain information requirements.
   - Normal analysis proceeds.

*Human vs DQ Insufficiency:* Data-quality ingestion rejection (information corruption) is strictly separate from human domain adjudication (`HUMAN_INSUFFICIENT_INFORMATION`).

---

## 7. IOGP Life-Saving Rules Semantic Separation

The foundation enforces strict logical separation between three distinct concepts:
$$\text{IOGP\_MATCH} \neq \text{IOGP\_VIOLATION} \neq \text{PSIF}$$

1. **`IOGP_MATCH` (Contextual Rule Match):**
   - Deterministic keyword and contextual phrase classification against incident narratives.
   - Indicates relevant activity context (e.g. "Work at Height", "Hot Work").
   - **Does NOT prove that a safety rule was violated.**
   - **Does NOT prove that a physical barrier failed.**
   - **Does NOT establish PSIF status.**
2. **`IOGP_VIOLATION` (Rule Non-Conformance):**
   - Explicit human/investigative finding that mandatory procedures were bypassed or breached.
3. **`PSIF` (Potential Serious Injury or Fatality):**
   - Requires high-energy hazard presence combined with direct barrier failure/absence in the credible exposure zone (EEI SCL / IOGP 559).

---

## 8. Public API & Facade Stability

All consumer components can import from the stable facade `apps.incidents.services` or directly from the underlying modular packages:
```python
from apps.incidents.services import (
    # Normalization
    normalize_entity, normalize_site, normalize_department, normalize_activity,
    normalize_equipment, normalize_asset, normalize_energy_source,
    normalize_control_type, normalize_barrier, normalize_control_condition,
    normalize_iogp_rule, normalize_incident_entities,
    NormalizationMethod, NormalizationStatus, NormalizedEntity,
    get_normalization_version,

    # Methodology
    MethodologyKey, METHODOLOGY_NOTICES, get_methodology_notice, get_all_methodology_notices,

    # Evidence
    AnalyticalEvidence, EvidenceSource, EvidenceType, EvidenceStrength,
    evidence_from_shap, evidence_from_incident_field, evidence_from_iogp_tag,
    evidence_from_narrative_span, evidence_from_similar_incident,
    evidence_from_recurrence_pattern, evidence_from_control_status,
    evidence_from_data_quality, evidence_from_cross_site,

    # Knowledge Base & Reasoning
    KNOWLEDGE_BASE_VERSION, get_knowledge_base_version,
    REASONING_RULESET_VERSION, get_reasoning_ruleset_version,
    evaluate_incident_psif_reasoning, reconcile_prediction_and_rules,

    # Action Library
    ACTION_LIBRARY_VERSION, get_action_library_version,
    get_corrective_actions, get_action_by_id,

    # Data Quality
    DATA_QUALITY_VERSION, get_data_quality_version,
    validate_incident_for_analysis, validate_incident_quality,

    # Runtime Introspection
    get_intelligence_foundation_versions,
)
```
Existing import paths remain 100% backwards-compatible.
