"""
Task 3 — Forensic Validation Regression and Semantic Assurance Suite
Tests natural narrative semantics, contrastive mutations, negation,
temporal ordering, corrective action leakage, IOGP independence, and action traceability.
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
)


# ── 1. Three-Way Semantic Validation Across Major Hazard Families ─────────────

@pytest.mark.django_db
class TestThreeWaySemanticValidationAcrossHazardFamilies:
    """
    Demonstrates that for each major hazard family, varying exposure and control
    evidence produces PSIF, NOT_PSIF, and INSUFFICIENT_INFORMATION deterministically.
    """

    # Family 1: Pressure / Stored Energy
    def test_pressure_threeway(self):
        # Case A: Worker in release path + incomplete isolation -> PSIF
        case_a = "Pipefitter cracked flange on 80 bar condensate line. Isolation was incorrectly applied to wrong valve and residual pressure escaped directly toward worker face."
        res_a = build_incident_reasoning_assessment(Incident(description=case_a, composite_narrative=case_a))
        assert res_a["decision"] == UserFacingDecision.PSIF
        assert res_a["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

        # Case B: Worker outside path + verified isolation -> NOT_PSIF
        case_b = "Pipefitter cracked flange on 80 bar condensate line. Mechanical isolation held throughout and pressure was fully depressurized to zero bar before unbolting."
        res_b = build_incident_reasoning_assessment(Incident(description=case_b, composite_narrative=case_b))
        assert res_b["decision"] == UserFacingDecision.NOT_PSIF
        assert res_b["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        # Case C: Pressure present + worker position unknown -> INSUFFICIENT_INFORMATION
        case_c = "High pressure testing at 250 bar was underway on manifold. Gauge pressure fluctuated abnormally during pressurization."
        res_c = build_incident_reasoning_assessment(Incident(description=case_c, composite_narrative=case_c))
        assert res_c["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res_c["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION

    # Family 2: Working at Height
    def test_working_at_height_threeway(self):
        # Case A: Scaffold worker at 8m + fall arrest unhitched -> PSIF
        case_a = "Scaffolder worked at 8 metres on elevated pipe rack. Harness lanyards were unhitched while repositioning between ledger beams."
        res_a = build_incident_reasoning_assessment(Incident(description=case_a, composite_narrative=case_a))
        assert res_a["decision"] == UserFacingDecision.PSIF
        assert res_a["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

        # Case B: Scaffold worker at 8m + fall arrest verified & connected -> NOT_PSIF
        case_b = "Scaffolder worked at 8 metres on elevated pipe rack. Fall arrest system was installed and verified with 100% tie-off maintained."
        res_b = build_incident_reasoning_assessment(Incident(description=case_b, composite_narrative=case_b))
        assert res_b["decision"] == UserFacingDecision.NOT_PSIF
        assert res_b["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        # Case C: Elevated work + worker position & harness state unrecorded -> INSUFFICIENT_INFORMATION
        case_c = "Scaffolding structure C-412 was erected at elevated platform level in utility area."
        res_c = build_incident_reasoning_assessment(Incident(description=case_c, composite_narrative=case_c))
        assert res_c["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res_c["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION

    # Family 3: Suspended Loads / Lifting
    def test_suspended_loads_threeway(self):
        # Case A: Crane lift + worker beneath suspended load -> PSIF
        case_a = "During 15-ton crane lift, rigger stood beneath suspended load while adjusting synthetic slings."
        res_a = build_incident_reasoning_assessment(Incident(description=case_a, composite_narrative=case_a))
        assert res_a["decision"] == UserFacingDecision.PSIF
        assert res_a["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

        # Case B: Crane lift + exclusion zone maintained & worker remote -> NOT_PSIF
        case_b = "During 15-ton crane lift, rigger remained outside exclusion zone behind designated safety barrier."
        res_b = build_incident_reasoning_assessment(Incident(description=case_b, composite_narrative=case_b))
        assert res_b["decision"] == UserFacingDecision.NOT_PSIF
        assert res_b["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        # Case C: Crane lift + proximity & barrier state unrecorded -> INSUFFICIENT_INFORMATION
        case_c = "Crane hoisting of steel beam package was scheduled at laydown area."
        res_c = build_incident_reasoning_assessment(Incident(description=case_c, composite_narrative=case_c))
        assert res_c["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res_c["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION

    # Family 4: Electrical
    def test_electrical_threeway(self):
        # Case A: 11kV switchgear + absence of voltage not verified + contact trajectory -> PSIF
        case_a = "Electrician began maintenance on 11kV switchgear cubicle. Lock-out/tag-out with independently verified absence of voltage was not maintained, creating direct contact trajectory."
        res_a = build_incident_reasoning_assessment(Incident(description=case_a, composite_narrative=case_a))
        assert res_a["decision"] == UserFacingDecision.PSIF
        assert res_a["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

        # Case B: 11kV switchgear + verified zero hazardous voltage + locked out -> NOT_PSIF
        case_b = "Electrician began maintenance on 11kV switchgear cubicle. Technicians verified zero hazardous voltage and switchgear remained fully locked out throughout."
        res_b = build_incident_reasoning_assessment(Incident(description=case_b, composite_narrative=case_b))
        assert res_b["decision"] == UserFacingDecision.NOT_PSIF
        assert res_b["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        # Case C: Electrical work + isolation condition unrecorded -> INSUFFICIENT_INFORMATION
        case_c = "Substation breaker racking activity was initiated at electrical switchgear building."
        res_c = build_incident_reasoning_assessment(Incident(description=case_c, composite_narrative=case_c))
        assert res_c["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res_c["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION

    # Family 5: Confined Space / Atmospheric
    def test_confined_space_threeway(self):
        # Case A: Borderline oxygen + worker entered without monitoring -> PSIF
        case_a = "Gas testing before confined space entry showed borderline oxygen levels, but entrant entered without continuous monitoring."
        res_a = build_incident_reasoning_assessment(Incident(description=case_a, composite_narrative=case_a))
        assert res_a["decision"] == UserFacingDecision.PSIF
        assert res_a["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

        # Case B: Tank entry + continuous gas testing confirmed safe + forced ventilation -> NOT_PSIF
        case_b = "Before confined space entry into tank, continuous gas testing confirmed zero toxic gas and forced ventilation was active throughout."
        res_b = build_incident_reasoning_assessment(Incident(description=case_b, composite_narrative=case_b))
        assert res_b["decision"] == UserFacingDecision.NOT_PSIF
        assert res_b["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

        # Case C: Confined space entry mentioned + gas reading & entry state unrecorded -> INSUFFICIENT_INFORMATION
        case_c = "Permit issued for vessel inspection in crude processing area."
        res_c = build_incident_reasoning_assessment(Incident(description=case_c, composite_narrative=case_c))
        assert res_c["decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res_c["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION


# ── 2. Contrastive Semantic Mutation Tests ────────────────────────────────────

@pytest.mark.django_db
class TestContrastiveSemanticMutations:
    """
    Tests exact contrastive pairs where ONLY ONE key safety fact changes
    and verifies that the engine inverts the relevant decision state.
    """

    def test_pair_1_isolation_verified_vs_not_verified(self):
        text_safe = "Mechanic performed line breaking on high pressure hydraulic line. Isolation was verified before breaking flange."
        text_haz = "Mechanic performed line breaking on high pressure hydraulic line. Isolation was not verified before breaking flange."
        res_safe = build_incident_reasoning_assessment(Incident(description=text_safe, composite_narrative=text_safe))
        res_haz = build_incident_reasoning_assessment(Incident(description=text_haz, composite_narrative=text_haz))
        assert res_safe["decision"] == UserFacingDecision.NOT_PSIF
        assert res_haz["decision"] == UserFacingDecision.PSIF

    def test_pair_2_exclusion_zone_remained_outside_vs_entered(self):
        text_safe = "During heavy crane lifting, worker remained outside exclusion zone behind designated barrier."
        text_haz = "During heavy crane lifting, worker entered exclusion zone directly under the lift radius."
        res_safe = build_incident_reasoning_assessment(Incident(description=text_safe, composite_narrative=text_safe))
        res_haz = build_incident_reasoning_assessment(Incident(description=text_haz, composite_narrative=text_haz))
        assert res_safe["decision"] == UserFacingDecision.NOT_PSIF
        assert res_haz["decision"] == UserFacingDecision.PSIF

    def test_pair_3_fall_arrest_connected_vs_unhitched(self):
        text_safe = "Technician worked at 7 meters elevation. Fall arrest was installed and verified prior to ascending."
        text_haz = "Technician worked at 7 meters elevation. Fall arrest was unhitched both harness lanyards while moving."
        res_safe = build_incident_reasoning_assessment(Incident(description=text_safe, composite_narrative=text_safe))
        res_haz = build_incident_reasoning_assessment(Incident(description=text_haz, composite_narrative=text_haz))
        assert res_safe["decision"] == UserFacingDecision.NOT_PSIF
        assert res_haz["decision"] == UserFacingDecision.PSIF

    def test_pair_4_gas_alarm_stopped_vs_continued(self):
        text_safe = "H2S gas alarm triggered in pit vessel. Work was halted and crew retreated before exposure."
        text_haz = "H2S gas alarm triggered in pit vessel. Work continued live without permit and worker exposed directly."
        res_safe = build_incident_reasoning_assessment(Incident(description=text_safe, composite_narrative=text_safe))
        res_haz = build_incident_reasoning_assessment(Incident(description=text_haz, composite_narrative=text_haz))
        assert res_safe["decision"] == UserFacingDecision.NOT_PSIF
        assert res_haz["decision"] == UserFacingDecision.PSIF

    def test_pair_5_zero_energy_verified_vs_skipped(self):
        text_safe = "During pump overhaul, zero energy was verified and mechanical isolation held throughout."
        text_haz = "During pump overhaul, zero-energy verification was skipped while stored pressure was present and line breaking occurred."
        res_safe = build_incident_reasoning_assessment(Incident(description=text_safe, composite_narrative=text_safe))
        res_haz = build_incident_reasoning_assessment(Incident(description=text_haz, composite_narrative=text_haz))
        assert res_safe["decision"] == UserFacingDecision.NOT_PSIF
        assert res_haz["decision"] == UserFacingDecision.PSIF

    def test_pair_6_worker_outside_release_path_vs_in_path(self):
        text_safe = "Hydrocarbon transfer line vented. Worker remained behind segregation walkway barriers outside the danger zone."
        text_haz = "Hydrocarbon transfer line vented. Worker was in the line of fire when pressurized mist was released toward worker face."
        res_safe = build_incident_reasoning_assessment(Incident(description=text_safe, composite_narrative=text_safe))
        res_haz = build_incident_reasoning_assessment(Incident(description=text_haz, composite_narrative=text_haz))
        assert res_safe["decision"] == UserFacingDecision.NOT_PSIF
        assert res_haz["decision"] == UserFacingDecision.PSIF


# ── 3. Negation Audit ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestNegationAudit:
    """
    Tests whether the engine recognizes negation prefixes and does not
    simply trigger on dangerous keywords when negated.
    """

    def test_negation_did_not_enter_path(self):
        text = "Forklift was moving in loading bay at 12 km/h. Worker did not enter vehicle path and remained behind barrier."
        res = build_incident_reasoning_assessment(Incident(description=text, composite_narrative=text))
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

    def test_negation_not_exposed_no_injury(self):
        text = "100 bar nitrogen line relief valve popped. Personnel were staged outside and nobody exposed, no injury sustained."
        res = build_incident_reasoning_assessment(Incident(description=text, composite_narrative=text))
        assert res["decision"] == UserFacingDecision.NOT_PSIF

    def test_negation_failed_to_isolate_is_compromised(self):
        text = "Operator failed to hold zero pressure during valve unbolting and spray was released toward personnel."
        ev = extract_incident_safety_evidence(Incident(description=text, composite_narrative=text))
        assert ev["control"].is_compromised is True

    def test_negation_without_guard_is_compromised(self):
        text = "Compressor started without reinstalling coupling guard and technician was within pinch point."
        ev = extract_incident_safety_evidence(Incident(description=text, composite_narrative=text))
        assert ev["control"].is_compromised is True
        assert ev["exposure"].state == ExposureState.DIRECT_EXPOSURE


# ── 4. Temporal Audit ─────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTemporalAudit:
    """
    Tests temporal ordering:
    - Restored before exposure != Restored after exposure
    - Planned / Recommended != Actually installed
    """

    def test_control_restored_before_vs_after_exposure(self):
        text_before = "Passing valve identified on crude manifold. Control was restored before exposure of work crew."
        text_after = "Passing valve on crude manifold caused hydrocarbon leak onto technician. Flange was repaired after the event."
        res_before = build_incident_reasoning_assessment(Incident(description=text_before, composite_narrative=text_before))
        res_after = build_incident_reasoning_assessment(Incident(description=text_after, composite_narrative=text_after))
        assert res_before["decision"] == UserFacingDecision.NOT_PSIF
        assert res_before["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res_after["decision"] == UserFacingDecision.PSIF
        assert res_after["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_planned_guard_not_credited_as_installed(self):
        text = "Worker operated rotating winch line. Guard was planned on paper but had not been installed."
        ev = extract_incident_safety_evidence(Incident(description=text, composite_narrative=text))
        assert ev["control"].is_compromised is True
        assert ev["control"].state in [ControlState.PLANNED_ONLY, ControlState.ABSENT, ControlState.FAILED]

    def test_post_incident_recommendation_is_not_control_state_at_event(self):
        text = "Supervisor recommended installing interlocking gate during routine walkaround."
        ev = extract_incident_safety_evidence(Incident(description=text, composite_narrative=text))
        assert ev["control"].state == ControlState.RECOMMENDATION_ONLY


# ── 5. Corrective Action Leakage Audit ────────────────────────────────────────

@pytest.mark.django_db
class TestCorrectiveActionLeakageAudit:
    """
    Ensures that downstream corrective action text does not pollute
    incident reasoning or cause false control failures.
    """

    def test_corrective_action_does_not_corrupt_intact_guard(self):
        narrative = "Technician conducted daily walkaround. Pump guard was intact and rigid barricades were held in place."
        corrective_action = "Action taken: Replace pump guard as preventive maintenance next month."
        inc = Incident(
            description=narrative,
            composite_narrative=narrative,
            corrective_actions=corrective_action,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["control"]["state"] == ControlState.EFFECTIVE

    def test_loto_recommendation_does_not_imply_loto_failure(self):
        narrative = "Operator observed minor condensation drip on cold water line during routine rounds."
        corrective_action = "Supervisor recommended reviewing LOTO compliance at next safety meeting."
        inc = Incident(
            description=narrative,
            composite_narrative=narrative,
            corrective_actions=corrective_action,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.LOW_ENERGY


# ── 6. IOGP Independence Audit ────────────────────────────────────────────────

@pytest.mark.django_db
class TestIOGPIndependenceAudit:
    """
    Verifies that IOGP rule matches do not equate to rule violations or PSIF decisions:
    IOGP_MATCH != IOGP_VIOLATION != PSIF
    """

    def test_iogp_energy_isolation_effective_is_not_psif(self):
        narrative = "During flange unbolting, energy isolation was independently verified by double block and bleed, and isolation valves held absolute isolation."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["iogp_separation"]["iogp_rule_matched"] is True
        assert res["iogp_separation"]["rule_adherence"] in ["COMPLIANT", "ADHERED"]
        assert res["iogp_separation"]["psif_decision"] == UserFacingDecision.NOT_PSIF
        assert res["decision"] == UserFacingDecision.NOT_PSIF

    def test_iogp_energy_isolation_violated_is_psif(self):
        narrative = "During flange unbolting, isolation was not verified before breaking flange and pressurized spray released toward worker face."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        assert res["iogp_separation"]["iogp_rule_matched"] is True
        assert res["iogp_separation"]["rule_adherence"] == "VIOLATED"
        assert res["iogp_separation"]["psif_decision"] == UserFacingDecision.PSIF
        assert res["decision"] == UserFacingDecision.PSIF


# ── 7. Action Traceability & Proportionality Audit ────────────────────────────

@pytest.mark.django_db
class TestActionTraceabilityAudit:
    """
    Verifies that actions are traceable to actual evidence, address relevant controls,
    and avoid dramatic actions on controlled cases.
    """

    def test_effective_control_avoids_high_urgency_corrective_action(self):
        narrative = "15-ton crane lift executed. Rigger remained outside exclusion zone behind designated barrier. Lift path was controlled."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        actions = res.get("grounded_actions", [])
        # In effective control, action is positive control learning or low/medium urgency verification
        for act in actions:
            if "positive_control" in act.get("action_type", ""):
                assert act.get("urgency") in ["low", "medium", "LOW", "MEDIUM"]

    def test_open_psif_pathway_generates_high_urgency_engineered_barrier_action(self):
        narrative = "Worker at 8 metres unhitched both harness lanyards and fell to lower deck sustaining fractures."
        inc = Incident(description=narrative, composite_narrative=narrative)
        res = build_incident_reasoning_assessment(inc)
        actions = res.get("grounded_actions", [])
        assert len(actions) > 0
        has_high_priority = any(a.get("urgency") in ["high", "immediate", "HIGH", "IMMEDIATE"] for a in actions)
        assert has_high_priority is True


# ── 8. Real Database Incidents Forensic Regression ────────────────────────────

@pytest.mark.django_db
class TestRealDatabaseIncidentsForensicRegression:
    """
    Verifies the real-world database cases discovered during forensic audit
    (Cases 1, 8, 15, 16, 18, 20, 60, 63, 67, 71).
    """

    def test_case_01_confined_space_oxygen_monitoring_bypass(self):
        text = "Gas testing before confined space entry into an overhead crane hook block at Numaligarh Refinery - Tank Farm showed borderline oxygen levels, but the panel operator entered without continuous monitoring; the near miss was reported immediately by the shift supervisor as having high fatal potential."
        inc = Incident(description=text, composite_narrative=text, job_task="Confined Space")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_case_08_mechanic_agitator_isolation_prevented_entry(self):
        text = "21:10 — Mechanic was working on agitator at the electrical substation. The maintenance task placed personnel close to moving or energized equipment, but the relevant isolation and physical guarding were established before access to the workface. The direct control and isolation prevented personnel from entering the movement or energy path."
        inc = Incident(description=text, composite_narrative=text, job_task="Mechanical Maintenance")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

    def test_case_15_delivery_truck_reversing_alarm_held(self):
        text = "The shift log noted vehicle movement at the laydown yard. Delivery truck DT-6587 was positioned at the work point. The reversing alarm check at DT-6587 held throughout, and the forklift operator stayed outside the reversing zone."
        inc = Incident(description=text, composite_narrative=text, job_task="vehicle movement")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

    def test_case_16_switchgear_lockout_degraded_arc_flash_risk(self):
        text = "Electrical testing continued at control building. Switchgear cubicle SG-6468 was positioned at the work point. The lockout verification at SG-6468 had degraded, and the energized-panel interface was not closed off from the electrical supervisor. This condition carried a credible risk of arc-flash burn."
        inc = Incident(description=text, composite_narrative=text, job_task="Electrical Maintenance")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_case_18_11kv_switchgear_absence_of_voltage_not_maintained(self):
        text = "Work scope: electrical isolation on 11kV switchgear (D-553). Hazard present: stored electrical energy. Lock-out/tag-out with independently verified absence of voltage was not maintained for the duration of the task. The layout meant the HSE advisor could not avoid contact with live parts or arc-flash exposure."
        inc = Incident(description=text, composite_narrative=text, job_task="Electrical Maintenance")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_case_20_pipeline_leak_sealing_tested_and_functioning(self):
        text = "Pressure reduction to a safe working level with a verified leak-sealing procedure before crew approach was tested and demonstrated to be functioning as intended before installation of a mechanical repair clamp on a pressurized pipeline began."
        inc = Incident(description=text, composite_narrative=text, job_task="pipeline repair")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

    def test_case_60_filter_vessel_pyrophoric_scale_unverified(self):
        text = "Filter vessel (E-651) required internal cleaning of a pressure vessel with pyrophoric scale and trapped pressure. The vacuum truck operator remained within reach of an uncontrolled release of pressure while work continued. Depressurization/venting verification was assumed to be in place but was never independently verified."
        inc = Incident(description=text, composite_narrative=text, job_task="internal cleaning of a pressure vessel")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_case_63_hydrocarbon_line_breaking_wrong_isolation_point(self):
        text = "Prior to line breaking on hydrocarbon service at 12-inch crude header (E-152), positive isolation was incorrectly applied to the wrong isolation point. The trajectory pointed toward a high-pressure hydrocarbon spray impacting the technician."
        inc = Incident(description=text, composite_narrative=text, job_task="line breaking on hydrocarbon service")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN

    def test_case_67_energy_isolation_independently_verified_controlled(self):
        text = "Carrying out energy isolation in the tank farm. Isolation was independently verified before the line was opened. The lifting path was controlled before isolation work proceeded. The control was effective before personnel entered the hazard area."
        inc = Incident(description=text, composite_narrative=text, job_task="Energy Isolation")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED

    def test_case_71_pump_overhaul_mechanical_isolation_held(self):
        text = "Pump overhaul in workshop. Mechanical isolation at SA-1787 held throughout, and the maintenance supervisor stayed outside the drive-train envelope. The condition was corrected before any credible exposure developed."
        inc = Incident(description=text, composite_narrative=text, job_task="pump overhaul")
        res = build_incident_reasoning_assessment(inc)
        assert res["decision"] == UserFacingDecision.NOT_PSIF
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
