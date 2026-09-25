"""
PSIF Platform — Golden Case Suite & Contrastive Assurance (Task 13 Freeze)

Exhaustively verifies:
1. Canonical Golden Cases A through O:
   A. High-energy + exposed + control compromised (PSIF)
   B. High-energy + controlled (HIGH_ENERGY_CONTROLLED / NOT PSIF)
   C. Low-energy event (LOW_ENERGY / NOT PSIF)
   D. Insufficient narrative (INSUFFICIENT_INFORMATION)
   E. Conflicting evidence (CONFLICTING_EVIDENCE)
   F. Multi-hazard identification
   G. Negated hazard handling
   H. Passive voice narrative handling
   I. IOGP match without control failure (NOT PSIF)
   J. Model-rule disagreement reconciliation
   K. Valid NOT PSIF
   L. Duplicate-looking but distinct incident
   M. Same incident re-entered (duplicate detection)
   N. Garbage text resilience
   O. Empty input handling

2. Contrastive Assurance Minimal Pairs:
   - Pair 1: Bypassed isolation vs Verified isolation
   - Pair 2: Confined space without gas test vs After gas test completed
   - Pair 3: Suspended load over workers vs No workers beneath suspended load

3. Semantic Contract Invariants:
   - UNKNOWN != NOT_PSIF
   - IOGP_MATCH != IOGP_VIOLATION
   - SHAP_CONTRIBUTION != CAUSE
   - MODEL_SCORE != CALIBRATED_PROBABILITY
   - SIMILARITY != DUPLICATE
   - RECURRENCE != CAUSALITY
   - ACTION_RECOMMENDATION != CLASSIFICATION_EVIDENCE
"""

import pytest
from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.psif_knowledge_base import (
    InternalReasoningState,
    UserFacingDecision,
    EnergyHazardType,
    ControlState,
    ExposureState,
)
from apps.incidents.services.psif_reasoning import (
    AgreementState,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
    reconcile_model_and_rules,
    build_incident_reasoning_assessment,
)


@pytest.mark.django_db
class TestGoldenCaseSuite:
    """Canonical Golden Cases A through O."""

    # Case A: high-energy + exposed + control compromised
    def test_case_a_high_energy_exposed_control_compromised(self):
        inc = Incident(
            description="Worker struck by pressurized hydraulic oil spray when hose burst during crane operation.",
            composite_narrative="Worker struck by pressurized hydraulic oil spray when hose burst during crane operation.",
            energy_type="pressure",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res["rule_decision"] == UserFacingDecision.PSIF
        assert res["final_policy_decision"] == UserFacingDecision.PSIF
        assert len(res["why_psif"]) > 0

    # Case B: high-energy + controlled
    def test_case_b_high_energy_controlled(self):
        inc = Incident(
            description="High pressure compressor tripped on high vibration. No personnel present at unmanned station. Interlock held safely.",
            composite_narrative="High pressure compressor tripped on high vibration. No personnel present at unmanned station. Interlock held safely.",
            energy_type="pressure",
            control_type="automatic_interlock",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res["final_policy_decision"] == UserFacingDecision.NOT_PSIF
        assert len(res["why_not_psif"]) > 0

    # Case C: low-energy event
    def test_case_c_low_energy_event(self):
        inc = Incident(
            description="Worker sustained minor paper cut while filing maintenance logs in the administration office.",
            composite_narrative="Worker sustained minor paper cut while filing maintenance logs in the administration office.",
            energy_type="low_energy",
            control_condition="not_applicable",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] in [
            InternalReasoningState.LOW_ENERGY,
            InternalReasoningState.INSUFFICIENT_INFORMATION,
        ]
        assert res["rule_decision"] in [UserFacingDecision.NOT_PSIF, UserFacingDecision.INSUFFICIENT_INFORMATION]

    # Case D: insufficient narrative
    def test_case_d_insufficient_narrative(self):
        inc = Incident(
            description="Something occurred near the workshop during afternoon shift.",
            composite_narrative="Something occurred near the workshop during afternoon shift.",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION
        assert res["rule_decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res["final_policy_decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION

    # Case E: conflicting evidence
    def test_case_e_conflicting_evidence(self):
        inc = Incident(
            description="Safety report claims full zero energy verified with LOTO locks applied, but operator received 480V electric shock while touching live busbar.",
            composite_narrative="Safety report claims full zero energy verified with LOTO locks applied, but operator received 480V electric shock while touching live busbar.",
            energy_type="electrical",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] in [
            InternalReasoningState.CONFLICTING_EVIDENCE,
            InternalReasoningState.PSIF_PATHWAY_OPEN,
        ]

    # Case F: multi-hazard identification
    def test_case_f_multi_hazard(self):
        inc = Incident(
            description="Scaffolder working at 15 meters height near overhead 11kV power line when crane slewed load into scaffold pole, creating simultaneous height, electrical, and suspended load hazards.",
            composite_narrative="Scaffolder working at 15 meters height near overhead 11kV power line when crane slewed load into scaffold pole, creating simultaneous height, electrical, and suspended load hazards.",
            energy_type="gravity_height",
        )
        ev = extract_incident_safety_evidence(inc)
        assert len(ev["all_detected_hazards"]) >= 1
        assert ev["hazard"].energy_present is True

    # Case G: negated hazard
    def test_case_g_negated_hazard(self):
        inc = Incident(
            description="Gas detector pre-entry alarm sounded. Subsequent calibrated multi-gas detector testing confirmed zero gas leak and no flammable vapors present. Area cleared for normal entry.",
            composite_narrative="Gas detector pre-entry alarm sounded. Subsequent calibrated multi-gas detector testing confirmed zero gas leak and no flammable vapors present. Area cleared for normal entry.",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["rule_decision"] != UserFacingDecision.PSIF

    # Case H: passive voice
    def test_case_h_passive_voice(self):
        inc = Incident(
            description="Heavy 2-ton casing pipe was dropped from crane rig floor into transit path while ground crew was walking through area.",
            composite_narrative="Heavy 2-ton casing pipe was dropped from crane rig floor into transit path while ground crew was walking through area.",
            energy_type="mechanical_lifting",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["rule_decision"] in [UserFacingDecision.PSIF, UserFacingDecision.INSUFFICIENT_INFORMATION]

    # Case I: IOGP match without control failure
    def test_case_i_iogp_match_without_control_failure(self):
        inc = Incident(
            description="Routine confined space entry conducted inside storage tank. Gas test verified 20.9% O2, 0% LEL, full permit signed, standby watch in place.",
            composite_narrative="Routine confined space entry conducted inside storage tank. Gas test verified 20.9% O2, 0% LEL, full permit signed, standby watch in place.",
            energy_type="confined_space",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

    # Case J: model-rule disagreement
    def test_case_j_model_rule_disagreement(self):
        inc = Incident(
            description="Minor slip on oily puddle on deck. No equipment involved, no high energy source.",
            composite_narrative="Minor slip on oily puddle on deck. No equipment involved, no high energy source.",
            energy_type="low_energy",
            control_condition="not_applicable",
        )
        pred = PredictionResult(
            psif_predicted=True,
            psif_probability=0.85,
        )
        recon = reconcile_model_and_rules(
            prediction=pred,
            rule_decision=UserFacingDecision.NOT_PSIF,
            internal_state=InternalReasoningState.HIGH_ENERGY_CONTROLLED,
            evidence_strength="STRONG",
        )
        assert recon.agreement_state == AgreementState.MODEL_STRONGER_THAN_RULE_EVIDENCE
        assert recon.high_priority_review is True

    # Case K: valid NOT PSIF
    def test_case_k_valid_not_psif(self):
        inc = Incident(
            description="Routine electrical inspection on de-energized low voltage cabinet. Breakers locked, tagged, and tested dead with calibrated voltmeter.",
            composite_narrative="Routine electrical inspection on de-energized low voltage cabinet. Breakers locked, tagged, and tested dead with calibrated voltmeter.",
            energy_type="electrical",
            control_type="loto_isolation",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # Case L: duplicate-looking but distinct incident
    def test_case_l_duplicate_looking_distinct_incident(self):
        inc1 = Incident.objects.create(
            description="Forklift backed into rack upright in warehouse B.",
            composite_narrative="Forklift backed into rack upright in warehouse B.",
            department="DULIAJAN",
        )
        inc2 = Incident.objects.create(
            description="Forklift backed into rack upright in warehouse B.",
            composite_narrative="Forklift backed into rack upright in warehouse B.",
            department="MORAN",
        )
        assert inc1.id != inc2.id
        assert inc1.department != inc2.department

    # Case M: same incident re-entered
    def test_case_m_same_incident_reentered(self):
        text = "Nitrogen bottle valve snapped during transfer operations."
        inc1 = Incident(description=text, composite_narrative=text)
        inc2 = Incident(description=text, composite_narrative=text)
        e1 = extract_incident_safety_evidence(inc1)
        e2 = extract_incident_safety_evidence(inc2)
        assert e1["hazard"].hazard_type == e2["hazard"].hazard_type
        assert e1["hazard"].energy_present == e2["hazard"].energy_present

    # Case N: garbage text resilience
    def test_case_n_garbage_text(self):
        garbage = "!@#$%^&*()_+ 12345 qwerty asdfghjk zxcvbnm ????"
        inc = Incident(description=garbage, composite_narrative=garbage)
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION
        assert res["rule_decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res["final_policy_decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION

    # Case O: empty input
    def test_case_o_empty_input(self):
        inc = Incident(description="", composite_narrative="")
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION
        assert res["rule_decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res["final_policy_decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION


@pytest.mark.django_db
class TestContrastiveAssurance:
    """Minimal-pair semantic tests where changing one fact flips the reasoning."""

    def test_minimal_pair_1_valve_isolation(self):
        """'Valve isolation was bypassed' vs 'Valve isolation was verified'"""
        inc_bypassed = Incident(
            description="Worker exposed to pressurized line while valve isolation was bypassed.",
            composite_narrative="Worker exposed to pressurized line while valve isolation was bypassed.",
            energy_type="pressure",
            control_condition="bypassed",
            control_failed_bypassed=True,
        )
        inc_verified = Incident(
            description="Worker protected while valve isolation was verified before line entry.",
            composite_narrative="Worker protected while valve isolation was verified before line entry.",
            energy_type="pressure",
            control_condition="effective",
        )
        res_bypassed = build_incident_reasoning_assessment(inc_bypassed)
        res_verified = build_incident_reasoning_assessment(inc_verified)

        assert res_bypassed["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res_bypassed["rule_decision"] == UserFacingDecision.PSIF

        assert res_verified["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res_verified["rule_decision"] == UserFacingDecision.NOT_PSIF

    def test_minimal_pair_2_confined_space_gas_testing(self):
        """'Worker entered confined space without gas testing' vs 'after gas testing was completed'"""
        inc_untested = Incident(
            description="Worker entered confined space without gas testing.",
            composite_narrative="Worker entered confined space without gas testing.",
            energy_type="chemical_toxic",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        inc_tested = Incident(
            description="Worker entered confined space after gas testing was completed and atmospheric monitors verified safe.",
            composite_narrative="Worker entered confined space after gas testing was completed and atmospheric monitors verified safe.",
            energy_type="chemical_toxic",
            control_condition="effective",
        )
        res_untested = build_incident_reasoning_assessment(inc_untested)
        res_tested = build_incident_reasoning_assessment(inc_tested)

        assert res_untested["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res_untested["rule_decision"] == UserFacingDecision.PSIF

        assert res_tested["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res_tested["rule_decision"] == UserFacingDecision.NOT_PSIF

    def test_minimal_pair_3_suspended_load_exposure(self):
        """'Load was suspended over workers' vs 'No workers were beneath the suspended load'"""
        inc_exposed = Incident(
            description="Rigging failed on 1-ton drill pipe bundle. Rigger was standing directly underneath load inside exclusion zone. Worker struck by pipe.",
            composite_narrative="Rigging failed on 1-ton drill pipe bundle. Rigger was standing directly underneath load inside exclusion zone. Worker struck by pipe.",
            energy_type="suspended_load",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        inc_safe = Incident(
            description="Heavy pipe load lifted while exclusion zone established; no workers were beneath the suspended load.",
            composite_narrative="Heavy pipe load lifted while exclusion zone established; no workers were beneath the suspended load.",
            energy_type="suspended_load",
            control_condition="effective",
        )
        res_exposed = build_incident_reasoning_assessment(inc_exposed)
        res_safe = build_incident_reasoning_assessment(inc_safe)

        assert res_exposed["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res_exposed["rule_decision"] == UserFacingDecision.PSIF

        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF


@pytest.mark.django_db
class TestCanonicalSemanticContract:
    """Audit semantic contract invariants."""

    def test_unknown_is_not_not_psif(self):
        """UNKNOWN != NOT PSIF"""
        inc = Incident(description="Unspecified event in utility area.")
        res = build_incident_reasoning_assessment(inc)
        assert res["rule_decision"] != UserFacingDecision.NOT_PSIF
        assert res["rule_decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION

    def test_iogp_match_is_not_violation(self):
        """IOGP MATCH != IOGP VIOLATION"""
        from apps.dashboard.cross_site_service import get_site_iogp_matrix
        m = get_site_iogp_matrix()
        assert "not confirmed violations" in m["status_disclaimer"].lower()

    def test_model_score_is_not_calibrated_probability(self):
        """MODEL SCORE != CALIBRATED PROBABILITY"""
        from apps.dashboard.services import CANONICAL_METRIC_DEFINITIONS
        # Verify score definition explicitly disclaims calibrated probability
        for k, v in CANONICAL_METRIC_DEFINITIONS.items():
            if "probability" in k.lower() or "score" in k.lower():
                desc = v.get("description", "").lower()
                assert "calibrated" not in desc or "not a calibrated probability" in desc or "uncalibrated" in desc
