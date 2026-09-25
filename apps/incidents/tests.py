from django.test import TestCase, Client
from django.urls import reverse
import uuid
import json
import numpy as np
from datetime import date
from apps.incidents.models import Incident, IncidentEmbedding, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.decision_trace import build_analytical_assessment

class AnalyticalAssessmentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.model_version = ModelVersion.objects.create(
            version_label="v_20260902_122321",
            is_active=True
        )
        self.incident = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 1),
            department="Maintenance",
            injury_type="Laceration",
            job_task="Pipefitting",
            composite_narrative="Worker cut hand on sharp pipe edge.",
            status="investigation"
        )
        self.prediction = PredictionResult.objects.create(
            incident=self.incident,
            model_version=self.model_version,
            psif_probability=0.85,
            psif_predicted=True,
            risk_level="high",
            top_factors=[
                {"feature": "injury_type_Laceration", "contribution": 0.45},
                {"feature": "job_task_Pipefitting", "contribution": 0.25}
            ]
        )
        IOGPRuleTag.objects.create(
            incident=self.incident,
            rule="Energy Isolation",
            classification_method="keyword_stemming",
            confidence=1.0,
            matched_keywords=["cut", "sharp"],
            matched_fields=["composite_narrative"]
        )
        self.embedding = IncidentEmbedding.objects.create(
            incident=self.incident,
            embedding_model="distilbert-base-uncased",
            vector=np.random.rand(768).tolist()
        )
        
        # Add a related incident
        self.incident_related = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 8, 15),
            department="Maintenance",
            injury_type="Laceration",
            job_task="Pipefitting",
            composite_narrative="Worker got a minor cut on hand.",
            status="closed"
        )
        self.embedding_related = IncidentEmbedding.objects.create(
            incident=self.incident_related,
            embedding_model="distilbert-base-uncased",
            vector=self.embedding.vector  # same vector to guarantee match
        )

    def test_build_analytical_assessment(self):
        assessment = build_analytical_assessment(self.incident)
        self.assertIn("psif_model", assessment)
        self.assertIn("iogp", assessment)
        self.assertIn("similarity", assessment)
        self.assertIn("recurrence", assessment)
        self.assertIn("multi_site_recurrence", assessment)
        self.assertIn("limitations", assessment)
        
        self.assertEqual(assessment["psif_model"]["score"], 85.0)
        self.assertEqual(assessment["psif_model"]["classification"], "PSIF")
        self.assertEqual(len(assessment["iogp"]["items"]), 1)
        self.assertEqual(assessment["iogp"]["items"][0]["rule"], "Energy Isolation")
        
        # Test related incidents
        # Since vector is identical, cosine similarity is ~1.0 (100%)
        self.assertTrue(len(assessment["similarity"]["items"]) > 0)
        self.assertEqual(assessment["similarity"]["items"][0]["incident_id"], str(self.incident_related.id))

    def test_incident_analysis_api(self):
        # We need a user to log in if the endpoint is protected.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(username="testuser", password="password", is_staff=True)
        self.client.login(username="testuser", password="password")
        
        url = reverse('incidents_api:incident_analysis', kwargs={'pk': self.incident.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn("psif_model", data)
        self.assertEqual(data["psif_model"]["score"], 85.0)


# ── P0-2: Human review write-path tests ────────────────────────────────────────

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status as drf_status
import uuid


class HumanReviewViewTests(TestCase):
    """Tests for PATCH /api/incidents/<uuid>/review/"""

    def setUp(self):
        User = get_user_model()
        # Reviewer with can_predict = True (safety_officer role)
        self.reviewer = User.objects.create_user(
            username="reviewer",
            password="pass",
            role="safety_officer",
        )
        # Viewer without can_predict
        self.viewer = User.objects.create_user(
            username="viewer",
            password="pass",
            role="viewer",
        )
        self.client = APIClient()

        from apps.incidents.models import Incident
        self.incident = Incident.objects.create(
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
        )
        self.url = f"/api/incidents/{self.incident.id}/review/"

    def test_viewer_cannot_post_review(self):
        """Viewers must not be able to write ground-truth labels."""
        self.client.force_authenticate(user=self.viewer)
        resp = self.client.patch(self.url, {"is_psif_human_label": False}, format="json")
        self.assertEqual(resp.status_code, drf_status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_post_review(self):
        resp = self.client.patch(self.url, {"is_psif_human_label": True}, format="json")
        self.assertEqual(resp.status_code, drf_status.HTTP_403_FORBIDDEN)

    def test_agreement_without_rationale_succeeds(self):
        """Reviewer gives boolean/PSIF review without rationale — succeeds."""
        self.client.force_authenticate(user=self.reviewer)
        resp = self.client.patch(
            self.url,
            {"is_psif_human_label": True},
            format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        self.incident.refresh_from_db()
        self.assertTrue(self.incident.is_psif_human_label)
        self.assertEqual(self.incident.psif_label_source, Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC)
        self.assertEqual(self.incident.reviewed_by, self.reviewer)
        self.assertIsNotNone(self.incident.reviewed_at)
        self.assertEqual(self.incident.status, "reviewed_psif")

    def test_insufficient_information_without_rationale_fails(self):
        """Marking insufficient info without rationale must be rejected."""
        self.client.force_authenticate(user=self.reviewer)
        resp = self.client.patch(
            self.url,
            {"decision": "INSUFFICIENT_INFORMATION"},
            format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_400_BAD_REQUEST)
        self.assertIn("rationale", resp.json())

    def test_insufficient_information_with_rationale_succeeds(self):
        """Marking insufficient info with rationale must succeed and persist all fields."""
        self.client.force_authenticate(user=self.reviewer)
        resp = self.client.patch(
            self.url,
            {
                "decision": "INSUFFICIENT_INFORMATION",
                "rationale": "Missing energy and severity context, cannot determine PSIF.",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        self.incident.refresh_from_db()
        self.assertIsNone(self.incident.is_psif_human_label)
        self.assertEqual(self.incident.adjudicated_human_decision, "INSUFFICIENT_INFORMATION")
        self.assertIn("Missing energy", self.incident.reviewer_rationale)
        # effective_training_label must be None (never converted to binary NOT_PSIF)
        self.assertIsNone(self.incident.effective_training_label)

    def test_404_for_unknown_incident(self):
        self.client.force_authenticate(user=self.reviewer)
        url = f"/api/incidents/{uuid.uuid4()}/review/"
        resp = self.client.patch(url, {"is_psif_human_label": True}, format="json")
        self.assertEqual(resp.status_code, drf_status.HTTP_404_NOT_FOUND)

    def test_prediction_result_not_modified(self):
        """Original AI prediction must not be mutated by the review."""
        from apps.predictions.models import PredictionResult, ModelVersion
        mv = ModelVersion.objects.create(
            version_label="v0.1-test",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="/tmp/model.json",
            encoder_artifact_path="/tmp/enc.joblib",
        )
        pred = PredictionResult.objects.create(
            incident=self.incident,
            model_version=mv,
            psif_probability=0.9,
            psif_predicted=True,
            risk_level="high",
            top_factors=[],
            is_sparse_input=False,
        )
        original_prob = pred.psif_probability

        self.client.force_authenticate(user=self.reviewer)
        self.client.patch(
            self.url,
            {"is_psif_human_label": False, "rationale": "Disagreement with model."},
            format="json",
        )
        pred.refresh_from_db()
        self.assertEqual(pred.psif_probability, original_prob,
                         "AI prediction probability must not be mutated by human review.")


from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.incidents.forms import IncidentReportForm
from apps.datasets.ingestion import create_incident_from_row

User = get_user_model()


class IncidentSafetyContextAndSubmissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="reporter_jane",
            email="jane@oilindia.in",
            password="testpassword123",
            role=User.Role.SAFETY_OFFICER,
        )
        self.client.force_authenticate(user=self.user)
        self.client.force_login(self.user)

    def test_a_submission_with_complete_safety_context(self):
        """A: Submission with complete safety context succeeds and syncs control_failed_bypassed."""
        payload = {
            "report_type": Incident.ReportType.INCIDENT,
            "incident_date": "2026-09-02",
            "department": "Drilling",
            "location": "Duliajan Rig 4",
            "job_task": "Derrick maintenance",
            "equipment_involved": "Traveling block",
            "description": "Traveling block shifted unexpectedly while securing line at 25m height.",
            "immediate_cause": "Line brake slipped under tension",
            "witness_statement": "Roughneck witnessed the line slip.",
            "corrective_actions": "Re-pinned mechanical brake mechanism.",
            "high_energy_present": Incident.SafetyContextState.YES,
            "energy_type": Incident.EnergyType.GRAVITY_HEIGHT,
            "worker_exposed": Incident.SafetyContextState.YES,
            "direct_control_present": Incident.SafetyContextState.YES,
            "control_type": Incident.ControlType.FALL_PROTECTION,
            "control_condition": Incident.ControlCondition.FAILED,
            "severity_actual": Incident.SeverityActual.NONE,
        }
        resp = self.client.post("/api/incidents/report/", payload, format="json")
        self.assertEqual(resp.status_code, drf_status.HTTP_201_CREATED)
        inc_id = resp.json()["incident_id"]
        incident = Incident.objects.get(id=inc_id)

        self.assertEqual(incident.high_energy_present, Incident.SafetyContextState.YES)
        self.assertEqual(incident.energy_type, Incident.EnergyType.GRAVITY_HEIGHT)
        self.assertEqual(incident.worker_exposed, Incident.SafetyContextState.YES)
        self.assertEqual(incident.direct_control_present, Incident.SafetyContextState.YES)
        self.assertEqual(incident.control_type, Incident.ControlType.FALL_PROTECTION)
        self.assertEqual(incident.control_condition, Incident.ControlCondition.FAILED)
        self.assertTrue(incident.control_failed_bypassed, "Condition FAILED must synchronize control_failed_bypassed=True")
        self.assertTrue(incident.composite_narrative)
        self.assertTrue(hasattr(incident, "data_quality"), "Data quality record should be generated on submission")

    def test_b_submission_with_unknown_energy_state(self):
        """B: Submission with unknown energy state preserves unknown, never coerces to No."""
        payload = {
            "report_type": Incident.ReportType.UNSAFE_CONDITION,
            "incident_date": "2026-09-03",
            "department": "Production",
            "description": "Unidentified pressure hissing noise noticed near separator manifold.",
            "high_energy_present": Incident.SafetyContextState.UNKNOWN,
            "energy_type": Incident.EnergyType.UNKNOWN,
            "worker_exposed": Incident.SafetyContextState.UNKNOWN,
            "direct_control_present": Incident.SafetyContextState.UNKNOWN,
            "control_type": Incident.ControlType.UNKNOWN,
            "control_condition": Incident.ControlCondition.UNKNOWN,
            "severity_actual": Incident.SeverityActual.NONE,
        }
        resp = self.client.post("/api/incidents/report/", payload, format="json")
        self.assertEqual(resp.status_code, drf_status.HTTP_201_CREATED)
        incident = Incident.objects.get(id=resp.json()["incident_id"])
        self.assertEqual(incident.high_energy_present, Incident.SafetyContextState.UNKNOWN)
        self.assertEqual(incident.energy_type, Incident.EnergyType.UNKNOWN)
        self.assertEqual(incident.worker_exposed, Incident.SafetyContextState.UNKNOWN)
        self.assertIsNone(incident.control_failed_bypassed)

    def test_c_submission_with_no_direct_control(self):
        """C: Direct control absent -> direct_control_present='no', control_condition='absent' -> control_failed_bypassed=False."""
        payload = {
            "report_type": Incident.ReportType.UNSAFE_ACT,
            "incident_date": "2026-09-04",
            "department": "Logistics",
            "description": "Forklift operated without seatbelt and without designated pedestrian barrier.",
            "high_energy_present": Incident.SafetyContextState.YES,
            "energy_type": Incident.EnergyType.MOTOR_VEHICLE,
            "worker_exposed": Incident.SafetyContextState.YES,
            "direct_control_present": Incident.SafetyContextState.NO,
            "control_type": Incident.ControlType.PHYSICAL_BARRIER,
            "control_condition": Incident.ControlCondition.ABSENT,
            "severity_actual": Incident.SeverityActual.NONE,
        }
        resp = self.client.post("/api/incidents/report/", payload, format="json")
        self.assertEqual(resp.status_code, drf_status.HTTP_201_CREATED)
        incident = Incident.objects.get(id=resp.json()["incident_id"])
        self.assertEqual(incident.direct_control_present, Incident.SafetyContextState.NO)
        self.assertEqual(incident.control_condition, Incident.ControlCondition.ABSENT)
        self.assertFalse(incident.control_failed_bypassed)

    def test_d_submission_with_direct_control_present_effective(self):
        """D: Direct control present and effective -> control_condition='effective' -> control_failed_bypassed=False."""
        payload = {
            "report_type": Incident.ReportType.NEAR_MISS,
            "incident_date": "2026-09-04",
            "department": "Maintenance",
            "description": "Wrench dropped from catwalk at 4m, caught by toe-board and safety netting.",
            "high_energy_present": Incident.SafetyContextState.YES,
            "energy_type": Incident.EnergyType.GRAVITY_HEIGHT,
            "worker_exposed": Incident.SafetyContextState.NO,
            "direct_control_present": Incident.SafetyContextState.YES,
            "control_type": Incident.ControlType.PHYSICAL_BARRIER,
            "control_condition": Incident.ControlCondition.EFFECTIVE,
            "severity_actual": Incident.SeverityActual.NONE,
        }
        resp = self.client.post("/api/incidents/report/", payload, format="json")
        self.assertEqual(resp.status_code, drf_status.HTTP_201_CREATED)
        incident = Incident.objects.get(id=resp.json()["incident_id"])
        self.assertEqual(incident.control_condition, Incident.ControlCondition.EFFECTIVE)
        self.assertFalse(incident.control_failed_bypassed)

    def test_e_near_miss_with_no_injury(self):
        """E: Near miss with no injury automatically syncs near_miss=True."""
        form = IncidentReportForm(data={
            "report_type": Incident.ReportType.NEAR_MISS,
            "incident_date": "2026-09-04",
            "department": "Production",
            "description": "High pressure hose vibrated loose but safety whip-check held.",
            "severity_actual": Incident.SeverityActual.NONE,
            "high_energy_present": Incident.SafetyContextState.YES,
            "energy_type": Incident.EnergyType.PRESSURE,
            "worker_exposed": Incident.SafetyContextState.NO,
            "direct_control_present": Incident.SafetyContextState.YES,
            "control_type": Incident.ControlType.PHYSICAL_BARRIER,
            "control_condition": Incident.ControlCondition.EFFECTIVE,
        })
        self.assertTrue(form.is_valid(), form.errors)
        incident = form.save()
        self.assertTrue(incident.near_miss)

    def test_f_incident_with_actual_injury(self):
        """F: Incident with actual injury syncs near_miss=False and preserves injury fields."""
        form = IncidentReportForm(data={
            "report_type": Incident.ReportType.INCIDENT,
            "incident_date": "2026-09-04",
            "department": "Maintenance",
            "description": "Technician hand caught between pump flange and casing during bolt tightening.",
            "severity_actual": Incident.SeverityActual.LOST_TIME,
            "injury_type": "Fracture",
            "body_part": "Right hand",
            "high_energy_present": Incident.SafetyContextState.YES,
            "energy_type": Incident.EnergyType.MECHANICAL_MOTION,
            "worker_exposed": Incident.SafetyContextState.YES,
            "direct_control_present": Incident.SafetyContextState.NO,
            "control_type": Incident.ControlType.MACHINE_GUARDING,
            "control_condition": Incident.ControlCondition.ABSENT,
        })
        self.assertTrue(form.is_valid(), form.errors)
        incident = form.save()
        self.assertFalse(incident.near_miss)
        self.assertEqual(incident.injury_type, "Fracture")
        self.assertEqual(incident.body_part, "Right hand")

    def test_g_contradictory_combination_rejected(self):
        """G: Validation rejects contradictory report_type='near_miss' with actual fatality/lost time."""
        form = IncidentReportForm(data={
            "report_type": Incident.ReportType.NEAR_MISS,
            "incident_date": "2026-09-04",
            "department": "Production",
            "description": "Contradictory event.",
            "severity_actual": Incident.SeverityActual.FATALITY,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Near Miss", str(form.non_field_errors()))

    def test_h_incident_detail_renders_new_fields(self):
        """H: Incident detail page renders Report Type and Safety Context & Controls card."""
        incident = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 4),
            report_type=Incident.ReportType.UNSAFE_CONDITION,
            department="Drilling",
            composite_narrative="Scaffolding plank unfastened at height.",
            high_energy_present=Incident.SafetyContextState.YES,
            energy_type=Incident.EnergyType.GRAVITY_HEIGHT,
            worker_exposed=Incident.SafetyContextState.YES,
            direct_control_present=Incident.SafetyContextState.YES,
            control_type=Incident.ControlType.FALL_PROTECTION,
            control_condition=Incident.ControlCondition.FAILED,
        )
        resp = self.client.get(f"/incidents/{incident.id}/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Safety Context &amp; Controls", content)
        self.assertIn("High Energy Hazard", content)
        self.assertIn("Gravity / Working at Height", content)
        self.assertIn("Fall Protection / Harness / Railing (Direct)", content)

    def test_i_existing_ingestion_not_broken(self):
        """I: Dataset ingestion pipeline remains fully functional with safe defaults."""
        row = {
            "Incident ID": "OIL-TEST-001",
            "Date": "2026-09-01",
            "Department": "Workover",
            "Severity Actual": "First Aid",
            "Severity Potential": "Serious",
            "Description": "Worker sustained laceration while handling wrench.",
        }
        mapping = {
            "Incident ID": "external_id",
            "Date": "incident_date",
            "Department": "department",
            "Severity Actual": "severity_actual",
            "Severity Potential": "severity_potential",
            "Description": "description",
        }
        inc = create_incident_from_row(row=row, dataset=None, column_mapping=mapping)
        inc.save()
        self.assertEqual(inc.high_energy_present, Incident.SafetyContextState.UNKNOWN)
        self.assertEqual(inc.energy_type, Incident.EnergyType.UNKNOWN)
        self.assertIsNone(inc.control_failed_bypassed)
        self.assertEqual(inc.psif_label_source, Incident.PsifLabelSource.NONE)

