import logging
import traceback
from celery import shared_task
from django.utils import timezone
from apps.predictions.models import ModelVersion

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def retrain_model_task(self, model_version_id, training_source=None, sample_limit=None):
    """
    Celery task to retrain the ML model asynchronously.
    Produces an inactive candidate model in READY status.
    """
    from ml_engine.training.trainer import run_training_pipeline
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


@shared_task(bind=True, max_retries=2, default_retry_delay=3)
def run_incident_prediction_task(self, incident_id: str) -> dict:
    """
    Dedicated Celery task executed by the ML worker to run DistilBERT + XGBoost + SHAP
    inference for an incident and persist the PredictionResult into PostgreSQL.
    """
    from apps.incidents.models import Incident, IOGPRuleTag
    from apps.predictions.models import ModelVersion, PredictionResult
    from ml_engine.model_inference import get_active_predictor
    from apps.incidents.services.embedding import generate_and_persist_embeddings
    from apps.predictions.iogp_classifier import classify_iogp_rules

    try:
        incident = Incident.objects.get(id=incident_id)
    except Incident.DoesNotExist:
        logger.error("run_incident_prediction_task: Incident %s not found.", incident_id)
        return {"status": "error", "message": f"Incident {incident_id} not found."}

    # 1. Retrieve active predictor and model version
    predictor = get_active_predictor()
    active_version = (
        ModelVersion.objects.filter(is_active=True, status=ModelVersion.Status.ACTIVE)
        .exclude(xgboost_artifact_path="")
        .first()
    )
    if not active_version:
        active_version = (
            ModelVersion.objects.filter(is_active=True)
            .exclude(xgboost_artifact_path="")
            .first()
        )
    if not active_version:
        active_version = ModelVersion.objects.filter(is_active=True).first()

    if not active_version or not predictor:
        logger.error("run_incident_prediction_task: No active model or predictor available on worker.")
        return {"status": "error", "message": "No active model or predictor available."}

    # 2. Execute inference
    record = incident.to_prediction_record()
    try:
        pred_output = predictor.predict(record)
    except Exception as exc:
        logger.exception("run_incident_prediction_task: ML inference failed for incident %s", incident_id)
        raise self.retry(exc=exc)

    # 3. Persist PredictionResult
    pred_res, created = PredictionResult.objects.update_or_create(
        incident=incident,
        defaults={
            "model_version": active_version,
            "psif_probability": pred_output.psif_probability,
            "psif_predicted": pred_output.psif_predicted,
            "risk_level": pred_output.risk_level,
            "top_factors": pred_output.top_factors,
            "is_sparse_input": getattr(pred_output, "is_sparse_input", False),
            "evidence_strength": getattr(pred_output, "evidence_strength", "MODERATE"),
            "explanation_detail": getattr(pred_output, "explanation", {}),
        },
    )

    # 4. Generate and persist embeddings
    try:
        generate_and_persist_embeddings([incident])
    except Exception as e:
        logger.warning("Embedding generation failed for incident %s: %s", incident_id, e)

    # 5. IOGP classification
    try:
        fields_to_check = {
            "description": incident.description,
            "job_task": incident.job_task,
            "equipment_involved": incident.equipment_involved,
            "immediate_cause": incident.immediate_cause,
            "corrective_actions": incident.corrective_actions,
            "location": incident.location,
            "composite_narrative": incident.composite_narrative,
        }
        iogp_results = classify_iogp_rules(fields_to_check)
        for res in iogp_results:
            IOGPRuleTag.objects.get_or_create(
                incident=incident,
                rule=res["rule"],
                defaults={
                    "matched_keywords": res["matched_keywords"],
                    "matched_fields": res["matched_fields"],
                    "classification_method": res["classification_method"],
                },
            )
    except Exception as e:
        logger.warning("IOGP classification failed for incident %s: %s", incident_id, e)

    logger.info(
        "run_incident_prediction_task: Successfully predicted incident %s | score=%.4f predicted=%s",
        incident.id, pred_output.psif_probability, pred_output.psif_predicted
    )

    return {
        "status": "success",
        "incident_id": str(incident.id),
        "prediction_id": str(pred_res.id),
        "psif_score": pred_output.psif_probability,
        "psif_predicted": pred_output.psif_predicted,
        "risk_level": pred_output.risk_level,
        "model_version": active_version.version_label,
    }
