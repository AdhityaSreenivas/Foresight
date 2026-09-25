# Foresight PSIF Platform — Model Training Provenance & Data Quality Gate Report
**OIL India Problem Statement 26165**  
*Document Version: 3.0 | Status: APPROVED ARCHITECTURE*

---

## Executive Summary

This report establishes the architectural and technical specification for data provenance, data quality gating, and candidate model training in the Foresight PSIF platform:
1. **Ingestion-Time Data Quality Gate**: Centralized gate rejecting materially insufficient, corrupted, or contradictory incident data at ingestion across all entry points (Manual entry, Manual Prediction API, Bulk file uploads, and Document ingestion).
2. **Clean Two-Category Synthetic Provenance**:
   - **`SYNTHETIC`**: Sole category for all generated records (benchmark, unreviewed, and simulated-review records).
   - **`HUMAN_APPROVED_SYNTHETIC`**: The only elevated synthetic category, strictly requiring genuine human HSE review and consensus adjudication.
3. **Decoupled Human Decision Status**: Review decisions (`PSIF`, `NOT_PSIF`, `INSUFFICIENT_INFORMATION`) are tracked separately from provenance.
4. **Internal Mixed Training Strategy**: Mixed training (`SYNTHETIC + HUMAN_APPROVED_SYNTHETIC`) exists strictly as an internal backend implementation strategy and is never exposed as a dataset type or user-facing category.

---

## 1. Architectural Separation: Data Quality Gate vs Training Eligibility

```
                           Incident Data Ingestion
           (Manual Form, Predict API, CSV/JSON/JSONL, Documents)
                                     │
                                     ▼
                ┌─────────────────────────────────────────┐
                │ validate_incident_for_analysis(record)  │
                └─────────────────────────────────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
      [CRITICAL Failure]                         [VALID or WARNING]
  "Data quality is insufficient                          │
         for analysis."                                  ▼
                 │                            Accepted for Ingestion
       HARD REJECTION AT GATE:                           │
  - No PSIF Score / Probability                          ├── ML Inference (PSIF Predictor)
  - No SHAP Explanation                                  ├── SHAP Feature Attributions
  - No IOGP Life-Saving Rules Tagging                    ├── IOGP Life-Saving Rules Tagging
  - No Recurrence / Similarity Analysis                  ├── Recurrence & Similarity Graphs
  - EXCLUDED from All Training Sources                   └── HSE Expert Review Queue
                                                                 │
                                                                 ▼
                                                    ┌────────────────────────┐
                                                    │ HSE Human Review Queue │
                                                    └────────────────────────┘
                                                                 │
                                       ┌─────────────────────────┴─────────────────────────┐
                                       ▼                                                   ▼
                         [Binary Consensus: PSIF / NOT_PSIF]                    [INSUFFICIENT_INFORMATION]
                                       │                                                   │
                                       ▼                                                   ▼
                            Eligible for Supervised                                Valid HSE Audit Record
                       Human-Approved Synthetic Training                  (Excluded from Binary Training Targets)
```

### 1.1 Ingestion Gate Enforcement
The canonical data quality service (`apps/incidents/services/data_quality.py`) evaluates:
- **Narrative Completeness**: Rejection of empty narratives, whitespace-only, single-word tokens (`"Accident"`), generic placeholders (`"desc"`, `"test"`, `"asdf"`), or corrupted character noise.
- **Structural Sanity**: Rejection of impossible dates (e.g. year 2099 or before 1970).
- **Physical Contradictions**: Rejection of conflicting anatomy (e.g. eye injuries paired with leg body parts).
- **Near-Miss vs Actual Severity**: Rejection of fatal/major injury classifications tagged as zero-consequence near-misses.

When rejected:
- The standard error message is issued: `Data quality is insufficient for analysis.`
- The UI displays explicit bulleted reasons explaining what is missing or contradictory.
- For bulk uploads (CSV, JSON, JSONL), row-level gating isolates invalid rows, tracks row numbers and rejection reasons in `quality_summary`, and allows clean rows to be ingested.

### 1.2 Strict Separation of Concepts
- **Data Quality Insufficient**: An **ingestion-time defect** indicating unprocessable raw data. The record is refused entry.
- **Human Review `INSUFFICIENT_INFORMATION`**: A **valid domain assessment** by an HSE reviewer indicating that an accepted, readable narrative does not contain sufficient forensic evidence to confirm or rule out a PSIF precursor. The record is retained for regulatory audit but excluded from binary classification training.

---

## 2. Provenance Architecture & Training Sources

The platform defines exactly two user-facing synthetic categories:

| Training / Provenance Category | Category Description | Record Eligibility Criteria | Default Validation Basis | Real-World HSE Validity |
|:---|:---|:---|:---|:---|
| **`SYNTHETIC`** | Sole category for all generated records | Artificial/generated records (`raw_row.sif_label`), unreviewed benchmark data, and simulated-review records | `SYNTHETIC BENCHMARK EVALUATION` | Experimental / Benchmark Only |
| **`HUMAN_APPROVED_SYNTHETIC`** | Sole elevated synthetic category | Synthetic records with genuine human reviewer adjudication (`PSIF` or `NOT_PSIF`), `is_synthetic_adjudication=False` | `HUMAN-APPROVED SYNTHETIC EVALUATION` | Human-Reviewed Synthetic Ground Truth |

### 2.1 Internal Implementation Strategy: Mixed Training
- **Mixed Training (`SYNTHETIC + HUMAN_APPROVED_SYNTHETIC`)**: Supported strictly as an internal implementation strategy if hybrid training is required.
- **Not a Dataset Type**: `MIXED_SYNTHETIC` is never presented as a dataset type or user-facing category in the UI or public API documentation.
- **Precedence**: Human-adjudicated decisions strictly override synthetic benchmark labels.

### 2.2 Non-Masquerading & Provenance Rules
1. **Zero Masquerading**: Synthetic records and simulated reviews (`is_synthetic_adjudication=True`) **never** count as real-world OIL ground truth.
2. **Simulation Exclusion**: Simulated review records belong to `SYNTHETIC` (never elevated to `HUMAN_APPROVED_SYNTHETIC`) and have `effective_training_label = None` (excluded from supervised binary targets).
3. **Immutable Traceability**: Every record in the training snapshot records its explicit `label_source` (`synthetic`, `human_approved_synthetic`).
4. **Controlled Promotion Lifecycle**: Newly trained candidate models are saved in `READY` status with `is_active=False`. Active models are never replaced automatically; activation requires an authorized administrator passing the 9-point safety gate.
5. **Mandatory Disclaimers**: Candidate models display persistent disclaimers:
   > *"Human approval of synthetic incidents indicates human review of generated examples; it is not equivalent to validation against real-world OIL HSE records."*

---

## 3. Database Provenance Breakdown (Authoritative Current State)

The platform strictly differentiates mutually exclusive provenance categories:

```text
1. SYNTHETIC (sole category for all generated/benchmark/simulated-review records)
2. HUMAN_APPROVED_SYNTHETIC (only elevated synthetic category)
3. REAL_EXTERNAL (real-world external datasets, e.g. OSHA)
4. REAL_HUMAN (genuine real-world human data)
5. UNKNOWN_UNLABELLED
```

### 3.1 Provenance Accounting Table
| Provenance Category | Database / File Count | Training Eligibility | Authoritative Validation Basis | Notes |
|:---|:---:|:---:|:---:|:---|
| **Total Incidents in Database** | **50,780** | — | — | Complete PostgreSQL incident inventory |
| **Synthetic Records (`final_50000_dataset.jsonl` + legacy)** | **49,870** in DB | Eligible for `SYNTHETIC` | `SYNTHETIC BENCHMARK EVALUATION` | Benchmark used 5,000-row sample |
| **Human-Approved Synthetic Records** | **9** | **9 (Eligible if ≥20)** | `HUMAN-APPROVED SYNTHETIC EVALUATION` | Genuine human HSE reviewed and adjudicated |
| **Simulated Review Records** | **600** (150 incidents) | **EXCLUDED (effective label None)** | `SYNTHETIC` | Simulated evaluation benchmark reviews (`is_synthetic_adjudication=True`) |
| **Former Heuristic Records (Audited)** | **765** | Reclassified to `SYNTHETIC` | `SYNTHETIC BENCHMARK EVALUATION` | Application-generated synthetic data; heuristic concept eliminated |

---

## 4. Immutable Training Snapshot Specification

Each training execution generates an immutable JSON snapshot persisted in `ml_engine/artifacts/<version_label>/training_snapshot.json` and linked to PostgreSQL `ModelVersion`:

```json
{
  "snapshot_id": "uuid-v4",
  "model_version_label": "v_YYYYMMDD_HHMMSS",
  "training_source": "SYNTHETIC | HUMAN_APPROVED_SYNTHETIC",
  "validation_basis": "SYNTHETIC BENCHMARK EVALUATION | HUMAN-APPROVED SYNTHETIC EVALUATION",
  "disclaimer": "Mandatory non-human disclaimer if applicable",
  "dataset_hash": "sha256-hex-digest",
  "provenance_summary": {
    "human_approved_synthetic": 9,
    "human_approved_synthetic_psif": 5,
    "human_approved_synthetic_not_psif": 4,
    "human_insufficient_information": 1,
    "synthetic": 49870,
    "real_external": 0,
    "unknown_unlabelled": 0
  },
  "provenance_composition": {
    "training_source": "SYNTHETIC",
    "total_eligible": 915,
    "human_approved_synthetic_count": 0,
    "synthetic_count": 915,
    "positive_count": 182,
    "negative_count": 733
  },
  "incident_records": [
    {
      "incident_id": "uuid",
      "target": 1,
      "label_source": "synthetic",
      "provenance_category": "SYNTHETIC"
    }
  ]
}
```
```

---

## 5. Regulatory & Operational Disclaimers

1. **OIL India Compliance**: This platform conforms to the Directorate General of Mines Safety (DGMS) and Oil Industry Safety Directorate (OISD) guidelines for precursor reporting.
2. **AI Advisory Role**: PSIF probability and precursor risk levels serve as triage decision support for safety officers and must not be used as the sole determinant for disciplinary or regulatory penalty actions.
3. **Model Promotion Gate**: All candidate model promotions require sign-off through the Foresight 9-point administrative safety gate.
4. **Overall System Characterization**:
   > A technically integrated, human-validation-ready SIH demonstration prototype whose real-world PSIF predictive validity remains to be established using genuine human-reviewed HSE data.

