import logging
import traceback
from celery import shared_task
from django.utils import timezone
from apps.predictions.models import ModelVersion
from ml_engine.training.trainer import run_training_pipeline

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def retrain_model_task(self, model_version_id, training_source=None, sample_limit=None):
    """
    Celery task to retrain the ML model asynchronously.
    Produces an inactive candidate model in READY status.
    """
    try:
        model_version = ModelVersion.objects.get(id=model_version_id)
    except ModelVersion.DoesNotExist:
        logger.error(f"retrain_model_task: ModelVersion {model_version_id} not found.")
        return

    if not training_source and isinstance(model_version.metrics, dict):
        training_source = model_version.metrics.get("training_source", "HUMAN")

    logger.info(
        f"Starting controlled retraining for candidate ModelVersion {model_version.version_label} "
        f"(Source: {training_source})"
    )

    # 1. Transition to RUNNING state
    model_version.status = ModelVersion.Status.RUNNING
    if not isinstance(model_version.metrics, dict):
        model_version.metrics = {}
    model_version.metrics["training_status"] = "RUNNING"
    model_version.metrics["training_source"] = training_source
    model_version.metrics["progress_pct"] = 3
    model_version.metrics["stage_code"] = "INITIALIZATION"
    model_version.metrics["current_stage"] = "Task dispatched to worker; initializing pipeline..."
    if not model_version.metrics.get("started_at"):
        model_version.metrics["started_at"] = timezone.now().isoformat()
    if getattr(self, "request", None) and self.request.id:
        model_version.metrics["celery_task_id"] = self.request.id

    from apps.predictions.timing import calculate_retraining_timing
    timing_init = calculate_retraining_timing(model_version, current_metrics=model_version.metrics)
    model_version.metrics.update(timing_init)
    model_version.save(update_fields=["status", "metrics"])

    try:
        # 2. Execute training pipeline on existing ModelVersion instance
        summary = run_training_pipeline(
            model_version=model_version,
            training_source=training_source,
            sample_limit=sample_limit,
        )

        # 3. ModelVersion is updated by trainer.py; refresh and finalize status
        model_version.refresh_from_db()
        model_version.status = ModelVersion.Status.READY
        model_version.is_active = False  # STRICT: Candidate model remains inactive until explicit promotion
        if not isinstance(model_version.metrics, dict):
            model_version.metrics = {}
        if isinstance(summary, dict):
            model_version.metrics.update(summary)
        model_version.metrics["training_status"] = "READY"
        model_version.metrics["progress_pct"] = 100
        model_version.metrics["stage_code"] = "COMPLETED"
        model_version.metrics["current_stage"] = "Retraining complete — candidate model ready for review."
        if not model_version.metrics.get("completed_at"):
            model_version.metrics["completed_at"] = timezone.now().isoformat()

        # Finalize and freeze timing
        timing_final = calculate_retraining_timing(model_version, current_metrics=model_version.metrics)
        model_version.metrics.update(timing_final)
        model_version.save()

        logger.info(
            f"Retraining successful for candidate ModelVersion {model_version.version_label} "
            f"(Status: READY, is_active: False, Duration: {model_version.metrics.get('formatted_duration')})"
        )

    except Exception as e:
        logger.exception(f"Retraining failed for candidate ModelVersion {model_version.version_label}")
        model_version.refresh_from_db()
        model_version.status = ModelVersion.Status.FAILED
        if not isinstance(model_version.metrics, dict):
            model_version.metrics = {}
        model_version.metrics["training_status"] = "FAILED"
        model_version.metrics["progress_pct"] = 0
        model_version.metrics["stage_code"] = "FAILED"
        model_version.metrics["current_stage"] = f"Failed: {str(e)}"
        model_version.metrics["training_error"] = str(e)
        model_version.metrics["traceback"] = traceback.format_exc()
        model_version.metrics["failed_at"] = timezone.now().isoformat()

        from apps.predictions.timing import calculate_retraining_timing
        timing_fail = calculate_retraining_timing(model_version, current_metrics=model_version.metrics)
        model_version.metrics.update(timing_fail)
        model_version.save(update_fields=["status", "metrics"])
