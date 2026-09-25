"""
PSIF Platform — Task 4 Admin Flow Activity Pattern Analysis Test Suite.

Verifies:
1. Empty state (0 records):
   - "No activity patterns available yet."
   - "Upload Dataset" and "Submit Report" action buttons.
2. Single record (1 record):
   - Correct ranking #1.
   - Top pattern callout displays "MOST FREQUENT ACTIVITY", "1 incidents".
   - Caption strictly uses "Most frequently observed activity in the current Admin Flow dataset."
   - No mention of "Most dangerous activity".
   - Percentage of Admin Flow incidents is 100.0% (1/1).
3. Multiple activities sample:
   - Ranked descending: highest activity = longest bar / rank 1, lowest = shortest bar.
   - Matches prompt example pattern: Safe Mechanical Lifting 42, Driving 28, Hot Work 18, etc.
   - Explicit denominator formula: incident count / total Admin Flow incidents.
4. Dual view toggle:
   - Incident Volume vs PSIF-Linked Volume.
   - Correct Chart.js payload with volume and PSIF counts.
5. Filtering:
   - Date range, PSIF classification, and activity search.
   - Dynamic denominator recomputation.
6. Unknown activity handling:
   - Graceful handling of unclassified/sparse activities.
7. Workspace isolation:
   - Global incidents (workspace_id IS NULL) are completely excluded.
8. Role-based access control:
   - Admin Flow users have access; other roles and anonymous users are blocked.
9. REST API endpoint (/admin-flow/api/patterns/activity/).
"""

import uuid
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.pattern_engine import (
    ADMIN_FLOW_WORKSPACE,
    get_admin_flow_activity_pattern_view_data,
    invalidate_admin_flow_pattern_cache,
)

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        email="admin_flow_evaluator@foresight.app",
        defaults={
            "username": "admin_flow_evaluator@foresight.app",
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
        email="operator_standard@foresight.app",
        defaults={
            "username": "operator_standard@foresight.app",
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
        version_label="v_task4_test",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.mark.django_db
class TestTask4ActivityPatternAnalysis:
    """Comprehensive test suite for Task 4 Activity Pattern Analysis."""

    def test_empty_state_zero_records(self, client, admin_flow_user):
        """When no Admin Flow records exist, shows clean empty state with action buttons."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns_activity")
        resp = client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode()

        # Prompt requirement: “No activity patterns available yet.”
        assert "No activity patterns available yet." in content
        # Prompt requirement: Upload Dataset and Submit Report buttons
        assert "Upload Dataset" in content
        assert "Submit Report" in content
        assert reverse("admin_flow:upload") in content
        assert reverse("admin_flow:submit") in content

        # View data check
        view_data = resp.context["activity_data"]
        assert view_data["has_data"] is False
        assert view_data["total_workspace_incidents"] == 0
        assert len(view_data["activities"]) == 0
        assert view_data["top_activity"]["has_data"] is False

    def test_single_record_pattern(self, client, admin_flow_user, active_model):
        """When 1 incident exists, shows top pattern callout, 100% share, and defensible caption."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Lifting Operation / Crane Work",
            description="Crane operation lifted steel beam near compressor bay.",
            location="Compressor Area",
            incident_date="2026-05-10",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.88,
            psif_predicted=True,
            risk_level="HIGH",
        )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns_activity")
        resp = client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode()

        # Top pattern callout header & caption requirements
        assert "MOST FREQUENT ACTIVITY" in content
        assert "Lifting Operation / Crane Work" in content
        assert "Most frequently observed activity in the current Admin Flow dataset." in content
        assert "Most dangerous activity" not in content  # Strictly forbidden phrase

        # Table shows rank 1, count 1, and 100.0% (1/1)
        assert "100.0% (1/1)" in content
        view_data = resp.context["activity_data"]
        assert view_data["top_activity"]["incident_count"] == 1
        assert view_data["top_activity"]["psif_linked_count"] == 1
        assert view_data["top_activity"]["psif_linkage_rate"] == 100.0

    def test_multiple_activities_ranked_descending(self, client, admin_flow_user, active_model):
        """
        Creates prompt example distribution with canonical activity categories:
        Safe Mechanical Lifting = 42
        Vehicle Operation / Road Transport = 28
        Hot Work in Classified Area = 18
        Confined Space Vessel Entry = 5
        Total = 93
        Verifies descending ranking, dual toggle counts, and explicit denominator percentages.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        distribution = [
            ("Lifting Operation / Crane Work", "Lifting steel pipe with crane", 42, 15),
            ("Vehicle Operation / Road Transport", "Heavy transport truck driving on access road", 28, 10),
            ("Hot Work in Classified Area", "Welding and cutting flange in maintenance bay", 18, 4),
            ("Confined Space Vessel Entry", "Entering storage tank for inspection", 5, 2),
        ]

        for activity, desc, count, psif_count in distribution:
            for i in range(count):
                is_psif = i < psif_count
                inc = Incident.objects.create(
                    workspace_id=ADMIN_FLOW_WORKSPACE,
                    job_task=activity,
                    description=f"{desc} instance {i}",
                    location="Workshop / Maintenance Bay",
                    incident_date="2026-06-01",
                )
                PredictionResult.objects.create(
                    incident=inc,
                    model_version=active_model,
                    psif_probability=0.85 if is_psif else 0.20,
                    psif_predicted=is_psif,
                    risk_level="HIGH" if is_psif else "LOW",
                )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns_activity")
        resp = client.get(url)

        assert resp.status_code == 200
        view_data = resp.context["activity_data"]

        assert view_data["total_workspace_incidents"] == 93
        assert view_data["total_filtered_incidents"] == 93
        assert len(view_data["activities"]) == 4

        # Verify descending order
        acts = view_data["activities"]
        assert acts[0]["category"] == "Lifting Operation / Crane Work"
        assert acts[0]["rank"] == 1
        assert acts[0]["incident_count"] == 42
        assert acts[0]["psif_linked_count"] == 15
        assert acts[0]["share_of_total"] == round((42 / 93) * 100, 1)  # 45.2%
        assert acts[0]["share_label"] == "45.2% (42/93)"

        assert acts[1]["category"] == "Vehicle Operation / Road Transport"
        assert acts[1]["rank"] == 2
        assert acts[1]["incident_count"] == 28
        assert acts[1]["psif_linked_count"] == 10
        assert acts[1]["share_of_total"] == round((28 / 93) * 100, 1)  # 30.1%

        assert acts[2]["category"] == "Hot Work in Classified Area"
        assert acts[2]["rank"] == 3
        assert acts[2]["incident_count"] == 18
        assert acts[2]["psif_linked_count"] == 4

        assert acts[3]["category"] == "Confined Space Vessel Entry"
        assert acts[3]["rank"] == 4
        assert acts[3]["incident_count"] == 5
        assert acts[3]["psif_linked_count"] == 2

        # Verify Chart.js data arrays
        assert view_data["chart_labels"] == [
            "Lifting Operation / Crane Work",
            "Vehicle Operation / Road Transport",
            "Hot Work in Classified Area",
            "Confined Space Vessel Entry"
        ]
        assert view_data["chart_incident_counts"] == [42, 28, 18, 5]
        assert view_data["chart_psif_counts"] == [15, 10, 4, 2]

        # Verify HTML rendered content
        content = resp.content.decode()
        assert "MOST FREQUENT ACTIVITY" in content
        assert "42" in content
        assert "Lifting Operation / Crane Work" in content
        assert "Most frequently observed activity in the current Admin Flow dataset." in content
        assert "toggle-incident-volume" in content
        assert "toggle-psif-volume" in content
        assert "activityPatternChart" in content
        assert "Percentage denominator: incident count / 93 total incidents" in content

    def test_dual_view_toggle_elements(self, client, admin_flow_user):
        """Verifies dual view toggle buttons and Chart.js integration scripts exist."""
        client.force_login(admin_flow_user)
        # Create 1 incident to trigger populated state
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Driving",
            description="Truck transit on lease road",
        )
        resp = client.get(reverse("admin_flow:patterns_activity"))
        content = resp.content.decode()

        assert 'data-metric="volume"' in content
        assert 'data-metric="psif"' in content
        assert "Incident Volume" in content
        assert "PSIF-Linked Volume" in content
        assert "chart-labels-data" in content
        assert "chart-incident-counts-data" in content
        assert "chart-psif-counts-data" in content

    def test_filtering_date_psif_query(self, client, admin_flow_user, active_model):
        """Verifies filtering by date range, PSIF classification, and search query."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Incident 1: Jan 2026, Lifting, PSIF
        inc1 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Lifting Operation / Crane Work",
            description="Crane lifting pipe",
            incident_date="2026-01-15",
        )
        PredictionResult.objects.create(
            incident=inc1,
            model_version=active_model,
            psif_probability=0.9,
            psif_predicted=True,
            risk_level="HIGH",
        )

        # Incident 2: March 2026, Lifting, NOT PSIF
        inc2 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Lifting Operation / Crane Work",
            description="Forklift moving pallet",
            incident_date="2026-03-20",
        )
        PredictionResult.objects.create(
            incident=inc2,
            model_version=active_model,
            psif_probability=0.1,
            psif_predicted=False,
            risk_level="LOW",
        )

        # Incident 3: March 2026, Driving, NOT PSIF
        inc3 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Driving",
            description="Vehicle speeding on rig road",
            incident_date="2026-03-22",
        )
        PredictionResult.objects.create(
            incident=inc3,
            model_version=active_model,
            psif_probability=0.2,
            psif_predicted=False,
            risk_level="LOW",
        )

        client.force_login(admin_flow_user)

        # 1. Date filter (March only)
        resp = client.get(reverse("admin_flow:patterns_activity"), {
            "date_from": "2026-03-01",
            "date_to": "2026-03-31",
        })
        assert resp.status_code == 200
        view_data = resp.context["activity_data"]
        assert view_data["total_filtered_incidents"] == 2
        assert len(view_data["activities"]) == 2

        # 2. PSIF filter (PSIF only)
        resp = client.get(reverse("admin_flow:patterns_activity"), {
            "psif": "psif",
        })
        assert resp.status_code == 200
        view_data = resp.context["activity_data"]
        assert view_data["total_filtered_incidents"] == 1
        assert view_data["activities"][0]["category"] == "Lifting Operation / Crane Work"

        # 3. Query filter (q=Forklift)
        resp = client.get(reverse("admin_flow:patterns_activity"), {
            "q": "Forklift",
        })
        assert resp.status_code == 200
        view_data = resp.context["activity_data"]
        assert view_data["total_filtered_incidents"] == 1
        assert view_data["activities"][0]["category"] == "Lifting Operation / Crane Work"

    def test_unknown_activity_handling(self, client, admin_flow_user):
        """Verifies handling of unclassified or vague activities without errors."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="N/A",
            description="Unknown general occurrence on site during shift change.",
            location="Process Area",
        )

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:patterns_activity"))
        assert resp.status_code == 200
        view_data = resp.context["activity_data"]
        assert view_data["total_filtered_incidents"] == 1
        assert len(view_data["activities"]) == 1
        assert view_data["activities"][0]["category"] in ["UNKNOWN ACTIVITY", "Other / General Site Operations", "Unknown Activity"]

    def test_workspace_isolation_hard_segregation(self, client, admin_flow_user):
        """Verifies global incidents (workspace_id IS NULL) are completely excluded."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Create global incidents
        for i in range(10):
            Incident.objects.create(
                workspace_id=None,
                job_task="Vehicle Operation / Road Transport",
                description=f"Global enterprise transport incident {i}",
            )

        # Create 2 Admin Flow incidents
        for i in range(2):
            Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                job_task="Hot Work in Classified Area",
                description=f"Admin Flow welding activity {i}",
            )

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:patterns_activity"))
        assert resp.status_code == 200
        view_data = resp.context["activity_data"]

        # Admin Flow should strictly see 2 incidents, both Hot Work
        assert view_data["total_workspace_incidents"] == 2
        assert len(view_data["activities"]) == 1
        assert view_data["activities"][0]["category"] == "Hot Work in Classified Area"
        assert view_data["activities"][0]["incident_count"] == 2

    def test_role_based_access_control(self, client, standard_user):
        """Verifies non-admin flow users are denied access (403 Forbidden)."""
        client.force_login(standard_user)
        resp = client.get(reverse("admin_flow:patterns_activity"))
        assert resp.status_code == 403

        # Anonymous user gets redirected to login
        client.logout()
        resp = client.get(reverse("admin_flow:patterns_activity"))
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    def test_activity_patterns_api(self, client, admin_flow_user):
        """Verifies GET /admin-flow/api/patterns/activity/ returns JSON with filters."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Vehicle Operation / Road Transport",
            description="Vehicle operation",
        )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:api_patterns_activity")
        resp = client.get(url)

        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == "admin_flow"
        assert data["total_filtered_incidents"] == 1
        assert len(data["activities"]) == 1
        assert data["activities"][0]["category"] == "Vehicle Operation / Road Transport"
        assert data["chart_labels"] == ["Vehicle Operation / Road Transport"]
        assert data["chart_incident_counts"] == [1]
        assert data["top_activity"]["category"] == "Vehicle Operation / Road Transport"
        assert data["top_activity"]["callout_caption"] == "Most frequently observed activity in the current Admin Flow dataset."
