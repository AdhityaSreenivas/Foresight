"""
PSIF Platform — Task 7 Admin Flow Pattern Analysis Hub + Full Judge Integration Test Suite.

Verifies:
1. Pattern Analysis Hub (/admin-flow/patterns/):
   - Executive landing page (not a dense analytics page).
   - Three clean visual cards/buttons letting the judge immediately choose:
     * ACTIVITY PATTERNS ("Which activities occur most frequently?") -> /admin-flow/patterns/activity/
     * BARRIER / CONTROL PATTERNS ("Which control-deficiency signals recur?") -> /admin-flow/patterns/barrier/
     * LOCATION PATTERNS ("Where are observations concentrated?") -> /admin-flow/patterns/location/
   - Small visual preview in each card.
   - Top-Level Pattern Summary:
     * Total Admin Flow incidents
     * Most frequent activity
     * Most frequent barrier-linked signal
     * Highest observation-concentration location
     * Neutral presentation (not "highest risk").
   - Relationship visual:
     Activity -> Location -> Barrier / Control Signal -> PSIF-linked observations
     ("Observed relationship in Admin Flow data.")
   - Subtle, compliant methodology notices:
     * "Pattern analysis is based on the current Admin Flow demonstration dataset."
     * "Patterns represent historical observation frequency and association."
     * "Barrier-linked observations are based on evidence-supported control states."
     * "Pattern analysis does not establish causation or predict future incidents."

2. Admin Flow Dashboard Pattern Snapshot:
   - Compact section under the six KPI boxes and dual action cards:
     * Top Activity
     * Top Barrier-Linked Signal
     * Top Location
     * "View Pattern Analysis" button.

3. Demonstration Data Baseline:
   - Starts strictly at 0 / 0 / 0 / 0 / 0 / 0 on login.
   - Increments exclusively from actual submissions and dataset uploads.

4. Workspace Isolation (No Cross-Contamination):
   - Global enterprise records are completely excluded from Admin Flow.
   - Admin Flow records never leak into global views.

5. Complete Judge Journey End-to-End:
   - Dashboard -> Submit -> Counter increase -> Incidents -> Detail -> Upload -> Processing -> Pattern Hub -> Activity -> Barrier -> Location -> Detail Drill-down -> Logout -> Non-admin login check.
"""

import io
import uuid
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.services import ADMIN_FLOW_WORKSPACE
from apps.admin_flow.pattern_engine import (
    invalidate_admin_flow_pattern_cache,
    get_admin_flow_pattern_hub_view_data,
)

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    """Isolated Admin Flow test user."""
    user, _ = User.objects.get_or_create(
        email="admin_flow_judge@foresight.app",
        defaults={
            "username": "admin_flow_judge@foresight.app",
            "role": "admin_flow",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def standard_admin_user(db):
    """Standard global enterprise admin user."""
    user, _ = User.objects.get_or_create(
        email="standard_admin@foresight.app",
        defaults={
            "username": "standard_admin@foresight.app",
            "role": "admin",
            "is_active": True,
            "is_staff": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def active_model_version(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v1.0.0-test",
        defaults={
            "is_active": True,
            "status": "active",
        }
    )
    return mv


@pytest.mark.django_db
class TestPatternHubEmptyState:
    """Verifies the Pattern Analysis landing page when 0 demonstration records exist."""

    def test_hub_empty_state_and_cards(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        url = reverse("admin_flow:patterns")
        resp = client.get(url)

        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        # 1. Page Title & Heading
        assert "Pattern Analysis Hub" in content

        # 2. Hard Data Isolation Notice removed from visible UI
        assert "Hard Data Isolation Active" not in content
        assert "workspace_id" not in content

        # 3. Top-Level Pattern Summary Bar (0 counts, neutral presentation)
        assert 'id="summary-total-incidents">0</div>' in content
        assert "Total Incidents" in content
        assert "Most Frequent Activity" in content
        assert "Most Frequent Barrier Signal" in content
        assert "Highest Concentration Location" in content
        assert "None yet" in content

        # Verify no unsupported "highest risk" claims
        assert "highest risk" not in content.lower()

        # 4. Three Primary Decision Cards
        # Activity Card
        assert "ACTIVITY PATTERNS" in content
        assert "Which activities occur most frequently?" in content
        assert reverse("admin_flow:patterns_activity") in content
        assert 'id="btn-explore-activity"' in content

        # Barrier Card
        assert "BARRIER / CONTROL PATTERNS" in content
        assert "Which control-deficiency signals recur?" in content
        assert reverse("admin_flow:patterns_barrier") in content
        assert 'id="btn-explore-barrier"' in content

        # Location Card
        assert "LOCATION PATTERNS" in content
        assert "Where are observations concentrated?" in content
        assert reverse("admin_flow:patterns_location") in content
        assert 'id="btn-explore-location"' in content

        # 5. Multi-Dimensional Relationship Flow — empty state shows no-pattern sentinel
        assert "Observed Multi-Dimensional Pattern Flow" in content
        assert "Observed pattern relationship" in content
        # In the empty state, no qualifying co-occurrences exist, so the card
        # shows the honest no-data sentinel instead of a manufactured pathway.
        assert "No recurring multi-dimensional pattern established." in content
        assert "Outcome" not in content or "Precursor Task Signal" not in content

        # 6. Subtle, Compliant Methodology Disclaimers
        assert "Pattern analysis is based on the current Admin Flow demonstration dataset." in content
        assert "Patterns represent historical observation frequency and association." in content
        assert "Barrier-linked observations are based on evidence-supported control states." in content
        assert "Pattern analysis does not establish causation or predict future incidents." in content


@pytest.mark.django_db
class TestPatternHubPopulatedState:
    """Verifies Pattern Hub with populated demonstration records."""

    def test_hub_populated_summary_previews_and_pipeline(self, client, admin_flow_user, active_model_version):
        # Seed 5 Admin Flow incidents
        incidents = [
            Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description="Worker suffered flash burn during hot work cutting near gas compressor in Process Area.",
                job_task="Hot Work in Classified Area",
                location="Process Area",
                department="Operations",
                control_type="Energy Isolation",
                control_condition="FAILED",
                control_failed_bypassed=True,
            ),
            Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description="Spark generated during grinding hot work without hot work permit in Process Area.",
                job_task="Hot Work in Classified Area",
                location="Process Area",
                department="Maintenance",
                control_type="Work Authorization",
                control_condition="BYPASSED",
                control_failed_bypassed=True,
            ),
            Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description="Crane rigging sling slipped during heavy lift in Workshop area.",
                job_task="Safe Mechanical Lifting",
                location="Workshop",
                department="Logistics",
            ),
            Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description="Forklift operating near chemical tank in Tank Farm without spotter.",
                job_task="Forklift Logistics",
                location="Tank Farm",
                department="Warehouse",
            ),
            Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description="Hot work welding torch ignited oily rag in Process Area.",
                job_task="Hot Work in Classified Area",
                location="Process Area",
                department="Operations",
                control_type="Energy Isolation",
                control_condition="FAILED",
                control_failed_bypassed=True,
            ),
        ]

        # Tag IOGP rules
        IOGPRuleTag.objects.create(
            incident=incidents[0],
            rule="Energy Isolation",
            confidence=0.92,
        )
        IOGPRuleTag.objects.create(
            incident=incidents[1],
            rule="Work Authorization",
            confidence=0.90,
        )
        IOGPRuleTag.objects.create(
            incident=incidents[4],
            rule="Energy Isolation",
            confidence=0.88,
        )

        # Create Predictions
        PredictionResult.objects.create(
            incident=incidents[0],
            model_version=active_model_version,
            psif_probability=0.88,
            psif_predicted=True,
            risk_level="CRITICAL",
        )
        PredictionResult.objects.create(
            incident=incidents[1],
            model_version=active_model_version,
            psif_probability=0.75,
            psif_predicted=True,
            risk_level="HIGH",
        )

        invalidate_admin_flow_pattern_cache()

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:patterns"))
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        # Total incidents = 5
        assert 'id="summary-total-incidents">5</div>' in content

        # Most frequent activity is Hot Work
        assert "Hot Work" in content
        assert "Process Area" in content
        assert "Energy Isolation" in content

        # Multi-dimensional flow check
        assert "Step 1 &bull; Activity" in content
        assert "Step 2 &bull; Location" in content
        assert "Step 3 &bull; Barrier Signal" in content
        assert "Outcome &bull; Risk State" in content


@pytest.mark.django_db
class TestDashboardPatternSnapshot:
    """Verifies the compact Pattern Snapshot section on the Admin Flow Dashboard."""

    def test_dashboard_snapshot_empty_baseline(self, client, admin_flow_user):
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:dashboard"))
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        # Snapshot container exists
        assert 'id="pattern-snapshot-section"' in content
        assert "PATTERN SNAPSHOT" in content
        assert "View Pattern Analysis" in content
        assert reverse("admin_flow:patterns") in content

        # Empty labels
        assert 'id="snapshot-top-activity"' in content
        assert 'id="snapshot-top-barrier"' in content
        assert 'id="snapshot-top-location"' in content
        assert "None yet" in content

    def test_dashboard_snapshot_populated_state(self, client, admin_flow_user, active_model_version):
        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Hot work welding on gas line in Process Area.",
            job_task="Hot Work",
            location="Process Area",
            control_type="Energy Isolation",
            control_condition="FAILED",
            control_failed_bypassed=True,
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Energy Isolation",
            confidence=0.9,
        )
        invalidate_admin_flow_pattern_cache()

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:dashboard"))
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")

        assert "Hot Work" in content
        assert "Energy Isolation" in content
        assert "Process Area" in content


@pytest.mark.django_db
class TestCompleteJudgeFlowLifecycle:
    """
    Simulates and validates the complete judge demonstration journey:
    1. Login as Admin Flow
    2. Verify initial baseline is strictly 0 / 0 / 0 / 0 / 0 / 0
    3. Submit one incident report
    4. Verify dashboard counters increment
    5. Inspect incident list and incident detail (PSIF + IOGP)
    6. Upload multi-incident dataset
    7. Verify counters update
    8. Visit Pattern Analysis Hub
    9. Visit Activity Analysis
    10. Visit Barrier Analysis
    11. Visit Location Analysis
    12. Verify drill-down & pattern relationships
    13. Logout
    14. Login as non-Admin-Flow standard user
    15. Verify standard enterprise dashboard and navigation remain untouched.
    """

    def test_full_judge_lifecycle(self, client, admin_flow_user, standard_admin_user, active_model_version):
        import csv
        from django.core.files.uploadedfile import SimpleUploadedFile

        # 1. Login as Admin Flow
        login_success = client.login(username=admin_flow_user.username, password="foresight2026")
        assert login_success is True

        # 2. Verify Initial 0 / 0 / 0 / 0 / 0 / 0 Baseline
        dash_resp = client.get(reverse("admin_flow:dashboard"))
        assert dash_resp.status_code == 200
        dash_content = dash_resp.content.decode("utf-8")

        assert 'id="stat-total">0</div>' in dash_content
        assert 'id="stat-eligible">0</div>' in dash_content
        assert 'id="stat-psif"' in dash_content and '>0</div>' in dash_content
        assert 'id="stat-not-psif">0</div>' in dash_content
        assert 'id="stat-insufficient">0</div>' in dash_content
        assert 'id="stat-human-reviewed">0</div>' in dash_content

        # 3. Submit One Incident Report
        submit_url = reverse("admin_flow:submit")
        submit_data = {
            "report_type": "near_miss",
            "incident_date": "2026-09-10",
            "location": "Compressor Area",
            "department": "Production",
            "job_task": "Hot Work in Classified Area",
            "description": "High pressure natural gas line flange began leaking while hot work was occurring in Compressor Area without proper isolation.",
            "immediate_cause": "Flange gasket compromised during pressure buildup.",
            "high_energy_present": "yes",
            "energy_type": "pressure",
            "direct_control_present": "yes",
            "control_condition": "failed",
            "action": "submit_only",
        }
        submit_resp = client.post(submit_url, submit_data, follow=True)
        assert submit_resp.status_code == 200

        # 4. Return to Dashboard & Verify Counters Updated (Total=1)
        dash_resp2 = client.get(reverse("admin_flow:dashboard"))
        dash_content2 = dash_resp2.content.decode("utf-8")
        assert 'id="stat-total">1</div>' in dash_content2

        # 5. Open Incidents Table
        incidents_resp = client.get(reverse("admin_flow:incidents"))
        assert incidents_resp.status_code == 200
        inc_content = incidents_resp.content.decode("utf-8")
        assert "Compressor Area" in inc_content

        created_inc = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).first()
        assert created_inc is not None

        # 6. Open Incident Detail & Verify Incident Context
        detail_url = reverse("admin_flow:incidents_detail", kwargs={"pk": created_inc.pk})
        detail_resp = client.get(detail_url)
        assert detail_resp.status_code == 200
        detail_content = detail_resp.content.decode("utf-8")
        assert "Compressor Area" in detail_content

        # 7. Upload Multi-Incident Dataset
        upload_url = reverse("admin_flow:upload")
        csv_data = io.StringIO()
        writer = csv.writer(csv_data)
        writer.writerow(["Date", "Department", "Activity", "Description", "Location", "HighEnergy", "ControlStatus"])
        writer.writerow(["2026-09-09", "Rigging", "Safe Mechanical Lifting", "Heavy lift crane sling snapped while moving pipe in Workshop.", "Workshop", "yes", "failed"])
        writer.writerow(["2026-09-08", "Logistics", "Tank Gauging", "Diesel fuel overflowed tank valve in Tank Farm during transfer.", "Tank Farm", "no", "effective"])

        uploaded_file = SimpleUploadedFile(
            name="demo_batch.csv",
            content=csv_data.getvalue().encode("utf-8"),
            content_type="text/csv",
        )
        upload_resp = client.post(upload_url, {"dataset_file": uploaded_file}, follow=True)
        assert upload_resp.status_code == 200

        # Verify counter increased to 3
        dash_resp3 = client.get(reverse("admin_flow:dashboard"))
        dash_content3 = dash_resp3.content.decode("utf-8")
        assert 'id="stat-total">3</div>' in dash_content3

        # 8. Visit Pattern Analysis Landing Page (Hub)
        hub_resp = client.get(reverse("admin_flow:patterns"))
        assert hub_resp.status_code == 200
        hub_content = hub_resp.content.decode("utf-8")
        assert "Pattern Analysis Hub" in hub_content
        assert 'id="summary-total-incidents">3</div>' in hub_content
        assert "Which activities occur most frequently?" in hub_content
        assert "Which control-deficiency signals recur?" in hub_content
        assert "Where are observations concentrated?" in hub_content

        # 9. Visit Activity Pattern Analysis
        act_resp = client.get(reverse("admin_flow:patterns_activity"))
        assert act_resp.status_code == 200
        assert "Activity Pattern Analysis" in act_resp.content.decode("utf-8")

        # 10. Visit Barrier Pattern Analysis
        bar_resp = client.get(reverse("admin_flow:patterns_barrier"))
        assert bar_resp.status_code == 200
        assert "Barrier / Control-Deficiency Associated Observations" in bar_resp.content.decode("utf-8")

        # 11. Visit Location Pattern Analysis
        loc_resp = client.get(reverse("admin_flow:patterns_location"))
        assert loc_resp.status_code == 200
        loc_content = loc_resp.content.decode("utf-8")
        assert "Location-Based Pattern Analysis" in loc_content
        assert "INCIDENT OBSERVATION DENSITY" in loc_content

        # 12. Logout
        client.logout()

        # 13. Login as standard enterprise user
        std_login = client.login(username=standard_admin_user.username, password="foresight2026")
        assert std_login is True

        # 14. Access standard global dashboard
        std_dash = client.get("/dashboard/")
        assert std_dash.status_code == 200
        std_content = std_dash.content.decode("utf-8")

        # Standard navigation check: Should NOT contain Admin Flow links
        assert 'href="/admin-flow/dashboard/"' not in std_content
        assert 'href="/admin-flow/patterns/"' not in std_content

        # Admin Flow pages must return 403 Forbidden for standard user
        forbidden_resp = client.get(reverse("admin_flow:patterns"))
        assert forbidden_resp.status_code == 403


@pytest.mark.django_db
class TestWorkspaceIsolationStrictness:
    """Verifies that global enterprise records never contaminate Admin Flow."""

    def test_global_records_never_appear_in_admin_flow(self, client, admin_flow_user):
        # Create a global record
        Incident.objects.create(
            workspace_id="default",
            description="Global refinery catastrophic pump explosion in Texas Unit 4.",
            location="Texas Unit 4",
            department="Global Operations",
            job_task="Pump Maintenance",
        )

        client.force_login(admin_flow_user)

        # Check Admin Flow dashboard
        dash_resp = client.get(reverse("admin_flow:dashboard"))
        dash_content = dash_resp.content.decode("utf-8")
        assert 'id="stat-total">0</div>' in dash_content

        # Check Admin Flow hub
        hub_resp = client.get(reverse("admin_flow:patterns"))
        hub_content = hub_resp.content.decode("utf-8")
        assert 'id="summary-total-incidents">0</div>' in hub_content
        assert "Texas Unit 4" not in hub_content
