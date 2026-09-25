# SIH Demonstration Guide: Foresight

This guide outlines a focused 5–10 minute demonstration of the Foresight platform tailored for the Smart India Hackathon (SIH) presentation. 

## The Narrative
1. **The Problem**: Organizations like OIL receive massive volumes of safety reports. Manually reading and prioritizing these is slow, meaning precursors to Serious Injuries or Fatalities (PSIF) might be missed until it's too late.
2. **The Solution**: Foresight ingests safety observations, near-miss reports and incident narratives, combines narrative and structured safety information, and produces a model-based PSIF prioritization score. The system then provides analytical evidence through SHAP and routes the observation into a human review workflow.

---

## Prerequisites
Before the demo, ensure the local environment is fully running:
- PostgreSQL
- Redis (`redis-server`)
- Celery Worker (`celery -A config worker -l info`)
- Django Server (`python manage.py runserver`)
- A clean demo CSV (`sample_incidents.csv`) is available on your desktop.

## Recommended Flow

### 1. Login & Dashboard (1 min)
- Navigate to `http://127.0.0.1:8000/`.
- Log in with Admin credentials.
- Land on the **Dashboard**. Briefly explain that this is the command center aggregating all historical safety data into actionable insights (e.g., Risk Distribution, Incident Volumes).

### 2. Ingestion & Asynchronous Processing (3 mins)
- Explain the operational challenge of bulk data.
- Navigate to **Datasets** -> **Upload Dataset**.
- Upload `sample_incidents.csv`.
- On the **Column Mapping** screen, point out that safety data rarely arrives in a clean, unified format. Show how the system auto-maps fields (e.g., matching the CSV's "Event Narrative" to the canonical `narrative_content`).
- Click **Start Processing**.
- Land on the **Dataset Status** page.
- *Talking Point*: Point out that the processing happens asynchronously via Celery/Redis in chunks. Watch the progress bar increment live. The platform handles memory efficiently and doesn't block the user's browser.

### 3. Reviewing Incidents & Explainability (3 mins)
- Once complete, click **View Incidents**.
- You are now looking at the newly ingested data. Notice the risk badges (Low, Medium, High, Critical).
- Click into a **Critical** or **High** risk incident.
- Show the **PSIF Model Score**.
- **Crucial Step**: Scroll to the **Analytical Evidence** chart.
- *Talking Point*: AI in industrial safety must be trustworthy. Show how the system provides analytical evidence—highlighting whether factors like the `department` or the textual `narrative_content` contributed to the model score.
- **IOGP Life-Saving Rules**: Point out the deterministic classification flags (e.g. Energy Isolation, Confined Space) and emphasize that these are mapped transparently via word-stems, not black-box ML.
- **Related Incidents & Recurrence**: Scroll down to the related incidents list. Show how the system surfaces historically similar events from across different facilities and identifies active multi-site recurring patterns. 
- **Data Quality & Trust**: Navigate to an incident with contradictory data (e.g., body part says knee, but narrative says eye). Show how the **Data Quality Layer** explicitly flags the contradiction and warns the reviewer, ensuring bad data is never disguised as clean intelligence.

### 4. Real-time Triage (Manual Prediction) (1 min)
- Navigate to **Manual Prediction**.
- Explain this is for safety officers in the field needing immediate triage.
- Fill out a sample high-risk scenario (e.g., "Worker fell from unharnessed scaffolding").
- Click **Generate Prediction** and show the instantaneous return of risk and SHAP values without needing bulk CSV processing.

### 5. Transparency & Limitations (1 min)
- Navigate to **Models**.
- Show the model versioning system. Explain that models can be retrained and rolled back safely natively within the database.
- *Honesty Point*: The current model is a demonstration prototype. Its inference pipeline has been technically validated, but predictive performance must be validated on human-reviewed OIL data before operational deployment.
