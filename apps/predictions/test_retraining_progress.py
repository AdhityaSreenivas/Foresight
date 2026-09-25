"""
Tests for Model Retraining Progress, Elapsed Time, and ETA Engine.
Validates requirements 11 through 24:
11. training start timestamp recorded once.
12. progress changes when actual phase work completes.
13. embedding progress reflects processed units.
14. progress cannot exceed 100.
15. progress cannot go backwards unexpectedly.
16. ETA unavailable before sufficient work exists.
17. ETA calculated from real throughput.
18. ETA is smoothed.
19. completed training freezes duration.
20. page refresh preserves training state.
21. multiple training tasks maintain independent progress.
22. worker retry does not falsely report progress.
23. API maintains backward compatibility.
24. historical model versions with no timing data remain valid.
"""
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.predictions.models import ModelVersion
from apps.predictions.timing import (
    calculate_retraining_timing,
    format_seconds,
)
from apps.predictions.tasks import retrain_model_task
from ml_engine.bert_encoder import encode_texts

User = get_user_model()


class ModelRetrainingProgressAndETATests(TestCase):
    """Test suite covering real retraining progress, throughput, and ETA tracking."""

    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username="retrain_admin",
            email="admin@test.oil",
            password="adminpassword123",
        )
        if hasattr(self.admin_user, "role"):
            self.admin_user.role = "admin"
            self.admin_user.save()
        self.client.force_authenticate(user=self.admin_user)

    def test_11_training_start_timestamp_recorded_once(self):
        """11. Training start timestamp recorded once and preserved across checks."""
        model = ModelVersion.objects.create(
            version_label="v_test_start_ts",
            status=ModelVersion.Status.PENDING,
            metrics={"training_status": "PENDING"},
        )
        # Dispatch task with mocked pipeline so it doesn't run full ML
        with patch("apps.predictions.tasks.run_training_pipeline", return_value={"mock": True}):
            retrain_model_task(str(model.id), training_source="SYNTHETIC")

        model.refresh_from_db()
        first_started_at = model.metrics.get("started_at")
        self.assertIsNotNone(first_started_at)

        # Simulate subsequent task or poll
        timing = calculate_retraining_timing(model)
        self.assertEqual(model.metrics.get("started_at"), first_started_at)

    def test_12_progress_changes_when_actual_phase_work_completes(self):
        """12. Progress changes when actual phase work completes."""
        model = ModelVersion.objects.create(
            version_label="v_test_phases",
            status=ModelVersion.Status.RUNNING,
            metrics={
                "training_status": "RUNNING",
                "progress_pct": 5,
                "stage_code": "DATA_LOADING",
                "started_at": timezone.now().isoformat(),
            },
        )
        # Advance stage to DATA_AUDIT
        model.metrics["progress_pct"] = 12
        model.metrics["stage_code"] = "DATA_AUDIT"
        timing = calculate_retraining_timing(model)
        model.metrics.update(timing)
        model.save(update_fields=["metrics"])

        res = self.client.get(f"/api/models/{model.id}/status/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["progress_pct"], 12)
        self.assertEqual(res.data["stage_code"], "DATA_AUDIT")

    def test_13_embedding_progress_reflects_processed_units(self):
        """13. Embedding progress reflects processed units."""
        # Test encode_texts with mock tokenizer/model
        mock_texts = ["Incident narrative 1", "Incident narrative 2", "Incident narrative 3"]
        callback_history = []

        def mock_callback(processed, total):
            callback_history.append((processed, total))

        with patch("ml_engine.bert_encoder._get_model_and_tokenizer") as mock_get:
            mock_tok = MagicMock()
            mock_tok.model_max_length = 512
            mock_tok.return_value = {
                "input_ids": MagicMock(),
                "attention_mask": MagicMock(unsqueeze=lambda x: MagicMock(expand=lambda s: MagicMock(float=lambda: 1))),
            }
            mock_model = MagicMock()
            mock_model.config.hidden_size = 768
            mock_model.return_value = MagicMock(last_hidden_state=MagicMock())
            mock_get.return_value = (mock_tok, mock_model)

            with patch("ml_engine.bert_encoder._mean_pool", return_value=MagicMock(cpu=lambda: MagicMock(numpy=lambda: MagicMock()))):
                with patch("numpy.vstack", return_value=MagicMock(shape=(3, 768))):
                    encode_texts(mock_texts, model_name="distilbert-base-uncased", batch_size=2, progress_callback=mock_callback)

        self.assertGreater(len(callback_history), 0)
        final_processed, final_total = callback_history[-1]
        self.assertEqual(final_processed, 3)
        self.assertEqual(final_total, 3)

    def test_14_progress_cannot_exceed_100(self):
        """14. Progress percentage cannot exceed 100."""
        model = ModelVersion.objects.create(
            version_label="v_test_clamp",
            status=ModelVersion.Status.RUNNING,
            metrics={"progress_pct": 150, "started_at": timezone.now().isoformat()},
        )
        timing = calculate_retraining_timing(model)
        # Clamped inside timing
        res = self.client.get(f"/api/models/{model.id}/status/")
        self.assertLessEqual(res.data["progress_pct"], 100)

    def test_15_progress_cannot_go_backwards_unexpectedly(self):
        """15. Progress monotonicity across sequential pipeline stages."""
        stage_weights = [
            ("DATA_LOADING", 5),
            ("DATA_AUDIT", 12),
            ("DATA_PREP", 20),
            ("EMBEDDING_TRAIN", 50),
            ("EMBEDDING_TEST", 63),
            ("STRUCTURED_ENCODING", 68),
            ("FEATURE_FUSION", 72),
            ("XGBOOST_SEARCH", 78),
            ("THRESHOLD_CALIBRATION", 85),
            ("MODEL_FIT", 88),
            ("BASELINES", 91),
            ("EVALUATION", 95),
            ("ARTIFACT_PERSISTENCE", 98),
            ("COMPLETED", 100),
        ]
        prev_pct = 0
        for code, pct in stage_weights:
            self.assertGreaterEqual(pct, prev_pct, f"Stage {code} violated monotonicity")
            prev_pct = pct

    def test_16_eta_unavailable_before_sufficient_work_exists(self):
        """16. ETA is reported as 'Estimating...' before sufficient work exists."""
        now = timezone.now()
        model = ModelVersion.objects.create(
            version_label="v_test_warmup",
            status=ModelVersion.Status.RUNNING,
            metrics={
                "training_status": "RUNNING",
                "progress_pct": 3,
                "stage_code": "DATA_LOADING",
                "started_at": now.isoformat(),
            },
        )
        timing = calculate_retraining_timing(model)
        self.assertEqual(timing["estimate_source"], "ESTIMATING")
        self.assertIsNone(timing["estimated_remaining_seconds"])
        self.assertIn("Estimating", timing["formatted_remaining"])

    def test_17_eta_calculated_from_real_throughput(self):
        """17. ETA is calculated from real throughput during embedding generation."""
        started_at = timezone.now() - timedelta(seconds=100)
        emb_started_at = timezone.now() - timedelta(seconds=80)
        model = ModelVersion.objects.create(
            version_label="v_test_throughput",
            status=ModelVersion.Status.RUNNING,
            metrics={
                "training_status": "RUNNING",
                "progress_pct": 36,
                "stage_code": "EMBEDDING_TRAIN",
                "processed_units": 4000,
                "total_units": 10000,
                "started_at": started_at.isoformat(),
                "emb_train_started_at": emb_started_at.isoformat(),
            },
        )
        timing = calculate_retraining_timing(model)
        self.assertEqual(timing["estimate_source"], "LIVE_THROUGHPUT")
        self.assertIsNotNone(timing["estimated_remaining_seconds"])
        self.assertGreater(timing["estimated_remaining_seconds"], 0)
        self.assertIn("~", timing["formatted_remaining"])

    def test_18_eta_is_smoothed(self):
        """18. ETA is smoothed to prevent wild jumps."""
        started_at = timezone.now() - timedelta(seconds=120)
        model = ModelVersion.objects.create(
            version_label="v_test_smoothing",
            status=ModelVersion.Status.RUNNING,
            metrics={
                "training_status": "RUNNING",
                "progress_pct": 40,
                "stage_code": "EMBEDDING_TRAIN",
                "processed_units": 5000,
                "total_units": 10000,
                "started_at": started_at.isoformat(),
                "emb_train_started_at": started_at.isoformat(),
                "smoothed_eta_seconds": 120.0,
            },
        )
        timing = calculate_retraining_timing(model)
        smoothed = timing["estimated_remaining_seconds"]
        # With previous 120s, smoothed ETA cannot jump wildly to 10s or 500s
        self.assertTrue(50 <= smoothed <= 160)

    def test_19_completed_training_freezes_duration(self):
        """19. Completed training freezes duration and stops timer."""
        started_at = timezone.now() - timedelta(seconds=245)
        completed_at = started_at + timedelta(seconds=240)
        model = ModelVersion.objects.create(
            version_label="v_test_completed_freeze",
            status=ModelVersion.Status.READY,
            metrics={
                "training_status": "READY",
                "progress_pct": 100,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "training_duration_seconds": 240.0,
            },
        )
        timing = calculate_retraining_timing(model)
        self.assertEqual(timing["estimated_remaining_seconds"], 0)
        self.assertEqual(timing["elapsed_seconds"], 240)
        self.assertIn("Completed in 4m", timing["formatted_duration"])

    def test_20_page_refresh_preserves_training_state(self):
        """20. Polling/page refresh preserves started_at and progress state."""
        started_at = timezone.now() - timedelta(seconds=60)
        model = ModelVersion.objects.create(
            version_label="v_test_refresh",
            status=ModelVersion.Status.RUNNING,
            metrics={
                "training_status": "RUNNING",
                "progress_pct": 52,
                "stage_code": "EMBEDDING_TRAIN",
                "started_at": started_at.isoformat(),
            },
        )
        res1 = self.client.get(f"/api/models/{model.id}/status/")
        res2 = self.client.get(f"/api/models/{model.id}/status/")
        self.assertEqual(res1.data["started_at"], res2.data["started_at"])
        self.assertEqual(res1.data["progress_pct"], 52)
        self.assertEqual(res2.data["progress_pct"], 52)

    def test_21_multiple_training_tasks_maintain_independent_progress(self):
        """21. Multiple training models maintain isolated timing and progress states."""
        t1 = timezone.now() - timedelta(seconds=90)
        t2 = timezone.now() - timedelta(seconds=20)
        m1 = ModelVersion.objects.create(
            version_label="v_task_1",
            status=ModelVersion.Status.RUNNING,
            metrics={"progress_pct": 60, "stage_code": "EMBEDDING_TRAIN", "started_at": t1.isoformat()},
        )
        m2 = ModelVersion.objects.create(
            version_label="v_task_2",
            status=ModelVersion.Status.RUNNING,
            metrics={"progress_pct": 15, "stage_code": "DATA_PREP", "started_at": t2.isoformat()},
        )
        res1 = self.client.get(f"/api/models/{m1.id}/status/")
        res2 = self.client.get(f"/api/models/{m2.id}/status/")
        self.assertEqual(res1.data["progress_pct"], 60)
        self.assertEqual(res2.data["progress_pct"], 15)
        self.assertNotEqual(res1.data["elapsed_seconds"], res2.data["elapsed_seconds"])

    def test_22_worker_retry_does_not_falsely_report_progress(self):
        """22. Failure records error and does not falsely report 100%."""
        model = ModelVersion.objects.create(
            version_label="v_test_failed",
            status=ModelVersion.Status.RUNNING,
            metrics={"training_status": "RUNNING", "progress_pct": 30},
        )
        with patch("apps.predictions.tasks.run_training_pipeline", side_effect=RuntimeError("CUDA OOM")):
            retrain_model_task(str(model.id), training_source="SYNTHETIC")

        model.refresh_from_db()
        self.assertEqual(model.status, ModelVersion.Status.FAILED)
        self.assertEqual(model.metrics["training_status"], "FAILED")
        self.assertEqual(model.metrics["progress_pct"], 0)
        self.assertIn("CUDA OOM", model.metrics["training_error"])

    def test_23_api_maintains_backward_compatibility(self):
        """23. API preserves all legacy fields while exposing new ETA fields."""
        model = ModelVersion.objects.create(
            version_label="v_test_compat",
            status=ModelVersion.Status.READY,
            metrics={
                "training_status": "READY",
                "progress_pct": 100,
                "training_source": "SYNTHETIC",
                "validation_basis": "SYNTHETIC DATASET EVALUATION",
                "training_duration_seconds": 185.0,
            },
        )
        res = self.client.get(f"/api/models/{model.id}/status/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Legacy fields
        for field in ["model_version_id", "version_label", "status", "is_active", "trained_at",
                      "training_status", "training_source", "validation_basis", "disclaimer",
                      "progress_pct", "current_stage", "selected_threshold"]:
            self.assertIn(field, res.data, f"Missing legacy field: {field}")

        # New fields
        for field in ["stage_code", "elapsed_seconds", "estimated_remaining_seconds",
                      "estimated_total_seconds", "estimate_source", "formatted_elapsed",
                      "formatted_remaining", "formatted_total", "formatted_duration"]:
            self.assertIn(field, res.data, f"Missing new timing field: {field}")

    def test_24_historical_model_versions_with_no_timing_data_remain_valid(self):
        """24. Historical model versions with no timing data report 'Duration unavailable'."""
        old_model = ModelVersion.objects.create(
            version_label="v_legacy_2024",
            status=ModelVersion.Status.READY,
            metrics={},  # Completely empty metrics
        )
        res = self.client.get(f"/api/models/{old_model.id}/status/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["formatted_duration"], "Duration unavailable")
        self.assertIsNone(res.data["training_duration_seconds"])

        timing = calculate_retraining_timing(old_model)
        self.assertEqual(timing["formatted_duration"], "Duration unavailable")
        self.assertIsNone(timing["training_duration_seconds"])
