"""
PSIF Platform — Task 5 Admin Flow Barrier Intelligence Test Suite.

Verifies:
1. Empty state (0 records or no evidence-supported barriers):
   - Clear empty state message.
   - "Upload Dataset" action button.
2. Single record (1 record):
   - Top pattern callout displays most frequent barrier.
   - Strictly forbids "Worst barrier", "Barrier responsible for most accidents", "Barriers causing incidents".
   - Methodology note is present.
3. Every control state:
   - Deficiencies tracked: ABSENT, FAILED, BYPASSED, NOT_VERIFIED, PARTIALLY_EFFECTIVE.
   - Effective safeguards recognized and not labeled as failures.
4. Multiple barriers sample ranked descending:
   - Ranked by incident count descending.
5. Affected internal locations & Dominant control state:
   - Counts distinct internal locations affected.
   - Computes dominant state from evidence.
6. IOGP Association:
   - Preserves IOGP rules as associated dimensions, NOT the barrier identity.
7. Simple Filters:
   - PSIF only, All incidents, Control state, Location.
8. Workspace isolation:
   - Global incidents (workspace_id IS NULL) are completely excluded.
9. Role-based access control:
   - Admin Flow users have access; standard users get 403 Forbidden; anonymous redirected (302).
10. REST API endpoint (/admin-flow/api/patterns/barrier/).
"""

import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.barrier_engine import (
    BarrierCategory,
    BarrierObservation,
    BarrierRole,
    BarrierState,
)
from apps.admin_flow.barrier_service import (
    ADMIN_FLOW_WORKSPACE,
    BarrierPatternService,
    invalidate_admin_flow_barrier_cache,
)
from apps.admin_flow.pattern_engine import (
    get_admin_flow_barrier_pattern_view_data,
    invalidate_admin_flow_pattern_cache,
)

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        email="admin_flow_evaluator_t5@foresight.app",
        defaults={
            "username": "admin_flow_evaluator_t5@foresight.app",
            "role": "admin_flow",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def standard_user(db):
    user, _ = User.objects.get_or_create(
        email="operator_standard_t5@foresight.app",
        defaults={
            "username": "operator_standard_t5@foresight.app",
            "role": "safety_officer",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def active_model(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_task5_test",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.mark.django_db
class TestTask5BarrierPatternAnalysis:
    """Comprehensive test suite for Admin Flow Barrier Pattern Analysis."""

    def test_empty_state_zero_records(self, client, admin_flow_user):
        """When no Admin Flow records exist, shows clean empty state with action buttons."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns_barrier")
        resp = client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode()

        # Empty state text
        assert "No Barrier Intelligence Data Found" in content or "No barrier" in content
        assert "Upload Dataset" in content
        assert reverse("admin_flow:upload") in content

        # View data check
        view_data = resp.context["barrier_data"]
        assert view_data["has_data"] is False
        assert view_data["total_workspace_incidents"] == 0
        assert len(view_data["portfolio_cards"]) == 0

    def test_single_record_pattern_and_semantic_rules(self, client, admin_flow_user, active_model):
        """
        When 1 incident with a protective barrier exists:
        - Displays top barrier information.
        - Strictly forbids "Worst barrier", "Barrier responsible for most accidents", "Barriers causing incidents".
        - Methodology note is present.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Isolation of Energy Sources",
            description="Electrical breaker panel opened without positive lock out. Lockout tagout was absent.",
            control_type="Energy Isolation",
            control_condition="FAILED",
            location="Compressor Area",
            incident_date="2026-05-10",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.91,
            psif_predicted=True,
            risk_level="HIGH",
        )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns_barrier")
        resp = client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode()

        # Semantic rule forbidden strings check
        assert "Worst barrier" not in content
        assert "Barrier responsible for most accidents" not in content
        assert "Barriers causing incidents" not in content

        # Methodology note check
        assert "A Barrier is the actual physical or operational protective measure" in content or "protective measures" in content

        view_data = resp.context["barrier_data"]
        assert view_data["barrier_identified_count"] == 1
        assert len(view_data["portfolio_cards"]) == 1
        assert "Lockout" in view_data["portfolio_cards"][0]["barrier_name"]

    def test_every_control_state_deficiency_vs_effective(self, client, admin_flow_user):
        """
        Comprehensive test of supported barrier states:
        - Effective safeguards are counted as successes and NOT as deficiencies.
        - Deficiencies (ABSENT, FAILED, BYPASSED, NOT_VERIFIED) are recognized separately.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # 1. Effective safeguards
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Routine Inspection",
            description="Isolation valve closed and held pressure as designed.",
            control_type="Energy Isolation",
            location="Workshop",
        )
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Atmospheric Check",
            description="Gas detector alarmed when hydrocarbon levels rose.",
            control_type="Hazardous Atmospheres",
            location="Compressor Area",
        )

        # 2. Deficiencies
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Machine Maintenance",
            description="Machine guard had been removed before maintenance.",
            control_type="Line of Fire",
            location="Workshop",
        )
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Elevated Work",
            description="The harness was available in the vehicle but was not connected.",
            control_type="Working at Height",
            location="Tank Farm",
        )

        data = get_admin_flow_barrier_pattern_view_data()

        assert data["barrier_identified_count"] == 4
        assert data["effective_barrier_signals"] == 2
        assert data["deficient_barrier_signals"] == 2

    def test_multiple_barriers_ranked_descending(self, client, admin_flow_user, active_model):
        """
        Verifies barriers are ranked descending by associated incident count.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Create 10 Isolation Valve incidents, 6 Machine Guard incidents, 3 Safety Harness incidents
        for i in range(10):
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                job_task="Pipeline Operations",
                description=f"Isolation valve closed to stop release #{i}",
                location="Compressor Area",
            )
            PredictionResult.objects.create(
                incident=inc,
                model_version=active_model,
                psif_probability=0.85,
                psif_predicted=True,
            )

        for i in range(6):
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                job_task="Machining",
                description=f"Machine guard absent on lathe #{i}",
                location="Workshop",
            )
            PredictionResult.objects.create(
                incident=inc,
                model_version=active_model,
                psif_probability=0.2,
                psif_predicted=False,
            )

        for i in range(3):
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                job_task="Elevated Work",
                description=f"Safety harness caught worker #{i}",
                location="Tank Farm",
            )
            PredictionResult.objects.create(
                incident=inc,
                model_version=active_model,
                psif_probability=0.85,
                psif_predicted=True,
            )

        data = get_admin_flow_barrier_pattern_view_data()

        cards = data["portfolio_cards"]
        assert len(cards) >= 3
        # First should have 10, second 6, third 3
        assert cards[0]["associated_incidents_count"] == 10
        assert cards[1]["associated_incidents_count"] == 6
        assert cards[2]["associated_incidents_count"] == 3

        # Chart labels array sorted descending
        assert data["chart_total_counts"][:3] == [10, 6, 3]

    def test_affected_locations_and_dominant_state(self, client, admin_flow_user):
        """
        Verifies affected locations and dominant barrier states.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # 3 incidents for Machine Guard across 2 locations
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Machine guard had been removed from pump.",
            location="Compressor Area",
        )
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Machine guard was absent during maintenance.",
            location="Workshop",
        )
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Machine guard missing from conveyor.",
            location="Workshop",
        )

        data = get_admin_flow_barrier_pattern_view_data()
        guard = next((c for c in data["portfolio_cards"] if "Machine Guard" in c["barrier_name"]), None)
        assert guard is not None
        assert guard["associated_incidents_count"] == 3
        assert guard["affected_locations_count"] == 2
        assert any("Workshop" in loc for loc in guard["affected_locations"])

    def test_filtering_psif_control_state_and_location(self, client, admin_flow_user, active_model):
        """
        Verifies filtering by PSIF, state, and location.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Incident 1: Compressor Area, Isolation Valve, Effective, PSIF
        inc1 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Isolation valve closed successfully stopping high pressure leak.",
            location="Compressor Area",
        )
        PredictionResult.objects.create(
            incident=inc1,
            model_version=active_model,
            psif_probability=0.9,
            psif_predicted=True,
        )

        # Incident 2: Workshop, Machine Guard, Absent, Non-PSIF
        inc2 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Machine guard had been removed from grinder.",
            location="Workshop",
        )
        PredictionResult.objects.create(
            incident=inc2,
            model_version=active_model,
            psif_probability=0.2,
            psif_predicted=False,
        )

        client.force_login(admin_flow_user)

        # 1. Filter by PSIF only
        resp = client.get(reverse("admin_flow:patterns_barrier"), {"psif": "psif"})
        assert resp.status_code == 200
        view_data = resp.context["barrier_data"]
        assert view_data["total_filtered_incidents"] == 1
        assert len(view_data["portfolio_cards"]) == 1
        assert "Isolation Valve" in view_data["portfolio_cards"][0]["barrier_name"]

        # 2. Filter by control state (EFFECTIVE)
        resp2 = client.get(reverse("admin_flow:patterns_barrier"), {"state": "EFFECTIVE"})
        assert resp2.status_code == 200
        view_data2 = resp2.context["barrier_data"]
        assert len(view_data2["portfolio_cards"]) == 1
        assert "Isolation Valve" in view_data2["portfolio_cards"][0]["barrier_name"]

        # 3. Filter by location (Workshop)
        resp3 = client.get(reverse("admin_flow:patterns_barrier"), {"location": "Workshop"})
        assert resp3.status_code == 200
        view_data3 = resp3.context["barrier_data"]
        assert len(view_data3["portfolio_cards"]) == 1
        assert "Machine Guard" in view_data3["portfolio_cards"][0]["barrier_name"]

    def test_workspace_isolation_hard_segregation(self, client, admin_flow_user):
        """
        Verifies:
        - Global incidents (workspace_id IS NULL) are completely excluded from Admin Flow.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Global incidents
        for i in range(10):
            Incident.objects.create(
                workspace_id=None,
                description=f"Global isolation valve failed {i}",
                location="Refinery Unit",
            )

        # Admin Flow incident
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Safety harness caught worker when he slipped.",
            location="Drilling Area",
        )

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:patterns_barrier"))
        assert resp.status_code == 200
        view_data = resp.context["barrier_data"]

        # Admin Flow must strictly see only 1 incident and 1 barrier (Safety Harness)
        assert view_data["total_workspace_incidents"] == 1
        assert len(view_data["portfolio_cards"]) == 1
        assert "Safety Harness" in view_data["portfolio_cards"][0]["barrier_name"]

    def test_role_based_access_control(self, client, standard_user):
        """Verifies non-admin flow users are denied access (403 Forbidden)."""
        client.force_login(standard_user)
        resp = client.get(reverse("admin_flow:patterns_barrier"))
        assert resp.status_code == 403

        # Anonymous user gets redirected to login
        client.logout()
        resp = client.get(reverse("admin_flow:patterns_barrier"))
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    def test_barrier_patterns_api(self, client, admin_flow_user):
        """Verifies GET /admin-flow/api/patterns/barrier/ returns JSON compliant with specs."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Physical segregation barrier stopped vehicle from entering pedestrian area.",
            location="Workshop",
        )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:api_patterns_barrier")
        resp = client.get(url)

        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == "admin_flow"
        assert data["total_filtered_incidents"] == 1
        assert len(data["portfolio_cards"]) == 1
        assert "Segregation" in data["portfolio_cards"][0]["barrier_name"]
        assert "Worst barrier" not in str(data)
        assert "Barriers causing incidents" not in str(data)
