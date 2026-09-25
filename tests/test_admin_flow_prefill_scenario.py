"""
Tests for Admin Flow Pre-fill SIF Precursor Scenario:
Validates that the scenario produces a strong, realistic, fully classifiable demonstration incident
that executes the canonical PSIF reasoning and IOGP pipeline without classifier workarounds.
"""
import pytest
from django.urls import reverse
from apps.incidents.models import Incident
from apps.admin_flow.pattern_engine import (
    extract_admin_flow_barrier_observations,
    normalize_admin_flow_activity,
    normalize_admin_flow_location,
    ADMIN_FLOW_WORKSPACE,
)
from apps.incidents.services.submission import process_new_incident_submission
from apps.incidents.services.psif_reasoning import (
    extract_incident_safety_evidence,
    evaluate_psif_rules,
)
from apps.incidents.services.decision_trace import build_analytical_assessment
from apps.accounts.models import User
from apps.predictions.models import ModelVersion
from apps.predictions.iogp_classifier import classify_iogp_rules


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        username="test_admin_flow_judge_prefill",
        defaults={
            "email": "test_admin_flow_prefill@foresight.app",
            "first_name": "Demo",
            "last_name": "Judge",
            "role": User.Role.ADMIN_FLOW,
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.role = User.Role.ADMIN_FLOW
    user.save()
    return user


@pytest.fixture
def active_model(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_20260906_202052",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


PREFILL_DATA = {
    "report_type": "near_miss",
    "location": "Compressor Area",
    "department": "Mechanical Maintenance / Gas Compressor Train",
    "job_task": "Pressure-Line Maintenance / Flange Breaking",
    "equipment_involved": "Gas compressor discharge line and isolation valves",
    "description": (
        "During maintenance on the gas compressor discharge line, the maintenance crew prepared to "
        "break containment at a flange after shutting the upstream isolation valve. The required "
        "zero-energy verification had not been completed and energy isolation was not verified before "
        "breaking flange. Residual pressure remained in the line. One technician was positioned "
        "directly in the release path adjacent to the flange while unbolting the connection. A sudden "
        "release of pressurized hydrocarbon gas occurred from the flange toward the technician. The "
        "technician was directly exposed to the release path before moving clear. The incident was "
        "identified as a near miss involving unverified energy isolation and direct worker exposure to "
        "the potential release path."
    ),
    "immediate_cause": (
        "Work stopped immediately upon release. Line was re-isolated, residual pressure safely relieved, "
        "and isolation confirmed. Immediate precursor: failure to complete and independently confirm "
        "zero-energy verification before breaking containment."
    ),
    "witness_statement": (
        "Before the flange was loosened, the technician had not received confirmation that zero energy "
        "had been verified. A residual release was observed when the connection was opened."
    ),
    "corrective_actions": (
        "Require documented zero-energy verification and independent confirmation of isolation before "
        "breaking containment on pressurized lines. Reinforce verification-before-touch requirements for maintenance activities."
    ),
    "high_energy_present": "yes",
    "energy_type": "pressure",
    "direct_control_present": "yes",
    "control_condition": "unknown",
}


@pytest.mark.django_db
class TestAdminFlowPrefillScenario:
    """Test suite verifying the redesigned SIF precursor pre-fill scenario."""

    def test_prefill_button_rendered_in_submit_report_page(self, client, admin_flow_user):
        """Verify the Submit Report template includes the pre-fill button and updated scenario values."""
        client.force_login(admin_flow_user)
        url = reverse("admin_flow:submit")
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()

        assert "btn-prefill-scenario" in content
        assert "Pre-fill SIF Precursor Scenario" in content
        assert "Compressor Area" in content
        assert "Mechanical Maintenance / Gas Compressor Train" in content
        assert "Pressure-Line Maintenance / Flange Breaking" in content
        assert "Gas compressor discharge line and isolation valves" in content
        assert "energy isolation was not verified before breaking flange" in content

    def test_canonical_iogp_classifier_produces_only_energy_isolation(self):
        """Verify the canonical IOGP classifier matches Energy Isolation and ONLY Energy Isolation."""
        fields = {
            "description": PREFILL_DATA["description"],
            "job_task": PREFILL_DATA["job_task"],
            "equipment_involved": PREFILL_DATA["equipment_involved"],
            "immediate_cause": PREFILL_DATA["immediate_cause"],
            "composite_narrative": (
                f"{PREFILL_DATA['description']} Immediate cause: {PREFILL_DATA['immediate_cause']}"
            ),
        }
        matches = classify_iogp_rules(fields)
        matched_rule_names = [m["rule"] for m in matches]

        # Must match exactly ONE rule
        assert len(matched_rule_names) == 1, f"Expected exactly 1 IOGP rule, got: {matched_rule_names}"
        assert matched_rule_names[0] == "Energy Isolation"

    def test_reasoning_pipeline_exercises_psif_pathway(self):
        """Verify the deterministic PSIF reasoning engine recognizes the unverified isolation pathway."""
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            **PREFILL_DATA,
        )
        evidence = extract_incident_safety_evidence(inc)

        # 1. Hazard verification
        assert evidence["hazard"].hazard_type == "pressure_stored"

        # 2. Exposure verification (must NOT be EXPOSURE_INTERRUPTED)
        assert evidence["exposure"].state in ["DIRECT_EXPOSURE", "IN_RELEASE_PATH"]

        # 3. Control condition verification
        assert evidence["control"].state == "NOT_VERIFIED"

        # 4. Consequence pathway & rule matching
        decision, path_type, matched_rule, matrix = evaluate_psif_rules(evidence)
        assert decision == "PSIF_PATHWAY_OPEN"
        assert matched_rule is not None
        assert matched_rule.rule_id == "PSIF-R-03"

    def test_end_to_end_submission_and_detail_view(self, client, admin_flow_user, active_model):
        """
        Verify end-to-end incident creation, processing through the canonical pipeline,
        and rendering on the detail page.
        """
        client.force_login(admin_flow_user)
        submit_url = reverse("admin_flow:submit")

        form_payload = {
            **PREFILL_DATA,
            "incident_date": "2026-09-11",
            "action": "submit_and_process",
        }

        resp = client.post(submit_url, data=form_payload, follow=True)
        assert resp.status_code == 200

        # Retrieve created incident
        inc = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).latest("created_at")
        assert inc.location == "Compressor Area"
        assert inc.department == "Mechanical Maintenance / Gas Compressor Train"
        assert inc.job_task == "Pressure-Line Maintenance / Flange Breaking"

        # IOGP Rule verification: exactly ONE tag
        rule_tags = list(inc.iogp_rules.all())
        assert len(rule_tags) == 1
        assert rule_tags[0].rule == "Energy Isolation"

        # Pattern Analysis verification
        barrier_obs = extract_admin_flow_barrier_observations(inc)
        assert len(barrier_obs) >= 1
        assert any("Isolation" in b["control"] or b.get("iogp_rule") == "Energy Isolation" for b in barrier_obs)
        assert any(b["is_deficiency"] is True for b in barrier_obs)

        norm_act, _ = normalize_admin_flow_activity(inc.job_task)
        assert any(term in norm_act for term in ["Flange Breaking", "Pressure-Line", "Pipeline Maintenance", "Valve Work"])

        norm_loc, _, _ = normalize_admin_flow_location(inc)
        assert norm_loc == "Compressor Area"

        # Analytical assessment & detail page rendering
        assessment = build_analytical_assessment(inc)
        psif_reasoning = assessment.get("psif_reasoning", {})
        assert psif_reasoning.get("rule_decision") == "PSIF"
        assert psif_reasoning.get("why_psif") is not None
        assert "Energy Isolation" in psif_reasoning.get("why_psif") or "Stored Energy" in psif_reasoning.get("why_psif")

        # Detail view HTTP check
        detail_url = reverse("admin_flow:incidents_detail", kwargs={"pk": inc.pk})
        detail_resp = client.get(detail_url)
        assert detail_resp.status_code == 200
        content = detail_resp.content.decode()

        # Check badges and reasoning rendered
        assert "Energy Isolation" in content
        assert "YES" in content  # High-energy present
        assert "Pressure" in content  # Energy type
        assert "Rule Pathway: PSIF" in content or "PSIF" in content
