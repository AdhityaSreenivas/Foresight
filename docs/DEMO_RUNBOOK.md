# Foresight PSIF Platform: Demonstration Runbook

**Document Version:** 1.0 (Frozen Demo Release)  
**Target Audience:** Engineering Evaluators, HSE Demonstration Leads, System Demonstrators  
**Intended Context:** Prototype Demonstration for SIH Evaluation  

---

## 1. System Startup & Verification

### Prerequisites
- macOS or Linux with Python 3.12+ (tested on Python 3.14)
- Redis server installed and running on default port `6379`
- Active Python virtual environment (`./venv`)

### Exact Startup Commands

```bash
# Terminal 1: Start Redis
brew services start redis  # or: redis-server

# Terminal 2: Verify Database Migrations & Static Files
cd /Users/sas/Developer/prototype_165
./venv/bin/python manage.py migrate
./venv/bin/python manage.py collectstatic --noinput

# Terminal 3: Start Celery Worker (Optional for batch ingestion demo)
./venv/bin/celery -A config worker --loglevel=info

# Terminal 4: Start Django Web Application Server
./venv/bin/python manage.py runserver 127.0.0.1:8000
```

### Accessing the Web Application
- **URL:** `http://127.0.0.1:8000/`
- **Default Superuser:** `admin`
- **Password:** `Admin1234!`

---

## 2. Recommended Demonstration Incident

For the primary demonstration walkthrough, use Incident ID:  
`3951f0c2-555e-4735-8663-8a3014c243ce`  
(or navigate from the Incident Queue to the top prioritized PSIF candidate).

**Incident Characteristics:**
- **Narrative:** High-pressure line rupture during well testing at Duliajan drilling rig; worker exposed within 3 meters; high-pressure bleed valve was bypassed without secondary isolation.
- **PSIF Model Score:** 0.850 (High Precursor Signal)
- **Classification:** `PSIF` (PSIF Pathway Open)
- **Matched IOGP Rule:** Safe Mechanical Lifting / Energy Isolation
- **Evidence:** High pressure energy (>3000 psi), worker line-of-fire exposure, bypassed isolation valve.

---

## 3. Step-by-Step Demonstration Flow

Follow this structured, 16-step narrative sequence during demonstration:

### Step 1: Executive Dashboard (`/`)
- **Action:** Open `http://127.0.0.1:8000/`.
- **Show:** The top 6 KPI metric cards displaying live enterprise figures:
  - Total Incidents (~561,351)
  - Prediction Eligible (~558,087)
  - Insufficient Evidence (~2,514)
  - PSIF Candidates (~345,329)
  - NOT PSIF (~212,758)
  - PSIF Prediction Rate (~61.88%)
- **Show:** Local Recurring Patterns and Cross-Site Signals widgets loading quickly (<500ms).
- **Explain:** "The dashboard provides high-level situational awareness across thousands of field observations, immediately segregating records with insufficient evidence from prediction-eligible cases."

### Step 2: Open Representative Incident Detail (`/incidents/<id>/`)
- **Action:** Click into the representative high-pressure line incident (`3951f0c2-555e-4735-8663-8a3014c243ce`).
- **Show:** The unified breadcrumbs, incident metadata, and side-by-side analytical panels.

### Step 3: Explain the PSIF Model Score
- **Action:** Point to the PSIF Model Score gauge (0.850).
- **Explain (Crucial Script):**  
  *"Notice the terminology: this is explicitly labeled 'PSIF Model Score', not a probability. It is an uncalibrated ranking score derived from the active XGBoost model that compares the semantic features of this event against historical precursor patterns. It does not claim that a fatality had an 85% probability of occurring."*

### Step 4: Explain "Why PSIF" / "Why NOT PSIF" Justification
- **Action:** Scroll to the "Why PSIF Reasoning Engine" breakdown.
- **Show:** The 8-point evidentiary tree:
  1. Energy Source: Pressurized gas line (>3000 psi)
  2. Worker Exposure: Operator in line of fire (<3m)
  3. Barrier Failure: Bleed valve bypassed
  4. Plausible Consequence: Fatal strike or blast trauma
  5. Textual Evidence: Direct quoted phrase from technician narrative
  6. Model Contribution: Top SHAP feature contributions
  7. Rule Match: IOGP Energy Isolation
  8. Reconciliation: Concordance between rule and model

### Step 5: Highlight Extracted Evidence & Quotes
- **Action:** Point to the extracted verbatim quote highlighting the bypassed valve.
- **Explain:** "Foresight does not hallucinate facts. Every assertion in the justification is directly anchored to specific textual excerpts in the original source report."

### Step 6: IOGP Life-Saving Rule Match
- **Action:** View the IOGP Rule tag badge.
- **Explain (Crucial Script):**  
  *"The system tags this as an IOGP Rule Match for Energy Isolation based on deterministic vocabulary mapping. We explicitly distinguish an IOGP Match from an IOGP Violation: matching identifies domain relevance, not legal or regulatory culpability."*

### Step 7: Control-Linked Corrective Actions
- **Action:** View the "Recommended Actions" panel.
- **Show:** The recommended action: "Conduct mandatory secondary isolation audit and independent verification prior to pressurization."
- **Explain:** "Notice that this action is directly derived from the identified control failure. The system does not emit generic safety slogans. Furthermore, action generation is strictly downstream—it never feeds backward into the incident classification."

### Step 8: Vector Semantic Similarity Panel
- **Action:** View the "Semantically Similar Incidents" widget.
- **Show:** The top 3 historical incidents across other facilities with similar energy and barrier characteristics.
- **Explain:** "Semantic similarity allows safety leads to see if identical operational conditions have appeared elsewhere, without claiming that the incidents share the same root cause."

### Step 9: Historical Recurrence Signal
- **Action:** Point to the Recurrence Indicator.
- **Explain:** "Recurrence reflects historical clustering of similar reports in our database. It assists audit prioritization but is never claimed as a predictive forecast of future events."

### Step 10: Cross-Site Safety Signals (`/dashboard/cross-site/`)
- **Action:** Click "Cross-Site Intelligence" in the top navigation.
- **Show:** The normalized site comparison table, IOGP cross-tabulation matrix, and hazard distribution heatmap across Duliajan, Digboi, Moran, and other operating regions.
- **Explain (Crucial Script):**  
  *"Foresight displays safety signal volume normalized by observed reporting denominators. We strictly avoid misleading 'most unsafe site' leaderboards, because raw report counts often reflect strong safety reporting cultures rather than poor safety performance."*

### Step 11: Barrier Intelligence (`/barriers/`)
- **Action:** Click "Barrier Intelligence" in the top navigation.
- **Show:** The 9 IOGP Life-Saving Rule cards, showing Matched Observations, PSIF-Linked Observations, and Affected Sites.
- **Explain:** "These metrics track barrier-related narrative matches. Notice we do not display unsupported 'barrier failure percentages' or 'control health rates', which would be unscientific given reporting biases."

### Step 12: Human Review Workbench (`/predictions/review/`)
- **Action:** Click "Human Review" in the top navigation.
- **Show:** The prioritized adjudication queue.

### Step 13: Submit / Inspect a Review Decision
- **Action:** Open an incident in the review queue, inspect the reasoning, and demonstrate selecting an adjudication decision (e.g., `PSIF`), entering an auditor rationale, and submitting.
- **Explain (Crucial Script):**  
  *"When an HSE expert reviews a case, the human decision is stored in a dedicated governance table (`IncidentReview`). The original AI model prediction and score remain completely untouched. Human review does not silently alter historical model outputs."*

### Step 14: Model Assurance & Drift Monitor (`/models/assurance/`)
- **Action:** Navigate to `Model Assurance`.
- **Show:** The active model metadata (version `v1.0`, architecture `BERT + XGBoost`), precision/recall trade-off, optimal threshold ($0.50$), and calibration disclaimer.
- **Explain:** "The Model Assurance console provides complete technical transparency regarding how the model was trained, its performance metrics on validation sets, and its decision boundary."

### Step 15: Data Quality Gate & Remediation (`/incidents/dq-dashboard/`)
- **Action:** Navigate to the Data Quality Dashboard.
- **Show:** Completeness metrics, narrative quality distribution, and the remediation queue for records with insufficient evidence.
- **Explain:** "Records with sparse narratives or missing data are quarantined under `INSUFFICIENT INFORMATION` rather than being falsely classified as `NOT PSIF`."

### Step 16: Return to Executive Dashboard & Wrap-Up
- **Action:** Return to `/`.
- **Conclude:** Summarize the core platform ethos: Traceable, Defensible, Honest, and Auditable.

---

## 4. How to Handle Tough Evaluator Questions

| Evaluator Question | Recommended Scripted Response |
| :--- | :--- |
| **"Is this model 100% accurate?"** | *"No AI model in safety is 100% accurate. Foresight is designed as a decision-support aid. High-uncertainty cases are surfaced to HSE experts in the Human Review Workbench."* |
| **"Is this system production-ready for OIL?"** | *"Foresight is an audited prototype demonstration. Genuine enterprise deployment requires formal calibration and blind validation on human-adjudicated enterprise datasets."* |
| **"Why isn't the score a real probability?"** | *"Real-world probability requires calibrated actuarial event frequencies that reflect actual operating exposure hours. Labeling raw model scores as probabilities is misleading; we treat it as an uncalibrated ranking score."* |
| **"Does SHAP prove the root cause?"** | *"No. SHAP identifies which words or structured features influenced the machine learning model's tree splits. Physical root cause requires on-site forensic investigation."* |
