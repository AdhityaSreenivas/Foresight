"""
PSIF Platform — Semantic Assurance & Golden Trace Regression Test Suite

Tests:
1. Material Contradiction Detection (4 required contradiction scenarios)
2. Multi-Hazard Extraction and Representation
3. Golden Reasoning Traces (8 canonical scenarios in tests/fixtures/golden_reasoning_traces.json)
4. Comprehensive API Schema & Contract Verification (Section 11)
"""

import json
from pathlib import Path
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.psif_knowledge_base import (
    InternalReasoningState,
    UserFacingDecision,
)
from apps.incidents.services.psif_reasoning import (
    AgreementState,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
    reconcile_model_and_rules,
    build_incident_reasoning_assessment,
    detect_evidence_contradictions,
)

User = get_user_model()


# ── Test Suite 1: Material Contradiction Detection ────────────────────────────

@pytest.mark.django_db
class TestMaterialContradictionDetection:
    """
    Verifies that contradictory claims in incident narratives are flagged as CONFLICTING_EVIDENCE
    rather than silently favoring one claim over the other.
    """

    def test_contradiction_isolation_verified_and_valve_passing(self):
        """Claim of verified isolation contradicted by evidence of passing valve."""
        text = (
            "Permit confirmed zero energy isolation verified and signed off. "
            "However, during line break, the isolation valve was found passing steam at 14 bar."
        )
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)
        
        assert ev["is_conflicting_evidence"] is True
        assert "isolation" in ev["contradiction_details"].lower()
        assert "passing" in ev["contradiction_details"].lower()

        state, decision, rule, matrix = evaluate_psif_rules(ev)
        assert state == InternalReasoningState.CONFLICTING_EVIDENCE
        assert decision == UserFacingDecision.INSUFFICIENT_INFORMATION

    def test_contradiction_outside_zone_and_entered_zone(self):
        """Claim that worker remained outside exclusion zone contradicted by entry/strike inside zone."""
        text = (
            "Riggers ensured all crew remained outside exclusion zone during tandem lift. "
            "However, the helper entered the exclusion zone to retrieve a tag line and was hit by the headache ball."
        )
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)
        
        assert ev["is_conflicting_evidence"] is True
        assert "exclusion zone" in ev["contradiction_details"].lower()

        state, decision, rule, matrix = evaluate_psif_rules(ev)
        assert state == InternalReasoningState.CONFLICTING_EVIDENCE
        assert decision == UserFacingDecision.INSUFFICIENT_INFORMATION

    def test_contradiction_harness_installed_and_lanyard_unhitched(self):
        """Claim that fall arrest was verified contradicted by worker unhitching lanyards."""
        text = (
            "Full body harness was installed and verified prior to ascending scaffold tower. "
            "The scaffold builder unhitched both harness lanyards while repositioning and lost footing."
        )
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)
        
        assert ev["is_conflicting_evidence"] is True
        assert "harness" in ev["contradiction_details"].lower()

        state, decision, rule, matrix = evaluate_psif_rules(ev)
        assert state == InternalReasoningState.CONFLICTING_EVIDENCE
        assert decision == UserFacingDecision.INSUFFICIENT_INFORMATION

    def test_contradiction_work_stopped_before_exposure_and_injury_occurred(self):
        """Claim that stop work halted exposure contradicted by worker sustaining injury."""
        text = (
            "Supervisor enacted stop work authority before worker exposure occurred. "
            "The technician was struck in the face and fractured jaw when the pressurized fitting parted."
        )
        inc = Incident(description=text, composite_narrative=text, injury_type="fracture", body_part="jaw")
        ev = extract_incident_safety_evidence(inc)
        
        assert ev["is_conflicting_evidence"] is True
        assert "halted" in ev["contradiction_details"].lower() or "stopped" in ev["contradiction_details"].lower()

        state, decision, rule, matrix = evaluate_psif_rules(ev)
        assert state == InternalReasoningState.CONFLICTING_EVIDENCE
        assert decision == UserFacingDecision.INSUFFICIENT_INFORMATION


# ── Test Suite 2: Multi-Hazard Extraction ─────────────────────────────────────

@pytest.mark.django_db
class TestMultiHazardExtraction:
    """
    Verifies that multi-hazard incidents preserve all detected hazard families rather than
    collapsing to a single keyword match.
    """

    def test_pressure_plus_hot_work_multi_hazard(self):
        """Simultaneous high-pressure gas release and hot work sparks are both captured."""
        text = (
            "High pressure natural gas line at 40 bar leaked flammable vapor while hot work "
            "structural welding was actively underway 3 meters away. Welding sparks ignited a flash fire."
        )
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)

        hazards = ev.get("all_detected_hazards", [])
        assert len(hazards) >= 2
        assert "pressure_stored" in hazards
        assert "chemical_flammable" in hazards

    def test_confined_space_plus_toxic_atmosphere(self):
        """Confined space entry with toxic H2S atmosphere captures multiple hazards."""
        text = (
            "Tank cleaning technician entered crude storage vessel (confined space) without entry permit. "
            "Toxic hydrogen sulfide (H2S gas) was detected at 45 ppm, causing dizziness and collapse."
        )
        inc = Incident(description=text, composite_narrative=text)
        ev = extract_incident_safety_evidence(inc)

        hazards = ev.get("all_detected_hazards", [])
        assert len(hazards) >= 2
        assert "confined_space" in hazards
        assert "chemical_flammable" in hazards


# ── Test Suite 3: Golden Reasoning Traces ─────────────────────────────────────

@pytest.mark.django_db
class TestGoldenReasoningTraces:
    """
    Loads canonical test fixtures from tests/fixtures/golden_reasoning_traces.json
    and asserts end-to-end evaluation against Foresight's reasoning engine.
    """

    @pytest.fixture
    def golden_fixtures(self):
        fixture_path = Path(__file__).parent / "fixtures" / "golden_reasoning_traces.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            return json.load(f)["fixtures"]

    def test_golden_fixtures_end_to_end(self, golden_fixtures):
        for fix in golden_fixtures:
            fix_id = fix["id"]
            inc_data = fix["incident"]
            pred_data = fix.get("prediction")
            expected = fix["expected"]

            incident = Incident(
                description=inc_data["description"],
                composite_narrative=inc_data.get("composite_narrative", inc_data["description"]),
                injury_type=inc_data.get("injury_type", "none"),
                body_part=inc_data.get("body_part", "none"),
            )

            prediction = None
            if pred_data:
                prediction = PredictionResult(
                    psif_probability=pred_data["psif_score"],
                    psif_predicted=pred_data["psif_predicted"],
                )

            # Build full reasoning assessment
            assessment = build_incident_reasoning_assessment(incident, prediction=prediction)

            # 1. Verify policy decision
            assert assessment["decision"] == expected["decision"], (
                f"[{fix_id}] Decision mismatch: expected {expected['decision']}, got {assessment['decision']}"
            )

            # 2. Verify internal reasoning state
            if "internal_reasoning_state" in expected:
                assert assessment["internal_reasoning_state"] == expected["internal_reasoning_state"], (
                    f"[{fix_id}] State mismatch: expected {expected['internal_reasoning_state']}, got {assessment['internal_reasoning_state']}"
                )

            # 3. Verify reconciliation & disagreement types
            recon = assessment["reconciliation"]
            if "agreement_state" in expected:
                assert recon["agreement_state"] == expected["agreement_state"], (
                    f"[{fix_id}] Agreement state mismatch: expected {expected['agreement_state']}, got {recon['agreement_state']}"
                )
            if "disagreement_type" in expected:
                assert recon.get("disagreement_type") == expected["disagreement_type"], (
                    f"[{fix_id}] Disagreement type mismatch: expected {expected['disagreement_type']}, got {recon.get('disagreement_type')}"
                )

            # 4. Verify contradiction flag
            if "is_conflicting" in expected:
                assert (assessment["internal_reasoning_state"] == InternalReasoningState.CONFLICTING_EVIDENCE) == expected["is_conflicting"]

            # 5. Verify multi-hazard detections if specified
            if "min_detected_hazards" in expected:
                all_hazards = assessment["multi_hazard"]["all_detected_hazards"]
                assert len(all_hazards) >= expected["min_detected_hazards"], (
                    f"[{fix_id}] Expected at least {expected['min_detected_hazards']} hazards, got {all_hazards}"
                )
            if "required_hazards" in expected:
                all_hazards = assessment["multi_hazard"]["all_detected_hazards"]
                for req_h in expected["required_hazards"]:
                    assert req_h in all_hazards, f"[{fix_id}] Expected hazard {req_h} not in {all_hazards}"

            # 6. Verify why_psif or why_not_psif is informative
            if assessment["decision"] == UserFacingDecision.PSIF:
                assert len(assessment["why_psif"]) > 20
            elif assessment["decision"] == UserFacingDecision.NOT_PSIF:
                assert len(assessment["why_not_psif"]) > 20
            else:
                assert len(assessment["what_information_would_close_case"]) > 0


# ── Test Suite 4: Comprehensive API Schema & Contract Verification ────────────

@pytest.mark.django_db
class TestReasoningAPIEndpointContract:
    """
    Verifies that GET /api/incidents/<uuid:pk>/reasoning/ strictly complies with
    the Section 11 API schema required by the Why PSIF / Why NOT PSIF UX.
    """

    @pytest.fixture
    def auth_client(self):
        user = User.objects.create_user(username="hse_auditor", password="secure_password_123")
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    @pytest.fixture
    def test_incident(self):
        mv = ModelVersion.objects.create(version_label="psif_lgbm_prod_v2", is_active=True)
        inc = Incident.objects.create(
            description="Operator struck by pressurized line during unverified pressure test at 180 bar.",
            composite_narrative="Operator struck by pressurized line during unverified pressure test at 180 bar. Isolation had not been verified and no bleeder was opened.",
            injury_type="fracture",
            body_part="arm",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=mv,
            psif_probability=0.915,
            psif_predicted=True,
        )
        return inc

    def test_api_returns_all_section_11_fields(self, auth_client, test_incident):
        url = f"/api/incidents/{test_incident.id}/reasoning/"
        response = auth_client.get(url)
        assert response.status_code == 200
        data = response.json()

        # Check all required Section 11 keys
        required_keys = [
            "decision",
            "internal_reasoning_state",
            "evidence_strength",
            "reasoning_chain",
            "evidence_matrix",
            "what_is_known",
            "what_is_missing",
            "why_psif",
            "why_not_psif",
            "rules_applied",
            "control",
            "consequence_pathway",
            "reconciliation",
            "high_priority_review",
            "grounded_actions",
            "knowledge_base_version",
            "reasoning_ruleset_version",
            "action_library_version",
            "source_provenance",
        ]
        for k in required_keys:
            assert k in data, f"Required Section 11 key '{k}' missing from API response!"

        # Check reasoning chain has all 8 steps in order
        expected_steps = [
            "Hazard Identification",
            "Worker Exposure",
            "Critical Control State",
            "Barrier Interruption",
            "Consequence Pathway",
            "Evidence Sufficiency",
            "Rule Assessment",
            "Model Reconciliation",
        ]
        actual_steps = [s["step"] for s in data["reasoning_chain"]]
        assert actual_steps == expected_steps, f"Reasoning chain steps mismatch: {actual_steps}"

        # Check grounded actions have full traceability fields
        for act in data["grounded_actions"]:
            assert "action_id" in act
            assert "title" in act
            assert "triggering_evidence" in act
            assert "control_addressed" in act
            assert "rule_addressed" in act
            assert "urgency" in act
            assert "verification_method" in act

        # Check reconciliation contains model score without misleading "confidence"
        assert "model_score" in data["reconciliation"]
        assert "evidence_strength" in data
        assert data["evidence_strength"] in ["STRONG", "MODERATE", "WEAK"]
