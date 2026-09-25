# Controlled Experimental Model Comparison Report
**Foresight PSIF Platform (OIL India Problem Statement 26165)**  
*Date: September 6, 2026*  
*Protocol: Controlled Multi-Source Candidate Training & Safety Gate Benchmark*

---

## 1. Executive Summary & Experimental Protocol

Under Problem Statement 26165, Foresight classifies high-severity precursors to prevent Serious Injuries and Fatalities (SIF). Because predictive safety models operate in high-consequence environments, model retraining must adhere to **zero masquerading**, **immutable snapshotting**, and **safety gate candidate isolation**.

### Core Governance Rules Enforced
1. **Zero Masquerading**: Synthetic dataset labels, simulated reviewer outputs, and application heuristics are strictly separated and never merged or substituted for real human Health, Safety & Environment (HSE) consensus ground truth.
2. **Safety Gate Isolation**: Newly trained candidate models are saved strictly in `READY` status with `is_active=False`. The active production inference model (`v_20260902_122321`) remains untouched and active.
3. **Immutable Provenance Snapshots**: Every candidate is linked to an immutable JSON snapshot on disk containing the exact row-level record IDs, raw data hashes, source composition, and class distributions.
4. **Authoritative Validation Basis**: Evaluation metrics reflect their true source — candidates trained on synthetic data display `SYNTHETIC DATASET EVALUATION`; candidates trained on heuristic proxies display `APPLICATION HEURISTIC EVALUATION`; genuine human validation displays `REAL HUMAN HSE VALIDATION`.

---

## 2. Candidate Model Specifications & Provenance

| Specification | Active Baseline Model | Candidate 1: Heuristic Proxy | Candidate 2: Synthetic Dataset | Candidate 3: Human Consensus | Candidate 4: Mixed Multi-Source |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Model Version Label** | `v_20260902_122321` | `v_20260905_203530` | `v_20260906_093529` | *Controlled Gate* | *Experimental Spec* |
| **Lifecycle Status** | **ACTIVE** | **READY (CANDIDATE)** | **READY (CANDIDATE)** | **INELIGIBLE** | **READY (CANDIDATE)** |
| **Active in Serving?** | **YES (`is_active=True`)** | **NO (`is_active=False`)** | **NO (`is_active=False`)** | **NO** | **NO** |
| **Training Source** | `HEURISTIC` | `HEURISTIC` | `SYNTHETIC` | `HUMAN` | `MIXED` |
| **Validation Basis** | `APPLICATION HEURISTIC EVALUATION` | `APPLICATION HEURISTIC EVALUATION` | `SYNTHETIC DATASET EVALUATION` | `NOT ESTABLISHED` (0 consensus cases) | `MIXED DATASET EVALUATION` |
| **Dataset / Snapshot Path** | Legacy Baseline (PostgreSQL) | `ml_engine/artifacts/v_20260905_203530/training_snapshot.json` | `ml_engine/artifacts/v_20260906_093529/training_snapshot.json` | N/A (Requires &ge; 20 verified rows) | `ml_engine/artifacts/mixed_snapshot.json` |
| **Dataset SHA-256 Hash** | N/A (Pre-gate baseline) | `be9f0a16bc202e85fa424f36f5dc53f46d13e5370ceed495f76770e10a22c586` | `d502d61e6847b2bdf70b378250363dbfa76466e4224dfb1d1358f4f676d32dcd` | N/A | Preserved multi-hash |
| **Total Labeled Records** | 761 | 760 | 1,500 (sampled from 50,000) | 149 individual reviews / 0 consensus | 2,260 |
| **Train / Test Split** | 646 / 115 (85% / 15%) | 646 / 114 (85% / 15%) | 1,275 / 225 (85% / 15%) | 0 / 0 | 1,921 / 339 |
| **Class Distribution (Pos / Neg)**| 152 / 609 (19.97% pos) | 150 / 610 (19.74% pos) | 704 / 796 (46.93% pos) | 63 / 86 (legacy tagged) | 854 / 1,406 (37.79% pos) |
| **Human Consensus Records** | 0 | 0 | 0 | **0 verified consensus cases** | 0 |
| **Heuristic Proxy Records** | 761 | 760 | 0 | 0 | 760 |
| **Synthetic Records** | 0 | 0 | 1,500 | 0 | 1,500 |
| **Excluded / Unlabelled Records** | 0 | 49,870 excluded | 0 excluded | 50,631 excluded | 48,520 excluded |
| **Data Quality Gate Status** | Pre-gate import | 760 Valid (0 Critical) | 1,500 Valid (0 Critical) | N/A | 2,260 Valid |

---

## 3. Head-to-Head Performance Evaluation

Evaluation was conducted under identical held-out split protocols (stratified 85% train / 15% test, 5-fold cross-validation on train for threshold selection, feature fusion of 768-dim frozen DistilBERT embeddings + 6-dim one-hot structured features).

| Metric | Active Serving Model (`v_20260902_122321`) | Heuristic Candidate (`v_20260905_203530`) | Synthetic Candidate (`v_20260906_093529`) | Delta (Heuristic vs Active) | Delta (Synthetic vs Active) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Validation Basis** | *Application Heuristic* | *Application Heuristic* | *Synthetic Dataset* | — | — |
| **Precursor Recall** | **0.9565** | **0.9545** | **0.9906** | -0.0020 | +0.0341 |
| **Precision** | **0.2018** | **0.2165** | **1.0000** | +0.0147 | +0.7982 |
| **F1 Score** | **0.3333** | **0.3529** | **0.9953** | +0.0196 | +0.6620 |
| **F2 Score ($F_2$)** | **0.5473** | **0.5676** | **0.9924** | **+0.0203** | **+0.4451** |
| **ROC-AUC** | **0.6215** | **0.6843** | **0.9999** | **+0.0628** | **+0.3784** |
| **PR-AUC** | **0.3742** | **0.4783** | **0.9999** | +0.1041 | +0.6257 |
| **Operating Threshold** | **0.10** | **0.15** | **0.50** | +0.05 | +0.40 |
| **True Positives ($TP$)** | 22 | 21 | 105 | -1 | +83 |
| **False Negatives ($FN$)** | 1 | 1 | 1 | 0 | 0 |
| **False Positives ($FP$)** | 87 | 76 | 0 | -11 | -87 |
| **True Negatives ($TN$)** | 5 | 16 | 119 | +11 | +114 |

---

## 4. In-Depth Empirical Analysis: Synthetic vs Heuristic Discrepancy

### 4.1 The Synthetic "Near-Perfect" Illusion
The synthetic candidate model (`v_20260906_093529`) achieves extraordinary, near-perfect test scores:
- **Precision:** 1.0000 (100.0%)
- **Recall:** 0.9906 (99.1%)
- **F2 Score:** 0.9924
- **ROC-AUC:** 0.9999
- **PR-AUC:** 0.9999

**Root Cause (Discovered via Dataset Validity Benchmark Suite):**
1. **Lexical Template Leakage:** As demonstrated in the benchmark suite, the 50,000 synthetic dataset was generated with structural boilerplate syntax:
   - 100% of narratives contain rigid templates: `"The observation was made at..."` (31.1%), `"The interacting condition was..."` (10.2%), `"Barrier finding:..."` (2.3%).
   - 138 lexical tokens have extreme class association ($p < 10^{-10}$).
   - The token `"Barrier finding:"` occurs almost exclusively in positive PSIF records, while `"Observation finding:"` marks negatives.
2. **Grouped vs Random Split Reconciliation:**
   - **Text TF-IDF Models:** Maintain an artificial **ROC-AUC of 1.0000** even under group-aware operational splits (`f"{site_area}_{activity}"`, 256 disjoint groups). This occurs because the generator inserted identical class-associated tokens uniformly across all operational groups, crossing train/test group boundaries.
   - **Structured Operational Baseline:** Models evaluated on non-target operational metadata alone (`activity`, `site_area`, `report_type`, `department`) achieve **ROC-AUC of 0.5399** (~0.5401 on random split; 0.5177 on grouped split). This confirms that operational metadata alone contains virtually zero predictive signal, and reconciles previous references to 0.5401 as the structured operational baseline.
3. **Engineered vs Real-World Precursor Signal:** In a real refinery or offshore drilling rig, incident narratives are unstructured, messy, hurried, and lack artificial barrier tags. The synthetic model has learned to exploit generative templates rather than true physical precursor mechanics.
4. **Integrity Finding:** Deploying Candidate 2 as a production model would create severe safety blind spots in real refinery operations. Candidate 2 is designated strictly as a **DEVELOPMENT / EXPERIMENTAL CANDIDATE**, suitable **only for architecture testing, pipeline verification, and scaling**, and must remain marked `SYNTHETIC DATASET EVALUATION`.

### 4.2 The Heuristic Baseline & Candidate
The Heuristic candidate model (`v_20260905_203530`) demonstrates:
- **High Precursor Recall:** 95.45% ($Recall = 0.9545$, with only 1 false negative out of 22 positive cases).
- **Moderate Precision:** 21.65%, resulting from the deliberate decision to lower the operating threshold to 0.15 to satisfy the F2-optimization criterion ($\beta = 2$, placing $5\times$ more weight on avoiding missed PSIFs than on avoiding false alarms).
- **ROC-AUC:** 0.6843 (an improvement of +0.0628 over the active baseline's 0.6215).
- **Real-World Characteristic:** Reflects the noisy, unverified nature of weak proxy labels derived from initial reporting severity fields before formal root-cause investigation.

---

## 5. Status of the Human Ground Truth Model

When `training_source="HUMAN"` is requested via the API (`POST /api/models/retrain/`), the platform executes the following validation:
1. Queries all incidents with `is_psif_human_label__isnull=False`.
2. Strictly excludes all heuristic labels, synthetic labels, and simulated reviewer outputs.
3. Checks if the number of eligible human consensus records meets the minimum sample threshold ($N \ge 20$).
4. Because the current database contains 149 individual reviews without verified dual-expert consensus (0 consensus cases), training raises a clean, non-crashing error:
   ```json
   {
     "error": "Insufficient human-reviewed records for training. Found 0 verified human consensus records (minimum 20 required)."
   }
   ```
5. **Zero Falsification:** Foresight strictly refuses to bootstrap or substitute heuristic data under a human validation banner.

---

## 6. Safety Gate Activation Verification

To prove that the safety gate prevents unauthorized promotion:
1. Both `v_20260905_203530` and `v_20260906_093529` are persisted in PostgreSQL with:
   - `status = 'READY'`
   - `is_active = False`
2. The production predictor continues to query:
   ```sql
   SELECT * FROM predictions_modelversion WHERE is_active = TRUE;
   ```
   which returns strictly `v_20260902_122321` (Active Serving Model).
3. The platform's 9-point safety gate in `apps/predictions/api_views.py` (`ModelActivateAPIView`) requires explicit administrator authentication, verified artifact integrity, threshold existence, and metric sufficiency before any candidate can be promoted.

---

## 7. Conclusion & Authoritative System State

1. **Active Serving Model Unchanged:** `v_20260902_122321` remains the operational active predictor.
2. **Candidate 1 (`v_20260905_203530`)**: Established as the official Heuristic development candidate ($F_2 = 0.5676$, $Recall = 0.9545$).
3. **Candidate 2 (`v_20260906_093529`)**: Established as the Synthetic development candidate ($F_2 = 0.9924$). It must remain tagged with `SYNTHETIC DATASET EVALUATION` and must **not** be promoted to production safety inference.
4. **Primary Path Forward**: Human HSE domain expert consensus reviews must be collected through the Foresight Review Queue (`/predictions/review/`) to accumulate genuine ground truth for the first Human-Validated PSIF model.
5. **Authoritative System Summary**:
   > A technically integrated, human-validation-ready SIH demonstration prototype whose real-world PSIF predictive validity remains to be established using genuine human-reviewed HSE data.

