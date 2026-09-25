# Candidate Model Retraining & Engineering Validation Report
**Project**: Foresight — OIL India SIH Problem Statement 26165  
**Candidate Model Version**: `v_20260905_203530` (ID: `e5a2c1a5-0a94-4a1f-8a1f-1877974c24d2`)  
**Active Baseline Model**: `v_20260902_122321` (ID: `53480641-f2fd-4ead-b3ef-55c70a931689`)  
**Execution Timestamp**: 2026-09-05T20:44:28Z  
**System Status**: Candidate Model in `READY` state (Inactive). Engineering validation passed. Human-validation-ready.  

---

## 1. Executive Summary & Safety Language

> [!IMPORTANT]
> **Safety & Governance Statement**:  
> In accordance with safety and evaluation guidelines for this prototype system, this report documents an **engineering validation** and **candidate model** evaluation.  
> - This retrained model is a **candidate model** subject to **controlled promotion** via an authenticated administrator action.  
> - It is **NOT** characterized as "production-ready" or "human-validated" because **zero genuine human HSE reviews** currently exist in the database.  
> - All training was conducted provisionally on **approved heuristic labels** with simulated evaluation records strictly excluded.  
> - The model is classified as **human-validation-ready**, awaiting genuine HSE personnel ground-truth adjudication.

---

## 2. Authoritative Database Label Provenance Audit

Rather than assuming hard-coded quantities, all label provenance is derived dynamically from PostgreSQL using authoritative model flags (`is_synthetic_adjudication`, `is_synthetic`, `psif_label_source`, and `adjudicated_human_decision`).

### Exact Database Provenance Breakdown (Execution Time)
*Total incidents in database: 50,780*

| Provenance Classification | Count | Training Eligibility | Supervised Target | Provenance Source of Truth |
| :--- | :---: | :---: | :---: | :--- |
| **Real Human PSIF** | **0** | Eligible | `True` (1) | `Incident.is_synthetic_adjudication=False` & `adjudicated_human_decision="PSIF"` |
| **Real Human NOT PSIF** | **0** | Eligible | `False` (0) | `Incident.is_synthetic_adjudication=False` & `adjudicated_human_decision="NOT_PSIF"` |
| **Real Human INSUFFICIENT_INFORMATION** | **0** | Excluded | `None` | `Incident.is_synthetic_adjudication=False` & `adjudicated_human_decision="INSUFFICIENT_INFORMATION"` |
| **Synthetic Evaluation Simulation** | **150** | **Strictly Excluded** | `None` | `Incident.is_synthetic_adjudication=True` or `psif_label_source="SYNTHETIC"` |
| **Heuristic PSIF** | **150** | Eligible (Provisional) | `True` (1) | `is_synthetic_adjudication=False` & `is_psif_heuristic_label=True` (Unreviewed by human) |
| **Heuristic NOT PSIF** | **610** | Eligible (Provisional) | `False` (0) | `is_synthetic_adjudication=False` & `is_psif_heuristic_label=False` (Unreviewed by human) |
| **Unknown / Unlabelled Incidents** | **49,870** | Excluded | `None` | Ingested incidents without heuristic or human labels |
| **Total Database Records** | **50,780** | — | — | Full PostgreSQL population |

### Training Cohort Summary
- **Human-labeled eligible**: `0`
- **Heuristic-labeled eligible**: `760` (150 positive, 610 negative)
- **Total training cohort size**: `760` incidents
- **Excluded from training**: `50,020` incidents (150 synthetic + 49,870 unlabelled)
- **Positive Prevalence**: `19.74%`
- **Class Imbalance Ratio (Neg / Pos)**: `4.07 : 1`
- **scale_pos_weight (computed from training fold only)**: `4.0469`

---

## 3. Strict Training Label Hierarchy & Precedence

The model training engine enforces the strict precedence hierarchy:

```text
synthetic evaluation
    → EXCLUDE / None (Strictly excluded; NEVER falls through to heuristic)

real human PSIF
    → True (Supervised Target 1)

real human NOT_PSIF
    → False (Supervised Target 0)

real human INSUFFICIENT_INFORMATION
    → EXCLUDE / None (Supersedes heuristic; never coerced to binary target)

otherwise heuristic PSIF / NOT_PSIF
    → True (1) / False (0) (Provisional engineering baseline)

otherwise
    → EXCLUDE / None
```

- **Audit Preservation**: Human decisions override heuristic labels for training purposes while preserving `is_psif_heuristic_label` intact on the database record for regulatory audit.
- **Flag-Based Identification**: Synthetic records are identified strictly through `is_synthetic_adjudication` and `is_synthetic` database booleans rather than brittle reviewer usernames.

---

## 4. Immutable Training Snapshot Audit

Each training execution binds an immutable snapshot artifact to the candidate `ModelVersion`.

- **Snapshot File**: `ml_engine/artifacts/v_20260905_203530/training_snapshot.json` (Size: 172,169 bytes)
- **Snapshot ID**: `9eb0badf-22c3-4ffe-9d0d-dfd2189de254`
- **SHA256 Dataset Hash**: `be9f0a16bc202e85fa424f36f5dc53f46d13e5370ceed495f76770e10a22c586`
- **Associated Model Version**: `v_20260905_203530`
- **Policy Version**: `2.0-provenance-hierarchy`
- **Feature Schema Version**: `1.0-distilbert768+structured` (856 fused dimensions)
- **Training Code Version**: `git-sih-26165-v2`
- **Complete Incident UUID List**: Exactly 760 UUIDs recorded with target and label source.
- **Reproducibility**: The exact training set, feature inputs, and evaluation metrics can be deterministically re-evaluated from this snapshot.

---

## 5. Metric Provenance Separation & Empirical Results

Metrics are rigorously partitioned by source. Heuristic metrics are never reported as human validation evidence.

### A. Real Human Validation Metrics
> **Status: N/A — No genuine HSE human ground truth currently available.**  
> Genuine HSE personnel have not yet reviewed incidents in the system. The platform is ready to record human ground-truth metrics as soon as reviews are submitted.

### B. Synthetic Simulation Metrics
> **Status: N/A — Excluded from model evaluation.**  
> Simulated reviewer records from software evaluation sweeps are quarantined and strictly excluded from candidate model performance claims.

### C. Heuristic-Label Evaluation Metrics (Observed Empirical Results)
*Evaluated on 760 approved heuristic records with 85/15 stratified split (Train: 646, Test: 114).*

#### 1. Out-of-Fold (OOF) 5-Fold Stratified Cross-Validation on Training Set (N=646)
- **Threshold Selection**: `0.15` (Selected to maximize F2 on OOF predictions)
- **Precision**: `0.2200`
- **Recall**: `0.8594`
- **F2 Score**: `0.5435`
- **F1 Score**: `0.3503`
- **ROC-AUC**: `0.6037`
- **PR-AUC**: `0.2681`
- **Confusion Matrix (OOF)**:
  - True Negatives (TN): `128`
  - False Positives (FP): `390`
  - False Negatives (FN): `18`
  - True Positives (TP): `110`
  - *Support*: 128 positive, 518 negative

#### 2. Final Test Set Evaluation (N=114, 85/15 Holdout)
- **Threshold**: `0.15`
- **Precision**: `0.2165`
- **Recall**: `0.9545` (21 out of 22 positive incidents detected; only 1 FN)
- **F2 Score**: `0.5676`
- **F1 Score**: `0.3529`
- **ROC-AUC**: `0.6843`
- **PR-AUC**: `0.4783`
- **Confusion Matrix (Test)**:
  - True Negatives (TN): `16`
  - False Positives (FP): `76`
  - False Negatives (FN): `1`
  - True Positives (TP): `21`
  - *Support*: 22 positive, 92 negative

#### 3. Model Architecture Ablation (Test Set N=114)
| Architecture | Features | Precision | Recall | F2 Score | F1 Score | ROC-AUC | PR-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline A: Structured-Only** | 88 | 0.1964 | 1.0000 | 0.5500 | 0.3284 | 0.6198 | 0.2750 |
| **Baseline B: Text-Only (BERT)** | 768 | 0.2105 | 0.9091 | 0.5464 | 0.3419 | 0.6561 | 0.4766 |
| **Fused Model (Candidate)** | **856** | **0.2165** | **0.9545** | **0.5676** | **0.3529** | **0.6843** | **0.4783** |

*Finding*: The multimodal fused model (DistilBERT 768-d text narrative embeddings + 88 structured one-hot features) outperforms both individual unimodal baselines in ROC-AUC (0.6843 vs 0.6198 / 0.6561) and PR-AUC (0.4783 vs 0.2750 / 0.4766).

---

## 6. Activation Safety Gate & Controlled Lifecycle Verification

The activation safety gate enforces a strict 10-point checklist before any candidate model can be promoted to active:

1. **Candidate Status**: `ModelVersion.status == READY` (Passed: `READY`)
2. **Current State**: Candidate is currently inactive (`is_active == False`)
3. **Training Status**: Successful training confirmed (`metrics.training_status == "READY"`)
4. **Evaluation Metrics**: `precision`, `recall`, `f1`, `roc_auc` present and non-null (Passed)
5. **Model Artifact**: `model.json` exists (106,883 bytes) and successfully loads via `xgb.Booster()` API
6. **Encoder Artifact**: `encoder.joblib` exists (6,271 bytes) and successfully unpickles via `joblib.load()` with 88 features
7. **Metadata Consistency**: `metadata.json` exists (9,354 bytes) and model version matches candidate (`v_20260905_203530`)
8. **Training Snapshot Integrity**: `training_snapshot.json` exists (172,169 bytes), version label matches, and snapshot ID (`9eb0badf-22c3-4ffe-9d0d-dfd2189de254`) matches `metadata.json` exactly
9. **Authorization**: Requires authenticated user with `role="admin"` or superuser status
10. **Atomic Promotion**: Deactivation of previous active models and activation of the candidate occurs in a single atomic database transaction

### Operational Decoupling Verification
- **Candidate Predictions**: `0` predictions exist for `v_20260905_203530` (Retraining did **NOT** trigger automatic prediction backfill).
- **Active Model Serving**: `v_20260902_122321` remains `is_active=True` with all `50,030` prediction records intact and serving production triage traffic undisturbed.

---

## 7. Full Verification Test Results

All verification suites were executed directly against the workspace environment. Zero tests failed.

| Test Suite | Command | Tests Run | Passed | Failed | Duration |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Django System Check** | `./venv/bin/python manage.py check` | 1 | 1 | 0 | 1.2s |
| **Retraining Flow & Safety Gate** | `./venv/bin/pytest apps/predictions/test_model_retraining_flow.py` | 10 | 10 | 0 | 22.5s |
| **Leakage Prevention Tests** | `./venv/bin/pytest ml_engine/training/test_no_leakage.py` | 4 | 4 | 0 | 9.2s |
| **Platform Unit & API Suite** | `./venv/bin/pytest tests/` | 125 | 125 | 0 | 51.3s |
| **App Domain & Quality Tests** | `./venv/bin/pytest apps/incidents/ apps/predictions/` | 83 | 83 | 0 | 10.4s |
| **Total Automated Tests** | — | **223** | **223** | **0** | **~94.6s** |

### Key Regression Assertions Verified:
- `test_01_retrain_task_handles_summary_dict_without_unpacking_error`: Celery signature mismatch resolved (single dict consumed).
- `test_02_retrain_task_failure_recording`: Task failures set `status=FAILED` and record traceback without crashing worker.
- `test_03_human_label_provenance_and_synthetic_exclusion`: Synthetic records are excluded from training targets.
- `test_04_dynamic_data_collection_and_human_increment`: Genuine non-synthetic human reviews increment training count by exactly 1; synthetic reviews do NOT increment count.
- `test_05_human_decision_overrides_heuristic_preserving_audit_provenance`: Human decision overrides heuristic while preserving original heuristic field in DB.
- `test_06_immutable_training_snapshot_generation`: Snapshot binds SHA256 hash, UUID list, schema versions, and provenance breakdown.
- `test_07_candidate_model_remains_inactive_after_creation`: Retraining creates inactive candidate without modifying active baseline.
- `test_08_activation_safety_gate_enforcement`: 10-point safety gate rejects non-admin, non-READY status, missing metrics, and missing/mismatched snapshot.
- `test_10_target_and_metadata_leakage_prevented`: Zero target or reviewer metadata fields enter feature encoder.

---

## 8. Candidate vs. Baseline Active Model Comparison

| Characteristic | Active Baseline (`v_20260902_122321`) | Candidate Model (`v_20260905_203530`) |
| :--- | :--- | :--- |
| **Status** | `ACTIVE` | `READY` (Candidate) |
| **Lifecycle State** | Serving active production triage | Staged; controlled promotion required |
| **Training Dataset** | Synthetic prototype cohort (909 rows) | Database eligible records (760 rows) |
| **Synthetic Simulation Exclusion** | Historical prototype artifact | **Strictly Excluded (150 synthetic records quarantined)** |
| **Operating Threshold** | `0.10` (Static baseline) | `0.15` (F2-optimal from 5-fold OOF) |
| **Scale Pos Weight** | ~4.0 | `4.0469` (Computed strictly from training fold) |
| **Test Recall (PSIF)** | ~0.92 | `0.9545` (21/22 positive incidents detected) |
| **Test Precision (PSIF)** | ~0.20 | `0.2165` |
| **Test F2 Score** | ~0.52 | `0.5676` |
| **Test ROC-AUC** | ~0.64 | `0.6843` |
| **Test PR-AUC** | ~0.38 | `0.4783` |
| **Immutable Snapshot** | Not recorded in DB | **Persisted (`training_snapshot.json`, SHA256 verified)** |
| **Provenance Tracking** | Monolithic counts | **7-way mutually exclusive DB provenance breakdown** |
| **Backfill Status** | 50,030 predictions in production | **0 predictions (Decoupled; explicit promotion)** |

---

## 9. Conclusion & Next Steps

1. **Controlled Retraining Pipeline Validated**: The Admin → Models → "Retrain Model" workflow is fully functioning, non-blocking, auditable, and resilient.
2. **Integrity Guardrails Active**: Synthetic simulation records are strictly quarantined and cannot dilute genuine human ground truth or supervise model training.
3. **Candidate Model Staged**: Candidate `v_20260905_203530` is safely stored in `READY` status. The active model `v_20260902_122321` continues serving incoming reports.
4. **Human Validation Readiness**: When genuine HSE safety officers submit incident reviews via `/api/incidents/<id>/review/`, the training pipeline will automatically prioritize real human ground truth and calculate true human-validation metrics.
