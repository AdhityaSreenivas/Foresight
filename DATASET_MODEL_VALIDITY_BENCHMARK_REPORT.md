# Foresight PSIF Platform — Dataset & Model Validity Benchmark Report
**OIL India Problem Statement 26165**  
*Document Version: 1.0 | Evaluation Date: 2026-09-06T09:29:00.318631+00:00*

---

## Executive Summary

This report establishes the empirical validity, leakage vulnerability, and generalization integrity of benchmark datasets within the Foresight PSIF platform.

Key findings:
1. **100k Dataset Availability**: Inspected repository and media storage; **100k dataset is NOT present** in the environment. All benchmark analyses were performed on the verified **50,000 incident synthetic dataset** (`final_50000_dataset.jsonl`, 43,667,279 bytes) and the **heuristic training dataset** (760 rows in PostgreSQL).
2. **Dataset Size & Benchmark Sampling**: The synthetic dataset contains exactly **50,000 rows**. For computational tractability, benchmark analyses were evaluated on a stratified sample of **5,000 rows** (`seed=42`), while key dataset-wide statistics (boilerplate, schema integrity, and baselines) were also verified across the full 50,000 rows.
3. **Template & Label Leakage**: The 50k synthetic dataset exhibits pervasive **boilerplate sentence templates** (`"The observation was made at..."` in 31.08% of sample records and 31.61% of full 50k records; overall boilerplate present in 100% of narratives).
4. **Random vs Grouped Split Reconciliation**:
   - **Text TF-IDF Models**: Achieve an artificial **ROC-AUC of 1.0000** under both random splits and group-aware operational splits (`f"{site_area}_{activity}"`, 256 disjoint groups). This 1.0000 performance does **not** reflect generalized risk comprehension; rather, it is driven by **138 class-associated lexical tokens** (e.g. `"Barrier finding:"`, `"incorrect restoration"`, `"unexpected start"`) that the synthetic generator inserted uniformly across all operational groups, leaking label shortcuts across train/test group boundaries.
   - **Structured Operational Baselines**: When evaluated on non-target operational metadata alone (`activity`, `site_area`, `report_type`, `department`), models achieve **ROC-AUC of 0.5399** (~0.5401 on random split; 0.5177 on grouped split). This confirms that operational metadata alone contains virtually no predictive signal, and explains previous documentation references to 0.5401 as the structured operational baseline.
5. **Active Model Integrity**: The active serving predictor (`v_20260902_122321`) **remains untouched and active**.

---

## 1. Dataset Inventory & Schema Integrity

### 1.1 Evaluated Dataset Inventory
| Dataset Name | File Path | Total File Rows | Benchmark Analyzed Rows | Sampling Method & Seed | Availability | Primary Usage Tier |
|:---|:---|:---:|:---:|:---|:---:|:---|
| **Synthetic 50k Dataset** | `media/uploads/182250b2-dd76-4506-826a-dd6da0c457a3/final_50000_dataset.jsonl` | **50,000** | **5,000** (sample) & **50,000** (full) | Stratified random (`seed=42`) | **Available** (43.7 MB) | Pretraining / Stress Testing |
| **Heuristic DB Incidents** | PostgreSQL DB (`is_psif_heuristic_label`) | 760 | 760 | Full census | **Available** | Weak Supervision Development |
| **100k Benchmark Dataset** | Searched filesystem & media storage | 0 | 0 | N/A | **NOT AVAILABLE** | N/A |
| **Genuine Human Ground Truth** | HSE Review Queue consensus | 0 | 0 | N/A | Pending Expert Consensus | Formal Regulatory Validation |

### 1.2 Schema Integrity Analysis (Synthetic 50k Dataset)
* **Dataset File Row Count**: **50,000** (43,667,279 bytes)
* **Benchmark Sample Size**: **5,000** rows (Stratified uniform random sampling without replacement, `seed=42`)
* **Duplicate Record IDs**: 0
* **Empty Narratives**: 0
* **Exact Duplicate Narratives**: 0
* **Class Distribution (Benchmark Sample)**:
  - Positive SIF Precursor (`sif_label=1`): **3,013** (60.26%)
  - Negative Non-SIF (`sif_label=0`): **1,987** (39.74%)
  - Missing/Other: **0**
* **Class Distribution (Full 50,000 Census)**:
  - Positive SIF Precursor (`sif_label=1`): **30,327** (60.65%)
  - Negative Non-SIF (`sif_label=0`): **19,673** (39.35%)

---

## 2. Duplication & Template Analysis

Synthetic incident generators often combine fixed clause skeletons. Our n-gram and sentence prefix analysis reveals heavy structural repetition:

### 2.1 Top Repeated Boilerplate Patterns
| Boilerplate Skeleton | Occurrences (5k Sample) | Prevalence (% of Sample) | Occurrences (Full 50k) | Prevalence (% of Full 50k) | Crosses Train/Test? |
|:---|:---:|:---:|:---:|:---:|:---:|
| `the observation was made at` | 1,554 | 31.08% | 15,806 | 31.61% | **YES** |
| `the interacting condition was` | 511 | 10.22% | 5,428 | 10.86% | **YES** |
| `potential consequence was` | 264 | 5.28% | 2,685 | 5.37% | **YES** |
| `the reported activity was` | 208 | 4.16% | 2,251 | 4.50% | **YES** |
| `the task context was` | 222 | 4.44% | 2,221 | 4.44% | **YES** |
| `barrier finding:` | 115 | 2.30% | 1,098 | 2.20% | **YES** |
| `the next step was to` | 47 | 0.94% | 544 | 1.09% | **YES** |
| `risk: unexpected` | 42 | 0.84% | 430 | 0.86% | **YES** |

### 2.2 Template Repetition Assessment
* **Boilerplate Detected**: **True**
* **Repetition Severity**: **HIGH** (Phrases like `"the observation was made at"` appear in over 31% of records; 100% of narratives contain rigid generative template skeletons)
* **Implication**: Because identical phrasing templates cross both train and test partitions under random and grouped splits, high text classification performance reflects template memorization rather than real safety precursor discernment.

---

## 3. Class-Associated Lexical Leakage

Tokens occurring near-exclusively in either the positive or negative class act as shortcut features:

### 3.1 Suspicious Class-Associated Tokens
| Token | Total Occurrences (5k) | Positive Count | Negative Count | Positive Rate | Odds Ratio | Category |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| `adequately` | 97 | 97 | 0 | 100.0% | 66.10 | Synthetic Generator Artifact |
| `damaged` | 40 | 40 | 0 | 100.0% | 26.73 | Synthetic Generator Artifact |
| `obstructed` | 114 | 114 | 0 | 100.0% | 78.14 | Synthetic Generator Artifact |
| `complete` | 25 | 0 | 25 | 0.0% | 0.00 | Synthetic Generator Artifact |
| `fatigue` | 20 | 20 | 0 | 100.0% | 13.28 | Synthetic Generator Artifact |
| `remains` | 84 | 84 | 0 | 100.0% | 56.98 | Synthetic Generator Artifact |
| `entrapment` | 36 | 36 | 0 | 100.0% | 24.03 | Synthetic Generator Artifact |
| `allow` | 92 | 0 | 92 | 0.0% | 0.00 | Synthetic Generator Artifact |
| `entered` | 110 | 110 | 0 | 100.0% | 75.29 | Synthetic Generator Artifact |
| `management` | 17 | 17 | 0 | 100.0% | 11.27 | Synthetic Generator Artifact |

* **Leakage Conclusion**: Detected **138 tokens** in the 5k sample (and **158 tokens** in the full 50k dataset) with >95% exclusive class association. This is definitive evidence of template-directed synthetic generation.

---

## 4. Generalization Benchmark: Random vs Group-Aware Split

To evaluate whether models learn transferable safety principles or memorize scenario templates, we compared identical TF-IDF and structured models across:
1. **Random Stratified Split**: Uniform 80/20 partition across incidents (4,000 train / 1,000 test).
2. **Group-Aware Split**: Partitioned by operational category (`f"{site_area}_{activity}"`, 256 disjoint groups, train/test group overlap = 0; 4,029 train / 971 test).

### 4.1 Comparative Baseline Performance
| Model Pipeline | Split Method | Accuracy | Precision | Recall | F1 Score | F2 Score | ROC-AUC | PR-AUC |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Text TF-IDF + Logistic Reg** | Random (80/20) | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | **1.0000** | 1.0000 |
| **Text TF-IDF + Linear SVM** | Random (80/20) | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | **1.0000** | 1.0000 |
| **Structured Only (One-Hot)** | Random (80/20) | 0.5270 | 0.6255 | 0.5373 | 0.5781 | 0.5529 | **0.5399** | 0.6384 |
| **Combined Text + Structured** | Random (80/20) | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | **1.0000** | 1.0000 |
| **Text TF-IDF + Logistic Reg** | **Grouped Split** | 0.9990 | 0.9983 | 1.0000 | 0.9992 | 0.9997 | **1.0000** | 1.0000 |
| **Structured Only (One-Hot)** | **Grouped Split** | 0.5242 | 0.6180 | 0.5612 | 0.5882 | 0.5717 | **0.5177** | 0.6064 |
| **Combined Text + Structured** | **Grouped Split** | 0.9979 | 0.9966 | 1.0000 | 0.9983 | 0.9993 | **1.0000** | 1.0000 |

### 4.2 Grouped vs Random Reconciliation Findings
* **Why Text TF-IDF achieves 1.0000 on Grouped Split**: The synthetic generation process distributed identical template phrases (`"the observation was made at"`, `"the interacting condition was"`) and 138 class-associated vocabulary items across all 256 operational groups. As a consequence, holding out entire site areas and activities fails to hide the generator artifacts, allowing text models to achieve near-perfect discrimination across group boundaries.
* **Why Structured Operational Features achieve 0.5401 (0.5399)**: When text shortcuts are removed and only non-target operational metadata is used (`activity`, `site_area`, `report_type`, `department`), models achieve **ROC-AUC = 0.5399** on random split and **0.5177** on grouped split. Operational metadata alone is near random guessing (~0.52–0.54), confirming that previous report references to `0.5401` documented the structured operational baseline.

---

## 5. Counterfactual Sensitivity Evaluation

Minimal pair counterfactual testing measures whether the active serving model (`v_20260902_122321`) responds to safety-critical precursor changes:

| Test ID | Hazard Domain | PSIF Variant Score | Control Variant Score | Score Delta | Correct Behavior |
|:---|:---|:---:|:---:|:---:|:---:|
| `CF_01_FALL_PROTECTION` | Working at Height | 0.5679 | 0.2634 | +0.3045 | **PASSED** |
| `CF_02_PRESSURE_ISOLATION` | Energy Isolation | 0.1430 | 0.1058 | +0.0372 | **FAILED** |
| `CF_03_TRENCH_EXCAVATION` | Excavation | 0.2230 | 0.2256 | -0.0026 | **FAILED** |
| `CF_04_CONFINED_SPACE` | Confined Space | 0.1861 | 0.2816 | -0.0955 | **FAILED** |
| `CF_05_CRANE_LIFTING` | Lifting Operations | 0.5328 | 0.5047 | +0.0280 | **FAILED** |

* **Counterfactual Accuracy**: **20.0%** (1 / 5 pairs passed)
* **Precursor Sensitivity Verdict**: **POOR** (Active serving model is insufficiently sensitive to subtle control-barrier state distinctions in minimal narrative pairs).

---

## 6. Hard Negative Analysis

Hard negatives represent routine or hazardous work where safety barriers prevented an exposure pathway:
* **Benchmark Sample (5k)**: **64 / 1,987 = 3.2%**
* **Full 50,000 Census**: **648 / 19,673 = 3.29%**
* **Negative Diversity Assessment**: **SPARSE**
* **Engineering Finding**: **Hard-negative diversity is insufficient for strong real-world validation.**

---

## 7. Adversarial Robustness

Adversarial testing probes model behavior on empty narratives, keyboard mash, and benign safety reports:
* **Total Tests Executed**: 10
* **Passed (Score < 0.50)**: 6
* **Pass Rate**: **60.0%**
* **Robustness Assessment**: **VULNERABLE** (Colloquial hazard words in benign inspections or garbled characters can trigger false precursor alarms).

---

## 8. Foresight Model Comparison: Active Baseline vs Candidates

| Evaluation Metric | Simple Text Baseline (TF-IDF + LR) | Active Serving Model (`v_20260902_122321`) | Heuristic Candidate (`v_20260905_203530`) | Synthetic Candidate (`v_20260906_093529`) |
|:---|:---:|:---:|:---:|:---:|
| **Training Source** | Synthetic TF-IDF | `HEURISTIC` | `HEURISTIC` | `SYNTHETIC` |
| **Validation Basis** | Synthetic Text Split | `APPLICATION HEURISTIC EVALUATION` | `APPLICATION HEURISTIC EVALUATION` | `SYNTHETIC DATASET EVALUATION` |
| **Lifecycle Status** | Baseline | **ACTIVE** | **READY (CANDIDATE)** | **READY (CANDIDATE)** |
| **Active in Serving (`is_active`)** | NO | **YES** | **NO** | **NO** |
| **Held-Out Test Precision** | 1.0000 | 0.2018 | 0.2165 | 1.0000 |
| **Held-Out Test Recall** | 1.0000 | 0.9565 | 0.9545 | 0.9906 |
| **Held-Out Test F1** | 1.0000 | 0.3333 | 0.3529 | 0.9953 |
| **Held-Out Test F2** | 1.0000 | 0.5473 | 0.5676 | 0.9924 |
| **Held-Out Test ROC-AUC** | 1.0000 | 0.6215 | 0.6843 | 0.9999 |
| **Held-Out Test PR-AUC** | 1.0000 | 0.3742 | 0.4783 | 0.9999 |
| **Operating Threshold** | 0.50 | 0.10 | 0.15 | 0.50 |

---

## 9. Definitive Dataset Suitability Verdict

Based on empirical evidence, we issue formal suitability verdicts across all development tiers:

| Development Tier | Suitability Verdict | Formal Engineering Rationale |
|:---|:---:|:---|
| **Pipeline Development** | **YES** | Dataset schema and format are well-structured for code development and pipeline integration. |
| **Stress Testing & Scaling** | **YES** | Scale (50,000 rows, 43.7 MB) allows high-throughput stress testing of ingestion workers, Celery queues, and databases. |
| **Algorithmic Benchmarking** | **YES** | Suitable for algorithmic benchmarking provided synthetic template leakage is explicitly accounted for. |
| **Final Real-World Validation** | **NO** | **NOT SUITABLE** for final real-world PSIF predictive validation. Contains synthetic template artifacts and non-human labels. Real-world predictive validity requires genuine human HSE domain consensus. |

### Recommendation Summary
> **Suitable for synthetic development, architecture testing, and stress testing. Not suitable as the sole evidence of real-world PSIF predictive validity.**

---

## 10. Verification Audit & Safeguards

1. **Active Model Unchanged**: Active version `v_20260902_122321` remains untouched in status and weights (`is_active=True`).
2. **Deterministic Reproducibility**: All benchmark sampling and evaluations are fixed to `seed=42`.
3. **Leakage Prevention**: All 18 forbidden target-derived fields were excluded from baseline features.
4. **Authoritative Full-Suite Test Result**:
   ```text
   OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE ./venv/bin/pytest -q
   170 passed, 5 warnings in 53.98s
   ```
5. **Canonical System Characterization**:
   > A technically integrated, human-validation-ready SIH demonstration prototype whose real-world PSIF predictive validity remains to be established using genuine human-reviewed HSE data.

