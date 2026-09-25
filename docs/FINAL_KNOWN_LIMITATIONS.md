# Foresight PSIF Platform: Final Known Limitations & Disclosures

**Document Version:** 1.0 (Frozen Demo Release)  
**Status:** Mandatory Governance Document  
**Audience:** SIH Evaluators, Safety Directors, AI Auditors, Deployment Teams  

---

## 1. Foundational System Disclaimer

Foresight is an **AI-assisted safety-intelligence prototype** developed for engineering demonstration, architectural benchmarking, and concept validation. It is **not** an operationally certified safety system and has **not** been validated on human-reviewed operational Oil India Limited (OIL) data.

> **Operational Warning:**  
> This software must not be used as the sole basis for operational shut-in decisions, permit-to-work approvals, or regulatory compliance reporting without prior formal calibration, field verification, and blind validation against genuine enterprise historical datasets.

---

## 2. Epistemic & Methodological Limitations

### 1. PSIF Model Score Is Not an Actuarial Probability
- **Limitation:** The machine learning pipeline outputs a `psif_score` bounded between $0.0$ and $1.0$. This score reflects relative statistical resemblance between the semantic embedding of an incident narrative and historical training precursor patterns.
- **Boundary:** It does **not** represent an actuarial or frequentist probability of death or injury. It does not measure event frequency per million exposure hours.
- **Mitigation in Code:** The term "probability" has been eradicated from user-facing surfaces and replaced with **PSIF Model Score**. Explanatory banners on every view remind operators: *"Model score is an uncalibrated relative ranking score, not a physical probability."*

### 2. IOGP Life-Saving Rule Matching Is Deterministic Keyword Alignment
- **Limitation:** The IOGP tagging engine utilizes deterministic keyword patterns and regex token matchers to associate incidents with one of the 9 IOGP Life-Saving Rules.
- **Boundary:** A rule match does **not** prove a procedural violation, negligence, or culpability. It indicates thematic relevance to a barrier domain.
- **Mitigation in Code:** System surfaces use the phrase **"IOGP Rule Match"** and never "Rule Violation" or "Confirmed Breach".

### 3. SHAP Feature Attributions Are Not Physical Causes
- **Limitation:** Explainability panels display TreeSHAP feature contributions indicating which tokens or structured fields influenced XGBoost tree branch decisions.
- **Boundary:** High SHAP contribution indicates statistical importance to the classifier; it does **not** establish root cause, systemic organizational failure, or causal mechanics.
- **Mitigation in Code:** Explanations label these factors as **"Model Influencing Factors"** with an explicit notice: *"SHAP values reflect model feature importance, not physical or organizational causality."*

### 4. Vector Semantic Similarity Does Not Establish Duplication or Shared Causality
- **Limitation:** Incident similarity relies on cosine distance between 768-dimensional BERT embeddings.
- **Boundary:** Two incidents with $92\%$ cosine similarity may share similar phrasing or equipment names while having completely distinct geological, mechanical, or operational root causes. Similarity does not indicate a duplicate ticket.
- **Mitigation in Code:** The similarity panel is titled **"Semantically Similar Narratives"** with disclosures warning against assuming causal identity.

### 5. Cross-Site Aggregates Reflect Reporting Behavior, Not True Safety Performance
- **Limitation:** Cross-site comparison matrices tabulate recorded incident reports across operational regions (e.g., Duliajan, Digboi, Moran).
- **Boundary:** A site with high reported observations may possess a world-class reporting culture where minor near-misses are proactively documented, whereas a site with low counts may suffer from under-reporting.
- **Mitigation in Code:** Foresight strictly forbids "Most Unsafe Site" rankings, presenting neutral denominators: *"Observed Safety-Signal Volume"* and *"Reporting Rate"*.

### 6. Historical Recurrence Is Retrospective, Not Predictive
- **Limitation:** The recurrence engine groups incidents sharing normalized site, activity, and hazard profiles over rolling 30/90/365-day windows.
- **Boundary:** Recurrence reflects historical clustering of past reports; it does not forecast future incident probability or catastrophic risk.
- **Mitigation in Code:** Labeled strictly as **"Historical Cluster Frequency"**.

### 7. Synthetic Data Artifacts
- **Limitation:** The active prototype database incorporates synthetically augmented incident narratives designed to simulate low-frequency, high-severity precursors.
- **Boundary:** Synthetic narratives may exhibit stylistic uniformities or vocabulary distributions that differ subtly from raw field notes.
- **Mitigation in Code:** All synthetic records carry `is_synthetic = True` and explicit provenance badges (`psif_label_source = SYNTHETIC`). Synthetic reviews are marked with `is_synthetic_adjudication = True`.

---

## 3. Human Review Independence

1. **AI Predictions Are Decision Support, Not Ground Truth:** Final determinations of PSIF classification must rest with certified HSE professionals.
2. **Immutability of Historical AI Outputs:** When a human safety expert adjudicates an incident, the human decision is recorded separately in the audit trail. The original AI prediction score and model version are permanently preserved for drift tracking and regulatory auditability.
