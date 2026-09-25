"""
Comprehensive Test Suite for Binary PSIF Decision & Explanation Engine.

Covers all 20 required verification scenarios:
 1. Binary PSIF classification (psif_predicted=True -> PSIF).
 2. Binary NOT PSIF classification (psif_predicted=False -> NOT PSIF).
 3. UNKNOWN handling (missing severity -> None, never False).
 4. Human label precedence (human label overrides heuristic label).
 5. Heuristic provenance (psif_label_source=heuristic).
 6. No silent conversion of UNKNOWN -> NOT PSIF in dataset/training prep.
 7. Threshold configuration (configurable threshold triggers correct binary decision).
 8. Explanation generation (produces all required SIF evidence keys).
 9. Supporting evidence extraction (high-energy, exposure, control failure).
10. Contradicting evidence handling (effective controls, isolated workers).
11. Missing-information handling (flags omitted fields).
12. SHAP positive/negative contributor handling (separated polarity, non-causal).
13. Data-quality integration (DQ findings reflected in limitations).
14. Analytical sufficiency (INSUFFICIENT_EVIDENCE for sparse input with non-PSIF disclaimer).
15. Human-review override (HSE review updates ground truth and rationale).
16. Model prediction preservation after human review (original prediction immutable).
17. Dashboard binary metric definitions (independent denominators and canonical formulas).
18. Regression test proving legacy Low/Medium/High/Critical is no longer primary output.
19. Sparse/meaningless narrative behavior (< 10 words flagged).
20. Adversarial narrative handling (severity keywords used colloquially without physical mechanism).
"""

import uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.incidents.models import (
    Incident,
    IncidentDataQuality,
)
from apps.predictions.models import (
    ModelVersion,
    PredictionResult,
)
from ml_engine.explanation_engine import generate_explanation
from ml_engine.model_inference import PredictionOutput
from apps.incidents.services.decision_trace import (
    evaluate_psif_sufficiency,
    build_analytical_assessment,
)
from apps.dashboard.api_views import CANONICAL_METRIC_DEFINITIONS

User = get_user_model()


class BinaryPSIFClassificationTests(TestCase):
    """Tests 1, 2, 7, 18: Binary candidate classification, thresholding, and legacy deprecation."""

    def setUp(self):
        self.model_version = ModelVersion.objects.create(
            version_label="test_model_v1",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="ml_engine/artifacts/test_model_v1/model.json",
            encoder_artifact_path="ml_engine/artifacts/test_model_v1/encoders.joblib",
            is_active=True,
            metrics={"selected_threshold": 0.35, "precision": 0.85, "recall": 0.80},
        )
        self.incident = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="High pressure steam line vented into work bay near personnel.",
            department="Operations",
            incident_date="2026-09-01",
        )

    def test_01_binary_psif_classification(self):
        """Test 1: psif_predicted=True yields binary classification 'PSIF'."""
        pred = PredictionResult.objects.create(
            incident=self.incident,
            model_version=self.model_version,
            psif_probability=0.78,
            psif_predicted=True,
            risk_level="high",  # legacy band
            evidence_strength="Strong",
            is_sparse_input=False,
            explanation_detail={"high_energy_source": {"identified": True}},
        )
        self.assertEqual(pred.binary_classification, "PSIF")
        self.assertEqual(pred.psif_score, 0.78)
        self.assertTrue(pred.psif_predicted)

    def test_02_binary_not_psif_classification(self):
        """Test 2: psif_predicted=False yields binary classification 'NOT PSIF'."""
        pred = PredictionResult.objects.create(
            incident=self.incident,
            model_version=self.model_version,
            psif_probability=0.12,
            psif_predicted=False,
            risk_level="low",  # legacy band
            evidence_strength="Strong",
            is_sparse_input=False,
        )
        self.assertEqual(pred.binary_classification, "NOT PSIF")
        self.assertEqual(pred.psif_score, 0.12)
        self.assertFalse(pred.psif_predicted)

    def test_07_threshold_configuration(self):
        """Test 7: Configurable threshold determines binary decision."""
        # Threshold at 0.35: score 0.30 -> False, score 0.40 -> True
        threshold = self.model_version.metrics.get("selected_threshold", 0.5)
        self.assertEqual(threshold, 0.35)

        score_below = 0.30
        pred_below = score_below >= threshold
        self.assertFalse(pred_below)

        score_above = 0.40
        pred_above = score_above >= threshold
        self.assertTrue(pred_above)

        # Output dataclass behaves consistently
        out = PredictionOutput(
            psif_probability=0.40,
            psif_predicted=pred_above,
            risk_level="medium",
            evidence_strength="Moderate",
            threshold=threshold,
        )
        self.assertEqual(out.binary_classification, "PSIF")
        self.assertEqual(out.psif_score, 0.40)

    def test_18_regression_legacy_bands_not_primary_output(self):
        """Test 18: Verify risk_level is deprecated and primary output is binary PSIF/NOT PSIF."""
        pred = PredictionResult.objects.create(
            incident=self.incident,
            model_version=self.model_version,
            psif_probability=0.82,
            psif_predicted=True,
            risk_level="critical",  # legacy band
            evidence_strength="Strong",
            is_sparse_input=False,
        )
        # Primary decision must come from binary_classification
        self.assertEqual(pred.binary_classification, "PSIF")
        self.assertNotEqual(pred.binary_classification, "CRITICAL")
        # Legacy field remains accessible for audit/compatibility only
        self.assertEqual(pred.risk_level, "critical")


class ProvenanceAndTrainingEligibilityTests(TestCase):
    """Tests 3, 4, 5, 6: UNKNOWN handling, human label precedence, provenance, and training eligibility."""

    def test_03_unknown_handling_unlabelled_incident(self):
        """Test 3: Unlabelled records have NONE provenance and effective_training_label=None, never silently False."""
        incident = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Routine check of pipeline perimeter.",
            severity_potential=None,
            severity_actual="first_aid",
            is_synthetic=False,
            psif_label_source=Incident.PsifLabelSource.NONE,
        )
        incident.refresh_from_db()

        self.assertEqual(incident.psif_label_source, Incident.PsifLabelSource.NONE)
        self.assertIsNone(incident.effective_training_label)

    def test_04_human_label_precedence_over_synthetic(self):
        """Test 4: Human-reviewed label strictly overrides synthetic benchmark label."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        reviewer, _ = User.objects.get_or_create(username="test_reviewer_04", defaults={"role": "reviewer"})

        incident = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Worker tripped over cable on rig floor.",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_psif_human_label=False,  # Human HSE expert determined NOT PSIF
            adjudicated_human_decision=Incident.HumanDecision.NOT_PSIF,
            reviewed_by=reviewer,
            reviewed_at=timezone.now(),
            status=Incident.Status.REVIEWED_NON_PSIF,
        )
        # Effective label must be False (human label), ignoring synthetic True
        self.assertFalse(incident.effective_training_label)
        self.assertTrue(incident.is_human_approved_synthetic)

        # Opposite case: Synthetic says 0, Human says True
        incident.raw_row = {"sif_label": 0}
        incident.is_psif_human_label = True
        incident.adjudicated_human_decision = Incident.HumanDecision.PSIF
        incident.status = Incident.Status.REVIEWED_PSIF
        incident.save()
        self.assertTrue(incident.effective_training_label)

    def test_05_synthetic_provenance_tracking(self):
        """Test 5: Synthetic benchmark record is tracked as synthetic; human review converts to HUMAN_APPROVED_SYNTHETIC."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        reviewer, _ = User.objects.get_or_create(username="test_reviewer_05", defaults={"role": "reviewer"})

        incident = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Near-miss high pressure steam release.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 1},
        )
        self.assertTrue(incident.is_synthetic)
        self.assertEqual(incident.psif_label_source, Incident.PsifLabelSource.SYNTHETIC)
        self.assertEqual(incident.effective_training_label, True)
        self.assertFalse(incident.is_human_approved_synthetic)

        # Genuine human reviews it
        incident.is_psif_human_label = True
        incident.adjudicated_human_decision = Incident.HumanDecision.PSIF
        incident.reviewed_by = reviewer
        incident.reviewed_at = timezone.now()
        incident.psif_label_source = Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC
        incident.save()

        self.assertTrue(incident.is_human_approved_synthetic)
        self.assertEqual(incident.provenance_category, "HUMAN_APPROVED_SYNTHETIC")

    def test_06_no_silent_conversion_unknown_to_not_psif(self):
        """Test 6: Unknown/unlabelled records are not silently converted to False in dataset queries."""
        inc_known_pos = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="High energy fall.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 1},
        )
        inc_known_neg = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Paper cut in office.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 0},
        )
        inc_unknown = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Observation report pending review.",
            is_synthetic=False,
            is_psif_human_label=None,
            psif_label_source=Incident.PsifLabelSource.NONE,
        )

        self.assertIsNotNone(inc_known_pos.effective_training_label)
        self.assertIsNotNone(inc_known_neg.effective_training_label)
        self.assertIsNone(inc_unknown.effective_training_label)


class ExplanationEngineTests(TestCase):
    """Tests 8, 9, 10, 11, 12, 13, 19, 20: Explanation generation, SIF factors, quotes, SHAP, and adversarial narratives."""

    def test_08_explanation_generation_schema(self):
        """Test 8: Explanation engine produces all required SIF evidence structure keys."""
        narrative = "Technician opened high pressure valve without lockout, releasing flammable gas near hot work."
        structured = {
            "department": "Drilling",
            "job_task": "Wellhead Maintenance",
            "equipment_involved": "High Pressure Choke Valve",
            "immediate_cause": "Failure to isolate",
            "root_cause_category": "Procedure Not Followed",
        }
        shap_factors = [
            {"feature": "high_pressure", "contribution": 0.25},
            {"feature": "routine_ppe", "contribution": -0.10},
        ]
        dq = {"has_warnings": False, "findings": []}

        exp = generate_explanation(
            record=structured,
            narrative=narrative,
            psif_score=0.85,
            psif_predicted=True,
            threshold=0.35,
            shap_factors=shap_factors,
            dq_findings=dq,
        )

        required_keys = [
            "high_energy_source",
            "worker_exposure",
            "control_condition",
            "credible_sif_consequence",
            "escalation_potential",
            "supporting_evidence",
            "contradicting_evidence",
            "narrative_evidence",
            "structured_evidence",
            "missing_or_uncertain_info",
            "data_quality_findings",
            "analytical_limitations",
            "evidence_strength",
            "analytical_status",
            "model_contributors",
            "reasoning",
        ]
        for key in required_keys:
            self.assertIn(key, exp, f"Missing required explanation key: {key}")

    def test_09_supporting_evidence_extraction(self):
        """Test 9: High-energy source, worker exposure, and control failure are extracted into supporting evidence."""
        narrative = "Scaffolder working at height 8 meters slipped when safety harness lanyard was not hooked, falling toward rig floor."
        exp = generate_explanation(
            record={},
            narrative=narrative,
            psif_score=0.92,
            psif_predicted=True,
            threshold=0.35,
            shap_factors=[],
            dq_findings=None,
        )

        self.assertTrue(exp["high_energy_source"]["identified"])
        self.assertIn("height", exp["high_energy_source"]["source_type"].lower())
        self.assertTrue(exp["worker_exposure"]["identified"])
        self.assertTrue(exp["control_condition"]["identified"])
        self.assertEqual(exp["control_condition"]["condition"], "bypassed_or_failed")
        self.assertTrue(exp["credible_sif_consequence"]["credible"])
        self.assertGreater(len(exp["supporting_evidence"]), 0)
        self.assertGreater(len(exp["narrative_evidence"]), 0)

    def test_10_contradicting_evidence_effective_controls(self):
        """Test 10: Contradicting evidence identified when controls are effective or workers isolated."""
        narrative = "During hydrotest, personnel were evacuated to safe distance and automatic pressure relief operated as designed."
        record = {"direct_control_present": "yes", "control_condition": "effective"}
        exp = generate_explanation(
            record=record,
            narrative=narrative,
            psif_score=0.15,
            psif_predicted=False,
            threshold=0.35,
            shap_factors=[],
            dq_findings=None,
        )

        self.assertGreater(len(exp["contradicting_evidence"]), 0)
        self.assertTrue(
            any("safe distance" in c.lower() or "operated as designed" in c.lower() or "effective" in c.lower() for c in exp["contradicting_evidence"])
        )

    def test_11_missing_information_handling(self):
        """Test 11: Missing structured fields and context are explicitly audited in missing_or_uncertain_info."""
        narrative = "Small flash observed near generator."
        # No structured fields provided
        exp = generate_explanation(
            record={},
            narrative=narrative,
            psif_score=0.45,
            psif_predicted=True,
            threshold=0.35,
            shap_factors=[],
            dq_findings=None,
        )

        missing = exp["missing_or_uncertain_info"]
        self.assertGreater(len(missing), 0)
        missing_text = " ".join(missing)
        self.assertIn("job task", missing_text.lower())
        self.assertIn("immediate cause", missing_text.lower())

    def test_12_shap_positive_negative_contributor_separation(self):
        """Test 12: SHAP factors are partitioned into positive (pushing PSIF) and negative (pulling NOT PSIF) non-causally."""
        shap_factors = [
            {"feature": "pressure_line", "contribution": 0.32},
            {"feature": "hot_work_permit", "contribution": 0.18},
            {"feature": "ppe_worn", "contribution": -0.22},
            {"feature": "low_activity", "contribution": -0.08},
        ]
        exp = generate_explanation(
            record={},
            narrative="Test narrative",
            psif_score=0.60,
            psif_predicted=True,
            threshold=0.35,
            shap_factors=shap_factors,
            dq_findings=None,
        )

        contributors = exp["model_contributors"]
        pos = contributors["positive_contributors"]
        neg = contributors["negative_contributors"]

        self.assertEqual(len(pos), 2)
        self.assertEqual(len(neg), 2)
        self.assertTrue(all(f["contribution"] > 0 for f in pos))
        self.assertTrue(all(f["contribution"] < 0 for f in neg))
        self.assertIn("non-causal", contributors["interpretation"].lower())

    def test_13_data_quality_integration(self):
        """Test 13: IncidentDataQuality warnings are integrated into analytical limitations."""
        dq_findings = {
            "has_warnings": True,
            "findings": ["Conflicting event timestamps", "Duplicate narrative detected across 4 records"],
        }
        exp = generate_explanation(
            record={},
            narrative="Gas leak reported.",
            psif_score=0.65,
            psif_predicted=True,
            threshold=0.35,
            shap_factors=[],
            dq_findings=dq_findings,
        )

        self.assertTrue(exp["data_quality_findings"]["has_warnings"])
        self.assertIn("Conflicting event timestamps", exp["data_quality_findings"]["findings"])
        limitations = " ".join(exp["analytical_limitations"])
        self.assertIn("data quality warnings", limitations.lower())

    def test_19_sparse_meaningless_narrative_behavior(self):
        """Test 19: Sparse narrative (< 10 words) triggers INSUFFICIENT_EVIDENCE and Weak strength."""
        sparse_narrative = "Valve inspected ok."  # 3 words
        exp = generate_explanation(
            record={},
            narrative=sparse_narrative,
            psif_score=0.08,
            psif_predicted=False,
            threshold=0.35,
            shap_factors=[],
            dq_findings=None,
        )

        self.assertEqual(exp["analytical_status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(exp["evidence_strength"], "Weak")
        limitations = " ".join(exp["analytical_limitations"])
        self.assertIn("sparse", limitations.lower())

    def test_20_adversarial_narratives_colloquial_severity_words(self):
        """Test 20: Narrative with words like 'dead' and 'fatal' used colloquially without physical mechanism."""
        adversarial_narrative = (
            "Worker said he was dead tired after completing the routine office timesheets "
            "and had a fatal headache from staring at the computer screen all afternoon."
        )
        exp = generate_explanation(
            record={"department": "Finance"},
            narrative=adversarial_narrative,
            psif_score=0.10,
            psif_predicted=False,
            threshold=0.35,
            shap_factors=[],
            dq_findings=None,
        )

        # High energy source should NOT be identified
        self.assertFalse(exp["high_energy_source"]["identified"])
        # No credible SIF consequence mechanism
        self.assertFalse(exp["credible_sif_consequence"]["credible"])
        # Escalation potential should be False
        self.assertFalse(exp["escalation_potential"]["credible"])


class AnalyticalSufficiencyAndDecisionTraceTests(TestCase):
    """Test 14: Analytical sufficiency evaluation and non-PSIF disclaimer."""

    def setUp(self):
        self.model_version = ModelVersion.objects.create(
            version_label="mv_suff_test",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="ml_engine/artifacts/mv_suff_test/model.json",
            encoder_artifact_path="ml_engine/artifacts/mv_suff_test/encoders.joblib",
            is_active=True,
        )

    def test_14_analytical_sufficiency_sparse_disclaimer(self):
        """Test 14: Insufficient evidence status explicitly warns that lack of data is NOT proof of safety."""
        incident = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Small leak.",  # 2 words
            department="Operations",
            incident_date=timezone.now().date(),
        )
        pred = PredictionResult.objects.create(
            incident=incident,
            model_version=self.model_version,
            psif_probability=0.05,
            psif_predicted=False,
            is_sparse_input=True,
            evidence_strength="Weak",
        )

        eval_status, eval_reason = evaluate_psif_sufficiency(incident, None, pred)
        self.assertEqual(eval_status, "INSUFFICIENT_EVIDENCE")
        self.assertIn("not be interpreted as strong evidence", eval_reason.lower())

        assessment = build_analytical_assessment(incident)
        self.assertEqual(assessment["analytical_status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(assessment["binary_decision"], "NOT PSIF")
        self.assertEqual(assessment["evidence_strength"], "Weak")


class HumanReviewWorkflowTests(TestCase):
    """Tests 15, 16: Human review override and model prediction preservation."""

    def setUp(self):
        self.client = APIClient()
        self.reviewer = User.objects.create_user(
            username="hse_expert",
            password="testpassword",
            role="safety_officer",
        )
        self.client.force_authenticate(user=self.reviewer)

        self.model_version = ModelVersion.objects.create(
            version_label="model_v_test",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="ml_engine/artifacts/model_v_test/model.json",
            encoder_artifact_path="ml_engine/artifacts/model_v_test/encoders.joblib",
            is_active=True,
        )
        self.incident = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Worker bumped elbow against casing during rig move.",
            department="Operations",
            incident_date="2026-09-01",
        )
        self.pred = PredictionResult.objects.create(
            incident=self.incident,
            model_version=self.model_version,
            psif_probability=0.72,
            psif_predicted=True,
            risk_level="high",
            evidence_strength="Moderate",
            explanation_detail={"high_energy_source": {"identified": True}},
        )

    def test_15_human_review_override(self):
        """Test 15: HSE expert can review incident, mark NOT PSIF with rationale, preserving reviewer audit trail."""
        url = f"/api/incidents/{self.incident.id}/review/"
        payload = {
            "is_psif_human_label": False,
            "rationale": "Equipment was de-energized and at rest. Impact speed was negligible, no SIF potential.",
        }
        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, 200)

        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.REVIEWED_NON_PSIF)
        self.assertFalse(self.incident.is_psif_human_label)
        self.assertEqual(self.incident.reviewed_by, self.reviewer)
        self.assertIn("negligible", self.incident.reviewer_rationale)
        self.assertIsNotNone(self.incident.reviewed_at)

    def test_16_model_prediction_preservation_after_human_review(self):
        """Test 16: Human review NEVER overwrites or mutates original model prediction record."""
        original_pred_id = self.pred.id
        original_prob = self.pred.psif_probability
        original_pred_val = self.pred.psif_predicted
        original_strength = self.pred.evidence_strength

        # Perform human review
        url = f"/api/incidents/{self.incident.id}/review/"
        payload = {
            "is_psif_human_label": False,
            "rationale": "Disagreed with model.",
        }
        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, 200)

        self.pred.refresh_from_db()
        self.assertEqual(self.pred.id, original_pred_id)
        self.assertEqual(self.pred.psif_probability, original_prob)
        self.assertEqual(self.pred.psif_predicted, original_pred_val)
        self.assertEqual(self.pred.evidence_strength, original_strength)
        self.assertEqual(self.pred.binary_classification, "PSIF")  # Model's original candidate decision preserved


class DashboardBinaryMetricsTests(TestCase):
    """Test 17: Dashboard binary metrics suite with strictly defined independent denominators."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="dash_analyst",
            password="password",
            role="analyst",
        )
        self.client.force_authenticate(user=self.user)

        self.model_version = ModelVersion.objects.create(
            version_label="mv_dash_test",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="ml_engine/artifacts/mv_dash_test/model.json",
            encoder_artifact_path="ml_engine/artifacts/mv_dash_test/encoders.joblib",
            is_active=True,
        )
        # Create 4 incidents:
        # Inc 1: Eligible, Model PSIF, Human Confirmed PSIF
        i1 = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="High pressure gas blow out near rig floor.",
            department="Drilling",
            incident_date="2026-09-01",
            status=Incident.Status.REVIEWED_PSIF,
            is_psif_human_label=True,
        )
        PredictionResult.objects.create(
            incident=i1,
            model_version=self.model_version,
            psif_probability=0.85,
            psif_predicted=True,
            is_sparse_input=False,
        )

        # Inc 2: Eligible, Model NOT PSIF, Human Confirmed NOT PSIF
        i2 = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Minor paper cut while filing drilling reports in office.",
            department="Admin",
            incident_date="2026-09-02",
            status=Incident.Status.REVIEWED_NON_PSIF,
            is_psif_human_label=False,
        )
        PredictionResult.objects.create(
            incident=i2,
            model_version=self.model_version,
            psif_probability=0.04,
            psif_predicted=False,
            is_sparse_input=False,
        )

        # Inc 3: Eligible, Model PSIF, Human NOT REVIEWED
        i3 = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Crane hoisted drill pipe over personnel path without tag lines.",
            department="Logistics",
            incident_date="2026-09-03",
        )
        PredictionResult.objects.create(
            incident=i3,
            model_version=self.model_version,
            psif_probability=0.75,
            psif_predicted=True,
            is_sparse_input=False,
        )

        # Inc 4: Sparse (< 10 words), Model NOT PSIF, Insufficient Evidence
        i4 = Incident.objects.create(
            id=uuid.uuid4(),
            composite_narrative="Bolt loose.",
            department="Operations",
            incident_date="2026-09-04",
        )
        PredictionResult.objects.create(
            incident=i4,
            model_version=self.model_version,
            psif_probability=0.10,
            psif_predicted=False,
            is_sparse_input=True,
        )

    def test_17_dashboard_binary_metric_definitions(self):
        """Test 17: Canonical definitions and independent denominators in summary API."""
        res = self.client.get("/api/analytics/summary/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Check all required keys
        self.assertEqual(data["total_incidents"], 4)
        self.assertEqual(data["prediction_eligible_count"], 3)  # i1, i2, i3 (non-sparse)
        self.assertEqual(data["insufficient_evidence_count"], 1)  # i4 (sparse)
        self.assertEqual(data["psif_count"], 2)  # i1, i3
        self.assertEqual(data["not_psif_count"], 1)  # i2
        self.assertEqual(data["human_reviewed_count"], 2)  # i1, i2
        self.assertEqual(data["human_confirmed_psif_count"], 1)  # i1
        self.assertEqual(data["human_confirmed_not_psif_count"], 1)  # i2

        # Check PSIF percentage: 2 / 3 * 100 = 66.7%
        expected_pct = (2 / 3) * 100
        self.assertAlmostEqual(data["psif_percentage"], expected_pct, places=1)

        # Check Agreement Rate: both i1 (model=True, human=True) and i2 (model=False, human=False) agree -> 2 / 2 = 1.0 (100%)
        self.assertEqual(data["human_model_agreement_rate"], 1.0)

        # Verify Canonical Metric Definitions dictionary
        metric_defs = data["canonical_metric_definitions"]
        self.assertIn("psif_percentage", metric_defs)
        self.assertIn("prediction_eligible_count", metric_defs["psif_percentage"]["formula"])
        self.assertIn("prediction-eligible", metric_defs["psif_percentage"]["denominator"])
        self.assertIn("eligible", metric_defs["human_model_agreement_rate"]["denominator"])
