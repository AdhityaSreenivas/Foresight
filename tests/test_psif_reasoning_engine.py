"""
PSIF Platform — Comprehensive Adversarial & Integration Test Suite
for PSIF Domain Knowledge Base & Rule-Grounded Reasoning Engine

Tests all 15 Core Adversarial Scenarios:
A. High energy + direct exposure + control failure -> PSIF (PSIF_PATHWAY_OPEN)
B. High energy + effective control + no exposure -> NOT_PSIF (HIGH_ENERGY_CONTROLLED / Capacity)
C. High energy + nearby worker + protected -> NOT_PSIF (HIGH_ENERGY_CONTROLLED)
D. Hazard detected before exposure -> NOT_PSIF (HIGH_ENERGY_CONTROLLED / Stop Work)
E. Control bypass + direct exposure -> PSIF (PSIF_PATHWAY_OPEN)
F. Control restored before exposure -> NOT_PSIF (HIGH_ENERGY_CONTROLLED)
G. Pressure + verified isolation -> NOT_PSIF (HIGH_ENERGY_CONTROLLED)
H. Pressure + uncontrolled release toward worker -> PSIF (PSIF_PATHWAY_OPEN)
I. Vehicle movement + effective segregation -> NOT_PSIF (HIGH_ENERGY_CONTROLLED)
J. Vehicle movement + worker in path -> PSIF (PSIF_PATHWAY_OPEN)
K. Working at height + effective fall protection -> NOT_PSIF (HIGH_ENERGY_CONTROLLED)
L. Working at height + worker exposed + failed protection -> PSIF (PSIF_PATHWAY_OPEN)
M. Sparse report -> INSUFFICIENT_INFORMATION
N. IOGP rule matched but control is effective -> NOT_PSIF (Never PSIF solely from rule match)
O. Data leakage test: corrective action text never influences inference or rule evaluation.

Plus:
- 10 Diverse Representative / Adversarial Case Traces
- Reconciliation & Decision Policy States
- Evidence Strength Matrix & Missing Evidence Checklist
- API Endpoint Verification (/api/incidents/<pk>/reasoning/)
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.incidents.models import Incident, IOGPRuleTag, IncidentDataQuality
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.psif_knowledge_base import (
    KNOWLEDGE_BASE_VERSION,
    SourceAuthority,
    InternalReasoningState,
    UserFacingDecision,
    EnergyHazardType,
    ExposureState,
    ControlState,
    ConsequencePathwayState,
    IOGPRuleCode,
    PSIF_RULES_CATALOG,
    get_rule_by_id,
)
from apps.incidents.services.psif_reasoning import (
    REASONING_RULESET_VERSION,
    AgreementState,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
    reconcile_model_and_rules,
    generate_constrained_explanation,
    select_grounded_actions,
    build_incident_reasoning_assessment,
)


# ── 1. Knowledge Base Authoritative Structure Tests ───────────────────────────

@pytest.mark.django_db
class TestPSIFKnowledgeBase:
    def test_rules_catalog_has_exact_source_sections(self):
        """Every rule must cite exact source document and section."""
        assert len(PSIF_RULES_CATALOG) >= 12
        for rule in PSIF_RULES_CATALOG:
            assert rule.rule_id.startswith("PSIF-R-")
            assert rule.source_section, f"Rule {rule.rule_id} missing source_section citation"
            assert rule.source in [SourceAuthority.EEI_SCL, SourceAuthority.IOGP_459, SourceAuthority.IOGP_559, SourceAuthority.INDIAN_OISD]

    def test_no_hard_numeric_energy_cutoffs(self):
        """Knowledge base should not enforce arbitrary hard numerical cutoffs as universal rules."""
        for rule in PSIF_RULES_CATALOG:
            # Rule names and descriptions should focus on energy release and barrier condition
            assert "gravity > 2m" not in rule.name.lower()
            assert "pressure > 100 psi" not in rule.name.lower()

    def test_iogp_rules_have_start_work_checks(self):
        from apps.incidents.services.psif_knowledge_base import IOGP_RULE_DEFINITIONS
        assert len(IOGP_RULE_DEFINITIONS) == 9
        for code, data in IOGP_RULE_DEFINITIONS.items():
            assert len(data["start_work_checks"]) >= 3
            assert data["source_section"].startswith("IOGP Report 459")


# ── 2. The 15 Core Adversarial Scenarios (A through O) ─────────────────────────

@pytest.mark.django_db
class TestAdversarialReasoningScenarios:

    # A: High energy + direct exposure + control failure -> PSIF
    def test_scenario_a_high_energy_direct_exposure_control_failure(self):
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

    # B: High energy + effective control + no exposure -> NOT_PSIF (Capacity)
    def test_scenario_b_high_energy_effective_control_no_exposure(self):
        inc = Incident(
            description="High pressure compressor tripped on high vibration. No personnel present at unmanned station. Interlock held safely.",
            composite_narrative="High pressure compressor tripped on high vibration. No personnel present at unmanned station. Interlock held safely.",
            energy_type="pressure",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # C: High energy + nearby worker + protected -> NOT_PSIF (Capacity)
    def test_scenario_c_high_energy_nearby_worker_protected(self):
        inc = Incident(
            description="Hot steam line flange vented unexpectedly. Technicians were nearby but protected behind engineered polycarbonate blast barrier. Nobody exposed.",
            composite_narrative="Hot steam line flange vented unexpectedly. Technicians were nearby but protected behind engineered polycarbonate blast barrier. Nobody exposed.",
            energy_type="thermal",
            control_type="physical_barrier",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # D: Hazard detected before exposure -> NOT_PSIF
    def test_scenario_d_hazard_detected_before_exposure_stop_work(self):
        inc = Incident(
            description="During pre-job Start Work Checks, rigger noticed frayed winch cable. Crew invoked Stop Work Authority and work halted before lifting commenced.",
            composite_narrative="During pre-job Start Work Checks, rigger noticed frayed winch cable. Crew invoked Stop Work Authority and work halted before lifting commenced.",
            energy_type="mechanical_motion",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # E: Control bypass + direct exposure -> PSIF
    def test_scenario_e_control_bypass_direct_exposure(self):
        inc = Incident(
            description="Technician bypassed interlock on centrifuge cover to inspect spinning rotor. Worker exposed directly with hand inside danger zone.",
            composite_narrative="Technician bypassed interlock on centrifuge cover to inspect spinning rotor. Worker exposed directly with hand inside danger zone.",
            energy_type="mechanical_motion",
            control_condition="bypassed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res["rule_decision"] == UserFacingDecision.PSIF

    # F: Control restored before exposure -> NOT_PSIF
    def test_scenario_f_control_restored_before_exposure(self):
        inc = Incident(
            description="Scaffold missing mid-rail was identified prior to shift. Work stopped and guardrails restored properly before scaffolders accessed the deck.",
            composite_narrative="Scaffold missing mid-rail was identified prior to shift. Work stopped and guardrails restored properly before scaffolders accessed the deck.",
            energy_type="gravity_height",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # G: Pressure + verified isolation -> NOT_PSIF
    def test_scenario_g_pressure_verified_isolation(self):
        inc = Incident(
            description="Routine maintenance on high pressure discharge manifold. Positive mechanical blinds installed and zero energy verified before breaking containment.",
            composite_narrative="Routine maintenance on high pressure discharge manifold. Positive mechanical blinds installed and zero energy verified before breaking containment.",
            energy_type="pressure",
            control_type="loto_isolation",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # H: Pressure + uncontrolled release toward worker -> PSIF
    def test_scenario_h_pressure_uncontrolled_release_toward_worker(self):
        inc = Incident(
            description="Pressurized line ruptured at 200 psi. Uncontrolled release sprayed directly in the line of fire toward worker who was splashed.",
            composite_narrative="Pressurized line ruptured at 200 psi. Uncontrolled release sprayed directly in the line of fire toward worker who was splashed.",
            energy_type="pressure",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res["rule_decision"] == UserFacingDecision.PSIF

    # I: Vehicle movement + effective segregation -> NOT_PSIF
    def test_scenario_i_vehicle_movement_effective_segregation(self):
        inc = Incident(
            description="Forklift operating in logistics yard. Pedestrians segregated behind continuous heavy steel guardrail barricade. Nobody exposed.",
            composite_narrative="Forklift operating in logistics yard. Pedestrians segregated behind continuous heavy steel guardrail barricade. Nobody exposed.",
            energy_type="motor_vehicle",
            control_type="physical_barrier",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # J: Vehicle movement + worker in path -> PSIF
    def test_scenario_j_vehicle_movement_worker_in_path(self):
        inc = Incident(
            description="Reversing heavy dump truck with broken backup alarm. Worker caught between truck tailgate and concrete loading bay.",
            composite_narrative="Reversing heavy dump truck with broken backup alarm. Worker caught between truck tailgate and concrete loading bay.",
            energy_type="motor_vehicle",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res["rule_decision"] == UserFacingDecision.PSIF

    # K: Working at height + effective fall protection -> NOT_PSIF
    def test_scenario_k_working_at_height_effective_fall_protection(self):
        inc = Incident(
            description="Scaffolder slipped on wet plank at 10 meters height. Safety harness arrested fall immediately; worker safely lowered without injury.",
            composite_narrative="Scaffolder slipped on wet plank at 10 meters height. Safety harness arrested fall immediately; worker safely lowered without injury.",
            energy_type="gravity_height",
            control_type="fall_protection",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # L: Working at height + worker exposed + failed protection -> PSIF
    def test_scenario_l_working_at_height_failed_protection(self):
        inc = Incident(
            description="Worker fell from elevated platform when unanchored lifeline snapped during scaffold dismantling.",
            composite_narrative="Worker fell from elevated platform when unanchored lifeline snapped during scaffold dismantling.",
            energy_type="gravity_height",
            control_type="fall_protection",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert res["rule_decision"] == UserFacingDecision.PSIF

    # M: Sparse report -> INSUFFICIENT_INFORMATION
    def test_scenario_m_sparse_report_insufficient_information(self):
        inc = Incident(
            description="Oil leak observed on skid.",
            composite_narrative="Oil leak observed on skid.",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION
        assert res["rule_decision"] == UserFacingDecision.INSUFFICIENT_INFORMATION
        assert res["is_sparse_report"] is True
        assert len(res["constrained_explanation"]["missing_evidence_checklist"]) >= 1

    # N: IOGP rule matched but control is effective -> NOT_PSIF
    def test_scenario_n_iogp_rule_matched_but_control_effective(self):
        """IOGP Rule Matched != IOGP Violation != PSIF."""
        inc = Incident.objects.create(
            description="Confined space vessel inspection conducted with permit, continuous 4-gas monitoring, and positive mechanical blinds. Isolated properly.",
            composite_narrative="Confined space vessel inspection conducted with permit, continuous 4-gas monitoring, and positive mechanical blinds. Isolated properly.",
            energy_type="chemical",
            control_condition="effective",
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Confined Space",
            matched_keywords=["confined space"],
            matched_fields=["description"],
            confidence=1.0,
        )
        res = build_incident_reasoning_assessment(inc)
        assert "Confined Space" in res["evidence_summary"]["matched_iogp_rules"]
        # Crucial check: rule matched does NOT trigger PSIF!
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF

    # O: Data leakage test: corrective action text never influences inference
    def test_scenario_o_corrective_action_text_does_not_leak_into_reasoning(self):
        """Presence of severe corrective action phrasing must not contaminate the evidence extraction."""
        inc = Incident(
            description="Minor slip on level walkway. Employee visited clinic for band-aid on knee.",
            composite_narrative="Minor slip on level walkway. Employee visited clinic for band-aid on knee.",
            energy_type="unknown",
            control_condition="effective",
            corrective_actions="Conduct site-wide safety standdown, review corporate crisis escalation plan, and replace all PPE.",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.LOW_ENERGY
        assert res["rule_decision"] == UserFacingDecision.NOT_PSIF


# ── 3. 10 Diverse Representative / Adversarial Case Traces ────────────────────

@pytest.mark.django_db
class TestDiverseRepresentativeCaseTraces:
    """
    Manually inspect and verify 10 diverse cases tracing:
    raw report -> extracted evidence -> rule reasoning -> ML result -> decision policy -> final assessment.
    """
    def test_10_diverse_representative_traces(self):
        cases = [
            # 1. Hot work gas leak with positive gas test
            {
                "narrative": "Welding pipe spool in gas plant. Hot work permit in place, continuous gas testing confirmed 0% LEL, fire watch stationed. Safely contained.",
                "energy": "chemical",
                "cond": "effective",
                "expected_internal": InternalReasoningState.HIGH_ENERGY_CONTROLLED,
                "expected_decision": UserFacingDecision.NOT_PSIF,
            },
            # 2. Electrician working live without LOTO
            {
                "narrative": "Electrician was troubleshooting 440V distribution panel. Breaker lockout was not applied and live wire touched panel enclosure causing arc flash.",
                "energy": "electrical",
                "cond": "failed",
                "expected_internal": InternalReasoningState.PSIF_PATHWAY_OPEN,
                "expected_decision": UserFacingDecision.PSIF,
            },
            # 3. Dropped wrench caught by netting
            {
                "narrative": "Technician dropped 2kg crescent wrench from 15m derrick floor. Dropped object safety netting caught tool. Nobody exposed underneath.",
                "energy": "gravity_height",
                "cond": "effective",
                "expected_internal": InternalReasoningState.HIGH_ENERGY_CONTROLLED,
                "expected_decision": UserFacingDecision.NOT_PSIF,
            },
            # 4. Crane lift over worker in exclusion zone
            {
                "narrative": "Rigging failed on 1-ton drill pipe bundle. Rigger was standing directly underneath load inside exclusion zone. Worker struck by pipe.",
                "energy": "suspended_load",
                "cond": "failed",
                "expected_internal": InternalReasoningState.PSIF_PATHWAY_OPEN,
                "expected_decision": UserFacingDecision.PSIF,
            },
            # 5. Nitrogen purge pre-job abort
            {
                "narrative": "Operator noticed nitrogen supply valve passing prior to vessel entry. Team invoked stop work and purged line before anyone entered.",
                "energy": "chemical",
                "cond": "restored_before_exposure",
                "expected_internal": InternalReasoningState.HIGH_ENERGY_CONTROLLED,
                "expected_decision": UserFacingDecision.NOT_PSIF,
            },
            # 6. High pressure bleed valve failure
            {
                "narrative": "High pressure mud line bleed valve failed during testing. Uncontrolled pressurized mud sprayed directly in worker face causing eye injury.",
                "energy": "pressure",
                "cond": "failed",
                "expected_internal": InternalReasoningState.PSIF_PATHWAY_OPEN,
                "expected_decision": UserFacingDecision.PSIF,
            },
            # 7. Routine office papercut
            {
                "narrative": "Clerk received papercut while filing manifest reports in administrative control room.",
                "energy": "unknown",
                "cond": "effective",
                "expected_internal": InternalReasoningState.LOW_ENERGY,
                "expected_decision": UserFacingDecision.NOT_PSIF,
            },
            # 8. Excavation cave-in with worker inside trench
            {
                "narrative": "Worker inside 3-meter deep trench without shoring or trench box. Trench wall collapsed, partially engulfing worker.",
                "energy": "gravity_height",
                "cond": "absent",
                "expected_internal": InternalReasoningState.PSIF_PATHWAY_OPEN,
                "expected_decision": UserFacingDecision.PSIF,
            },
            # 9. Forklift collision with concrete bollard
            {
                "narrative": "Forklift struck perimeter concrete bollard at low speed while turning. Operator was wearing seatbelt inside ROPS cabin. No personnel exposed.",
                "energy": "motor_vehicle",
                "cond": "effective",
                "expected_internal": InternalReasoningState.HIGH_ENERGY_CONTROLLED,
                "expected_decision": UserFacingDecision.NOT_PSIF,
            },
            # 10. Minimal incomplete report
            {
                "narrative": "Vessel inspection completed.",
                "energy": "unknown",
                "cond": "unknown",
                "expected_internal": InternalReasoningState.INSUFFICIENT_INFORMATION,
                "expected_decision": UserFacingDecision.INSUFFICIENT_INFORMATION,
            },
        ]

        for i, c in enumerate(cases, 1):
            inc = Incident(
                description=c["narrative"],
                composite_narrative=c["narrative"],
                energy_type=c["energy"],
                control_condition=c["cond"],
            )
            res = build_incident_reasoning_assessment(inc)
            assert res["internal_reasoning_state"] == c["expected_internal"], f"Case {i} failed internal state: got {res['internal_reasoning_state']}"
            assert res["rule_decision"] == c["expected_decision"], f"Case {i} failed decision: got {res['rule_decision']}"
            # Verify evidence matrix is populated
            assert len(res["evidence_matrix"]) == 6


# ── 4. Reconciliation & Decision Policy Tests ─────────────────────────────────

@pytest.mark.django_db
class TestMLRuleReconciliationAndPolicy:
    def test_model_and_rule_agree_psif(self):
        pred = PredictionResult(
            psif_predicted=True,
            psif_probability=0.88,
        )
        recon = reconcile_model_and_rules(
            prediction=pred,
            rule_decision=UserFacingDecision.PSIF,
            internal_state=InternalReasoningState.PSIF_PATHWAY_OPEN,
            evidence_strength="STRONG",
        )
        assert recon.agreement_state == AgreementState.MODEL_AND_RULE_AGREE
        assert recon.policy_final_decision == UserFacingDecision.PSIF
        assert recon.high_priority_review is False

    def test_false_negative_risk_triggers_high_priority_review(self):
        """Rule evidence proves PSIF, but statistical model score was low."""
        pred = PredictionResult(
            psif_predicted=False,
            psif_probability=0.15,
        )
        recon = reconcile_model_and_rules(
            prediction=pred,
            rule_decision=UserFacingDecision.PSIF,
            internal_state=InternalReasoningState.PSIF_PATHWAY_OPEN,
            evidence_strength="STRONG",
        )
        assert recon.agreement_state == AgreementState.RULE_EVIDENCE_STRONGER_THAN_MODEL
        assert recon.high_priority_review is True
        assert recon.policy_final_decision == UserFacingDecision.PSIF
        assert "false-negative" in recon.disagreement_reason.lower()

    def test_false_positive_risk_high_energy_controlled(self):
        """Model score was high due to keywords, but direct controls held (Capacity)."""
        pred = PredictionResult(
            psif_predicted=True,
            psif_probability=0.78,
        )
        recon = reconcile_model_and_rules(
            prediction=pred,
            rule_decision=UserFacingDecision.NOT_PSIF,
            internal_state=InternalReasoningState.HIGH_ENERGY_CONTROLLED,
            evidence_strength="STRONG",
        )
        assert recon.agreement_state == AgreementState.MODEL_STRONGER_THAN_RULE_EVIDENCE
        assert recon.high_priority_review is True
        assert recon.policy_final_decision == UserFacingDecision.NOT_PSIF
        assert "Capacity" in recon.disagreement_reason

    def test_critical_data_quality_blocks_decision(self):
        dq = IncidentDataQuality(status=IncidentDataQuality.Status.CRITICAL)
        recon = reconcile_model_and_rules(
            prediction=None,
            rule_decision=UserFacingDecision.PSIF,
            internal_state=InternalReasoningState.PSIF_PATHWAY_OPEN,
            evidence_strength="STRONG",
            dq_record=dq,
        )
        assert recon.agreement_state == AgreementState.DATA_QUALITY_BLOCKED
        assert recon.policy_final_decision == UserFacingDecision.INSUFFICIENT_INFORMATION


# ── 5. Action Engine Positive Learning & Trace Consumption ────────────────────

@pytest.mark.django_db
class TestActionEngineTraceConsumption:
    def test_positive_control_learning_on_capacity(self):
        """When direct control held, recommend positive learning rather than punitive actions."""
        inc = Incident(
            description="Steam pressure relieved safely through automatic trip valve. Barricade prevented entry.",
            composite_narrative="Steam pressure relieved safely through automatic trip valve. Barricade prevented entry.",
            energy_type="thermal",
            control_type="physical_barrier",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        actions = res["grounded_actions"]
        assert len(actions) >= 1
        assert actions[0]["action_type"] == "POSITIVE_LEARNING_ACTION"
        assert "Document & Share Effective Direct Control Learning" in actions[0]["title"]


# ── 6. API Endpoint Verification ──────────────────────────────────────────────

@pytest.mark.django_db
class TestIncidentReasoningAPIEndpoint:
    def test_reasoning_endpoint_returns_200_authenticated(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="reasoning_analyst",
            password="testpassword123",
            role="analyst",
        )
        client.login(username="reasoning_analyst", password="testpassword123")

        inc = Incident.objects.create(
            description="Scaffolder fell from height when lifeline disconnected.",
            composite_narrative="Scaffolder fell from height when lifeline disconnected.",
            energy_type="gravity_height",
            control_condition="failed",
            control_failed_bypassed=True,
        )

        url = reverse("incidents_api:incident_reasoning", kwargs={"pk": inc.id})
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()

        assert data["incident_id"] == str(inc.id)
        assert data["knowledge_base_version"] == KNOWLEDGE_BASE_VERSION
        assert data["reasoning_ruleset_version"] == REASONING_RULESET_VERSION
        assert data["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        assert data["rule_decision"] == UserFacingDecision.PSIF
        assert "evidence_matrix" in data
        assert len(data["evidence_matrix"]) == 6
        assert "reconciliation" in data
        assert "constrained_explanation" in data
        assert "grounded_actions" in data
