"""
Tests for TASK 0 — ADMIN FLOW FOUNDATION, AUTHENTICATION & HARD DATA ISOLATION.

Verifies:
1. Genuine dynamic computation of zero initial counters in Admin Flow.
2. Strict two-way hard data isolation between Admin Flow and the global enterprise dataset.
3. Access control: Anonymous users redirected, standard users 403 Forbidden, Admin Flow users 200 OK.
4. Object-level isolation: Global incidents cannot be accessed via /admin-flow/ routes (returns 404).
5. Navbar contract: Admin Flow user sees exclusively the 7 dedicated navigation links.
6. REST API scoping: Admin Flow analytics endpoints enforce DRF permissions and isolate data.
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.incidents.models import Incident, IOGPRuleTag
from apps.datasets.models import Dataset
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.services import (
    ADMIN_FLOW_WORKSPACE,
    is_admin_flow_user,
    get_admin_flow_incidents,
    get_global_incidents,
    get_admin_flow_analytics_summary,
)
from apps.dashboard.services import get_analytics_summary

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        username="test_admin_flow_judge",
        defaults={
            "email": "test_admin_flow@foresight.app",
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
def standard_user(db):
    user, _ = User.objects.get_or_create(
        username="test_safety_officer_user",
        defaults={
            "email": "test_safety_officer@foresight.app",
            "first_name": "Standard",
            "last_name": "Officer",
            "role": User.Role.SAFETY_OFFICER,
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.role = User.Role.SAFETY_OFFICER
    user.save()
    return user


@pytest.mark.django_db
class TestAdminFlowAccessControl:
    """Access control and permission validation."""

    def test_anonymous_redirected_to_login(self, client):
        """Unauthenticated user accessing /admin-flow/ must be redirected to login."""
        response = client.get("/admin-flow/dashboard/")
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

        response_incidents = client.get("/admin-flow/incidents/")
        assert response_incidents.status_code == 302
        assert "/accounts/login/" in response_incidents.url

    def test_standard_user_forbidden_on_admin_flow(self, client, standard_user):
        """Standard users (non-admin_flow role) receive 403 Forbidden."""
        client.force_login(standard_user)

        response = client.get("/admin-flow/dashboard/")
        assert response.status_code == 403

        response = client.get("/admin-flow/incidents/")
        assert response.status_code == 403

        response = client.get("/admin-flow/submit/")
        assert response.status_code == 403

        response = client.get("/admin-flow/upload/")
        assert response.status_code == 403

        response = client.get("/admin-flow/psif/")
        assert response.status_code == 403

        response = client.get("/admin-flow/iogp/")
        assert response.status_code == 403

        response = client.get("/admin-flow/patterns/")
        assert response.status_code == 403

    def test_admin_flow_user_granted_access(self, client, admin_flow_user):
        """Admin Flow user successfully accesses all 7 routes."""
        client.force_login(admin_flow_user)

        routes = [
            "/admin-flow/dashboard/",
            "/admin-flow/submit/",
            "/admin-flow/upload/",
            "/admin-flow/incidents/",
            "/admin-flow/psif/",
            "/admin-flow/iogp/",
            "/admin-flow/patterns/",
        ]
        for r in routes:
            resp = client.get(r)
            assert resp.status_code == 200, f"Route {r} returned {resp.status_code}"

    def test_admin_flow_user_redirected_from_global_dashboard(self, client, admin_flow_user):
        """Admin Flow user visiting standard /dashboard/ is rerouted to /admin-flow/dashboard/."""
        client.force_login(admin_flow_user)
        resp = client.get("/dashboard/")
        assert resp.status_code == 302
        assert resp.url == "/admin-flow/dashboard/"

        resp_root = client.get("/")
        assert resp_root.status_code == 302
        assert resp_root.url == "/admin-flow/dashboard/"


@pytest.mark.django_db
class TestAdminFlowInitialCounters:
    """Verify genuinely computed zero counters at initial state."""

    def test_genuine_zero_baseline(self, db):
        """Zero initial counts computed directly from database queries over workspace_id='admin_flow'."""
        summary = get_admin_flow_analytics_summary()
        assert summary["total_incidents"] == 0
        assert summary["prediction_eligible_count"] == 0
        assert summary["psif_count"] == 0
        assert summary["not_psif_count"] == 0
        assert summary["insufficient_evidence_count"] == 0
        assert summary["human_reviewed_count"] == 0
        assert summary["psif_percentage"] == 0.0

    def test_dashboard_renders_computed_zeros(self, client, admin_flow_user):
        """Admin Flow dashboard template renders genuine zeros from context."""
        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        assert '<div class="metric-value tabular-nums" id="stat-total">0</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-eligible">0</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-psif" style="color: var(--risk-critical);">0</div>' in content
        assert '<div class="metric-value tabular-nums" id="stat-not-psif">0</div>' in content


@pytest.mark.django_db
class TestAdminFlowHardDataIsolation:
    """Mandatory two-way data isolation contract verification."""

    def test_two_way_dataset_isolation(self, client, admin_flow_user, standard_user):
        """
        1. Insert Admin Flow incident -> Admin Flow count increases, Global count unchanged.
        2. Insert Global incident -> Global count increases, Admin Flow count unchanged.
        """
        # Baseline counts
        initial_admin_flow_count = get_admin_flow_incidents().count()
        initial_global_count = get_global_incidents().count()

        # Step 1: Create an Admin Flow incident
        admin_inc = Incident.objects.create(
            description="Admin Flow drill string slip test failure during demo",
            department="Drilling",
            workspace_id=ADMIN_FLOW_WORKSPACE,
            status="OPEN",
            high_energy_present="yes",
            control_condition="failed",
        )

        assert get_admin_flow_incidents().count() == initial_admin_flow_count + 1
        assert get_global_incidents().count() == initial_global_count

        # Step 2: Create a Global enterprise incident
        global_inc = Incident.objects.create(
            description="Global production routine observation in refinery yard",
            department="Refining",
            workspace_id=None,  # Global records have workspace_id = NULL
            status="OPEN",
        )

        assert get_admin_flow_incidents().count() == initial_admin_flow_count + 1
        assert get_global_incidents().count() == initial_global_count + 1

    def test_object_id_bypass_prevention(self, client, admin_flow_user):
        """
        Admin Flow user cannot view global incidents by supplying object IDs to /admin-flow/incidents/<id>/.
        Must return 404 Not Found.
        """
        global_inc = Incident.objects.create(
            description="Confidential global enterprise safety incident",
            department="Pipelines",
            workspace_id=None,
        )

        client.force_login(admin_flow_user)

        # Attempt to access global incident detail through Admin Flow URL
        response = client.get(f"/admin-flow/incidents/{global_inc.pk}/")
        assert response.status_code == 404

    def test_admin_flow_incident_submission(self, client, admin_flow_user):
        """Submitting a report via /admin-flow/submit/ strictly saves with workspace_id='admin_flow'."""
        client.force_login(admin_flow_user)

        post_data = {
            "report_type": "near_miss",
            "incident_date": "2026-03-15",
            "location": "Drilling Rig OIL-09",
            "department": "Drilling Operations",
            "job_task": "Casing make-up",
            "equipment_involved": "Power tongs",
            "description": "High-pressure hydraulic hose whip near rotary table during casing connection makeup.",
            "immediate_cause": "Hydraulic hose burst due to pressure surge.",
            "high_energy_present": "yes",
            "energy_type": "pressure",
            "direct_control_present": "yes",
            "control_condition": "failed",
        }

        resp = client.post("/admin-flow/submit/", data=post_data, follow=True)
        assert resp.status_code == 200

        # Verify created record
        created_inc = Incident.objects.filter(description__icontains="hydraulic hose whip").first()
        assert created_inc is not None
        assert created_inc.workspace_id == ADMIN_FLOW_WORKSPACE


@pytest.mark.django_db
class TestAdminFlowNavbarContract:
    """Admin Flow navbar must contain exclusively the 7 specified links."""

    def test_admin_flow_navbar_contents(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        # Must contain all 7 required items
        required_items = [
            'href="/admin-flow/dashboard/"',
            'href="/admin-flow/submit/"',
            'href="/admin-flow/upload/"',
            'href="/admin-flow/incidents/"',
            'href="/admin-flow/psif/"',
            'href="/admin-flow/iogp/"',
            'href="/admin-flow/patterns/"',
        ]
        for item in required_items:
            assert item in content, f"Missing required navbar link: {item}"

        # Must NOT contain global navbar links
        forbidden_links = [
            'href="/datasets/"',
            'href="/predictions/"',
            'href="/investigation/"',
            'href="/data-quality/"',
            'href="/benchmarks/"',
        ]
        for item in forbidden_links:
            assert item not in content, f"Forbidden global link found in Admin Flow navbar: {item}"

    def test_standard_user_navbar_unchanged(self, client, standard_user):
        """Standard user navbar retains normal navigation and does NOT show Admin Flow links."""
        client.force_login(standard_user)
        response = client.get("/dashboard/")
        assert response.status_code == 200
        content = response.content.decode()

        # Standard navigation present
        assert 'href="/dashboard/"' in content
        assert 'href="/incidents/"' in content

        # Admin Flow links NOT present
        assert 'href="/admin-flow/dashboard/"' not in content
        assert 'href="/admin-flow/patterns/"' not in content


@pytest.mark.django_db
class TestAdminFlowAPIEndpoints:
    """Test scoped REST API endpoints."""

    def test_analytics_api_forbidden_for_standard_user(self, client, standard_user):
        client.force_login(standard_user)
        response = client.get("/admin-flow/api/analytics/overview/")
        assert response.status_code == 403

    def test_analytics_api_success_for_admin_flow_user(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        response = client.get("/admin-flow/api/analytics/overview/")
        assert response.status_code == 200
        data = response.json()
        assert "total_incidents" in data
        assert "psif_count" in data
        assert "workspace_id" in data
        assert data["workspace_id"] == "admin_flow"
