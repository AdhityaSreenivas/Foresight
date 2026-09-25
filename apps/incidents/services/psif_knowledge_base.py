"""
PSIF Platform — Versioned PSIF Domain Knowledge Base Facade

Backwards-compatible facade for apps.incidents.knowledge.
Maintains 100% API compatibility with existing imports across tests, views, and services
while delegating all authoritative domain knowledge to the modularized knowledge layer:
- apps.incidents.knowledge.sources
- apps.incidents.knowledge.energy_hazards
- apps.incidents.knowledge.exposures
- apps.incidents.knowledge.controls
- apps.incidents.knowledge.consequences
- apps.incidents.knowledge.iogp
- apps.incidents.knowledge.anti_inferences
- apps.incidents.knowledge.temporal
- apps.incidents.knowledge.terminology
- apps.incidents.knowledge.evidence_requirements
- apps.incidents.knowledge.action_mappings
- apps.incidents.knowledge.psif_rules
"""

from apps.incidents.knowledge import (
    KNOWLEDGE_BASE_VERSION,
    get_knowledge_base_version,
    # Sources
    SourceAuthority,
    ProvenanceTier,
    SourceMetadata,
    SOURCE_REGISTRY,
    get_source_metadata,
    # Energy Hazards
    EnergyHazardType,
    HazardAmplifier,
    HazardFamilyDefinition,
    ExtractedHazard,
    HAZARD_FAMILY_CATALOG,
    get_hazard_definition,
    # Exposures
    ExposureState,
    WorkerPositionState,
    ExtractedExposure,
    # Controls
    ControlHierarchyType,
    ControlState,
    ExtractedControl,
    # Consequences
    ConsequenceMechanism,
    ConsequencePathwayState,
    ExtractedConsequence,
    # IOGP
    IOGPRuleCode,
    IOGP_RULE_DEFINITIONS,
    IOGPSeparationResult,
    get_iogp_rule_definition,
    # Anti-Inferences
    AntiInferenceCode,
    AntiInferenceRule,
    AntiInferenceEvaluation,
    ANTI_INFERENCE_CATALOG,
    evaluate_anti_inferences,
    get_anti_inference_rule,
    # Temporal
    SemanticRole,
    TemporalPhase,
    TemporalExpression,
    extract_temporal_expressions,
    # Terminology
    SemanticConcept,
    TerminologyMatch,
    TERMINOLOGY_CLUSTERS,
    find_terminology_matches,
    get_concepts_for_text,
    # Evidence Requirements
    EvidenceContract,
    MissingEvidenceItem,
    EVIDENCE_CONTRACTS,
    get_evidence_contract,
    evaluate_evidence_completeness,
    # Action Mappings
    ActionCategory,
    ActionClass,
    ActionRecommendation,
    map_reasoning_to_actions,
    # PSIF Rules
    InternalReasoningState,
    UserFacingDecision,
    INTERNAL_STATE_TO_DECISION,
    PSIFRuleDefinition,
    PSIF_RULES_CATALOG,
    get_rule_by_id,
    get_rules_for_hazard,
    get_rules_for_iogp,
)

__all__ = [
    "KNOWLEDGE_BASE_VERSION",
    "get_knowledge_base_version",
    "SourceAuthority",
    "ProvenanceTier",
    "SourceMetadata",
    "SOURCE_REGISTRY",
    "get_source_metadata",
    "EnergyHazardType",
    "HazardAmplifier",
    "HazardFamilyDefinition",
    "ExtractedHazard",
    "HAZARD_FAMILY_CATALOG",
    "get_hazard_definition",
    "ExposureState",
    "WorkerPositionState",
    "ExtractedExposure",
    "ControlHierarchyType",
    "ControlState",
    "ExtractedControl",
    "ConsequenceMechanism",
    "ConsequencePathwayState",
    "ExtractedConsequence",
    "IOGPRuleCode",
    "IOGP_RULE_DEFINITIONS",
    "IOGPSeparationResult",
    "get_iogp_rule_definition",
    "AntiInferenceCode",
    "AntiInferenceRule",
    "AntiInferenceEvaluation",
    "ANTI_INFERENCE_CATALOG",
    "evaluate_anti_inferences",
    "get_anti_inference_rule",
    "SemanticRole",
    "TemporalPhase",
    "TemporalExpression",
    "extract_temporal_expressions",
    "SemanticConcept",
    "TerminologyMatch",
    "TERMINOLOGY_CLUSTERS",
    "find_terminology_matches",
    "get_concepts_for_text",
    "EvidenceContract",
    "MissingEvidenceItem",
    "EVIDENCE_CONTRACTS",
    "get_evidence_contract",
    "evaluate_evidence_completeness",
    "ActionCategory",
    "ActionClass",
    "ActionRecommendation",
    "map_reasoning_to_actions",
    "InternalReasoningState",
    "UserFacingDecision",
    "INTERNAL_STATE_TO_DECISION",
    "PSIFRuleDefinition",
    "PSIF_RULES_CATALOG",
    "get_rule_by_id",
    "get_rules_for_hazard",
    "get_rules_for_iogp",
]
