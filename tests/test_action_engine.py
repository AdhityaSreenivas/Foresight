"""
Test Suite: Evidence-Grounded Corrective Action + Next-Step Engine
tests/test_action_engine.py

Verifies:
1. 15-Hazard Family Coverage (Working at Height, Lifting, Line of Fire, Pressure, Electrical,
   Vehicle, Mechanical, Hot Work, Confined Space, Hydrocarbon release, Toxic atmosphere,
   Thermal, Stored mechanical, Excavation, Dropped objects).
2. Four-way Reasoning State Mapping (PSIF_PATHWAY_OPEN, HIGH_ENERGY_CONTROLLED,
   INSUFFICIENT_INFORMATION, CONFLICTING_EVIDENCE).
3. Seven Action Categories (IMMEDIATE_ACTION, CONTROL_RESTORATION, VERIFICATION_ACTION,
   CORRECTIVE_ACTION, PREVENTIVE_ACTION, ESCALATION_ACTION, POSITIVE_LEARNING_ACTION).
4. Qualitative Prioritization (CRITICAL, HIGH, MEDIUM, LOW, INFO).
5. Action Deduplication & Multi-Hazard Merging.
6. Action Traceability & Non-Hallucination (triggering evidence, control, rule, provenance).
7. Anti-Inference & Leakage Quarantine: Modifying corrective_actions text does not alter PSIF decision.
8. API Endpoints: GET /api/incidents/<id>/actions/ and GET /api/incidents/<id>/reasoning/.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.incidents.models import Incident
from apps.incidents.knowledge.controls import ControlState, ControlHierarchyType
from apps.incidents.knowledge.energy_hazards import EnergyHazardType
from apps.incidents.knowledge.sources import SourceAuthority, ProvenanceTier
from apps.incidents.knowledge.psif_rules import InternalReasoningState, UserFacingDecision
from apps.incidents.knowledge.action_mappings import (
    ActionCategory,
    ActionUrgency,
    ActionRecommendation,
    generate_grounded_actions,
    map_reasoning_to_actions,
)
from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment
from apps.incidents.services.action_library import get_corrective_actions, ACTION_LIBRARY_VERSION


# ── 1. 15-Hazard Family Action Coverage Tests ─────────────────────────────────

@pytest.mark.django_db
class TestFifteenHazardFamilyActionCoverage:
    """Verifies that all 15 hazard families generate tailored, evidence-grounded actions."""

    @pytest.mark.parametrize("hazard,keyword_in_title", [
        ("working_at_height", "Elevated Work"),
        ("suspended_loads", "Crane Hoisting"),
        ("line_of_fire", "Release Trajectory"),
        ("pressure_stored", "Pressure Intervention"),
        ("electrical", "Power Disconnect"),
        ("vehicle_mobile_equipment", "Mobile Equipment"),
        ("rotating_equipment", "Machinery E-Stop"),
        ("hot_work_ignition", "Hot Work Ignition"),
        ("confined_space", "Evacuation of Confined Space"),
        ("chemical_flammable", "Emergency Shutdown (ESD)"),
        ("toxic_atmosphere", "Escape Breathing Apparatus"),
        ("thermal_energy", "Steam / Cryogenic"),
        ("stored_mechanical_energy", "Mechanical Adjustment"),
        ("excavation_ground_collapse", "Trench Excavation"),
        ("dropped_objects", "Overhead Drop Hazard Zone"),
    ])
    def test_psif_open_pathway_generates_tailored_immediate_action(self, hazard, keyword_in_title):
        actions = generate_grounded_actions(
            hazard_type=hazard,
            control_state=ControlState.FAILED,
            exposure_state="DIRECT_EXPOSURE",
            decision=UserFacingDecision.PSIF,
            internal_state=InternalReasoningState.PSIF_PATHWAY_OPEN,
            trigger_text=f"Direct exposure to {hazard} with failed barrier.",
        )
        assert len(actions) >= 2
        categories = [a["action_type"] for a in actions]
        assert ActionCategory.IMMEDIATE_ACTION in categories
        assert ActionCategory.CONTROL_RESTORATION in categories

        # Find immediate action
        imm = next(a for a in actions if a["action_type"] == ActionCategory.IMMEDIATE_ACTION)
        assert imm["urgency"] == ActionUrgency.CRITICAL
        assert keyword_in_title.lower() in imm["title"].lower()
        assert imm["hazard"] == hazard
        assert len(imm["verification_steps"]) >= 1
        assert "provenance" in imm or "source" in imm

    @pytest.mark.parametrize("hazard", [
        "working_at_height", "suspended_loads", "line_of_fire", "pressure_stored",
        "electrical", "vehicle_mobile_equipment", "rotating_equipment", "hot_work_ignition",
        "confined_space", "chemical_flammable", "toxic_atmosphere", "thermal_energy",
        "stored_mechanical_energy", "excavation_ground_collapse", "dropped_objects",
    ])
    def test_controlled_capacity_generates_positive_learning_for_all_hazards(self, hazard):
        actions = generate_grounded_actions(
            hazard_type=hazard,
            control_state=ControlState.EFFECTIVE,
            exposure_state="NO_WORKER_EXPOSURE",
            decision=UserFacingDecision.NOT_PSIF,
            internal_state=InternalReasoningState.HIGH_ENERGY_CONTROLLED,
            trigger_text=f"Direct control held effectively under {hazard}.",
        )
        assert len(actions) >= 1
        # First action MUST be positive control learning
        assert actions[0]["action_type"] == ActionCategory.POSITIVE_LEARNING_ACTION
        assert "Document & Share Effective Direct Control Learning" in actions[0]["title"]
        assert actions[0]["urgency"] == ActionUrgency.LOW
        # Must not generate an immediate stop-work action
        categories = [a["action_type"] for a in actions]
        assert ActionCategory.IMMEDIATE_ACTION not in categories


# ── 2. Four-Way Reasoning State Action Mapping Tests ──────────────────────────

@pytest.mark.django_db
class TestReasoningStateActionMatrix:
    """Verifies that actions strictly depend on the 5 canonical internal reasoning states."""

    def test_psif_pathway_open_produces_immediate_restoration_and_escalation(self):
        inc = Incident.objects.create(
            description="Technician cracked pressurized valve at 400 psi without lockout. Fluid sprayed onto chest.",
            composite_narrative="Technician cracked pressurized valve at 400 psi without lockout. Fluid sprayed onto chest.",
            energy_type="pressure",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.PSIF_PATHWAY_OPEN
        actions = res["grounded_actions"]
        assert len(actions) >= 3

        categories = [a["action_type"] for a in actions]
        assert ActionCategory.IMMEDIATE_ACTION in categories
        assert ActionCategory.CONTROL_RESTORATION in categories
        assert ActionCategory.ESCALATION_ACTION in categories

        # Verify urgency and traceability
        imm = next(a for a in actions if a["action_type"] == ActionCategory.IMMEDIATE_ACTION)
        assert imm["urgency"] == ActionUrgency.CRITICAL
        assert "Depressurization" in imm["title"] or "Halt" in imm["title"]
        assert imm["triggering_evidence"] != ""
        assert len(imm["verification_steps"]) >= 2

    def test_high_energy_controlled_produces_positive_learning_and_no_stop_work(self):
        inc = Incident.objects.create(
            description="High pressure bleed fitting sheared at 320 bar during proof test. Blast containment barricade held and testing crew remained inside monitoring trailer.",
            composite_narrative="High pressure bleed fitting sheared at 320 bar during proof test. Blast containment barricade held and testing crew remained inside monitoring trailer. Blast containment barrier held securely and completely contained the 320 bar release.",
            energy_type="pressure",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        actions = res["grounded_actions"]
        assert len(actions) >= 1

        # Must be positive learning
        assert actions[0]["action_type"] == ActionCategory.POSITIVE_LEARNING_ACTION
        assert "Positive" in actions[0]["title"] or "Learning" in actions[0]["title"]

        # Must NOT generate emergency stop work or punitive corrective action
        categories = [a["action_type"] for a in actions]
        assert ActionCategory.IMMEDIATE_ACTION not in categories

    def test_low_energy_produces_proportionate_maintenance_no_escalation(self):
        inc = Incident.objects.create(
            description="Office clerk slipped on damp linoleum in hallway sustaining minor wrist bruise.",
            composite_narrative="Office clerk slipped on damp linoleum in hallway sustaining minor wrist bruise. Caution cone placed near entryway.",
            energy_type="other",
            control_condition="unknown",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.LOW_ENERGY
        actions = res["grounded_actions"]
        assert len(actions) >= 1

        # Must be routine / low urgency
        assert all(a["urgency"] in [ActionUrgency.LOW, ActionUrgency.MEDIUM] for a in actions)
        categories = [a["action_type"] for a in actions]
        assert ActionCategory.IMMEDIATE_ACTION not in categories
        assert ActionCategory.ESCALATION_ACTION not in categories

    def test_insufficient_information_produces_evidence_gathering_actions(self):
        inc = Incident.objects.create(
            description="Minor pneumatic air hose hissed near compressor shed during shift change.",
            composite_narrative="Minor pneumatic air hose hissed near compressor shed during shift change.",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.INSUFFICIENT_INFORMATION
        actions = res["grounded_actions"]
        assert len(actions) >= 1

        # Must be verification / evidence request
        assert actions[0]["action_type"] == ActionCategory.VERIFICATION_ACTION
        assert "Investigation" in actions[0]["title"] or "Evidence" in actions[0]["title"]
        assert "missing" in actions[0]["reason"].lower() or "missing" in actions[0]["triggering_evidence"].lower()

    def test_conflicting_evidence_produces_neutral_verification_and_human_review(self):
        inc = Incident.objects.create(
            description="Worker entered the exclusion zone under the suspended 5-ton drill collar. Worker remained outside the exclusion zone behind the physical barricade.",
            composite_narrative="Worker entered the exclusion zone under the suspended 5-ton drill collar. Worker remained outside the exclusion zone behind the physical barricade.",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.CONFLICTING_EVIDENCE
        actions = res["grounded_actions"]
        assert len(actions) >= 1

        # Must be neutral verification
        ver = actions[0]
        assert ver["action_type"] == ActionCategory.VERIFICATION_ACTION
        assert "Contradictory" in ver["title"] or "Reconcile" in ver["title"]
        assert "contradiction" in ver["reason"].lower() or "contradict" in ver["triggering_evidence"].lower()
        # Must not assume worker entered or stayed outside
        assert "physical inspection" in ver["description"].lower() or "records" in ver["description"].lower()


# ── 3. Action Deduplication & Multi-Hazard Merging Tests ───────────────────────

@pytest.mark.django_db
class TestActionDeduplicationAndMultiHazard:
    """Verifies that multi-hazard incidents merge overlapping operational actions intelligently."""

    def test_multi_hazard_action_merging(self):
        """
        Hot work + Flammable hydrocarbon + Line of fire:
        Should not produce 3 separate 'Stop Work' actions; merges into a unified action.
        """
        actions = generate_grounded_actions(
            hazard_type=EnergyHazardType.HOT_WORK_IGNITION,
            control_state=ControlState.FAILED,
            exposure_state="DIRECT_EXPOSURE",
            decision=UserFacingDecision.PSIF,
            internal_state=InternalReasoningState.PSIF_PATHWAY_OPEN,
            all_detected_hazards=[
                EnergyHazardType.HOT_WORK_IGNITION,
                EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE,
                EnergyHazardType.LINE_OF_FIRE,
            ],
            trigger_text="Welding sparks adjacent to leaking flange in line of fire.",
        )
        assert len(actions) >= 2

        # Count immediate actions
        imm_actions = [a for a in actions if a["action_type"] == ActionCategory.IMMEDIATE_ACTION]
        # Should be merged into 1 consolidated immediate action
        assert len(imm_actions) == 1

        merged_imm = imm_actions[0]
        assert merged_imm["urgency"] == ActionUrgency.CRITICAL
        # Attributed multiple hazards
        assert (
            EnergyHazardType.HOT_WORK_IGNITION in merged_imm["hazard"]
            or "hot_work" in merged_imm["hazard"]
        )

    def test_identical_action_ids_deduplicated(self):
        rec1 = ActionRecommendation(
            action_id="ACT-WAH-IMM-01",
            title="Halt Elevated Work & Evacuate Unprotected Fall Zone",
            action_type=ActionCategory.IMMEDIATE_ACTION,
            urgency=ActionUrgency.CRITICAL,
            description="Immediately cease work on elevated platforms.",
            reason="Gravity fall hazard.",
            triggering_evidence="Worker on edge.",
            hazard="working_at_height",
            control="Fall Arrest",
            control_state="FAILED",
            applicable_rule="Working at Height",
            verification_steps=["Step 1", "Step 2"],
        )
        rec2 = ActionRecommendation(
            action_id="ACT-WAH-IMM-01",
            title="Halt Elevated Work & Evacuate Unprotected Fall Zone",
            action_type=ActionCategory.IMMEDIATE_ACTION,
            urgency=ActionUrgency.HIGH,
            description="Immediately cease work on elevated platforms.",
            reason="Gravity fall hazard.",
            triggering_evidence="Worker on edge.",
            hazard="working_at_height",
            control="Fall Arrest",
            control_state="FAILED",
            applicable_rule="Working at Height",
            verification_steps=["Step 2", "Step 3"],
        )
        from apps.incidents.knowledge.action_mappings import _deduplicate_and_prioritize_actions
        deduped = _deduplicate_and_prioritize_actions([rec1, rec2])
        assert len(deduped) == 1
        assert deduped[0].urgency == ActionUrgency.CRITICAL
        assert len(deduped[0].verification_steps) == 3  # Step 1, Step 2, Step 3


# ── 4. Action Schema & Traceability Contract ───────────────────────────────────

@pytest.mark.django_db
class TestActionSchemaAndTraceability:
    """Verifies that every action satisfies the exact required 14-field contract."""

    REQUIRED_ACTION_FIELDS = [
        "action_id",
        "title",
        "action_type",
        "urgency",
        "description",
        "reason",
        "triggering_evidence",
        "hazard",
        "control",
        "control_state",
        "applicable_rule",
        "verification_steps",
        "source",
        "library_version",
    ]

    def test_all_grounded_actions_have_complete_contract(self):
        inc = Incident.objects.create(
            description="Scaffolder fell from height when lifeline disconnected.",
            composite_narrative="Scaffolder fell from height when lifeline disconnected.",
            energy_type="gravity_height",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        res = build_incident_reasoning_assessment(inc)
        actions = res["grounded_actions"]
        assert len(actions) > 0

        for act in actions:
            for field_name in self.REQUIRED_ACTION_FIELDS:
                assert field_name in act, f"Action {act.get('action_id')} missing required field '{field_name}'"
                assert act[field_name] is not None, f"Action {act.get('action_id')} field '{field_name}' is None"

            # Check verification steps is non-empty list
            assert isinstance(act["verification_steps"], list)
            assert len(act["verification_steps"]) >= 1

            # Check source has provenance tier
            assert "provenance_tier" in act["source"] or "provenance" in act

            # Check urgency is valid enum
            assert act["urgency"] in [
                ActionUrgency.CRITICAL, ActionUrgency.HIGH, ActionUrgency.MEDIUM,
                ActionUrgency.LOW, ActionUrgency.INFO
            ]


# ── 5. Anti-Inference & Quarantine Leakage Tests ──────────────────────────────

@pytest.mark.django_db
class TestAntiInferenceAndQuarantineLeakage:
    """Verifies that corrective action text NEVER contaminates incident reasoning or PSIF decision."""

    def test_corrective_action_text_modification_does_not_alter_psif_decision(self):
        """
        Identical incident narrative with dramatically different corrective_actions text:
        Decision, internal state, hazard, and exposure must remain strictly identical.
        """
        base_narrative = "Hydraulic pressure line at 350 psi parted during pump testing without lockout applied. Worker was struck by flailing hose."

        inc1 = Incident.objects.create(
            description=base_narrative,
            composite_narrative=base_narrative,
            corrective_actions="Replace worn O-ring and issue refresher training to operator.",
            energy_type="pressure",
            control_condition="failed",
        )
        inc2 = Incident.objects.create(
            description=base_narrative,
            composite_narrative=base_narrative,
            corrective_actions="Shut down facility, replace all hydraulic manifolds, and dismiss contractor company.",
            energy_type="pressure",
            control_condition="failed",
        )

        res1 = build_incident_reasoning_assessment(inc1)
        res2 = build_incident_reasoning_assessment(inc2)

        # PSIF decision and reasoning state MUST be 100% identical
        assert res1["decision"] == res2["decision"]
        assert res1["internal_reasoning_state"] == res2["internal_reasoning_state"]
        assert res1["rule_decision"] == res2["rule_decision"]
        assert res1["control_assessment"]["state"] == res2["control_assessment"]["state"]
        assert res1["consequence_pathway"]["pathway_state"] == res2["consequence_pathway"]["pathway_state"]

    def test_recommendation_only_text_does_not_trigger_action_as_failure(self):
        """
        Narrative with verified isolation and a mere future recommendation:
        Must not infer isolation failure or generate corrective action for LOTO.
        """
        narrative = "Double block and bleed isolation was verified with zero pressure. Supervisor recommended reviewing LOTO logs next quarter."
        inc = Incident.objects.create(
            description=narrative,
            composite_narrative=narrative,
            energy_type="pressure",
            control_condition="effective",
        )
        res = build_incident_reasoning_assessment(inc)
        assert res["internal_reasoning_state"] == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        actions = res["grounded_actions"]

        # Must NOT generate corrective action claiming LOTO failed
        for act in actions:
            assert "failed" not in act["triggering_evidence"].lower()
            assert act["action_type"] != ActionCategory.IMMEDIATE_ACTION


# ── 6. Live API Endpoints Verification ────────────────────────────────────────

@pytest.mark.django_db
class TestActionAPIEndpoints:
    """Verifies that both /actions/ and /reasoning/ API views return the grounded action payload."""

    def test_incident_actions_endpoint_returns_200_and_grounded_actions(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="action_analyst",
            password="testpassword123",
            role="analyst",
        )
        client.login(username="action_analyst", password="testpassword123")

        inc = Incident.objects.create(
            description="Operator touched 480V live terminal inside motor control center without lockout.",
            composite_narrative="Operator touched 480V live terminal inside motor control center without lockout.",
            energy_type="electrical",
            control_condition="failed",
            control_failed_bypassed=True,
        )

        url = reverse("incidents_api:incident_actions", kwargs={"pk": inc.id})
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()

        assert data["incident_id"] == str(inc.id)
        assert data["library_version"] == ACTION_LIBRARY_VERSION
        assert "actions" in data
        assert len(data["actions"]) >= 2

        first_act = data["actions"][0]
        assert "action_id" in first_act
        assert "action_type" in first_act
        assert "urgency" in first_act
        assert "triggering_evidence" in first_act
        assert "verification_steps" in first_act

    def test_incident_reasoning_endpoint_includes_grounded_actions(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="reasoning_user",
            password="testpassword123",
            role="analyst",
        )
        client.login(username="reasoning_user", password="testpassword123")

        inc = Incident.objects.create(
            description="Suspended 2-ton load swung into scaffolding when crane rigging failed.",
            composite_narrative="Suspended 2-ton load swung into scaffolding when crane rigging failed.",
            energy_type="suspended_load",
            control_condition="failed",
            control_failed_bypassed=True,
        )

        url = reverse("incidents_api:incident_reasoning", kwargs={"pk": inc.id})
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()

        assert "grounded_actions" in data
        assert isinstance(data["grounded_actions"], list)
        assert len(data["grounded_actions"]) >= 2
        assert "action_interface" in data
        assert "recommended_actions" in data["action_interface"]
