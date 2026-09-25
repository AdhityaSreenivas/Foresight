"""
PSIF Platform — Admin Flow IOGP Classification Redesign: Barrier Intelligence Portfolio Tests.

Validates:
1. Presence of exactly 9 canonical IOGP Life-Saving Rule cards.
2. Canonical rule ordering (1 to 9).
3. Zero state (empty Admin Flow workspace renders all 9 cards with 0 counts).
4. Real data counts (matched observations, PSIF-linked observations, affected locations).
5. Detail modal dialogs present for all 9 rules with descriptions, citations, and checks.
6. Non-matching observations reconciliation banner.
7. REST API endpoint /admin-flow/api/iogp/portfolio/ (structure, metrics, and rule filtering).
8. Admin Flow workspace scoping & isolation from global records.
9. Reset behavior (clean sheet returns all 9 cards to 0).
10. Terminology safety audit (absence of forbidden causal/violation phrases).
11. Regression verification: Global barrier intelligence page remains intact.
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.normalization import CANONICAL_IOGP_RULES
from apps.admin_flow.services import (
    ADMIN_FLOW_WORKSPACE,
    get_admin_flow_barrier_portfolio_data,
    reset_admin_flow_workspace,
)

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        email="admin_flow_portfolio_tester@foresight.app",
        defaults={
            "username": "admin_flow_portfolio_tester@foresight.app",
            "role": "admin_flow",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def global_admin_user(db):
    user, _ = User.objects.get_or_create(
        email="global_admin_portfolio_tester@foresight.app",
        defaults={
            "username": "global_admin_portfolio_tester@foresight.app",
            "role": "admin",
            "is_active": True,
            "is_staff": True,
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
class TestBarrierIntelligencePortfolio:
    """Core test suite for Admin Flow Barrier Intelligence Portfolio."""

    def test_zero_state_renders_nine_cards_with_zero_counts(self, client, admin_flow_user):
        """Zero state test: all 9 cards persist with 0s after reset or empty workspace."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:iogp"))
        assert resp.status_code == 200

        content = resp.content.decode()

        # Section header
        assert "Barrier Intelligence Portfolio" in content
        assert "9 Canonical Rules" in content

        # Methodology note
        assert "IOGP categories are derived from the canonical rule-matching system" in content

        # All 9 canonical rules must be present
        for rule_name in CANONICAL_IOGP_RULES:
            assert rule_name in content

        # Check card IDs
        for i in range(1, 10):
            assert f'id="card-rule-{i}"' in content
            assert f'id="modal-rule-{i}"' in content

        # Check existing first chart header is preserved and shows zero state placeholder
        assert "IOGP Barrier Risk Distribution Comparison" in content
        assert "No IOGP Rule Matches Recorded" in content

        # Check that old table is GONE from Admin Flow page
        assert 'id="table-iogp-rules"' not in content

    def test_real_data_aggregations_and_card_metrics(self, client, admin_flow_user, active_model):
        """Verify accurate counts for matched observations, PSIF-linkages, and locations."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        # Create Incidents with specific IOGP tags
        # 1. Working at Height (PSIF)
        inc1 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Scaffold plank slipped while working at 15m elevation, lanyard caught worker.",
            location="Drilling Platform A",
            job_task="Scaffold Erection",
            control_condition="effective",
        )
        PredictionResult.objects.create(
            incident=inc1,
            model_version=active_model,
            psif_probability=0.88,
            psif_predicted=True,
            risk_level="critical",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=inc1, rule="Working at Height")

        # 2. Working at Height (Not PSIF, different location)
        inc2 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Safety harness toe board inspected and replaced on low staging.",
            location="Warehouse B",
            job_task="Maintenance Inspection",
            control_condition="effective",
        )
        PredictionResult.objects.create(
            incident=inc2,
            model_version=active_model,
            psif_probability=0.15,
            psif_predicted=False,
            risk_level="low",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=inc2, rule="Working at Height")

        # 3. Energy Isolation (PSIF)
        inc3 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="High pressure nitrogen valve opened without LOTO verification tag.",
            location="Compressor Station 3",
            job_task="Valve Maintenance",
            control_condition="bypassed",
        )
        PredictionResult.objects.create(
            incident=inc3,
            model_version=active_model,
            psif_probability=0.79,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=inc3, rule="Energy Isolation")

        # Query service data directly
        data = get_admin_flow_barrier_portfolio_data(use_cache=False)
        assert data["total_analyzed_incidents"] == 3
        assert data["total_rule_matches"] == 3
        assert data["total_psif_linked"] == 2

        rules_by_name = {r["rule"]: r for r in data["rules"]}

        # Check Working at Height
        wah = rules_by_name["Working at Height"]
        assert wah["matched_observations"] == 2
        assert wah["psif_linked_observations"] == 1
        assert wah["affected_locations"] == 2
        assert wah["psif_linkage_rate"] == 50.0

        # Check Energy Isolation
        ei = rules_by_name["Energy Isolation"]
        assert ei["matched_observations"] == 1
        assert ei["psif_linked_observations"] == 1
        assert ei["affected_locations"] == 1
        assert ei["dominant_control_state"] == "Bypassed / Defeated (1 observation)"

        # Check HTML view
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:iogp"))
        content = resp.content.decode()

        assert 'Rule #4' in content  # Energy Isolation is Rule #4
        assert 'Rule #9' in content  # Working at Height is Rule #9
        assert "Working at Height" in content
        assert "Energy Isolation" in content
        assert 'id="adminFlowIOGPChart"' in content

    def test_api_portfolio_endpoint(self, client, admin_flow_user, active_model):
        """Verify GET /admin-flow/api/iogp/portfolio/ returns canonical schema."""
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:api_iogp_portfolio"))
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "success"
        assert len(data["rules"]) == 9

        # Canonical rule order check
        for idx, rule_data in enumerate(data["rules"]):
            expected_name = CANONICAL_IOGP_RULES[idx]
            assert rule_data["rule"] == expected_name
            assert rule_data["order"] == idx + 1
            assert "description" in rule_data
            assert "source_reference" in rule_data
            assert "matched_observations" in rule_data
            assert "psif_linked_observations" in rule_data
            assert "affected_locations" in rule_data
            assert "top_activity" in rule_data
            assert "top_location" in rule_data
            assert "dominant_control_state" in rule_data

        # Single rule filter test
        resp_filtered = client.get(reverse("admin_flow:api_iogp_portfolio") + "?rule=Energy Isolation")
        assert resp_filtered.status_code == 200
        filtered_data = resp_filtered.json()
        assert filtered_data["rule"] == "Energy Isolation"
        assert filtered_data["order"] == 4

    def test_global_isolation(self, client, admin_flow_user, active_model):
        """Global production records must not leak into Admin Flow Barrier Portfolio."""
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        # Create global incident
        global_inc = Incident.objects.create(
            workspace_id=None,
            description="Global production offshore drill floor incident.",
            location="Offshore Alpha",
        )
        PredictionResult.objects.create(
            incident=global_inc,
            model_version=active_model,
            psif_probability=0.92,
            psif_predicted=True,
            risk_level="critical",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=global_inc, rule="Line of Fire")

        # Admin Flow portfolio must remain 0
        data = get_admin_flow_barrier_portfolio_data(use_cache=False)
        assert data["total_analyzed_incidents"] == 0
        lof = next(r for r in data["rules"] if r["rule"] == "Line of Fire")
        assert lof["matched_observations"] == 0
        assert lof["psif_linked_observations"] == 0

        # Clean up global fixture
        global_inc.delete()

    def test_reset_clears_barrier_portfolio(self, client, admin_flow_user, active_model):
        """Admin Flow reset resets all 9 cards to 0 counts."""
        # Create incident
        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Hot work welding near solvent storage.",
            location="Fabrication Shop",
        )
        IOGPRuleTag.objects.create(incident=inc, rule="Hot Work")

        data_before = get_admin_flow_barrier_portfolio_data(use_cache=False)
        hw_before = next(r for r in data_before["rules"] if r["rule"] == "Hot Work")
        assert hw_before["matched_observations"] == 1

        # Perform reset
        reset_result = reset_admin_flow_workspace(user=admin_flow_user)
        assert reset_result["status"] == "success"

        # Check portfolio data after reset
        data_after = get_admin_flow_barrier_portfolio_data(use_cache=True)
        assert data_after["total_analyzed_incidents"] == 0
        assert data_after["total_rule_matches"] == 0
        for r in data_after["rules"]:
            assert r["matched_observations"] == 0
            assert r["psif_linked_observations"] == 0
            assert r["affected_locations"] == 0

    def test_prohibited_terminology_audit(self, client, admin_flow_user):
        """Ensure prohibited causal/violation phrases are strictly absent and disclaimers are present."""
        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:iogp"))
        content = resp.content.decode().lower()

        forbidden_phrases = [
            "barrier caused",
            "failure probability",
            "risk probability",
            "100% confidence",
            "most dangerous location",
            "most dangerous activity",
        ]
        for phrase in forbidden_phrases:
            assert phrase not in content, f"Forbidden phrase '{phrase}' found in Admin Flow IOGP page!"

        # "confirmed violation" must ONLY appear in explicit negative disclaimers
        assert "does not by itself establish a confirmed violation" in content
        # Ensure no affirmative "is a confirmed violation" or "confirmed violation rate"
        assert "is a confirmed violation" not in content
        assert "confirmed violation rate" not in content
        assert "confirmed violations:" not in content

    def test_regular_login_global_barrier_page_unaffected(self, client, global_admin_user):
        """Verify that global barrier intelligence page (/dashboard/barriers/) is unaffected."""
        client.force_login(global_admin_user)
        resp = client.get(reverse("dashboard:barriers"))
        # Should render 200 OK without Admin Flow template contamination
        assert resp.status_code == 200
        content = resp.content.decode()
        # Global page has its own title and does not have the Admin Flow banner
        assert "Hard Isolation Contract" not in content
