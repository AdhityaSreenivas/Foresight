"""
PSIF Reasoning Engine — Forensic Validation & Contrastive Semantic Suite

Tests semantic reasoning correctness on naturally written operational text,
critical contrastive pairs, negation, temporal ordering, and control-state separation.
"""
import pytest
from apps.incidents.models import Incident
from apps.incidents.services.psif_knowledge_base import (
    InternalReasoningState,
    UserFacingDecision,
    EnergyHazardType,
    ExposureState,
    ControlState,
)
from apps.incidents.services.psif_reasoning import (
    build_incident_reasoning_assessment,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
)


# ── 1. Critical Contrastive Semantic Pairs ────────────────────────────────────

@pytest.mark.django_db
class TestContrastiveSemanticPairs:
    """
    Tests the 9 mandatory contrastive pairs where phrasing is similar
    but the underlying physical safety reality inverts.
    """

    def test_pair_a_energy_isolation_verification(self):
        """'Isolation verified' vs 'Isolation not verified'"""
        safe_text = "Mechanic performed line breaking on high pressure hydraulic line. Isolation verified by double block and bleed."
        haz_text = "Mechanic performed line breaking on high pressure hydraulic line. Isolation not verified before breaking flange."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_pair_b_exclusion_zone_worker_positioning(self):
        """'Worker remained outside exclusion zone' vs 'Worker entered exclusion zone'"""
        safe_text = "During 10-ton crane lift operation, worker remained outside exclusion zone behind designated safety barrier."
        haz_text = "During 10-ton crane lift operation, worker entered exclusion zone directly inside the lift radius."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_pair_c_suspended_load_proximity(self):
        """'Load was suspended' vs 'Worker stood beneath suspended load'"""
        safe_text = "During heavy pipe transfer, the 2-ton load was suspended while riggers signaled from safe standoff distance."
        haz_text = "During heavy pipe transfer, the worker stood beneath suspended load while adjusting pipe taglines."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_pair_d_fall_arrest_system(self):
        """'Fall arrest system installed and verified' vs 'Fall arrest system absent'"""
        safe_text = "Scaffolder worked at 6 meters height. Fall arrest system was installed and verified prior to ascending."
        haz_text = "Scaffolder worked at 6 meters height. Fall arrest system was absent on the elevated working platform."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_pair_e_pressure_depressurization(self):
        """'Pressure was fully depressurized' vs 'Residual pressure was released'"""
        safe_text = "Pipefitters opened separator valve manifold. Pressure was fully depressurized to zero bar before unbolting."
        haz_text = "Pipefitters opened separator valve manifold. Residual pressure was released toward workers during unbolting."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_pair_f_pedestrian_vehicle_segregation(self):
        """'Pedestrian remained behind segregation' vs 'Pedestrian entered vehicle path'"""
        safe_text = "Forklift traversed high-traffic loading bay. Pedestrian remained behind segregation walkway barriers."
        haz_text = "Forklift traversed high-traffic loading bay. Pedestrian entered vehicle path directly in front of moving mast."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_pair_g_temporal_control_restoration(self):
        """'Control was restored before exposure' vs 'Exposure occurred before control restoration'"""
        safe_text = "Technicians detected passing valve on hydrocarbon line. Control was restored before exposure of maintenance crew."
        haz_text = "Technicians detected passing valve on hydrocarbon line. Exposure occurred before control restoration by crew."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_pair_h_near_miss_temporal_exposure(self):
        """'Near miss identified before worker exposure' vs 'Near miss occurred after worker exposure'"""
        safe_text = "Crane hoist limit switch failed during pre-use check. Near miss was identified before worker exposure to load."
        haz_text = "Crane hoist limit switch failed during pre-use check. Near miss occurred after worker exposure beneath load."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_pair_i_iogp_rule_mention_vs_event_state(self):
        """Mention in corrective action recommendation does not prove control failure during event"""
        safe_text = "Worker slipped on oily platform walkway. Supervisor noted in corrective actions that IOGP Energy Isolation should be reviewed."
        haz_text = "Worker opened energized switchgear without permit. IOGP Energy Isolation rule violated during event causing flashover."

        res_safe = build_incident_reasoning_assessment(Incident(description=safe_text, composite_narrative=safe_text))
        res_haz = build_incident_reasoning_assessment(Incident(description=haz_text, composite_narrative=haz_text))

        # Safe is minor slip (low energy); IOGP recommendation does not invent a high-energy control failure
        assert res_safe["rule_decision"] == UserFacingDecision.NOT_PSIF
        assert res_safe["internal_reasoning_state"] == InternalReasoningState.LOW_ENERGY

        # Hazardous is actual energized switchgear opened without permit with flashover
        assert res_haz["rule_decision"] == UserFacingDecision.PSIF
        assert res_haz["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN


# ── 2. Negation & Linguistic Robustness ────────────────────────────────────────

@pytest.mark.django_db
class TestNegationAndLinguisticRobustness:
    def test_negative_barrier_installation(self):
        """'No drop zone netting had been installed' correctly detected as absent control"""
        text = "Scaffolder dropped a clamp from 9 meters. No drop zone netting or ground barricades had been installed along walkway."
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)
        assert ev["control"].is_compromised is True
        assert ev["control"].state in [ControlState.ABSENT, ControlState.FAILED]

    def test_coupling_guard_was_removed(self):
        """Passive voice 'guard was removed' detected as compromised control"""
        text = "Mechanic tested motor at 1,780 RPM. The protective mesh coupling guard was removed during rotation check."
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)
        assert ev["control"].is_compromised is True

    def test_unhitched_harness_lanyard(self):
        """Synonym 'unhitched both harness lanyards' detected as bypassed/compromised fall protection"""
        text = "Welder at 5.8 meters unhitched both harness lanyards to walk around brace and fell."
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)
        assert ev["control"].is_compromised is True
        assert ev["exposure"].state == ExposureState.DIRECT_EXPOSURE

    def test_physical_containment_barrier_hit(self):
        """'Hit interior wall of blast containment barricade' detected as effective control (Capacity)"""
        text = "High pressure bleed fitting sheared at 320 bar. High pressure water stream hit the interior wall of blast containment barricade."
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)
        assert ev["control"].state == ControlState.EFFECTIVE
