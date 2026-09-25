"""
Tests for Task 2: PSIF Domain Knowledge + Rule-Grounded Reasoning Engine.

Validates:
1. Fivefold internal reasoning state distinctions mapped to 3 user-facing decisions:
   - PSIF (PSIF_PATHWAY_OPEN)
   - HIGH-ENERGY CONTROLLED / NOT PSIF (HIGH_ENERGY_CONTROLLED)
   - LOW ENERGY / NOT PSIF (LOW_ENERGY)
   - INSUFFICIENT_INFORMATION (INSUFFICIENT_INFORMATION)
   - CONFLICTING_EVIDENCE (CONFLICTING_EVIDENCE -> INSUFFICIENT_INFORMATION + HIGH_PRIORITY_REVIEW)
2. Hierarchy of controls: ordinary PPE is never a direct engineered barrier (is_direct_control = False).
3. Strict IOGP separation: IOGP applicability != Rule violation != PSIF decision.
4. Reconstructible evidence trace (Section 11).
5. Downstream action interface exposing (hazard, exposure, control, control_state, consequence, rule, evidence_strength, decision).
6. Constrained language explanation keys (uppercase and lowercase).
7. Statistical ML + rule reconciliation with POTENTIAL_FALSE_NEGATIVE and POTENTIAL_FALSE_POSITIVE without silent model overwrite.
8. Missing evidence checklist with what, why_it_matters, and decision_impact.
9. Extended hazard families (Excavation, Dropped Objects, Toxic Atmosphere) and physical consequence mechanisms.
"""

import pytest
from apps.incidents.models import Incident, IncidentDataQuality
from apps.incidents.services.psif_knowledge_base import (
    EnergyHazardType,
    ExposureState,
    ControlState,
    ControlHierarchyType,
    ConsequenceMechanism,
    ConsequencePathwayState,
    InternalReasoningState,
    UserFacingDecision,
    ProvenanceTier,
    SourceAuthority,
    SOURCE_REGISTRY,
    get_rule_by_id,
)
from apps.incidents.services.psif_reasoning import (
    AgreementState,
    MissingEvidenceItem,
    EvidenceTraceItem,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
    reconcile_model_and_rules,
    build_incident_reasoning_assessment,
    evaluate_incident_psif_reasoning,
    reconcile_prediction_and_rules,
    detect_evidence_contradictions,
)
from apps.predictions.models import PredictionResult, ModelVersion


@pytest.mark.django_db
class TestFivefoldReasoningDistinctions:
    """Verifies the 5 internal reasoning states map accurately to the 3 user-facing decisions."""

    def test_state_a_psif_open_pathway(self):
        """A. PSIF: Open high-energy SIF pathway supported by evidence."""
        inc = Incident.objects.create(
            description=(
                "During pipe line breaking, double block and bleed isolation was not applied and failed. "
                "High pressure hydrocarbon gas line at 45 bar released suddenly. Worker was positioned "
                "directly in the line of fire and sustained severe facial burns and blast trauma."
            ),
            energy_type="pressure",
            control_condition="failed",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["rule_decision"] == UserFacingDecision.PSIF
        assert res["action_interface"]["decision"] == UserFacingDecision.PSIF
        assert "WHY_PSIF" in res

    def test_state_b_high_energy_controlled_not_psif(self):
        """B. HIGH-ENERGY CONTROLLED / NOT PSIF: Hazard present, but direct control held (EEI Capacity)."""
        inc = Incident.objects.create(
            description=(
                "High pressure steam accumulator overpressured to 35 bar. The certified pressure safety valve (PSV) "
                "lifted as designed and safely vented into the closed blowdown header. The double block and bleed isolation "
                "held effectively. All operating crew remained inside the blast-resistant control room."
            ),
            energy_type="pressure",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert "Capacity" in res["WHY_NOT_PSIF"] or "effectively" in res["WHY_NOT_PSIF"]

    def test_state_c_low_energy_not_psif(self):
        """C. LOW ENERGY / NOT PSIF: No credible physical SIF capability established."""
        inc = Incident.objects.create(
            description=(
                "Clerk was sorting routine permit papers in the office building on level ground and sustained "
                "a minor superficial paper cut to the right index finger. First aid kit adhesive bandage applied."
            ),
            energy_type="unknown",
            control_condition="unknown",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.LOW_ENERGY
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    def test_state_d_insufficient_information(self):
        """D. INSUFFICIENT_INFORMATION: Essential exposure/control/pathway evidence unavailable."""
        inc = Incident.objects.create(
            description="Water booster pump tripped.",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION
        assert res["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert len(res["what_is_missing"]) > 0

    def test_state_e_conflicting_evidence(self):
        """E. CONFLICTING_EVIDENCE: Material contradictory statements in narrative."""
        inc = Incident.objects.create(
            description=(
                "Positive isolation was verified and zero pressure confirmed by the technician. "
                "When the technician loosened the flange bolts, residual pressure escaped and fluid sprayed."
            ),
            energy_type="pressure",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.CONFLICTING_EVIDENCE
        assert res["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res["high_priority_review"] is True
        assert res["reconciliation"]["high_priority_review"] is True


@pytest.mark.django_db
class TestControlHierarchyAndOrdinaryPPE:
    """Verifies Section 7: Ordinary PPE is never equivalent to an engineered direct barrier."""

    def test_ppe_is_not_direct_engineered_control(self):
        inc = Incident.objects.create(
            description=(
                "Worker was wearing safety helmet, gloves, and safety boots while performing high pressure hydrotesting "
                "at 150 bar. No whip check or physical barrier was installed. Pipe whip struck worker in line of fire."
            ),
            energy_type="pressure",
        )
        evidence = extract_incident_safety_evidence(inc)
        control = evidence["control"]
        assert control.hierarchy_type == ControlHierarchyType.PPE
        assert control.is_direct_control is False
        assert control.is_compromised is True

        res = build_incident_reasoning_assessment(inc)
        assert res["control"]["is_direct_control"] is False
        assert res["control"]["hierarchy_type"] == ControlHierarchyType.PPE
        assert res["decision"] == UserFacingDecision.PSIF


@pytest.mark.django_db
class TestIOGPSeparation:
    """Verifies Section 9: IOGP applicability != Rule adherence != SIF pathway != PSIF decision."""

    def test_iogp_applicable_but_control_effective_is_not_psif(self):
        inc = Incident.objects.create(
            description=(
                "Electrical lockout tagout was fully verified and zero hazardous voltage confirmed on 11kV busbar. "
                "Electrician wore arc-rated flash suit and tested for dead. Busbar was de-energized and grounded. "
                "No electrical flash or shock occurred."
            ),
            energy_type="electrical",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        iogp_sep = res["iogp_separation"]
        assert iogp_sep["rule_adherence"] == "COMPLIANT"
        assert iogp_sep["control_state"] == ControlState.EFFECTIVE
        assert iogp_sep["psif_decision"] == UserFacingDecision.NOT_PSIF
        assert "violation" in iogp_sep["separation_rationale"].lower()


@pytest.mark.django_db
class TestEvidenceTraceAndReconstruction:
    """Verifies Section 11: Reconstructible trace linking span -> concept -> state -> rule -> decision."""

    def test_evidence_trace_structure(self):
        inc = Incident.objects.create(
            description=(
                "Scaffold handrail had been removed and was missing on platform at 6 meters height. "
                "Worker was directly exposed without safety harness tied off and fell to the concrete ground below."
            ),
            energy_type="gravity",
            control_condition="failed",
        )
        res = build_incident_reasoning_assessment(inc)
        trace = res["evidence_trace"]
        assert isinstance(trace, list)
        assert len(trace) >= 4

        fields = [t["field"] for t in trace]
        assert "hazard" in fields
        assert "exposure" in fields
        assert "control" in fields
        assert "consequence_pathway" in fields

        for item in trace:
            assert "source" in item
            assert "supporting_text" in item
            assert "normalized_concept" in item
            assert "state" in item
            assert "strength" in item
            assert "rule_association" in item
            assert "provenance" in item
            assert "decision_effect" in item


@pytest.mark.django_db
class TestActionInterfaceContract:
    """Verifies Section 16: Action interface exposes exact required keys without generic text."""

    def test_action_interface_keys(self):
        inc = Incident.objects.create(
            description="Forklift operating on excessive incline rolled over; seatbelt was not worn.",
            energy_type="motor_vehicle",
            control_condition="failed",
        )
        res = build_incident_reasoning_assessment(inc)
        action_iface = res["action_interface"]

        required_keys = {
            "hazard", "exposure", "control", "control_state",
            "consequence", "rule", "evidence_strength", "decision"
        }
        assert required_keys.issubset(set(action_iface.keys()))
        assert action_iface["hazard"] == EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT


@pytest.mark.django_db
class TestConstrainedLanguageGenerationKeys:
    """Verifies Section 15: Required uppercase and lowercase keys are present in explanation."""

    def test_constrained_language_keys_available(self):
        inc = Incident.objects.create(
            description="Crane hoisted 10-ton compressor skid. Crane rigging snapped; load fell into unbarricaded area where worker stood.",
            energy_type="suspended_load",
            control_condition="failed",
        )
        res = build_incident_reasoning_assessment(inc)

        uppercase_keys = [
            "WHY_PSIF", "WHY_NOT_PSIF", "WHAT_IS_MISSING",
            "WHAT_RULES_APPLY", "WHAT_CONTROL_MATTERS", "WHAT_WOULD_CHANGE_ASSESSMENT"
        ]
        for key in uppercase_keys:
            assert key in res
            assert key in res["constrained_explanation"]
            assert len(res[key]) > 0


@pytest.mark.django_db
class TestMLAndRuleReconciliation:
    """Verifies Section 14: ML reconciliation keeps model prediction intact and assigns false positive/negative risk."""

    def test_potential_false_negative(self):
        """Rule says PSIF, but ML model gave low score 0.12."""
        version = ModelVersion.objects.create(version_label="v1.0-test-fn", is_active=True)
        pred = PredictionResult(
            psif_probability=0.12,
            psif_predicted=False,
            risk_level=PredictionResult.RiskLevel.LOW,
            model_version=version,
        )
        reconciled = reconcile_model_and_rules(
            prediction=pred,
            rule_decision=UserFacingDecision.PSIF,
            internal_state=InternalReasoningState.PSIF_PATHWAY_OPEN,
            evidence_strength="STRONG",
        )
        assert reconciled.disagreement_type == "POTENTIAL_FALSE_NEGATIVE"
        assert reconciled.agreement_state == AgreementState.RULE_EVIDENCE_STRONGER_THAN_MODEL
        assert reconciled.high_priority_review is True
        assert reconciled.policy_final_decision == UserFacingDecision.PSIF
        # Ensure model score was not overwritten
        assert reconciled.model_score == 0.12
        assert reconciled.model_prediction in ["NOT_PSIF", "NOT PSIF"]

    def test_potential_false_positive(self):
        """ML gave high score 0.88, but Rule confirms EEI Capacity (High Energy Controlled)."""
        version = ModelVersion.objects.create(version_label="v1.0-test-fp", is_active=True)
        pred = PredictionResult(
            psif_probability=0.88,
            psif_predicted=True,
            risk_level=PredictionResult.RiskLevel.CRITICAL,
            model_version=version,
        )
        reconciled = reconcile_model_and_rules(
            prediction=pred,
            rule_decision=UserFacingDecision.NOT_PSIF,
            internal_state=InternalReasoningState.HIGH_ENERGY_CONTROLLED,
            evidence_strength="STRONG",
        )
        assert reconciled.disagreement_type == "POTENTIAL_FALSE_POSITIVE"
        assert reconciled.agreement_state == AgreementState.MODEL_STRONGER_THAN_RULE_EVIDENCE
        assert reconciled.high_priority_review is True
        assert reconciled.policy_final_decision == UserFacingDecision.NOT_PSIF


@pytest.mark.django_db
class TestMissingEvidenceWhatWhyImpact:
    """Verifies Section 12: Missing evidence items have what, why_it_matters, and decision_impact."""

    def test_missing_evidence_fields(self):
        inc = Incident.objects.create(
            description="Technician opened junction box. Work paused.",
            energy_type="electrical",
        )
        res = build_incident_reasoning_assessment(inc)
        missing = res["constrained_explanation"]["missing_evidence_checklist"]
        assert len(missing) >= 1
        for item in missing:
            assert "what" in item
            assert "why_it_matters" in item
            assert "decision_impact" in item


@pytest.mark.django_db
class TestExtendedHazardFamiliesAndConsequenceMechanisms:
    """Verifies Section 5 & 8: Excavation, Dropped Objects, Toxic Atmosphere and physical mechanisms."""

    def test_excavation_ground_collapse_rule_13(self):
        inc = Incident.objects.create(
            description=(
                "Worker entered a 2.5-meter deep trench without trench box or shoring. "
                "Trench wall collapsed and soil engulfed worker."
            ),
            energy_type="other",
            control_condition="absent",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["matched_rule"]["rule_id"] == "PSIF-R-13"
        assert res["consequence_pathway"]["physical_mechanism"] == ConsequenceMechanism.ENGULFMENT

    def test_dropped_objects_rule_14(self):
        inc = Incident.objects.create(
            description=(
                "During mast operations, scaffold clamp and pipe dropped from 15 meters. "
                "Exclusion zone was unbarricaded and ground worker was positioned directly underneath."
            ),
            energy_type="other",
            control_condition="absent",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["matched_rule"]["rule_id"] == "PSIF-R-14"
        assert res["consequence_pathway"]["physical_mechanism"] == ConsequenceMechanism.DROPPED_OBJECT

    def test_toxic_atmosphere_rule_15(self):
        inc = Incident.objects.create(
            description=(
                "Field technician exposed to acute toxic H2S gas release at 120 ppm during sampling manifold operation in open process area. "
                "Continuous gas detector was absent and line was not isolated. Worker sustained severe toxic inhalation poisoning."
            ),
            energy_type="other",
            control_condition="absent",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["matched_rule"]["rule_id"] == "PSIF-R-15"
        assert res["consequence_pathway"]["physical_mechanism"] in [ConsequenceMechanism.TOXIC_EXPOSURE, ConsequenceMechanism.ASPHYXIATION]


def test_public_contract_aliases():
    """Verifies that evaluate_incident_psif_reasoning and reconcile_prediction_and_rules are exported."""
    assert evaluate_incident_psif_reasoning is build_incident_reasoning_assessment
    assert reconcile_prediction_and_rules is reconcile_model_and_rules


def test_provenance_registry():
    """Verifies Section 3: Provenance classes registered."""
    expected_tiers = {
        ProvenanceTier.IOGP_GUIDANCE,
        ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        ProvenanceTier.INDIAN_REGULATORY,
        ProvenanceTier.OIL_PROCEDURAL,
        ProvenanceTier.FORESIGHT_ANALYTICAL,
    }
    registered_tiers = {s["provenance_tier"] for s in SOURCE_REGISTRY.values()}
    assert expected_tiers.issubset(registered_tiers)
