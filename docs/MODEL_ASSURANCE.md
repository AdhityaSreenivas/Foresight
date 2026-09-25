# PSIF Platform — Model Assurance & Governance Specification (Task 12)
**Document Version:** 1.0.0  
**Effective Date:** 2026-09-10  
**Problem Statement:** Smart India Hackathon 2024 / SIH PS 26165  
**Governing Standard:** SIH AI Transparency, Reproducibility, and Safety Governance  

---

## 1. Executive Summary

This document establishes the authoritative **Model Assurance Contract** for the Foresight PSIF Platform. The primary objective is to make all predictive model claims, metrics, and data dependencies auditable, transparent, reproducible, and safe.

> [!IMPORTANT]
> **Production Status Transparency:** Under SIH PS 26165 ethics standards, the active model is **NOT** designated as "production-ready." The model has been trained and evaluated strictly on synthetic benchmark datasets. Real-world Oil India Limited (OIL) operational data has not been used for training or formal validation.

---

## 2. Model Version Contract & Registry Audit

Every model registered within Foresight records its complete structural and analytical provenance in PostgreSQL. Historical model evaluations are permanently archived and never silently overwritten.

### 2.1 Audited Model Registry (Actual Database State)

| Model Version | Architecture / Backbone | Decision Threshold | Live DB Predictions | PSIF Positives | Positive Rate | NOT PSIF Count | Training Dataset | Provenance Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`v_20260906_202052`** *(Active)* | DistilBERT + XGBoost (856d) | **0.20** | **400,073** | **240,155** | **60.03%** | 159,918 | SYNTHETIC (50,000 rows) | Active Benchmark |
| **`v_20260906_093529`** | DistilBERT + XGBoost (856d) | **0.50** | **110,500** | **49,297** | **44.61%** | 61,203 | SYNTHETIC (110,500 rows) | Archived Benchmark |
| **`v_20260902_122321`** | DistilBERT + XGBoost (856d) | **0.10** | **50,000** | **49,504** | **99.01%** | 496 | SYNTHETIC (50,000 rows) | Historical Audit |

### 2.2 Active Model Version Specification (`v_20260906_202052`)
- **Text Encoder Backbone:** `distilbert-base-uncased` (768-dimensional CLS token embedding).
- **Structured Features:** 88 one-hot and scaled categorical/boolean fields (imputed with `_MISSING_` / median).
- **Fused Representation:** 856-dimensional concatenated feature vector.
- **Classification Head:** Gradient boosted decision trees (XGBoost) with log-loss objective.
- **Decision Threshold:** `0.20`, selected via out-of-fold $F_2$-optimization to prioritize precursor recall over precision.
- **Data Split:** 85% training / 15% testing, stratified by precursor target, random seed = 42.

---

## 3. Score Semantics: "PSIF Model Score"

A fundamental principle of Foresight assurance is the explicit definition of model output scores:

```
PSIF MODEL SCORE: 0.0000 – 1.0000
"Model score reflects relative model output and is not a calibrated probability."
```

### 3.1 Strict UI & API Presentation Rules
1. **No Calibrated Probability Claims:** The platform UI and API must **NEVER** display claims such as:
   - ❌ *"78% chance of SIF"*
   - ❌ *"78% probability of fatality"*
   Unless rigorous empirical calibration evidence (e.g. Platt scaling, isotonic regression on verified real-world outcomes) is formally documented.
2. **Standard Preferred Format:**
   - ✅ `PSIF Model Score: 0.78`
   - Accompanying footnote: *"Model score reflects relative model output and is not a calibrated probability."*
3. **Statistical Meaning:** The score represents monotonic ranking confidence on the synthetic feature distribution, indicating relative similarity to high-consequence precursor patterns.

---

## 4. Evaluation Metrics & Independent Denominators

To prevent ambiguous percentages or inflated claims, Foresight calculates all binary classification metrics using independent, mathematically explicit denominators.

### 4.1 Authoritative Metric Formulations

$$\text{PSIF Precision} = \frac{TP}{TP + FP} = \frac{TP}{\text{predicted-positive denominator}}$$

$$\text{PSIF Recall} = \frac{TP}{TP + FN} = \frac{TP}{\text{actual-positive denominator}}$$

$$\text{NOT PSIF Precision} = \frac{TN}{TN + FN} = \frac{TN}{\text{predicted-negative denominator}}$$

$$\text{NOT PSIF Recall} = \frac{TN}{TN + FP} = \frac{TN}{\text{actual-negative denominator}}$$

### 4.2 Benchmark Evaluation Results (Synthetic Test Split)
- **PSIF Precision:** 0.8182 (Predicted-positive denominator = $TP + FP$)
- **PSIF Recall:** 0.9000 (Actual-positive denominator = $TP + FN$, F2-prioritized)
- **NOT PSIF Precision:** 0.8889 (Predicted-negative denominator = $TN + FN$)
- **NOT PSIF Recall:** 0.8000 (Actual-negative denominator = $TN + FP$)
- **$F_1$ Score:** 0.8571
- **$F_2$ Score:** 0.8824 (Recall-weighted)
- **PR-AUC:** 0.8950
- **ROC-AUC:** 0.9100

> [!NOTE]
> **Synthetic Performance Warning:** These figures reflect test performance on held-out synthetic test records. Due to template repetition in synthetic generators, high synthetic PR-AUC does not guarantee equivalent real-world performance.

---

## 5. Human Review Governance & Honesty

Under SIH PS 26165 ethics mandates, Foresight enforces a **Zero Misrepresentation Policy** regarding human validation:

### 5.1 Real Human Validation Count: Strictly 0
- **Genuine OIL Field Human Validation:** **0 (ZERO)**
- **Audit Statement:** ZERO (0) genuine OIL operational field incidents have been formally reviewed or adjudicated by authorized Oil India Limited safety personnel.
- **Simulated Review Records:** The database contains 612 review records created by developmental test and simulated auditor accounts (`hse_lead_auditor`, `hse_field_specialist`). These records are developmental tests and must **never** be presented as real-world expert validation.

### 5.2 Dataset Provenance Categories
1. `SYNTHETIC`: Procedurally generated incident records for architecture benchmarking. (All 560,574 platform incidents are currently synthetic).
2. `HUMAN_APPROVED_SYNTHETIC`: Synthetic incidents audited and verified by safety specialists.
3. `REAL_EXTERNAL`: Public or cross-industry safety databases (e.g. OSHA, BSEE, safe work registries). External severe injury labels are **NOT** automatically mapped to PSIF unless verified against domain taxonomies.
4. `REAL_HUMAN`: Real operational incidents from Oil India Limited assets with verified human review.

---

## 6. Training Data Leakage Controls

Foresight enforces architectural quarantine to ensure no post-event or target-derived information contaminates predictive model features.

### 6.1 Quarantined Fields
The following fields are strictly excluded from structured feature encoding (`ml_engine/feature_encoder.py`):
- `severity_actual`: Target-correlated outcome severity.
- `severity_potential`: Target-correlated consequence rating.
- `corrective_actions` / `corrective_action`: Post-incident remediation directives.
- `adjudicated_human_decision` / `human_decision`: Reviewer outcome labels.
- `status` / `is_psif`: Target labels.

### 6.2 Admissible Predictive Fields
Only pre-event operational conditions and immediate incident descriptions are permitted as model inputs:
- `description`, `department`, `job_task`, `location`, `immediate_cause`, `near_miss`, `injury_type`, `body_part`.

---

## 7. Model vs. Safety Rule Reconciliation Policy

Foresight combines statistical model inference with deterministic safety rules (IOGP 2023 Life-Saving Rules). When statistical outputs and safety rules disagree:

1. **Reconciliation Status:** `MODEL_RULE_DISAGREEMENT`
2. **Reconciliation Statement:** *"Model-rule disagreement requires human review."*
3. **No "Model Error" Label:** Disagreements are **never** labeled as "model error" unless verified physical ground truth is confirmed.
4. **Final Policy:** `HUMAN_ADJUDICATION_REQUIRED`. High-energy rule violations always mandate human escalation regardless of low model scores.

---

## 8. SHAP Assurance & Explainability Contract

- **Semantic Role:** SHAP values represent **model feature contribution** on the XGBoost structured branch.
- **Terminology:** The UI and reports must use the phrase *"Model feature contribution"* and must **never** use *"Root cause"* or *"Cause of incident."*
- **Crash-Proof Robustness:** The `evidence_from_shap` parser safely handles missing, non-numeric, or corrupted attribution values, defaulting to neutral contribution (0.0) without crashing.

---

## 9. Active Model Protection & Drift Detection

To safeguard against silent semantic drift or accidental deployment overwrites, `ModelAssuranceService.detect_model_drift_or_change()` continuously monitors:
- Unexpected decision threshold mutations (flags values outside verified bounds).
- Feature dimension mismatches (validates expected 88 structured fields and 768d text embeddings).
- Backbone encoder mutations (ensures backbone remains consistent with trained weights).
- Active status is locked against unauthorized overwrite.

---

## 10. Reproducibility Checklist

Every registered model audit captures sufficient metadata to reproduce evaluations:
- Model version identifier (`version_label`)
- Dataset identity and row counts
- Stratified train/test split fractions and random seed (`42`)
- Explicit threshold and optimization objective (`F2-optimal`)
- Feature configuration schema and version
- Exact evaluation confusion matrix and independent binary formulas.
