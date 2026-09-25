"""
PSIF Platform — Dataset Processing Watchdog and Crash Recovery Service

Detects and recovers from native-library crashes (SIGSEGV), worker drops
(WorkerLostError), and stalled/dead Celery workers that leave Dataset rows
permanently stuck in 'processing' or 'retrying'.
"""
import logging
from datetime import timedelta
from typing import Optional, Union

from celery import current_app
from celery.result import AsyncResult
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Dataset

logger = logging.getLogger(__name__)

# Default timeout in seconds after which a processing job with no heartbeat is considered stale
DEFAULT_STALE_TIMEOUT_SECONDS = getattr(settings, "DATASET_PROCESSING_STALE_TIMEOUT", 120)
MAX_RECOVERY_RETRIES = getattr(settings, "DATASET_PROCESSING_MAX_RETRIES", 3)


def is_task_actively_running(task_id: str) -> bool:
    """
    Check Celery worker inspect API to see if task_id is actively running on any worker.
    Returns False if task is not in active or reserved lists, or if inspector times out.
    """
    if not task_id or task_id.startswith("sync"):
        return False
    try:
        insp = current_app.control.inspect(timeout=1.0)
        if not insp:
            return False

        active = insp.active() or {}
        for worker, tasks in active.items():
            for t in tasks:
                if t.get("id") == task_id:
                    return True

        reserved = insp.reserved() or {}
        for worker, tasks in reserved.items():
            for t in tasks:
                if t.get("id") == task_id:
                    return True

        return False
    except Exception as exc:
        logger.debug("Failed to inspect active Celery tasks for %s: %s", task_id, exc)
        return False


def check_and_recover_dataset(
    dataset_or_id: Union[Dataset, str],
    stale_timeout_seconds: int = DEFAULT_STALE_TIMEOUT_SECONDS,
) -> Dataset:
    """
    Inspect a single dataset. If it is in PROCESSING or RETRYING status, verify whether
    its Celery worker is still alive. If a WorkerLostError or heartbeat timeout is detected,
    transition into RETRYING (resuming from last durable chunk checkpoint) or FAILED
    (if retries are exhausted).

    Thread-safe and atomic via select_for_update.
    """
    from .tasks import process_dataset

    dataset_id = str(dataset_or_id.id if isinstance(dataset_or_id, Dataset) else dataset_or_id)

    with transaction.atomic():
        try:
            dataset = Dataset.objects.select_for_update().get(id=dataset_id)
        except Dataset.DoesNotExist:
            logger.warning("check_and_recover_dataset: Dataset %s does not exist", dataset_id)
            if isinstance(dataset_or_id, Dataset):
                return dataset_or_id
            raise

        # Only evaluate datasets in active processing or retrying states that have not requested cancellation
        if dataset.cancel_requested or dataset.status in (
            Dataset.Status.CANCEL_REQUESTED,
            Dataset.Status.CANCELED,
        ) or dataset.status not in (Dataset.Status.PROCESSING, Dataset.Status.RETRYING):
            return dataset

        now = timezone.now()
        task_id = dataset.current_task_id
        is_worker_lost = False
        is_stale_timeout = False
        diagnostic_reason = ""

        # 1. Inspect Celery AsyncResult if task_id is present
        if task_id and not task_id.startswith("sync"):
            try:
                res = AsyncResult(task_id, app=current_app)
                if res.ready():
                    if res.status == "FAILURE":
                        res_str = str(res.result)
                        res_info = str(getattr(res, "info", ""))
                        exc_name = getattr(res.result, "__class__", type(res.result)).__name__
                        if (
                            "WorkerLostError" in exc_name
                            or "WorkerLostError" in res_str
                            or "Worker exited prematurely" in res_str
                            or "signal 11" in res_str
                            or "SIGSEGV" in res_str
                            or "WorkerLostError" in res_info
                        ):
                            is_worker_lost = True
                            diagnostic_reason = (
                                f"Worker terminated prematurely (WorkerLostError/SIGSEGV) for task {task_id}."
                            )
                        else:
                            # Other fatal failure that escaped standard task handler
                            is_worker_lost = True
                            diagnostic_reason = (
                                f"Celery task failed unexpectedly: {res.result}"
                            )
                    elif res.status in ("REVOKED",):
                        is_worker_lost = True
                        diagnostic_reason = f"Celery task {task_id} was revoked."
            except Exception as e:
                logger.debug("Error checking AsyncResult for task %s: %s", task_id, e)

        # 2. Check Heartbeat / Stale Duration
        reference_time = dataset.last_heartbeat_at or dataset.created_at
        elapsed_seconds = (now - reference_time).total_seconds() if reference_time else 999999

        if not is_worker_lost and elapsed_seconds > stale_timeout_seconds:
            # Heartbeat is past the stale threshold. Check if worker is actually executing it.
            if not is_task_actively_running(task_id):
                is_stale_timeout = True
                diagnostic_reason = (
                    f"Processing heartbeat stalled ({int(elapsed_seconds)}s elapsed since last progress). "
                    f"No active worker is executing task {task_id or 'none'}."
                )

        # If healthy, return without modification
        if not is_worker_lost and not is_stale_timeout:
            return dataset

        # 3. Handle Crash Recovery
        max_allowed_retries = dataset.max_retries or MAX_RECOVERY_RETRIES
        logger.warning(
            "Crash/Stall detected for dataset %s: %s (retry_count=%d/%d, checkpoint=chunk %d, rows=%d)",
            dataset.id,
            diagnostic_reason,
            dataset.retry_count,
            max_allowed_retries,
            dataset.chunks_processed,
            dataset.processed_rows,
        )

        if dataset.retry_count < max_allowed_retries:
            dataset.retry_count += 1
            dataset.status = Dataset.Status.RETRYING
            dataset.recovery_state = f"recovering_attempt_{dataset.retry_count}"
            dataset.last_heartbeat_at = now
            recovery_msg = (
                f"[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Recovery event: {diagnostic_reason}\n"
                f"Automatic retry {dataset.retry_count}/{max_allowed_retries} initiated. "
                f"Resuming safely from durable checkpoint: chunk {dataset.chunks_processed} "
                f"({dataset.processed_rows} rows already committed)."
            )
            dataset.append_error(recovery_msg)

            # Dispatch new process task
            try:
                new_task = process_dataset.delay(str(dataset.id))
                dataset.current_task_id = getattr(new_task, "id", None)
                logger.info(
                    "Dispatched recovery task for dataset %s: new task_id=%s",
                    dataset.id,
                    dataset.current_task_id,
                )
            except Exception as dispatch_err:
                if getattr(settings, "DEV_SYNC_FALLBACK", False):
                    logger.warning("Celery dispatch failed (%s), running sync fallback", dispatch_err)
                    dataset.current_task_id = "sync-recovery"
                    dataset.save(update_fields=[
                        "status", "retry_count", "recovery_state",
                        "last_heartbeat_at", "current_task_id", "error_log"
                    ])
                    process_dataset(str(dataset.id))
                    dataset.refresh_from_db()
                    return dataset
                else:
                    dataset.status = Dataset.Status.FAILED
                    dataset.recovery_state = "recovery_dispatch_failed"
                    dataset.append_error(f"Failed to dispatch recovery task: {dispatch_err}")

            dataset.save(update_fields=[
                "status", "retry_count", "recovery_state",
                "last_heartbeat_at", "current_task_id", "error_log"
            ])
            return dataset

        else:
            # Retries exhausted -> Clean, recoverable terminal FAILED state
            dataset.status = Dataset.Status.FAILED
            dataset.recovery_state = "retries_exhausted"
            dataset.completed_at = now
            exhausted_msg = (
                f"[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Fatal: Dataset processing worker terminated unexpectedly.\n"
                f"Failure reason: {diagnostic_reason}\n"
                f"Automatic retries ({dataset.retry_count}/{max_allowed_retries}) were exhausted.\n"
                f"Data integrity notice: Previously completed rows ({dataset.processed_rows}) were safely preserved. "
                f"The dataset was not lost and can be retried from the last durable checkpoint (chunk {dataset.chunks_processed})."
            )
            dataset.append_error(exhausted_msg)
            dataset.save(update_fields=[
                "status", "recovery_state", "completed_at", "error_log"
            ])
            return dataset


def recover_stale_dataset_jobs(
    stale_timeout_seconds: int = DEFAULT_STALE_TIMEOUT_SECONDS,
) -> list[dict]:
    """
    Scan all datasets currently in PROCESSING or RETRYING status, detect any
    crashed workers, and trigger recovery. Returns a summary of recovered datasets.
    """
    active_datasets = Dataset.objects.filter(
        status__in=[Dataset.Status.PROCESSING, Dataset.Status.RETRYING],
        cancel_requested=False,
    ).order_by("created_at")

    results = []
    for ds in active_datasets:
        old_status = ds.status
        old_retries = ds.retry_count
        recovered_ds = check_and_recover_dataset(ds, stale_timeout_seconds=stale_timeout_seconds)
        if recovered_ds.status != old_status or recovered_ds.retry_count != old_retries:
            results.append({
                "dataset_id": str(recovered_ds.id),
                "name": recovered_ds.name,
                "previous_status": old_status,
                "new_status": recovered_ds.status,
                "retry_count": recovered_ds.retry_count,
                "checkpoint_chunks": recovered_ds.chunks_processed,
                "checkpoint_rows": recovered_ds.processed_rows,
                "recovery_state": recovered_ds.recovery_state,
            })

    return results
