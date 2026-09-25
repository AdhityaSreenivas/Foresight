"""
PSIF Platform — Task 6 Admin Flow Location Pattern Analysis Test Suite.

Verifies:
1. Empty state (0 records):
   - "No location patterns available yet."
   - "Upload Dataset" and "Submit Report" action buttons.
2. Single-site assumption & single location:
   - Same site context ("Duliajan Operational Complex").
   - Top location callout displays "HIGHEST OBSERVATION CONCENTRATION".
   - Neutral caption: "Highest observation concentration in the current Admin Flow dataset."
   - 100.0% share (1/1).
3. Multiple locations ranked descending:
   - Process Area = 42, Compressor Area = 30, Workshop = 18, Tank Farm = 10.
   - Sorted descending by incident observation count.
   - Explicit denominator formula: count / total filtered Admin Flow incidents.
4. Continuous heat intensity derivation:
   - Highest concentration has intensity 1.0 (Critical / Red #C62828).
   - Legend explicitly says "INCIDENT OBSERVATION DENSITY" (not "danger probability").
5. Granular location data metrics:
   - Incident count, PSIF-linked count, share of total, top activity, top barrier-linked signal.
6. Pattern relationship chain view:
   - Location -> Activity -> Barrier-linked signal.
   - Strictly enforces neutral wording: "Observed relationship in Admin Flow data."
7. Unknown location handling:
   - Graceful normalization to "UNKNOWN LOCATION" without errors or crashes.
8. Many locations & schematic layout:
   - Both 3x3 canonical grid zones and auxiliary zones populated.
   - No geographic coordinates required or fabricated.
9. Workspace isolation:
   - Global incidents (workspace_id IS NULL) are completely excluded.
10. Role-based access control:
    - Admin Flow users allowed (200), standard users forbidden (403), anonymous redirected (302).
11. REST API endpoint (/admin-flow/api/patterns/location/).
"""

import uuid
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.pattern_engine import (
    ADMIN_FLOW_WORKSPACE,
    ADMIN_FLOW_SITE_NAME,
    get_admin_flow_location_pattern_view_data,
    invalidate_admin_flow_pattern_cache,
)

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        email="admin_flow_evaluator_t6@foresight.app",
        defaults={
            "username": "admin_flow_evaluator_t6@foresight.app",
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
        email="operator_standard_t6@foresight.app",
        defaults={
            "username": "operator_standard_t6@foresight.app",
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
        version_label="v_task6_test",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.mark.django_db
class TestTask6LocationPatternAnalysis:
    """Comprehensive test suite for Task 6 Admin Flow Location Pattern Analysis."""

    def test_empty_state_zero_records(self, client, admin_flow_user):
        """When no Admin Flow records exist, shows clean empty state with action buttons."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns_location")
        resp = client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode()

        # Prompt requirement: Exact empty state text
        assert "No location patterns available yet." in content
        # Action buttons
        assert "Upload Dataset" in content
        assert "Submit Report" in content
        assert reverse("admin_flow:upload") in content
        assert reverse("admin_flow:submit") in content

        # View data check
        view_data = resp.context["location_data"]
        assert view_data["has_data"] is False
        assert view_data["total_workspace_incidents"] == 0
        assert len(view_data["locations"]) == 0
        assert view_data["top_location"]["has_data"] is False

    def test_same_site_assumption_and_single_location(self, client, admin_flow_user, active_model):
        """
        When 1 incident exists:
        - Confirms single site context (Duliajan Operational Complex).
        - Top location callout displays "HIGHEST OBSERVATION CONCENTRATION".
        - Neutral caption: "Highest observation concentration in the current Admin Flow dataset."
        - Denominator share is 100.0% (1/1).
        - No geographic coordinates fabricated.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Gas Compression Inspection",
            description="Compressor fuel gas leak detected during startup.",
            control_type="Energy Isolation",
            control_condition="FAILED",
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
        url = reverse("admin_flow:patterns_location")
        resp = client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode()

        # Site context assertion & clean UI (no isolation banners)
        assert ADMIN_FLOW_SITE_NAME in content
        assert "Operational Single-Site Scope" not in content
        assert "workspace_id" not in content

        # Top location callout
        assert "HIGHEST OBSERVATION CONCENTRATION" in content
        assert "Compressor Area" in content
        assert "Highest observation concentration in the current Admin Flow dataset." in content

        # Table shows rank 1, count 1, and 100.0% (1/1)
        assert "100.0% (1/1)" in content
        view_data = resp.context["location_data"]
        assert view_data["site_context"] == ADMIN_FLOW_SITE_NAME
        assert view_data["top_location"]["incident_count"] == 1
        assert view_data["top_location"]["psif_linked_count"] == 1
        assert view_data["top_location"]["total_locations_count"] == 1

        # Legend title strictly compliant
        assert "INCIDENT OBSERVATION DENSITY" in content
        assert "danger probability" not in content

    def test_multiple_locations_ranked_descending(self, client, admin_flow_user, active_model):
        """
        Recreates prompt distribution:
        - Process Area: 42 incidents (18 PSIF)
        - Compressor Area: 30 incidents (12 PSIF)
        - Workshop: 18 incidents (4 PSIF)
        - Tank Farm: 10 incidents (2 PSIF)
        Total = 100 incidents.
        Verifies:
        - Descending ranking: Process Area #1, Compressor Area #2, Workshop #3, Tank Farm #4.
        - Explicit denominator formula: count / total filtered incidents.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        distribution = [
            ("Process Area", "Hot work in process unit", 42, 18, "Hot Work in Classified Area", "Work Authorization"),
            ("Compressor Area", "Compressor gas valve check", 30, 12, "Routine Operational Maintenance", "Energy Isolation"),
            ("Workshop", "Grinding and machining task", 18, 4, "Machining and Tool Operation", "Line of Fire"),
            ("Tank Farm", "Storage tank level gauge check", 10, 2, "Working at Height", "Fall Protection"),
        ]

        for loc, desc, count, psif_count, act, bar in distribution:
            for i in range(count):
                is_psif = i < psif_count
                inc = Incident.objects.create(
                    workspace_id=ADMIN_FLOW_WORKSPACE,
                    job_task=act,
                    description=f"{desc} instance {i}",
                    control_type=bar,
                    control_condition="FAILED" if i % 2 == 0 else "ABSENT",
                    location=loc,
                    incident_date="2026-06-01",
                )
                PredictionResult.objects.create(
                    incident=inc,
                    model_version=active_model,
                    psif_probability=0.88 if is_psif else 0.20,
                    psif_predicted=is_psif,
                    risk_level="HIGH" if is_psif else "LOW",
                )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns_location")
        resp = client.get(url)

        assert resp.status_code == 200
        view_data = resp.context["location_data"]

        assert view_data["total_workspace_incidents"] == 100
        assert view_data["total_filtered_incidents"] == 100
        assert len(view_data["locations"]) == 4

        locs = view_data["locations"]
        # Rank 1: Process Area
        assert locs[0]["internal_location"] == "Process Area / Refining Unit"
        assert locs[0]["rank"] == 1
        assert locs[0]["incident_count"] == 42
        assert locs[0]["psif_linked_count"] == 18
        assert locs[0]["share_of_total"] == 42.0
        assert locs[0]["share_label"] == "42.0% (42/100)"
        assert locs[0]["top_activity"] == "Hot Work in Classified Area"

        # Rank 2: Compressor Area
        assert locs[1]["internal_location"] == "Compressor Area"
        assert locs[1]["rank"] == 2
        assert locs[1]["incident_count"] == 30
        assert locs[1]["psif_linked_count"] == 12
        assert locs[1]["share_of_total"] == 30.0

        # Rank 3: Workshop
        assert locs[2]["internal_location"] == "Workshop / Maintenance Bay"
        assert locs[2]["rank"] == 3
        assert locs[2]["incident_count"] == 18

        # Rank 4: Tank Farm
        assert locs[3]["internal_location"] == "Tank Farm"
        assert locs[3]["rank"] == 4
        assert locs[3]["incident_count"] == 10

        # HTML assertions
        content = resp.content.decode()
        assert "HIGHEST OBSERVATION CONCENTRATION" in content
        assert "42 incidents" in content or "42" in content
        assert "Percentage denominator: incident count / 100 total incidents" in content

    def test_heat_intensity_derivation_and_scale(self, client, admin_flow_user):
        """
        Verifies heat intensity derivation from frequency:
        - Highest location: intensity 1.0 (Critical / Red #C62828).
        - Continuous heat scale: critical, elevated, moderate, low, zero.
        - Legend title: "INCIDENT OBSERVATION DENSITY".
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Create 100 incidents in Process Area, 60 in Compressor, 30 in Workshop, 10 in Wellhead
        distribution = [
            ("Process Area", 100),
            ("Compressor Area", 60),
            ("Workshop", 30),
            ("Wellhead Area", 10),
        ]
        for loc, count in distribution:
            for i in range(count):
                Incident.objects.create(
                    workspace_id=ADMIN_FLOW_WORKSPACE,
                    description=f"Incident {i} in {loc}",
                    location=loc,
                )

        data = get_admin_flow_location_pattern_view_data()
        loc_map = {l["internal_location"]: l for l in data["locations"]}

        # Process Area: 100/100 -> intensity 1.0 -> critical (red)
        pa = loc_map["Process Area / Refining Unit"]
        assert pa["heatmap_intensity"] == 1.0
        assert pa["heat_level"] == "critical"
        assert pa["heat_color"] == "#C62828"

        # Compressor Area: 60/100 -> intensity 0.6 -> elevated (orange)
        ca = loc_map["Compressor Area"]
        assert ca["heatmap_intensity"] == 0.6
        assert ca["heat_level"] == "elevated"
        assert ca["heat_color"] == "#E65100"

        # Workshop: 30/100 -> intensity 0.3 -> moderate (yellow)
        ws = loc_map["Workshop / Maintenance Bay"]
        assert ws["heatmap_intensity"] == 0.3
        assert ws["heat_level"] == "moderate"
        assert ws["heat_color"] == "#F57F17"

        # Wellhead: 10/100 -> intensity 0.1 -> low (green)
        wh = loc_map["Wellhead Area"]
        assert wh["heatmap_intensity"] == 0.1
        assert wh["heat_level"] == "low"
        assert wh["heat_color"] == "#2E7D32"

        # Legend title check
        assert data["legend_title"] == "INCIDENT OBSERVATION DENSITY"

    def test_pattern_relationship_chain_view(self, client, admin_flow_user):
        """
        Verifies:
        - Location -> Activity -> Barrier-linked signal pattern chain.
        - Example: Process Area -> Hot Work in Classified Area -> Gas-testing deficiency.
        - Enforces neutral caption: "Observed relationship in Admin Flow data."
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        for i in range(5):
            Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                job_task="Hot Work in Classified Area",
                description=f"Flange welding near gas manifold #{i}",
                control_type="Gas Testing / Atmospheric Monitoring",
                control_condition="FAILED",
                location="Process Area",
            )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns_location")
        resp = client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode()

        # Pattern relationship chain wording
        assert "PATTERN RELATIONSHIP CHAIN" in content
        assert "Observed relationship in Admin Flow data." in content

        view_data = resp.context["location_data"]
        chain = view_data["top_location"]["pattern_chain"]
        assert chain is not None
        assert chain["location"] == "Process Area / Refining Unit"
        assert chain["top_activity"] == "Hot Work in Classified Area"
        assert chain["top_barrier"] in ["Gas Testing / Atmospheric Monitoring", "Gas Detection / Atmospheric Monitoring"]
        assert chain["relationship_label"] == "Observed relationship in Admin Flow data."

    def test_unknown_location_handling(self, client, admin_flow_user):
        """Verifies missing or vague location normalizes to UNKNOWN LOCATION without crashing."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Inspection",
            description="General incident somewhere on site.",
            location=None,
        )

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:patterns_location"))
        assert resp.status_code == 200
        view_data = resp.context["location_data"]

        assert view_data["total_filtered_incidents"] == 1
        assert len(view_data["locations"]) == 1
        assert view_data["locations"][0]["internal_location"] == "UNKNOWN LOCATION"
        assert view_data["locations"][0]["incident_count"] == 1

    def test_schematic_site_grid_and_no_fabricated_coordinates(self, client, admin_flow_user):
        """
        Verifies:
        - 3x3 Schematic Grid represents the 9 canonical layout zones:
          Workshop, Process Area, Tank Farm, Warehouse, Compressor Area, Pipe Rack,
          Main Gate, Wellhead, Drilling Area.
        - Textual names are mapped to schematic cells, NEVER inventing latitude/longitude.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Workshop incident",
            location="Workshop",
        )
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Main Gate access badge failed",
            location="Main Gate",
        )

        data = get_admin_flow_location_pattern_view_data()
        grid = data["schematic_grid"]

        # Exactly 9 schematic grid zones
        assert len(grid) == 9
        codes = [z["code"] for z in grid]
        assert codes == ["Z-01", "Z-02", "Z-03", "Z-04", "Z-05", "Z-06", "Z-07", "Z-08", "Z-09"]

        # Check Workshop (Z-01) has observations
        z01 = [z for z in grid if z["code"] == "Z-01"][0]
        assert z01["has_observations"] is True
        assert z01["incident_count"] == 1

        # Check Main Gate (Z-07) has observations
        z07 = [z for z in grid if z["code"] == "Z-07"][0]
        assert z07["has_observations"] is True
        assert z07["incident_count"] == 1

        # Check Process Area (Z-02) has 0 observations but is rendered in layout
        z02 = [z for z in grid if z["code"] == "Z-02"][0]
        assert z02["has_observations"] is False
        assert z02["incident_count"] == 0

        # Assert no GIS coordinates in data
        assert "latitude" not in str(data).lower()
        assert "longitude" not in str(data).lower()

    def test_filtering_psif_and_query(self, client, admin_flow_user, active_model):
        """Verifies simple filters: PSIF status and text query."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Incident 1: Process Area, PSIF
        inc1 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Hot Work",
            description="Process unit heater tube leak",
            location="Process Area",
        )
        PredictionResult.objects.create(
            incident=inc1,
            model_version=active_model,
            psif_probability=0.9,
            psif_predicted=True,
            risk_level="HIGH",
        )

        # Incident 2: Compressor Area, NOT PSIF
        inc2 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Filter Cleaning",
            description="Compressor air intake filter replacement",
            location="Compressor Area",
        )
        PredictionResult.objects.create(
            incident=inc2,
            model_version=active_model,
            psif_probability=0.1,
            psif_predicted=False,
            risk_level="LOW",
        )

        client.force_login(admin_flow_user)

        # 1. Filter by PSIF only
        resp = client.get(reverse("admin_flow:patterns_location"), {"psif": "psif"})
        assert resp.status_code == 200
        view_data = resp.context["location_data"]
        assert view_data["total_filtered_incidents"] == 1
        assert len(view_data["locations"]) == 1
        assert view_data["locations"][0]["internal_location"] == "Process Area / Refining Unit"

        # 2. Filter by search query (q=air intake)
        resp = client.get(reverse("admin_flow:patterns_location"), {"q": "air intake"})
        assert resp.status_code == 200
        view_data = resp.context["location_data"]
        assert view_data["total_filtered_incidents"] == 1
        assert view_data["locations"][0]["internal_location"] == "Compressor Area"

    def test_workspace_isolation_hard_segregation(self, client, admin_flow_user):
        """Verifies global incidents (workspace_id IS NULL) are completely excluded."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Global incidents
        for i in range(20):
            Incident.objects.create(
                workspace_id=None,
                description=f"Global refinery incident {i}",
                location="Process Area",
            )

        # Admin Flow incident
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Admin Flow single incident in Workshop",
            location="Workshop",
        )

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:patterns_location"))
        assert resp.status_code == 200
        view_data = resp.context["location_data"]

        # Admin Flow must strictly see only 1 incident and 1 location (Workshop), NOT Process Area
        assert view_data["total_workspace_incidents"] == 1
        assert len(view_data["locations"]) == 1
        assert view_data["locations"][0]["internal_location"] == "Workshop / Maintenance Bay"

    def test_role_based_access_control(self, client, standard_user):
        """Verifies non-admin flow users are denied access (403 Forbidden)."""
        client.force_login(standard_user)
        resp = client.get(reverse("admin_flow:patterns_location"))
        assert resp.status_code == 403

        # Anonymous user gets redirected to login
        client.logout()
        resp = client.get(reverse("admin_flow:patterns_location"))
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    def test_location_patterns_api(self, client, admin_flow_user):
        """Verifies GET /admin-flow/api/patterns/location/ returns full JSON payload with filters."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Valve check",
            description="Wellhead manifold check",
            location="Wellhead",
        )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:api_patterns_location")
        resp = client.get(url)

        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == "admin_flow"
        assert data["site_context"] == ADMIN_FLOW_SITE_NAME
        assert data["total_filtered_incidents"] == 1
        assert len(data["locations"]) == 1
        assert data["locations"][0]["internal_location"] == "Wellhead Area"
        assert data["locations"][0]["incident_count"] == 1
        assert data["top_location"]["name"] == "Wellhead Area"
        assert data["top_location"]["callout_caption"] == "Highest observation concentration in the current Admin Flow dataset."
        assert len(data["schematic_grid"]) == 9

    def test_visual_site_intelligence_workspace_structures(self, client, admin_flow_user, active_model):
        """
        Verifies:
        1. 4 summary cards: card1 (Highest concentration), card2 (Operating zones),
           card3 (PSIF-linked concentration), card4 (Location attribution rate).
        2. 100% data reconciliation in coverage_stats:
           location_identified_count + unknown_location_count == total_incidents.
        3. Cross-dimensional matrices: iogp_matrix with 9 canonical rules, activity_matrix.
        4. Ranking bars data with proportional width.
        5. Visual workspace rendering in HTML:
           - Cross-Dimensional Risk Intelligence Matrix
           - Zoom controls
           - Detail inspector elements
           - Auditability guarantee notice.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Create known locations with IOGP rules
        test_data = [
            ("Process Area", "Hot Work in Classified Area", "Hot Work", "FAILED", True),
            ("Process Area", "Hot Work in Classified Area", "Work Authorization", "ABSENT", False),
            ("Compressor Area", "Routine Operational Maintenance", "Energy Isolation", "FAILED", True),
            ("Workshop", "Machining and Tool Operation", "Line of Fire", "BYPASSED", False),
            (None, "General inspection narrative without explicit location", "Bypassing Safety Controls", "FAILED", True),
        ]

        for loc, task, bar, cond, is_psif in test_data:
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                job_task=task,
                description=f"Operational event for {task} at {loc}" if loc else f"Operational event for {task}",
                control_type=bar,
                control_condition=cond,
                location=loc,
                incident_date="2026-06-15",
            )
            PredictionResult.objects.create(
                incident=inc,
                model_version=active_model,
                psif_probability=0.85 if is_psif else 0.15,
                psif_predicted=is_psif,
                risk_level="HIGH" if is_psif else "LOW",
            )

        data = get_admin_flow_location_pattern_view_data()

        # 1. Verify summary cards
        summary = data["summary"]
        assert "card1" in summary
        assert "card2" in summary
        assert "card3" in summary
        assert "card4" in summary

        assert summary["card1"]["name"] == "Process Area / Refining Unit"
        assert summary["card1"]["incident_count"] == 2
        assert summary["card1"]["psif_count"] == 1

        assert summary["card2"]["count"] == 3  # Process Area, Compressor Area, Workshop
        assert summary["card3"]["count"] == 3  # 3 PSIF incidents total
        assert summary["card4"]["known_count"] == 4
        assert summary["card4"]["unknown_count"] == 1

        # 2. Verify coverage stats reconciliation
        cov = data["coverage_stats"]
        assert cov["total_incidents"] == 5
        assert cov["location_identified_count"] == 4
        assert cov["unknown_location_count"] == 1
        assert cov["location_identified_count"] + cov["unknown_location_count"] == cov["total_incidents"]
        assert cov["location_identified_pct"] == 80.0
        assert cov["unknown_location_pct"] == 20.0

        # 3. Verify IOGP Matrix
        matrix = data["iogp_matrix"]
        assert len(matrix["columns"]) == 9
        assert "Hot Work" in matrix["columns"]
        assert "Energy Isolation" in matrix["columns"]
        assert "Line of Fire" in matrix["columns"]
        assert len(matrix["rows"]) == 3  # 3 known locations with observations

        # 4. Verify Ranking Bars
        bars = data["ranking_bars"]
        assert len(bars) >= 3
        assert bars[0]["name"] == "Process Area / Refining Unit"
        assert bars[0]["bar_width_pct"] == 100.0

        # 5. HTML rendering test
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:patterns_location"))
        assert resp.status_code == 200
        content = resp.content.decode()

        assert "Site-Intelligence Workspace" in content
        assert "Cross-Dimensional Risk Intelligence Matrix" in content
        assert "IOGP Life-Saving Rules Matrix" in content
        assert "Operational Activity Matrix" in content
        assert "zoomIn()" in content
        assert "zoomOut()" in content
        assert "resetZoom()" in content
        assert "PATTERN RELATIONSHIP CHAIN" in content
        assert "Auditability Guarantee:" in content

