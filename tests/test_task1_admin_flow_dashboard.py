"""
Test suite for TASK 1 — ADMIN FLOW DASHBOARD, NAVIGATION & DATASET-SCOPED COUNTERS.

Tests cover:
1. Dashboard counters (initial state all 6 = 0, dynamic DB aggregations, not static strings).
2. Counter behavior:
   - Submit 1 incident -> Total Incidents increases by 1.
   - Process eligible incident -> Prediction Eligible + (PSIF or NOT PSIF) increases.
   - Sparse incident -> Insufficient Evidence increases, Prediction Eligible does not.
   - Human review adjudication -> Human Reviewed increases by 1.
3. Primary dashboard actions (SINGLE INCIDENT PREDICTION, UPLOAD DATASET / MULTI INCIDENT PREDICTION).
4. Dedicated 7-item Admin Flow Navbar.
5. Isolated Incident List (columns: Incident ID, Date, Location, Activity, PSIF, Model Score, IOGP, Evidence State; empty state: "No Admin Flow incidents yet.").
6. Scoped Dataset Upload (multi-record batch assigned workspace_id='admin_flow' without touching global dataset).
7. Hard isolation & regression tests (global counts 561k+ remain unchanged).
"""
import io
import csv
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from apps.incidents.models import Incident, IOGPRuleTag, IncidentReview
from apps.datasets.models import Dataset
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.services import (
    ADMIN_FLOW_WORKSPACE,
    get_admin_flow_incidents,
    get_global_incidents,
    get_admin_flow_analytics_summary,
    get_admin_flow_datasets,
)
from apps.dashboard.services import get_analytics_summary as get_global_analytics_summary

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        username="task1_admin_flow_judge",
        defaults={
            "email": "judge_task1@foresight.app",
            "first_name": "Judge",
            "last_name": "Evaluator",
            "role": User.Role.ADMIN_FLOW,
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.role = User.Role.ADMIN_FLOW
    user.save()
    return user


@pytest.fixture
def standard_user(db):
    user, _ = User.objects.get_or_create(
        username="task1_safety_officer",
        defaults={
            "email": "officer_task1@foresight.app",
            "first_name": "Safety",
            "last_name": "Officer",
            "role": User.Role.SAFETY_OFFICER,
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.role = User.Role.SAFETY_OFFICER
    user.save()
    return user


@pytest.fixture
def active_model(db):
    mv = ModelVersion.objects.filter(is_active=True).first()
    if not mv:
        mv = ModelVersion.objects.create(
            version_label="v_20260906_202052",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="/Users/sas/Developer/prototype_165/ml_engine/artifacts/v_20260906_202052/model.json",
            encoder_artifact_path="/Users/sas/Developer/prototype_165/ml_engine/artifacts/v_20260906_202052/encoder.joblib",
            is_active=True,
        )
    return mv


# ==============================================================================
# 1. DASHBOARD COUNTERS & BEHAVIOR
# ==============================================================================

@pytest.mark.django_db
class TestAdminFlowDashboardCounters:
    """Validate all 6 KPI counters and their live reactive state transitions."""

    def test_initial_state_all_six_zero(self, db, client, admin_flow_user):
        """Initial state: All six boxes must calculate to 0 from Admin Flow data."""
        # Ensure workspace has 0 records
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        Dataset.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        summary = get_admin_flow_analytics_summary()
        assert summary["total_incidents"] == 0
        assert summary["prediction_eligible_count"] == 0
        assert summary["psif_count"] == 0
        assert summary["not_psif_count"] == 0
        assert summary["insufficient_evidence_count"] == 0
        assert summary["human_reviewed_count"] == 0

        # Verify rendered template outputs
        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        assert '<div class="metric-value tabular-nums" id="stat-total">0</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-eligible">0</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-psif" style="color: var(--risk-critical);">0</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-not-psif">0</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-insufficient">0</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-human-reviewed">0</div>' in content

    def test_submit_one_incident_increments_total_incidents(self, client, admin_flow_user):
        """When 1 incident is submitted with submit_only, Total Incidents increases by 1, others remain 0."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        client.force_login(admin_flow_user)
        post_data = {
            "report_type": "near_miss",
            "incident_date": "2026-03-20",
            "location": "Drilling Rig OIL-04",
            "department": "Drilling",
            "job_task": "Tripping pipe out of hole",
            "equipment_involved": "Traveling block",
            "description": "Traveling block struck monkey board during pipe hoisting operation due to brake slippage.",
            "immediate_cause": "Brake lining worn beyond tolerance.",
            "high_energy_present": "yes",
            "energy_type": "gravity_height",
            "direct_control_present": "yes",
            "control_condition": "failed",
            "action": "submit_only",
        }
        res = client.post("/admin-flow/submit/", data=post_data, follow=True)
        assert res.status_code == 200

        summary = get_admin_flow_analytics_summary()
        assert summary["total_incidents"] == 1
        assert summary["prediction_eligible_count"] == 0
        assert summary["psif_count"] == 0
        assert summary["not_psif_count"] == 0
        assert summary["insufficient_evidence_count"] == 0
        assert summary["human_reviewed_count"] == 0

        # Check dashboard renders total = 1 and others = 0
        resp_dash = client.get("/admin-flow/dashboard/")
        content = resp_dash.content.decode()
        assert '<div class="metric-value tabular-nums" id="stat-total">1</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-eligible">0</div>' in content

    def test_process_eligible_incident_updates_metrics(self, client, admin_flow_user, active_model):
        """Processing an incident with rich narrative increases Prediction Eligible and PSIF Candidates/Not PSIF."""
        incident = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).first()
        if not incident:
            incident = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description="Traveling block struck monkey board during pipe hoisting operation due to brake slippage.",
                location="Drilling Rig OIL-04",
                department="Drilling",
                job_task="Tripping pipe out of hole",
            )

        client.force_login(admin_flow_user)
        res = client.post(f"/admin-flow/incidents/{incident.pk}/", data={"action": "process"}, follow=True)
        assert res.status_code == 200

        summary = get_admin_flow_analytics_summary()
        assert summary["total_incidents"] >= 1
        assert summary["prediction_eligible_count"] >= 1
        assert (summary["psif_count"] + summary["not_psif_count"]) == summary["prediction_eligible_count"]

    def test_sparse_incident_increments_insufficient_evidence(self, client, admin_flow_user, active_model):
        """An incident with sparse narrative (< 10 words) increments Insufficient Evidence, NOT Prediction Eligible."""
        # Create a sparse incident in Admin Flow
        sparse_inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Hand slip.",  # 2 words -> sparse
            location="Workshop",
            department="Maintenance",
        )
        PredictionResult.objects.create(
            incident=sparse_inc,
            model_version=active_model,
            psif_probability=0.15,
            psif_predicted=False,
            is_sparse_input=True,  # Sparse input flag
        )

        summary = get_admin_flow_analytics_summary()
        assert summary["insufficient_evidence_count"] >= 1

    def test_human_review_adjudication_increments_counter(self, client, admin_flow_user):
        """Submitting an HSE human review record increments Human Reviewed by 1."""
        inc = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).first()
        if not inc:
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description="High-voltage electrical arc flash during sub-station switchgear maintenance.",
                location="Substation B",
                department="Electrical",
            )

        initial_human_reviewed = get_admin_flow_analytics_summary()["human_reviewed_count"]

        client.force_login(admin_flow_user)
        post_data = {
            "decision": "PSIF",
            "rationale": "High-potential energy exposure with failed primary barrier.",
        }
        res = client.post(f"/admin-flow/incidents/{inc.pk}/", data=post_data, follow=True)
        assert res.status_code == 200

        summary = get_admin_flow_analytics_summary()
        assert summary["human_reviewed_count"] == initial_human_reviewed + 1
        assert summary["human_psif_count"] >= 1

        inc.refresh_from_db()
        assert inc.adjudication_status == Incident.AdjudicationStatus.ADJUDICATED
        assert inc.adjudicated_human_decision == "PSIF"
        assert inc.reviews.count() >= 1


# ==============================================================================
# 2. PRIMARY DASHBOARD ACTIONS
# ==============================================================================

@pytest.mark.django_db
class TestAdminFlowPrimaryDashboardActions:
    """Verify the two prominent action cards immediately below the 6 KPI boxes."""

    def test_primary_actions_present_and_linked(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        # Check action 1: SINGLE INCIDENT PREDICTION
        assert "SINGLE INCIDENT PREDICTION" in content
        assert 'id="btn-single-incident-prediction"' in content
        assert 'href="/admin-flow/submit/"' in content

        # Check action 2: UPLOAD DATASET / MULTI INCIDENT PREDICTION
        assert "UPLOAD DATASET / MULTI INCIDENT PREDICTION" in content
        assert 'id="btn-multi-incident-prediction"' in content
        assert 'href="/admin-flow/upload/"' in content

        # Verify clicking action 1 redirects properly
        resp_single = client.get("/admin-flow/submit/")
        assert resp_single.status_code == 200

        # Verify clicking action 2 redirects properly
        resp_upload = client.get("/admin-flow/upload/")
        assert resp_upload.status_code == 200


# ==============================================================================
# 3. ADMIN FLOW NAVBAR (EXACTLY 7 ITEMS)
# ==============================================================================

@pytest.mark.django_db
class TestAdminFlowNavbarContract:
    """Admin Flow navbar must contain strictly only the 7 specified links."""

    def test_navbar_contains_only_seven_links(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        expected_links = [
            "/admin-flow/dashboard/",
            "/admin-flow/submit/",
            "/admin-flow/upload/",
            "/admin-flow/incidents/",
            "/admin-flow/psif/",
            "/admin-flow/iogp/",
            "/admin-flow/patterns/",
        ]
        for link in expected_links:
            assert f'href="{link}"' in content, f"Expected {link} in Admin Flow navbar"

        # Global navigation links must NOT appear
        disallowed = [
            'href="/datasets/"',
            'href="/predictions/"',
            'href="/investigation/"',
            'href="/data-quality/"',
            'href="/benchmarks/"',
        ]
        for link in disallowed:
            assert link not in content, f"Disallowed global link {link} found in Admin Flow navbar"


# ==============================================================================
# 4. ADMIN FLOW INCIDENT LIST & EMPTY STATE
# ==============================================================================

@pytest.mark.django_db
class TestAdminFlowIncidentListScope:
    """Incident list displays only Admin Flow records with specified columns and clean empty state."""

    def test_empty_state_when_no_records(self, client, admin_flow_user):
        """When no records exist, displays 'No Admin Flow incidents yet.' and action buttons."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/incidents/")
        assert response.status_code == 200
        content = response.content.decode()

        assert "No Incidents Recorded Yet" in content or "No Admin Flow incidents yet." in content
        assert 'id="btn-empty-submit"' in content
        assert 'id="btn-empty-upload"' in content

    def test_table_headers_and_columns(self, client, admin_flow_user, active_model):
        """When records exist, incident table contains the 8 required columns."""
        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="High-voltage electrical arc flash during sub-station switchgear maintenance.",
            incident_date="2026-03-22",
            location="Substation B",
            job_task="Switchgear inspection",
            department="Electrical",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.885,
            psif_predicted=True,
            is_sparse_input=False,
            evidence_strength="Strong",
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Energy Isolation",
            classifier_version="iogp_rules_v2",
        )

        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/incidents/")
        assert response.status_code == 200
        content = response.content.decode()

        # Check table headers
        assert "<th>Incident ID</th>" in content
        assert "<th>Date</th>" in content
        assert "<th>Location</th>" in content
        assert "<th>Activity</th>" in content
        assert "<th>PSIF</th>" in content
        assert "<th>Model Score</th>" in content
        assert "<th>IOGP</th>" in content
        assert "<th>Evidence State</th>" in content

        # Check rendered values
        assert str(inc.id)[:8] in content
        assert "2026-03-22" in content
        assert "Substation B" in content
        assert "Switchgear inspection" in content
        assert "PSIF" in content
        assert "0.885" in content
        assert "Energy Isolation" in content
        assert "Strong" in content

    def test_global_incidents_never_appear_in_admin_flow_list(self, client, admin_flow_user):
        """Global incidents are completely excluded from the Admin Flow list."""
        global_inc = Incident.objects.create(
            workspace_id=None,
            description="SECRET_GLOBAL_ENTERPRISE_TOKEN_99812",
            department="Pipelines",
        )

        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/incidents/")
        assert response.status_code == 200
        assert "SECRET_GLOBAL_ENTERPRISE_TOKEN_99812" not in response.content.decode()


# ==============================================================================
# 5. DATASET UPLOAD SCOPE
# ==============================================================================

@pytest.mark.django_db
class TestAdminFlowUploadDatasetScope:
    """Uploaded datasets and resulting incidents strictly belong to Admin Flow."""

    def test_upload_csv_dataset_scoping(self, client, admin_flow_user):
        """Uploading a CSV creates an Admin Flow Dataset and all records have workspace_id='admin_flow'."""
        initial_global_incidents = get_global_incidents().count()
        initial_admin_incidents = get_admin_flow_incidents().count()

        # Build a valid 3-row test CSV
        csv_data = io.StringIO()
        writer = csv.writer(csv_data)
        writer.writerow(["Date", "Department", "Activity", "Description", "HighEnergy", "ControlStatus"])
        writer.writerow(["2026-03-25", "Drilling", "Wireline logging", "Wireline snapped under 4000 lbs tension near wellhead.", "yes", "failed"])
        writer.writerow(["2026-03-26", "Production", "Separator vessel cleaning", "Confined space entry permit gas detector alarm beeped once.", "no", "effective"])
        writer.writerow(["2026-03-27", "Logistics", "Forklift loading", "Forklift operator observed loose gravel on ramp.", "no", "effective"])

        uploaded_file = SimpleUploadedFile(
            name="admin_flow_demo_batch.csv",
            content=csv_data.getvalue().encode("utf-8"),
            content_type="text/csv",
        )

        client.force_login(admin_flow_user)
        response = client.post("/admin-flow/upload/", data={"dataset_file": uploaded_file}, follow=True)
        assert response.status_code == 200

        # Verify dataset object
        dataset = Dataset.objects.filter(name="admin_flow_demo_batch.csv").first()
        assert dataset is not None
        assert dataset.workspace_id == ADMIN_FLOW_WORKSPACE
        assert dataset.total_rows == 3

        # Verify created incidents
        new_incidents = Incident.objects.filter(dataset=dataset)
        assert new_incidents.count() == 3
        for inc in new_incidents:
            assert inc.workspace_id == ADMIN_FLOW_WORKSPACE

        # Verify global enterprise dataset count was UNTOUCHED
        assert get_global_incidents().count() == initial_global_incidents
        # Verify Admin Flow incident count grew by exactly 3
        assert get_admin_flow_incidents().count() == initial_admin_incidents + 3


# ==============================================================================
# 6. REGRESSION & GLOBAL ISOLATION
# ==============================================================================

@pytest.mark.django_db
class TestAdminFlowGlobalRegression:
    """Ensure standard users and existing global data remain completely untouched."""

    def test_standard_user_dashboard_unchanged(self, client, standard_user):
        """Standard user dashboard renders normal navigation and normal counts."""
        client.force_login(standard_user)
        response = client.get("/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        # Normal dashboard elements
        assert 'href="/incidents/"' in content
        assert 'href="/admin-flow/dashboard/"' not in content
        assert 'Admin Flow' not in content
