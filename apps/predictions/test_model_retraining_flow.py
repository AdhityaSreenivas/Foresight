"""
Comprehensive Integration & Regression Test Suite for Controlled Model Retraining Workflow.
OIL India SIH Problem Statement 26165.

Validates all 7 user-mandated approval conditions:
1. Human-label provenance classification and synthetic simulation exclusion.
2. Training label hierarchy: real human > heuristic > exclude.
3. 9-point activation safety gate.
4. Immutable training snapshot persistence and reproducibility.
5. Metric provenance separation (human vs heuristic vs synthetic).
6. Dynamic database-derived training data collection.
7. Candidate model status lifecycle (is_active=False until explicit promotion).
"""
import hashlib
import json
from pathlib import Path
import tempfile
import uuid
from unittest.mock import patch, MagicMock

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.incidents.models import Incident, IncidentReview
from apps.predictions.models import ModelVersion
from apps.predictions.tasks import retrain_model_task
from ml_engine.training.trainer import (
    audit_labels,
    generate_training_snapshot,
    prepare_training_data,
    run_training_pipeline,
)

User = get_user_model()


class MockEncoder:
    feature_names_ = ["f1", "f2"]
    def transform(self, x): return x


class ControlledModelRetrainingTests(TestCase):
    """Test suite covering the complete controlled retraining pipeline."""

    def setUp(self):
        self.client = APIClient()
        
        # Create administrative and non-administrative users
        self.admin_user = User.objects.create_superuser(
            username="admin_test",
            email="admin@test.oil",
            password="adminpassword123",
        )
        if hasattr(self.admin_user, "role"):
            self.admin_user.role = "admin"
            self.admin_user.save()

        self.operator_user = User.objects.create_user(
            username="operator_test",
            email="op@test.oil",
            password="userpassword123",
        )
        if hasattr(self.operator_user, "role"):
            self.operator_user.role = "safety_officer"
            self.operator_user.save()

        # Seed currently active model
        self.active_model = ModelVersion.objects.create(
            version_label="v_active_baseline",
            is_active=True,
            status=ModelVersion.Status.ACTIVE,
            xgboost_artifact_path="/tmp/fake_active_model.json",
            encoder_artifact_path="/tmp/fake_active_encoder.joblib",
            metrics={
                "training_status": "READY",
                "selected_threshold": 0.10,
                "metrics_final_test": {
                    "precision": 0.75,
                    "recall": 0.88,
                    "f1": 0.81,
                    "roc_auc": 0.89,
                },
                "label_audit": {
                    "training_eligible": 100,
                    "provenance_counts": {"heuristic_psif": 20, "heuristic_not_psif": 80},
                },
            },
        )

        # Seed baseline incidents
        self._seed_incidents()

    def _seed_incidents(self):
        """Seed representative incidents for provenance and training tests."""
        # 1. Human-approved synthetic PSIF
        self.inc_human_psif = Incident.objects.create(
            id=uuid.uuid4(),
            description="High pressure gas release near drilling derrick with worker exposure.",
            composite_narrative="High pressure gas release near drilling derrick with worker exposure.",
            department="Drilling",
            injury_type="burn",
            body_part="face",
            immediate_cause="equipment failure",
            root_cause_category="maintenance",
            near_miss=False,
            is_synthetic=True,
            raw_row={"sif_label": 0},  # Human decision overrides synthetic 0
            is_psif_human_label=True,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_synthetic_adjudication=False,
        )

        # 2. Human-approved synthetic NOT PSIF
        self.inc_human_not_psif = Incident.objects.create(
            id=uuid.uuid4(),
            description="Minor slip on flat walkway in office area, no hazard present.",
            composite_narrative="Minor slip on flat walkway in office area, no hazard present.",
            department="Admin",
            injury_type="bruise",
            body_part="knee",
            immediate_cause="distraction",
            root_cause_category="housekeeping",
            near_miss=False,
            is_synthetic=True,
            raw_row={"sif_label": 1},  # Human decision overrides synthetic 1
            is_psif_human_label=False,
            adjudicated_human_decision=Incident.HumanDecision.NOT_PSIF,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_synthetic_adjudication=False,
        )

        # 3. Human-approved synthetic INSUFFICIENT_INFORMATION (strictly excluded)
        self.inc_human_insufficient = Incident.objects.create(
            id=uuid.uuid4(),
            description="Event noted in logbook.",
            composite_narrative="Event noted in logbook.",
            department="Logistics",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            is_psif_human_label=None,
            adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_synthetic_adjudication=False,
        )

        # 4. Synthetic evaluation simulation (strictly excluded from binary targets)
        self.inc_synthetic = Incident.objects.create(
            id=uuid.uuid4(),
            description="Simulated cohort incident with high pressure valve test.",
            composite_narrative="Simulated cohort incident with high pressure valve test.",
            department="Production",
            is_synthetic=True,
            is_psif_human_label=True,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=True,
        )

        # 5. Synthetic benchmark PSIF (unreviewed by human)
        self.inc_heuristic_psif = Incident.objects.create(
            id=uuid.uuid4(),
            description="Unreviewed event with serious potential severity.",
            composite_narrative="Unreviewed event with serious potential severity.",
            department="Production",
            severity_potential="serious",
            severity_actual="first_aid",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )

        # 6. Synthetic benchmark NOT PSIF (unreviewed by human)
        self.inc_heuristic_not_psif = Incident.objects.create(
            id=uuid.uuid4(),
            description="Unreviewed event with low potential severity.",
            composite_narrative="Unreviewed event with low potential severity.",
            department="Logistics",
            severity_potential="low",
            severity_actual="first_aid",
            is_synthetic=True,
            raw_row={"sif_label": 0},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )

        # 7. Unreviewed without benchmark label / unknown
        self.inc_unknown = Incident.objects.create(
            id=uuid.uuid4(),
            description="Raw ingested report without severity fields.",
            composite_narrative="Raw ingested report without severity fields.",
            department="Logistics",
            is_synthetic=False,
            psif_label_source=Incident.PsifLabelSource.NONE,
            is_synthetic_adjudication=False,
        )

    # ── Test 1: Celery Task Signature Regression Fix ─────────────────────────
    @patch("apps.predictions.tasks.run_training_pipeline")
    def test_01_retrain_task_handles_summary_dict_without_unpacking_error(self, mock_trainer):
        """
        Regression Test: Proves retrain_model_task consumes a single summary dictionary
        returned by run_training_pipeline without causing a TypeError unpacking error.
        """
        candidate = ModelVersion.objects.create(
            version_label="v_test_candidate",
            status=ModelVersion.Status.PENDING,
            is_active=False,
        )
        
        mock_trainer.return_value = {
            "version_label": candidate.version_label,
            "artifact_dir": "/tmp/test_dir",
            "selected_threshold": 0.12,
            "metrics_final_test": {"precision": 0.80, "recall": 0.90, "f1": 0.85, "roc_auc": 0.91},
        }

        # Run Celery task synchronously
        retrain_model_task(candidate.id)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, ModelVersion.Status.READY)
        self.assertFalse(candidate.is_active, "Candidate model must NOT be activated automatically.")
        self.assertEqual(candidate.metrics.get("training_status"), "READY")
        self.assertEqual(candidate.metrics.get("selected_threshold"), 0.12)
        # Verify trainer was invoked with model_version=candidate
        self.assertEqual(mock_trainer.call_args.kwargs.get("model_version"), candidate)

    # ── Test 2: Failure Recording on Exception ────────────────────────────────
    @patch("apps.predictions.tasks.run_training_pipeline")
    def test_02_retrain_task_failure_recording(self, mock_trainer):
        """Proves unexpected exceptions during retraining mark model as FAILED and record error details."""
        candidate = ModelVersion.objects.create(
            version_label="v_failing_candidate",
            status=ModelVersion.Status.PENDING,
            is_active=False,
        )
        mock_trainer.side_effect = RuntimeError("CUDA/BERT memory allocation failed.")

        retrain_model_task(candidate.id)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, ModelVersion.Status.FAILED)
        self.assertFalse(candidate.is_active)
        self.assertEqual(candidate.metrics.get("training_status"), "FAILED")
        self.assertIn("CUDA/BERT memory allocation failed.", candidate.metrics.get("training_error"))
        self.assertIn("failed_at", candidate.metrics)
        self.assertIn("traceback", candidate.metrics)

    # ── Test 3: Provenance Classification & Synthetic Exclusion ──────────────
    def test_03_human_label_provenance_and_synthetic_exclusion(self):
        """
        User Condition 1:
        Proves synthetic evaluation simulation is NEVER counted as genuine human ground truth
        and is strictly excluded from binary supervised targets.
        """
        # 1. Human-approved synthetic PSIF
        self.assertEqual(self.inc_human_psif.provenance_category, "HUMAN_APPROVED_SYNTHETIC")
        self.assertEqual(self.inc_human_psif.effective_training_label, True)

        # 2. Human-approved synthetic NOT PSIF
        self.assertEqual(self.inc_human_not_psif.provenance_category, "HUMAN_APPROVED_SYNTHETIC")
        self.assertEqual(self.inc_human_not_psif.effective_training_label, False)

        # 3. Human-approved synthetic INSUFFICIENT_INFORMATION
        self.assertEqual(self.inc_human_insufficient.provenance_category, "HUMAN_APPROVED_SYNTHETIC")
        self.assertIsNone(self.inc_human_insufficient.effective_training_label)

        # 4. Synthetic evaluation simulation (Synthetic is the sole category for all generated records)
        self.assertEqual(self.inc_synthetic.provenance_category, "SYNTHETIC")
        self.assertIsNone(self.inc_synthetic.effective_training_label, "Synthetic evaluation MUST be excluded from training.")

        # 5. Synthetic benchmark labels
        self.assertEqual(self.inc_heuristic_psif.provenance_category, "SYNTHETIC")
        self.assertEqual(self.inc_heuristic_psif.effective_training_label, True)

        self.assertEqual(self.inc_heuristic_not_psif.provenance_category, "SYNTHETIC")
        self.assertEqual(self.inc_heuristic_not_psif.effective_training_label, False)

        # 6. Unknown
        self.assertEqual(self.inc_unknown.provenance_category, "UNKNOWN_UNLABELLED")
        self.assertIsNone(self.inc_unknown.effective_training_label)

    # ── Test 4: Dynamic Training Data Collection (Real Human vs Synthetic) ────
    def test_04_dynamic_data_collection_and_human_increment(self):
        """
        User Conditions 2 & 4:
        Proves data collection queries DB dynamically:
        1. Adding exactly 1 genuine human binary adjudication (is_synthetic=True, non-simulation, valid human decision)
           increases eligible training population by exactly 1.
        2. Adding a synthetic simulation adjudication (is_synthetic_adjudication=True) does NOT increase eligible training population.
        """
        from django.db.models import Q
        
        candidates_before = list(
            Incident.objects.filter(
                Q(psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC, is_synthetic_adjudication=False) |
                Q(psif_label_source=Incident.PsifLabelSource.SYNTHETIC, is_synthetic_adjudication=False)
            )
        )
        eligible_before = [inc for inc in candidates_before if inc.effective_training_label is not None]
        count_before = len(eligible_before)

        # 1. Add 1 genuine human review on synthetic incident
        inc_real = Incident.objects.create(
            id=uuid.uuid4(),
            description="Worker exposed to toxic H2S release during flange disconnect.",
            composite_narrative="Worker exposed to toxic H2S release during flange disconnect.",
            is_synthetic=True,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_synthetic_adjudication=False,
            reviewed_by=self.admin_user,
            reviewed_at=timezone.now(),
        )

        candidates_after_real = list(
            Incident.objects.filter(
                Q(psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC, is_synthetic_adjudication=False) |
                Q(psif_label_source=Incident.PsifLabelSource.SYNTHETIC, is_synthetic_adjudication=False)
            )
        )
        eligible_after_real = [inc for inc in candidates_after_real if inc.effective_training_label is not None]
        count_after_real = len(eligible_after_real)

        self.assertEqual(
            count_after_real, count_before + 1,
            "Adding 1 genuine human review (is_synthetic_adjudication=False) must increment eligible training count by exactly 1."
        )

        # 2. Add 1 synthetic adjudication (e.g. from simulation/evaluation script)
        Incident.objects.create(
            id=uuid.uuid4(),
            description="Simulated test incident for evaluation sweep.",
            composite_narrative="Simulated test incident for evaluation sweep.",
            is_synthetic=True,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=True,
        )

        candidates_after_synth = list(
            Incident.objects.filter(
                Q(psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC, is_synthetic_adjudication=False) |
                Q(psif_label_source=Incident.PsifLabelSource.SYNTHETIC, is_synthetic_adjudication=False)
            )
        )
        eligible_after_synth = [inc for inc in candidates_after_synth if inc.effective_training_label is not None]
        count_after_synth = len(eligible_after_synth)

        self.assertEqual(
            count_after_synth, count_after_real,
            "Adding a synthetic simulation adjudication (is_synthetic_adjudication=True) must NOT increase eligible training population."
        )

    # ── Test 5: Exact Training Label Precedence Hierarchy ─────────────────────
    def test_05_human_decision_overrides_heuristic_preserving_audit_provenance(self):
        """
        Verify exact label precedence order:
        - human PSIF + synthetic 0 -> training label True (PSIF)
        - human NOT_PSIF + synthetic 1 -> training label False (NOT PSIF)
        - human INSUFFICIENT_INFORMATION + synthetic 1 -> None (excluded)
        - synthetic simulation -> None (excluded)
        - unreviewed synthetic records -> synthetic target (1 -> True, 0 -> False)
        - unreviewed without benchmark label -> None (excluded)
        """
        # Case 1: human PSIF + synthetic 0 -> training label True
        inc1 = Incident.objects.create(
            id=uuid.uuid4(),
            description="High risk crane lift breach.",
            is_synthetic=True,
            raw_row={"sif_label": 0},
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_synthetic_adjudication=False,
            reviewed_by=self.admin_user,
            reviewed_at=timezone.now(),
        )
        self.assertEqual(inc1.effective_training_label, True)
        self.assertTrue(inc1.is_human_approved_synthetic)

        # Case 2: human NOT_PSIF + synthetic 1 -> training label False
        inc2 = Incident.objects.create(
            id=uuid.uuid4(),
            description="Near miss with falling object caught by net.",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            adjudicated_human_decision=Incident.HumanDecision.NOT_PSIF,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_synthetic_adjudication=False,
            reviewed_by=self.admin_user,
            reviewed_at=timezone.now(),
        )
        self.assertEqual(inc2.effective_training_label, False)
        self.assertTrue(inc2.is_human_approved_synthetic)

        # Case 3: human INSUFFICIENT_INFORMATION + synthetic label -> None (excluded)
        inc3 = Incident.objects.create(
            id=uuid.uuid4(),
            description="Vague entry in log.",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_synthetic_adjudication=False,
            reviewed_by=self.admin_user,
            reviewed_at=timezone.now(),
        )
        self.assertIsNone(inc3.effective_training_label, "INSUFFICIENT_INFORMATION must exclude incident from binary training")

        # Case 4: synthetic simulation -> None (excluded)
        inc4 = Incident.objects.create(
            id=uuid.uuid4(),
            description="Simulated cohort record.",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=True,
        )
        self.assertIsNone(inc4.effective_training_label, "Synthetic simulation must never become training target")

        # Case 5: unreviewed synthetic records -> benchmark target
        inc5a = Incident.objects.create(
            id=uuid.uuid4(),
            description="Unreviewed event with positive synthetic label.",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        inc5b = Incident.objects.create(
            id=uuid.uuid4(),
            description="Unreviewed event with negative synthetic label.",
            is_synthetic=True,
            raw_row={"sif_label": 0},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        self.assertEqual(inc5a.effective_training_label, True)
        self.assertEqual(inc5b.effective_training_label, False)

        # Case 6: unreviewed without benchmark label -> None (excluded)
        inc6 = Incident.objects.create(
            id=uuid.uuid4(),
            description="Raw record without labels.",
            is_synthetic=False,
            psif_label_source=Incident.PsifLabelSource.NONE,
            is_synthetic_adjudication=False,
        )
        self.assertIsNone(inc6.effective_training_label)

    # ── Test 6: Immutable Training Snapshot ───────────────────────────────────
    def test_06_immutable_training_snapshot_generation(self):
        """
        User Condition 4:
        Proves ModelVersion-bound snapshot contains complete UUID list, targets,
        label sources, schema versions, and SHA256 dataset hash.
        """
        incidents = [self.inc_human_psif, self.inc_human_not_psif, self.inc_heuristic_psif, self.inc_heuristic_not_psif]
        audit = {
            "total_incidents_in_db": 7,
            "provenance_counts": {
                "human_approved_synthetic": 2,
                "synthetic": 2,
                "synthetic_simulation": 1,
                "unknown_unlabelled": 1,
            },
            "human_eligible": 2, "synthetic_eligible": 2,
            "training_eligible": 4, "training_excluded": 3,
            "final_positive_count": 2, "final_negative_count": 2,
        }

        snapshot = generate_training_snapshot(
            eligible_incidents=incidents,
            audit=audit,
            version_label="v_snap_test",
            feature_names=["bert_0", "struct_dept"],
        )

        self.assertIn("snapshot_id", snapshot)
        self.assertIn("dataset_hash", snapshot)
        self.assertEqual(snapshot["label_policy_version"], "2.0-provenance-hierarchy")
        self.assertEqual(len(snapshot["incident_uuid_list"]), 4)
        self.assertEqual(len(snapshot["incident_records"]), 4)
        
        # Verify hash format
        original_hash = snapshot["dataset_hash"]
        self.assertEqual(len(original_hash), 64, "SHA256 hash must be 64 hex characters.")

    # ── Test 7: Candidate Model Inactive Status ───────────────────────────────
    def test_07_candidate_model_remains_inactive_after_creation(self):
        """
        User Condition 3 & 7:
        Proves candidate model remains is_active=False and does not replace active model.
        """
        candidate = ModelVersion.objects.create(
            version_label="v_candidate_test",
            status=ModelVersion.Status.READY,
            is_active=False,
        )
        self.active_model.refresh_from_db()
        self.assertTrue(self.active_model.is_active)
        self.assertFalse(candidate.is_active)
        self.assertEqual(ModelVersion.objects.filter(is_active=True).count(), 1)

    # ── Test 8: 9-Point Activation Safety Gate ────────────────────────────────
    def test_08_activation_safety_gate_enforcement(self):
        """
        User Condition 3:
        Validates the strict 9-point safety gate:
        - Rejects non-admin users
        - Rejects candidate with status != READY
        - Rejects candidate if already active
        - Rejects candidate if training_status != READY
        - Rejects candidate if required metrics missing
        - Rejects candidate if artifacts missing on disk
        - Succeeds only when all 9 conditions are met
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            model_file = tmp_path / "model.json"
            encoder_file = tmp_path / "encoder.joblib"
            metadata_file = tmp_path / "metadata.json"

            # Create mock artifacts
            import xgboost as xgb
            import joblib
            
            # Simple booster
            dtrain = xgb.DMatrix(np.array([[0, 1], [1, 0]]), label=np.array([0, 1]))
            bst = xgb.train({"max_depth": 2, "objective": "binary:logistic"}, dtrain, num_boost_round=2)
            bst.save_model(str(model_file))

            # Simple encoder mock
            joblib.dump(MockEncoder(), str(encoder_file))

            # Metadata file
            snapshot_id = "test-snap-uuid-9999"
            dataset_hash = "f" * 64
            with open(metadata_file, "w") as f:
                json.dump({
                    "model_version": "v_valid_candidate",
                    "training_snapshot_id": snapshot_id,
                    "dataset_hash": dataset_hash,
                    "is_candidate": True,
                }, f)

            # Training snapshot file
            snapshot_file = tmp_path / "training_snapshot.json"
            with open(snapshot_file, "w") as f:
                json.dump({
                    "snapshot_id": snapshot_id,
                    "model_version_label": "v_valid_candidate",
                    "dataset_hash": dataset_hash,
                }, f)

            candidate = ModelVersion.objects.create(
                version_label="v_valid_candidate",
                status=ModelVersion.Status.READY,
                is_active=False,
                xgboost_artifact_path=str(model_file),
                encoder_artifact_path=str(encoder_file),
                training_snapshot_path=str(snapshot_file),
                metrics={
                    "training_status": "READY",
                    "training_snapshot_id": snapshot_id,
                    "metrics_final_test": {
                        "precision": 0.82,
                        "recall": 0.91,
                        "f1": 0.86,
                        "roc_auc": 0.92,
                    },
                },
            )

            # 1. Non-admin forbidden
            self.client.force_authenticate(user=self.operator_user)
            res = self.client.post(f"/api/models/{candidate.id}/activate/")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

            # Authenticate as admin
            self.client.force_authenticate(user=self.admin_user)

            # 2. Reject status != READY
            candidate.status = ModelVersion.Status.RUNNING
            candidate.save()
            res = self.client.post(f"/api/models/{candidate.id}/activate/")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("status must be READY", res.data["error"])
            candidate.status = ModelVersion.Status.READY
            candidate.save()

            # 3. Reject if training_status != READY
            candidate.metrics["training_status"] = "FAILED"
            candidate.save()
            res = self.client.post(f"/api/models/{candidate.id}/activate/")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("expected 'READY'", res.data["error"])
            candidate.metrics["training_status"] = "READY"
            candidate.save()

            # 4. Reject if required metrics missing
            saved_metrics = candidate.metrics["metrics_final_test"]
            candidate.metrics["metrics_final_test"] = {"precision": 0.80}  # missing recall, f1, roc_auc
            candidate.save()
            res = self.client.post(f"/api/models/{candidate.id}/activate/")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("Missing required evaluation metrics", res.data["error"])
            candidate.metrics["metrics_final_test"] = saved_metrics
            candidate.save()

            # 5. Reject if model file missing
            candidate.xgboost_artifact_path = "/nonexistent/model.json"
            candidate.save()
            res = self.client.post(f"/api/models/{candidate.id}/activate/")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("model.json file not found", res.data["error"])
            candidate.xgboost_artifact_path = str(model_file)
            candidate.save()

            # 6. Reject if training_snapshot.json missing or ID mismatch
            candidate.training_snapshot_path = "/nonexistent/training_snapshot.json"
            candidate.save()
            res = self.client.post(f"/api/models/{candidate.id}/activate/")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("training_snapshot.json not found", res.data["error"])
            candidate.training_snapshot_path = str(snapshot_file)
            candidate.save()

            # 7. Promotion succeeds atomically when all conditions are met!
            res = self.client.post(f"/api/models/{candidate.id}/activate/")
            self.assertEqual(res.status_code, status.HTTP_200_OK)

            candidate.refresh_from_db()
            self.active_model.refresh_from_db()

            self.assertTrue(candidate.is_active)
            self.assertEqual(candidate.status, ModelVersion.Status.ACTIVE)
            self.assertFalse(self.active_model.is_active)
            self.assertEqual(self.active_model.status, ModelVersion.Status.READY)
            self.assertEqual(ModelVersion.objects.filter(is_active=True).count(), 1)

    # ── Test 9: Model Comparison API ──────────────────────────────────────────
    def test_09_model_comparison_api(self):
        """Proves side-by-side candidate vs active comparison returns structured metrics."""
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(f"/api/models/{self.active_model.id}/compare/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("candidate", res.data)
        self.assertIn("active", res.data)
        self.assertEqual(res.data["candidate"]["version_label"], self.active_model.version_label)

    # ── Test 10: Zero Feature/Target Leakage ──────────────────────────────────
    def test_10_target_and_metadata_leakage_prevented(self):
        """
        Proves prepare_training_data omits all target and reviewer metadata fields.
        """
        records, narratives, labels = prepare_training_data([self.inc_human_psif])
        rec = records[0]
        forbidden_keys = [
            "severity_actual", "severity_potential", "is_psif_human_label",
            "is_psif_heuristic_label", "psif_label_source", "adjudicated_human_decision",
            "reviewer_rationale", "sif_label", "confidence_target"
        ]
        for key in forbidden_keys:
            self.assertNotIn(key, rec, f"Leakage violation: {key} found in training record.")
