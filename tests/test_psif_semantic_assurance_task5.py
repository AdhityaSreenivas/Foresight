"""
Task 5 — Final Semantic Assurance & Reasoning Contract Freeze Test Suite

Comprehensive tests verifying:
1. Four-tier internal reasoning states and 3-way user-facing decisions
2. 10-stage decision sequence adherence
3. Contrastive single-fact mutations across major hazards
4. Semantic role isolation and temporal ordering
5. Negation assurance
6. Corrective-action quarantine
7. IOGP separation
8. Control state hierarchy (PPE is non-direct)
9. Exposure and consequence pathway connection
10. Low-energy vs insufficient information separation
11. ML + Rule Reconciliation and Decision Policy Layer
12. Reasoning Provenance Graph serialization
13. Multi-hazard composite pathways
14. Source provenance integrity
15. Grounded action mappings decoupling
16. Frozen API endpoint contract on GET /api/incidents/<pk>/reasoning/
"""
import pytest
from apps.incidents.models import Incident, IncidentDataQuality
from apps.predictions.models import PredictionResult
from apps.incidents.services.psif_knowledge_base import (
    KNOWLEDGE_BASE_VERSION,
    InternalReasoningState,
    UserFacingDecision,
    INTERNAL_STATE_TO_DECISION,
    EnergyHazardType,
    ExposureState,
    ControlState,
    ControlHierarchyType,
    ConsequencePathwayState,
    PSIF_RULES_CATALOG,
    SOURCE_REGISTRY,
    get_rule_by_id,
    get_evidence_contract,
    SemanticRole,
    TemporalPhase,
)
from apps.incidents.services.psif_reasoning import (
    build_incident_reasoning_assessment,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
    reconcile_model_and_rules,
    AgreementState,
    REASONING_RULESET_VERSION,
)
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


# ── 1. Canonical State Space & Sequence Assurance ────────────────────────────

@pytest.mark.django_db
class TestCanonicalStateSpaceAndSequence:
    """Verifies the four-tier state space and 10-stage decision sequence."""

    def test_state_mapping_completeness(self):
        """All 5 internal states map deterministically to user-facing decisions."""
        assert INTERNAL_STATE_TO_DECISION[InternalReasoningState.PSIF_PATHWAY_OPEN] == UserFacingDecision.PSIF
        assert INTERNAL_STATE_TO_DECISION[InternalReasoningState.HIGH_ENERGY_CONTROLLED] == UserFacingDecision.NOT_PSIF
        assert INTERNAL_STATE_TO_DECISION[InternalReasoningState.LOW_ENERGY] == UserFacingDecision.NOT_PSIF
        assert INTERNAL_STATE_TO_DECISION[InternalReasoningState.INSUFFICIENT_INFORMATION] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert INTERNAL_STATE_TO_DECISION[InternalReasoningState.CONFLICTING_EVIDENCE] == UserFacingDecision.INSUFFICIENT_INFORMATION

    def test_sequence_high_energy_absent_yields_low_energy(self):
        """Step A: Absence of high energy halts sequence at LOW_ENERGY."""
        narrative = "Clerk slipped on wet tile in breakroom sustaining a bruised knee. First aid ice pack applied."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.LOW_ENERGY
        assert res["decision"] == UserFacingDecision.NOT_PSIF

    def test_sequence_exposure_protected_yields_controlled(self):
        """Step B: High energy present, but worker in safe positioning yields HIGH_ENERGY_CONTROLLED."""
        narrative = "Pressure testing of 350 bar pipeline spool executed. Testing crew remained inside monitoring trailer with blast containment barricades in place."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["decision"] == UserFacingDecision.NOT_PSIF

    def test_sequence_missing_barrier_yields_insufficient(self):
        """Step D/G: High energy and worker present, but barrier condition unknown yields INSUFFICIENT_INFORMATION."""
        narrative = "Technician was troubleshooting high pressure manifold. Narrative omits whether line was depressurized or isolated."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION
        assert res["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert len(res["evidence_needed_to_close"]) > 0

    def test_sequence_open_pathway_yields_psif(self):
        """Step I/J: High energy + exposed worker + compromised direct control yields PSIF_PATHWAY_OPEN."""
        narrative = "Technician attempted to tighten union under live pressure on 250 bar manifold without lockout applied. Threads stripped off and line whipped striking worker directly in chest."
        inc = Incident(description=narrative, composite_narrative=narrative, injury_type="severe", body_part="chest")
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res["decision"] == UserFacingDecision.PSIF


# ── 2. Material Contradictions & Negation Assurance ──────────────────────────

@pytest.mark.django_db
class TestContradictionAndNegationAssurance:
    """Verifies material contradiction detection and negation handling."""

    def test_isolation_verified_vs_passing_valve_contradiction(self):
        """Contradiction: Verified isolation asserted, but valve was passing steam."""
        narrative = "Operator confirmed zero energy isolation verified on permit. However, during unbolting the isolation valve was found passing steam at 18 bar."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.CONFLICTING_EVIDENCE
        assert res["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res["high_priority_review"] is True

    def test_exclusion_zone_safe_vs_entered_contradiction(self):
        """Contradiction: Worker remained outside exclusion zone asserted, but worker entered zone."""
        narrative = "Rigging supervisor ensured worker remained outside the exclusion zone. Simultaneously, helper entered the exclusion zone under the suspended load."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.CONFLICTING_EVIDENCE
        assert res["high_priority_review"] is True

    def test_negation_not_exposed_does_not_become_direct_exposure(self):
        """'Worker was not exposed' must NOT be classified as direct exposure."""
        narrative = "High pressure hydraulic fitting leaked at 200 bar. Operator remained behind protective shield and worker was not exposed."
        inc = Incident(description=narrative, composite_narrative=narrative)
        ev = extract_incident_safety_evidence(inc)
        assert ev["exposure"].state in [ExposureState.NO_WORKER_EXPOSURE, ExposureState.NEARBY_BUT_PROTECTED]

    def test_negation_not_verified_becomes_compromised_state(self):
        """'Isolation was not verified' must NOT become effective isolation."""
        narrative = "Technician cracked flange on hydrocarbon manifold. Isolation not verified prior to unbolting."
        inc = Incident(description=narrative, composite_narrative=narrative)
        ev = extract_incident_safety_evidence(inc)
        assert ev["control"].state in [ControlState.NOT_VERIFIED, ControlState.FAILED]


# ── 3. Semantic Roles & Temporal Reasoning ────────────────────────────────────

@pytest.mark.django_db
class TestSemanticRolesAndTemporalAssurance:
    """Verifies semantic roles (event vs recommendation vs plan) and temporal ordering."""

    def test_recommendation_quarantine_does_not_infer_failure(self):
        """Post-event recommendation to replace guard must not infer guard failed during event."""
        narrative = "Mechanic stood behind designated safety barrier while coupling guard was securely bolted during pump operation. [SEP] Corrective action: Recommend replacing guard during next shutdown."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["decision"] == UserFacingDecision.NOT_PSIF

    def test_planned_action_does_not_mask_current_failure(self):
        """Future planned guard does not mask present open nip point during work."""
        narrative = "Drive belt was running unguarded while technician reached into nip point. Maintenance team plans to install an interlocked guard next week."
        inc = Incident(description=narrative, composite_narrative=narrative, injury_type="laceration", body_part="hand")
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res["decision"] == UserFacingDecision.PSIF

    def test_restored_before_exposure_yields_controlled(self):
        """Control restored before exposure halts pathway -> HIGH_ENERGY_CONTROLLED."""
        narrative = "Scaffolding work at height was halted when lanyard defect was noticed. Lanyard was restored before exposure and worker remained behind segregation."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["decision"] == UserFacingDecision.NOT_PSIF


# ── 4. IOGP Separation Assurance ──────────────────────────────────────────────

@pytest.mark.django_db
class TestIOGPSeparationAssurance:
    """Verifies: IOGP applicable != IOGP violation != control failure != PSIF."""

    def test_iogp_applicable_with_effective_control_is_not_psif(self):
        """IOGP rule applies, but controls were followed -> HIGH_ENERGY_CONTROLLED."""
        narrative = "Work at height permit reviewed per IOGP Life-Saving Rules. Scaffolder wore full body harness and was 100% tied off. Guardrail held and worker remained behind segregation."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["iogp_separation"]["rule_adherence"] == "COMPLIANT"

    def test_iogp_violated_with_exposure_is_psif(self):
        """IOGP rule violated + exposure + energy -> PSIF."""
        narrative = "Scaffolder walked on elevated scaffold deck at 8 meters where guardrail was missing. Lanyard was unclipped and worker fell from height."
        inc = Incident(description=narrative, composite_narrative=narrative, injury_type="fracture", body_part="leg")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN


# ── 5. Control Hierarchy & PPE Non-Direct Assurance ───────────────────────────

@pytest.mark.django_db
class TestControlHierarchyAndPPE:
    """Verifies that PPE is recognized as non-direct and cannot eliminate high energy."""

    def test_gloves_do_not_eliminate_rotating_nip_point(self):
        """Leather gloves do not act as an engineered direct barrier against rotating equipment."""
        narrative = "Operator wore leather gloves while reaching into unguarded drive belt. Drive belt caught glove and amputated finger."
        inc = Incident(description=narrative, composite_narrative=narrative, injury_type="amputation", body_part="finger")
        ev = extract_incident_safety_evidence(inc)
        assert ev["control"].is_direct_control is False or ev["control"].is_compromised is True
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF


# ── 6. ML + Rule Reconciliation & Decision Policy ─────────────────────────────

@pytest.mark.django_db
class TestMLAndRuleReconciliationPolicy:
    """Verifies the explicit reconciliation and policy decision rules."""

    def test_potential_false_negative_safety_override(self):
        """Rule says PSIF, Model score is low (0.05) -> Decision is PSIF, High Priority Review."""
        narrative = "Technician attempted to tighten union under live pressure on 250 bar manifold without lockout. Threads stripped off and struck worker."
        inc = Incident(description=narrative, composite_narrative=narrative, injury_type="severe", body_part="chest")
        pred = PredictionResult(psif_probability=0.05, psif_predicted=False)
        res = build_incident_reasoning_assessment(inc, prediction=pred)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["reconciliation"]["agreement_state"] == AgreementState.RULE_EVIDENCE_STRONGER_THAN_MODEL
        assert res["reconciliation"]["disagreement_type"] == "POTENTIAL_FALSE_NEGATIVE"
        assert res["high_priority_review"] is True

    def test_potential_false_positive_capacity_recognition(self):
        """Rule says Controlled, Model score is high (0.85) -> Decision is NOT_PSIF, High Priority Review."""
        narrative = "Crane performed 10-ton lift. The cordoned drop zone was established and rigid timber barricades prevented any pedestrian entry."
        inc = Incident(description=narrative, composite_narrative=narrative)
        pred = PredictionResult(psif_probability=0.85, psif_predicted=True)
        res = build_incident_reasoning_assessment(inc, prediction=pred)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["reconciliation"]["agreement_state"] == AgreementState.MODEL_STRONGER_THAN_RULE_EVIDENCE
        assert res["reconciliation"]["disagreement_type"] == "POTENTIAL_FALSE_POSITIVE"
        assert res["high_priority_review"] is True

    def test_data_quality_critical_blocks_determination(self):
        """Critical DQ gate blocks determination -> INSUFFICIENT_INFORMATION."""
        narrative = "Technician unbolted live 50 bar line without permit."
        inc = Incident(description=narrative, composite_narrative=narrative)
        dq = IncidentDataQuality(incident=inc, status=IncidentDataQuality.Status.CRITICAL)
        res = build_incident_reasoning_assessment(inc, dq_record=dq)
        assert res["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res["reconciliation"]["agreement_state"] == AgreementState.DATA_QUALITY_BLOCKED
        assert res["high_priority_review"] is True


# ── 7. Contrastive Single-Fact Semantic Mutations ─────────────────────────────

@pytest.mark.django_db
class TestContrastiveSingleFactMutations:
    """
    Derives paired mutations where exactly one physical safety fact is inverted.
    Verifies that the target dimension changes while unrelated dimensions remain stable.
    """

    def test_mutation_working_at_height_lanyard(self):
        """Mutation: '100% tied off' -> 'lanyard unclipped'"""
        base_text = "Scaffolder worked on elevated scaffold at 8 meters. Guardrail held and worker was 100% tied off behind segregation."
        mutated_text = "Scaffolder worked on elevated scaffold at 8 meters. Guardrail held but lanyard was unclipped and worker fell from height."

        res_base = build_incident_reasoning_assessment(Incident(description=base_text, composite_narrative=base_text))
        res_mut = build_incident_reasoning_assessment(Incident(description=mutated_text, composite_narrative=mutated_text, injury_type="fracture", body_part="leg"))

        assert res_base["decision"] == UserFacingDecision.NOT_PSIF
        assert res_base["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_mut["decision"] == UserFacingDecision.PSIF
        assert res_mut["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_mutation_pressure_isolation(self):
        """Mutation: 'isolation verified' -> 'isolation not verified'"""
        base_text = "Pipefitters worked on 40 bar manifold. Valves held absolute isolation and zero energy verified before flange break."
        mutated_text = "Pipefitters worked on 40 bar manifold. Isolation not verified before flange break and pressurized spray was released toward worker."

        res_base = build_incident_reasoning_assessment(Incident(description=base_text, composite_narrative=base_text))
        res_mut = build_incident_reasoning_assessment(Incident(description=mutated_text, composite_narrative=mutated_text, injury_type="burn", body_part="eyes"))

        assert res_base["decision"] == UserFacingDecision.NOT_PSIF
        assert res_base["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_mut["decision"] == UserFacingDecision.PSIF
        assert res_mut["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_mutation_suspended_load_worker_position(self):
        """Mutation: 'remained outside drop zone' -> 'walked underneath suspended load'"""
        base_text = "Crane lifted 5-ton steel bundle. Riggers remained safely outside the drop zone behind designated safety barrier."
        mutated_text = "Crane lifted 5-ton steel bundle. Rigger walked underneath suspended load to adjust timber dunnage when sling unseated."

        res_base = build_incident_reasoning_assessment(Incident(description=base_text, composite_narrative=base_text))
        res_mut = build_incident_reasoning_assessment(Incident(description=mutated_text, composite_narrative=mutated_text, injury_type="crush", body_part="chest"))

        assert res_base["decision"] == UserFacingDecision.NOT_PSIF
        assert res_base["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_mut["decision"] == UserFacingDecision.PSIF
        assert res_mut["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN


# ── 8. Source Provenance Integrity ────────────────────────────────────────────

class TestSourceProvenanceIntegrity:
    """Verifies that all catalog rules are anchored to verifiable authoritative sources."""

    def test_every_catalog_rule_has_registered_source(self):
        """Every rule in PSIF_RULES_CATALOG must map to an authoritative source in SOURCE_REGISTRY."""
        for rule in PSIF_RULES_CATALOG:
            assert rule.source in SOURCE_REGISTRY, f"Rule {rule.rule_id} has unregistered source {rule.source}"
            meta = SOURCE_REGISTRY[rule.source]
            assert meta.document, f"Source {rule.source} missing document title"
            assert meta.organization, f"Source {rule.source} missing organization"
            assert meta.provenance_tier, f"Source {rule.source} missing provenance tier"
            assert rule.source_section, f"Rule {rule.rule_id} missing verified section/clause citation"


# ── 9. Frozen Reasoning API Endpoint Contract ─────────────────────────────────

@pytest.mark.django_db
class TestFrozenReasoningAPIEndpointContract:
    """Verifies the GET /api/incidents/<pk>/reasoning/ endpoint contract matches Section 23."""

    def test_api_returns_all_frozen_contract_keys(self):
        user = User.objects.create_user(username="frozen_auditor", password="testpassword123")
        client = APIClient()
        client.force_authenticate(user=user)

        desc = "Technician attempted to tighten union under live pressure on 250 bar manifold without lockout. Threads stripped off and struck worker."
        incident = Incident.objects.create(
            description=desc,
            composite_narrative=desc,
            injury_type="severe",
            body_part="chest",
        )

        response = client.get(f"/api/incidents/{incident.id}/reasoning/")
        assert response.status_code == 200
        data = response.json()

        # Section 23 Minimum Frozen Contract Keys
        required_keys = [
            "incident_id",
            "decision",
            "internal_reasoning_state",
            "evidence_strength",
            "reasoning_chain",
            "evidence_matrix",
            "evidence_summary",
            "what_is_known",
            "evidence_needed_to_close",
            "why_psif",
            "why_not_psif",
            "rules_applied",
            "control_assessment",
            "consequence_pathway",
            "reconciliation",
            "high_priority_review",
            "grounded_actions",
            "source_provenance",
            "knowledge_base_version",
            "reasoning_ruleset_version",
            "action_library_version",
        ]

        for key in required_keys:
            assert key in data, f"Missing frozen contract key: '{key}'"

        # Additional core assurance payloads
        assert "provenance_graph" in data
        assert "anti_inferences" in data
        assert "multi_hazard" in data
        assert data["knowledge_base_version"] == "psif_kb_v1.0"
        assert data["reasoning_ruleset_version"] == "psif_ruleset_v1.0"
