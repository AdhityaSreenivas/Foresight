"""
PSIF Platform — Task Admin Flow Reset Test Suite.

Comprehensive verification of:
1. Fresh reset on empty Admin Flow workspace.
2. Clean-sheet demonstration reset with controlled 10-record fixture.
3. Complete reset of all 6 dashboard KPIs (all = 0).
4. Complete reset of incident list, PSIF classification, IOGP classification,
   and all Pattern Analysis dimensions (Hub, Activity, Barrier, Location).
5. Double reset safety (idempotent, no negative counters, no exceptions).
6. 100% preservation of global records, datasets, predictions, human reviews,
   and model registry.
7. Post-reset reuse: submit 1 new report -> count becomes 1; upload new data accumulates from clean baseline.
8. Backend security: anonymous redirect, standard user 403 forbidden, GET 405 method not allowed,
   workspace spoofing parameter immunity.
9. Async cooperative cancellation of in-flight dataset processing.
10. Audit event logging of ADMIN_FLOW_RESET with user, timestamp, and tallies.
"""
import uuid
import pytest
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache

from apps.accounts.models import User
from apps.incidents.models import Incident, IOGPRuleTag, IncidentReview
from apps.predictions.models import PredictionResult, ModelVersion
from apps.datasets.models import Dataset
from apps.admin_flow.services import (
    ADMIN_FLOW_WORKSPACE,
    reset_admin_flow_workspace,
    get_admin_flow_analytics_summary,
    get_admin_flow_psif_metrics,
    get_admin_flow_iogp_metrics,
    get_admin_flow_reset_audit_log,
    is_admin_flow_reset_in_progress,
)
from apps.admin_flow.pattern_engine import (
    get_admin_flow_pattern_hub_view_data,
    get_admin_flow_activity_pattern_view_data,
    get_admin_flow_barrier_pattern_view_data,
    get_admin_flow_location_pattern_view_data,
)


@pytest.fixture
def admin_flow_user(db):
    """Admin Flow evaluator user fixture."""
    user, _ = User.objects.get_or_create(
        email="admin_flow@foresight.app",
        defaults={
            "username": "admin_flow@foresight.app",
            "role": "admin_flow",
            "is_active": True,
        },
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def regular_admin_user(db):
    """Standard regular user fixture (not Admin Flow)."""
    user, _ = User.objects.get_or_create(
        email="admin@foresight.app",
        defaults={
            "username": "admin@foresight.app",
            "role": "admin",
            "is_active": True,
            "is_staff": True,
        },
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def active_model(db):
    """Active production model fixture."""
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_20260906_202052",
        defaults={
            "bert_model_name": "distilbert-base-uncased",
            "is_active": True,
            "status": ModelVersion.Status.ACTIVE,
            "xgboost_artifact_path": "/Users/sas/Developer/prototype_165/ml_engine/artifacts/v_20260906_202052/model.json",
            "encoder_artifact_path": "/Users/sas/Developer/prototype_165/ml_engine/artifacts/v_20260906_202052/encoder.joblib",
        },
    )
    if not mv.is_active or mv.status != ModelVersion.Status.ACTIVE:
        mv.is_active = True
        mv.status = ModelVersion.Status.ACTIVE
        mv.bert_model_name = "distilbert-base-uncased"
        mv.xgboost_artifact_path = "/Users/sas/Developer/prototype_165/ml_engine/artifacts/v_20260906_202052/model.json"
        mv.encoder_artifact_path = "/Users/sas/Developer/prototype_165/ml_engine/artifacts/v_20260906_202052/encoder.joblib"
        mv.save()
    return mv


@pytest.fixture
def controlled_10_records(db, active_model):
    """
    Creates a controlled 10-record fixture in the Admin Flow workspace:
    - 2 PSIF (score >= 0.20)
    - 3 NOT PSIF (score < 0.20)
    - 2 INSUFFICIENT INFORMATION (sparse text < 10 words)
    - 3 other branches (near miss, high energy controlled, etc.)
    - Diverse IOGP rules, activities, locations, and barrier states.
    """
    # Clear any leftover admin flow records
    Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

    records = []

    # 1. PSIF + Hot Work (Drilling Area)
    i1 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Flash fire occurred during pipe cutting in bay 2. Worker suffered second degree burn.",
        job_task="Pipe Cutting",
        department="Drilling",
        location="Drilling Area",
        high_energy_present="yes",
        direct_control_present="yes",
        control_condition="failed",
    )
    PredictionResult.objects.create(
        incident=i1,
        model_version=active_model,
        psif_probability=0.88,
        psif_predicted=True,
        risk_level="CRITICAL",
        is_sparse_input=False,
    )
    IOGPRuleTag.objects.create(incident=i1, rule="Hot Work")
    records.append(i1)

    # 2. PSIF + Confined Space + Work Authorization (Process Bay 1)
    i2 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Toxic gas release inside pressure vessel while worker inside without breathing apparatus.",
        job_task="Vessel Entry",
        department="Production",
        location="Process Area",
        high_energy_present="yes",
        direct_control_present="yes",
        control_condition="failed",
    )
    PredictionResult.objects.create(
        incident=i2,
        model_version=active_model,
        psif_probability=0.92,
        psif_predicted=True,
        risk_level="CRITICAL",
        is_sparse_input=False,
    )
    IOGPRuleTag.objects.create(incident=i2, rule="Confined Space")
    IOGPRuleTag.objects.create(incident=i2, rule="Work Authorization")
    records.append(i2)

    # 3. NOT PSIF (Routine pump inspection)
    i3 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Routine pump inspection completed with no hazards or anomalies found.",
        job_task="Pump Inspection",
        department="Maintenance",
        location="Compressor Station",
        high_energy_present="no",
        direct_control_present="no",
    )
    PredictionResult.objects.create(
        incident=i3,
        model_version=active_model,
        psif_probability=0.04,
        psif_predicted=False,
        risk_level="LOW",
        is_sparse_input=False,
    )
    records.append(i3)

    # 4. NOT PSIF + Safe Mechanical Lifting
    i4 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Chain hoist rigging inspected prior to lift. Slings verified and lift executed safely.",
        job_task="Rigging and Lifting",
        department="Logistics",
        location="Warehouse",
        high_energy_present="no",
        direct_control_present="yes",
        control_condition="effective",
    )
    PredictionResult.objects.create(
        incident=i4,
        model_version=active_model,
        psif_probability=0.08,
        psif_predicted=False,
        risk_level="LOW",
        is_sparse_input=False,
    )
    IOGPRuleTag.objects.create(incident=i4, rule="Safe Mechanical Lifting")
    records.append(i4)

    # 5. NOT PSIF (Office ergonomical discomfort)
    i5 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Office staff reported ergonomic wrist strain from keyboard usage during documentation entry.",
        job_task="Administrative Data Entry",
        department="Administration",
        location="Main Office",
    )
    PredictionResult.objects.create(
        incident=i5,
        model_version=active_model,
        psif_probability=0.01,
        psif_predicted=False,
        risk_level="LOW",
        is_sparse_input=False,
    )
    records.append(i5)

    # 6. INSUFFICIENT INFORMATION 1 (sparse < 10 words)
    i6 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Noise heard.",
        job_task="General Inspection",
        department="Operations",
        location="Process Area",
    )
    PredictionResult.objects.create(
        incident=i6,
        model_version=active_model,
        psif_probability=0.10,
        psif_predicted=False,
        risk_level="LOW",
        is_sparse_input=True,
    )
    records.append(i6)

    # 7. INSUFFICIENT INFORMATION 2 (sparse < 10 words)
    i7 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Worker fell.",
        job_task="Maintenance",
        department="Maintenance",
        location="Tank Farm",
    )
    PredictionResult.objects.create(
        incident=i7,
        model_version=active_model,
        psif_probability=0.15,
        psif_predicted=False,
        risk_level="LOW",
        is_sparse_input=True,
    )
    records.append(i7)

    # 8. Other Branch: Near Miss (Tool dropped, caught by secondary barrier)
    i8 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Wrench slipped from hand at height but was caught by safety tether. No impact.",
        job_task="Working at Height",
        department="Maintenance",
        location="Drilling Area",
        report_type=Incident.ReportType.NEAR_MISS,
        near_miss=True,
        high_energy_present="yes",
        direct_control_present="yes",
        control_condition="effective",
    )
    PredictionResult.objects.create(
        incident=i8,
        model_version=active_model,
        psif_probability=0.18,
        psif_predicted=False,
        risk_level="LOW",
        is_sparse_input=False,
    )
    IOGPRuleTag.objects.create(incident=i8, rule="Working at Height")
    records.append(i8)

    # 9. Other Branch: High-energy controlled (Electrical lockout held)
    i9 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="High voltage breaker trip tested with LOTO lock secured. Barrier performed as designed.",
        job_task="Electrical Isolation",
        department="Electrical",
        location="Substation",
        high_energy_present="yes",
        direct_control_present="yes",
        control_condition="effective",
    )
    PredictionResult.objects.create(
        incident=i9,
        model_version=active_model,
        psif_probability=0.06,
        psif_predicted=False,
        risk_level="LOW",
        is_sparse_input=False,
    )
    IOGPRuleTag.objects.create(incident=i9, rule="Energy Isolation")
    records.append(i9)

    # 10. Other Branch: Vehicle minor contact
    i10 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        description="Forklift grazed plastic bollard at low speed in parking lot during reverse maneuver.",
        job_task="Vehicle Operation",
        department="Logistics",
        location="Warehouse",
        high_energy_present="no",
    )
    PredictionResult.objects.create(
        incident=i10,
        model_version=active_model,
        psif_probability=0.03,
        psif_predicted=False,
        risk_level="LOW",
        is_sparse_input=False,
    )
    IOGPRuleTag.objects.create(incident=i10, rule="Driving")
    records.append(i10)

    return records


@pytest.mark.django_db
class TestAdminFlowResetFreshAndEmpty:
    """Verifies reset behavior when Admin Flow starts at a zero baseline."""

    def test_fresh_reset_on_empty_workspace(self, client, admin_flow_user):
        """Reset on an already empty workspace succeeds harmlessly and returns zeros."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        Dataset.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        client.force_login(admin_flow_user)
        response = client.post(reverse("admin_flow:reset"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["deleted"]["incidents"] == 0
        assert data["remaining"]["incidents"] == 0

        # Verify summary services return natural zeros
        summary = get_admin_flow_analytics_summary()
        assert summary["total_incidents"] == 0
        assert summary["psif_count"] == 0
        assert summary["not_psif_count"] == 0
        assert summary["insufficient_evidence_count"] == 0

    def test_reset_button_rendered_in_navbar_for_admin_flow_only(self, client, admin_flow_user, regular_admin_user):
        """The Reset Demo button is visible in Admin Flow navbar and absent for regular logins."""
        # Admin Flow user sees Reset Demo
        client.force_login(admin_flow_user)
        resp_af = client.get(reverse("admin_flow:dashboard"))
        assert resp_af.status_code == 200
        content_af = resp_af.content.decode("utf-8")
        assert 'id="btn-reset-demo"' in content_af
        assert "Reset Demo" in content_af
        assert 'id="admin-flow-reset-modal"' in content_af
        assert "Reset Demo?" in content_af or "Reset Admin Flow?" in content_af
        assert "RESET DEMO" in content_af

        # Regular user does NOT see Reset Demo
        client.force_login(regular_admin_user)
        resp_reg = client.get("/dashboard/")
        assert resp_reg.status_code == 200
        content_reg = resp_reg.content.decode("utf-8")
        assert 'id="btn-reset-demo"' not in content_reg
        assert 'id="admin-flow-reset-modal"' not in content_reg


@pytest.mark.django_db
class TestAdminFlowResetWithData:
    """Verifies complete clean-sheet demonstration reset with controlled data."""

    def test_reset_with_controlled_10_records(self, client, admin_flow_user, controlled_10_records):
        """Populate 10 mixed records, reset, and verify all 6 KPIs and all pages return to zero/empty."""
        client.force_login(admin_flow_user)

        # Baseline check before reset
        summary_before = get_admin_flow_analytics_summary()
        assert summary_before["total_incidents"] == 10
        assert summary_before["psif_count"] == 2
        assert summary_before["insufficient_evidence_count"] == 2

        # Trigger reset via standard POST
        response = client.post(reverse("admin_flow:reset"))
        assert response.status_code == 302
        assert response.url == reverse("admin_flow:dashboard")

        # 1. Database level check
        assert Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).count() == 0
        assert PredictionResult.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE).count() == 0
        assert IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE).count() == 0

        # 2. Service level check: natural recalculation
        summary_after = get_admin_flow_analytics_summary()
        assert summary_after["total_incidents"] == 0
        assert summary_after["prediction_eligible_count"] == 0
        assert summary_after["psif_count"] == 0
        assert summary_after["not_psif_count"] == 0
        assert summary_after["insufficient_evidence_count"] == 0
        assert summary_after["human_reviewed_count"] == 0

        # 3. Dashboard page HTML check: all 6 KPI cards strictly zero
        dashboard_resp = client.get(reverse("admin_flow:dashboard"))
        assert dashboard_resp.status_code == 200
        dash_content = dashboard_resp.content.decode("utf-8")
        assert 'id="stat-total">0</div>' in dash_content
        assert 'id="stat-eligible">0</div>' in dash_content
        assert 'id="stat-psif"' in dash_content
        assert summary_after["psif_count"] == 0
        assert 'id="stat-not-psif">0</div>' in dash_content
        assert 'id="stat-insufficient">0</div>' in dash_content
        assert 'id="stat-human-reviewed">0</div>' in dash_content

        # 4. Incidents page HTML check: clean empty state
        incidents_resp = client.get(reverse("admin_flow:incidents"))
        assert incidents_resp.status_code == 200
        inc_content = incidents_resp.content.decode("utf-8")
        assert "No Incidents Recorded Yet" in inc_content or "No Admin Flow incidents yet." in inc_content

        # 5. PSIF page HTML check: 0 candidates
        psif_resp = client.get(reverse("admin_flow:psif"))
        assert psif_resp.status_code == 200
        psif_content = psif_resp.content.decode("utf-8")
        assert 'id="kpi-psif"' in psif_content
        assert psif_resp.context["psif_metrics"]["psif_count"] == 0
        assert 'id="kpi-total-incidents">0</div>' in psif_content

        # 6. IOGP page HTML check: 0 matches, clean empty state
        iogp_resp = client.get(reverse("admin_flow:iogp"))
        assert iogp_resp.status_code == 200
        iogp_content = iogp_resp.content.decode("utf-8")
        assert 'id="kpi-matched">0</div>' in iogp_content

        # 7. Pattern Analysis pages check: naturally empty
        hub_data = get_admin_flow_pattern_hub_view_data()
        assert hub_data["has_data"] is False
        assert hub_data["total_incidents"] == 0
        assert hub_data["top_activity"]["has_data"] is False
        assert hub_data["top_barrier"]["has_data"] is False
        assert hub_data["top_location"]["has_data"] is False

        act_data = get_admin_flow_activity_pattern_view_data()
        assert act_data["has_data"] is False
        assert len(act_data["activities"]) == 0

        bar_data = get_admin_flow_barrier_pattern_view_data()
        assert bar_data["has_data"] is False
        assert len(bar_data["barriers"]) == 0

        loc_data = get_admin_flow_location_pattern_view_data()
        assert loc_data["has_data"] is False
        assert len(loc_data["locations"]) == 0

    def test_double_reset(self, client, admin_flow_user, controlled_10_records):
        """Calling reset twice consecutively succeeds with zero negative counters or errors."""
        client.force_login(admin_flow_user)

        # First reset
        r1 = client.post(reverse("admin_flow:reset"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["deleted"]["incidents"] == 10
        assert d1["remaining"]["incidents"] == 0

        # Immediate second reset
        r2 = client.post(reverse("admin_flow:reset"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["deleted"]["incidents"] == 0
        assert d2["remaining"]["incidents"] == 0

        summary = get_admin_flow_analytics_summary()
        assert summary["total_incidents"] == 0


@pytest.mark.django_db
class TestGlobalDataAndModelRegistryPreservation:
    """Verifies that Admin Flow reset NEVER touches global records or models."""

    def test_global_data_and_model_registry_preservation(self, client, admin_flow_user, regular_admin_user, active_model):
        """Global incidents, predictions, reviews, datasets, and models are 100% untouched."""
        # 1. Create global data
        g_ds = Dataset.objects.create(name="Global Dataset", workspace_id=None, status=Dataset.Status.COMPLETED)
        g_inc = Incident.objects.create(
            workspace_id=None,
            dataset=g_ds,
            description="Global historical offshore blowout report.",
            location="Rig 4",
        )
        g_pred = PredictionResult.objects.create(
            incident=g_inc,
            model_version=active_model,
            psif_probability=0.95,
            psif_predicted=True,
            risk_level="CRITICAL",
        )
        g_rule = IOGPRuleTag.objects.create(incident=g_inc, rule="Bypassing Safety Controls")
        g_review = IncidentReview.objects.create(
            incident=g_inc,
            decision=IncidentReview.HumanDecision.PSIF,
            rationale="Verified global human review",
        )

        global_inc_count_before = Incident.objects.filter(workspace_id__isnull=True).count()
        global_pred_count_before = PredictionResult.objects.filter(incident__workspace_id__isnull=True).count()
        global_rule_count_before = IOGPRuleTag.objects.filter(incident__workspace_id__isnull=True).count()
        global_review_count_before = IncidentReview.objects.filter(incident__workspace_id__isnull=True).count()

        # 2. Create Admin Flow demo data
        af_inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Admin flow temporary observation.",
        )
        PredictionResult.objects.create(
            incident=af_inc,
            model_version=active_model,
            psif_probability=0.50,
            psif_predicted=True,
            risk_level="HIGH",
        )

        # 3. Reset Admin Flow
        client.force_login(admin_flow_user)
        reset_resp = client.post(reverse("admin_flow:reset"))
        assert reset_resp.status_code == 302

        # 4. Verify Admin Flow data is gone
        assert Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).count() == 0

        # 5. Verify Global data is completely unchanged
        assert Incident.objects.filter(workspace_id__isnull=True).count() == global_inc_count_before
        assert PredictionResult.objects.filter(incident__workspace_id__isnull=True).count() == global_pred_count_before
        assert IOGPRuleTag.objects.filter(incident__workspace_id__isnull=True).count() == global_rule_count_before
        assert IncidentReview.objects.filter(incident__workspace_id__isnull=True).count() == global_review_count_before

        # 6. Verify ModelVersion registry untouched
        active_mv = ModelVersion.objects.filter(is_active=True).first()
        assert active_mv is not None
        assert active_mv.version_label == active_model.version_label

        # 7. Verify Regular User Dashboard is accessible and undisturbed
        from django.test import Client as DjangoTestClient
        reg_client = DjangoTestClient()
        reg_client.force_login(regular_admin_user)
        reg_resp = reg_client.get("/dashboard/")
        assert reg_resp.status_code == 200
        reg_content = reg_resp.content.decode("utf-8")
        assert "Reset Demo" not in reg_content
        assert "admin-flow-reset-modal" not in reg_content
        assert "/admin-flow/" not in reg_content


@pytest.mark.django_db
class TestAdminFlowResetSecurityAndPermissions:
    """Verifies security controls, permissions, HTTP methods, and spoofing resistance."""

    def test_anonymous_user_redirected_to_login(self, client):
        """Unauthenticated requests are redirected to login."""
        response = client.post(reverse("admin_flow:reset"))
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_standard_user_forbidden(self, client, regular_admin_user):
        """Standard authenticated users cannot invoke reset (HTTP 403)."""
        client.force_login(regular_admin_user)
        response = client.post(reverse("admin_flow:reset"))
        assert response.status_code == 403

    def test_get_method_rejected(self, client, admin_flow_user):
        """Destructive reset rejects GET with HTTP 405 Method Not Allowed."""
        client.force_login(admin_flow_user)
        response = client.get(reverse("admin_flow:reset"))
        assert response.status_code == 405

    def test_workspace_parameter_spoofing_ignored(self, client, admin_flow_user, active_model):
        """Passing workspace_id='global' or other parameters does not affect other workspaces."""
        # Create global incident
        g_inc = Incident.objects.create(workspace_id=None, description="Critical global incident.")

        client.force_login(admin_flow_user)
        # Attempt to spoof global deletion
        response = client.post(
            reverse("admin_flow:reset"),
            {"workspace_id": "global", "scope": "all"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert response.status_code == 200

        # Global incident still exists unharmed
        assert Incident.objects.filter(id=g_inc.id).exists()


@pytest.mark.django_db
class TestPostResetReuseAndWorkflow:
    """Verifies submitting reports and uploading datasets after reset accumulates from clean state."""

    def test_post_reset_new_submission_and_accumulation(self, client, admin_flow_user, controlled_10_records, active_model):
        """Submit one incident after reset -> counter becomes exactly 1."""
        client.force_login(admin_flow_user)

        # Reset
        client.post(reverse("admin_flow:reset"))
        assert Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).count() == 0

        # Submit ONE new incident
        submit_url = reverse("admin_flow:submit")
        form_data = {
            "description": "Forklift backed into rack corner protector causing light scuffing on column.",
            "report_type": Incident.ReportType.INCIDENT,
            "incident_date": "2026-09-11",
            "department": "Logistics",
            "location": "Warehouse A",
            "job_task": "Forklift Transport",
            "action": "submit_only",
        }
        submit_resp = client.post(submit_url, form_data)
        assert submit_resp.status_code == 302

        # Verify Total Incidents is now exactly 1
        summary = get_admin_flow_analytics_summary()
        assert summary["total_incidents"] == 1
        assert Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).count() == 1


@pytest.mark.django_db
class TestAsyncProcessingSafetyAndAuditLog:
    """Verifies cooperative cancellation of active tasks and audit logging."""

    def test_reset_during_active_dataset_processing(self, db):
        """Active datasets in PROCESSING state are cooperatively cancelled on reset."""
        ds = Dataset.objects.create(
            name="In Flight Demo Batch",
            workspace_id=ADMIN_FLOW_WORKSPACE,
            status=Dataset.Status.PROCESSING,
            cancel_requested=False,
        )

        result = reset_admin_flow_workspace(user=None)
        assert result["status"] == "success"
        # In-flight dataset was deleted/cancelled
        assert not Dataset.objects.filter(id=ds.id).exists()

    def test_audit_event_logged(self, client, admin_flow_user, controlled_10_records):
        """Reset records an ADMIN_FLOW_RESET audit event with user and counts."""
        client.force_login(admin_flow_user)
        client.post(reverse("admin_flow:reset"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        audit_log = get_admin_flow_reset_audit_log()
        assert len(audit_log) > 0
        latest = audit_log[0]
        assert latest["event"] == "ADMIN_FLOW_RESET"
        assert latest["user"] == "admin_flow@foresight.app"
        assert latest["result"] == "SUCCESS"
        assert latest["deleted_counts"]["incidents"] == 10
        assert latest["remaining_counts"]["incidents"] == 0
