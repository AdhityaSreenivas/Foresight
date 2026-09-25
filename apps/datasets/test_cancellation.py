"""
PSIF Platform — Tests for Dataset Upload / Processing Cancellation

Covers all 10 core cancellation test cases:
1. Pending dataset can be safely discarded.
2. Cancel request on processing dataset changes state correctly.
3. Celery task detects cancellation request.
4. Task stops at safe checkpoint.
5. Cancel is idempotent.
6. Cancellation race with completion is handled correctly.
7. Existing committed chunks remain intact (no data loss).
8. Completed dataset cannot be canceled.
9. Retry/cancel interaction is safe.
10. Active unrelated dataset is untouched.
"""
import uuid
import tempfile
import os
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.datasets.models import Dataset
from apps.incidents.models import Incident
from apps.datasets.tasks import (
    process_dataset,
    is_cancellation_requested,
    finalize_dataset_cancellation,
)
from apps.datasets.recovery import check_and_recover_dataset

User = get_user_model()


class DatasetCancellationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="safety_officer_test",
            email="safety@example.com",
            role="safety_officer",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _create_test_file(self, content="header1,header2\nval1,val2\n"):
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
        tmp.write(content)
        tmp.flush()
        tmp.close()
        return tmp.name

    def tearDown(self):
        pass

    # ── Test 1: Pending dataset can be safely discarded ───────────────────────
    def test_01_pending_dataset_can_be_safely_discarded(self):
        file_path = self._create_test_file()
        try:
            ds = Dataset.objects.create(
                name="Pending Dataset",
                uploaded_by=self.user,
                file_type="csv",
                status=Dataset.Status.MAPPING_PENDING,
                total_rows=10,
            )
            ds.original_file.name = file_path
            ds.save()

            url = f"/api/datasets/{ds.id}/"
            resp = self.client.delete(url)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertFalse(Dataset.objects.filter(id=ds.id).exists())
        finally:
            if os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except OSError:
                    pass

    # ── Test 2: Cancel request on processing dataset changes state ────────────
    @patch("apps.datasets.recovery.is_task_actively_running", return_value=True)
    def test_02_cancel_request_on_processing_dataset_changes_state(self, mock_running):
        ds = Dataset.objects.create(
            name="Processing Dataset",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            current_task_id="task-test-123",
            total_rows=1000,
            processed_rows=250,
            chunks_processed=1,
            processing_started_at=timezone.now(),
        )

        url = f"/api/datasets/{ds.id}/cancel/"
        resp = self.client.post(url, format="json")

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(resp.data["status"], "cancel_requested")
        self.assertIn("checkpoint", resp.data["message"].lower())

        ds.refresh_from_db()
        self.assertTrue(ds.cancel_requested)
        self.assertEqual(ds.status, Dataset.Status.CANCEL_REQUESTED)
        self.assertEqual(ds.recovery_state, "cancel_requested")

    # ── Test 3: Celery task detects cancellation request ──────────────────────
    def test_03_celery_task_detects_cancellation_request(self):
        ds = Dataset.objects.create(
            name="Cancel Detect Dataset",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.CANCEL_REQUESTED,
            cancel_requested=True,
            total_rows=500,
            processed_rows=100,
        )

        # is_cancellation_requested returns True
        self.assertTrue(is_cancellation_requested(str(ds.id)))

        # When process_dataset runs, it immediately detects cancellation and finalizes
        result = process_dataset(str(ds.id))
        self.assertEqual(result["status"], "canceled")
        ds.refresh_from_db()
        self.assertEqual(ds.status, Dataset.Status.CANCELED)
        self.assertIsNotNone(ds.canceled_at)

    # ── Test 4: Task stops at safe checkpoint ─────────────────────────────────
    def test_04_task_stops_at_safe_checkpoint(self):
        ds = Dataset.objects.create(
            name="Checkpoint Dataset",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.CANCEL_REQUESTED,
            cancel_requested=True,
            total_rows=1000,
            processed_rows=250,
            chunks_processed=1,
            processing_started_at=timezone.now(),
        )

        finalize_dataset_cancellation(str(ds.id))
        ds.refresh_from_db()

        self.assertEqual(ds.status, Dataset.Status.CANCELED)
        self.assertEqual(ds.recovery_state, "canceled")
        self.assertEqual(ds.processed_rows, 250)
        self.assertEqual(ds.chunks_processed, 1)
        self.assertIn("cooperatively canceled", ds.error_log)
        self.assertIn("chunk 1", ds.error_log)

    # ── Test 5: Cancel is idempotent ──────────────────────────────────────────
    @patch("apps.datasets.recovery.is_task_actively_running", return_value=True)
    def test_05_cancel_is_idempotent(self, mock_running):
        ds = Dataset.objects.create(
            name="Idempotent Dataset",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            current_task_id="task-idemp-1",
            total_rows=1000,
            processed_rows=500,
        )

        url = f"/api/datasets/{ds.id}/cancel/"
        
        # First call: transitions to cancel_requested
        resp1 = self.client.post(url, format="json")
        self.assertEqual(resp1.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(resp1.data["status"], "cancel_requested")

        # Second call while cancel_requested: returns 200 OK with cancel_requested
        resp2 = self.client.post(url, format="json")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.data["status"], "cancel_requested")

        # Third call after finalized to CANCELED: returns 200 OK with canceled
        finalize_dataset_cancellation(str(ds.id))
        resp3 = self.client.post(url, format="json")
        self.assertEqual(resp3.status_code, status.HTTP_200_OK)
        self.assertEqual(resp3.data["status"], "canceled")

    # ── Test 6: Cancellation race with completion ─────────────────────────────
    def test_06_cancellation_race_with_completion(self):
        ds = Dataset.objects.create(
            name="Race Dataset",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.COMPLETED,
            total_rows=1000,
            processed_rows=1000,
            completed_at=timezone.now(),
        )

        # Even if cancel_requested flag was somehow set, finalize must not overwrite COMPLETED
        result = finalize_dataset_cancellation(str(ds.id))
        self.assertEqual(result["status"], "completed")

        ds.refresh_from_db()
        self.assertEqual(ds.status, Dataset.Status.COMPLETED)

        # API should reject cancel on already completed dataset
        url = f"/api/datasets/{ds.id}/cancel/"
        resp = self.client.post(url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already completed", resp.data["detail"])

    # ── Test 7: Existing committed chunks remain intact ───────────────────────
    def test_07_existing_committed_chunks_remain_intact(self):
        ds = Dataset.objects.create(
            name="Committed Chunk Dataset",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            total_rows=1000,
            processed_rows=250,
            chunks_processed=1,
            quality_summary={"accepted": 240, "accepted_with_warnings": 10, "rejected": 0},
            processing_started_at=timezone.now(),
        )

        # Create committed incident rows for this dataset
        inc1 = Incident.objects.create(
            dataset=ds,
            incident_date=timezone.now().date(),
            description="Incident in chunk 1",
            status="investigation",
        )
        inc2 = Incident.objects.create(
            dataset=ds,
            incident_date=timezone.now().date(),
            description="Incident in chunk 1 second",
            status="investigation",
        )

        finalize_dataset_cancellation(str(ds.id))
        ds.refresh_from_db()

        # Check incidents are still preserved
        self.assertEqual(ds.incidents.count(), 2)
        self.assertEqual(ds.processed_rows, 250)
        self.assertEqual(ds.chunks_processed, 1)
        self.assertEqual(ds.quality_summary["accepted"], 240)

        # Attempt to discard via DELETE must be rejected because incidents exist
        del_resp = self.client.delete(f"/api/datasets/{ds.id}/")
        self.assertEqual(del_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("existing incident records", del_resp.data["detail"])
        self.assertTrue(Dataset.objects.filter(id=ds.id).exists())

    # ── Test 8: Completed dataset cannot be canceled ──────────────────────────
    def test_08_completed_dataset_cannot_be_canceled(self):
        ds = Dataset.objects.create(
            name="Protected Completed Dataset",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.COMPLETED,
            total_rows=500,
            processed_rows=500,
        )

        resp = self.client.post(f"/api/datasets/{ds.id}/cancel/", format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        ds.refresh_from_db()
        self.assertEqual(ds.status, Dataset.Status.COMPLETED)

    # ── Test 9: Retry / Cancel interaction is safe ────────────────────────────
    @patch("apps.datasets.tasks.process_dataset.delay")
    def test_09_retry_cancel_interaction_is_safe(self, mock_delay):
        mock_task = MagicMock()
        mock_task.id = "retry-task-new-456"
        mock_delay.return_value = mock_task

        ds = Dataset.objects.create(
            name="Canceled Retried Dataset",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.CANCELED,
            cancel_requested=True,
            canceled_at=timezone.now(),
            total_rows=1000,
            processed_rows=500,
            chunks_processed=2,
            column_mapping={"col1": "description"},
        )

        # Trigger retry endpoint
        url = f"/api/datasets/{ds.id}/retry/"
        resp = self.client.post(url, format="json")
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        ds.refresh_from_db()
        # cancel_requested should be cleared, status set to RETRYING, checkpoints preserved
        self.assertFalse(ds.cancel_requested)
        self.assertIsNone(ds.canceled_at)
        self.assertEqual(ds.status, Dataset.Status.RETRYING)
        self.assertEqual(ds.chunks_processed, 2)
        self.assertEqual(ds.processed_rows, 500)
        self.assertEqual(ds.current_task_id, "retry-task-new-456")

    # ── Test 10: Active unrelated dataset is untouched ────────────────────────
    @patch("apps.datasets.recovery.is_task_actively_running", return_value=True)
    def test_10_active_unrelated_dataset_is_untouched(self, mock_running):
        ds_a = Dataset.objects.create(
            name="Dataset A (To Cancel)",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            current_task_id="task-a",
            total_rows=1000,
            processed_rows=300,
        )
        ds_b = Dataset.objects.create(
            name="Dataset B (Unrelated Active)",
            uploaded_by=self.user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            current_task_id="task-b",
            total_rows=2000,
            processed_rows=800,
            chunks_processed=3,
        )

        # Cancel Dataset A
        self.client.post(f"/api/datasets/{ds_a.id}/cancel/", format="json")

        ds_a.refresh_from_db()
        ds_b.refresh_from_db()

        self.assertTrue(ds_a.cancel_requested)
        self.assertEqual(ds_a.status, Dataset.Status.CANCEL_REQUESTED)

        # Dataset B must be completely untouched
        self.assertFalse(ds_b.cancel_requested)
        self.assertEqual(ds_b.status, Dataset.Status.PROCESSING)
        self.assertEqual(ds_b.processed_rows, 800)
        self.assertEqual(ds_b.chunks_processed, 3)
        self.assertEqual(ds_b.current_task_id, "task-b")
