"""
PSIF Platform — Model Assurance & Data Quality Test Suite (Task 12)
tests/test_model_assurance.py

Comprehensive tests covering:
1. Model Registry Auditing & Actual Database State
2. Score Semantics & Disclaimers ("PSIF Model Score", not calibrated probability)
3. Independent Binary Metric Denominators (PSIF vs NOT PSIF precision/recall)
4. Human Review Honesty (Zero genuine OIL field human validation, honest simulation disclosure)
5. Data Quality Categories, Gating & 4 Distinct Evidence States (Sparse != Invalid)
6. Training Data Leakage Controls (Quarantined severity and corrective actions)
7. Split Methodology & Synthetic Artifacts Disclosures
8. Model / Safety Rule Reconciliation ("Model-rule disagreement requires human review")
9. Robustness: Contrastive Pairs, Negation, Empty and Garbage Input
10. Active Model Protection & Drift Detection
11. Ingestion Pathway Assurance (All 6 Pathways)
12. REST APIs and UI View Rendering
"""

import pytest
from django.test import Client

from apps.accounts.models import User
from apps.datasets.models import Dataset
from apps.incidents.models import Incident, IncidentDataQuality, IncidentReview, IOGPRuleTag
from apps.incidents.services.data_quality import (
    DataEvidenceState,
    validate_incident_for_analysis,
    classify_incident_data_evidence_state,
    compute_narrative_duplicate_hash,
)
from apps.incidents.services.dq_assurance_service import DataQualityAssuranceService
from apps.incidents.services.evidence import evidence_from_shap
from apps.incidents.services.psif_reasoning import (
    extract_incident_safety_evidence,
    build_incident_reasoning_assessment,
)
from apps.predictions.models import ModelVersion, PredictionResult
from apps.predictions.services.assurance_service import (
    ModelAssuranceService,
    SCORE_SEMANTICS_DISCLAIMER,
    METHODOLOGY_STATEMENT,
)
from ml_engine.feature_encoder import (
    BOOLEAN_FIELDS,
    NUMERIC_FIELDS,
    CATEGORICAL_FIELDS,
)


@pytest.fixture
def auth_client(db):
    user, _ = User.objects.get_or_create(
        username="test_assurance_admin",
        defaults={
            "email": "admin@foresight.oil.in",
            "is_superuser": True,
            "is_staff": True,
            "role": "hse_lead_auditor",
        },
    )
    user.set_password("password123")
    user.save()
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def setup_assurance_db(db):
    """Populate database with active and historical model versions, incidents, and reviews."""
    dataset, _ = Dataset.objects.get_or_create(name="Assurance Benchmark Dataset")

    # 1. Active Model Version
    active_mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_20260906_202052",
        defaults={
            "bert_model_name": "distilbert-base-uncased",
            "xgboost_artifact_path": "/tmp/test_xgb.json",
            "encoder_artifact_path": "/tmp/test_enc.joblib",
            "is_active": True,
            "metrics": {
                "selected_threshold": 0.20,
                "threshold_methodology": "F2-optimal from OOF",
                "training_source": "SYNTHETIC",
                "validation_basis": "SYNTHETIC DATASET EVALUATION",
                "split_methodology": "85% train / 15% test, stratified",
                "random_seed": 42,
                "bert_dim": 768,
                "structured_feature_count": 88,
                "fused_dimension": 856,
                "total_labeled_rows": 50000,
                "positive_count": 12500,
                "negative_count": 37500,
                "metrics_final_test": {
                    "precision": 0.8182,
                    "recall": 0.9000,
                    "f1": 0.8571,
                    "f2": 0.8824,
                    "roc_auc": 0.9100,
                    "pr_auc": 0.8950,
                    "confusion_matrix": [[80, 20], [10, 90]],  # [[TN, FP], [FN, TP]]
                },
                "leakage_notes": "severity_actual and severity_potential do not enter structured features. corrective_actions is quarantined.",
            },
        },
    )

    # 2. Historical Model Version
    hist_mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_20260902_122321",
        defaults={
            "bert_model_name": "distilbert-base-uncased",
            "is_active": False,
            "metrics": {
                "selected_threshold": 0.10,
                "training_source": "SYNTHETIC",
                "metrics_final_test": {
                    "precision": 0.2018,
                    "recall": 0.9565,
                    "f1": 0.3331,
                    "roc_auc": 0.6215,
                    "pr_auc": 0.3742,
                    "confusion_matrix": [[10, 40], [2, 48]],
                },
            },
        },
    )

    # 3. Sample Incidents with Predictions and IOGP Rules
    inc1 = Incident.objects.create(
        dataset=dataset,
        description="High pressure gas line maintenance. Energy isolation was bypassed during valve overhaul.",
        location="Assam Asset Rig 02",
        department="Drilling",
        job_task="Valve maintenance",
        is_synthetic=True,
    )
    IOGPRuleTag.objects.create(incident=inc1, rule="Energy Isolation", confidence=0.95)
    PredictionResult.objects.create(
        incident=inc1,
        model_version=active_mv,
        psif_probability=0.88,
        psif_predicted=True,
        evidence_strength="Strong",
        is_sparse_input=False,
    )
    IncidentDataQuality.objects.create(
        incident=inc1,
        status=IncidentDataQuality.Status.VALID,
        quality_version="incident_quality_v1",
    )

    # Simulated Reviewer Record
    sim_user, _ = User.objects.get_or_create(
        username="hse_lead_auditor",
        defaults={"role": "hse_lead_auditor"},
    )
    IncidentReview.objects.create(
        incident=inc1,
        reviewer=sim_user,
        decision="PSIF",
        rationale="Simulated test review for bypass of energy isolation barrier.",
        is_synthetic=True,
    )

    return active_mv


# ── 1. Model Registry Audit & Score Semantics ────────────────────────────────

@pytest.mark.django_db
def test_model_registry_audit_live_db(setup_assurance_db):
    """Verify registry audit queries real database records without hardcoding."""
    audit = ModelAssuranceService.get_model_registry_audit()

    assert audit["registered_models_count"] >= 1
    assert "active_model" in audit
    active = audit["active_model"]
    assert active is not None
    assert active["is_active"] is True
    assert active["score_semantics"] == "PSIF Model Score"
    assert active["score_disclaimer"] == SCORE_SEMANTICS_DISCLAIMER
    assert SCORE_SEMANTICS_DISCLAIMER in audit["score_semantics_rule"]

    # Verify live predictions in PostgreSQL
    live_preds = active["live_predictions"]
    assert live_preds["total"] >= 0
    assert live_preds["psif_count"] >= 0
    assert 0.0 <= live_preds["psif_rate"] <= 100.0


def test_score_semantics_disclaimer_content():
    """Verify that score semantics explicitly state model score is not calibrated probability."""
    assert "calibrated probability" in SCORE_SEMANTICS_DISCLAIMER.lower()
    assert "relative model output" in SCORE_SEMANTICS_DISCLAIMER.lower()


# ── 2. Independent Binary Metric Denominators ───────────────────────────────

@pytest.mark.django_db
def test_independent_binary_metric_denominators(setup_assurance_db):
    """Verify independent denominators for PSIF and NOT PSIF precision and recall."""
    audit = ModelAssuranceService.get_model_registry_audit()
    active = audit["active_model"]
    metrics = active["evaluation_metrics"]

    # Independent formulas must be explicitly declared
    assert "predicted-positive" in metrics["psif_precision_formula"].lower()
    assert "actual-positive" in metrics["psif_recall_formula"].lower()
    assert "predicted-negative" in metrics["not_psif_precision_formula"].lower()
    assert "actual-negative" in metrics["not_psif_recall_formula"].lower()

    # Values must be numeric and bounded [0, 1]
    assert 0.0 <= metrics["psif_precision"] <= 1.0
    assert 0.0 <= metrics["psif_recall"] <= 1.0
    assert 0.0 <= metrics["not_psif_precision"] <= 1.0
    assert 0.0 <= metrics["not_psif_recall"] <= 1.0


# ── 3. Human Review Honesty & Provenance ─────────────────────────────────────

@pytest.mark.django_db
def test_human_review_honesty_zero_real_validation(setup_assurance_db):
    """Verify platform strictly discloses zero genuine OIL field human validation."""
    human_audit = ModelAssuranceService.get_human_review_audit()

    assert human_audit["real_human_validation_count"] == 0
    assert "ZERO (0)" in human_audit["real_human_validation_statement"]
    assert human_audit["human_approved_synthetic_count"] == 0

    # Simulated reviews must be attributed to simulated/development users
    assert human_audit["simulated_human_reviews_count"] >= 1
    assert "governance_rule" in human_audit
    assert "synthetic and simulated reviewer judgments must never be claimed" in human_audit["governance_rule"]


# ── 4. Data Quality Categories & Gating ─────────────────────────────────────

@pytest.mark.django_db
def test_data_quality_gating_and_categories():
    """Test data quality checks for critical rejection vs warning admission."""
    # Critical: empty narrative
    res_empty = validate_incident_for_analysis({
        "description": "",
        "incident_date": "2025-01-01",
    })
    assert res_empty["quality_status"] == IncidentDataQuality.Status.CRITICAL
    assert any(f["check_id"] == "MISSING_NARRATIVE" for f in res_empty["findings"])

    # Critical: unsupported encoding / null byte
    res_encoding = validate_incident_for_analysis({
        "description": "Corrupted text \x00\ufffd line break",
        "incident_date": "2025-01-01",
    })
    assert res_encoding["quality_status"] == IncidentDataQuality.Status.CRITICAL
    assert any(f["check_id"] == "UNSUPPORTED_ENCODING" for f in res_encoding["findings"])

    # Warning: short narrative (< 10 words)
    res_short = validate_incident_for_analysis({
        "description": "Valve leaked slightly.",
        "incident_date": "2025-01-01",
    })
    assert res_short["quality_status"] == IncidentDataQuality.Status.WARNING
    assert any(f["check_id"] == "SHORT_NARRATIVE" for f in res_short["findings"])

    # Valid: complete operational narrative
    res_valid = validate_incident_for_analysis({
        "description": "Worker was performing scheduled maintenance on the high pressure separator valve when flange loosened.",
        "incident_date": "2025-01-01",
        "department": "Production",
        "location": "Platform Alpha",
        "job_task": "Valve replacement",
    })
    assert res_valid["quality_status"] == IncidentDataQuality.Status.VALID


@pytest.mark.django_db
def test_data_evidence_states_distinct():
    """Verify the 4 distinct evidence states do not collapse into NOT PSIF."""
    inc_crit = Incident(description="")
    inc_sparse = Incident(description="Gas leak.")
    inc_low_ev = Incident(
        description="Routine morning inspection was completed at pump station without any identified issues."
    )

    state_crit = classify_incident_data_evidence_state(inc_crit)
    state_sparse = classify_incident_data_evidence_state(inc_sparse)
    state_low_ev = classify_incident_data_evidence_state(inc_low_ev)

    assert state_crit == DataEvidenceState.INVALID_DATA
    assert state_sparse == DataEvidenceState.SPARSE_DATA
    assert state_low_ev in [DataEvidenceState.VALID_LOW_EVIDENCE, DataEvidenceState.VALID]

    # None of these may collapse into NOT PSIF
    assert state_crit != "NOT_PSIF"
    assert state_sparse != "NOT_PSIF"


# ── 5. Training Data Leakage Controls ────────────────────────────────────────

def test_training_data_leakage_quarantine():
    """Verify predictive model features exclude actual/potential severity and corrective actions."""
    all_features = set(BOOLEAN_FIELDS + NUMERIC_FIELDS + CATEGORICAL_FIELDS)

    # Must NOT contain target-derived or outcome-derived fields
    assert "severity_actual" not in all_features
    assert "severity_potential" not in all_features
    assert "corrective_action" not in all_features
    assert "corrective_actions" not in all_features
    assert "human_decision" not in all_features
    assert "adjudicated_human_decision" not in all_features
    assert "psif_target" not in all_features
    assert "is_psif" not in all_features


# ── 6. Robustness & Contrastive Pairs ───────────────────────────────────────

@pytest.mark.django_db
def test_robustness_contrastive_pairs():
    """Verify bypassed vs verified controls do not collapse to same reasoning state."""
    inc_bypassed = Incident(
        description="High pressure gas line maintenance. Isolation was bypassed during maintenance."
    )
    inc_verified = Incident(
        description="High pressure gas line maintenance. Isolation was verified before maintenance."
    )

    ev_bypassed = extract_incident_safety_evidence(inc_bypassed)
    ev_verified = extract_incident_safety_evidence(inc_verified)

    assert ev_bypassed["control"].state != ev_verified["control"].state
    assert ev_bypassed["control"].state == "BYPASSED"
    assert ev_verified["control"].state == "EFFECTIVE"
    assert ev_bypassed["control"].is_compromised is True
    assert ev_verified["control"].is_compromised is False


@pytest.mark.django_db
def test_robustness_empty_and_garbage_input():
    """Verify safety reasoning and SHAP do not crash on empty or garbage inputs."""
    inc_empty = Incident(description="")
    inc_garbage = Incident(description="@#$%^&*()_+ 12345 99999 \x00")

    ev_empty = extract_incident_safety_evidence(inc_empty)
    ev_garbage = extract_incident_safety_evidence(inc_garbage)

    assert ev_empty is not None
    assert ev_garbage is not None

    # SHAP robustness with garbage/missing values
    shap_bad1 = evidence_from_shap({"feature": "test", "contribution": "not_a_number"})
    shap_bad2 = evidence_from_shap({"feature": None, "contribution": None})
    shap_bad3 = evidence_from_shap("not_a_dict")

    assert shap_bad1.value == 0.0
    assert shap_bad2.value == 0.0
    assert shap_bad3.value == 0.0


# ── 7. Model / Safety Rule Reconciliation ────────────────────────────────────

@pytest.mark.django_db
def test_model_rule_reconciliation_statement(setup_assurance_db):
    """Verify reconciliation uses required text and never classifies disagreement as model error."""
    incident = Incident.objects.filter(iogp_rules__isnull=False, prediction__isnull=False).first()
    assert incident is not None

    reconciliation = ModelAssuranceService.evaluate_model_rule_reconciliation(incident)

    assert "model_decision" in reconciliation
    assert "rule_decision" in reconciliation
    assert "reconciliation_status" in reconciliation
    assert "reconciliation_statement" in reconciliation
    assert "final_policy" in reconciliation

    # Never claim "model error"
    assert "model error" not in reconciliation["reconciliation_statement"].lower()

    if not reconciliation["agreement"]:
        assert reconciliation["reconciliation_statement"] == "Model-rule disagreement requires human review."
        assert reconciliation["final_policy"] == "HUMAN_ADJUDICATION_REQUIRED"


# ── 8. Active Model Protection & Drift Detection ─────────────────────────────

@pytest.mark.django_db
def test_active_model_drift_safeguard(setup_assurance_db):
    """Test model drift detection flags invalid mutations in thresholds or features."""
    active_model = ModelVersion.objects.filter(is_active=True).first()
    assert active_model is not None

    audit_stable = ModelAssuranceService.detect_model_drift_or_change(active_model)
    assert audit_stable["status"] == "STABLE"
    assert audit_stable["is_stable"] is True

    # Mutate threshold artificially on a mock copy
    mock_metrics = dict(active_model.metrics or {})
    mock_metrics["selected_threshold"] = 0.99
    active_model.metrics = mock_metrics

    audit_drift = ModelAssuranceService.detect_model_drift_or_change(active_model)
    assert audit_drift["status"] == "DRIFT_DETECTED"
    assert audit_drift["is_stable"] is False
    assert len(audit_drift["drift_issues"]) > 0


# ── 9. Ingestion Pathways Assurance Audit ────────────────────────────────────

@pytest.mark.django_db
def test_ingestion_pathways_audit():
    """Verify all 6 ingestion pathways are audited with validation gating."""
    dq_summary = DataQualityAssuranceService.get_data_quality_summary()
    pathways = dq_summary["ingestion_pathways"]

    assert len(pathways) == 6
    names = [p["pathway_name"] for p in pathways]
    assert "CSV Batch Ingestion" in names
    assert "JSON / JSONL Bulk Upload" in names
    assert "Interactive Web Form Submission" in names
    assert "REST API Incident Submission" in names
    assert "Document & Multi-Format Ingestion" in names
    assert "Manual Single Prediction API" in names

    for p in pathways:
        assert p["gating_applied"] is True
        assert p["provenance_recorded"] is True
        assert p["critical_action"] is not None


# ── 10. REST API Endpoints Verification ──────────────────────────────────────

@pytest.mark.django_db
def test_rest_api_model_assurance_and_dq(auth_client, setup_assurance_db):
    """Verify all Model Assurance and Data Quality REST API endpoints respond 200."""
    endpoints = [
        "/api/model-assurance/",
        "/api/model-assurance/models/",
        "/api/model-assurance/metrics/",
        "/api/model-assurance/human-review/",
        "/api/data-quality/",
        "/api/data-quality/summary/",
    ]
    for url in endpoints:
        resp = auth_client.get(url)
        assert resp.status_code == 200, f"Endpoint {url} failed with {resp.status_code}"
        data = resp.json()
        assert data is not None


# ── 11. UI View Rendering Verification ──────────────────────────────────────

@pytest.mark.django_db
def test_ui_views_model_assurance_and_dq(auth_client, setup_assurance_db):
    """Verify Model Assurance and Data Quality HTML pages render successfully."""
    r_assurance = auth_client.get("/predictions/assurance/")
    assert r_assurance.status_code == 200
    content_ass = r_assurance.content.decode("utf-8")
    assert "PSIF MODEL SCORE" in content_ass
    assert "calibrated probability" in content_ass.lower()
    assert "PSIF Precision" in content_ass
    assert "NOT PSIF Precision" in content_ass
    assert "Human Review Governance" in content_ass

    r_dq = auth_client.get("/dashboard/data-quality/")
    assert r_dq.status_code == 200
    content_dq = r_dq.content.decode("utf-8")
    assert "Data Quality Assurance & Ingestion Governance" in content_dq
    assert "Evidence Sufficiency & Data Quality States" in content_dq
    assert "Category-Level Defect Breakdown" in content_dq
    assert "Ingestion Pathway Assurance" in content_dq
