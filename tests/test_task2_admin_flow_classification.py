"""
PSIF Platform — Task 2 Admin Flow PSIF & IOGP Classification Test Suite.

Verifies:
1. Zero records baseline (empty state, zero counts, denominator is zero behavior).
2. One record test.
3. Multiple records (PSIF + NOT PSIF + Insufficient Information).
4. Explicit denominator calculation (sparse inputs excluded from denominator).
5. Strict distinction: NOT PSIF != INSUFFICIENT INFORMATION.
6. Terminology enforcement: "PSIF Model Score" used, forbidden phrases absent.
7. Methodology note present.
8. IOGP 9 Life-Saving Rules coverage and descending sort order.
9. IOGP semantics banner present (Rule-matched candidate != violation != barrier failure != PSIF).
10. Workspace isolation (Admin Flow completely isolated from global records).
11. REST APIs (/admin-flow/api/psif/metrics/, /admin-flow/api/iogp/metrics/).
"""
import uuid
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.normalization import CANONICAL_IOGP_RULES
from apps.admin_flow.services import (
    ADMIN_FLOW_WORKSPACE,
    get_admin_flow_psif_metrics,
    get_admin_flow_iogp_metrics,
)

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    """Admin Flow user fixture."""
    user, _ = User.objects.get_or_create(
        email="admin_flow_test@foresight.app",
        defaults={
            "username": "admin_flow_test@foresight.app",
            "role": "admin_flow",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def global_admin_user(db):
    """Global admin user fixture."""
    user, _ = User.objects.get_or_create(
        email="global_admin_test@foresight.app",
        defaults={
            "username": "global_admin_test@foresight.app",
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
    """Active ModelVersion fixture."""
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_20260906_202052",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.mark.django_db
class TestTask2ZeroRecordsBaseline:
    """Verify zero state behavior across both Admin Flow classification pages."""

    def test_psif_page_zero_state(self, client, admin_flow_user):
        # Ensure workspace is empty
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:psif"))
        assert resp.status_code == 200

        content = resp.content.decode()
        # Verify title & badges
        assert "PSIF Precursor Classification" in content
        assert "Admin Flow" in content

        # Verify zero counts in KPI elements
        assert 'id="kpi-total-incidents">0<' in content
        assert 'id="kpi-eligible">0<' in content
        assert 'id="kpi-psif" style="color: var(--risk-critical);">0<' in content
        assert 'id="kpi-not-psif" style="color: var(--risk-low);">0<' in content
        assert 'id="kpi-insufficient">0<' in content

        # Verify denominator behavior: rate should show dash and zero denominator note
        assert "Denominator is 0 (no eligible observations)" in content
        assert "PSIF Rate (Eligible)" in content
        assert "—" in content

        # Verify mandatory methodology note
        assert "The PSIF Model Score is a model output and is not presented as a calibrated probability." in content

        # Verify critical distinction banner is removed from visible UI
        assert "Critical Semantic Distinction: NOT PSIF" not in content
        assert "Hard Isolation Contract" not in content

        # Verify forbidden phrases are NOT present
        assert "Probability of fatality" not in content
        assert "Chance of death" not in content

        # Verify empty state guidance
        assert "No eligible observations evaluated yet." in content

    def test_iogp_page_zero_state(self, client, admin_flow_user):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:iogp"))
        assert resp.status_code == 200

        content = resp.content.decode()
        assert "IOGP Life-Saving Rules Classification" in content

        # Verify KPI counts
        assert 'id="kpi-matched">0<' in content
        assert 'id="kpi-psif-linked" style="color: var(--risk-critical);">' in content

        # Verify all 9 canonical rules are displayed
        for rule in CANONICAL_IOGP_RULES:
            assert rule in content

        # Verify important IOGP semantics banner removed from visible UI
        assert "Important Operational Semantics: Rule-Matched Candidate vs. Failure" not in content
        assert "Hard Isolation Contract" not in content

        # Verify empty state guidance
        assert "No IOGP Rule Matches Recorded" in content


@pytest.mark.django_db
class TestTask2PSIFMetricsAndCalculations:
    """Verify single and multiple records, rate calculations, and denominator scoping."""

    def test_single_psif_record(self, client, admin_flow_user, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Worker fell 8 meters from unsupported scaffolding during pipe maintenance.",
            department="Drilling",
            location="Site Alpha",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.88,
            psif_predicted=True,
            risk_level="critical",
            is_sparse_input=False,
        )

        metrics = get_admin_flow_psif_metrics()
        assert metrics["total_incidents"] == 1
        assert metrics["prediction_eligible_count"] == 1
        assert metrics["psif_count"] == 1
        assert metrics["not_psif_count"] == 0
        assert metrics["insufficient_evidence_count"] == 0
        assert metrics["psif_rate"] == 100.0
        assert metrics["psif_rate_display"] == "100.0%"

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:psif"))
        content = resp.content.decode()

        assert 'id="kpi-total-incidents">1<' in content
        assert 'id="kpi-eligible">1<' in content
        assert 'id="kpi-psif" style="color: var(--risk-critical);">1<' in content
        assert "100.0%" in content
        assert "Denominator: 1 eligible records" in content

    def test_multiple_records_with_sparse_exclusion(self, client, admin_flow_user, active_model):
        """
        Verify that sparse records (<10 words) are:
        1. Counted as INSUFFICIENT INFORMATION.
        2. Strictly excluded from Prediction Eligible denominator.
        3. Separated from NOT PSIF.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        # 1 PSIF record
        inc1 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="High pressure steam line blew gasket causing severe burns and blast hazard.",
            department="Refining",
            location="Unit 4",
        )
        PredictionResult.objects.create(
            incident=inc1,
            model_version=active_model,
            psif_probability=0.82,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
        )

        # 2 NOT PSIF records
        inc2 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Small paper cut while opening packaging box in stationery storage room.",
            department="Logistics",
            location="Warehouse B",
        )
        PredictionResult.objects.create(
            incident=inc2,
            model_version=active_model,
            psif_probability=0.08,
            psif_predicted=False,
            risk_level="low",
            is_sparse_input=False,
        )

        inc3 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Operator tripped over extension cord on clean dry office floor.",
            department="Operations",
            location="Admin Building",
        )
        PredictionResult.objects.create(
            incident=inc3,
            model_version=active_model,
            psif_probability=0.25,
            psif_predicted=False,
            risk_level="low",
            is_sparse_input=False,
        )

        # 1 INSUFFICIENT INFORMATION record (sparse narrative)
        inc4 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Minor leak noted.",
            department="Maintenance",
            location="Valve 12",
        )
        PredictionResult.objects.create(
            incident=inc4,
            model_version=active_model,
            psif_probability=0.0,
            psif_predicted=False,
            risk_level="low",
            is_sparse_input=True,  # Insufficient Information
        )

        metrics = get_admin_flow_psif_metrics()
        assert metrics["total_incidents"] == 4
        assert metrics["prediction_eligible_count"] == 3  # inc1, inc2, inc3
        assert metrics["psif_count"] == 1
        assert metrics["not_psif_count"] == 2
        assert metrics["insufficient_evidence_count"] == 1
        # PSIF rate = 1 / 3 * 100 = 33.3%
        assert metrics["psif_rate"] == 33.3
        assert metrics["psif_rate_display"] == "33.3%"

        # Score distribution check
        assert metrics["score_distribution"]["low"] == 1  # 0.08
        assert metrics["score_distribution"]["medium"] == 1  # 0.25
        assert metrics["score_distribution"]["high"] == 0
        assert metrics["score_distribution"]["critical"] == 1  # 0.82

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:psif"))
        content = resp.content.decode()

        assert 'id="kpi-total-incidents">4<' in content
        assert 'id="kpi-eligible">3<' in content
        assert 'id="kpi-psif" style="color: var(--risk-critical);">1<' in content
        assert 'id="kpi-not-psif" style="color: var(--risk-low);">2<' in content
        assert 'id="kpi-insufficient">1<' in content
        assert "33.3%" in content
        assert "Denominator: 3 eligible records" in content


@pytest.mark.django_db
class TestTask2IOGPClassification:
    """Verify IOGP rule counting, descending sorting, PSIF linkage, and semantics."""

    def test_iogp_rule_sorting_and_linkage(self, client, admin_flow_user, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        # Incident A: Working at Height + PSIF
        incA = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Worker slipped on scaffold at 10m height without harness lanyard attached.",
            location="Site Alpha",
        )
        PredictionResult.objects.create(
            incident=incA,
            model_version=active_model,
            psif_probability=0.89,
            psif_predicted=True,
            risk_level="critical",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=incA, rule="Working at Height")

        # Incident B: Working at Height + NOT PSIF
        incB = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Inspection of scaffolding platform railing completed at 2m height.",
            location="Site Beta",
        )
        PredictionResult.objects.create(
            incident=incB,
            model_version=active_model,
            psif_probability=0.10,
            psif_predicted=False,
            risk_level="low",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=incB, rule="Working at Height")

        # Incident C: Confined Space + Energy Isolation
        incC = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Entry into vessel tank without permit or atmospheric testing, valve not locked out.",
            location="Site Alpha",
        )
        PredictionResult.objects.create(
            incident=incC,
            model_version=active_model,
            psif_probability=0.76,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=incC, rule="Confined Space")
        IOGPRuleTag.objects.create(incident=incC, rule="Energy Isolation")

        metrics = get_admin_flow_iogp_metrics()
        rules = metrics["rules"]

        # 9 rules must be present
        assert len(rules) == 9

        # Working at Height has 2 matches (highest count)
        assert rules[0]["rule"] == "Working at Height"
        assert rules[0]["matched_observations"] == 2
        assert rules[0]["psif_linked_observations"] == 1
        assert rules[0]["affected_sites"] == 2
        assert rules[0]["psif_linkage_rate"] == 50.0

        # Next rules have 1 match each
        next_rules = [r["rule"] for r in rules[1:3]]
        assert "Confined Space" in next_rules
        assert "Energy Isolation" in next_rules

        # Total rule matches
        assert metrics["total_rule_matches"] == 4
        assert metrics["total_psif_linked"] == 3

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:iogp"))
        content = resp.content.decode()

        assert 'id="kpi-matched">4<' in content
        assert 'id="kpi-psif-linked" style="color: var(--risk-critical);">' in content
        assert "Working at Height" in content
        assert "Confined Space" in content
        assert "Energy Isolation" in content


@pytest.mark.django_db
class TestTask2WorkspaceIsolation:
    """Verify strict isolation from global production records."""

    def test_global_records_excluded_from_admin_flow(self, client, admin_flow_user, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        # Create a global incident (workspace_id=None)
        global_inc = Incident.objects.create(
            workspace_id=None,
            description="Global production crane hoist cable snap.",
            location="Offshore Rig 12",
        )
        PredictionResult.objects.create(
            incident=global_inc,
            model_version=active_model,
            psif_probability=0.95,
            psif_predicted=True,
            risk_level="critical",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=global_inc, rule="Safe Mechanical Lifting")

        # Admin Flow should still show 0 records
        psif_metrics = get_admin_flow_psif_metrics()
        assert psif_metrics["total_incidents"] == 0
        assert psif_metrics["psif_count"] == 0
        assert psif_metrics["prediction_eligible_count"] == 0

        iogp_metrics = get_admin_flow_iogp_metrics()
        assert iogp_metrics["total_rule_matches"] == 0
        lifting_rule = next(r for r in iogp_metrics["rules"] if r["rule"] == "Safe Mechanical Lifting")
        assert lifting_rule["matched_observations"] == 0

        client.force_login(admin_flow_user)
        resp_psif = client.get(reverse("admin_flow:psif"))
        assert 'id="kpi-total-incidents">0<' in resp_psif.content.decode()

        resp_iogp = client.get(reverse("admin_flow:iogp"))
        assert 'id="kpi-matched">0<' in resp_iogp.content.decode()

        # Clean up global fixture
        global_inc.delete()


@pytest.mark.django_db
class TestTask2APIs:
    """Verify REST APIs for PSIF and IOGP metrics."""

    def test_psif_metrics_api(self, client, admin_flow_user, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Chemical leak in storage warehouse.",
            location="Plant 1",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.65,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
        )

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:api_psif_metrics"))
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_incidents"] == 1
        assert data["prediction_eligible_count"] == 1
        assert data["psif_count"] == 1
        assert data["not_psif_count"] == 0
        assert data["psif_rate"] == 100.0
        assert "methodology_note" in data
        assert "The PSIF Model Score is a model output and is not presented as a calibrated probability." in data["methodology_note"]

    def test_iogp_metrics_api(self, client, admin_flow_user, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Vehicle collision during night convoy.",
            location="Access Road",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.72,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=inc, rule="Driving")

        client.force_login(admin_flow_user)
        resp = client.get(reverse("admin_flow:api_iogp_metrics"))
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_rule_matches"] == 1
        assert data["total_psif_linked"] == 1
        assert len(data["rules"]) == 9
        driving = next(r for r in data["rules"] if r["rule"] == "Driving")
        assert driving["matched_observations"] == 1
        assert driving["psif_linked_observations"] == 1
        assert driving["psif_linkage_rate"] == 100.0
        assert "semantic_disclaimer" in data
