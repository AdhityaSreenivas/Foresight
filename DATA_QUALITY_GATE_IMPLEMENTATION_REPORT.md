# Foresight PSIF Platform — Data Quality Gate Implementation Report
**OIL India Problem Statement 26165**  
*Document Version: 1.0 | Status: COMPLETED & VERIFIED*

---

## Executive Summary

This report provides the technical documentation and verification audit for the single canonical **Data Quality Gate** implemented across all incident ingestion channels in the Foresight PSIF platform.

The primary objective is:
> *Materially insufficient incident data must be rejected before automated analysis and must never receive a misleading PSIF prediction.*

The implementation extends the platform's native `apps/incidents/services/data_quality.py` framework, ensuring that all 6 ingestion pathways (Manual Incident Creation, Manual Predict API, CSV Upload, JSON Upload, JSONL Ingestion, and Document/File Ingestion) share the exact same validation rules, error formats, and gating semantics.

---

## 1. Architectural Design & Canonical Quality Gate

### 1.1 Canonical Service Function
The single entry point for incident quality evaluation is:
```python
validate_incident_for_analysis(
    data: Incident | Dict[str, Any],
    min_quality_status: str = "WARNING",
) -> Dict[str, Any]
```

### 1.2 Return Schema
The gate returns a structured, strictly validated dictionary containing:
```python
{
    "accepted": bool,              # True if quality_status in (VALID, WARNING); False if CRITICAL
    "quality_status": str,         # "VALID" | "WARNING" | "CRITICAL"
    "quality_score": float,        # Continuous score [0.0 - 1.0]
    "blocking_findings": list[str],# Explicit reasons causing CRITICAL rejection
    "warning_findings": list[str], # Non-blocking quality warnings (sparse narrative, etc.)
    "missing_fields": list[str],   # List of missing mandatory field names
    "reason": str,                 # High-level summary string
    "quality_version": str,        # "incident_quality_v1"
    "findings": list[dict],        # Full audit findings with check IDs and severities
}
```

### 1.3 Gating Status Vocabulary
* **VALID**: Fully compliant record with sufficient narrative and non-contradictory metadata. Proceed directly to inference, embedding, and downstream analysis.
* **WARNING**: Mildly sparse record (e.g. narrative < 10 words, optional activity missing, or missing incident date). Proceed with downstream analysis, but flag the prediction as potentially reduced confidence.
* **CRITICAL**: Materially corrupted, placeholder, empty, or structurally contradictory record. **Strictly rejected from automated analysis**. No PSIF prediction is generated, no SHAP explanation is computed, no IOGP rules are tagged, and the record is excluded from all training pipelines.

---

### 1.4 Database Data Quality Breakdown (Authoritative Reconciliation)
Direct query of the PostgreSQL database establishes the empirical inventory:
* **Total Incidents in Database**: **50,780**
* **Total Records with Explicit Data Quality Assessments**: **850**
  - **VALID**: **713** (83.9%)
  - **WARNING**: **100** (11.8%)
  - **CRITICAL**: **37** (4.4%)
  - *Sum (VALID + WARNING + CRITICAL)*: **850** (100.0% match)
* **Incidents Awaiting Batch Quality Assessment**: **49,930** (historical unanalyzed bulk exploratory synthetic records)
* **Rejected Ingestion Records**: **2** (recorded in `test_verification.csv` ingestion audit; isolated at system perimeter and never created in the Incident table)

---

## 2. Comprehensive Quality Rules

The quality gate evaluates three distinct dimensions:

### 2.1 Narrative Completeness & Integrity
1. **Empty & Whitespace Rejection**: Any empty or whitespace-only narrative is rejected (`MISSING_NARRATIVE`).
2. **Placeholder Detection**: Narratives matching known test tokens (`test`, `dummy`, `asdf`, `sample`, `n/a`, `none`, `placeholder`, `tbd`, `na na`, `desc123`, etc.) are rejected (`PLACEHOLDER_NARRATIVE`).
3. **Meaningless & Corrupted Text**: Narratives consisting of non-alphanumeric noise, repetitive characters (`zzzzzz`), zero vowels (`bcdfgh jklmnp`), or keyboard mash (`asdfghjkl qwertyuiop`) are rejected (`MEANINGLESS_NARRATIVE`, `CORRUPTED_NARRATIVE`).
4. **Single-Word Rejection**: Generic one-word narratives without operational context (`"Accident"`, `"Fell"`, `"Injured"`, `"Spill"`) are rejected (`INSUFFICIENT_NARRATIVE`).
5. **Short Narrative Warning**: Legitimate short narratives (< 10 words, e.g. `"Worker slipped on stairs and bruised elbow."`) are **accepted with a WARNING**, preserving the essential sparse-input distinction.

### 2.2 Structural & Chronological Sanity
1. **Future Date Prevention**: Incident dates beyond `date.today()` are rejected (`FUTURE_DATE`).
2. **Impossible Historical Dates**: Incident dates earlier than 1970 or past 2050 are rejected (`IMPOSSIBLE_DATE`).
3. **Missing Date Handling**: Missing dates trigger a warning (`MISSING_DATE`) but do not block narrative analysis.

### 2.3 Physical & Operational Contradictions
1. **Anatomical Contradictions**: Rejects records where the narrative describes an injury to one body part (e.g., eye laceration) but the structured dropdown specifies an incompatible body part (e.g., `leg`) (`CONTRADICTORY_BODY_PART`).
2. **Injury Type Conflicts**: Rejects records where the text details a severe injury (e.g., `fracture`) while the categorical field specifies an incompatible minor injury (e.g., `burn`) (`CONTRADICTORY_INJURY_TYPE`).
3. **Severity vs Near-Miss Conflicts**: Rejects incidents marked as near-misses that report fatal, lost-time, or major medical outcomes (`CONTRADICTORY_SEVERITY_NEAR_MISS`).

---

## 3. Ingestion Path Integration

| Ingestion Pathway | Module / View | Handling on CRITICAL Status | Handling on VALID / WARNING Status |
|:---|:---|:---|:---|
| **Manual Form** | `apps/incidents/forms.py`<br>`IncidentForm.clean()` | Form validation error raised. Form redisplayed with message: `"Data quality is insufficient for analysis."` and explicit bulleted findings. No database incident or prediction created. | Incident saved to DB. Downstream prediction and IOGP analysis triggered. |
| **Prediction API** | `apps/predictions/api_views.py`<br>`PredictView.post()` | Returns HTTP 400 Bad Request: `{"error": "Data quality is insufficient for analysis.", "blocking_findings": [...]}`. No PSIF score, no SHAP explanation. | Incident saved, prediction generated, SHAP attributions and IOGP rules returned. |
| **Bulk CSV / JSON / JSONL** | `apps/datasets/ingestion.py`<br>`bulk_create_incidents()` | Per-row isolation: invalid row rejected and logged in `quality_summary["rejection_details"]` with row number and reason. File processing continues for remaining valid rows. | Valid rows ingested into PostgreSQL in batches; `IncidentDataQuality` records saved. |
| **Document Ingestion** | `apps/datasets/ingestion.py`<br>`ingest_document_incidents()` | Extracted incident rows passed through identical `bulk_create_incidents()` gate. Critical rows isolated; clean rows accepted. | Valid extracted incidents created and linked to dataset. |
| **Celery Async Ingestion** | `apps/datasets/tasks.py`<br>`process_dataset_file()` | Chunked ingestion records `quality_summary` with `accepted`, `accepted_with_warnings`, and `rejected` counts in Dataset model. | Progress updated; downstream batch inference run only on accepted rows. |

---

## 4. UI Gating & User Feedback

1. **Manual Incident Creation**:
   - Rejection banner displayed with the exact required wording:
     > **Submission rejected**  
     > **Data quality is insufficient for analysis.**
   - Unfolded bulleted list of blocking findings explains precisely what to correct.
   - For warnings, an amber notice informs the user that brief narrative context may reduce prediction confidence.
2. **Bulk Ingestion Status UI** (`templates/datasets/status.html`):
   - Displays a dedicated **Data Quality Summary** card:
     * **Accepted Rows**: e.g. `47,900`
     * **Accepted with Warnings**: e.g. `1,950`
     * **Rejected Rows**: e.g. `150`
   - Interactive rejection table displays row numbers, specific failure causes, and missing fields.
   - Partial success semantics: files with some rejected rows are marked completed with quality warnings, not failed.

---

## 5. Strict Separation: Ingestion Rejection vs Human Review

| Dimension | Ingestion Data Quality Rejection | Human HSE Review `INSUFFICIENT_INFORMATION` |
|:---|:---|:---|
| **Nature** | Technical data defect (corrupted, empty, or contradictory input). | Professional safety domain assessment by an expert. |
| **Action** | **The rejected incident is not created as an analyzable Incident; the rejection event and reasons are retained in the audit/ingestion record** (e.g. Dataset `quality_summary` and `error_log`). | Valid incident accepted; reviewer concludes incident narrative lacks forensic details to confirm a precursor. |
| **Downstream PSIF** | Zero prediction, zero SHAP, zero IOGP tagging, zero similarity. | Retains original model prediction for audit, but flags need for investigation. |
| **Training Impact** | Excluded from all training. | Retained in audit registry; excluded from binary classification targets. |

---

## 6. Test Suite & Authoritative Full-Suite Verification

The platform was verified via the single authoritative full test command:

```bash
OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE ./venv/bin/pytest -q
```

### Exact Full-Suite Command Output:
```text
======================= 170 passed, 5 warnings in 53.98s =======================
```
* **Passed Tests**: **170**
* **Failed Tests**: **0**
* **Warnings**: **5** (Django async decorator and pandas datetime inference deprecation notices)
* **Execution Duration**: **53.98s**

The test coverage spans:
- `tests/test_data_quality_gate.py`: 18 tests covering all rejection, contradiction, and bypass prevention rules.
- `tests/test_multi_source_training.py`: 19 tests verifying provenance separation and non-masquerading.
- `tests/test_dataset_validity_benchmark.py`: 8 tests covering schema integrity, group-split isolation, counterfactuals, adversarial robustness, and active model preservation.
- Core pipeline suites: `test_api_predict.py` (7), `test_api_upload.py` (11), `test_celery_ingestion.py` (5), `test_column_mapping.py` (9), `test_data_integrity.py` (4), `test_dataset_inference.py` (4), `test_dataset_lifecycle.py` (6), `test_explainability.py` (3), `test_explainability_regression.py` (1), `test_ml_pipeline.py` (36), `test_parsers.py` (14), `test_permissions.py` (5), `test_seed_data.py` (5), `test_upload_security.py` (6), `apps/incidents/tests/test_data_quality.py` (9).

---

## 7. Known Operational Limitations & Architectural State

1. **Multilingual Narratives**: The current rule engine uses English lexicon and anatomy heuristics. Non-English narratives (e.g. Hindi or Assamese terms used in regional oilfields) require transliteration or upstream translation before semantic contradiction checks can execute.
2. **OCR Noise in Scanned Documents**: Low-resolution document scans can introduce OCR artifacts (e.g. `l` read as `1` or `rn` as `m`). The gate accommodates minor typographical variance but will reject severe OCR corruptions where word recognizability drops below threshold.
3. **Active Model Isolation**: Active inference predictor (`v_20260902_122321`) remains untouched, active, and safely protected by the gate.
4. **Authoritative Final Summary**:
   > A technically integrated, human-validation-ready SIH demonstration prototype whose real-world PSIF predictive validity remains to be established using genuine human-reviewed HSE data.

