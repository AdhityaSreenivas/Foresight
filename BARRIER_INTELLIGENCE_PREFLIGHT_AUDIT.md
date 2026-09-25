# Barrier & Critical-Control Intelligence: Preflight Repository & Database Audit

**Document Status**: COMPLETE & AUTHORITATIVE  
**Date**: September 9, 2026  
**Audited Target**: Foresight PSIF Platform (`/Users/sas/Developer/prototype_165`)  
**Audit Purpose**: Enforce strict methodological defensibility prior to implementing Barrier & Critical-Control Intelligence UI.

---

## 1. Existing Deterministic Control & Barrier Rules

A comprehensive code and database audit was performed across all apps, services, models, and ML pipelines. The findings regarding control and barrier rules are detailed below:

### A. IOGP Life-Saving Rules Classifier
* **File**: [`apps/predictions/iogp_classifier.py`](file:///Users/sas/Developer/prototype_165/apps/predictions/iogp_classifier.py)
* **Function**: `classify_iogp_rules(fields_dict)`
* **Taxonomy**: 9 canonical IOGP Life-Saving Rules:
  1. *Bypassing Safety Controls*
  2. *Confined Space*
  3. *Driving*
  4. *Energy Isolation*
  5. *Hot Work*
  6. *Line of Fire*
  7. *Safe Mechanical Lifting*
  8. *Work Authorization*
  9. *Working at Height*
* **Mechanism**: Compiled regular expressions against incident text fields (`description`, `corrective_actions`, `job_task`, etc.).
* **Semantic Filters (`_check_match_context`)**:
  - Preceding and following negation detection (`PRECEDING_NEGATION_RE`, `FOLLOWING_NEGATION_RE`, `PRECEDING_WITHOUT_ACTIVITY_RE`).
  - Context differentiation: categorizes matches into `direct_event` (strength 1.0), `corrective_action` (strength 0.5), or `incidental` (strength 0.3).
  - Oil & Gas domain rule: `"cold cutting"` explicitly negates *Hot Work*.
* **Critical Limitation for Barrier Intelligence**:
  - The classifier detects **hazard/activity involvement**, NOT whether the control was effective vs. compromised.
  - For example, `"Isolation was verified before maintenance"` triggers a match for *Energy Isolation* because the activity involves energy isolation. It does not measure whether the barrier held or failed.

### B. Incident Structured Control Fields
* **File**: [`apps/incidents/models.py`](file:///Users/sas/Developer/prototype_165/apps/incidents/models.py#L235-L260)
* **Model**: `Incident`
* **Fields**:
  - `control_condition`: Enum (`effective`, `failed`, `absent`, `bypassed`, `unknown`)
  - `control_failed_bypassed`: Nullable Boolean (`True` if failed/bypassed, `False` if effective/absent, `None` if unknown)
  - `control_type`: Enum (`loto_isolation`, `machine_guarding`, `physical_barrier`, `fall_protection`, `permit_isolation`, `ventilation_monitoring`, etc.)
  - `direct_control_present`: Enum (`yes`, `no`, `unknown`)
* **Database State Audit (561,351 Records)**:
  - `control_condition`: **100% (561,351 records) are `"unknown"`**
  - `control_failed_bypassed`: **100% (561,351 records) are `None`**
  - `control_type`: **100% (561,351 records) are `"unknown"`**
  - `direct_control_present`: **100% (561,351 records) are `"unknown"`**
* **Conclusion**: The ingested production dataset does not contain populated structured control fields.

### C. Rubric Simulation & Explanation Patterns
* **Evaluation Rubric** ([`apps/incidents/services/evaluation.py`](file:///Users/sas/Developer/prototype_165/apps/incidents/services/evaluation.py)): Contains `compromised_control_phrases` and `effective_control_phrases`, but is **only** invoked for synthetic dual reviews on the 181-record validation cohort (`IncidentReview`).
* **Explanation Engine** ([`ml_engine/explanation_engine.py`](file:///Users/sas/Developer/prototype_165/ml_engine/explanation_engine.py)): Defines regexes `CONTROL_FAILURE_PATTERNS` and `CONTROL_EFFECTIVE_PATTERNS` for on-the-fly single-record decision explanations. It is **not** persisted as a batch aggregation across the database.

---

## 2. Classification of Candidate Barrier Metrics

| Candidate Metric | Current Implementation | Exact Source | Computable Now? | Classification |
|---|---|---|---|---|
| **Matched Observations** | `IOGPRuleTag.objects.filter(rule=barrier).values('incident').distinct().count()` | `IOGPRuleTag` table via `classify_iogp_rules()` | **YES** | **A. Directly Computable Today** |
| **PSIF-Linked Observations** | `IOGPRuleTag.objects.filter(rule=barrier, incident__prediction__psif_predicted=True, incident__prediction__is_sparse_input=False).values('incident').distinct().count()` | Join: `IOGPRuleTag` ⨝ `PredictionResult` (canonical non-sparse PSIF candidates) | **YES** | **A. Directly Computable Today** |
| **Concern-Pattern Matches** | None exists in database or batch tables. Structured fields are 100% `unknown`. | N/A (requires developing a new batch narrative rule engine and backfilling) | **NO** | **B. Computable Only After New Rule Work** |
| **Affected Sites** | `Incident.objects.filter(iogp_rules__rule=barrier).exclude(location__in=[None, '']).values('location').distinct().count()` | `Incident.location` linked to `IOGPRuleTag` | **YES** | **A. Directly Computable Today** |

> [!IMPORTANT]
> Because **Concern-Pattern Matches** has no existing deterministic batch rule or populated database field, it is classified as **NOT CURRENTLY COMPUTABLE** and **MUST BE OMITTED** from the V1 UI.

---

## 3. Definition of "Matched Observations"

An observation becomes associated with a barrier/control exclusively through the deterministic IOGP rule engine:
- **Exact Engine**: `apps.predictions.iogp_classifier.classify_iogp_rules`
- **Database Table**: `apps_incidents_iogpruletag` (`IOGPRuleTag`)
- **Storage**: Each incident contains 0, 1, or multiple rule tags based on keyword and phrase matching in the incident's narrative and contextual fields.
- **Mandatory Disclosure**:
  > *Barrier association is derived from deterministic rule/keyword matching across incident narratives and is not a calibrated barrier-health measurement.*

---

## 4. Audit of "Concern-Pattern Matches"

* **Current Status**: **NOT CURRENTLY COMPUTABLE**.
* **Reasoning**:
  1. The database structured fields `control_condition` and `control_failed_bypassed` are 100% unpopulated (`unknown` / `None`).
  2. `IOGPRuleTag` records store rule names, but do not record whether the control was observed failing or held.
  3. A naive keyword search for words like `"failed"`, `"isolation"`, or `"bypass"` in isolation produces high false-positive rates (e.g., `"Isolation was verified and held before work commenced"` would falsely trigger if not strictly parsed for failure context).
  4. While `ml_engine/explanation_engine.py` has failure regexes, it is an on-the-fly explanation tool, not an audited or benchmarked batch classifier.
* **Resolution**: Per instruction, this metric is **excluded from V1**.

---

## 5. Authoritative PSIF Metric Definition & Denominators

Audit of Dashboard & Reports analytics services ([`apps/dashboard/services.py`](file:///Users/sas/Developer/prototype_165/apps/dashboard/services.py)):

* **Total Ingested Incidents**: `561,351` (`Incident.objects.count()`)
* **Prediction Eligible**: `558,087` (`PredictionResult.objects.filter(is_sparse_input=False).count()`)
* **Insufficient Evidence (Sparse)**: `2,514` (`PredictionResult.objects.filter(is_sparse_input=True).count()`)
  - Defined as narrative text `< 10` words or lacking factual context.
  - Excluded from prediction denominators to prevent uninformative baseline distortions.
* **PSIF Candidates (Model Positive)**: `345,329` (`PredictionResult.objects.filter(is_sparse_input=False, psif_predicted=True).count()`)
* **NOT PSIF (Model Negative)**: `212,758` (`PredictionResult.objects.filter(is_sparse_input=False, psif_predicted=False).count()`)
* **Canonical PSIF Rate**:
  $$\text{PSIF Prediction Rate} = \frac{\text{PSIF Candidates (345,329)}}{\text{Prediction Eligible (558,087)}} = 61.88\% \approx 61.9\%$$

---

## 6. Audit of Model Versions & Rate Discrepancies

Database audit of all `ModelVersion` records:

| Version Label | Is Active? | Selected Threshold | Total Predictions | Positive Predictions | Positive Rate |
|---|---|---|---|---|---|
| `v_20260906_202052` | **True (Active)** | **0.20** (F2-optimal) | 400,081 | 248,949 | 62.22% |
| `v_20260906_093529` | False | 0.50 (Balanced) | 110,500 | 49,297 | 44.61% |
| `v_20260902_122321` | False | 0.10 (High Recall) | 50,020 | 49,524 | 99.01% |
| `v_20260901_072752` | False | 0.10 | 0 | 0 | 0.0% |

### Historical Rate Discrepancy Reconciliation
1. **The ~18.8% Legacy Rate**: Occurred in earlier prototypes when 174 predicted PSIFs were divided by 926 total ingested incidents without cohort alignment.
2. **The ~92.4% Forensic Rate**: Occurred when evaluating an early high-recall model (`v_20260902_122321`, threshold 0.10) solely across scored records.
3. **Current Authoritative Rate (~61.9%)**: Derived from the active pipeline and persisted inference results across non-sparse prediction records.

---

## 7. Authoritative PSIF-Linked Barrier Metric Query

For Barrier & Critical-Control Intelligence, **PSIF-Linked Observations** is strictly defined as:

$$\text{PSIF-Linked Count} = \text{Count of distinct incidents associated with barrier } B \text{ where } \text{is\_sparse\_input}=\text{False} \text{ and } \text{psif\_predicted}=\text{True}$$

### Precise ORM Query:
```python
from apps.incidents.models import IOGPRuleTag
from django.db.models import Count, Q

barrier_stats = IOGPRuleTag.objects.values("rule").annotate(
    matched_observations=Count("incident", distinct=True),
    psif_linked_observations=Count(
        "incident",
        filter=Q(incident__prediction__psif_predicted=True, incident__prediction__is_sparse_input=False),
        distinct=True
    ),
    affected_sites=Count(
        "incident__location",
        filter=~Q(incident__location__in=[None, ""]),
        distinct=True
    )
).order_by("-matched_observations")
```

---

## 8. Current Computed Baseline per Barrier

Actual verified database values across all 561,351 records:

| IOGP Life-Saving Rule (Barrier) | Matched Observations | PSIF-Linked Observations | PSIF Linkage Rate | Affected Sites |
|---|---|---|---|---|
| **Safe Mechanical Lifting** | 132,947 | 85,482 | 64.3% | 170 |
| **Energy Isolation** | 111,803 | 68,922 | 61.6% | 179 |
| **Driving** | 88,054 | 59,847 | 68.0% | 132 |
| **Hot Work** | 72,072 | 48,982 | 68.0% | 129 |
| **Working at Height** | 68,778 | 45,028 | 65.5% | 128 |
| **Confined Space** | 45,515 | 26,429 | 58.1% | 117 |
| **Line of Fire** | 45,342 | 29,680 | 65.5% | 134 |
| **Work Authorization** | 31,666 | 24,743 | 78.1% | 173 |
| **Bypassing Safety Controls** | 30,052 | 25,354 | 84.4% | 161 |

---

## 9. Final V1 Barrier Intelligence Metric Selection

Per the decision framework in Section 10 of the prompt:

### **Selected: Case B (Three Truthful, Directly Computable Metrics)**
1. **Matched Observations**: Total observations linked to this barrier by deterministic IOGP rule matching.
2. **PSIF-Linked Observations**: Number (and percentage) of matched observations classified as PSIF candidates by the authoritative predictive model.
3. **Affected Sites**: Number of distinct operational locations reporting observations matching this barrier.

*Excluded Metric*: **Concern-Pattern Matches** (OMITTED — no calibrated batch failure rule exists).

---

## 10. Mandatory Methodology Disclosures

Every Barrier Intelligence screen and card component must prominently display:
> **Methodology Notice**:  
> *Barrier associations are derived from deterministic IOGP Life-Saving Rules keyword and phrase matching across incident narratives. PSIF linkages reflect authoritative model predictions on non-sparse reports. These metrics indicate operational observation frequency and risk correlation, not calibrated physical barrier integrity.*

---

## 11. Cache & Scope Consistency

- **Cache Key**: `dashboard:barrier_intelligence:v1`
- **Cache TTL**: 3600 seconds (1 hour), synchronized with `dashboard:analytics_summary:v3`.
- **Cache Invalidation**: Invalidated whenever `invalidate_analytics_cache()` is called.
