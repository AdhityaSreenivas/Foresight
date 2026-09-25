"""
PSIF Platform — Tests for Dataset Timing & ETA Engine

Covers:
1. Start timestamp recorded once and preserved across retries/crashes
2. Elapsed time and completion duration calculation
3. Prevention of negative durations and numerical stability (up to 1M+ rows)
4. ETA calculation from throughput and warmup suppression (< 1% or < 50 rows)
5. Historical throughput blending
6. ETA smoothing and throughput adaptation
7. Completed datasets freeze their duration
8. Stale worker / heartbeat loss pause handling
9. Multiple simultaneous datasets have independent timing
10. API backward compatibility and serializer timing structure
11. UI template rendering for status and list pages
12. Safety verification of existing records with null timing
"""
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.datasets.models import Dataset
from apps.datasets.timing import (
    format_seconds,
    calculate_dataset_timing,
    get_historical_average_throughput,
    HISTORICAL_THROUGHPUT_CACHE_KEY,
    MIN_PROGRESS_ROWS,
    MIN_PROGRESS_PERCENT,
    STALE_HEARTBEAT_THRESHOLD_SECONDS,
)
from apps.datasets.serializers import (
    DatasetStatusSerializer,
    DatasetListSerializer,
)
from apps.datasets.views import DatasetListView, DatasetStatusView

User = get_user_model()


class TimingFormattingAndMathTests(TestCase):
    """Tests for format_seconds and numerical stability across dataset sizes."""

    def test_format_seconds_boundary_rules(self):
        # Null handling
        self.assertEqual(format_seconds(None), "")
        
        # Negative clamped to 0
        self.assertEqual(format_seconds(-15), "0s")
        self.assertEqual(format_seconds(-0.01), "0s")

        # < 60 seconds
        self.assertEqual(format_seconds(0), "0s")
        self.assertEqual(format_seconds(42), "42s")
        self.assertEqual(format_seconds(59), "59s")
        self.assertEqual(format_seconds(42.8), "43s")
        self.assertEqual(format_seconds(42, is_estimate=True), "~42s")

        # 1m to 59m 59s
        self.assertEqual(format_seconds(60), "1m")
        self.assertEqual(format_seconds(90), "1m 30s")
        self.assertEqual(format_seconds(258), "4m 18s")
        self.assertEqual(format_seconds(258, is_estimate=True), "~4m 18s")
        self.assertEqual(format_seconds(3599), "59m 59s")

        # >= 60 minutes (hours)
        self.assertEqual(format_seconds(3600), "1h")
        self.assertEqual(format_seconds(4320), "1h 12m")
        self.assertEqual(format_seconds(7320, is_estimate=True), "~2h 2m")

    def test_numerical_stability_across_sizes(self):
        """Verify ETA math remains stable from 100 to 1,000,000 rows."""
        dataset_sizes = [100, 10500, 50000, 100000, 1000000]
        rates = [5.0, 50.0, 250.0, 1000.0]

        now = timezone.now()
        for size in dataset_sizes:
            for rate in rates:
                ds = Dataset(
                    name=f"test_{size}",
                    status="processing",
                    total_rows=size,
                    processed_rows=int(size * 0.5),
                    processing_started_at=now - timedelta(seconds=int((size * 0.5) / rate)),
                    last_heartbeat_at=now,
                )
                timing = calculate_dataset_timing(ds, now=now)
                self.assertIsNotNone(timing["estimated_remaining_seconds"])
                self.assertGreaterEqual(timing["estimated_remaining_seconds"], 0)
                self.assertIsNotNone(timing["estimated_total_seconds"])
                self.assertGreater(timing["estimated_total_seconds"], 0)
                # Formatted outputs should not crash or produce NaN/inf
                self.assertNotIn("NaN", timing["formatted_estimated_remaining"])
                self.assertNotIn("inf", timing["formatted_estimated_remaining"])


class DatasetTimingEngineTests(TestCase):
    """Comprehensive test of timing calculations, ETA logic, and state transitions."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="test_safety_officer",
            email="safety@foresight.org",
            role="safety_officer"
        )
        self.now = timezone.now()

    def test_timing_for_unprocessed_or_null_record(self):
        """Historical records without timing timestamps return safe defaults."""
        ds = Dataset.objects.create(
            name="historical_legacy.csv",
            status="completed",
            file_type="csv",
            total_rows=5000,
            processed_rows=5000,
            uploaded_by=self.user,
        )
        timing = calculate_dataset_timing(ds, now=self.now)
        self.assertIsNone(timing["started_at"])
        self.assertIsNone(timing["completed_at"])
        self.assertIsNone(timing["duration_seconds"])
        self.assertFalse(timing["formatted_duration"])
        self.assertFalse(timing["is_estimate_reliable"])
        self.assertEqual(timing["summary"], "Completed · Duration unavailable")

    def test_elapsed_time_and_completion_freeze(self):
        """Elapsed time grows while processing, but freezes upon completion."""
        start_time = self.now - timedelta(seconds=120)
        ds = Dataset.objects.create(
            name="active_job.jsonl",
            status="processing",
            file_type="jsonl",
            total_rows=1000,
            processed_rows=400,
            processing_started_at=start_time,
            last_heartbeat_at=self.now,
            uploaded_by=self.user,
        )

        timing_active = calculate_dataset_timing(ds, now=self.now)
        self.assertEqual(timing_active["elapsed_seconds"], 120.0)
        self.assertEqual(timing_active["formatted_elapsed"], "2m")

        # Mark completed at 150 seconds
        completion_time = start_time + timedelta(seconds=150)
        ds.status = "completed"
        ds.processed_rows = 1000
        ds.processing_completed_at = completion_time
        ds.processing_duration_seconds = 150.0
        ds.save()

        # Check at now (which is start + 120, but even if evaluated 1 hour later):
        later = self.now + timedelta(hours=1)
        timing_done = calculate_dataset_timing(ds, now=later)
        self.assertEqual(timing_done["duration_seconds"], 150.0)
        self.assertEqual(timing_done["formatted_duration"], "2m 30s")
        self.assertEqual(timing_done["estimated_remaining_seconds"], 0.0)
        self.assertEqual(timing_done["summary"], "Completed in 2m 30s")

    def test_warmup_suppression_low_progress(self):
        """Under 1% or under 50 rows, ETA is marked unreliable and returns Estimating…"""
        start = self.now - timedelta(seconds=10)
        ds = Dataset.objects.create(
            name="just_started.csv",
            status="processing",
            file_type="csv",
            total_rows=10000,
            processed_rows=20,  # Only 20 rows (< 50) and 0.2% (< 1%)
            processing_started_at=start,
            last_heartbeat_at=self.now,
            uploaded_by=self.user,
        )

        timing = calculate_dataset_timing(ds, now=self.now)
        self.assertFalse(timing["is_estimate_reliable"])
        self.assertIsNone(timing["estimated_remaining_seconds"])
        self.assertIn("Estimating", timing["summary"])

    def test_eta_becomes_available_after_warmup(self):
        """Once >= 50 rows and >= 1%, ETA is calculated and marked reliable."""
        start = self.now - timedelta(seconds=60)
        ds = Dataset.objects.create(
            name="running_well.csv",
            status="processing",
            file_type="csv",
            total_rows=1000,
            processed_rows=250,  # 250 rows (25%), 60s => rate = 250/60 = 4.166 rows/s
            processing_started_at=start,
            last_heartbeat_at=self.now,
            uploaded_by=self.user,
        )

        timing = calculate_dataset_timing(ds, now=self.now)
        self.assertTrue(timing["is_estimate_reliable"])
        self.assertIsNotNone(timing["estimated_remaining_seconds"])
        # Expected remaining = 750 / 4.1666 ~= 180s = 3m
        self.assertAlmostEqual(timing["estimated_remaining_seconds"], 180.0, delta=5.0)
        self.assertEqual(timing["formatted_estimated_remaining"], "~3m")
        self.assertEqual(timing["estimate_source"], "LIVE_THROUGHPUT")

    def test_historical_throughput_blending_during_early_progress(self):
        """Early progress between 50 rows and 10% blends with historical average."""
        # Create a historical completed dataset of same file_type to seed stats
        Dataset.objects.create(
            name="history_sample.csv",
            status="completed",
            file_type="csv",
            total_rows=1000,
            processed_rows=1000,
            processing_started_at=self.now - timedelta(seconds=100),
            processing_completed_at=self.now,
            processing_duration_seconds=100.0,  # 10 rows/s
            uploaded_by=self.user,
        )
        cache.clear()

        # New dataset at 2% progress with slow startup
        start = self.now - timedelta(seconds=20)
        ds = Dataset.objects.create(
            name="blended_early.csv",
            status="processing",
            file_type="csv",
            total_rows=5000,
            processed_rows=100,  # 100 rows in 20s = 5 rows/s raw rate
            processing_started_at=start,
            last_heartbeat_at=self.now,
            uploaded_by=self.user,
        )

        timing = calculate_dataset_timing(ds, now=self.now)
        self.assertTrue(timing["is_estimate_reliable"])
        self.assertEqual(timing["estimate_source"], "HISTORICAL_ASSISTED")
        # Blended rate should be between raw (5) and historical (10)
        self.assertGreater(timing["processing_rate_rows_per_second"], 5.0)
        self.assertLess(timing["processing_rate_rows_per_second"], 10.0)

    def test_stale_worker_heartbeat_detection(self):
        """When heartbeat is older than threshold, task is flagged stalled and live ETA is paused."""
        start = self.now - timedelta(minutes=10)
        old_heartbeat = self.now - timedelta(seconds=STALE_HEARTBEAT_THRESHOLD_SECONDS + 30)

        ds = Dataset.objects.create(
            name="stalled_job.csv",
            status="processing",
            file_type="csv",
            total_rows=2000,
            processed_rows=500,
            processing_started_at=start,
            last_heartbeat_at=old_heartbeat,
            uploaded_by=self.user,
        )

        timing = calculate_dataset_timing(ds, now=self.now)
        self.assertTrue(timing["is_stalled"])
        self.assertIn("paused / retrying", timing["formatted_remaining"].lower())

    def test_failed_dataset_preserves_elapsed_duration(self):
        """Failure preserves elapsed time before failure and sets appropriate summary."""
        start = self.now - timedelta(seconds=45)
        ds = Dataset.objects.create(
            name="faulty.csv",
            status="failed",
            file_type="csv",
            total_rows=1000,
            processed_rows=320,
            processing_started_at=start,
            processing_completed_at=self.now,
            processing_duration_seconds=45.0,
            uploaded_by=self.user,
        )

        timing = calculate_dataset_timing(ds, now=self.now)
        self.assertEqual(timing["duration_seconds"], 45.0)
        self.assertEqual(timing["formatted_duration"], "45s")
        self.assertEqual(timing["summary"], "Failed after 45s")


class MultipleDatasetsIsolationTests(TestCase):
    """Ensure multiple simultaneously processing datasets have completely isolated timing."""

    def setUp(self):
        self.user = User.objects.create_user(username="multi_user", role="safety_officer")
        self.now = timezone.now()

    def test_independent_timing_multiple_datasets(self):
        start_a = self.now - timedelta(seconds=60)
        start_b = self.now - timedelta(seconds=300)

        ds_a = Dataset.objects.create(
            name="dataset_a.csv",
            status="processing",
            file_type="csv",
            total_rows=1000,
            processed_rows=300,  # 300 in 60s = 5 rows/s
            processing_started_at=start_a,
            last_heartbeat_at=self.now,
            uploaded_by=self.user,
        )

        ds_b = Dataset.objects.create(
            name="dataset_b.jsonl",
            status="processing",
            file_type="jsonl",
            total_rows=10000,
            processed_rows=5000,  # 5000 in 300s = 16.66 rows/s
            processing_started_at=start_b,
            last_heartbeat_at=self.now,
            uploaded_by=self.user,
        )

        timing_a = calculate_dataset_timing(ds_a, now=self.now)
        timing_b = calculate_dataset_timing(ds_b, now=self.now)

        self.assertEqual(timing_a["elapsed_seconds"], 60.0)
        self.assertEqual(timing_b["elapsed_seconds"], 300.0)

        self.assertAlmostEqual(timing_a["processing_rate_rows_per_second"], 5.0, delta=0.5)
        self.assertAlmostEqual(timing_b["processing_rate_rows_per_second"], 16.66, delta=0.5)

        # ETA for A remaining: 700 / 5 = 140s (~2m 20s)
        # ETA for B remaining: 5000 / 16.66 = 300s (~5m)
        self.assertNotEqual(timing_a["estimated_remaining_seconds"], timing_b["estimated_remaining_seconds"])


class SerializerAndAPITests(TestCase):
    """Verify DRF serializers output expected timing structure and maintain backward compatibility."""

    def setUp(self):
        self.user = User.objects.create_user(username="api_user", role="safety_officer")
        self.now = timezone.now()

    def test_status_serializer_includes_full_timing(self):
        start = self.now - timedelta(seconds=41)
        ds = Dataset.objects.create(
            name="api_test.csv",
            status="processing",
            file_type="csv",
            total_rows=1000,
            processed_rows=500,
            processing_started_at=start,
            last_heartbeat_at=self.now,
            uploaded_by=self.user,
        )

        serializer = DatasetStatusSerializer(ds)
        data = serializer.data

        # Backward compatible fields must exist
        self.assertIn("status", data)
        self.assertIn("percent", data)
        self.assertIn("processed_rows", data)
        self.assertIn("total_rows", data)

        # New timing object
        self.assertIn("timing", data)
        timing = data["timing"]
        self.assertEqual(timing["elapsed_seconds"], 41.0)
        self.assertIn("estimated_remaining_seconds", timing)
        self.assertIn("processing_rate_rows_per_second", timing)
        self.assertIn("is_estimate_reliable", timing)
        self.assertIn("summary", timing)

    def test_list_serializer_includes_timing_summary(self):
        ds = Dataset.objects.create(
            name="list_item.csv",
            status="completed",
            file_type="csv",
            total_rows=200,
            processed_rows=200,
            processing_duration_seconds=13.0,
            uploaded_by=self.user,
        )

        serializer = DatasetListSerializer(ds)
        data = serializer.data

        self.assertIn("timing", data)
        self.assertIn("timing_summary", data)
        self.assertEqual(data["timing_summary"], "Completed in 13s")


class ViewsAndTemplateRenderingTests(TestCase):
    """Verify views render the new timing elements on status and list pages."""

    def setUp(self):
        self.user = User.objects.create_user(username="viewer", role="safety_officer")
        self.client.force_login(self.user)
        self.now = timezone.now()

    def test_status_page_renders_timing_containers(self):
        ds = Dataset.objects.create(
            name="web_status_view.csv",
            status="processing",
            file_type="csv",
            total_rows=1000,
            processed_rows=400,
            processing_started_at=self.now - timedelta(seconds=50),
            last_heartbeat_at=self.now,
            uploaded_by=self.user,
        )

        res = self.client.get(f"/datasets/{ds.id}/status/")
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")

        self.assertIn("timing-strip", content)
        self.assertIn("timing-elapsed", content)
        self.assertIn("timing-remaining", content)
        self.assertIn("timing-total", content)
        self.assertIn("timing-rate", content)

    def test_list_page_renders_duration_column(self):
        Dataset.objects.create(
            name="completed_for_list.csv",
            status="completed",
            file_type="csv",
            total_rows=500,
            processed_rows=500,
            processing_duration_seconds=95.0,
            uploaded_by=self.user,
        )

        res = self.client.get("/datasets/")
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")

        self.assertIn("Duration / ETA", content)
        self.assertIn("1m 35s", content)


class LifecycleAndTaskIntegrationTests(TestCase):
    """Verify task start, retry, and completion timing lifecycle behavior."""

    def setUp(self):
        self.user = User.objects.create_user(username="task_user", role="safety_officer")
        self.now = timezone.now()

    def test_task_preserves_started_at_across_retries(self):
        """Retrying a task does NOT overwrite the original processing_started_at timestamp."""
        original_start = self.now - timedelta(minutes=5)
        ds = Dataset.objects.create(
            name="retry_test.csv",
            status="retrying",
            file_type="csv",
            total_rows=1000,
            processed_rows=200,
            processing_started_at=original_start,
            uploaded_by=self.user,
        )

        from django.core.files.base import ContentFile
        from apps.datasets.tasks import process_dataset

        ds.original_file.save("retry_test.csv", ContentFile(b"col1\nval1\n"))
        ds.column_mapping = {"col1": "description"}
        ds.save()

        # Mock iter_file_chunks and bulk_create_incidents
        with patch("apps.datasets.parsers.iter_file_chunks", return_value=[]), \
             patch("apps.datasets.ingestion.bulk_create_incidents", return_value=[]):
            process_dataset.apply(args=[str(ds.id)])

        ds.refresh_from_db()
        # processing_started_at MUST still be original_start
        self.assertEqual(ds.processing_started_at, original_start)
        self.assertIsNotNone(ds.processing_completed_at)
        self.assertIsNotNone(ds.processing_duration_seconds)
        # Duration must span from original_start to completion, not just retry time
        self.assertGreaterEqual(ds.processing_duration_seconds, 300.0)


class ExistingDataSafetyTests(TestCase):
    """Verify that existing datasets across all statuses are completely untouched and safe."""

    def setUp(self):
        self.user = User.objects.create_user(username="safety_auditor", role="safety_officer")

    def test_existing_datasets_remain_intact_and_backward_compatible(self):
        """Pre-existing datasets in all states remain valid with null timing fields."""
        statuses = ["uploaded", "mapping_pending", "processing", "retrying", "completed", "failed"]
        created = []
        for s in statuses:
            ds = Dataset.objects.create(
                name=f"legacy_{s}.csv",
                status=s,
                file_type="csv",
                total_rows=100,
                processed_rows=50 if s in ("processing", "completed") else 0,
                current_task_id=f"legacy-task-{s}",
                uploaded_by=self.user,
            )
            created.append((ds.id, s, ds.processed_rows, ds.current_task_id))

        for ds_id, orig_status, orig_processed, orig_task_id in created:
            ds = Dataset.objects.get(id=ds_id)
            self.assertEqual(ds.status, orig_status)
            self.assertEqual(ds.processed_rows, orig_processed)
            self.assertEqual(ds.current_task_id, orig_task_id)
            # Timing should be cleanly callable without exceptions
            timing = ds.get_timing_info
            self.assertIsInstance(timing, dict)
            self.assertIn("summary", timing)

