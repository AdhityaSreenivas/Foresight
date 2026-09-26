"""
PSIF Platform — Celery Tasks for Dataset Processing

Single task: process_dataset(dataset_id)

Processes an uploaded dataset file in chunks:
  1. Streams the file with parsers.iter_file_chunks()
  2. Converts each chunk to Incident rows via ingestion.bulk_create_incidents()
  3. Applies weak PSIF labels during creation
  4. Updates Dataset.processed_rows after each chunk (enables live progress)
  5. Sets final status to completed or failed

Phase 4 note:
  BERT inference is intentionally NOT run here in Phase 2.
  composite_narrative is stored on each Incident, ready for the Phase 4
  inference pass that creates PredictionResult objects.
"""
import logging
import traceback
from pathlib import Path

from celery import shared_task
from django.utils import timezone
from django.db import transaction

from .models import Dataset

logger = logging.getLogger(__name__)


def is_cancellation_requested(dataset_id: str) -> bool:
    """
    Check whether cancellation has been requested for this dataset.
    Checks Redis first for sub-millisecond polling, with DB fallback.
    Also cooperatively cancels if this dataset belongs to Admin Flow and a reset is in progress.
    """
    try:
        from apps.admin_flow.services import is_admin_flow_reset_in_progress, ADMIN_FLOW_WORKSPACE
        if is_admin_flow_reset_in_progress():
            if Dataset.objects.filter(id=dataset_id, workspace_id=ADMIN_FLOW_WORKSPACE).exists():
                return True
    except Exception:
        pass

    try:
        import redis
        from django.conf import settings
        broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.from_url(broker_url)
        if r.get(f"dataset:cancel:{dataset_id}"):
            return True
    except Exception:
        pass
    return Dataset.objects.filter(
        id=dataset_id,
        cancel_requested=True,
    ).exists()


def finalize_dataset_cancellation(dataset_id: str) -> dict:
    """
    Cooperatively finalize cancellation of a dataset at a safe checkpoint.
    Preserves all committed chunks, incidents, predictions, and embeddings.
    Sets status to CANCELED and records duration and audit summary.
    """
    now = timezone.now()
    with transaction.atomic():
        ds = Dataset.objects.select_for_update().get(id=dataset_id)
        # If already completed, do not overwrite with CANCELED
        if ds.status == Dataset.Status.COMPLETED:
            return {"status": "completed", "processed_rows": ds.processed_rows}

        ds.status = Dataset.Status.CANCELED
        ds.cancel_requested = True
        ds.canceled_at = now
        ds.completed_at = now
        ds.processing_completed_at = now
        ds.recovery_state = "canceled"
        if ds.processing_started_at:
            ds.processing_duration_seconds = max(0.0, (now - ds.processing_started_at).total_seconds())

        total_psif = ds.incidents.filter(prediction__psif_predicted=True).count()
        total_non_psif = ds.incidents.filter(prediction__psif_predicted=False).count()
        if ds.quality_summary:
            ds.quality_summary["psif_count"] = total_psif
            ds.quality_summary["non_psif_count"] = total_non_psif

        cancel_msg = (
            f"[{now.strftime('%Y-%m-%d %H:%M:%S UTC')}] Processing cooperatively canceled by user request.\n"
            f"Stopped safely at durable checkpoint: chunk {ds.chunks_processed} "
            f"({ds.processed_rows} of {ds.total_rows or 'unknown'} rows preserved).\n"
            f"Preserved data: {ds.incidents.count()} incidents, {total_psif} PSIF candidates, "
            f"{total_non_psif} non-PSIF records."
        )
        ds.append_error(cancel_msg)
        ds.save(update_fields=[
            "status", "cancel_requested", "canceled_at", "completed_at",
            "processing_completed_at", "processing_duration_seconds",
            "recovery_state", "quality_summary", "error_log"
        ])

    try:
        import redis
        from django.conf import settings
        broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.from_url(broker_url)
        r.delete(f"dataset:cancel:{dataset_id}")
    except Exception:
        pass

    logger.info(
        "process_dataset CANCELED: dataset=%s processed=%d rows preserved duration=%.1fs",
        dataset_id, ds.processed_rows, ds.processing_duration_seconds or 0.0
    )
    return {
        "status": "canceled",
        "processed_rows": ds.processed_rows,
        "total_rows": ds.total_rows,
    }


@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=3600,
    soft_time_limit=3500,
)
def process_dataset(self, dataset_id: str) -> dict:
    """
    Process a single uploaded dataset file end-to-end with crash resilience
    and durable chunk-level checkpointing.

    Args:
        dataset_id: UUID string of the Dataset to process.

    Returns:
        Summary dict: {processed_rows, error_rows, status}
    """
    from .parsers import iter_file_chunks
    from .ingestion import bulk_create_incidents

    task_id = getattr(self.request, "id", None) or "sync"
    logger.info("process_dataset started: dataset_id=%s task_id=%s", dataset_id, task_id)

    # ── Load dataset ──────────────────────────────────────────────────────────
    try:
        dataset = Dataset.objects.get(id=dataset_id)
    except Dataset.DoesNotExist:
        logger.error("process_dataset: Dataset %s not found", dataset_id)
        return {"status": "error", "message": "Dataset not found"}

    # Guard: check for immediate cancellation before beginning work
    if dataset.cancel_requested or dataset.status in (Dataset.Status.CANCEL_REQUESTED, Dataset.Status.CANCELED) or is_cancellation_requested(dataset_id):
        logger.info("process_dataset: cancellation detected at start for dataset %s", dataset_id)
        return finalize_dataset_cancellation(dataset_id)

    # Guard: only process if in the correct state (allow RETRYING on recovery)
    if dataset.status not in (Dataset.Status.PROCESSING, Dataset.Status.RETRYING):
        logger.warning(
            "process_dataset: dataset %s has unexpected status '%s' — aborting",
            dataset_id, dataset.status,
        )
        return {"status": "skipped", "message": f"Unexpected status: {dataset.status}"}

    # Record active task ID, heartbeat, and processing_started_at
    now = timezone.now()
    if dataset.processing_started_at is None:
        dataset.processing_started_at = now
    dataset.current_task_id = task_id
    dataset.last_heartbeat_at = now
    if dataset.status == Dataset.Status.RETRYING:
        dataset.status = Dataset.Status.PROCESSING
        dataset.recovery_state = "resumed"
    dataset.save(update_fields=[
        "current_task_id", "last_heartbeat_at", "status",
        "recovery_state", "processing_started_at"
    ])

    try:
        file_path = dataset.original_file.path
    except Exception:
        file_path = None

    if not file_path or not Path(file_path).exists():
        raw_content = (dataset.quality_summary or {}).get("raw_file_content")
        if raw_content:
            from django.conf import settings
            target_path = Path(settings.MEDIA_ROOT) / str(dataset.original_file.name)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(raw_content, encoding="utf-8")
            file_path = str(target_path)
            logger.info("Restored dataset file from database payload to %s", file_path)
        else:
            logger.error("Dataset file %s does not exist on worker and no raw payload stored.", file_path)
            now = timezone.now()
            dataset.status = Dataset.Status.FAILED
            dataset.error_log = f"Dataset file not found on worker and no raw payload stored: {file_path}"
            dataset.completed_at = now
            dataset.processing_completed_at = now
            dataset.save(update_fields=["status", "error_log", "completed_at", "processing_completed_at"])
            return {"status": "failed", "message": "File not found"}

    file_type = dataset.file_type
    column_mapping = dataset.column_mapping

    if not column_mapping:
        # Safety guard — should never happen if the API enforces it
        now = timezone.now()
        dataset.status = Dataset.Status.FAILED
        dataset.recovery_state = "missing_mapping"
        dataset.error_log = "No column mapping found. Cannot process without a mapping."
        dataset.completed_at = now
        dataset.processing_completed_at = now
        if dataset.processing_started_at:
            dataset.processing_duration_seconds = max(0.0, (now - dataset.processing_started_at).total_seconds())
        dataset.save(update_fields=[
            "status", "recovery_state", "error_log", "completed_at",
            "processing_completed_at", "processing_duration_seconds"
        ])
        return {"status": "failed", "message": "No column mapping"}

    # ── Phase 4: Snapshot ModelVersion for consistent batch processing ────────
    from apps.predictions.models import ModelVersion, PredictionResult
    from ml_engine.model_inference import get_active_predictor

    try:
        predictor = get_active_predictor()
    except Exception as exc:
        logger.warning(
            "process_dataset: Could not initialize active predictor (%s). "
            "Ingestion will complete, but predictions will be skipped.", exc
        )
        predictor = None

    active_model = (
        ModelVersion.objects.filter(is_active=True, status=ModelVersion.Status.ACTIVE)
        .exclude(xgboost_artifact_path="")
        .first()
    )
    if not active_model:
        active_model = (
            ModelVersion.objects.filter(is_active=True)
            .exclude(xgboost_artifact_path="")
            .first()
        )
    if not active_model:
        active_model = ModelVersion.objects.filter(is_active=True).first()

    if not active_model or not predictor:
        logger.warning(
            "process_dataset: No active ModelVersion or predictor available. "
            "Ingestion will complete, but predictions will be skipped."
        )
        dataset.append_error("Warning: No active model version or predictor found. Predictions skipped for this dataset.")
        dataset.save(update_fields=["error_log"])

    # ── Process chunks ────────────────────────────────────────────────────────
    chunk_num = 0
    # Resumption safety: restore previous counts if resuming from checkpoint
    existing_qs = dataset.quality_summary or {}
    total_accepted = existing_qs.get("accepted", 0)
    total_warnings = existing_qs.get("accepted_with_warnings", 0)
    total_rejected = existing_qs.get("rejected", 0)
    all_rejections = list(existing_qs.get("rejections", []))
    current_row_offset = 1

    try:
        for rows_in_chunk, parser_skipped in iter_file_chunks(file_path, file_type):
            chunk_num += 1

            # Cooperative checkpoint: check if cancellation was requested before starting chunk
            if is_cancellation_requested(dataset_id):
                logger.info(
                    "process_dataset: cooperative cancellation detected before chunk %d for dataset %s",
                    chunk_num, dataset_id
                )
                return finalize_dataset_cancellation(dataset_id)

            # Wrap each chunk in an atomic transaction to ensure Incident and PredictionResult
            # stay consistent if inference or DB insertion fails mid-chunk.
            with transaction.atomic():
                # Lock the dataset row to prevent concurrent duplicate processing
                locked_ds = Dataset.objects.select_for_update().get(id=dataset_id)
                
                if chunk_num <= locked_ds.chunks_processed:
                    logger.info("process_dataset: chunk %d already processed, skipping", chunk_num)
                    current_row_offset += len(rows_in_chunk)
                    continue

                created_incidents, ingestion_errors, chunk_dq = bulk_create_incidents(
                    rows_in_chunk, locked_ds, column_mapping, start_row_index=current_row_offset, return_details=True
                )
                
                total_accepted += chunk_dq.get("accepted", len(created_incidents))
                total_warnings += chunk_dq.get("accepted_with_warnings", 0)
                total_rejected += chunk_dq.get("rejected", ingestion_errors)
                chunk_rejections = chunk_dq.get("rejections", [])
                all_rejections.extend(chunk_rejections)

                created_count = len(created_incidents)
                chunk_errors = parser_skipped + ingestion_errors
                current_row_offset += len(rows_in_chunk)

                # Log rejections to error_log for direct auditability
                for rej in chunk_rejections:
                    rej_msg = f"Row {rej['row']}: Rejected. Reason: {rej['reason']}"
                    if rej.get("findings"):
                        rej_msg += f" ({'; '.join(rej['findings'])})"
                    locked_ds.append_error(rej_msg)

                # ── Inference Pass ────────────────────────────────────────────────
                if created_incidents and predictor and active_model:
                    # Safely handle incidents that may already have a PredictionResult 
                    # (e.g., from a partial/retried execution or manual DB manipulation)
                    # to maintain the OneToOne invariant.
                    existing_prediction_incident_ids = set(
                        PredictionResult.objects.filter(
                            incident__in=created_incidents
                        ).values_list("incident_id", flat=True)
                    )
                    
                    incidents_to_predict = [
                        inc for inc in created_incidents 
                        if inc.id not in existing_prediction_incident_ids
                    ]

                    if incidents_to_predict:
                        records = [inc.to_prediction_record() for inc in incidents_to_predict]

                        # Run inference (batch)
                        batch_outputs = predictor.predict_batch(records)

                        # Create PredictionResult objects
                        prediction_results = []
                        for inc, pred in zip(incidents_to_predict, batch_outputs):
                            prediction_results.append(PredictionResult(
                                incident=inc,
                                model_version=active_model,
                                psif_probability=pred.psif_probability,
                                psif_predicted=pred.psif_predicted,
                                risk_level=pred.risk_level,
                                top_factors=pred.top_factors,
                                is_sparse_input=getattr(pred, "is_sparse_input", False),
                                evidence_strength=getattr(pred, "evidence_strength", "MODERATE"),
                                explanation_detail=getattr(pred, "explanation", {}),
                            ))
                        
                        PredictionResult.objects.bulk_create(prediction_results, batch_size=500)

                # ── IOGP Classification Pass ──────────────────────────────────────
                if created_incidents:
                    from apps.predictions.iogp_classifier import classify_iogp_rules
                    from apps.incidents.models import IOGPRuleTag
                    
                    iogp_tags_to_create = []
                    for inc in created_incidents:
                        fields_to_check = {
                            "description": inc.description,
                            "job_task": inc.job_task,
                            "equipment_involved": inc.equipment_involved,
                            "immediate_cause": inc.immediate_cause,
                            "corrective_actions": inc.corrective_actions,
                            "location": inc.location,
                            "composite_narrative": inc.composite_narrative
                        }
                        
                        iogp_results = classify_iogp_rules(fields_to_check)
                        for res in iogp_results:
                            iogp_tags_to_create.append(IOGPRuleTag(
                                incident=inc,
                                rule=res["rule"],
                                matched_keywords=res["matched_keywords"],
                                matched_fields=res["matched_fields"],
                                classification_method=res["classification_method"],
                                classifier_version=res["classifier_version"],
                                confidence=res["confidence"]
                            ))
                            
                    if iogp_tags_to_create:
                        IOGPRuleTag.objects.bulk_create(iogp_tags_to_create, batch_size=500, ignore_conflicts=True)

                # ── Incident Embedding Queue Pass (Idempotent) ────────────────────
                if created_incidents:
                    incident_ids = [str(inc.id) for inc in created_incidents]
                    try:
                        generate_incident_embeddings_task.delay(incident_ids)
                        logger.info(
                            "Dispatched async embedding generation task for %d incidents (chunk %d).",
                            len(incident_ids), chunk_num
                        )
                    except Exception as emb_dispatch_err:
                        logger.warning(
                            "Async Celery broker dispatch failed (%s); generating embeddings synchronously for %d incidents.",
                            emb_dispatch_err, len(created_incidents)
                        )
                        try:
                            from apps.incidents.services.embedding import generate_and_persist_embeddings
                            generate_and_persist_embeddings(created_incidents)
                        except Exception as emb_inline_err:
                            logger.error(
                                "Inline embedding generation failed for chunk %d: %s. Can be recovered via backfill_incident_embeddings.",
                                chunk_num, emb_inline_err
                            )

                # Update progress atomically. processed_rows includes both successes and errors.
                locked_ds.processed_rows += (created_count + chunk_errors)
                locked_ds.error_rows += chunk_errors
                locked_ds.chunks_processed += 1
                
                # Safeguard: never let processed_rows exceed total_rows during execution
                if locked_ds.total_rows is not None and locked_ds.processed_rows > locked_ds.total_rows:
                    locked_ds.total_rows = locked_ds.processed_rows

                locked_ds.quality_summary = {
                    "total": locked_ds.processed_rows,
                    "accepted": total_accepted,
                    "accepted_with_warnings": total_warnings,
                    "rejected": total_rejected,
                    "rejections": all_rejections[:500],
                }

                locked_ds.last_heartbeat_at = timezone.now()
                locked_ds.save(update_fields=[
                    "processed_rows", "error_rows", "chunks_processed",
                    "total_rows", "quality_summary", "error_log", "last_heartbeat_at"
                ])

                logger.info(
                    "process_dataset chunk %d: dataset=%s +%d rows (total=%d, errors=%d)",
                    chunk_num, dataset_id, created_count, locked_ds.processed_rows, locked_ds.error_rows,
                )

            # Cooperative checkpoint: check if cancellation was requested after chunk committed
            if is_cancellation_requested(dataset_id):
                logger.info(
                    "process_dataset: cooperative cancellation detected after chunk %d commit for dataset %s",
                    chunk_num, dataset_id
                )
                return finalize_dataset_cancellation(dataset_id)

        # ── Check cancellation before marking completed ──────────────────────
        if is_cancellation_requested(dataset_id):
            logger.info("process_dataset: cooperative cancellation detected before completion for dataset %s", dataset_id)
            return finalize_dataset_cancellation(dataset_id)

        # ── Mark completed ────────────────────────────────────────────────────
        with transaction.atomic():
            final_ds = Dataset.objects.select_for_update().get(id=dataset_id)
            
            # Synchronize total_rows to exactly match processed_rows, ensuring 100% completion
            if final_ds.processed_rows > 0:
                final_ds.total_rows = final_ds.processed_rows

            now = timezone.now()
            final_ds.status = Dataset.Status.COMPLETED
            final_ds.recovery_state = "completed"
            final_ds.completed_at = now
            final_ds.processing_completed_at = now
            if final_ds.processing_started_at:
                final_ds.processing_duration_seconds = max(0.0, (now - final_ds.processing_started_at).total_seconds())

            total_psif = final_ds.incidents.filter(prediction__psif_predicted=True).count()
            total_non_psif = final_ds.incidents.filter(prediction__psif_predicted=False).count()

            final_ds.quality_summary = {
                **(final_ds.quality_summary or {}),
                "total": final_ds.processed_rows,
                "accepted": total_accepted,
                "accepted_with_warnings": total_warnings,
                "rejected": total_rejected,
                "rejections": all_rejections[:500],
                "psif_count": total_psif,
                "non_psif_count": total_non_psif,
            }

            if final_ds.error_rows > 0:
                final_ds.append_error(
                    f"Processing complete. Data Quality Summary: "
                    f"Accepted={total_accepted}, Accepted with warnings={total_warnings}, Rejected={total_rejected}. "
                    f"Classified PSIF Candidates={total_psif}, Non-PSIF={total_non_psif}."
                )

            final_ds.save(update_fields=[
                "status", "recovery_state", "total_rows", "completed_at",
                "processing_completed_at", "processing_duration_seconds",
                "error_log", "quality_summary"
            ])

            logger.info(
                "process_dataset COMPLETED: dataset=%s processed=%d errors=%d duration=%.1fs",
                dataset_id, final_ds.processed_rows, final_ds.error_rows,
                final_ds.processing_duration_seconds or 0.0,
            )

        # Trigger scoped backfill for any unpredicted incidents in this dataset outside the atomic transaction
        try:
            from django.core.management import call_command
            logger.info("Triggering backfill_predictions for dataset %s.", dataset_id)
            call_command("backfill_predictions", dataset_id=str(dataset_id))
        except Exception as e:
            logger.error("Failed to run post-processing backfills: %s", e)
            
        return {"status": "completed", "processed_rows": final_ds.processed_rows, "error_rows": final_ds.error_rows}

    except Exception as exc:
        error_detail = traceback.format_exc()
        logger.exception("process_dataset FAILED: dataset=%s", dataset_id)

        try:
            with transaction.atomic():
                now = timezone.now()
                fail_ds = Dataset.objects.select_for_update().get(id=dataset_id)
                fail_ds.status = Dataset.Status.FAILED
                fail_ds.recovery_state = "failed"
                fail_ds.completed_at = now
                fail_ds.processing_completed_at = now
                if fail_ds.processing_started_at:
                    fail_ds.processing_duration_seconds = max(0.0, (now - fail_ds.processing_started_at).total_seconds())
                fail_ds.append_error(f"Fatal error: {exc}\n\n{error_detail}")
                fail_ds.save(update_fields=[
                    "status", "recovery_state", "completed_at",
                    "processing_completed_at", "processing_duration_seconds", "error_log"
                ])
        except Exception:
            logger.exception("Failed to save FAILED status for dataset %s", dataset_id)

        raise


@shared_task(bind=True)
def watchdog_recover_stale_datasets_task(self, stale_timeout_seconds: int = 120) -> list[dict]:
    """
    Periodic Celery task / watchdog to detect crashed workers or stalled processing jobs
    and automatically recover them from their last durable checkpoint.
    """
    from .recovery import recover_stale_dataset_jobs
    recovered = recover_stale_dataset_jobs(stale_timeout_seconds=stale_timeout_seconds)
    logger.info("Watchdog scan completed: %d datasets recovered", len(recovered))
    return recovered


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_incident_embeddings_task(self, incident_ids: list[str], model_name: str = None, version: str = "v1") -> dict:
    """
    Asynchronous Celery task to generate embeddings for newly imported incidents.
    Idempotent: skips any incident that already has an embedding for the model/version.
    """
    from apps.incidents.models import Incident
    from apps.incidents.services.embedding import generate_and_persist_embeddings
    
    logger.info("generate_incident_embeddings_task started: %d incidents", len(incident_ids))
    try:
        incidents = list(Incident.objects.filter(id__in=incident_ids))
        created = generate_and_persist_embeddings(incidents, model_name=model_name, version=version)
        count = len(created) if created else 0
        logger.info("generate_incident_embeddings_task completed: %d new embeddings created", count)
        return {"status": "success", "created_count": count}
    except Exception as exc:
        logger.exception("generate_incident_embeddings_task failed: %s", exc)
        raise self.retry(exc=exc)

