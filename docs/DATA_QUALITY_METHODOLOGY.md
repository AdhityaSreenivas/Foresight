# PSIF Platform — Data Quality Methodology & Ingestion Assurance (Task 12)
**Document Version:** 1.0.0  
**Effective Date:** 2026-09-10  
**Problem Statement:** Smart India Hackathon 2024 / SIH PS 26165  
**Governing Standard:** Deterministic Safety Screening & Ingestion Assurance  

---

## 1. Overview & Objectives

The Foresight Data Quality (DQ) framework ensures that incident narratives and structured records entering the platform undergo rigorous, deterministic validation before analytical consumption. The system guarantees that:
1. Low-quality, corrupted, or contradictory records are screened at the ingestion boundary.
2. Incomplete or sparse records are recognized as **uncertainty** rather than being collapsed into ground-truth safety.
3. Every metric reported on data quality carries explicit scope, timestamps, and independent denominators.

---

## 2. Ingestion Gating Contract & Decision States

Every incident record ingested through any of the platform's six ingestion pathways is evaluated against canonical validation logic (`validate_incident_for_analysis`).

### 2.1 Screening Decisions
- **CRITICAL (Rejected):** The record fails fundamental integrity requirements (empty narrative, severe date contradiction, placeholder text, corrupted encoding). The record is rejected at the ingestion boundary and blocked from entering the analytical database.
- **WARNING (Accepted with Findings):** The record has minor omissions or brevity (e.g. narrative under 10 words, missing non-mandatory metadata). Admitted to the database with explicit warning findings. Prediction is flagged with `is_sparse_input = True` and excluded from high-confidence precursor statistics.
- **VALID (Fully Admitted):** The record satisfies all chronological, grammatical, and structured requirements with sufficient operational evidence.

---

## 3. Four Distinct Evidence States (Sparse vs. Invalid)

Under Foresight methodology, data completeness concepts are strictly separated. The platform does **not** collapse missing evidence into a negative classification:

| Evidence State | Conceptual Definition | Screening Action | Downstream Analytical Handling |
| :--- | :--- | :---: | :--- |
| **`INVALID_DATA`** | Corrupted encoding, impossible future timestamps, empty narrative, or direct field contradictions. | **REJECTED** | Discarded at ingestion boundary; audit log entry retained. |
| **`SPARSE_DATA`** | Narrative under 10 words or single operational token without contextual explanation. | **WARNING** | Flagged as `is_sparse_input = True`; excluded from portfolio precursor numerator. |
| **`VALID_LOW_EVIDENCE`** | Formally valid grammatical description lacking high-energy hazard indicators or direct control cues. | **VALID / INFO** | Processed through standard model inference with "Weak" or "Moderate" evidence strength rating. |
| **`INSUFFICIENT_INFORMATION`** | Operational reasoning state where causal precursor pathway cannot be confirmed or refuted. | **ESCALATED** | Escalated for human review and on-site evidence gathering. Never treated as "NOT PSIF". |
| **`VALID`** | Complete operational context satisfying all structural, chronological, and semantic requirements. | **ACCEPTED** | Admitted to portfolio metrics, semantic reasoning, and model assurance. |

> [!CAUTION]
> **Fundamental Safety Axiom:** Unknown $\neq$ NOT PSIF. Absence of documented evidence in an incident narrative must never be construed as positive evidence that safety barriers remained effective.

---

## 4. Audited Ingestion Pathways (All 6 Pathways)

Foresight enforces canonical validation across all entry points:

| Pathway Name | Entry Point | Ingestion Gating Enforced | Critical Gate Action | Warning Gate Action | Provenance Tracking |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **CSV Batch Ingestion** | `apps.datasets.ingestion.bulk_create_incidents` | `validate_incident_for_analysis` | `REJECT_ROW` | `ACCEPT_WITH_FINDINGS` | Dataset ID + Row Index |
| **JSON / JSONL Bulk Upload** | `apps.datasets.ingestion.bulk_create_incidents` | `validate_incident_for_analysis` | `REJECT_ROW` | `ACCEPT_WITH_FINDINGS` | UUID + Batch Hash |
| **Interactive Web Form** | `apps.incidents.forms.IncidentCreateForm` | `validate_incident_for_analysis` | `BLOCK_FORM_VALIDATION` | `ACCEPT_WITH_NOTICE` | Submitting User ID |
| **REST API Ingestion** | `apps.incidents.serializers.IncidentSerializer` | `validate_incident_for_analysis` | `RETURN_HTTP_400` | `ACCEPT_AND_PERSIST_DQ` | API Client Token |
| **Document / PDF Ingestion** | `apps.datasets.ingestion.ingest_document_incidents` | `validate_incident_for_analysis` | `REJECT_ROW` | `ACCEPT_WITH_FINDINGS` | Source File SHA-256 |
| **Manual Prediction API** | `apps.predictions.api_views.ManualPredictAPIView` | `validate_incident_for_analysis` | `RETURN_HTTP_400` | `PERMIT_WITH_WARNING` | Ad-hoc Request Hash |

---

## 5. Category-Level Defect Checks

The Data Quality Engine (`incident_quality_v1`) evaluates the following specific categories:

1. **Missing Narrative (`MISSING_NARRATIVE`):** Narrative field is null or empty. (Severity: `CRITICAL`).
2. **Short Narrative (`SHORT_NARRATIVE`):** Narrative contains fewer than 10 words. (Severity: `WARNING`).
3. **Placeholder Text (`PLACEHOLDER_NARRATIVE`):** Narrative consists of placeholder tokens (e.g. "test", "dummy", "n/a", "asdf"). (Severity: `CRITICAL`).
4. **Unsupported Encodings (`UNSUPPORTED_ENCODING`):** Presence of null bytes (`\x00`) or Unicode replacement characters (`\ufffd`). (Severity: `CRITICAL`).
5. **Future Incident Date (`FUTURE_DATE`):** Incident date is later than the current calendar date. (Severity: `CRITICAL`).
6. **Missing Date (`MISSING_DATE`):** Incident timestamp is null. (Severity: `WARNING`).
7. **Invalid Location (`INVALID_LOCATION`):** Location contains placeholder strings or is blank. (Severity: `WARNING`).
8. **Field Contradictions (`SEVERITY_CONFLICT`, `NEAR_MISS_CONFLICT`):** Record marked as "Near Miss" but reports lost time injury or fatality. (Severity: `WARNING`).
9. **Duplicate Detection (`compute_narrative_duplicate_hash`):** Computes normalized 16-character SHA-256 narrative fingerprints to flag repeated templates.

---

## 6. Data Quality Reporting & Endpoints

Data Quality metrics are exposed through authoritative REST APIs and interactive dashboards:
- `GET /dashboard/data-quality/`: Interactive HTML dashboard with dataset filtering.
- `GET /api/data-quality/`: Full data quality audit payload including summary metrics, evidence states, defect categories, and ingestion pathway assurance.
- `GET /api/data-quality/summary/`: Concise summary KPIs with scope, timestamp, counts, and rates.
