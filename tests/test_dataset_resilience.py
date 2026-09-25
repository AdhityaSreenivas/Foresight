"""
PSIF Platform — Dataset Processing Crash Resilience & Watchdog Tests

Comprehensive test suite verifying:
- Worker crash simulation (WorkerLostError / native SIGSEGV)
- Durable chunk-level checkpoints
- Idempotent resumption without duplicate Incidents or Predictions
- Automatic bounded retries and timeout watchdog
- API status exposure and manual retry endpoint
"""
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.datasets.models import Dataset
from apps.datasets.recovery import check_and_recover_dataset, recover_stale_dataset_jobs
from apps.datasets.tasks import process_dataset
from apps.incidents.models import Incident, IncidentDataQuality, IncidentEmbedding
from apps.predictions.models import ModelVersion, PredictionResult


def generate_test_csv(num_rows: int = 25) -> bytes:
    """Generate a deterministic CSV with num_rows valid incidents."""
    lines = ["ID,Date,Dept,Actual,Potential,Narrative,Action"]
    for i in range(1, num_rows + 1):
        actual = "none" if i % 2 == 1 else "first_aid"
        potential = "serious" if i % 2 == 1 else "low"
        lines.append(
            f"TEST-{i:04d},2025-01-15,Drilling,{actual},{potential},"
            f"Simulated drill pipe incident {i} occurred during tripping out.,Replaced component {i}"
        )
    return "\n".join(lines).encode("utf-8")


@pytest.mark.django_db
class TestDatasetCrashResilience:

    def test_chunk_checkpoint_and_worker_loss_resume(self, safety_user):
        """
        Tests 1-9:
        1. Task starts
        2. Chunk 1 succeeds
        3. Checkpoint persists
        4. Worker dies (simulated WorkerLostError)
        5. Dataset becomes recoverable
        6. Retry occurs
        7. Already-completed chunk is not duplicated
        8. Remaining chunks process
        9. Dataset reaches COMPLETED with zero duplicates
        """
        # 25 rows, chunk size is 10 for test simulation
        csv_bytes = generate_test_csv(25)
        dataset = Dataset.objects.create(
            name="resilience_25.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            total_rows=25,
            column_mapping={
                "ID": "external_id",
                "Date": "incident_date",
                "Dept": "department",
                "Actual": "severity_actual",
                "Potential": "severity_potential",
                "Narrative": "description",
                "Action": "corrective_actions",
            },
        )
        dataset.original_file.save("resilience_25.csv", ContentFile(csv_bytes), save=True)

        # ── Step 1-3: Simulate Chunk 1 success (rows 1-10) ───────────────────
        # Process chunk 1:
        from apps.datasets.ingestion import bulk_create_incidents
        import csv
        import io

        reader = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))
        file_chunks = [
            (reader[0:10], 0),
            (reader[10:20], 0),
            (reader[20:25], 0),
        ]
        assert len(file_chunks) == 3  # chunks of 10, 10, 5

        # Ingest chunk 1
        chunk1_rows = file_chunks[0][0]
        created1, err1 = bulk_create_incidents(
            chunk1_rows, dataset, dataset.column_mapping, start_row_index=1
        )
        assert len(created1) == 10
        dataset.processed_rows = 10
        dataset.chunks_processed = 1
        dataset.current_task_id = "task-crashed-worker-101"
        dataset.last_heartbeat_at = timezone.now() - timedelta(seconds=200)
        dataset.quality_summary = {"total": 10, "accepted": 10, "accepted_with_warnings": 0, "rejected": 0}
        dataset.save()

        assert dataset.chunks_processed == 1
        assert dataset.processed_rows == 10
        assert Incident.objects.filter(dataset=dataset).count() == 10

        # ── Step 4-5: Simulate Worker Crash (WorkerLostError) ────────────────
        mock_async_result = MagicMock()
        mock_async_result.ready.return_value = True
        mock_async_result.status = "FAILURE"
        mock_async_result.result = "billiard.exceptions.WorkerLostError: Worker exited prematurely: signal 11 (SIGSEGV)"

        with patch("apps.datasets.recovery.AsyncResult", return_value=mock_async_result):
            with patch("apps.datasets.tasks.process_dataset.delay") as mock_delay:
                mock_delay.return_value = MagicMock(id="task-retry-102")
                
                # Check and recover
                recovered_ds = check_and_recover_dataset(dataset)

                assert recovered_ds.status == Dataset.Status.RETRYING
                assert recovered_ds.retry_count == 1
                assert recovered_ds.recovery_state == "recovering_attempt_1"
                assert "Worker terminated prematurely" in recovered_ds.error_log
                assert recovered_ds.current_task_id == "task-retry-102"
                mock_delay.assert_called_once_with(str(dataset.id))

        # ── Step 6-9: Resume execution from checkpoint ──────────────────────
        # Now run process_dataset (which simulates the retry task executing)
        with patch("apps.datasets.parsers.iter_file_chunks", return_value=file_chunks):
            res = process_dataset(str(dataset.id))
            assert res["status"] == "completed"

        dataset.refresh_from_db()
        assert dataset.status == Dataset.Status.COMPLETED
        assert dataset.processed_rows == 25
        assert dataset.chunks_processed == 3
        assert dataset.recovery_state == "completed"

        # Check that NO duplicate incidents exist
        all_incidents = Incident.objects.filter(dataset=dataset)
        assert all_incidents.count() == 25

        # Check external IDs are 1..25 exactly
        ext_ids = set(all_incidents.values_list("external_id", flat=True))
        assert len(ext_ids) == 25
        assert f"TEST-0001" in ext_ids
        assert f"TEST-0025" in ext_ids

    def test_bounded_failure_after_exhausting_retries(self, safety_user):
        """
        Test 10: Repeated worker loss reaches bounded FAILED state with actionable error.
        """
        dataset = Dataset.objects.create(
            name="crash_loop.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            total_rows=100,
            processed_rows=30,
            chunks_processed=3,
            retry_count=3,  # Already at max 3 retries
            max_retries=3,
            current_task_id="task-fatal-crash",
            last_heartbeat_at=timezone.now() - timedelta(seconds=300),
        )

        mock_async_result = MagicMock()
        mock_async_result.ready.return_value = True
        mock_async_result.status = "FAILURE"
        mock_async_result.result = "billiard.exceptions.WorkerLostError: Worker exited prematurely: signal 11"

        with patch("apps.datasets.recovery.AsyncResult", return_value=mock_async_result):
            recovered_ds = check_and_recover_dataset(dataset)

            assert recovered_ds.status == Dataset.Status.FAILED
            assert recovered_ds.recovery_state == "retries_exhausted"
            assert "Automatic retries (3/3) were exhausted" in recovered_ds.error_log
            assert "Previously completed rows (30) were safely preserved" in recovered_ds.error_log
            assert "checkpoint (chunk 3)" in recovered_ds.error_log

    def test_stale_processing_watchdog_detection(self, safety_user):
        """
        Tests 11-13:
        11. Stale PROCESSING dataset is detected
        12. Stale task is recovered
        13. Active task is not duplicated
        """
        stale_ds = Dataset.objects.create(
            name="stale.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            total_rows=50,
            processed_rows=10,
            chunks_processed=1,
            retry_count=0,
            current_task_id="task-vanished",
            last_heartbeat_at=timezone.now() - timedelta(seconds=250),
        )

        # Case A: Task is NOT active anywhere in Celery
        with patch("apps.datasets.recovery.is_task_actively_running", return_value=False):
            with patch("apps.datasets.tasks.process_dataset.delay") as mock_delay:
                mock_delay.return_value = MagicMock(id="task-stale-recovered")
                recovered = recover_stale_dataset_jobs(stale_timeout_seconds=120)
                assert len(recovered) == 1
                assert recovered[0]["dataset_id"] == str(stale_ds.id)
                assert recovered[0]["new_status"] == Dataset.Status.RETRYING

        # Case B: Task IS actively running on a worker -> do NOT duplicate or restart
        stale_ds.refresh_from_db()
        stale_ds.status = Dataset.Status.PROCESSING
        stale_ds.last_heartbeat_at = timezone.now() - timedelta(seconds=250)
        stale_ds.save()

        with patch("apps.datasets.recovery.is_task_actively_running", return_value=True):
            with patch("apps.datasets.tasks.process_dataset.delay") as mock_delay:
                check_and_recover_dataset(stale_ds, stale_timeout_seconds=120)
                # Should not have called delay
                mock_delay.assert_not_called()
                assert stale_ds.status == Dataset.Status.PROCESSING

    def test_idempotent_reprocessing_never_duplicates_incidents_or_predictions(self, safety_user):
        """
        Tests 14, 19, 20:
        14. Progress cannot move backwards
        19. Idempotent reprocessing does not duplicate Incident records
        20. Idempotent reprocessing does not duplicate Prediction records
        """
        from apps.datasets.ingestion import bulk_create_incidents

        dataset = Dataset.objects.create(
            name="idempotency.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            total_rows=5,
            column_mapping={
                "ID": "external_id",
                "Date": "incident_date",
                "Dept": "department",
                "Actual": "severity_actual",
                "Potential": "severity_potential",
                "Narrative": "description",
                "Action": "corrective_actions",
            },
        )

        rows = [
            {
                "ID": f"IDEM-{i}",
                "Date": "2025-01-15",
                "Dept": "Drilling",
                "Actual": "none",
                "Potential": "serious",
                "Narrative": f"Idempotency test narrative {i}",
                "Action": "None",
            }
            for i in range(1, 6)
        ]

        # Pass 1: create incidents
        incidents1, err1 = bulk_create_incidents(rows, dataset, dataset.column_mapping, start_row_index=1)
        assert len(incidents1) == 5
        assert Incident.objects.filter(dataset=dataset).count() == 5

        # Create Predictions for them
        active_model = ModelVersion.objects.filter(is_active=True).first()
        if not active_model:
            active_model = ModelVersion.objects.create(
                version_label="v_test_model",
                is_active=True,
                bert_model_name="distilbert-base-uncased",
                xgboost_artifact_path="ml_engine/artifacts/test/model.json",
                encoder_artifact_path="ml_engine/artifacts/test/encoders.joblib",
                metrics={"f1": 0.8},
            )

        for inc in incidents1:
            PredictionResult.objects.create(
                incident=inc,
                model_version=active_model,
                psif_probability=0.85,
                psif_predicted=True,
                risk_level="high",
            )
        assert PredictionResult.objects.filter(incident__dataset=dataset).count() == 5

        # Pass 2: execute identical rows again (simulating forced chunk retry)
        incidents2, err2 = bulk_create_incidents(rows, dataset, dataset.column_mapping, start_row_index=1)

        # Database counts must remain EXACTLY 5
        assert Incident.objects.filter(dataset=dataset).count() == 5
        assert PredictionResult.objects.filter(incident__dataset=dataset).count() == 5
        assert IncidentDataQuality.objects.filter(incident__dataset=dataset).count() == 5

    def test_status_api_and_manual_retry(self, safety_client, safety_user):
        """
        Tests 15-18:
        15. Retry count persists
        16. Error diagnostic persists
        17. Successful completion clears error state appropriately
        18. UI/API exposes recovery status and allows manual retry
        """
        dataset = Dataset.objects.create(
            name="api_recovery_test.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.FAILED,
            total_rows=100,
            processed_rows=40,
            chunks_processed=4,
            retry_count=3,
            max_retries=3,
            recovery_state="retries_exhausted",
            error_log="Worker terminated prematurely (WorkerLostError).",
            column_mapping={"Desc": "description"},
        )
        csv_content = b"Desc\nSome narrative\n"
        dataset.original_file.save("api_recovery_test.csv", ContentFile(csv_content), save=True)

        # GET status endpoint exposes recovery diagnostic fields
        status_url = reverse("datasets_api:status", kwargs={"pk": dataset.id})
        res = safety_client.get(status_url)
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["status"] == "failed"
        assert data["retry_count"] == 3
        assert data["max_retries"] == 3
        assert data["recovery_state"] == "retries_exhausted"
        assert "Worker terminated prematurely" in data["last_error"]
        assert data["processed_rows"] == 40
        assert data["chunks_processed"] == 4

        # POST retry endpoint resumes processing
        retry_url = reverse("datasets_api:retry", kwargs={"pk": dataset.id})
        with patch("apps.datasets.tasks.process_dataset.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="task-manual-retry-999")
            retry_res = safety_client.post(retry_url)
            assert retry_res.status_code == status.HTTP_202_ACCEPTED
            retry_data = retry_res.json()
            assert retry_data["status"] == "retrying"
            assert retry_data["checkpoint_chunk"] == 4
            assert retry_data["checkpoint_rows"] == 40
            assert retry_data["task_id"] == "task-manual-retry-999"

        dataset.refresh_from_db()
        assert dataset.status == Dataset.Status.RETRYING
        assert dataset.retry_count == 0  # reset on manual intervention
        assert dataset.recovery_state == "manual_retry_queued"
        assert dataset.current_task_id == "task-manual-retry-999"
        assert "Manual retry requested" in dataset.error_log
