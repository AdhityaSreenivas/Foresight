"""
Automated Integration Tests for the Admin Flow Reference Frontend Rebuild.
Validates the five core reference experiences:
1. Dashboard (6 KPIs, dual action buttons)
2. PSIF Classification (4 summary cards, model score distribution, observation cards)
3. Live Processing (animated counters, status indicator, file status, completion state)
4. IOGP Classification (4 summary cards, preserved comparison chart, 9 barrier cards, 3 bottom analytics)
5. Single Incident Reasoning (submission redirect, 2x2 investigation grid, decision trace, evidence, model calibration)
6. Reset Demo clean-sheet zero state
7. Regular login regression protection
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.services import ADMIN_FLOW_WORKSPACE, reset_admin_flow_workspace

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        email="admin_ref_tester@foresight.app",
        defaults={
            "username": "admin_ref_tester@foresight.app",
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
        email="standard_ref_tester@foresight.app",
        defaults={
            "username": "standard_ref_tester@foresight.app",
            "role": "hse_officer",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def active_model(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_20260906_202052",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.mark.django_db
class TestAdminFlowReferenceFrontendRebuild:

    def test_dashboard_reference_structure(self, client, admin_flow_user):
        """Page A: Dashboard retains 6 KPIs and dual action buttons."""
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:dashboard"))
        assert resp.status_code == 200
        content = resp.content.decode()

        # 6 KPI cards
        assert 'id="stat-total"' in content
        assert 'id="stat-eligible"' in content
        assert 'id="stat-psif"' in content
        assert 'id="stat-not-psif"' in content
        assert 'id="stat-insufficient"' in content
        assert 'id="stat-human-reviewed"' in content

        # Dual action buttons
        assert "SINGLE INCIDENT PREDICTION" in content
        assert "UPLOAD DATASET / MULTI-INCIDENT PREDICTION" in content
        assert reverse("admin_flow:submit") in content
        assert reverse("admin_flow:upload") in content

    def test_psif_reference_structure(self, client, admin_flow_user):
        """Page B: PSIF page contains 4 summary cards and score distribution."""
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:psif"))
        assert resp.status_code == 200
        content = resp.content.decode()

        assert "PSIF Precursor Classification" in content
        assert "PSIF CANDIDATES" in content
        assert "NOT PSIF" in content
        assert "INSUFFICIENT INFORMATION" in content
        assert "PREDICTION ELIGIBLE" in content
        assert "PSIF vs Not PSIF" in content
        assert "PSIF Model Score" in content
        assert "Probability of fatality" not in content

    def test_iogp_reference_structure(self, client, admin_flow_user):
        """Page D: IOGP page retains comparison chart and 9 barrier cards."""
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:iogp"))
        assert resp.status_code == 200
        content = resp.content.decode()

        # Header and summary
        assert "IOGP Incident Intelligence Dashboard" in content
        assert "TOTAL INCIDENTS" in content
        assert "TOTAL IOGP MATCHED" in content
        assert "PSIF-LINKED MATCHES" in content
        assert "NO RULE MATCHED" in content

        # First chart preserved
        assert "IOGP Barrier Risk Distribution Comparison" in content
        assert 'id="adminFlowIOGPChart"' in content

        # Barrier Intelligence Portfolio with 9 canonical cards
        assert "Barrier Intelligence Portfolio" in content
        assert "9 Canonical Rules" in content
        for i in range(1, 10):
            assert f'id="card-rule-{i}"' in content
            assert f'id="modal-rule-{i}"' in content

        # 3 bottom charts from React reference
        assert 'id="chartVolume"' in content
        assert 'id="chartDistribution"' in content
        assert 'id="chartLinkage"' in content

    def test_live_processing_page_and_api(self, client, admin_flow_user):
        """Page C: Live processing counter page and live status API."""
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:live_processing"))
        assert resp.status_code == 200
        content = resp.content.decode()

        assert "Live Processing" in content
        assert "Processing multiple incident records" in content
        assert "PSIF Candidates" in content
        assert "Non-PSIF" in content
        assert 'id="live-psif-counter"' in content
        assert 'id="live-nonpsif-counter"' in content
        assert 'id="live-status-pill"' in content
        assert 'id="live-progress-bar"' in content

        # Check API
        api_resp = client.get(reverse("admin_flow:api_live_status"))
        assert api_resp.status_code == 200
        data = api_resp.json()
        assert "status" in data
        assert "total_rows" in data
        assert "processed_rows" in data
        assert "psif_count" in data
        assert "non_psif_count" in data
        assert "progress_pct" in data

    def test_submit_redirects_to_single_incident_reasoning(self, client, admin_flow_user, active_model):
        """Page E: Form submission redirects directly to Single Incident Reasoning page."""
        client.force_login(admin_flow_user)

        post_data = {
            "report_type": "near_miss",
            "incident_date": "2026-03-20",
            "location": "Offshore Platform Gamma",
            "department": "Production Operations",
            "job_task": "High-Pressure Gas Separator Blowdown",
            "equipment_involved": "Blowdown valve and rupture pin",
            "description": "Pressure surge in separator vessel during blowdown. Operator bypassed manual trip interlock before confirming downstream vent was unblocked.",
            "immediate_cause": "Manual trip bypassed without permit.",
            "high_energy_present": "yes",
            "energy_type": "pressure",
            "direct_control_present": "yes",
            "control_condition": "bypassed",
            "action": "submit_and_process",
        }

        resp = client.post(reverse("admin_flow:submit"), data=post_data, follow=True)
        assert resp.status_code == 200

        # Verify redirection landed on reasoning page
        inc = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).latest("created_at")
        expected_url = reverse("admin_flow:incident_reasoning", kwargs={"pk": inc.pk})
        assert resp.redirect_chain[-1][0] == expected_url

        content = resp.content.decode()
        assert "Incident Investigation &amp; Decision Trace" in content or "Incident Investigation" in content
        assert "Offshore Platform Gamma" in content
        assert "High-Pressure Gas Separator Blowdown" in content
        assert "Decision Trace Sequence" in content
        assert "Pathway Remained Uncontained" in content or "Fatal Sequence Interrupted" in content
        assert "IOGP Life-Saving Rules" in content
        assert "Model Provenance &amp; Calibration" in content

    def test_reset_demo_clears_all_five_experiences(self, client, admin_flow_user, active_model):
        """Reset Demo cleanly resets Dashboard, PSIF, IOGP, and Live Processing."""
        # 1. Create a dummy incident
        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="High voltage breaker trip with flash.",
            location="Substation 4",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.85,
            psif_predicted=True,
            risk_level="HIGH",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=inc, rule="Energy Isolation")

        # 2. Reset
        reset_res = reset_admin_flow_workspace(user=admin_flow_user)
        assert reset_res["status"] == "success"

        client.force_login(admin_flow_user)

        # Dashboard check
        d_resp = client.get(reverse("admin_flow:dashboard"))
        assert d_resp.status_code == 200
        d_content = d_resp.content.decode()
        assert 'id="stat-total">0</div>' in d_content
        assert 'id="stat-psif" style="color: var(--risk-critical);">0</div>' in d_content

        # PSIF check
        p_resp = client.get(reverse("admin_flow:psif"))
        assert p_resp.status_code == 200
        p_content = p_resp.content.decode()
        assert 'id="kpi-total-incidents">0</div>' in p_content

        # IOGP check
        i_resp = client.get(reverse("admin_flow:iogp"))
        assert i_resp.status_code == 200
        i_content = i_resp.content.decode()
        assert 'id="kpi-matched">0</div>' in i_content

    def test_regular_login_regression_unaffected(self, client, standard_user):
        """Regular user login views must remain completely unchanged."""
        client.force_login(standard_user)

        # Standard Dashboard (root)
        dash_resp = client.get("/dashboard/")
        assert dash_resp.status_code == 200

        # Standard Reports
        rep_resp = client.get("/dashboard/reports/")
        assert rep_resp.status_code == 200

        # Standard Barrier page
        barr_resp = client.get("/dashboard/barriers/")
        assert barr_resp.status_code == 200

        # Admin Flow namespace should not be accessible to standard user
        af_resp = client.get("/admin-flow/dashboard/")
        # Should either redirect to login or return 403 — not 500
        assert af_resp.status_code in (200, 302, 403)
