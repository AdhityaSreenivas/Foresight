# Foresight: Industrial Safety Analytics Platform

> **Disclaimer**: This is a prototype system built for demonstration purposes. The ML models are trained using synthetic data or human-approved synthetic data. **Human approval of synthetic incidents indicates human review of generated examples; it is not equivalent to validation against real-world OIL HSE records.** All former heuristic-labelled records have been audited and reclassified as application-generated synthetic data. The analytical features provided (Recurrence, IOGP Classification, Similarity) are functional but depend on the quality of the underlying source data.

Foresight is an analytical platform designed to provide evidence-based insights for triaging industrial safety incidents. Rather than operating as a black box, Foresight enforces a **True Decision Trace** architecture that separates raw source data, data-quality validation, deterministic classification, historical recurrence, and ML-based predictions (PSIF).

## Current Working Capabilities (Absolute Honesty)

1. **PSIF Prediction (Synthetic Model)**: A DistilBERT + XGBoost pipeline that scores Potential Serious Injury or Fatality (PSIF) risk. The model is fully integrated but trained on synthetic data.
2. **SHAP Explainability**: Functional feature-level attributions for the XGBoost model, explaining *what the model evaluated*, not inferring causality.
3. **Data Quality Layer (New)**: A deterministic engine that identifies logical contradictions (e.g., knee vs eye injury), missing data, or placeholders in source records, explicitly warning users when ML scores or analytical results are based on inconsistent inputs. The original source data is *never* altered.
4. **IOGP Life-Saving Rule Classification**: A deterministic, rule-based text-stem classifier mapping narratives to the 9 IOGP rules.
5. **Related Incidents Retrieval**: Functional vector-similarity search using `all-MiniLM-L6-v2` embeddings, persisted in PostgreSQL (`IncidentEmbedding`), surfaced via pgvector cosine similarity.
6. **Cross-Incident Recurrence Detection**: Analytical engine finding active local and multi-site systemic patterns by grouping highly similar incidents within 90-day windows.
7. **Human Triage Queue**: A workflow to review AI recommendations alongside data quality warnings and override or confirm decisions.

## Architecture
See [ARCHITECTURE.md](ARCHITECTURE.md) for a detailed look at how Django, PostgreSQL, Celery, Redis, and the analytical pipeline fit together.

## Requirements
- **Python 3.14+** (Recommended)
- **PostgreSQL 14+** (with `pgvector` extension)
- **Redis 5+** (Required for Celery task queuing)

## Installation & Setup

1. **Clone and Virtual Environment**
   ```bash
   git clone <repository_url>
   cd prototype_165
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Database Setup**
   Ensure your PostgreSQL server is running and the database has `pgvector` enabled.
   ```bash
   python manage.py migrate
   ```

4. **Seed Synthetic Data (Optional)**
   ```bash
   python manage.py generate_seed_data
   ```

5. **Train Initial Model & Generate Embeddings (Optional)**
   ```bash
   python manage.py retrain_model
   python manage.py generate_embeddings
   python manage.py validate_incident_quality
   ```

## Verification & Testing
Run the complete test suite (includes ML pipeline, DQ checks, API validation):
```bash
pytest
```
