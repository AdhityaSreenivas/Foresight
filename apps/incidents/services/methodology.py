"""
PSIF Platform — Centralized Methodology Disclosure System

Provides standardized, concise methodological notices across all platform features:
- IOGP Life-Saving Rules
- Semantic Similarity
- Historical Recurrence
- PSIF Model Score
- SHAP Feature Attribution
- Human Review & Adjudication
- Data Quality Validation
- Barrier & Critical-Control Intelligence

Ensures consistent disclosures, prevents misleading claims (e.g., claiming probability or causality),
and eliminates duplicate hardcoded disclaimers across templates.
"""

from typing import Dict, Any, Optional, List


# ── Canonical Methodology Keys ────────────────────────────────────────────────

class MethodologyKey:
    IOGP = "iogp"
    SIMILARITY = "similarity"
    RECURRENCE = "recurrence"
    PSIF_MODEL = "psif_model"
    SHAP = "shap"
    HUMAN_REVIEW = "human_review"
    DATA_QUALITY = "data_quality"
    BARRIER = "barrier"
    CROSS_SITE = "cross_site"


# ── Canonical Methodology Registry ───────────────────────────────────────────

METHODOLOGY_NOTICES: Dict[str, Dict[str, Any]] = {
    MethodologyKey.IOGP: {
        "key": MethodologyKey.IOGP,
        "title": "IOGP Life-Saving Rules Classification",
        "badge_label": "Rule-Derived",
        "summary": "Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure.",
        "caveats": [
            "Matches are derived deterministically from keywords and contextual negation rules in incident text fields.",
            "A rule match indicates relevant activity or hazard context, not proof that a safety rule was violated or that a barrier failed."
        ],
        "provenance": "deterministic_iogp_ruleset_v1",
        "category": "rule_based",
        "severity": "info"
    },
    MethodologyKey.SIMILARITY: {
        "key": MethodologyKey.SIMILARITY,
        "title": "Semantic Incident Narrative Similarity",
        "badge_label": "Semantic Vector",
        "summary": "Semantic similarity between incident narratives; not causal evidence or duplicate identity.",
        "caveats": [
            "Calculated via cosine similarity over high-dimensional text embeddings of composite narratives.",
            "High similarity indicates shared language and contextual themes, not causal linkage or duplicate event identity."
        ],
        "provenance": "distilbert_embedding_cosine_v1",
        "category": "vector_similarity",
        "severity": "info"
    },
    MethodologyKey.RECURRENCE: {
        "key": MethodologyKey.RECURRENCE,
        "title": "Historical Recurrence Pattern Detection",
        "badge_label": "Historical Pattern",
        "summary": "Historical recurrence based on normalized entities and time-window matching; not causal/systemic prediction.",
        "caveats": [
            "Aggregates repeated combinations of normalized site, activity, and life-saving rules within rolling temporal windows.",
            "Historical recurrence patterns provide visibility into reporting frequency, not statistical or physical proof of future failure."
        ],
        "provenance": "temporal_entity_clustering_v1",
        "category": "historical_aggregation",
        "severity": "info"
    },
    MethodologyKey.PSIF_MODEL: {
        "key": MethodologyKey.PSIF_MODEL,
        "title": "PSIF Predictive Model Score",
        "badge_label": "PSIF Model Score",
        "summary": "PSIF Model Score from the active model; score is not a calibrated probability.",
        "caveats": [
            "The score represents relative machine learning prioritization rank based on extracted text and structured safety attributes.",
            "Model scores are decision-support indicators for safety professionals and do not constitute physical certainty."
        ],
        "provenance": "active_xgboost_transformer_pipeline",
        "category": "predictive_model",
        "severity": "warning"
    },
    MethodologyKey.SHAP: {
        "key": MethodologyKey.SHAP,
        "title": "Mathematical Feature Attribution (SHAP)",
        "badge_label": "Feature Attribution",
        "summary": "SHAP values show mathematical model contribution, not causality.",
        "caveats": [
            "SHAP attributions quantify the marginal mathematical influence of features on the model's output score.",
            "Feature weights indicate statistical association within the trained dataset, not physical root causes."
        ],
        "provenance": "tree_shap_explainer_v1",
        "category": "interpretability",
        "severity": "info"
    },
    MethodologyKey.HUMAN_REVIEW: {
        "key": MethodologyKey.HUMAN_REVIEW,
        "title": "HSE Expert Adjudication",
        "badge_label": "Human Adjudication",
        "summary": "Human adjudication is shown separately from model prediction.",
        "caveats": [
            "Expert safety review represents human domain judgment and is never overwritten or conflated with automated model inference.",
            "All human determinations retain full auditor attribution and timestamped rationale."
        ],
        "provenance": "audited_human_workflow_v1",
        "category": "human_governance",
        "severity": "info"
    },
    MethodologyKey.DATA_QUALITY: {
        "key": MethodologyKey.DATA_QUALITY,
        "title": "Incident Data Quality & Analytical Suitability",
        "badge_label": "Data Quality",
        "summary": "Data-quality rules indicate analytical suitability; they do not establish PSIF status.",
        "caveats": [
            "Deterministic checks verify narrative completeness, chronological logic, and metadata consistency.",
            "Data quality status reflects information readiness, not the inherent physical hazard or safety outcome."
        ],
        "provenance": "incident_quality_rules_v1",
        "category": "data_governance",
        "severity": "info"
    },
    MethodologyKey.BARRIER: {
        "key": MethodologyKey.BARRIER,
        "title": "Barrier & Critical Control Intelligence",
        "badge_label": "Barrier Intelligence",
        "summary": "Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure.",
        "caveats": [
            "Signals reflect explicit keyword and contextual patterns for control conditions and IOGP life-saving rules.",
            "Automated flags do not substitute for technical root-cause investigation or physical barrier inspection."
        ],
        "provenance": "barrier_rule_engine_v1",
        "category": "rule_based",
        "severity": "info"
    },
    MethodologyKey.CROSS_SITE: {
        "key": MethodologyKey.CROSS_SITE,
        "title": "Cross-Site Recurrence Pattern Analysis",
        "badge_label": "Cross-Site Intelligence",
        "summary": "Cross-site findings use normalized safety entities and historical occurrence data. They indicate recurrence patterns, not causal relationships or future-risk predictions.",
        "caveats": [
            "Matches utilize normalized safety entities (site, activity, equipment, life-saving rules) across operational boundaries.",
            "Cross-site findings highlight historical patterns and shared context, not causal relationships or predictive failure certainty."
        ],
        "provenance": "cross_site_normalization_v1",
        "category": "cross_site_analysis",
        "severity": "info"
    },
}


# ── Accessor Functions ────────────────────────────────────────────────────────

def get_methodology_notice(key: str) -> Dict[str, Any]:
    """
    Retrieve the standard methodology disclosure for a given analytical component.
    Falls back to a safe generic disclosure if key is unknown.
    """
    cleaned_key = (key or "").strip().lower()
    if cleaned_key in METHODOLOGY_NOTICES:
        return METHODOLOGY_NOTICES[cleaned_key]
    
    return {
        "key": cleaned_key,
        "title": f"{cleaned_key.replace('_', ' ').title()} Methodology",
        "badge_label": "Analytical Signal",
        "summary": "Analytical indicator for human review; not causal evidence or verified ground truth.",
        "caveats": ["Derived from automated processing. Review source data before operational decisions."],
        "provenance": "platform_analytics_v1",
        "category": "general",
        "severity": "info"
    }


def get_all_methodology_notices() -> Dict[str, Dict[str, Any]]:
    """
    Returns the complete registry of canonical methodology notices.
    """
    return dict(METHODOLOGY_NOTICES)
