# Model Card: Foresight PSIF Classifier

## Model Details
- **Name**: Foresight PSIF Classifier
- **Model Type**: Stacked Text + Tabular Classifier (DistilBERT + XGBoost)
- **Version**: `v_20260902_122321`
- **Architecture**: A pipeline that fuses mean-pooled DistilBERT text embeddings (dim=768) with structured categorical/numerical features via XGBoost classification.

## Intended Use
- **Primary Use Case**: Triage and prioritize industrial safety incident reports to identify Potential Serious Injuries or Fatalities (PSIF).
- **Users**: Safety officers, data analysts, and EHS admins.
- **Out of Scope**: Automated, unreviewed firing/punitive actions based on risk scores.

## Inputs
- **Narrative Fields**: Unstructured text describing the incident.
- **Structured Fields**: Date, Department, Incident Type, Specific Location, Root Cause Category, etc.
- **Excluded Inputs**: Actual Severity and Potential Severity are explicitly excluded to prevent target leakage.

## Processing
1. **Text Preprocessing**: Normalization, casing adjustments, truncation.
2. **BERT Encoding**: DistilBERT mean pooling converts text into a 768-dimensional float vector.
3. **Structured Encoding**: Scikit-Learn pipelines encode categorical strings and scale numerical data.
4. **Feature Fusion**: Text vectors and structured vectors are concatenated horizontally.

## Outputs
- **PSIF Model Score**: Float `[0.0, 1.0]` estimating likelihood of PSIF based on synthetic training data.
- **Binary Prediction**: Boolean (True if Score >= Threshold).
- **Contributing Factors (SHAP)**: Feature-level attribution indicating *what* influenced the score (this is **NOT** a causal explanation).

## Explicitly NOT Driven By This Model
To ensure absolute honesty, the following capabilities in Foresight are explicitly **NOT** produced by this ML model:
- **IOGP Life-Saving Rules**: Handled by a deterministic text-stem matching engine.
- **Data Quality Warnings**: Handled by a deterministic validation engine checking for logical contradictions (e.g., knee vs eye) and missing data.
- **Recurring Patterns**: Handled by analytical clustering of similar incidents (via separate vector embeddings), not predictive forecasting.
- **Natural Language Explanations**: The system explicitly avoids fabricating conversational explanations of why an incident is a PSIF. It surfaces the SHAP factors directly alongside the deterministic IOGP flags and related historical evidence.

## Training Data & Limitations
- **Data Source**: Synthetic dataset generated via Python Faker.
- **CRITICAL CAVEAT**: The current model is a demonstration prototype trained on limited/synthetic data. Diagnostic experiments identified limitations in predictive separation on manually curated control narratives. The model therefore requires validation and retraining using human-reviewed OIL observations before operational deployment.

## Evaluation Metrics (Prototype / Synthetic)
- **Train/Test Split**: 85/15
- **Class Weighting**: Employed to handle severe class imbalance typical in safety data.
- **Threshold Selection**: Threshold tuned to maximize the **F2 score**, prioritizing Recall (catching PSIF events) over Precision.

## Explainability
The system employs `shap.TreeExplainer` on the fused XGBoost feature space. Because text features are densely embedded (768 dims), the explainer sums the SHAP values of all BERT dimensions into a single `narrative_content` aggregate factor. This provides a clean interface showing whether the "story" or the "structured metadata" drove the model's decision.
