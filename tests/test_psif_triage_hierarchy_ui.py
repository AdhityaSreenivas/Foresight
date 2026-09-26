import pytest
from unittest.mock import patch
from rest_framework.test import APIClient
from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.decision_trace import build_analytical_assessment
from apps.accounts.models import User

@pytest.fixture
def test_setup(db):
    user = User.objects.create_user(
        username="admin_triage",
        email="admin@example.com",
        password="password123",
        role=User.Role.ADMIN_FLOW,
        is_staff=True,
        is_superuser=True
    )
    admin_user = User.objects.create_user(
        username="admin_full",
        email="admin_full@example.com",
        password="password123",
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=True
    )
    mv = ModelVersion.objects.create(
        version_label="v1.0.0-triage-test",
        is_active=True,
        metrics={"optimal_threshold": 0.5, "selected_threshold": 0.5}
    )
    client = APIClient()
    client.force_authenticate(user=user)
    client.force_login(user)

    admin_client = APIClient()
    admin_client.force_authenticate(user=admin_user)
    admin_client.force_login(admin_user)

    return {"user": user, "admin_user": admin_user, "mv": mv, "client": client, "admin_client": admin_client}

@pytest.mark.django_db
class TestPSIFTriageHierarchyUI:
    """
    Test suite for the 3-stage safety triage hierarchy:
    1. MODEL OUTPUT
    2. EVIDENCE ASSESSMENT
    3. FINAL TRIAGE STATUS
    Ensures that Model Candidate != Final Classification is clear, unambiguous,
    and tested across all four canonical test cases (A, B, C, D).
    """

    def test_case_a_model_psif_evidence_interrupted_final_not_psif(self, test_setup):
        """
        Case A:
        Model: PSIF candidate (score >= threshold)
        Evidence: effective control / interrupted pathway
        Final: NOT PSIF
        Expected UI:
        - MODEL OUTPUT -> PSIF CANDIDATE
        - EVIDENCE ASSESSMENT -> Consequence Pathway: Interrupted / Barrier: Effective
        - FINAL TRIAGE STATUS -> NOT PSIF
        """
        mv = test_setup["mv"]
        inc = Incident.objects.create(
            description="High pressure nitrogen valve relief popped. Isolation barrier was closed immediately with zero leakage and no worker was nearby.",
            job_task="Pressure Testing",
            equipment_involved="Isolation Valve",
            control_condition="effective",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=mv,
            psif_probability=0.785,
            psif_predicted=True,
            risk_level="HIGH"
        )

        assessment = build_analytical_assessment(inc)
        stages = assessment["triage_stages"]

        assert stages["model_output"]["is_candidate"] is True
        assert stages["model_output"]["candidate_label"] == "PSIF CANDIDATE"
        assert "0.785" in stages["model_output"]["score_formatted"]
        assert stages["model_output"]["score_label"] == "PSIF MODEL SCORE"

        assert "Effective" in stages["evidence_assessment"]["barrier_state"]
        assert stages["evidence_assessment"]["consequence_pathway"] == "Interrupted"

        assert stages["final_triage"]["status"] == "NOT PSIF"
        assert "interrupted" in stages["final_triage"]["reason"].lower() or "control" in stages["final_triage"]["reason"].lower()

        # Verify incident detail rendering
        client = test_setup["client"]
        resp = client.get(f"/incidents/{inc.id}/")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "STAGE 1 &mdash; MODEL OUTPUT" in content
        assert "PSIF CANDIDATE" in content
        assert "STAGE 2 &mdash; EVIDENCE ASSESSMENT" in content
        assert "STAGE 3 &mdash; FINAL TRIAGE STATUS" in content
        assert "NOT PSIF" in content

        # Verify admin flow reasoning page
        inc_admin = Incident.objects.create(
            description="High pressure nitrogen valve relief popped. Isolation barrier was closed immediately with zero leakage and no worker was nearby.",
            job_task="Pressure Testing",
            equipment_involved="Isolation Valve",
            control_condition="effective",
            workspace_id="admin_flow",
        )
        PredictionResult.objects.create(
            incident=inc_admin,
            model_version=mv,
            psif_probability=0.785,
            psif_predicted=True,
            risk_level="HIGH"
        )
        resp_reasoning = client.get(f"/admin-flow/incidents/{inc_admin.id}/reasoning/")
        assert resp_reasoning.status_code == 200
        content_r = resp_reasoning.content.decode("utf-8")
        assert "STAGE 1 &mdash; MODEL OUTPUT" in content_r
        assert "PSIF CANDIDATE" in content_r
        assert "STAGE 2 &mdash; EVIDENCE ASSESSMENT" in content_r
        assert "STAGE 3 &mdash; FINAL TRIAGE STATUS" in content_r
        assert "NOT PSIF" in content_r

    def test_case_b_model_psif_evidence_open_final_psif(self, test_setup):
        """
        Case B:
        Model: PSIF candidate
        Evidence: open serious-consequence pathway (controls failed or absent)
        Final: PSIF
        Expected UI:
        - MODEL OUTPUT -> PSIF CANDIDATE
        - EVIDENCE ASSESSMENT -> Consequence Pathway: Open / Barrier: Failed
        - FINAL TRIAGE STATUS -> PSIF
        """
        mv = test_setup["mv"]
        inc = Incident.objects.create(
            description="Worker was working at height of 8 meters on scaffolding when the safety harness snapped and worker sustained severe head impact from the fall.",
            job_task="Scaffolding work at elevation",
            equipment_involved="Safety Harness",
            control_condition="failed",
            workspace_id="admin_flow",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=mv,
            psif_probability=0.912,
            psif_predicted=True,
            risk_level="CRITICAL"
        )

        assessment = build_analytical_assessment(inc)
        stages = assessment["triage_stages"]

        assert stages["model_output"]["is_candidate"] is True
        assert stages["model_output"]["candidate_label"] == "PSIF CANDIDATE"
        assert "Failed" in stages["evidence_assessment"]["barrier_state"]
        assert stages["evidence_assessment"]["consequence_pathway"] in ["Open", "Supported"]
        assert stages["final_triage"]["status"] == "PSIF"

        # Verify UI rendering
        client = test_setup["client"]
        resp = client.get(f"/admin-flow/incidents/{inc.id}/")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "STAGE 1 &mdash; MODEL OUTPUT" in content
        assert "PSIF CANDIDATE" in content
        assert "STAGE 3 &mdash; FINAL TRIAGE STATUS" in content
        assert "PSIF" in content

    def test_case_c_model_not_psif_evidence_insufficient_final_insufficient(self, test_setup):
        """
        Case C:
        Model: NOT PSIF (or sparse input)
        Evidence: insufficient information
        Final: INSUFFICIENT INFORMATION
        Expected UI:
        - MODEL OUTPUT -> NOT PSIF (or score)
        - EVIDENCE ASSESSMENT -> Insufficient
        - FINAL TRIAGE STATUS -> INSUFFICIENT INFORMATION
        """
        mv = test_setup["mv"]
        inc = Incident.objects.create(
            description="Worker slipped on floor.",
            job_task="Walking",
            equipment_involved="None",
            control_condition="unknown",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=mv,
            psif_probability=0.120,
            psif_predicted=False,
            is_sparse_input=True,
            risk_level="LOW"
        )

        assessment = build_analytical_assessment(inc)
        stages = assessment["triage_stages"]

        assert stages["final_triage"]["status"] == "INSUFFICIENT INFORMATION"
        assert "sparse" in stages["final_triage"]["reason"].lower() or "sufficient" in stages["final_triage"]["reason"].lower() or "insufficient" in stages["final_triage"]["reason"].lower()

        client = test_setup["client"]
        resp = client.get(f"/incidents/{inc.id}/")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "INSUFFICIENT INFORMATION" in content or "INSUFFICIENT_EVIDENCE" in content

    def test_case_d_model_psif_evidence_conflicting_or_unresolved(self, test_setup):
        """
        Case D:
        Model: PSIF candidate
        Evidence: unverified / conflicting control condition with missing pathway details
        Final: Reconciled safely per canonical reasoning engine
        """
        mv = test_setup["mv"]
        inc = Incident.objects.create(
            description="Pressure gauge line showed unexpected flutter during test. Operators checked lines, no audible release.",
            job_task="Pressure Line Check",
            equipment_involved="Gauge line",
            control_condition="unknown",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=mv,
            psif_probability=0.550,
            psif_predicted=True,
            risk_level="MEDIUM"
        )

        assessment = build_analytical_assessment(inc)
        stages = assessment["triage_stages"]

        assert stages["model_output"]["is_candidate"] is True
        assert stages["model_output"]["candidate_label"] == "PSIF CANDIDATE"
        assert stages["final_triage"]["status"] in ["NOT PSIF", "INSUFFICIENT INFORMATION", "PSIF"]
        assert stages["final_triage"]["heading"] == "FINAL TRIAGE STATUS"
        assert stages["evidence_assessment"]["heading"] == "EVIDENCE ASSESSMENT"
        assert stages["model_output"]["heading"] == "MODEL OUTPUT"

    def test_predict_api_returns_canonical_triage_stages(self, test_setup):
        """
        Test that /api/predict/ includes triage_stages without modifying existing keys.
        """
        client = test_setup["admin_client"]

        class MockOutput:
            psif_probability = 0.85
            psif_predicted = True
            risk_level = "high"
            top_factors = [{"feature": "pressure", "contribution": 0.5}]
            is_sparse_input = False
            evidence_strength = "HIGH"
            explanation = {"summary": "High energy test"}

        class MockPredictor:
            def predict(self, record):
                return MockOutput()

        with patch("apps.predictions.api_views.get_active_predictor", return_value=MockPredictor()):
            payload = {
                "description": "High pressure pipe fitting burst during hydrostatic leak test. Direct barrier shield arrested all high velocity debris and prevented operator injury.",
                "job_task": "Hydrostatic Testing",
                "equipment_involved": "High Pressure Pipe Fitting",
                "control_condition": "effective",
                "severity_actual": "first_aid",
                "severity_potential": "serious",
            }
            resp = client.post("/api/predict/", payload, format="json")
            assert resp.status_code == 200
            data = resp.json()

            # Contract preservation: existing keys must exist
            assert "incident_id" in data
            assert "model_version" in data
            assert "psif_score" in data
            assert "psif_predicted" in data
            assert "binary_classification" in data
            assert "threshold_used" in data

            # New explicit triage hierarchy
            assert "triage_stages" in data
            stages = data["triage_stages"]
            assert "model_output" in stages
            assert "evidence_assessment" in stages
            assert "final_triage" in stages

            assert stages["model_output"]["heading"] == "MODEL OUTPUT"
            assert stages["evidence_assessment"]["heading"] == "EVIDENCE ASSESSMENT"
            assert stages["final_triage"]["heading"] == "FINAL TRIAGE STATUS"
            assert stages["final_triage"]["status"] in ["NOT PSIF", "PSIF", "INSUFFICIENT INFORMATION"]
