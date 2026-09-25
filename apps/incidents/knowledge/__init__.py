"""
PSIF Knowledge Base Package — apps/incidents/knowledge

Authoritative Domain Knowledge Layer for the PSIF Reasoning Engine.
Modularized in Task 4 into focused domain modules:
- sources: Source registry & provenance hierarchy
- energy_hazards: 15 canonical hazard families + state space
- exposures: Worker exposure states & positioning
- controls: Control hierarchy and 12-state lifecycle
- consequences: Consequence mechanisms & physical pathways
- iogp: IOGP Life-Saving Rules (9 official) & Start Work Checks
- anti_inferences: 13 declarative anti-inference rules
- temporal: 10 semantic roles and 7 temporal phases
- terminology: Multi-hazard terminology clusters
- evidence_requirements: Evidence contracts across all 15 hazard families
- action_mappings: Grounded downstream corrective action recommendations
- psif_rules: Authoritative rule definitions with counterexample logic
"""

from apps.incidents.knowledge.sources import (
    SourceAuthority,
    ProvenanceTier,
    SourceMetadata,
    SOURCE_REGISTRY,
    get_source_metadata,
)
from apps.incidents.knowledge.energy_hazards import (
    EnergyHazardType,
    HazardAmplifier,
    HazardFamilyDefinition,
    ExtractedHazard,
    HAZARD_FAMILY_CATALOG,
    get_hazard_definition,
)
from apps.incidents.knowledge.exposures import (
    ExposureState,
    WorkerPositionState,
    ExtractedExposure,
)
from apps.incidents.knowledge.controls import (
    ControlHierarchyType,
    ControlState,
    ExtractedControl,
)
from apps.incidents.knowledge.consequences import (
    ConsequenceMechanism,
    ConsequencePathwayState,
    ExtractedConsequence,
)
from apps.incidents.knowledge.iogp import (
    IOGPRuleCode,
    IOGP_RULE_DEFINITIONS,
    IOGPSeparationResult,
    get_iogp_rule_definition,
)
from apps.incidents.knowledge.anti_inferences import (
    AntiInferenceCode,
    AntiInferenceRule,
    AntiInferenceEvaluation,
    ANTI_INFERENCE_CATALOG,
    evaluate_anti_inferences,
    get_anti_inference_rule,
)
from apps.incidents.knowledge.temporal import (
    SemanticRole,
    TemporalPhase,
    TemporalExpression,
    extract_temporal_expressions,
)
from apps.incidents.knowledge.terminology import (
    SemanticConcept,
    TerminologyMatch,
    TERMINOLOGY_CLUSTERS,
    find_terminology_matches,
    get_concepts_for_text,
)
from apps.incidents.knowledge.evidence_requirements import (
    EvidenceContract,
    MissingEvidenceItem,
    EVIDENCE_CONTRACTS,
    get_evidence_contract,
    evaluate_evidence_completeness,
)
from apps.incidents.knowledge.action_mappings import (
    ActionCategory,
    ActionClass,
    ActionRecommendation,
    map_reasoning_to_actions,
)
from apps.incidents.knowledge.psif_rules import (
    InternalReasoningState,
    UserFacingDecision,
    INTERNAL_STATE_TO_DECISION,
    PSIFRuleDefinition,
    PSIF_RULES_CATALOG,
    get_rule_by_id,
    get_rules_for_hazard,
    get_rules_for_iogp,
)

KNOWLEDGE_BASE_VERSION = "psif_kb_v1.0"


def get_knowledge_base_version() -> str:
    """Returns the active PSIF knowledge base schema version."""
    return KNOWLEDGE_BASE_VERSION


__all__ = [
    "KNOWLEDGE_BASE_VERSION",
    "get_knowledge_base_version",
    # Sources
    "SourceAuthority",
    "ProvenanceTier",
    "SourceMetadata",
    "SOURCE_REGISTRY",
    "get_source_metadata",
    # Energy Hazards
    "EnergyHazardType",
    "HazardAmplifier",
    "HazardFamilyDefinition",
    "ExtractedHazard",
    "HAZARD_FAMILY_CATALOG",
    "get_hazard_definition",
    # Exposures
    "ExposureState",
    "WorkerPositionState",
    "ExtractedExposure",
    # Controls
    "ControlHierarchyType",
    "ControlState",
    "ExtractedControl",
    # Consequences
    "ConsequenceMechanism",
    "ConsequencePathwayState",
    "ExtractedConsequence",
    # IOGP
    "IOGPRuleCode",
    "IOGP_RULE_DEFINITIONS",
    "IOGPSeparationResult",
    "get_iogp_rule_definition",
    # Anti-Inferences
    "AntiInferenceCode",
    "AntiInferenceRule",
    "AntiInferenceEvaluation",
    "ANTI_INFERENCE_CATALOG",
    "evaluate_anti_inferences",
    "get_anti_inference_rule",
    # Temporal
    "SemanticRole",
    "TemporalPhase",
    "TemporalExpression",
    "extract_temporal_expressions",
    # Terminology
    "SemanticConcept",
    "TerminologyMatch",
    "TERMINOLOGY_CLUSTERS",
    "find_terminology_matches",
    "get_concepts_for_text",
    # Evidence Requirements
    "EvidenceContract",
    "MissingEvidenceItem",
    "EVIDENCE_CONTRACTS",
    "get_evidence_contract",
    "evaluate_evidence_completeness",
    # Action Mappings
    "ActionCategory",
    "ActionClass",
    "ActionRecommendation",
    "map_reasoning_to_actions",
    # PSIF Rules
    "InternalReasoningState",
    "UserFacingDecision",
    "INTERNAL_STATE_TO_DECISION",
    "PSIFRuleDefinition",
    "PSIF_RULES_CATALOG",
    "get_rule_by_id",
    "get_rules_for_hazard",
    "get_rules_for_iogp",
]
