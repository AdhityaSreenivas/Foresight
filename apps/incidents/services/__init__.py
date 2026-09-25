"""
PSIF Platform — Shared Intelligence Foundation Facade

Provides canonical re-exports and authoritative version introspection for:
- Safety Entity Normalization
- Centralized Analytical Methodology Disclosures
- Standardized Analytical Evidence Structures
- Versioned Domain Knowledge Base
- Grounded Reasoning & Reconciliation Engine
- Corrective Action Library
- Ingestion Data Quality Gates

Ensures 100% backwards-compatible import paths and unified public contract.
"""

from typing import Dict, Any, Optional

# Core decoupled foundation components (zero Django app-registry dependency)
from apps.incidents.services.normalization import (
    NORMALIZATION_VERSION,
    NormalizationMethod,
    NormalizationStatus,
    NormalizedEntity,
    normalize_entity,
    normalize_site,
    normalize_location,
    normalize_department,
    normalize_activity,
    normalize_job_task,
    normalize_equipment,
    normalize_asset,
    normalize_energy_source,
    normalize_control_type,
    normalize_barrier,
    normalize_control_condition,
    normalize_iogp_rule,
    normalize_incident_entities,
    get_normalization_version,
)

from apps.incidents.services.methodology import (
    MethodologyKey,
    METHODOLOGY_NOTICES,
    get_methodology_notice,
    get_all_methodology_notices,
)

from apps.incidents.services.evidence import (
    EvidenceSource,
    EvidenceType,
    EvidenceStrength,
    AnalyticalEvidence,
    evidence_from_shap,
    evidence_from_incident_field,
    evidence_from_iogp_tag,
    evidence_from_narrative_span,
    evidence_from_similar_incident,
    evidence_from_recurrence_pattern,
    evidence_from_control_status,
    evidence_from_data_quality,
    evidence_from_cross_site,
)

from apps.incidents.services.psif_knowledge_base import (
    KNOWLEDGE_BASE_VERSION,
    get_knowledge_base_version,
    SourceAuthority,
    ProvenanceTier,
)

from apps.incidents.services.action_library import (
    ACTION_LIBRARY_VERSION,
    get_action_library_version,
    get_corrective_actions,
    get_action_by_id,
    ACTION_LIBRARY,
)

# Version identifiers available without loading models
REASONING_RULESET_VERSION = "psif_ruleset_v1.0"
DATA_QUALITY_VERSION = "incident_quality_v1"


def get_reasoning_ruleset_version() -> str:
    return REASONING_RULESET_VERSION


def get_data_quality_version() -> str:
    return DATA_QUALITY_VERSION


def get_intelligence_foundation_versions() -> Dict[str, str]:
    """
    Returns the authoritative runtime version manifest for all intelligence foundation components.
    Guarantees that every analytical feature can inspect active versions programmatically.
    """
    active_model_version = "none_active"
    try:
        from apps.predictions.models import ModelVersion
        active = ModelVersion.objects.filter(is_active=True).first()
        if active and active.version_label:
            active_model_version = active.version_label
    except Exception:
        pass

    return {
        "model_version": active_model_version,
        "knowledge_base_version": get_knowledge_base_version(),
        "reasoning_ruleset_version": get_reasoning_ruleset_version(),
        "action_library_version": get_action_library_version(),
        "data_quality_version": get_data_quality_version(),
        "normalization_version": get_normalization_version(),
    }


def __getattr__(name: str) -> Any:
    """Lazy imports for modules requiring Django models loaded."""
    if name in ("evaluate_incident_psif_reasoning", "reconcile_prediction_and_rules"):
        from apps.incidents.services import psif_reasoning
        return getattr(psif_reasoning, name)
    if name in ("validate_incident_for_analysis", "validate_incident_quality"):
        from apps.incidents.services import data_quality
        return getattr(data_quality, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    # Normalization
    "NORMALIZATION_VERSION",
    "NormalizationMethod",
    "NormalizationStatus",
    "NormalizedEntity",
    "normalize_entity",
    "normalize_site",
    "normalize_location",
    "normalize_department",
    "normalize_activity",
    "normalize_job_task",
    "normalize_equipment",
    "normalize_asset",
    "normalize_energy_source",
    "normalize_control_type",
    "normalize_barrier",
    "normalize_control_condition",
    "normalize_iogp_rule",
    "normalize_incident_entities",
    "get_normalization_version",
    # Methodology
    "MethodologyKey",
    "METHODOLOGY_NOTICES",
    "get_methodology_notice",
    "get_all_methodology_notices",
    # Evidence
    "EvidenceSource",
    "EvidenceType",
    "EvidenceStrength",
    "AnalyticalEvidence",
    "evidence_from_shap",
    "evidence_from_incident_field",
    "evidence_from_iogp_tag",
    "evidence_from_narrative_span",
    "evidence_from_similar_incident",
    "evidence_from_recurrence_pattern",
    "evidence_from_control_status",
    "evidence_from_data_quality",
    "evidence_from_cross_site",
    # Knowledge Base
    "KNOWLEDGE_BASE_VERSION",
    "get_knowledge_base_version",
    "SourceAuthority",
    "ProvenanceTier",
    # Reasoning
    "REASONING_RULESET_VERSION",
    "get_reasoning_ruleset_version",
    "evaluate_incident_psif_reasoning",
    "reconcile_prediction_and_rules",
    # Actions
    "ACTION_LIBRARY_VERSION",
    "get_action_library_version",
    "get_corrective_actions",
    "get_action_by_id",
    "ACTION_LIBRARY",
    # Data Quality
    "DATA_QUALITY_VERSION",
    "get_data_quality_version",
    "validate_incident_for_analysis",
    "validate_incident_quality",
    # Foundation Introspection
    "get_intelligence_foundation_versions",
]
