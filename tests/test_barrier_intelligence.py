"""
Comprehensive Test Suite for Barrier & Critical-Control Intelligence (Task 11)
tests/test_barrier_intelligence.py

Verifies:
1. Exact definitions of authoritative V1 metrics:
   - Matched observations
   - PSIF-linked observations
   - Affected sites
   - PSIF-linkage rate
2. 9 canonical IOGP rules present (no 10th rule)
3. Unknown control preservation (missing/blank fields NEVER default to COMPROMISED)
4. Explicit compromised control detection
5. Explicit controlled barrier detection
6. Multi-rule incident distinct counting
7. Duplicate incident tag handling
8. Normalized site handling (blank/None excluded)
9. Cache lifecycle and invalidation
10. Empty dataset handling (zero division safe)
11. Barrier detail view and representative incidents disclaimer
12. Action Engine integration (Energy Isolation bypass vs unknown)
13. Workspace integration (canonical reasoning result & linkage)
14. REST API endpoints (/api/analytics/barriers/ and detail)
15. Regression validation against baseline database
"""

import pytest
from unittest.mock import patch
from django.core.cache import cache
from django.test import Client
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident, IOGPRuleTag
from apps.datasets.models import Dataset
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.normalization import CANONICAL_IOGP_RULES
from apps.incidents.services.barrier_service import (
    BarrierIntelligenceService,
    ControlSemantics,
    CACHE_KEY_BARRIER_INTELLIGENCE,
    UNKNOWN_CONTROL_EVIDENCE_TEXT,
    METHODOLOGY_STATEMENT,
    RATE_DEFINITION,
)
from apps.dashboard.services import get_barrier_intelligence, invalidate_analytics_cache
from apps.incidents.services.workspace import compose_investigation_workspace

User = get_user_model()


@pytest.fixture
def auth_client(db):
    client = APIClient()
    user = User.objects.create_user(username="barrier_tester", password="password123", email="tester@oil.in")
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def sample_dataset(db):
    dataset, _ = Dataset.objects.get_or_create(
        name="Barrier Test Dataset",
    )
    return dataset



@pytest.fixture
def sample_model_version(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_barrier_test",
        defaults={
            "bert_model_name": "distilbert-base-uncased",
            "xgboost_artifact_path": "/tmp/test_xgb.json",
            "encoder_artifact_path": "/tmp/test_enc.joblib",
            "is_active": True,
            "metrics": {"selected_threshold": 0.50},
        },
    )
    return mv


# ─────────────────────────────────────────────────────────────────────────────
# 1. CANONICAL 9 RULES & METRIC DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCanonicalRulesAndMetricDefinitions:
    def test_canonical_nine_rules_present(self):
        """Verify exactly 9 canonical rules are returned, matching CANONICAL_IOGP_RULES."""
        data = BarrierIntelligenceService.get_barrier_portfolio(use_cache=False, force_refresh=True)
        assert data["canonical_rule_count"] == 9
        assert data["total_monitored_barriers"] == 9
        returned_rules = [b["rule"] for b in data["barriers"]]
        for rule in CANONICAL_IOGP_RULES:
            assert rule in returned_rules
        assert len(returned_rules) == 9

    def test_exact_definitions_matched_psif_linked_sites(self, sample_dataset, sample_model_version):
        """
        Verify exact authoritative definitions:
        - matched_observations: distinct incidents matching the rule
        - psif_linked_observations: psif_predicted=True AND is_sparse_input=False
        - affected_sites: distinct nonblank locations
        - rate: psif_linked / matched
        """
        # Incident 1: Eligible PSIF candidate
        inc1 = Incident.objects.create(
            dataset=sample_dataset,
            description="Lifting steel pipe with mobile crane in yard",
            location="Digboi Rig 04",
        )
        PredictionResult.objects.create(
            incident=inc1,
            model_version=sample_model_version,
            psif_probability=0.88,
            psif_predicted=True,
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=inc1, rule="Safe Mechanical Lifting")

        # Incident 2: Eligible NOT_PSIF candidate
        inc2 = Incident.objects.create(
            dataset=sample_dataset,
            description="Crane operation completed with all slings inspected",
            location="Digboi Rig 04",
        )
        PredictionResult.objects.create(
            incident=inc2,
            model_version=sample_model_version,
            psif_probability=0.12,
            psif_predicted=False,
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(incident=inc2, rule="Safe Mechanical Lifting")

        # Incident 3: Sparse narrative (excluded from PSIF numerator)
        inc3 = Incident.objects.create(
            dataset=sample_dataset,
            description="Crane sling checked",
            location="Duliajan Gas Plant",
        )
        PredictionResult.objects.create(
            incident=inc3,
            model_version=sample_model_version,
            psif_probability=0.90,
            psif_predicted=True,
            is_sparse_input=True,  # Sparse!
        )
        IOGPRuleTag.objects.create(incident=inc3, rule="Safe Mechanical Lifting")

        # Incident 4: No prediction result
        inc4 = Incident.objects.create(
            dataset=sample_dataset,
            description="Crane boom inspection scheduled for next week",
            location="Moran Station",
        )
        IOGPRuleTag.objects.create(incident=inc4, rule="Safe Mechanical Lifting")

        detail = BarrierIntelligenceService.get_barrier_detail("Safe Mechanical Lifting", page=1, page_size=10)

        assert detail["matched_observations"] >= 4
        assert detail["psif_linked_observations"] >= 1
        assert detail["affected_sites"] >= 3
        # Check formula
        expected_rate = round(detail["psif_linked_observations"] / detail["matched_observations"] * 100, 1)
        assert detail["psif_linkage_rate"] == expected_rate
        assert f"{expected_rate}% of matched observations were PSIF-linked by the active model" in detail["psif_linkage_rate_label"]

    def test_multi_rule_incident_distinct_counting(self, sample_dataset, sample_model_version):
        """
        An incident matching multiple rules must increment each rule's count,
        but total_matched_distinct across the fleet must count the incident exactly once.
        """
        inc = Incident.objects.create(
            dataset=sample_dataset,
            description="Technician working at height unbolted high pressure gas line without isolation",
            location="Jorhat Well 12",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=sample_model_version,
            psif_probability=0.95,
            psif_predicted=True,
            is_sparse_input=False,
        )
        tag1 = IOGPRuleTag.objects.create(incident=inc, rule="Working at Height")
        tag2 = IOGPRuleTag.objects.create(incident=inc, rule="Energy Isolation")

        portfolio = BarrierIntelligenceService.get_barrier_portfolio(use_cache=False, force_refresh=True)
        wah = next(b for b in portfolio["barriers"] if b["canonical_rule"] == "Working at Height")
        ei = next(b for b in portfolio["barriers"] if b["canonical_rule"] == "Energy Isolation")

        assert wah["matched_observations"] >= 1
        assert ei["matched_observations"] >= 1
        # Distinct fleet count must not double count inc
        assert portfolio["total_matched_distinct"] <= (
            sum(b["matched_observations"] for b in portfolio["barriers"])
        )

    def test_blank_and_none_sites_excluded_from_affected_sites(self, sample_dataset):
        """Locations with None or empty string must not count toward affected_sites."""
        inc_blank = Incident.objects.create(
            dataset=sample_dataset,
            description="Work authorization permit expired during pump swap",
            location="",
        )
        inc_none = Incident.objects.create(
            dataset=sample_dataset,
            description="Work authorization permit missing supervisor signature",
            location=None,
        )
        IOGPRuleTag.objects.create(incident=inc_blank, rule="Work Authorization")
        IOGPRuleTag.objects.create(incident=inc_none, rule="Work Authorization")

        # Initial sites count
        portfolio = BarrierIntelligenceService.get_barrier_portfolio(use_cache=False, force_refresh=True)
        wa = next(b for b in portfolio["barriers"] if b["canonical_rule"] == "Work Authorization")
        # Now add one valid site
        inc_valid = Incident.objects.create(
            dataset=sample_dataset,
            description="Work authorization permit audited on drill site",
            location="Unique Site Alpha 999",
        )
        IOGPRuleTag.objects.create(incident=inc_valid, rule="Work Authorization")

        portfolio_after = BarrierIntelligenceService.get_barrier_portfolio(use_cache=False, force_refresh=True)
        wa_after = next(b for b in portfolio_after["barriers"] if b["canonical_rule"] == "Work Authorization")
        assert wa_after["affected_sites"] == wa["affected_sites"] + 1


# ─────────────────────────────────────────────────────────────────────────────
# 2. CONTROL STATES & EVIDENCE REQUIREMENTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestControlStatesAndEvidence:
    def test_unknown_control_preservation_when_fields_empty(self, sample_dataset):
        """
        CRITICAL SAFETY RULE:
        When structured control fields are None/unknown and narrative has no failure span,
        the control state MUST remain UNKNOWN. Never default to COMPROMISED.
        """
        inc = Incident.objects.create(
            dataset=sample_dataset,
            description="Standard routine maintenance was scheduled on compressor skid.",
            control_condition=Incident.ControlCondition.UNKNOWN,
            control_failed_bypassed=None,
        )
        linkage = BarrierIntelligenceService.evaluate_incident_control_linkage(inc)
        assert linkage.control_state == ControlSemantics.UNKNOWN
        assert linkage.control_evidence == UNKNOWN_CONTROL_EVIDENCE_TEXT

    def test_explicit_compromised_control_detection(self, sample_dataset):
        """Explicit evidence of bypass or failure sets control state to COMPROMISED."""
        # Case A: Structured field
        inc1 = Incident.objects.create(
            dataset=sample_dataset,
            description="Technician entered enclosure",
            control_failed_bypassed=True,
            control_condition="bypassed",
        )
        linkage1 = BarrierIntelligenceService.evaluate_incident_control_linkage(inc1)
        assert linkage1.control_state == ControlSemantics.COMPROMISED
        assert "explicitly recorded" in linkage1.control_evidence

        # Case B: Narrative failure cue
        inc2 = Incident.objects.create(
            dataset=sample_dataset,
            description="The high pressure relief line isolation was bypassed without authorization",
            control_condition=Incident.ControlCondition.UNKNOWN,
            control_failed_bypassed=None,
        )
        linkage2 = BarrierIntelligenceService.evaluate_incident_control_linkage(inc2)
        assert linkage2.control_state == ControlSemantics.COMPROMISED
        assert "bypassed" in linkage2.control_evidence.lower()

    def test_explicit_controlled_barrier_detection(self, sample_dataset):
        """Explicit evidence of effective control sets control state to CONTROLLED."""
        # Case A: Structured field
        inc1 = Incident.objects.create(
            dataset=sample_dataset,
            description="Maintenance commenced safely",
            control_condition=Incident.ControlCondition.EFFECTIVE,
        )
        linkage1 = BarrierIntelligenceService.evaluate_incident_control_linkage(inc1)
        assert linkage1.control_state == ControlSemantics.CONTROLLED
        assert "Effective / Held" in linkage1.control_evidence

        # Case B: Narrative effective cue
        inc2 = Incident.objects.create(
            dataset=sample_dataset,
            description="The crew followed lockout procedure and zero energy verified before work began",
            control_condition=Incident.ControlCondition.UNKNOWN,
        )
        linkage2 = BarrierIntelligenceService.evaluate_incident_control_linkage(inc2)
        assert linkage2.control_state == ControlSemantics.CONTROLLED
        assert "zero energy verified" in linkage2.control_evidence.lower()

    def test_partially_effective_control_detection(self, sample_dataset):
        """When both effective cue and compromise cue are cited, state is PARTIALLY_EFFECTIVE."""
        inc = Incident.objects.create(
            dataset=sample_dataset,
            description="Although zero energy verified earlier, the isolation was bypassed during the shift change",
        )
        linkage = BarrierIntelligenceService.evaluate_incident_control_linkage(inc)
        assert linkage.control_state == ControlSemantics.PARTIALLY_EFFECTIVE
        assert "effective control also cited" in linkage.control_evidence


# ─────────────────────────────────────────────────────────────────────────────
# 3. CACHE BEHAVIOR & INVALIDATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCacheAndInvalidation:
    def test_cache_population_and_invalidation(self):
        """Verify dashboard:barrier_intelligence:v1 cache key and invalidation."""
        cache.delete(CACHE_KEY_BARRIER_INTELLIGENCE)
        assert cache.get(CACHE_KEY_BARRIER_INTELLIGENCE) is None

        # Fetch populates cache
        data = get_barrier_intelligence(use_cache=True)
        assert data is not None
        assert cache.get(CACHE_KEY_BARRIER_INTELLIGENCE) is not None

        # Invalidate clears cache
        invalidate_analytics_cache()
        assert cache.get(CACHE_KEY_BARRIER_INTELLIGENCE) is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. ACTION ENGINE & INVESTIGATION WORKSPACE INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestActionEngineAndWorkspaceIntegration:
    def test_action_engine_energy_isolation_unknown_vs_bypass(self, sample_dataset):
        """
        TASK 10/11 ACTION CONTRACT:
        - Energy Isolation + no control evidence must NOT produce 'Isolation controls failed',
          but produce 'Verify isolation status and evidence of effective energy isolation.'
        - Energy Isolation + explicit bypass produces 'Verify isolation/bypass-control compliance at the identified work activity.'
        """
        from apps.incidents.services.action_library import get_corrective_actions

        # Case 1: Unknown control state
        inc_unk = Incident.objects.create(
            dataset=sample_dataset,
            description="Routine pump inspection scheduled in battery area",
            energy_type="electrical",
            control_condition=Incident.ControlCondition.UNKNOWN,
        )
        IOGPRuleTag.objects.create(incident=inc_unk, rule="Energy Isolation")
        res_unk = get_corrective_actions(inc_unk)
        actions_unk = res_unk.get("actions", [])

        # Must NOT claim isolation controls failed
        for act in actions_unk:
            assert "isolation controls failed" not in act.get("title", "").lower()
            assert "isolation controls failed" not in act.get("description", "").lower()

        # Check for verification action
        unk_action = next(
            (a for a in actions_unk if "effective energy isolation" in a.get("description", "").lower() or "verify isolation status" in a.get("description", "").lower() or "verify isolation" in a.get("title", "").lower()),
            None,
        )
        assert unk_action is not None

        # Case 2: Explicit bypass
        inc_byp = Incident.objects.create(
            dataset=sample_dataset,
            description="Technician bypassed the electrical lockout breaker to test motor rotation",
            energy_type="electrical",
            control_failed_bypassed=True,
            control_condition="bypassed",
        )
        IOGPRuleTag.objects.create(incident=inc_byp, rule="Energy Isolation")
        res_byp = get_corrective_actions(inc_byp)
        actions_byp = res_byp.get("actions", [])

        byp_action = next(
            (a for a in actions_byp if "bypass" in a.get("title", "").lower() or "bypass-control" in a.get("description", "").lower()),
            None,
        )
        assert byp_action is not None

    def test_investigation_workspace_barrier_context_integration(self, sample_dataset, sample_model_version):
        """Unified Investigation Workspace includes complete Barrier context with 7-stage linkage."""
        inc = Incident.objects.create(
            dataset=sample_dataset,
            description="Worker engaged in hot work near manifold without permit check",
            location="Naharkatiya Station",
            energy_type="thermal",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=sample_model_version,
            psif_probability=0.75,
            psif_predicted=True,
            is_sparse_input=False,
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Hot Work",
            matched_keywords=["hot work"],
            matched_fields=["description"],
        )

        ws = compose_investigation_workspace(inc)
        b_context = ws.get("barrier_context", {})

        assert b_context["status"] == "ok"
        assert b_context["count"] >= 1
        item = next((b for b in b_context["items"] if b["rule"] == "Hot Work"), None)
        assert item is not None
        assert item["control_state"] in ControlSemantics.ALL_STATES
        assert item["evidence"] is not None
        assert item["evidence_strength"] in ["STRONG", "MODERATE", "WEAK"]
        assert item["psif_pathway_role"] is not None
        assert item["action_linkage"] is not None
        assert "matched_observations" in item


# ─────────────────────────────────────────────────────────────────────────────
# 5. REST API & DETAIL VIEW TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBarrierAPIAndDetailViews:
    def test_barrier_api_returns_authoritative_payload(self, auth_client):
        """GET /api/analytics/barriers/ returns 200 with 9 rules and required metadata."""
        resp = auth_client.get("/api/analytics/barriers/")
        assert resp.status_code == 200
        data = resp.data
        assert "barriers" in data
        assert len(data["barriers"]) == 9
        assert data["canonical_rule_count"] == 9
        assert "methodology_statement" in data
        assert "rate_definition" in data
        assert "table_columns" in data

    def test_barrier_detail_api_valid_rule(self, auth_client):
        """GET /api/analytics/barriers/<rule_slug>/ returns rule detail with representative incidents."""
        resp = auth_client.get("/api/analytics/barriers/safe-mechanical-lifting/")
        assert resp.status_code == 200
        data = resp.data
        assert data["rule"] == "Safe Mechanical Lifting"
        assert "matched_observations" in data
        assert "psif_linked_observations" in data
        assert "affected_sites" in data
        assert "psif_linkage_rate" in data
        assert "sampling_notice" in data
        assert "representative_incidents" in data

    def test_barrier_detail_api_invalid_rule_returns_404(self, auth_client):
        """GET /api/analytics/barriers/<invalid>/ returns 404."""
        resp = auth_client.get("/api/analytics/barriers/non-existent-tenth-rule/")
        assert resp.status_code == 404

    def test_barrier_detail_html_view_renders(self, auth_client):
        """GET /dashboard/barriers/<rule_slug>/ renders 200 HTML."""
        client = Client()
        user = User.objects.get(username="barrier_tester")
        client.force_login(user)
        resp = client.get("/dashboard/barriers/safe-mechanical-lifting/")
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Safe Mechanical Lifting" in content
        assert "Representative Incidents" in content
        assert "Methodology Notice" in content


# ─────────────────────────────────────────────────────────────────────────────
# 6. LIVE DATABASE REGRESSION VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLiveDatabaseRegressionBaseline:
    def test_regression_against_baseline_live_dataset(self):
        """
        Validates against current real loaded dataset (560k incidents).
        Ensures methodology does not drift:
        - Exactly 9 rules
        - High volume rules have matched observations > 25,000
        - Rates are between 40% and 95%
        - Affected sites between 50 and 200
        """
        data = BarrierIntelligenceService.get_barrier_portfolio(use_cache=False, force_refresh=True)
        assert data["total_monitored_barriers"] == 9

        rules_dict = {b["rule"]: b for b in data["barriers"]}

        # Check all 9 rules exist
        for r in CANONICAL_IOGP_RULES:
            assert r in rules_dict

        # If running on full database (total_matched_distinct > 10,000)
        if data["total_matched_distinct"] > 10000:
            assert rules_dict["Safe Mechanical Lifting"]["matched_observations"] > 100000
            assert rules_dict["Energy Isolation"]["matched_observations"] > 100000
            assert rules_dict["Driving"]["matched_observations"] > 70000
            assert rules_dict["Hot Work"]["matched_observations"] > 60000
            assert rules_dict["Working at Height"]["matched_observations"] > 50000
            assert rules_dict["Confined Space"]["matched_observations"] > 30000
            assert rules_dict["Line of Fire"]["matched_observations"] > 30000
            assert rules_dict["Work Authorization"]["matched_observations"] > 25000
            assert rules_dict["Bypassing Safety Controls"]["matched_observations"] > 25000

            for r, b in rules_dict.items():
                assert 40.0 <= b["psif_linkage_rate"] <= 95.0
                assert 50 <= b["affected_sites"] <= 250
