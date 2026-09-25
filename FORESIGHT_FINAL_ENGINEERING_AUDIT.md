# Foresight PSIF Platform: Final Engineering & Technical Integrity Audit
**Smart India Hackathon (SIH) — Problem Statement 26165 (OIL India)**  
*System: Foresight Potential Serious Injury and Fatality (PSIF) Prediction Platform*  
*Repository: `/Users/sas/Developer/prototype_165`*  
*Audit Date: September 6, 2026*  
*Engineering Standard: High-Consequence Industrial Safety AI Governance*

---

## Canonical System Statement

> **"A technically integrated, human-validation-ready SIH demonstration prototype whose real-world PSIF predictive validity remains to be established using genuine human-reviewed HSE data."**

---

## Executive Summary

This Final Engineering Audit documents the authoritative reconciliation of the Foresight PSIF Platform across actual PostgreSQL database states, verified dataset files, model artifacts, benchmark executions, and automated test suites. 

Every claim, metric, and count in this report has been verified directly against executable source code, database tables, disk-based artifacts, and the test runner. No previous report values were accepted without empirical proof.

---

## 1. Canonical Data Quality Gate & Rejection Semantics

### 1.1 Architecture & Implementation
A single canonical Data Quality Gate is implemented in [`apps/incidents/services/data_quality.py`](file:///Users/sas/Developer/prototype_165/apps/incidents/services/data_quality.py) via `validate_incident_quality`. It executes unconditionally across all six ingestion pathways in the platform:
1. **Manual Incident Entry**: Form validation via [`apps/incidents/forms.py`](file:///Users/sas/Developer/prototype_165/apps/incidents/forms.py) (`IncidentForm.clean()`) and manual predict API (`PredictView` in [`apps/predictions/api_views.py`](file:///Users/sas/Developer/prototype_165/apps/predictions/api_views.py)).
2. **CSV Batch Upload**: Celery streaming ingestion in [`apps/datasets/ingestion.py`](file:///Users/sas/Developer/prototype_165/apps/datasets/ingestion.py).
3. **JSON Array Upload**: Streaming parser ingestion in [`apps/datasets/ingestion.py`](file:///Users/sas/Developer/prototype_165/apps/datasets/ingestion.py).
4. **JSONL Line-Delimited Upload**: Streaming ingestion in [`apps/datasets/ingestion.py`](file:///Users/sas/Developer/prototype_165/apps/datasets/ingestion.py).
5. **Document / Unstructured File Extraction**: PDF, DOCX, and TXT extraction pipeline in [`apps/datasets/ingestion.py`](file:///Users/sas/Developer/prototype_165/apps/datasets/ingestion.py) (`extract_incidents_from_document`).
6. **Bulk Ingestion & Re-Ingestion Services**: Dataset lifecycle processor in [`apps/datasets/tasks.py`](file:///Users/sas/Developer/prototype_165/apps/datasets/tasks.py).

### 1.2 Ingestion Rejection Semantics
The ingestion rejection semantics are strictly defined:
```text
Raw submission
      ↓
Quality Gate
      ↓
CRITICAL
      ├── The rejected incident is not created as an analyzable Incident
      ├── No Prediction is generated
      ├── No SHAP explanation or factor breakdown is computed
      ├── No IOGP rule mapping is performed
      ├── No similarity search is executed
      ├── No recurrence analysis is performed
      └── Preserves rejection event and reasons in dataset audit/ingestion record
```

**Precise Distinction**:
- **Ingestion Rejection (`IncidentDataQuality.Status.CRITICAL`)**: Automatic gate at the system boundary indicating the raw submission lacks minimal coherent information. The rejected incident is not created as an analyzable Incident in `incidents_incident`. The rejection event and diagnostic reasons are preserved in the dataset ingestion audit log (`quality_summary` and `error_log`).
- **HSE Reviewer Finding (`ReviewQueue.INSUFFICIENT_INFORMATION`)**: Human domain expert assessment during triage indicating that while the report is technically valid, additional field investigation or witness testimony is required to determine whether critical controls failed.

### 1.3 Database Data Quality Counts
Queried directly from PostgreSQL:
- **Total Incidents in Database**: **50,780**
- **Total Records with Data Quality Assessments**: **850**
  - **`VALID` (Accepted for Inference & Training)**: **713** (83.88%)
  - **`WARNING` (Accepted with Warning Callout)**: **100** (11.76%)
  - **`CRITICAL` (Rejected at Ingestion / Prediction Blocked)**: **37** (4.35%)
  - *(Sum: $713 + 100 + 37 = 850$)*
- **Incidents Awaiting Batch DQ Evaluation**: **49,930** (exploratory synthetic records)
- **Ingestion Attempts Rejected at Perimeter**: **2** (recorded in test verification audit; never created in `incidents_incident`)

---

## 2. Human Review & Training Provenance

### 2.1 Seven Canonical Provenance Categories
Implemented in [`ml_engine/training/training_sources.py`](file:///Users/sas/Developer/prototype_165/ml_engine/training/training_sources.py) and enforced in [`ml_engine/training/trainer.py`](file:///Users/sas/Developer/prototype_165/ml_engine/training/trainer.py):
1. `INDIVIDUAL HUMAN REVIEW`: A single human domain expert review without verified consensus.
2. `VERIFIED HUMAN CONSENSUS`: A dual-reviewer consensus or formal adjudication by qualified HSE experts.
3. `HUMAN INSUFFICIENT_INFORMATION`: Human domain expert triage determination that field investigation is incomplete.
4. `SYNTHETIC REVIEW SIMULATION`: Automated synthetic persona reviews (e.g., `hse_lead_auditor`, `hse_field_specialist`).
5. `HEURISTIC LABEL`: Rule-derived proxy labels from recorded severity classifications.
6. `SYNTHETIC DATASET LABEL`: Labels generated as part of synthetic generative datasets.
7. `UNKNOWN`: Records with unverified or missing provenance metadata.

### 2.2 Critical Human Validation Rule
**Individual human reviews do NOT automatically constitute human ground truth.**

Authoritative PostgreSQL database query results:
```text
Individual human reviews: 149
Verified human consensus cases: 0
Real human validation basis: NOT ESTABLISHED
Human training eligible: 0
```

- **Individual Human Reviews**: 149 reviews exist in historical snapshots.
- **Verified Human Consensus Cases**: **0**. There are 0 records in `incidents_incidentreviewadjudication` where `is_synthetic_adjudication=False` and a non-null consensus decision was reached.
- **Synthetic Review Simulations**: **600** reviews across 300 incidents (150 synthetic adjudications; all tagged with `is_synthetic=True`).
- **Application Heuristic Proxy Records**: **760** (150 PSIF, 610 NOT_PSIF).
- **Unlabelled Incidents**: **49,870**. *(Sum: $760 + 150 + 49,870 = 50,780$)*.

The system will **never** display `REAL HUMAN HSE VALIDATION` unless a model's validation set contains genuine validated human consensus cases. Usernames are never used as proof of human validation.

---

## 3. Dataset Inventory & Benchmark Reconciliation

### 3.1 50k Dataset Verification
The actual 50,000 synthetic dataset was inspected on the filesystem:
- **File Path**: [`media/uploads/182250b2-dd76-4506-826a-dd6da0c457a3/final_50000_dataset.jsonl`](file:///Users/sas/Developer/prototype_165/media/uploads/182250b2-dd76-4506-826a-dd6da0c457a3/final_50000_dataset.jsonl)
- **Exact File Size**: **43,667,279 bytes** (~41.6 MB)
- **Exact Row Count**: **50,000** lines (100% valid JSON, 0 malformed, 0 duplicate IDs, 0 empty narratives)
- **Full 50k Class Distribution**: 30,327 positive (60.65%), 19,673 negative (39.35%)
- **Benchmark Sample Size**: **5,000** rows
- **Sampling Method**: Stratified uniform random sampling preserving positive/negative class proportions
- **Random Seed**: `seed = 42` via `np.random.default_rng(42)`
- **Benchmark Sample Distribution**: 3,013 positive (60.26%), 1,987 negative (39.74%)

### 3.2 100k Dataset Status
A thorough search across all local and media storage paths confirms:
- **100k Dataset File**: **NOT PRESENT** anywhere in the project repository.
- **Reporting Rule**: The 100k dataset is formally documented as non-existent and is not reported as analyzed.

### 3.3 Boilerplate Repetition Analysis
- **Boilerplate Detected**: **`True`** (Severity: **`HIGH`**)
- **Top Repeated Phrases**:
  - `"the observation was made at"`: Found in **1,554** sample rows (31.1%) and **15,806** full 50k rows (31.6%).
  - `"the interacting condition was"`: Found in **511** sample rows (10.2%) and **5,428** full 50k rows (10.9%).
- **Template Mechanism**: Algorithmic slot-filling generative skeleton (`"The observation was made at [facility]. The interacting condition was [condition]..."`).
- **Crosses Train/Test Boundaries**: **Yes**. 100% of train and test folds contain identical skeleton phrases.

### 3.4 Grouped vs Random Evaluation Reconciliation
The apparent contradiction between reports citing **`ROC-AUC = 1.0`** and **`ROC-AUC = 0.5401`** is resolved by the actual benchmark implementation:
1. **Text TF-IDF Model**: Achieves **1.0000** ROC-AUC on the random split and **1.0000** ROC-AUC on the grouped split (`group_key = f"{site_area}_{activity}"`, 256 disjoint groups, 0 group overlap). This occurs because **138 class-associated lexical tokens** (`"Barrier finding:"`, `"incorrect restoration"`, `"unexpected start"`) cross group boundaries uniformly.
2. **Structured Only Operational Baseline**: A Logistic Regression model trained exclusively on non-target categorical metadata (`activity`, `site_area`, `report_type`, `department`) achieves an ROC-AUC of **0.5399** (~0.5401) on the random split and **0.5177** on the grouped split. 

The 0.5401 metric cited in earlier reports is the score of the non-target structured operational baseline, not a collapsed text model. Both numbers are empirically verified.

---

## 4. Counterfactual, Hard-Negative, and Adversarial Results

### 4.1 Counterfactual Sensitivity
- **Implementation**: Five pairs of semantically controlled incident narratives where only the precursor barrier failure status is toggled (e.g., control barrier holding vs barrier failing).
- **Result**: **1 / 5 passed (20.0% accuracy)**.
- **Assessment**: **POOR precursor sensitivity**. The model relies on surface vocabulary rather than semantic causal barrier dynamics.
- **Policy**: Thresholds were not artificially tuned to manipulate this result; failures are reported honestly.

### 4.2 Hard-Negative Analysis
- **Definition**: Incidents detailing high physical energy or dramatic operational disruptions that successfully contained all hazardous energy without critical barrier failure (true negative PSIF cases).
- **Benchmark Sample**: **64 / 1,987 negative rows (3.22%)**.
- **Full 50k Dataset Census**: **648 / 19,673 negative rows (3.29%)**.
- **Assessment**: **Hard-negative diversity is insufficient for strong real-world validation.**

### 4.3 Adversarial Robustness
- **Implementation**: 10 semantically controlled adversarial perturbations (synonym substitutions, colloquial severity shifts, and narrative phrasing adjustments).
- **Result**: **6 / 10 passed (60.0% pass rate)**.
- **Average Prediction Shift**: **0.28**.
- **Assessment**: **VULNERABLE**.

---

## 5. Model Catalog & Provenance

### 5.1 Authoritative Catalog

| Field | Active Baseline Model | Heuristic Candidate Model | Synthetic Candidate Model |
| :--- | :---: | :---: | :---: |
| **Model Version** | `v_20260902_122321` | `v_20260905_203530` | `v_20260906_093529` |
| **Lifecycle Status** | **ACTIVE** | **READY (DEVELOPMENT CANDIDATE)** | **READY (EXPERIMENTAL CANDIDATE)** |
| **Active in Serving (`is_active`)** | **`True`** | **`False`** | **`False`** |
| **Training Source** | `HEURISTIC` | `HEURISTIC` | `SYNTHETIC` |
| **Validation Basis** | `APPLICATION HEURISTIC EVALUATION` | `APPLICATION HEURISTIC EVALUATION` | `SYNTHETIC DATASET EVALUATION` |
| **Snapshot Path** | Legacy DB Snapshot | `.../v_20260905_203530/training_snapshot.json` | `.../v_20260906_093529/training_snapshot.json` |
| **Dataset SHA-256 Hash** | N/A | `be9f0a16bc202e85fa424f36f5dc53f...` | `d502d61e6847b2bdf70b378250363dbf...` |
| **Total Labeled Rows** | 761 | 760 | 1,500 (sampled from 50k) |
| **Train / Test Rows** | 646 / 115 | 646 / 114 | 1,275 / 225 |
| **Human Consensus Records** | 0 | 0 | 0 |
| **Heuristic Proxy Records** | 761 | 760 | 0 |
| **Synthetic Dataset Records** | 0 | 0 | 1,500 |
| **Precursor Recall** | **0.9565 (95.7%)** | **0.9545 (95.5%)** | **0.9906 (99.1%)** |
| **Precision** | **0.2018 (20.2%)** | **0.2165 (21.7%)** | **1.0000 (100.0%)** |
| **F1 Score** | **0.3333** | **0.3529** | **0.9953** |
| **F2 Score ($F_2$)** | **0.5473** | **0.5676** | **0.9924** |
| **ROC-AUC** | **0.6215** | **0.6843** | **0.9999** |
| **PR-AUC** | **0.3742** | **0.4783** | **0.9999** |
| **Operating Threshold** | **0.10** | **0.15** | **0.50** |
| **Confusion Matrix** | `[[5, 87], [1, 22]]` | `[[16, 76], [1, 21]]` | `[[119, 0], [1, 105]]` |
| **False Negatives ($FN$)** | **1** | **1** | **1** |

### 5.2 Active Model Invariance
Verified directly from PostgreSQL:
```python
ModelVersion.objects.filter(is_active=True)
# Result: <QuerySet [<ModelVersion: v_20260902_122321 (ACTIVE)>]>
```
There is strictly **one** active serving model: `v_20260902_122321`. Neither candidate was activated or modified.

---

## 6. Authoritative Full Test Suite Execution

A single authoritative test execution was run across the complete test suite:
```bash
OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE ./venv/bin/pytest -q
```

**Authoritative Test Result**:
```text
170 passed, 5 warnings in 53.98s
```
All 170 tests across ingestion, data quality, training provenance, dataset benchmarking, candidate isolation, model retraining, and permission gates passed with zero errors and zero failures.

---

## 7. Machine-Generated Reconciliation Table

The authoritative state of all 15 core platform entities is summarized below:

| Item | Actual Current Value | Source of Truth |
| :--- | :--- | :--- |
| **Total incidents** | **50,780** | PostgreSQL (`incidents_incident.objects.count()`) |
| **Synthetic dataset rows** | **50,000** | Actual file (`final_50000_dataset.jsonl`, 43,667,279 bytes) |
| **Benchmark rows** | **5,000** | Benchmark artifact (`dataset_benchmark_summary.json`, stratified seed=42) |
| **Individual human reviews** | **149** | PostgreSQL (`incidents_incidentreview` legacy records) |
| **Verified human consensus** | **0** | Adjudication query (`is_synthetic_adjudication=False`, decision not null) |
| **Heuristic labels** | **760** | PostgreSQL (`is_psif_heuristic_label=True`, 150 PSIF, 610 NOT_PSIF) |
| **Synthetic review simulations** | **600** | PostgreSQL (`IncidentReview.is_synthetic=True`, 300 incidents, 150 adjudications) |
| **Active model** | **`v_20260902_122321`** | PostgreSQL (`ModelVersion.objects.filter(is_active=True)`) |
| **Synthetic candidate** | **`v_20260906_093529`** | PostgreSQL (`ModelVersion`, `is_active=False`, `READY`) |
| **Heuristic candidate** | **`v_20260905_203530`** | PostgreSQL (`ModelVersion`, `is_active=False`, `READY`) |
| **Random ROC-AUC** | **1.0000** (Text TF-IDF) / **0.5399** (Structured Baseline) | Benchmark artifact (`dataset_benchmark_summary.json`) |
| **Grouped ROC-AUC** | **1.0000** (Text TF-IDF) / **0.5177** (Structured Baseline) | Benchmark artifact (256 disjoint groups, site_area + activity) |
| **Counterfactual accuracy** | **20.0%** (1 / 5 passed) | Benchmark artifact (`counterfactual_summary`) |
| **Hard-negative rate** | **3.22%** (64 / 1,987 in sample; 3.29% in 50k census) | Benchmark artifact (`hard_negative_summary`) |
| **Adversarial pass rate** | **60.0%** (6 / 10 passed) | Benchmark artifact (`adversarial_summary`) |
| **Final pytest result** | **170 passed, 5 warnings** | Test command (`OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE ./venv/bin/pytest -q`) |

---

## 8. Final Integrity Verdict

```text
INTEGRITY VERIFIED WITH DOCUMENTED LIMITATIONS
```

### Justification for Verdict:
1. **Integrity Verified**: The canonical Data Quality Gate executes unconditionally across all 6 ingestion pathways, rejecting critically deficient data and strictly blocking ML inference and SHAP explainability. Multi-source training provenance strictly separates human, heuristic, and synthetic records with zero masquerading. The active serving model (`v_20260902_122321`) remains untouched and isolated from candidate evaluations. All 170 tests in the test suite pass cleanly.
2. **Documented Limitations**:
   - **Real Human Validation Basis is NOT ESTABLISHED**: Although 149 individual human reviews exist, there are 0 verified dual-reviewer human consensus cases in the database.
   - **Synthetic Dataset Generalization**: The 50,000 synthetic dataset contains rigid template boilerplate (31.1% prevalence) and 138 class-leaking tokens that induce artificial 1.0 ROC-AUC scores on text models.
   - **Precursor Sensitivity**: Active serving models exhibit low counterfactual accuracy (20.0%) and vulnerability to adversarial phrasing (60.0% pass rate), reflecting a reliance on surface keywords rather than deep causal barrier understanding.
   - **Hard Negative Diversity**: Only 3.22% of negative samples represent hard negatives, which is insufficient for strong real-world industrial validation.
