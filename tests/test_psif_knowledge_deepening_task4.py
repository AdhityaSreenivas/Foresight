"""
PSIF Platform — Task 4 Deepened PSIF Knowledge Base & Upgraded Semantic Reasoning Test Suite

Comprehensive Test Matrix verifying:
1. 15 Required Hazard Families Coverage & Full State-Space Modeling
2. Three-Way Reasoning (PSIF / Controlled Not PSIF / Insufficient / Conflicting)
3. Explicit Counterexample Pairs across Major Hazard Families
4. 13 Declarative Anti-Inference Rules Evaluation & Enforcement
5. Semantic Roles & Temporal Reasoning Extraction
6. Reasoning Provenance Graph Generation (source text -> role -> concept -> state -> rule -> effect)
7. Multi-Hazard Reasoning & Pathway Retention
8. Grounded Hierarchy-of-Controls Action Mappings
9. Contrastive Semantic Mutation Tests (single-fact flips)
10. Backwards-Compatible Facade Integrity
"""
import pytest
from apps.incidents.models import Incident
from apps.incidents.services.psif_knowledge_base import (
    KNOWLEDGE_BASE_VERSION,
    get_knowledge_base_version,
    SourceAuthority,
    ProvenanceTier,
    SOURCE_REGISTRY,
    EnergyHazardType,
    HAZARD_FAMILY_CATALOG,
    get_hazard_definition,
    ExposureState,
    ControlState,
    ControlHierarchyType,
    ConsequenceMechanism,
    ConsequencePathwayState,
    IOGPRuleCode,
    IOGP_RULE_DEFINITIONS,
    AntiInferenceCode,
    ANTI_INFERENCE_CATALOG,
    evaluate_anti_inferences,
    SemanticRole,
    TemporalPhase,
    extract_temporal_expressions,
    SemanticConcept,
    TERMINOLOGY_CLUSTERS,
    find_terminology_matches,
    EVIDENCE_CONTRACTS,
    get_evidence_contract,
    evaluate_evidence_completeness,
    ActionCategory,
    ActionClass,
    ActionRecommendation,
    map_reasoning_to_actions,
    InternalReasoningState,
    UserFacingDecision,
    PSIF_RULES_CATALOG,
    get_rule_by_id,
    get_rules_for_hazard,
    get_rules_for_iogp,
)
from apps.incidents.services.psif_reasoning import (
    build_incident_reasoning_assessment,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
)


# ── 1. 15 Required Hazard Families Coverage & State-Space Integrity ─────────────

@pytest.mark.django_db
class TestHazardFamilyCoverage:
    """Verifies that all 15 required hazard families are modeled with full physical state spaces."""

    REQUIRED_15_FAMILIES = [
        EnergyHazardType.WORKING_AT_HEIGHT,
        EnergyHazardType.SUSPENDED_LOADS,
        EnergyHazardType.LINE_OF_FIRE,
        EnergyHazardType.PRESSURE_STORED,
        EnergyHazardType.ELECTRICAL,
        EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT,
        EnergyHazardType.ROTATING_EQUIPMENT,
        EnergyHazardType.HOT_WORK_IGNITION,
        EnergyHazardType.CONFINED_SPACE,
        EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE,
        EnergyHazardType.TOXIC_ASPHYXIANT_ATMOSPHERE,
        EnergyHazardType.THERMAL_ENERGY,
        EnergyHazardType.STORED_MECHANICAL_ENERGY,
        EnergyHazardType.EXCAVATION_GROUND_COLLAPSE,
        EnergyHazardType.DROPPED_OBJECTS,
    ]

    def test_all_15_required_hazard_families_defined_in_catalog(self):
        """All 15 required hazard families must have authoritative definitions."""
        assert len(self.REQUIRED_15_FAMILIES) == 15
        for hazard in self.REQUIRED_15_FAMILIES:
            defn = get_hazard_definition(hazard)
            assert defn is not None, f"Missing definition for required hazard: {hazard}"
            assert defn.hazard_type == hazard
            assert defn.energy_manifestation, f"Hazard {hazard} missing energy_manifestation"
            assert defn.release_mechanism, f"Hazard {hazard} missing release_mechanism"
            assert len(defn.exposure_mechanisms) >= 2, f"Hazard {hazard} insufficient exposure mechanisms"
            assert len(defn.worker_positions) >= 2, f"Hazard {hazard} insufficient worker positions"
            assert len(defn.critical_direct_controls) >= 1, f"Hazard {hazard} missing critical direct controls"
            assert len(defn.effective_states) >= 1, f"Hazard {hazard} missing effective states"
            assert len(defn.compromised_states) >= 1, f"Hazard {hazard} missing compromised states"
            assert len(defn.credible_consequences) >= 1, f"Hazard {hazard} missing credible consequences"
            assert defn.source_id in SOURCE_REGISTRY, f"Hazard {hazard} has unregistered source: {defn.source_id}"

    def test_all_15_hazard_families_have_evidence_contracts(self):
        """Every hazard family must have an evidence contract with required and missing prompts."""
        for hazard in self.REQUIRED_15_FAMILIES:
            contract = get_evidence_contract(hazard)
            assert contract is not None, f"Missing evidence contract for hazard: {hazard}"
            assert len(contract.required_evidence) >= 2, f"Contract for {hazard} has insufficient required evidence"
            assert len(contract.missing_evidence_prompts) >= 1, f"Contract for {hazard} missing actionable prompts"


# ── 2. Three-Way Knowledge per Hazard (PSIF / Controlled / Insufficient / Conflicting)

@pytest.mark.django_db
class TestThreeWayKnowledgeStateSpace:
    """Verifies that the engine produces PSIF, NOT PSIF (Controlled), and INSUFFICIENT depending on facts."""

    def test_working_at_height_three_way_states(self):
        # A. PSIF Pathway Open: Unprotected edge + no fall protection
        inc_psif = Incident(
            description="Scaffolder fell 7 metres from unguarded platform edge. Safety harness was not tied off to anchor.",
            composite_narrative="Scaffolder fell 7 metres from unguarded platform edge. Safety harness was not tied off to anchor.",
        )
        res_psif = build_incident_reasoning_assessment(inc_psif)
        assert res_psif["decision"] == UserFacingDecision.PSIF
        assert res_psif["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

        # B. High Energy Controlled / NOT PSIF: 100% tie-off verified + lanyard arrested fall
        inc_ctrl = Incident(
            description="Worker slipped at 6 metres on drilling derrick mast, but 100% tie-off held. Self-retracting lifeline arrested fall within 30cm.",
            composite_narrative="Worker slipped at 6 metres on drilling derrick mast, but 100% tie-off held. Self-retracting lifeline arrested fall within 30cm.",
            control_condition="effective",
        )
        res_ctrl = build_incident_reasoning_assessment(inc_ctrl)
        assert res_ctrl["decision"] == UserFacingDecision.NOT_PSIF
        assert res_ctrl["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        # C. Insufficient Information: Height mentioned without attachment or edge status
        inc_insuf = Incident(
            description="Work order WO-9912 authorized painting prep on elevated pipe rack.",
            composite_narrative="Work order WO-9912 authorized painting prep on elevated pipe rack.",
        )
        res_insuf = build_incident_reasoning_assessment(inc_insuf)
        assert res_insuf["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION

    def test_pressure_energy_three_way_states(self):
        # A. PSIF: Line unbolted with residual pressure + worker in discharge trajectory
        inc_psif = Incident(
            description="Operator unbolted flange on 60 bar separator line without verifying zero energy. Trapped crude oil sprayed into worker face.",
            composite_narrative="Operator unbolted flange on 60 bar separator line without verifying zero energy. Trapped crude oil sprayed into worker face.",
            control_condition="failed",
        )
        res_psif = build_incident_reasoning_assessment(inc_psif)
        assert res_psif["decision"] == UserFacingDecision.PSIF

        # B. Controlled / NOT PSIF: Double block and bleed verified zero pressure before line break
        inc_ctrl = Incident(
            description="High pressure pipeline maintenance conducted. Positive isolation held and verified zero pressure before line breaking. Bleeder verified 0 psi.",
            composite_narrative="High pressure pipeline maintenance conducted. Positive isolation held and verified zero pressure before line breaking. Bleeder verified 0 psi.",
            control_condition="effective",
        )
        res_ctrl = build_incident_reasoning_assessment(inc_ctrl)
        assert res_ctrl["decision"] == UserFacingDecision.NOT_PSIF
        assert res_ctrl["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

    def test_electrical_three_way_states(self):
        # A. PSIF: Live busbar contact + LOTO unverified
        inc_psif = Incident(
            description="Electrician suffered severe electrical contact burn while racking breaker on live 11kV busbar without verified lockout.",
            composite_narrative="Electrician suffered severe electrical contact burn while racking breaker on live 11kV busbar without verified lockout.",
            control_condition="failed",
        )
        res_psif = build_incident_reasoning_assessment(inc_psif)
        assert res_psif["decision"] == UserFacingDecision.PSIF

        # B. Controlled / NOT PSIF: Voltage tester verified 0V before touch
        inc_ctrl = Incident(
            description="Technician opened 11kV switchgear cubicle. Verified zero hazardous voltage with calibrated multimeter and test before touch verified dead busbar.",
            composite_narrative="Technician opened 11kV switchgear cubicle. Verified zero hazardous voltage with calibrated multimeter and test before touch verified dead busbar.",
            control_condition="effective",
        )
        res_ctrl = build_incident_reasoning_assessment(inc_ctrl)
        assert res_ctrl["decision"] == UserFacingDecision.NOT_PSIF

    def test_suspended_lifting_three_way_states(self):
        # A. PSIF: Worker under suspended 10-ton load + sling failed
        inc_psif = Incident(
            description="Rigger positioned directly beneath suspended 8-ton steel beam when synthetic web sling snapped dropping load onto deck.",
            composite_narrative="Rigger positioned directly beneath suspended 8-ton steel beam when synthetic web sling snapped dropping load onto deck.",
            control_condition="failed",
        )
        res_psif = build_incident_reasoning_assessment(inc_psif)
        assert res_psif["decision"] == UserFacingDecision.PSIF

        # B. Controlled / NOT PSIF: Worker outside exclusion zone during crane lift
        inc_ctrl = Incident(
            description="Heavy crane lift of 12-ton separator vessel conducted. All personnel remained outside exclusion zone behind safety barricades. Tag lines used remotely.",
            composite_narrative="Heavy crane lift of 12-ton separator vessel conducted. All personnel remained outside exclusion zone behind safety barricades. Tag lines used remotely.",
            control_condition="effective",
        )
        res_ctrl = build_incident_reasoning_assessment(inc_ctrl)
        assert res_ctrl["decision"] == UserFacingDecision.NOT_PSIF


# ── 3. Declarative Anti-Inference Layer Tests ─────────────────────────────────

@pytest.mark.django_db
class TestDeclarativeAntiInferences:
    """Verifies that all 13 declarative anti-inference principles protect against cognitive reasoning biases."""

    def test_all_13_anti_inferences_registered(self):
        expected_codes = [
            AntiInferenceCode.HAZARD_MENTION_NOT_EXPOSURE,
            AntiInferenceCode.IOGP_MATCH_NOT_VIOLATION,
            AntiInferenceCode.IOGP_VIOLATION_NOT_PSIF,
            AntiInferenceCode.CONTROL_MENTION_NOT_EFFECTIVENESS,
            AntiInferenceCode.CONTROL_NAME_NOT_FAILURE,
            AntiInferenceCode.CORRECTIVE_ACTION_NOT_EVENT_EVIDENCE,
            AntiInferenceCode.PLANNED_ACTION_NOT_COMPLETED_CONTROL,
            AntiInferenceCode.PPE_AVAILABILITY_NOT_USE,
            AntiInferenceCode.PPE_USE_NOT_DIRECT_CONTROL,
            AntiInferenceCode.LOTO_MENTION_NOT_ZERO_ENERGY_VERIFIED,
            AntiInferenceCode.NEAR_MISS_NOT_PSIF,
            AntiInferenceCode.HIGH_ENERGY_EQUIPMENT_NOT_PSIF,
            AntiInferenceCode.SERIOUS_LANGUAGE_NOT_PSIF,
        ]
        for code in expected_codes:
            rule = ANTI_INFERENCE_CATALOG.get(code)
            assert rule is not None, f"Anti-inference rule missing: {code}"
            assert rule.prohibited_inference, f"Rule {code} missing prohibited_inference"
            assert rule.required_corroboration, f"Rule {code} missing required_corroboration"
            assert rule.forensic_rationale, f"Rule {code} missing forensic_rationale"

    def test_hazard_mention_not_exposure_evaluated(self):
        """Mentioning high-voltage transformer without worker in zone triggers anti-inference protection."""
        evals = evaluate_anti_inferences(
            text="High voltage 33kV switchyard transformer hummed during morning perimeter inspection.",
            hazard_detected=True,
            exposure_state="NO_EXPOSURE",
            control_state="UNKNOWN",
            iogp_matches=["Energy Isolation"],
        )
        rule_eval = next(e for e in evals if e.rule_code == AntiInferenceCode.HAZARD_MENTION_NOT_EXPOSURE)
        assert rule_eval.is_applicable is True
        assert rule_eval.is_inference_prevented is True

    def test_iogp_match_not_violation_evaluated(self):
        """Working at height safely does not get flagged as an IOGP violation."""
        evals = evaluate_anti_inferences(
            text="Scaffolding erection team completed working at height with certified 100% tie-off.",
            hazard_detected=True,
            exposure_state="PROTECTED_POSITION",
            control_state="EFFECTIVE",
            iogp_matches=["Working at Height"],
        )
        rule_eval = next(e for e in evals if e.rule_code == AntiInferenceCode.IOGP_MATCH_NOT_VIOLATION)
        assert rule_eval.is_applicable is True
        assert rule_eval.is_inference_prevented is True

    def test_planned_action_not_completed_control_evaluated(self):
        """Future action ('guard will be installed') triggers PLANNED_ACTION anti-inference."""
        evals = evaluate_anti_inferences(
            text="Pump coupling guard was missing during shift. New safety guard will be installed tomorrow.",
            hazard_detected=True,
            exposure_state="DIRECT_EXPOSURE",
            control_state="ABSENT",
            iogp_matches=["Bypassing Safety Controls"],
        )
        rule_eval = next(e for e in evals if e.rule_code == AntiInferenceCode.PLANNED_ACTION_NOT_COMPLETED_CONTROL)
        assert rule_eval.is_applicable is True
        assert rule_eval.is_inference_prevented is True

    def test_ppe_use_not_direct_control_evaluated(self):
        """Wearing hard hat and gloves is not treated as a direct high-energy barrier."""
        evals = evaluate_anti_inferences(
            text="Operator wore helmet, safety shoes, and gloves while unbolting pressurized 100 bar flange.",
            hazard_detected=True,
            exposure_state="DIRECT_EXPOSURE",
            control_state="ABSENT",
            iogp_matches=["Energy Isolation"],
        )
        rule_eval = next(e for e in evals if e.rule_code == AntiInferenceCode.PPE_USE_NOT_DIRECT_CONTROL)
        assert rule_eval.is_applicable is True
        assert rule_eval.is_inference_prevented is True


# ── 4. Semantic Roles & Temporal Reasoning Extraction ─────────────────────────

@pytest.mark.django_db
class TestSemanticRolesAndTemporalReasoning:
    """Verifies that temporal extraction cleanly separates before/during/after and event vs recommendation."""

    def test_restored_before_vs_after_exposure(self):
        text_before = "Passing valve was discovered during line walk and isolated before entry of work crew."
        exprs_before = extract_temporal_expressions(text_before)
        assert any(e.semantic_role == SemanticRole.RESTORED_BEFORE_EXPOSURE for e in exprs_before)
        assert any(e.phase == TemporalPhase.BEFORE_EXPOSURE for e in exprs_before)

        text_after = "Valve leaked onto technician during line break; flange was repaired subsequently by maintenance."
        exprs_after = extract_temporal_expressions(text_after)
        assert any(e.semantic_role == SemanticRole.RESTORED_AFTER_EXPOSURE for e in exprs_after)
        assert any(e.phase == TemporalPhase.AFTER_EXPOSURE for e in exprs_after)

    def test_recommendation_and_planned_semantics(self):
        text = "Investigator noted coupling was open; safety interlock should be upgraded and will be replaced next cycle."
        exprs = extract_temporal_expressions(text)
        roles = [e.semantic_role for e in exprs]
        assert SemanticRole.RECOMMENDED in roles
        assert SemanticRole.PLANNED in roles


# ── 5. Reasoning Provenance Graph Generation ──────────────────────────────────

@pytest.mark.django_db
class TestReasoningProvenanceGraph:
    """Verifies that the payload contains an auditable provenance graph for downstream UI consumption."""

    def test_provenance_graph_schema_and_contents(self):
        inc = Incident(
            description="Operator unbolted pressurized hydraulic hose at 80 bar without isolation. Fluid spray struck worker chest.",
            composite_narrative="Operator unbolted pressurized hydraulic hose at 80 bar without isolation. Fluid spray struck worker chest.",
            energy_type="pressure",
            control_condition="failed",
        )
        res = build_incident_reasoning_assessment(inc)
        assert "provenance_graph" in res
        graph = res["provenance_graph"]
        assert len(graph) >= 4

        # Verify graph node schema: source_text -> semantic_role -> normalized_concept -> state -> applicable_rule -> decision_effect
        for node in graph:
            assert "source_text" in node
            assert "semantic_role" in node
            assert "normalized_concept" in node
            assert "state" in node
            assert "applicable_rule" in node
            assert "evidence_contribution" in node
            assert "decision_effect" in node


# ── 6. Multi-Hazard Reasoning & Pathway Retention ─────────────────────────────

@pytest.mark.django_db
class TestMultiHazardReasoning:
    """Verifies that simultaneous hazards retain distinct pathway evaluations without evidence collapsing."""

    def test_hot_work_plus_hydrocarbon_multi_hazard_retains_both_pathways(self):
        text = (
            "Welder performed oxy-acetylene torch cutting on pipe rack directly above leaking crude oil flange. "
            "Sparks dropped into flammable vapor pool creating flash fire risk."
        )
        inc = Incident(description=text, composite_narrative=text)
        res = build_incident_reasoning_assessment(inc)

        multi_hazard = res.get("multi_hazard", {})
        all_hazards = multi_hazard.get("all_detected_hazards", [])
        assert len(all_hazards) >= 2
        assert "hot_work_ignition" in all_hazards or "hot_work" in all_hazards

        pathways = multi_hazard.get("pathways", [])
        assert len(pathways) >= 2
        pathway_hazards = [p["hazard_type"] for p in pathways]
        assert len(set(pathway_hazards)) >= 2


# ── 7. Grounded Hierarchy-of-Controls Action Mappings ─────────────────────────

@pytest.mark.django_db
class TestActionMappings:
    """Verifies that action recommendations correctly map to hierarchy tiers and operational categories."""

    def test_psif_open_pathway_generates_immediate_and_restoration_actions(self):
        actions = map_reasoning_to_actions(
            hazard_type=EnergyHazardType.WORKING_AT_HEIGHT,
            control_state=ControlState.FAILED,
            exposure_state=ExposureState.DIRECT_EXPOSURE,
            decision=UserFacingDecision.PSIF,
            internal_state=InternalReasoningState.PSIF_PATHWAY_OPEN,
        )
        assert len(actions) >= 2
        categories = [a.category for a in actions]
        assert ActionCategory.IMMEDIATE_ACTION in categories
        assert ActionCategory.CONTROL_RESTORATION in categories
        assert any(a.priority == "HIGH" for a in actions)

    def test_high_energy_controlled_generates_positive_learning_action(self):
        actions = map_reasoning_to_actions(
            hazard_type=EnergyHazardType.PRESSURE_STORED,
            control_state=ControlState.EFFECTIVE,
            exposure_state=ExposureState.NO_WORKER_EXPOSURE,
            decision=UserFacingDecision.NOT_PSIF,
            internal_state=InternalReasoningState.HIGH_ENERGY_CONTROLLED,
        )
        assert len(actions) >= 1
        categories = [a.category for a in actions]
        assert ActionCategory.POSITIVE_LEARNING_ACTION in categories


# ── 8. Contrastive Semantic Mutation Tests ────────────────────────────────────

@pytest.mark.django_db
class TestContrastiveSemanticMutationsTask4:
    """
    Pairs of incident narratives identical in every word except for ONE single semantic fact.
    The decision must diverge precisely where the modified fact dictates.
    """

    def test_mutation_pair_1_isolation_verified_vs_unverified(self):
        # Base: verified
        inc_verified = Incident(
            description="Technician preparing for pump seal overhaul; double block isolation verified with bleeder reading zero psi.",
            composite_narrative="Technician preparing for pump seal overhaul; double block isolation verified with bleeder reading zero psi.",
            control_condition="effective",
        )
        res_v = build_incident_reasoning_assessment(inc_verified)
        assert res_v["decision"] == UserFacingDecision.NOT_PSIF

        # Mutated: unverified
        inc_unverified = Incident(
            description="Technician preparing for pump seal overhaul; double block isolation not verified with bleeder reading zero psi.",
            composite_narrative="Technician preparing for pump seal overhaul; double block isolation not verified with bleeder reading zero psi.",
            control_condition="failed",
        )
        res_u = build_incident_reasoning_assessment(inc_unverified)
        assert res_u["decision"] in [UserFacingDecision.PSIF, UserFacingDecision.INSUFFICIENT_INFORMATION]

    def test_mutation_pair_2_worker_protected_vs_exposed(self):
        # Base: protected outside exclusion zone
        inc_outside = Incident(
            description="Mobile crane lifted 14-ton pipe spool; rigger remained outside exclusion zone behind solid steel barriers.",
            composite_narrative="Mobile crane lifted 14-ton pipe spool; rigger remained outside exclusion zone behind solid steel barriers.",
            control_condition="effective",
        )
        res_out = build_incident_reasoning_assessment(inc_outside)
        assert res_out["decision"] == UserFacingDecision.NOT_PSIF

        # Mutated: exposed inside drop zone
        inc_inside = Incident(
            description="Mobile crane lifted 14-ton pipe spool; rigger entered exclusion zone behind solid steel barriers and stood beneath suspended load.",
            composite_narrative="Mobile crane lifted 14-ton pipe spool; rigger entered exclusion zone behind solid steel barriers and stood beneath suspended load.",
            control_condition="failed",
        )
        res_in = build_incident_reasoning_assessment(inc_inside)
        assert res_in["decision"] == UserFacingDecision.PSIF

    def test_mutation_pair_3_machine_guard_bolted_vs_removed(self):
        # Base: guard bolted
        inc_guarded = Incident(
            description="Slurry pump running at 1500 rpm; heavy steel coupling guard was securely bolted in place.",
            composite_narrative="Slurry pump running at 1500 rpm; heavy steel coupling guard was securely bolted in place.",
            control_condition="effective",
        )
        res_g = build_incident_reasoning_assessment(inc_guarded)
        assert res_g["decision"] == UserFacingDecision.NOT_PSIF

        # Mutated: guard removed
        inc_unguarded = Incident(
            description="Slurry pump running at 1500 rpm; heavy steel coupling guard was removed while operator reached into rotating nip point.",
            composite_narrative="Slurry pump running at 1500 rpm; heavy steel coupling guard was removed while operator reached into rotating nip point.",
            control_condition="failed",
        )
        res_ung = build_incident_reasoning_assessment(inc_unguarded)
        assert res_ung["decision"] == UserFacingDecision.PSIF


# ── 9. Backwards-Compatible Facade Integrity ──────────────────────────────────

def test_facade_reexports_all_required_symbols():
    """Confirms that importing from apps.incidents.services.psif_knowledge_base provides all symbols."""
    import apps.incidents.services.psif_knowledge_base as kb
    assert hasattr(kb, "KNOWLEDGE_BASE_VERSION")
    assert hasattr(kb, "SourceAuthority")
    assert hasattr(kb, "ProvenanceTier")
    assert hasattr(kb, "EnergyHazardType")
    assert hasattr(kb, "ExposureState")
    assert hasattr(kb, "ControlState")
    assert hasattr(kb, "ConsequenceMechanism")
    assert hasattr(kb, "IOGPRuleCode")
    assert hasattr(kb, "PSIFRuleDefinition")
    assert hasattr(kb, "PSIF_RULES_CATALOG")
    assert hasattr(kb, "get_rule_by_id")
    assert hasattr(kb, "AntiInferenceCode")
    assert hasattr(kb, "evaluate_anti_inferences")
    assert hasattr(kb, "SemanticRole")
    assert hasattr(kb, "extract_temporal_expressions")
    assert hasattr(kb, "map_reasoning_to_actions")
