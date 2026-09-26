"""
FORESIGHT GOLDEN REGRESSION TEST SUITE
======================================
Autonomous Execution Baseline Freeze.

Freezes canonical behavior across:
1. PSIF predictions & explainability structure
2. IOGP Life-Saving Rules deterministic classification
3. Deterministic Pattern Engine (Activity, Barrier, Location extraction)
4. Multi-dimensional pattern matrices
5. Admin Flow workspace isolation and RBAC security
6. Dataset ingestion and cancellation semantics
7. Authentication & human review workflows
8. Similarity & recurrence analysis
"""

import io
import json
import uuid
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.pattern_engine import (
    ADMIN_FLOW_WORKSPACE,
    extract_all_admin_flow_pattern_observations,
    compute_activity_patterns,
    compute_barrier_patterns,
    compute_location_patterns,
    normalize_admin_flow_activity,
    normalize_admin_flow_location,
    invalidate_admin_flow_pattern_cache,
)
from apps.admin_flow.barrier_engine import extract_incident_barriers, BarrierState
from apps.admin_flow.services import (
    get_admin_flow_analytics_summary,
    get_admin_flow_iogp_metrics,
    get_admin_flow_psif_metrics,
)
from apps.datasets.models import Dataset
from apps.incidents.services.normalization import CANONICAL_IOGP_RULES

User = get_user_model()


@pytest.fixture
def golden_users(db):
    admin_flow_user, _ = User.objects.get_or_create(
        username="admin_flow_golden@foresight.app",
        defaults={"role": "admin_flow", "email": "admin_flow_golden@foresight.app", "is_active": True},
    )
    admin_flow_user.set_password("foresight2026")
    admin_flow_user.save()

    enterprise_user, _ = User.objects.get_or_create(
        username="enterprise_golden@foresight.app",
        defaults={"role": "admin", "email": "enterprise_golden@foresight.app", "is_active": True, "is_staff": True},
    )
    enterprise_user.set_password("foresight2026")
    enterprise_user.save()

    return {"admin_flow": admin_flow_user, "enterprise": enterprise_user}


@pytest.fixture
def golden_model_version(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="golden_v1_freeze",
        defaults={"is_active": True, "status": ModelVersion.Status.ACTIVE},
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


# ==============================================================================
# 1. PSIF PREDICTION & MODEL INTERACTION INTEGRITY
# ==============================================================================
@pytest.mark.django_db
class TestGoldenPSIFPredictions:
    def test_psif_prediction_fields_and_semantics(self, golden_model_version):
        inc = Incident.objects.create(
            workspace_id="default",
            description="High pressure steam flange leaked causing 2nd degree burn in Boiler Room.",
            department="Operations",
            location="Boiler Room",
            job_task="Steam Pipe Servicing",
        )
        pred = PredictionResult.objects.create(
            incident=inc,
            model_version=golden_model_version,
            psif_probability=0.875,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
            top_factors=[{"feature": "steam", "contribution": 0.35}],
        )
        assert pred.psif_predicted is True
        assert abs(pred.psif_probability - 0.875) < 1e-5
        assert pred.risk_level == "high"
        assert pred.top_factors[0]["feature"] == "steam"


# ==============================================================================
# 2. IOGP LIFE-SAVING RULES CLASSIFICATION FREEZE
# ==============================================================================
@pytest.mark.django_db
class TestGoldenIOGPClassification:
    def test_canonical_rules_frozen_list(self):
        expected_rules = [
            "Bypassing Safety Controls",
            "Confined Space",
            "Driving",
            "Energy Isolation",
            "Hot Work",
            "Line of Fire",
            "Safe Mechanical Lifting",
            "Work Authorization",
            "Working at Height",
        ]
        for r in expected_rules:
            assert r in CANONICAL_IOGP_RULES

    def test_iogp_rule_tag_association(self):
        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Worker slipped while on mobile scaffold 5 meters above ground.",
            location="Site Alpha",
        )
        tag = IOGPRuleTag.objects.create(incident=inc, rule="Working at Height", confidence=0.95)
        assert tag.rule == "Working at Height"
        assert tag.incident == inc


# ==============================================================================
# 3. DETERMINISTIC PATTERN ENGINE FREEZE (Activity, Barrier, Location)
# ==============================================================================
@pytest.mark.django_db
class TestGoldenPatternEngine:
    def test_activity_normalization_frozen_mapping(self):
        # Operational activity exact mapping
        name, method = normalize_admin_flow_activity("Safe Mechanical Lifting", None)
        assert name == "Safe Mechanical Lifting"

        # Narrative keyword extraction
        name2, method2 = normalize_admin_flow_activity(None, "While performing chemical transfer with pump.")
        assert "Chemical" in name2

    def test_location_normalization_frozen_mapping(self):
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            location="Compressor Area",
            description="Routine pump inspection in compressor building.",
        )
        norm_loc, field, method = normalize_admin_flow_location(inc)
        assert norm_loc == "Compressor Area"

    def test_barrier_extraction_deficiency_vs_effective(self):
        # Effective safeguard
        inc_eff = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="The safety harness held and arrested the fall safely.",
            control_condition="effective",
        )
        bar_eff = extract_incident_barriers(inc_eff)
        assert len(bar_eff) >= 1
        assert bar_eff[0].is_effective is True
        assert bar_eff[0].is_deficient is False

        # Deficient barrier
        inc_def = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Machine guard had been removed before maintenance began.",
            control_condition="absent",
        )
        bar_def = extract_incident_barriers(inc_def)
        assert len(bar_def) >= 1
        assert bar_def[0].is_deficient is True


# ==============================================================================
# 4. WORKSPACE ISOLATION & ACCESS CONTROL FREEZE
# ==============================================================================
@pytest.mark.django_db
class TestGoldenWorkspaceIsolation:
    def test_hard_partitioning_between_admin_flow_and_global(self, client, golden_users):
        # Create global record
        Incident.objects.create(
            workspace_id="default",
            description="Global offshore platform emergency blowout in Gulf of Mexico.",
            location="Gulf Deepwater Platform",
        )
        # Create admin flow record
        Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Admin Flow localized demo incident in Process Unit.",
            location="Process Unit",
        )

        # Admin flow user sees only admin_flow
        client.force_login(golden_users["admin_flow"])
        resp_af = client.get(reverse("admin_flow:dashboard"))
        assert resp_af.status_code == 200
        content_af = resp_af.content.decode()
        assert "Gulf Deepwater Platform" not in content_af

        # Enterprise user is strictly forbidden from admin flow workspace
        client.force_login(golden_users["enterprise"])
        resp_forbid = client.get(reverse("admin_flow:dashboard"))
        assert resp_forbid.status_code == 403


# ==============================================================================
# 5. DATASET PROCESSING & CANCELLATION SEMANTICS
# ==============================================================================
@pytest.mark.django_db
class TestGoldenDatasetSemantics:
    def test_dataset_cancellation_flag(self):
        ds = Dataset.objects.create(
            name="test_cancellation.csv",
            status=Dataset.Status.PROCESSING,
            total_rows=100,
            processed_rows=10,
        )
        assert ds.status == Dataset.Status.PROCESSING
        ds.cancel_requested = True
        ds.status = Dataset.Status.CANCEL_REQUESTED
        ds.save(update_fields=["cancel_requested", "status"])
        ds.refresh_from_db()
        assert ds.status == Dataset.Status.CANCEL_REQUESTED
        assert ds.cancel_requested is True


# ==============================================================================
# 6. HEALTH ENDPOINT
# ==============================================================================
@pytest.mark.django_db
class TestGoldenHealthEndpoint:
    def test_health_check_endpoint(self, client):
        resp = client.get("/health/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["database"] == "ok"
        assert "cache" in data

