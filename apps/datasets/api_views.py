"""
PSIF Platform — Dataset API Views

Endpoints:
  POST   /api/datasets/upload/            → FileUploadView
  GET    /api/datasets/                   → DatasetListView
  GET    /api/datasets/<id>/status/       → DatasetStatusView
  POST   /api/datasets/<id>/column-mapping/ → ColumnMappingView
  POST   /api/datasets/<id>/process/     → ProcessDatasetView

Security:
  - Upload/mapping/process require CanUploadDataset (admin or safety_officer)
  - List/status require CanViewDataset (any authenticated user)
  - No filesystem paths, internal IDs, or secrets are exposed in responses
  - CSRF protection comes from DRF's SessionAuthentication for browser flows
"""
import logging
import os

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .column_mapping import (
    CANONICAL_FIELD_LABELS,
    suggest_column_mapping,
)
from .models import Dataset
from .parsers import detect_file_type, parse_preview
from .permissions import CanUploadDataset, CanViewDataset
from .serializers import (
    ColumnMappingSerializer,
    DatasetListSerializer,
    DatasetStatusSerializer,
    FileUploadSerializer,
)

logger = logging.getLogger(__name__)


class DatasetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


# ── Upload ────────────────────────────────────────────────────────────────────

class FileUploadView(APIView):
    """
    POST /api/datasets/upload/

    Accepts a multipart file upload.  Validates file type and size, saves
    the file to media/uploads/, parses the first ~100 rows synchronously,
    and returns preview data plus auto-suggested column mappings.

    Does NOT process the full dataset — that requires a subsequent POST to
    /api/datasets/<id>/process/ after the column mapping is confirmed.
    """
    permission_classes = [CanUploadDataset]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        ser = FileUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        uploaded_file = ser.validated_data["file"]
        original_name = uploaded_file.name
        _, ext = os.path.splitext(original_name)

        # Read raw content to store in database payload so any distributed Celery worker can access it
        raw_bytes = uploaded_file.read()
        uploaded_file.seek(0)
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = raw_bytes.decode("latin-1")

        # ── Create the Dataset record (generates the UUID before file save) ──
        dataset = Dataset(
            name=original_name,
            uploaded_by=request.user,
            file_type="csv",   # placeholder; corrected after detection below
            status=Dataset.Status.MAPPING_PENDING,
            quality_summary={"raw_file_content": raw_text},
        )
        dataset.original_file = uploaded_file
        dataset.save()   # file is written to disk here

        # ── Detect file type from extension + content ────────────────────────
        try:
            file_type = detect_file_type(dataset.original_file.path, ext)
        except ValueError as exc:
            # Invalid content — clean up and return 400
            dataset.original_file.delete(save=False)
            dataset.delete()
            raise ValidationError({"file": [str(exc)]})

        dataset.file_type = file_type
        dataset.save(update_fields=["file_type"])

        # ── Parse preview rows synchronously ─────────────────────────────────
        try:
            preview = parse_preview(dataset.original_file.path, file_type)
        except Exception as exc:
            logger.exception("Preview parse failed for dataset %s", dataset.id)
            dataset.status = Dataset.Status.FAILED
            dataset.error_log = f"Preview parsing failed: {exc}"
            dataset.save(update_fields=["status", "error_log"])
            raise ValidationError({"file": [f"Could not parse file: {exc}"]})

        # ── Update dataset with row estimate ─────────────────────────────────
        dataset.total_rows = preview.total_rows
        raw_dur = request.data.get("upload_duration_seconds")
        if raw_dur:
            try:
                dataset.upload_duration_seconds = max(0.0, round(float(raw_dur), 2))
                dataset.save(update_fields=["total_rows", "upload_duration_seconds"])
            except (ValueError, TypeError):
                dataset.save(update_fields=["total_rows"])
        else:
            dataset.save(update_fields=["total_rows"])

        # ── Auto-suggest column mapping ───────────────────────────────────────
        suggested = suggest_column_mapping(preview.columns)

        # Build response — strip raw filesystem paths, never expose them
        response_data = {
            "dataset_id": str(dataset.id),
            "name": dataset.name,
            "file_type": file_type,
            "status": dataset.status,
            "total_rows": preview.total_rows,
            "columns": preview.columns,
            "column_types": preview.column_types,
            "preview_rows": preview.preview_rows,
            "suggested_mapping": suggested,
            "canonical_field_labels": CANONICAL_FIELD_LABELS,
            "upload_duration_seconds": dataset.upload_duration_seconds,
        }

        logger.info(
            "Upload successful: dataset=%s file=%s type=%s total_rows=%s",
            dataset.id, original_name, file_type, preview.total_rows,
        )
        return Response(response_data, status=status.HTTP_201_CREATED)


# ── List ──────────────────────────────────────────────────────────────────────

class DatasetListView(APIView):
    """
    GET /api/datasets/

    Returns a paginated list of datasets, most recent first.
    Non-admin users see only their own datasets.
    Admins and safety officers see all.
    """
    permission_classes = [CanViewDataset]

    def get(self, request):
        user = request.user

        # Scope: admins/safety-officers see all; others see only theirs
        if user.role in ("admin", "safety_officer"):
            qs = Dataset.objects.select_related("uploaded_by").all()
        else:
            qs = Dataset.objects.select_related("uploaded_by").filter(uploaded_by=user)

        paginator = DatasetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = DatasetListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ── Status ────────────────────────────────────────────────────────────────────

class DatasetStatusView(APIView):
    """
    GET /api/datasets/<id>/status/

    Returns live processing progress for polling by the status UI.
    Automatically audits worker health and executes recovery if worker loss is detected.
    """
    permission_classes = [CanViewDataset]

    def get(self, request, pk):
        from .recovery import check_and_recover_dataset
        dataset = _get_dataset_or_404(pk)

        # Proactive watchdog check: if in PROCESSING or RETRYING, verify worker health
        if dataset.status in (Dataset.Status.PROCESSING, Dataset.Status.RETRYING):
            dataset = check_and_recover_dataset(dataset)

        serializer = DatasetStatusSerializer(dataset)
        return Response(serializer.data)


# ── Column Mapping ────────────────────────────────────────────────────────────

class ColumnMappingView(APIView):
    """
    POST /api/datasets/<id>/column-mapping/

    Accepts a {source_column: canonical_field} mapping and saves it to
    Dataset.column_mapping.  Validates for unknown canonical fields and
    duplicate assignments.

    The dataset must be in 'mapping_pending' status.
    """
    permission_classes = [CanUploadDataset]

    def post(self, request, pk):
        dataset = _get_dataset_or_404(pk)

        if dataset.status not in (
            Dataset.Status.MAPPING_PENDING,
            Dataset.Status.UPLOADED,
        ):
            raise ValidationError(
                {"status": [f"Cannot update mapping when dataset is in '{dataset.status}' status."]}
            )

        serializer = ColumnMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mapping = serializer.validated_data["column_mapping"]

        # Persist
        dataset.column_mapping = mapping
        dataset.save(update_fields=["column_mapping"])

        logger.info(
            "Column mapping saved: dataset=%s mapped_fields=%d",
            dataset.id,
            sum(1 for v in mapping.values() if v),
        )

        return Response(
            {
                "dataset_id": str(dataset.id),
                "column_mapping": mapping,
                "mapped_fields": sum(1 for v in mapping.values() if v),
                "unmapped_fields": sum(1 for v in mapping.values() if not v),
                "message": "Column mapping saved. POST to /process/ to begin ingestion.",
            }
        )


# ── Process ───────────────────────────────────────────────────────────────────

class ProcessDatasetView(APIView):
    """
    POST /api/datasets/<id>/process/

    Validates that a column mapping exists, transitions the dataset to
    'processing', and dispatches the process_dataset Celery task.
    Returns immediately (the actual work is async).
    """
    permission_classes = [CanUploadDataset]

    def post(self, request, pk):
        from .tasks import process_dataset as process_task

        dataset = _get_dataset_or_404(pk)

        # State guard
        if dataset.status == Dataset.Status.PROCESSING:
            raise ValidationError({"status": ["Dataset is already being processed."]})
        if dataset.status in (Dataset.Status.COMPLETED, Dataset.Status.FAILED):
            raise ValidationError(
                {"status": [f"Dataset has already been processed (status={dataset.status})."]}
            )

        # Mapping guard
        if not dataset.column_mapping:
            raise ValidationError(
                {"column_mapping": [
                    "No column mapping found.  POST to "
                    f"/api/datasets/{dataset.id}/column-mapping/ first."
                ]}
            )

        # Validate that at least one canonical field is mapped
        mapped = [v for v in dataset.column_mapping.values() if v]
        if not mapped:
            raise ValidationError(
                {"column_mapping": ["Column mapping exists but no fields are mapped to canonical fields."]}
            )

        # Transition to processing
        from django.utils import timezone
        now = timezone.now()
        dataset.status = Dataset.Status.PROCESSING
        dataset.processed_rows = 0
        if dataset.processing_started_at is None:
            dataset.processing_started_at = now
        update_fields = ["status", "processed_rows", "processing_started_at"]
        raw_upload_dur = request.data.get("upload_duration_seconds")
        if raw_upload_dur and dataset.upload_duration_seconds is None:
            try:
                dataset.upload_duration_seconds = max(0.0, round(float(raw_upload_dur), 2))
                update_fields.append("upload_duration_seconds")
            except (ValueError, TypeError):
                pass
        dataset.save(update_fields=update_fields)

        task_id = None
        # Dispatch Celery task, or execute directly if broker is unavailable and fallback is allowed
        try:
            task = process_task.delay(str(dataset.id))
            task_id = getattr(task, "id", None)
            logger.info("Dataset processing dispatched via Celery: dataset=%s task_id=%s", dataset.id, task_id)
        except Exception as broker_exc:
            from django.conf import settings
            if getattr(settings, "DEV_SYNC_FALLBACK", False):
                logger.warning("Celery broker dispatch failed (%s) — executing synchronously (DEV_SYNC_FALLBACK=True)", broker_exc)
                # Execute synchronously as fallback so processing never stalls
                res = process_task(str(dataset.id))
                task_id = "sync-executed"
                logger.info("Synchronous processing completed: %s", res)
            else:
                logger.error("Celery broker dispatch failed (%s) — DEV_SYNC_FALLBACK=False. Cannot process.", broker_exc)
                dataset.status = Dataset.Status.FAILED
                dataset.error_log = f"Failed to dispatch to background worker: {broker_exc}"
                dataset.save(update_fields=["status", "error_log"])
                return Response(
                    {"status": ["Service Unavailable: Background worker dispatch failed."]},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response(
            {
                "dataset_id": str(dataset.id),
                "status": dataset.status,
                "task_id": task_id,
                "message": (
                    "Processing started. "
                    f"Poll GET /api/datasets/{dataset.id}/status/ for progress."
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ── Retry / Resume ────────────────────────────────────────────────────────────

class RetryDatasetView(APIView):
    """
    POST /api/datasets/<id>/retry/

    Manually trigger recovery/retry for a dataset that failed, was interrupted, or is stalled.
    Resumes processing from the last durable checkpoint without duplicating rows or predictions.
    """
    permission_classes = [CanUploadDataset]

    def post(self, request, pk):
        from django.utils import timezone
        from .tasks import process_dataset as process_task

        dataset = _get_dataset_or_404(pk)

        if dataset.status == Dataset.Status.COMPLETED:
            raise ValidationError({"status": ["Dataset has already completed processing."]})

        if not dataset.column_mapping:
            raise ValidationError(
                {"column_mapping": ["No column mapping found. Cannot process without a mapping."]}
            )

        # Transition to RETRYING and reset retry_count for manual intervention
        dataset.status = Dataset.Status.RETRYING
        dataset.retry_count = 0
        dataset.cancel_requested = False
        dataset.canceled_at = None
        dataset.recovery_state = "manual_retry_queued"
        dataset.last_heartbeat_at = timezone.now()
        dataset.append_error(
            f"[{timezone.now().strftime('%Y-%m-%d %H:%M:%S UTC')}] Manual retry requested by user {request.user.username}. "
            f"Resuming safely from durable checkpoint: chunk {dataset.chunks_processed} ({dataset.processed_rows} rows)."
        )
        dataset.save(update_fields=[
            "status", "retry_count", "cancel_requested", "canceled_at",
            "recovery_state", "last_heartbeat_at", "error_log"
        ])

        # Clear Redis cancel key if present
        try:
            import redis
            from django.conf import settings
            r = redis.from_url(getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0"))
            r.delete(f"dataset:cancel:{dataset.id}")
        except Exception:
            pass

        task_id = None
        try:
            task = process_task.delay(str(dataset.id))
            task_id = getattr(task, "id", None)
            dataset.current_task_id = task_id
            dataset.save(update_fields=["current_task_id"])
            logger.info("Manual retry dispatched for dataset %s: task_id=%s", dataset.id, task_id)
        except Exception as broker_exc:
            from django.conf import settings
            if getattr(settings, "DEV_SYNC_FALLBACK", False):
                logger.warning("Celery dispatch failed (%s), running sync fallback", broker_exc)
                dataset.current_task_id = "sync-retry"
                dataset.save(update_fields=["current_task_id"])
                process_task(str(dataset.id))
                dataset.refresh_from_db()
                task_id = "sync-retry"
            else:
                dataset.status = Dataset.Status.FAILED
                dataset.recovery_state = "retry_dispatch_failed"
                dataset.append_error(f"Failed to dispatch retry task: {broker_exc}")
                dataset.save(update_fields=["status", "recovery_state", "error_log"])
                return Response(
                    {"status": ["Service Unavailable: Background worker dispatch failed."]},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response(
            {
                "dataset_id": str(dataset.id),
                "status": dataset.status,
                "task_id": task_id,
                "checkpoint_chunk": dataset.chunks_processed,
                "checkpoint_rows": dataset.processed_rows,
                "message": (
                    f"Retry initiated. Resuming from chunk {dataset.chunks_processed} "
                    f"({dataset.processed_rows} rows already committed)."
                ),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DatasetCancelView(APIView):
    """
    POST /api/datasets/<uuid:pk>/cancel/

    Cooperatively requests cancellation of a dataset that is:
    - actively processing,
    - retrying,
    - or pending column mapping.

    Does NOT kill workers or terminate processes.
    Signals the Celery task to stop at the next safe chunk checkpoint,
    commit the current transaction, and transition to CANCELED.
    """
    permission_classes = [CanUploadDataset]

    def post(self, request, pk):
        from django.utils import timezone
        from .tasks import finalize_dataset_cancellation
        from .recovery import is_task_actively_running

        dataset = _get_dataset_or_404(pk)

        # Guard 1: Completed datasets cannot be canceled (A9, A12)
        if dataset.status == Dataset.Status.COMPLETED:
            return Response(
                {
                    "detail": "Cannot cancel a dataset that has already completed processing.",
                    "status": dataset.status,
                    "processed_rows": dataset.processed_rows,
                    "total_rows": dataset.total_rows,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard 2: Already canceled (Idempotent - A11)
        if dataset.status == Dataset.Status.CANCELED:
            return Response(
                {
                    "status": "canceled",
                    "message": "Dataset is already canceled.",
                    "processed_rows": dataset.processed_rows,
                    "total_rows": dataset.total_rows,
                    "checkpoint_chunk": dataset.chunks_processed,
                },
                status=status.HTTP_200_OK,
            )

        # Guard 3: Already requested cancellation (Idempotent - A11)
        if dataset.status == Dataset.Status.CANCEL_REQUESTED or dataset.cancel_requested:
            return Response(
                {
                    "status": "cancel_requested",
                    "message": "Cancellation already requested. Waiting for the current processing checkpoint to finish.",
                    "processed_rows": dataset.processed_rows,
                    "total_rows": dataset.total_rows,
                    "checkpoint_chunk": dataset.chunks_processed,
                },
                status=status.HTTP_200_OK,
            )

        # Mapping-pending or uploaded datasets (no active worker running)
        if dataset.status in (Dataset.Status.MAPPING_PENDING, Dataset.Status.UPLOADED):
            now = timezone.now()
            dataset.status = Dataset.Status.CANCELED
            dataset.cancel_requested = True
            dataset.canceled_at = now
            dataset.completed_at = now
            dataset.processing_completed_at = now
            dataset.recovery_state = "canceled"
            dataset.append_error(f"[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Pending upload canceled by user {request.user.username}.")
            dataset.save(update_fields=[
                "status", "cancel_requested", "canceled_at", "completed_at",
                "processing_completed_at", "recovery_state", "error_log"
            ])
            return Response(
                {
                    "status": "canceled",
                    "message": "Pending dataset canceled successfully.",
                    "processed_rows": dataset.processed_rows,
                    "total_rows": dataset.total_rows,
                },
                status=status.HTTP_200_OK,
            )

        # Failed datasets
        if dataset.status == Dataset.Status.FAILED:
            now = timezone.now()
            dataset.status = Dataset.Status.CANCELED
            dataset.cancel_requested = True
            dataset.canceled_at = now
            dataset.recovery_state = "canceled"
            dataset.append_error(f"[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Failed dataset marked canceled by user {request.user.username}.")
            dataset.save(update_fields=[
                "status", "cancel_requested", "canceled_at", "recovery_state", "error_log"
            ])
            return Response(
                {
                    "status": "canceled",
                    "message": "Dataset marked canceled.",
                    "processed_rows": dataset.processed_rows,
                    "total_rows": dataset.total_rows,
                },
                status=status.HTTP_200_OK,
            )

        # Active processing / retrying states:
        # 1. Set fast Redis cancellation flag
        try:
            import redis
            from django.conf import settings
            broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
            r = redis.from_url(broker_url)
            r.set(f"dataset:cancel:{dataset.id}", "1", ex=3600)
        except Exception as r_err:
            logger.warning("Could not set Redis cancel key for %s: %s", dataset.id, r_err)

        # 2. Check if a worker is actively executing this task
        worker_alive = is_task_actively_running(dataset.current_task_id)

        if not worker_alive:
            # If no worker is actively executing, finalize immediately so it doesn't get stuck
            logger.info("Dataset %s has no active worker executing task %s; finalizing cancellation immediately.", dataset.id, dataset.current_task_id)
            res = finalize_dataset_cancellation(str(dataset.id))
            return Response(
                {
                    "status": "canceled",
                    "message": "Processing canceled successfully (no active worker was running).",
                    "processed_rows": res.get("processed_rows", dataset.processed_rows),
                    "total_rows": res.get("total_rows", dataset.total_rows),
                    "checkpoint_chunk": dataset.chunks_processed,
                },
                status=status.HTTP_200_OK,
            )

        # 3. Active worker is running: transition to CANCEL_REQUESTED and let worker cooperatively stop at checkpoint
        now = timezone.now()
        dataset.status = Dataset.Status.CANCEL_REQUESTED
        dataset.cancel_requested = True
        dataset.recovery_state = "cancel_requested"
        dataset.append_error(
            f"[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Cancellation requested by user {request.user.username}. "
            f"Awaiting safe cooperative checkpoint after chunk {dataset.chunks_processed}."
        )
        dataset.save(update_fields=["status", "cancel_requested", "recovery_state", "error_log"])

        logger.info(
            "Cancellation requested for dataset %s (task=%s, chunk=%d). Worker will stop at next safe checkpoint.",
            dataset.id, dataset.current_task_id, dataset.chunks_processed
        )

        return Response(
            {
                "status": "cancel_requested",
                "message": "Cancellation requested. Processing will stop at the next safe checkpoint.",
                "processed_rows": dataset.processed_rows,
                "total_rows": dataset.total_rows,
                "checkpoint_chunk": dataset.chunks_processed,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DatasetDeleteView(APIView):
    """
    DELETE /api/datasets/<uuid:pk>/

    Permanently deletes a dataset and all associated incident records.

    Guardrails:
      - Strictly disallows deleting datasets that are actively processing, retrying, or cancel_requested
        (returns 409 Conflict) to protect ongoing worker jobs.
      - On valid deletion:
        * Bulk-deletes all related Incident records (which cascades to PredictionResult rows)
        * Safely removes the uploaded file from disk (media/uploads/<id>/...)
        * Removes the empty parent folder
        * Deletes the Dataset database record
    """
    permission_classes = [CanUploadDataset]

    def delete(self, request, pk):
        from django.db import transaction
        from django.db.models import ProtectedError

        dataset = _get_dataset_or_404(pk)

        # Guard 1: Protect ongoing uploads (processing, retrying, cancel_requested)
        if dataset.status in [
            Dataset.Status.PROCESSING,
            Dataset.Status.RETRYING,
            Dataset.Status.CANCEL_REQUESTED,
        ]:
            return Response(
                {
                    "detail": "Cannot delete a dataset that is currently processing or retrying. "
                              "Wait for processing to reach a terminal state (canceled, completed, or failed)."
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Guard 2: Reject unknown/unexpected statuses
        deletable_statuses = (
            Dataset.Status.MAPPING_PENDING,
            Dataset.Status.UPLOADED,
            Dataset.Status.FAILED,
            Dataset.Status.CANCELED,
            Dataset.Status.COMPLETED,
        )
        if dataset.status not in deletable_statuses:
            return Response(
                {
                    "detail": f"Cannot delete dataset with status '{dataset.status}'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        dataset_id_str = str(dataset.id)
        dataset_name = dataset.name

        try:
            with transaction.atomic():
                # Delete incidents in chunks of 500 to avoid PostgreSQL's 65535
                # bind-parameter limit. Django's ORM collects all related PKs into
                # a single IN-list for cascade handling, which blows up on large datasets.
                from apps.incidents.models import Incident as _Incident
                CHUNK = 500
                incident_count = 0
                while True:
                    chunk_ids = list(
                        dataset.incidents.values_list("id", flat=True)[:CHUNK]
                    )
                    if not chunk_ids:
                        break
                    deleted, _ = _Incident.objects.filter(id__in=chunk_ids).delete()
                    incident_count += deleted
                logger.info(
                    "Deleted %d incident(s) for dataset %s.",
                    incident_count, dataset.id,
                )

                # Clean up file on disk if it exists
                folder_path = None
                try:
                    if dataset.original_file and dataset.original_file.name:
                        file_path = dataset.original_file.path
                        folder_path = os.path.dirname(file_path)
                        dataset.original_file.delete(save=False)
                except Exception as file_exc:
                    logger.warning("Error deleting file for dataset %s: %s", dataset.id, file_exc)

                if folder_path and os.path.isdir(folder_path):
                    try:
                        if not os.listdir(folder_path):
                            os.rmdir(folder_path)
                    except Exception as dir_exc:
                        logger.warning("Error cleaning directory for dataset %s: %s", dataset.id, dir_exc)

                dataset.delete()

        except ProtectedError as exc:
            logger.error("ProtectedError deleting dataset %s: %s", pk, exc)
            return Response(
                {
                    "detail": f"Cannot delete: a related record is protected. Detail: {exc}"
                },
                status=status.HTTP_409_CONFLICT,
            )
        except Exception as exc:
            logger.exception("Unexpected error deleting dataset %s: %s", pk, exc)
            return Response(
                {
                    "detail": f"An unexpected error occurred while deleting the dataset: {exc}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            "Dataset %s (%s) deleted by user %s. %d incident record(s) also deleted.",
            dataset_id_str,
            dataset_name,
            request.user.username,
            incident_count,
        )

        return Response(
            {
                "status": "deleted",
                "dataset_id": dataset_id_str,
                "incidents_deleted": incident_count,
                "message": f"Dataset '{dataset_name}' and {incident_count} associated incident record(s) were permanently deleted.",
            },
            status=status.HTTP_200_OK,
        )

class DatasetPreviewView(APIView):
    """
    GET /api/datasets/<uuid:pk>/preview/

    Returns parsed preview data and suggested column mappings for a pending
    uncompleted dataset, enabling the upload wizard to resume mapping.
    """
    permission_classes = [CanUploadDataset]

    def get(self, request, pk):
        dataset = _get_dataset_or_404(pk)
        if dataset.status not in (Dataset.Status.MAPPING_PENDING, Dataset.Status.UPLOADED):
            return Response(
                {"detail": f"Dataset is not awaiting column mapping (status: {dataset.status})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not dataset.original_file:
            return Response(
                {"detail": "Original file not found for dataset."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            preview = parse_preview(dataset.original_file.path, dataset.file_type)
        except Exception as exc:
            return Response(
                {"detail": f"Could not parse preview: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggested = dataset.column_mapping or suggest_column_mapping(preview.columns)

        return Response({
            "dataset_id": str(dataset.id),
            "name": dataset.name,
            "file_type": dataset.file_type,
            "status": dataset.status,
            "total_rows": preview.total_rows,
            "columns": preview.columns,
            "column_types": preview.column_types,
            "preview_rows": preview.preview_rows,
            "suggested_mapping": suggested,
            "canonical_field_labels": CANONICAL_FIELD_LABELS,
            "upload_duration_seconds": dataset.upload_duration_seconds,
        })



# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_dataset_or_404(pk) -> Dataset:
    """Return the Dataset with the given PK or raise NotFound."""
    try:
        return Dataset.objects.get(pk=pk)
    except Dataset.DoesNotExist:
        raise NotFound(f"Dataset {pk} not found.")
    except Exception:
        raise NotFound("Invalid dataset ID.")
