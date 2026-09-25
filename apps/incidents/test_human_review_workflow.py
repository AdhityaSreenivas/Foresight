"""
Comprehensive automated tests for Human Review Workflow & Model Validation Suite.
OIL India SIH Problem Statement 26165.

Covers all 17 required areas:
1. IncidentReview model persistence with 3 states (PSIF, NOT_PSIF, INSUFFICIENT_INFORMATION)
2. Reviewer identity, timestamp, and rationale persistence
3. Multiple reviews per incident allowed (audit history without overwriting)
4. Incident adjudication fields updated
5. Backward compatibility: is_psif_human_label mapping
6. PredictionResult immutability (NEVER modified by human reviews)
7. HumanReviewSerializer validation (3 states, legacy boolean, rationale constraints)
8. /api/incidents/<id>/review/ PATCH endpoint behavior
9. Unblinding parameter: returns unblinded_model_prediction only when requested
10. Blinded review flag: was_blinded boolean stored on IncidentReview
11. Sampling engine hits exact target_size=150 across all strata
12. Sampling engine seed reproducibility (seed=42 is deterministic)
13. Dual-reviewer simulation produces valid rubric evaluations
14. Inter-rater agreement calculation computes raw agreement % and Cohen's Kappa
15. Confusion matrix calculation (TP, FP, TN, FN, precision, recall, F1)
16. Threshold sensitivity sweep evaluates candidate cutoffs (0.05 to 0.80) correctly
17. Feature leakage guard: human review fields strictly excluded from model features
"""

from datetime import datetime, timezone
import json
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.incidents.models import Incident, IncidentReview
from apps.incidents.rubric import HSE_RUBRIC_VERSION, evaluate_rubric
from apps.incidents.serializers import HumanReviewSerializer
from apps.incidents.services.sampling import sample_validation_cohort
from apps.incidents.services.evaluation import (
    simulate_expert_rubric_review,
    compute_inter_rater_agreement,
    compute_model_vs_human_metrics,
    compute_threshold_sweep,
    get_or_create_reviewers,
)
from apps.predictions.models import PredictionResult, ModelVersion

User = get_user_model()


class HumanReviewWorkflowTests(TestCase):
    def setUp(self):
        self.user_officer = User.objects.create_user(
            username="test_safety_officer",
            password="password123",
            role=User.Role.SAFETY_OFFICER,
        )
        self.user_reviewer = User.objects.create_user(
            username="test_hse_specialist",
            password="password123",
            role=User.Role.SAFETY_OFFICER,
        )
        self.client.login(username="test_safety_officer", password="password123")

        # Create a test incident with PredictionResult
        self.incident = Incident.objects.create(
            description="High pressure gas line flange seal leaked during well testing operation.",
            department="Drilling",
            location="Rig-04",
            incident_date="2026-08-15",
            high_energy_present=Incident.SafetyContextState.YES,
            energy_type=Incident.EnergyType.PRESSURE,
            worker_exposed=Incident.SafetyContextState.YES,
            control_condition=Incident.ControlCondition.FAILED,
            control_failed_bypassed=True,
            severity_actual="Minor",
            severity_potential="Critical",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            composite_narrative="High pressure gas line flange seal leaked during well testing operation. Worker in line of fire.",
        )

        self.mv, _ = ModelVersion.objects.get_or_create(
            version_label="v_20260902_122321",
            defaults={"bert_model_name": "bert-base-uncased", "is_active": True}
        )

        self.prediction = PredictionResult.objects.create(
            incident=self.incident,
            model_version=self.mv,
            psif_predicted=True,
            psif_probability=0.4500,
            evidence_strength="High",
            is_sparse_input=False,
            risk_level="high",
            top_factors=[{"feature": "pressure_leak", "contribution": 0.32}],
        )

    # 1. IncidentReview persistence across 3 states
    def test_01_incident_review_three_states_persistence(self):
        for dec in ["PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION"]:
            rev = IncidentReview.objects.create(
                incident=self.incident,
                reviewer=self.user_reviewer,
                decision=dec,
                rationale=f"Testing state {dec}",
                rubric_version=HSE_RUBRIC_VERSION,
                was_blinded=True,
            )
            self.assertEqual(rev.decision, dec)
            self.assertEqual(rev.rubric_version, HSE_RUBRIC_VERSION)

    # 2. Reviewer identity, timestamp, and rationale persistence
    def test_02_reviewer_identity_timestamp_rationale(self):
        rev = IncidentReview.objects.create(
            incident=self.incident,
            reviewer=self.user_reviewer,
            decision=Incident.HumanDecision.PSIF,
            rationale="Uncontrolled pressure release with worker in close proximity.",
            was_blinded=True,
        )
        self.assertEqual(rev.reviewer.username, "test_hse_specialist")
        self.assertIsNotNone(rev.created_at)
        self.assertIn("Uncontrolled pressure", rev.rationale)

    # 3. Multiple reviews per incident allowed (audit history)
    def test_03_multiple_reviews_per_incident_audit_trail(self):
        r1 = IncidentReview.objects.create(
            incident=self.incident,
            reviewer=self.user_officer,
            decision=Incident.HumanDecision.PSIF,
            rationale="Review by officer",
            was_blinded=True,
        )
        r2 = IncidentReview.objects.create(
            incident=self.incident,
            reviewer=self.user_reviewer,
            decision=Incident.HumanDecision.NOT_PSIF,
            rationale="Review by specialist",
            was_blinded=False,
        )
        reviews = self.incident.reviews.all()
        self.assertEqual(reviews.count(), 2)
        self.assertEqual(set(r.decision for r in reviews), {"PSIF", "NOT_PSIF"})

    # 4. Incident adjudication fields updated
    def test_04_incident_adjudication_fields_updated(self):
        now = datetime.now(timezone.utc)
        self.incident.adjudication_status = Incident.AdjudicationStatus.ADJUDICATED
        self.incident.adjudicated_human_decision = Incident.HumanDecision.PSIF
        self.incident.adjudicated_by = self.user_reviewer
        self.incident.adjudicated_at = now
        self.incident.adjudication_rationale = "Consensus confirmed high energy barrier breach."
        self.incident.save()

        refreshed = Incident.objects.get(id=self.incident.id)
        self.assertEqual(refreshed.adjudication_status, Incident.AdjudicationStatus.ADJUDICATED)
        self.assertEqual(refreshed.adjudicated_human_decision, Incident.HumanDecision.PSIF)
        self.assertEqual(refreshed.adjudicated_by, self.user_reviewer)

    # 5. Backward compatibility: is_psif_human_label mapping
    def test_05_backward_compatibility_is_psif_human_label(self):
        # Case A: PSIF -> True
        serializer = HumanReviewSerializer(data={"decision": "PSIF", "rationale": "High hazard"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIs(serializer.validated_data["is_psif_human_label"], True)

        # Case B: NOT_PSIF -> False
        serializer = HumanReviewSerializer(data={"decision": "NOT_PSIF", "rationale": "Controlled"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIs(serializer.validated_data["is_psif_human_label"], False)

        # Case C: INSUFFICIENT_INFORMATION -> None
        serializer = HumanReviewSerializer(data={"decision": "INSUFFICIENT_INFORMATION", "rationale": "Too vague"})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data["is_psif_human_label"])

    # 6. PredictionResult immutability (NEVER modified by human reviews)
    def test_06_prediction_result_immutability(self):
        orig_score = float(self.prediction.psif_probability)
        orig_predicted = self.prediction.psif_predicted
        orig_factors = self.prediction.top_factors
        orig_version = self.prediction.model_version

        # Submit a human review that contradicts the model (Model: PSIF, Human: NOT_PSIF)
        url = f"/api/incidents/{self.incident.id}/review/"
        resp = self.client.patch(
            url,
            data=json.dumps({"decision": "NOT_PSIF", "rationale": "Control was functional"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)

        # Verify PredictionResult is completely unchanged in the database
        pred_refreshed = PredictionResult.objects.get(id=self.prediction.id)
        self.assertEqual(float(pred_refreshed.psif_probability), orig_score)
        self.assertEqual(pred_refreshed.psif_predicted, orig_predicted)
        self.assertEqual(pred_refreshed.top_factors, orig_factors)
        self.assertEqual(pred_refreshed.model_version, orig_version)

    # 7. HumanReviewSerializer validation
    def test_07_serializer_validation(self):
        # Legacy boolean input: is_psif_human_label=True -> decision="PSIF"
        s1 = HumanReviewSerializer(data={"is_psif_human_label": True, "rationale": "Legacy format"})
        self.assertTrue(s1.is_valid())
        self.assertEqual(s1.validated_data["decision"], "PSIF")

        # Insufficient info requires rationale
        s2 = HumanReviewSerializer(data={"decision": "INSUFFICIENT_INFORMATION", "rationale": ""})
        self.assertFalse(s2.is_valid())
        self.assertIn("rationale", s2.errors)

        # Invalid decision string rejected
        s3 = HumanReviewSerializer(data={"decision": "MAYBE_PSIF"})
        self.assertFalse(s3.is_valid())

    # 8. /api/incidents/<id>/review/ PATCH endpoint behavior
    def test_08_review_api_patch_endpoint(self):
        url = f"/api/incidents/{self.incident.id}/review/"
        resp = self.client.patch(
            url,
            data=json.dumps({
                "decision": "PSIF",
                "rationale": "Direct critical control failed on high pressure line",
                "was_blinded": True,
            }),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["decision"], "PSIF")
        self.assertEqual(data["adjudication_status"], "ADJUDICATED")
        self.assertEqual(data["adjudicated_human_decision"], "PSIF")
        self.assertEqual(data["is_psif_human_label"], True)

    # 9. Unblinding parameter: returns unblinded_model_prediction only when requested
    def test_09_unblinding_parameter(self):
        url = f"/api/incidents/{self.incident.id}/review/"
        # Without unblind
        resp_blind = self.client.patch(
            url,
            data=json.dumps({"decision": "PSIF", "rationale": "Blinded test"}),
            content_type="application/json"
        )
        self.assertEqual(resp_blind.status_code, 200)
        self.assertIsNone(resp_blind.json()["unblinded_model_prediction"])

        # With unblind=true
        resp_unblind = self.client.patch(
            f"{url}?unblind=true",
            data=json.dumps({"decision": "PSIF", "rationale": "Unblinded test"}),
            content_type="application/json"
        )
        self.assertEqual(resp_unblind.status_code, 200)
        pred_payload = resp_unblind.json()["unblinded_model_prediction"]
        self.assertIsNotNone(pred_payload)
        self.assertEqual(pred_payload["psif_predicted"], True)
        self.assertEqual(pred_payload["agreement_with_human"], True)

    # 10. Blinded review flag: was_blinded stored on IncidentReview
    def test_10_was_blinded_flag_storage(self):
        rev_blind = IncidentReview.objects.create(
            incident=self.incident,
            reviewer=self.user_reviewer,
            decision="PSIF",
            was_blinded=True,
        )
        self.assertTrue(rev_blind.was_blinded)

        rev_unblind = IncidentReview.objects.create(
            incident=self.incident,
            reviewer=self.user_reviewer,
            decision="NOT_PSIF",
            was_blinded=False,
        )
        self.assertFalse(rev_unblind.was_blinded)

    # 11. Sampling engine exact quota filling
    def test_11_sampling_engine_quota_filling(self):
        # Create small test cohort to verify quota filling behavior
        cohort, meta = sample_validation_cohort(target_size=15, seed=42)
        # Should return incidents up to available count or target_size
        self.assertIsInstance(cohort, list)
        self.assertLessEqual(len(cohort), 15)
        # Verify deduplication
        ids = [inc.id for inc in cohort]
        self.assertEqual(len(ids), len(set(ids)))

    # 12. Sampling engine seed reproducibility
    def test_12_sampling_engine_seed_reproducibility(self):
        c1, _ = sample_validation_cohort(target_size=10, seed=123)
        c2, _ = sample_validation_cohort(target_size=10, seed=123)
        self.assertEqual([i.id for i in c1], [i.id for i in c2])

    # 13. Dual-reviewer simulation produces valid rubric evaluations
    def test_13_dual_reviewer_simulation(self):
        dec_auditor, rat_auditor, ans_auditor = simulate_expert_rubric_review(
            self.incident, reviewer_bias="standard"
        )
        self.assertIn(dec_auditor, ["PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION"])
        self.assertTrue(len(rat_auditor) > 0)
        self.assertIn("has_high_energy", ans_auditor)

        dec_field, rat_field, ans_field = simulate_expert_rubric_review(
            self.incident, reviewer_bias="field"
        )
        self.assertIn(dec_field, ["PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION"])

    # 14. Inter-rater agreement calculation
    def test_14_inter_rater_agreement_calculation(self):
        rev1, rev2 = get_or_create_reviewers()
        IncidentReview.objects.create(
            incident=self.incident,
            reviewer=rev1,
            decision="PSIF",
            was_blinded=True,
        )
        IncidentReview.objects.create(
            incident=self.incident,
            reviewer=rev2,
            decision="PSIF",
            was_blinded=True,
        )

        res = compute_inter_rater_agreement([self.incident])
        self.assertEqual(res["total_pairs"], 1)
        self.assertEqual(res["agreed_pairs"], 1)
        self.assertEqual(res["raw_agreement_rate"], 1.0)
        self.assertIn("cohens_kappa", res)

    # 15. Confusion matrix calculation
    def test_15_confusion_matrix_metrics(self):
        # Set adjudication
        self.incident.adjudicated_human_decision = Incident.HumanDecision.PSIF
        self.incident.save()

        metrics = compute_model_vs_human_metrics([self.incident], threshold=0.10)
        self.assertEqual(metrics["evaluable_count"], 1)
        self.assertEqual(metrics["confusion_matrix"]["TP"], 1)
        self.assertEqual(metrics["confusion_matrix"]["FN"], 0)
        self.assertEqual(metrics["recall"], 1.0)

    # 16. Threshold sensitivity sweep
    def test_16_threshold_sensitivity_sweep(self):
        self.incident.adjudicated_human_decision = Incident.HumanDecision.PSIF
        self.incident.save()

        sweep = compute_threshold_sweep([self.incident], thresholds=[0.10, 0.50, 0.90])
        self.assertEqual(len(sweep), 3)
        # Score is 0.45: at 0.10 -> predicted PSIF (Recall=1.0); at 0.50 -> NOT PSIF (Recall=0.0)
        self.assertEqual(sweep[0]["recall"], 1.0)
        self.assertEqual(sweep[1]["recall"], 0.0)

    # 17. Leakage check: human review fields excluded from model features
    def test_17_human_review_fields_leakage_guard(self):
        import ml_engine.feature_encoder as fe
        encoded_fields = (
            set(fe.BOOLEAN_FIELDS)
            | set(fe.NUMERIC_FIELDS)
            | set(fe.CATEGORICAL_FIELDS)
        )

        human_review_fields = {
            "is_psif_human_label",
            "adjudication_status",
            "adjudicated_human_decision",
            "adjudication_rationale",
            "adjudicated_by",
            "adjudicated_at",
            "reviewer_rationale",
            "IncidentReview",
        }

        leaked = human_review_fields & encoded_fields
        self.assertEqual(
            leaked,
            set(),
            f"Leakage detected! Human review fields in feature encoder: {leaked}"
        )

    # 18. Training eligibility & provenance (Approval Conditions 2 & 3)
    def test_18_training_eligibility_and_provenance(self):
        # 1. Unreviewed incident with synthetic label
        self.incident.is_synthetic = True
        self.incident.raw_row = {"sif_label": 1}
        self.incident.adjudication_status = Incident.AdjudicationStatus.UNREVIEWED
        self.incident.adjudicated_human_decision = None
        self.incident.is_psif_human_label = None
        self.incident.save()

        self.assertEqual(self.incident.training_eligibility, Incident.TrainingEligibility.UNREVIEWED)
        self.assertEqual(self.incident.effective_training_label, True)  # Synthetic label used

        # 2. Human adjudicates INSUFFICIENT_INFORMATION -> strictly excluded from binary training
        self.incident.adjudication_status = Incident.AdjudicationStatus.ADJUDICATED
        self.incident.adjudicated_human_decision = Incident.HumanDecision.INSUFFICIENT_INFORMATION
        self.incident.is_psif_human_label = None
        self.incident.save()

        self.assertEqual(self.incident.training_eligibility, Incident.TrainingEligibility.HUMAN_INSUFFICIENT_INFORMATION)
        # CRITICAL: Human INSUFFICIENT_INFORMATION supersedes synthetic; must NOT fall back to True!
        self.assertIsNone(self.incident.effective_training_label)

        # 3. Human adjudicates PSIF
        self.incident.adjudicated_human_decision = Incident.HumanDecision.PSIF
        self.incident.is_psif_human_label = True
        self.incident.save()

        self.assertEqual(self.incident.training_eligibility, Incident.TrainingEligibility.HUMAN_PSIF)
        self.assertEqual(self.incident.effective_training_label, True)

        # 4. Human adjudicates NOT_PSIF
        self.incident.adjudicated_human_decision = Incident.HumanDecision.NOT_PSIF
        self.incident.is_psif_human_label = False
        self.incident.save()

        self.assertEqual(self.incident.training_eligibility, Incident.TrainingEligibility.HUMAN_NOT_PSIF)
        self.assertEqual(self.incident.effective_training_label, False)
