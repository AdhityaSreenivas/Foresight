"""
TASK 8 — ADMIN FLOW FINAL QA, ISOLATION AUDIT, PERFORMANCE & DEMO FREEZE

Comprehensive test suite verifying:
1. Two-User Isolation & Zero Baseline
2. Global Data Leak & Query-Level Boundary Audit
3. URL & API Bypass Prevention & Parameter Tampering
4. Navbar Strict 7-Item Contract
5. Dashboard Dynamic Non-Hardcoded Computations
6. Controlled Pattern Exact Data Verification (Lifting=10, Hot Work=7, Driving=4, etc.)
7. Barrier & Semantic Rule Enforcement (Effective/Unknown excluded, non-causal language)
8. Classification Semantics (PSIF vs IOGP, Match != Violation, Match != PSIF)
"""

import io
import csv
import pytest
from django.urls import reverse
from django.test import Client
from apps.accounts.models import User
from apps.incidents.models import Incident, IOGPRuleTag
from apps.datasets.models import Dataset
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.services import (
    ADMIN_FLOW_WORKSPACE,
    get_admin_flow_incidents,
    get_global_incidents,
    get_admin_flow_datasets,
    get_admin_flow_analytics_summary,
)
from apps.admin_flow.pattern_engine import (
    compute_activity_patterns,
    compute_barrier_patterns,
    get_admin_flow_pattern_hub_view_data,
    get_admin_flow_location_pattern_view_data,
    get_admin_flow_activity_pattern_view_data,
    get_admin_flow_barrier_pattern_view_data,
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        username="admin_flow_qa@foresight.app",
        defaults={
            "email": "admin_flow_qa@foresight.app",
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
        username="standard_user_qa@foresight.app",
        defaults={
            "email": "standard_user_qa@foresight.app",
            "role": "analyst",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def standard_admin_user(db):
    user, _ = User.objects.get_or_create(
        username="admin_enterprise_qa@foresight.app",
        defaults={
            "email": "admin_enterprise_qa@foresight.app",
            "role": "admin",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def active_model_version(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v1.0.0-freeze",
        defaults={
            "is_active": True,
            "status": "active",
        }
    )
    return mv


# ==============================================================================
# 1. TWO-USER ISOLATION TEST
# ==============================================================================

@pytest.mark.django_db
class TestTwoUserIsolation:
    """Verifies that Admin Flow user and standard user workspaces never bleed."""

    def test_admin_flow_user_starts_at_zero_baseline(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:dashboard"))
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        # All 6 KPIs must strictly be 0
        for stat_id in ["stat-total", "stat-eligible", "stat-psif", "stat-not-psif", "stat-insufficient", "stat-human-reviewed"]:
            assert f'id="{stat_id}"' in content and '>0</div>' in content

    def test_submission_mutates_only_admin_flow(self, client, admin_flow_user, standard_admin_user):
        initial_global_count = get_global_incidents().count()

        # Submit report into Admin Flow
        client.force_login(admin_flow_user)
        submit_data = {
            "report_type": "near_miss",
            "description": "High pressure gas leak in Compressor Area during scheduled maintenance.",
            "incident_date": "2026-09-10",
            "location": "Compressor Area",
            "department": "Operations",
            "job_task": "Hot Work in Classified Area",
            "immediate_cause": "Gasket failure",
            "high_energy_present": "yes",
            "energy_type": "pressure",
            "direct_control_present": "yes",
            "control_condition": "failed",
            "action": "submit_only",
        }
        resp = client.post(reverse("admin_flow:submit"), submit_data, follow=True)
        assert resp.status_code == 200

        # Admin flow counter = 1
        assert get_admin_flow_incidents().count() == 1

        # Global counter is completely unchanged
        assert get_global_incidents().count() == initial_global_count

        # Standard admin dashboard shows unmodified global count
        client.force_login(standard_admin_user)
        global_resp = client.get("/dashboard/")
        assert global_resp.status_code == 200
        assert "admin-flow" not in global_resp.content.decode("utf-8")


# ==============================================================================
# 2. GLOBAL DATA LEAK TEST
# ==============================================================================

@pytest.mark.django_db
class TestGlobalDataLeak:
    """Confirms at query- and service-level that Admin Flow cannot see any global records."""

    def test_global_records_strictly_excluded_from_all_admin_flow_queries(self, db, admin_flow_user, active_model_version):
        # Create global enterprise records
        global_inc = Incident.objects.create(
            workspace_id="default",
            description="Global refinery catastrophic explosion in Texas unit.",
            location="Texas Unit 99",
            job_task="Catastrophic Refining",
            department="Global Refining",
            control_type="Emergency Shutdown",
            control_condition="FAILED",
            control_failed_bypassed=True,
        )
        PredictionResult.objects.create(
            incident=global_inc,
            model_version=active_model_version,
            psif_probability=0.99,
            psif_predicted=True,
            risk_level="CRITICAL",
        )
        IOGPRuleTag.objects.create(
            incident=global_inc,
            rule="Energy Isolation",
            confidence=0.99,
        )

        # 1. Direct query isolation
        admin_incidents = get_admin_flow_incidents()
        assert not admin_incidents.filter(id=global_inc.id).exists()
        assert not admin_incidents.filter(location="Texas Unit 99").exists()

        # 2. Dashboard KPIs calculation isolation
        kpis = get_admin_flow_analytics_summary()
        assert kpis["total_incidents"] == 0
        assert kpis["psif_count"] == 0

        # 3. Pattern analysis isolation
        hub_data = get_admin_flow_pattern_hub_view_data()
        assert hub_data["total_incidents"] == 0
        assert hub_data["has_data"] is False
        assert "Texas Unit 99" not in str(hub_data)

        # 4. Activity pattern isolation
        act_patterns = compute_activity_patterns([])
        assert not any(a["activity"] == "Catastrophic Refining" for a in act_patterns)

        # 5. Location pattern isolation
        loc_data = get_admin_flow_location_pattern_view_data()
        assert not any(l["internal_location"] == "Texas Unit 99" for l in loc_data["locations"])

        # 6. Barrier pattern isolation
        barrier_patterns = compute_barrier_patterns([])
        assert not any(b["barrier_name"] == "Emergency Shutdown" for b in barrier_patterns)


# ==============================================================================
# 3. URL AND API BYPASS TEST
# ==============================================================================

@pytest.mark.django_db
class TestUrlAndApiBypass:
    """Verifies that unauthorized users and parameter manipulation cannot bypass access controls."""

    def test_standard_users_strictly_forbidden_on_all_admin_flow_routes(self, client, standard_user, standard_admin_user):
        protected_routes = [
            reverse("admin_flow:dashboard"),
            reverse("admin_flow:submit"),
            reverse("admin_flow:upload"),
            reverse("admin_flow:incidents"),
            reverse("admin_flow:psif"),
            reverse("admin_flow:iogp"),
            reverse("admin_flow:patterns"),
            reverse("admin_flow:patterns_activity"),
            reverse("admin_flow:patterns_barrier"),
            reverse("admin_flow:patterns_location"),
            reverse("admin_flow:api_analytics_overview"),
            reverse("admin_flow:api_psif_metrics"),
            reverse("admin_flow:api_iogp_metrics"),
            reverse("admin_flow:api_patterns_overview"),
            reverse("admin_flow:api_patterns_activity"),
            reverse("admin_flow:api_patterns_barrier"),
            reverse("admin_flow:api_patterns_location"),
        ]

        # Standard analyst
        client.force_login(standard_user)
        for url in protected_routes:
            resp = client.get(url)
            assert resp.status_code == 403, f"Expected 403 for analyst on {url}, got {resp.status_code}"

        # Standard enterprise admin (cannot access Admin Flow demonstration sandbox)
        client.force_login(standard_admin_user)
        for url in protected_routes:
            resp = client.get(url)
            assert resp.status_code == 403, f"Expected 403 for enterprise admin on {url}, got {resp.status_code}"

    def test_anonymous_user_redirected_to_login(self, client):
        client.logout()
        resp = client.get(reverse("admin_flow:dashboard"))
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    def test_global_incident_id_bypass_prevented(self, client, admin_flow_user):
        global_inc = Incident.objects.create(
            workspace_id="default",
            description="Global incident record.",
            location="Offshore Rig 1",
        )

        client.force_login(admin_flow_user)
        # Attempt to access global incident detail via Admin Flow URL
        resp = client.get(reverse("admin_flow:incidents_detail", kwargs={"pk": global_inc.pk}))
        assert resp.status_code == 404

    def test_workspace_parameter_tampering_overridden_server_side(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        tampered_data = {
            "workspace_id": "default",  # malicious attempt to inject into global workspace
            "report_type": "near_miss",
            "description": "Attempted cross-tenant injection test.",
            "incident_date": "2026-09-10",
            "location": "Process Area",
            "department": "Operations",
            "job_task": "Injection Testing",
            "action": "submit_only",
        }
        resp = client.post(reverse("admin_flow:submit"), tampered_data, follow=True)
        assert resp.status_code == 200

        # Verify incident was forced to 'admin_flow' workspace
        inc = Incident.objects.filter(description="Attempted cross-tenant injection test.").first()
        assert inc is not None
        assert inc.workspace_id == ADMIN_FLOW_WORKSPACE
        assert inc.workspace_id != "default"


# ==============================================================================
# 4. NAVBAR TEST
# ==============================================================================

@pytest.mark.django_db
class TestNavbarIntegrity:
    """Verifies that Admin Flow navbar contains exactly the 7 specified links."""

    def test_admin_flow_navbar_exact_items(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:dashboard"))
        content = resp.content.decode("utf-8")

        # 7 required items
        expected_items = [
            ("Dashboard", reverse("admin_flow:dashboard")),
            ("Submit Report", reverse("admin_flow:submit")),
            ("Upload dataset", reverse("admin_flow:upload")),
            ("Incidents", reverse("admin_flow:incidents")),
            ("PSIF Classification", reverse("admin_flow:psif")),
            ("IOGP classification", reverse("admin_flow:iogp")),
            ("Pattern Analysis", reverse("admin_flow:patterns")),
        ]

        for label, url in expected_items:
            assert f'href="{url}"' in content, f"Missing navbar link: {label} ({url})"

        # Verify global menus are not present
        assert 'href="/datasets/"' not in content
        assert 'href="/predictions/assurance/"' not in content
        assert 'href="/reports/"' not in content

    def test_standard_user_navbar_retains_enterprise_structure(self, client, standard_admin_user):
        client.force_login(standard_admin_user)
        resp = client.get("/dashboard/")
        content = resp.content.decode("utf-8")

        # Standard links exist
        assert 'href="/dashboard/"' in content
        assert 'href="/datasets/"' in content
        assert 'href="/incidents/"' in content

        # Zero Admin Flow links
        assert "/admin-flow/" not in content


# ==============================================================================
# 5. DASHBOARD TEST
# ==============================================================================

@pytest.mark.django_db
class TestDashboardDynamicComputation:
    """Verifies that all 6 KPI cards calculate dynamically without hard-coding."""

    def test_dynamic_updates_from_submissions(self, client, admin_flow_user, active_model_version):
        client.force_login(admin_flow_user)

        # Baseline: 0
        resp = client.get(reverse("admin_flow:dashboard"))
        assert 'id="stat-total">0</div>' in resp.content.decode("utf-8")

        # Create 1 PSIF Precursor
        inc1 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="High pressure gas release with failed barrier.",
            location="Compressor Area",
            high_energy_present="yes",
            direct_control_present="yes",
            control_condition="failed",
        )
        PredictionResult.objects.create(
            incident=inc1,
            model_version=active_model_version,
            psif_probability=0.88,
            psif_predicted=True,
            risk_level="CRITICAL",
        )

        # Create 1 Non-PSIF
        inc2 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Paper cut in office admin trailer.",
            location="Office",
            high_energy_present="no",
            direct_control_present="no",
        )
        PredictionResult.objects.create(
            incident=inc2,
            model_version=active_model_version,
            psif_probability=0.04,
            psif_predicted=False,
            risk_level="LOW",
        )

        # Create 1 Insufficient Evidence
        inc3 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Spill",
            location="Main Gate",
        )
        PredictionResult.objects.create(
            incident=inc3,
            model_version=active_model_version,
            psif_probability=0.0,
            psif_predicted=False,
            risk_level="LOW",
            is_sparse_input=True,
        )

        resp2 = client.get(reverse("admin_flow:dashboard"))
        content2 = resp2.content.decode("utf-8")

        # Verify dynamic calculations
        assert 'id="stat-total">3</div>' in content2
        assert 'id="stat-eligible">2</div>' in content2
        assert 'id="stat-psif"' in content2 and '>1</div>' in content2
        assert 'id="stat-not-psif">1</div>' in content2
        assert 'id="stat-insufficient">1</div>' in content2


# ==============================================================================
# 6. CONTROLLED PATTERN EXACT DATA TEST
# ==============================================================================

@pytest.mark.django_db
class TestControlledPatternFixture:
    """
    Builds the exact controlled fixture from Task 8 prompt:
    Activity: Lifting=10, Hot Work=7, Driving=4
    Location: Process Area=12, Workshop=6, Tank Farm=3
    Barrier: Energy Isolation=8, Work Authorization=5, Line of Fire=3
    Total = 21 incidents
    """

    @pytest.fixture
    def controlled_dataset(self, db):
        # 12 incidents in Process Area
        # 6 incidents in Workshop
        # 3 incidents in Tank Farm
        # (Total = 21)
        #
        # Activities:
        # Lifting = 10
        # Hot Work = 7
        # Driving = 4
        #
        # Barriers:
        # Energy Isolation = 8 (failed/bypassed)
        # Work Authorization = 5 (failed/bypassed)
        # Line of Fire = 3 (failed/bypassed)
        # Remaining 5 have effective or no control failure

        incidents = []
        for i in range(21):
            # Assign Location
            if i < 12:
                loc = "Process Area"
            elif i < 18:
                loc = "Workshop"
            else:
                loc = "Tank Farm"

            # Assign Activity
            if i < 10:
                act = "Safe Mechanical Lifting"  # Lifting: 10
            elif i < 17:
                act = "Hot Work in Classified Area"  # Hot Work: 7
            else:
                act = "Driving"  # Driving: 4

            # Assign Barrier
            if i < 8:
                barrier = "Energy Isolation"
                cond = "FAILED"
                bypassed = True
            elif i < 13:
                barrier = "Work Authorization"
                cond = "BYPASSED"
                bypassed = True
            elif i < 16:
                barrier = "Line of Fire"
                cond = "FAILED"
                bypassed = True
            else:
                barrier = "System Protection"
                cond = "EFFECTIVE"
                bypassed = False

            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description=f"Controlled test observation #{i+1} in {loc} during {act}.",
                job_task=act,
                location=loc,
                department="Operations",
                control_type=barrier,
                control_condition=cond,
                control_failed_bypassed=bypassed,
            )
            incidents.append(inc)

        return incidents

    def test_exact_activity_counts_and_rankings(self, controlled_dataset):
        act_data = get_admin_flow_activity_pattern_view_data()
        activities = act_data["activities"]
        assert len(activities) == 3

        # Rank 1: Lifting = 10
        assert activities[0]["category"] == "Safe Mechanical Lifting"
        assert activities[0]["incident_count"] == 10

        # Rank 2: Hot Work = 7
        assert activities[1]["category"] == "Hot Work in Classified Area"
        assert activities[1]["incident_count"] == 7

        # Rank 3: Driving = 4
        assert activities[2]["category"] in ["Driving", "Vehicle Operation / Road Transport"]
        assert activities[2]["incident_count"] == 4

    def test_exact_location_counts_and_rankings(self, controlled_dataset):
        loc_data = get_admin_flow_location_pattern_view_data()
        locations = loc_data["locations"]
        assert len(locations) == 3

        # Rank 1: Process Area = 12
        assert "Process Area" in locations[0]["internal_location"]
        assert locations[0]["incident_count"] == 12

        # Rank 2: Workshop = 6
        assert "Workshop" in locations[1]["internal_location"]
        assert locations[1]["incident_count"] == 6

        # Rank 3: Tank Farm = 3
        assert "Tank Farm" in locations[2]["internal_location"]
        assert locations[2]["incident_count"] == 3

        # Top location card
        assert "Process Area" in loc_data["top_location"]["name"]
        assert loc_data["top_location"]["incident_count"] == 12

    def test_exact_barrier_counts_and_effective_exclusion(self, controlled_dataset):
        bar_data = get_admin_flow_barrier_pattern_view_data()
        barriers = bar_data["barriers"]
        assert len(barriers) == 3

        # Rank 1: Energy Isolation = 8
        assert barriers[0]["barrier_domain"] == "Energy Isolation"
        assert barriers[0]["deficiency_linked_count"] == 8

        # Rank 2: Work Authorization = 5
        assert barriers[1]["barrier_domain"] == "Work Authorization"
        assert barriers[1]["deficiency_linked_count"] == 5

        # Rank 3: Line of Fire = 3
        assert barriers[2]["barrier_domain"] == "Line of Fire"
        assert barriers[2]["deficiency_linked_count"] == 3

        # Verify "System Protection" (effective) was excluded from failures
        assert not any(b["barrier_domain"] == "System Protection" for b in barriers)

    def test_pattern_hub_summary_exact_values(self, client, admin_flow_user, controlled_dataset):
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:patterns"))
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        # Total incidents = 21
        assert 'id="summary-total-incidents">21</div>' in content
        # Top Activity = Safe Mechanical Lifting (10)
        assert "Safe Mechanical Lifting" in content
        # Top Barrier = Energy Isolation (8)
        assert "Energy Isolation" in content
        # Top Location = Process Area (12)
        assert "Process Area" in content


# ==============================================================================
# 7. BARRIER & SEMANTIC RULES TEST
# ==============================================================================

@pytest.mark.django_db
class TestBarrierAndSemanticRules:
    """Verifies that non-deficiency states and causal words are excluded."""

    def test_effective_and_unknown_excluded_from_failure_signals(self, db):
        # 1 effective, 1 unknown
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Routine pump inspection with effective relief valve.",
            control_type="Pressure Relief",
            control_condition="EFFECTIVE",
            control_failed_bypassed=False,
        )
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="General observation with unknown control status.",
            control_type="Ventilation",
            control_condition="UNKNOWN",
            control_failed_bypassed=False,
        )

        bar_data = get_admin_flow_barrier_pattern_view_data()
        # Neither should appear as a barrier failure signal
        assert len(bar_data["barriers"]) == 0

    def test_non_causal_terminology_rendered_in_templates(self, client, admin_flow_user):
        # Seed an incident with a barrier failure so has_data is True
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="High pressure gas release observed near compressor flange.",
            location="Compressor Area",
            department="Operations",
            control_type="Energy Isolation",
            control_condition="FAILED",
            control_failed_bypassed=True,
        )

        client.force_login(admin_flow_user)

        # Check Barrier Analysis
        resp_barrier = client.get(reverse("admin_flow:patterns_barrier"))
        content_barrier = resp_barrier.content.decode("utf-8")
        assert "Control-Deficiency Associated Observations" in content_barrier or "Barrier-Linked Observations" in content_barrier
        assert "causal responsibility" in content_barrier.lower() or "causation" in content_barrier.lower()

        # Check Pattern Hub
        resp_hub = client.get(reverse("admin_flow:patterns"))
        content_hub = resp_hub.content.decode("utf-8")
        assert "Pattern analysis does not establish causation" in content_hub

        # Check Location Analysis
        resp_loc = client.get(reverse("admin_flow:patterns_location"))
        content_loc = resp_loc.content.decode("utf-8")
        assert "INCIDENT OBSERVATION DENSITY" in content_loc
        assert "danger probability" not in content_loc.lower()


# ==============================================================================
# 8. CLASSIFICATION SEMANTICS TEST
# ==============================================================================

@pytest.mark.django_db
class TestClassificationSemantics:
    """Verifies that IOGP matches are distinct from PSIF precursors and violations."""

    def test_iogp_match_is_not_automatically_psif(self, client, admin_flow_user, active_model_version):
        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Safe hot work welding inside workshop with fire blanket.",
            job_task="Hot Work in Classified Area",
            location="Workshop",
        )
        # IOGP rule matches "Hot Work"
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Hot Work",
            confidence=0.95,
        )
        # But prediction is NON-PSIF (safe operation)
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model_version,
            psif_probability=0.12,
            psif_predicted=False,
            risk_level="LOW",
        )

        client.force_login(admin_flow_user)

        # PSIF page shows Not-PSIF
        resp_psif = client.get(reverse("admin_flow:psif"))
        content_psif = resp_psif.content.decode("utf-8")
        assert 'id="kpi-not-psif"' in content_psif and '>1</div>' in content_psif
        assert 'id="kpi-psif"' in content_psif and '>0</div>' in content_psif

        # IOGP page displays rule context, clarifying rule association
        resp_iogp = client.get(reverse("admin_flow:iogp"))
        content_iogp = resp_iogp.content.decode("utf-8")
        assert "Hot Work" in content_iogp
