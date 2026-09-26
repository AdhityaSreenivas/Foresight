import logging
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.datasets.permissions import CanRunPrediction
from apps.incidents.models import Incident
from ml_engine.model_inference import get_active_predictor
from .models import ModelVersion, PredictionResult
from .serializers import PredictRequestSerializer, ModelVersionSerializer

logger = logging.getLogger(__name__)

class PredictView(APIView):
    """
    POST /api/predict/

    Accepts incident fields, creates a manual Incident record, runs ML inference,
    and returns the prediction result. Enforces that only authorized roles can run
    predictions.
    """
    permission_classes = [CanRunPrediction]

    def post(self, request, *args, **kwargs):
        serializer = PredictRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 1. Centralized Data Quality Gate (Reject insufficient / low-quality data before analysis)
        from apps.incidents.services.data_quality import validate_incident_for_analysis
        gate_res = validate_incident_for_analysis(data)
        if not gate_res["accepted"]:
            return Response(
                {
                    "accepted": False,
                    "error": "Data quality is insufficient for analysis.",
                    "quality_status": gate_res["quality_status"],
                    "blocking_findings": gate_res["blocking_findings"],
                    "warning_findings": gate_res["warning_findings"],
                    "missing_fields": gate_res["missing_fields"],
                    "reason": gate_res["reason"],
                    "quality_version": gate_res["quality_version"],
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1.5. Ensure an active model version exists in the registry
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

        if not active_version:
            logger.warning("PredictView: No active ModelVersion found in registry.")
            return Response(
                {"error": "No active model is currently available to serve predictions."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        # 2. Prepare narrative composite for prediction
        from apps.datasets.ingestion import build_composite_narrative, _normalise_severity_actual, _normalise_severity_potential
        
        incident_kwargs = {
            "dataset": None,
            "raw_row": {"_manual_prediction": True},
            "incident_date": data.get("incident_date"),
            "location": data.get("location"),
            "job_task": data.get("job_task"),
            "equipment_involved": data.get("equipment_involved"),
            "description": data.get("description"),
            "corrective_actions": data.get("corrective_actions"),
            "witness_statement": data.get("witness_statement"),
            "department": data.get("department"),
            "injury_type": data.get("injury_type"),
            "body_part": data.get("body_part"),
            "immediate_cause": data.get("immediate_cause"),
            "root_cause_category": data.get("root_cause_category"),
            "severity_actual": _normalise_severity_actual(data.get("severity_actual")),
            "severity_potential": _normalise_severity_potential(data.get("severity_potential")),
            "near_miss": data.get("near_miss"),
        }

        # Build composite narrative for the model
        composite = build_composite_narrative(
            description=incident_kwargs.get("description"),
            corrective_actions=incident_kwargs.get("corrective_actions"),
            witness_statement=incident_kwargs.get("witness_statement"),
        )
        incident_kwargs["composite_narrative"] = composite or None

        # 3. Create Incident in its own transaction so it commits immediately
        with transaction.atomic():
            incident = Incident.objects.create(**incident_kwargs)
            from apps.incidents.models import IncidentDataQuality
            IncidentDataQuality.objects.create(
                incident=incident,
                status=gate_res["quality_status"],
                findings=gate_res["findings"],
                quality_version=gate_res["quality_version"],
            )

        # 4. Run Inference (local predictor if ML runtime present, or Celery ML worker if serverless)
        predictor = get_active_predictor()
        if predictor is not None:
            record = incident.to_prediction_record()
            try:
                pred_output = predictor.predict(record)
            except Exception as exc:
                logger.exception("Prediction failed during manual API request.")
                return Response(
                    {"error": "Inference failed due to an internal model error."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Persist PredictionResult
            prediction_result = PredictionResult.objects.create(
                incident=incident,
                model_version=active_version,
                psif_probability=pred_output.psif_probability,
                psif_predicted=pred_output.psif_predicted,
                risk_level=pred_output.risk_level,
                top_factors=pred_output.top_factors,
                is_sparse_input=getattr(pred_output, "is_sparse_input", False),
                evidence_strength=getattr(pred_output, "evidence_strength", "MODERATE"),
                explanation_detail=getattr(pred_output, "explanation", {}),
            )

            from apps.incidents.services.embedding import generate_and_persist_embeddings
            try:
                generate_and_persist_embeddings([incident])
            except Exception:
                pass
        else:
            # Serverless edge runtime (e.g. Vercel) -> Delegate to Celery ML Worker
            import time

            try:
                from apps.predictions.tasks import run_incident_prediction_task
                task_res = run_incident_prediction_task.delay(str(incident.id))
            except Exception as exc:
                logger.exception("Failed to dispatch prediction task to Celery broker.")
                return Response(
                    {"error": "ML inference queue is temporarily unavailable.", "detail": str(exc)},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # Wait briefly (up to 8s) for dedicated Celery worker to finish
            prediction_result = None
            start_time = time.time()
            while time.time() - start_time < 8.0:
                prediction_result = PredictionResult.objects.filter(incident=incident).first()
                if prediction_result:
                    break
                time.sleep(0.3)

            if not prediction_result:
                return Response(
                    {
                        "status": "queued",
                        "incident_id": str(incident.id),
                        "task_id": task_res.id,
                        "model_version": active_version.version_label,
                        "message": "Inference task queued to dedicated ML worker.",
                    },
                    status=status.HTTP_202_ACCEPTED,
                )

        # 5. IOGP Classification
        from apps.incidents.models import IOGPRuleTag
        iogp_tags = list(IOGPRuleTag.objects.filter(incident=incident))
        if not iogp_tags:
            from apps.predictions.iogp_classifier import classify_iogp_rules
            fields_to_check = {
                "description": incident.description,
                "job_task": incident.job_task,
                "equipment_involved": incident.equipment_involved,
                "immediate_cause": incident.immediate_cause,
                "corrective_actions": incident.corrective_actions,
                "location": incident.location,
                "composite_narrative": incident.composite_narrative
            }
            iogp_results = classify_iogp_rules(fields_to_check)
            for res in iogp_results:
                IOGPRuleTag.objects.create(
                    incident=incident,
                    rule=res["rule"],
                    matched_keywords=res["matched_keywords"],
                    matched_fields=res["matched_fields"],
                    classification_method=res["classification_method"],
                    classifier_version=res.get("classifier_version", "1.0.0"),
                    confidence=res.get("confidence", 0.0),
                )
        else:
            iogp_results = [
                {
                    "rule": tag.rule,
                    "matched_keywords": tag.matched_keywords,
                    "matched_fields": tag.matched_fields,
                    "classification_method": tag.classification_method,
                    "classifier_version": tag.classifier_version,
                    "confidence": tag.confidence,
                }
                for tag in iogp_tags
            ]

        # 5.6 Build canonical triage stages
        from apps.incidents.services.decision_trace import build_analytical_assessment
        assessment = build_analytical_assessment(incident)
        triage_stages = assessment.get("triage_stages")

        # 6. Return response
        return Response({
            "incident_id": str(incident.id),
            "model_version": active_version.version_label,
            "psif_score": prediction_result.psif_score,
            "psif_predicted": prediction_result.psif_predicted,
            "binary_classification": prediction_result.binary_classification,
            "evidence_strength": prediction_result.evidence_strength,
            "risk_level": prediction_result.risk_level,
            "top_factors": prediction_result.top_factors,
            "explanation": prediction_result.explanation_detail,
            "is_sparse_input": prediction_result.is_sparse_input,
            "threshold_used": active_version.metrics.get("selected_threshold", active_version.metrics.get("optimal_threshold", 0.5)),
            "iogp_rules": iogp_results,
            "triage_stages": triage_stages,
        }, status=status.HTTP_200_OK)


class ModelListAPIView(APIView):
    """GET /api/models/"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        from django.db.models import F
        from apps.predictions.timing import calculate_retraining_timing
        models = list(ModelVersion.objects.all().order_by(F('trained_at').desc(nulls_first=True)))
        for m in models:
            if isinstance(m.metrics, dict):
                timing = calculate_retraining_timing(m, current_metrics=m.metrics)
                m.metrics.update(timing)
        serializer = ModelVersionSerializer(models, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ModelTrainingSourcesAPIView(APIView):
    """
    GET /api/models/training-sources/
    Returns live eligibility counts and readiness status for training sources.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from ml_engine.training.training_sources import get_training_sources_overview
        refresh = request.GET.get("refresh", "").lower() in ("true", "1", "yes")
        data = get_training_sources_overview(use_cache=not refresh)
        return Response(data, status=status.HTTP_200_OK)


class ModelRetrainAPIView(APIView):
    """POST /api/models/retrain/"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        # Model Management Permissions: admin allowed; safety_officer and analyst denied.
        if not request.user.is_staff and getattr(request.user, "role", None) != "admin":
            return Response(
                {"detail": "You do not have permission to retrain models. Only administrators may trigger retraining."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Read training_source
        raw_source = request.data.get("training_source", "SYNTHETIC")
        if not isinstance(raw_source, str):
            raw_source = "SYNTHETIC"
        training_source = raw_source.upper().strip()

        from ml_engine.training.training_sources import TrainingSource
        if training_source == "HEURISTIC":
            return Response(
                {
                    "error": (
                        "The 'HEURISTIC' training source has been eliminated. Former heuristic data has been audited and "
                        "reclassified as SYNTHETIC. Valid options are: SYNTHETIC, HUMAN_APPROVED_SYNTHETIC."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if training_source not in (TrainingSource.SYNTHETIC, TrainingSource.HUMAN_APPROVED_SYNTHETIC):
            return Response(
                {
                    "error": (
                        f"Invalid training_source '{training_source}'. "
                        "Must be 'SYNTHETIC' or 'HUMAN_APPROVED_SYNTHETIC'."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        sample_limit = request.data.get("sample_limit")
        if sample_limit is not None:
            try:
                sample_limit = int(sample_limit)
                if sample_limit <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return Response(
                    {"error": "sample_limit must be a positive integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        # Guard: prevent concurrent retraining runs
        running_models = ModelVersion.objects.filter(status=ModelVersion.Status.RUNNING)
        if running_models.exists():
            running_label = running_models.first().version_label
            return Response(
                {
                    "error": (
                        f"A model retraining run is already in progress ({running_label}). "
                        "Please wait for it to complete before initiating another."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Create candidate ModelVersion record in PENDING state
        timestamp_str = timezone.now().strftime("%Y%m%d_%H%M%S")
        version_label = f"v_{timestamp_str}"
        from django.conf import settings
        from apps.predictions.timing import calculate_retraining_timing
        now_iso = timezone.now().isoformat()
        initial_metrics = {
            "training_source": training_source,
            "training_status": "PENDING",
            "progress_pct": 1,
            "stage_code": "PENDING",
            "current_stage": "Enqueued in Celery task queue, awaiting worker dispatch...",
            "is_candidate": True,
            "enqueued_at": now_iso,
            "started_at": now_iso,
            "sample_limit": sample_limit,
        }
        
        new_model = ModelVersion(
            version_label=version_label,
            bert_model_name=getattr(settings, "BERT_MODEL_NAME", "distilbert-base-uncased"),
            xgboost_artifact_path="",
            encoder_artifact_path="",
            training_snapshot_path="",
            status=ModelVersion.Status.PENDING,
            is_active=False,
            metrics=initial_metrics,
        )
        timing_init = calculate_retraining_timing(new_model, current_metrics=initial_metrics)
        new_model.metrics.update(timing_init)
        new_model.save()

        # Dispatch Celery task
        from apps.predictions.tasks import retrain_model_task
        task = retrain_model_task.delay(
            new_model.id,
            training_source=training_source,
            sample_limit=sample_limit,
        )

        return Response({
            "message": f"Controlled retraining ({training_source}) enqueued. Candidate model is in PENDING state.",
            "status": "success",
            "model_version_id": str(new_model.id),
            "version_label": new_model.version_label,
            "training_source": training_source,
            "task_id": task.id,
            "model_status": new_model.status,
        }, status=status.HTTP_202_ACCEPTED)


class CancelTrainingAPIView(APIView):
    """
    DELETE /api/models/<uuid:model_id>/cancel/

    Terminates an in-progress or queued model training run.

    Safety rules enforced:
    - Only PENDING or RUNNING candidates may be cancelled.
    - Active models (is_active=True) and READY/ACTIVE/FAILED versions are never touched.
    - Revokes the Celery task (if a celery_task_id is recorded in metrics).
    - Deletes partial on-disk artifact directory for this version only.
    - Marks the ModelVersion record as FAILED with cancelled_at timestamp.
    - Only administrators may cancel training runs.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, model_id, *args, **kwargs):
        import shutil
        from pathlib import Path
        from django.utils import timezone as tz

        # Admin-only
        if not request.user.is_staff and getattr(request.user, "role", None) != "admin":
            return Response(
                {"detail": "Only administrators may cancel model training runs."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            mv = ModelVersion.objects.get(id=model_id)
        except ModelVersion.DoesNotExist:
            return Response({"error": f"ModelVersion {model_id} not found."}, status=status.HTTP_404_NOT_FOUND)

        # Safety: never cancel the active model or completed/ready versions
        if mv.is_active:
            return Response(
                {"error": "Cannot cancel the active model. Only PENDING or RUNNING candidates can be cancelled."},
                status=status.HTTP_409_CONFLICT,
            )
        if mv.status not in (ModelVersion.Status.PENDING, ModelVersion.Status.RUNNING):
            return Response(
                {
                    "error": f"ModelVersion '{mv.version_label}' has status '{mv.status}' and cannot be cancelled. "
                             "Only PENDING or RUNNING candidates may be terminated."
                },
                status=status.HTTP_409_CONFLICT,
            )

        # 1. Revoke the Celery task if we have its ID
        celery_task_id = (mv.metrics or {}).get("celery_task_id")
        revoke_result = None
        if celery_task_id:
            try:
                from celery.app.control import Control
                from config.celery import app as celery_app
                celery_app.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
                revoke_result = f"Celery task {celery_task_id} revoked."
                logger.info(f"CancelTrainingAPIView: Revoked Celery task {celery_task_id} for {mv.version_label}")
            except Exception as exc:
                logger.warning(f"CancelTrainingAPIView: Could not revoke Celery task {celery_task_id}: {exc}")
                revoke_result = f"Could not revoke Celery task ({exc}); record still cancelled."

        # 2. Delete partial on-disk artifact directory for this version only
        deleted_paths = []
        artifact_dirs_to_check = []

        # Check the standard artifacts directory
        from django.conf import settings as django_settings
        base_dir = getattr(django_settings, "BASE_DIR", None)
        if base_dir and mv.version_label:
            candidate_dir = Path(str(base_dir)) / "ml_engine" / "artifacts" / mv.version_label
            artifact_dirs_to_check.append(candidate_dir)

        # Also check the xgboost_artifact_path parent directory if set
        if mv.xgboost_artifact_path:
            xgb_path = Path(mv.xgboost_artifact_path)
            candidate_dir_from_path = xgb_path.parent if xgb_path.parent.name == mv.version_label else None
            if candidate_dir_from_path and candidate_dir_from_path not in artifact_dirs_to_check:
                artifact_dirs_to_check.append(candidate_dir_from_path)

        for artifact_dir in artifact_dirs_to_check:
            if artifact_dir.exists() and artifact_dir.is_dir():
                # Double-safety: directory name must match the version label
                if artifact_dir.name == mv.version_label:
                    try:
                        shutil.rmtree(str(artifact_dir))
                        deleted_paths.append(str(artifact_dir))
                        logger.info(f"CancelTrainingAPIView: Deleted artifact dir {artifact_dir}")
                    except Exception as exc:
                        logger.warning(f"CancelTrainingAPIView: Could not delete {artifact_dir}: {exc}")

        # 3. Mark the record as FAILED (cancelled) and save
        metrics = mv.metrics if isinstance(mv.metrics, dict) else {}
        metrics["training_status"] = "CANCELLED"
        metrics["stage_code"] = "CANCELLED"
        metrics["current_stage"] = "Training cancelled by administrator."
        metrics["progress_pct"] = 0
        metrics["cancelled_at"] = tz.now().isoformat()
        metrics["cancelled_by"] = request.user.username or str(request.user.id)
        if celery_task_id:
            metrics["celery_revoke_result"] = revoke_result

        mv.status = ModelVersion.Status.FAILED
        mv.metrics = metrics
        mv.save(update_fields=["status", "metrics"])

        logger.info(
            f"CancelTrainingAPIView: Cancelled ModelVersion {mv.version_label} "
            f"(id={mv.id}) by {request.user.username}. "
            f"Deleted paths: {deleted_paths}"
        )

        return Response({
            "message": f"Training run '{mv.version_label}' has been cancelled and its partial artifacts deleted.",
            "version_label": mv.version_label,
            "model_version_id": str(mv.id),
            "final_status": mv.status,
            "celery_revoke": revoke_result,
            "deleted_artifact_paths": deleted_paths,
        }, status=status.HTTP_200_OK)


class ModelStatusAPIView(APIView):
    """GET /api/models/<uuid:model_id>/status/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, model_id, *args, **kwargs):
        try:
            model = ModelVersion.objects.get(id=model_id)
        except ModelVersion.DoesNotExist:
            return Response({"error": f"ModelVersion {model_id} not found."}, status=status.HTTP_404_NOT_FOUND)

        metrics = model.metrics or {}
        audit = metrics.get("label_audit", {})
        provenance = metrics.get("metric_provenance", {})

        from apps.predictions.timing import calculate_retraining_timing
        timing_data = calculate_retraining_timing(model, current_metrics=metrics)

        raw_progress = metrics.get("progress_pct", 0)
        try:
            clamped_progress = max(0, min(100, int(raw_progress)))
        except (ValueError, TypeError):
            clamped_progress = 0

        return Response({
            "model_version_id": str(model.id),
            "version_label": model.version_label,
            "status": model.status,
            "is_active": model.is_active,
            "trained_at": model.trained_at.isoformat() if model.trained_at else None,
            "training_status": metrics.get("training_status", model.status),
            "training_source": metrics.get("training_source"),
            "validation_basis": metrics.get("validation_basis") or provenance.get("validation_basis"),
            "disclaimer": metrics.get("disclaimer") or provenance.get("disclaimer"),
            "training_error": metrics.get("training_error"),
            "progress_pct": clamped_progress,
            "progress": clamped_progress,
            "current_stage": metrics.get("current_stage", ""),
            "stage": metrics.get("stage_code", ""),
            "stage_code": metrics.get("stage_code", ""),
            "stage_progress": metrics.get("stage_progress", metrics.get("progress_pct", 0)),
            "processed_units": metrics.get("processed_units"),
            "total_units": metrics.get("total_units"),
            "elapsed_seconds": timing_data.get("elapsed_seconds"),
            "estimated_total_seconds": timing_data.get("estimated_total_seconds"),
            "estimated_remaining_seconds": timing_data.get("estimated_remaining_seconds"),
            "estimate_source": timing_data.get("estimate_source", "LIVE_THROUGHPUT"),
            "formatted_elapsed": timing_data.get("formatted_elapsed"),
            "formatted_remaining": timing_data.get("formatted_remaining"),
            "formatted_total": timing_data.get("formatted_total"),
            "formatted_duration": timing_data.get("formatted_duration"),
            "started_at": metrics.get("started_at"),
            "enqueued_at": metrics.get("enqueued_at"),
            "training_snapshot_path": model.training_snapshot_path,
            "training_duration_seconds": timing_data.get("training_duration_seconds") or metrics.get("training_duration_seconds"),
            "selected_threshold": metrics.get("selected_threshold"),
            "test_metrics": metrics.get("metrics_final_test") or metrics.get("metrics_fused_test"),
            "metric_provenance": provenance,
            "counts": audit.get("provenance_counts"),
            "training_eligible_count": audit.get("training_eligible"),
            "training_excluded_count": audit.get("training_excluded"),
        }, status=status.HTTP_200_OK)


class ModelActivateAPIView(APIView):
    """
    POST /api/models/<uuid:model_id>/activate/
    
    Controlled promotion gate enforcing strict 9-point activation safety check:
    1. ModelVersion.status == READY
    2. Candidate is currently inactive (is_active == False)
    3. Training completed successfully (training_status == 'READY')
    4. Required evaluation metrics exist (precision, recall, f1, roc_auc)
    5. model.json exists on disk and loads successfully via XGBoost
    6. encoder.joblib exists on disk and loads successfully via joblib
    7. metadata.json exists on disk and is internally consistent
    8. Authorized admin permission
    9. Atomic database transaction deactivating previous active model and activating candidate
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, model_id, *args, **kwargs):
        import os
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

        import json
        from pathlib import Path
        import joblib
        try:
            import xgboost as xgb
        except ImportError:
            xgb = None

        # 8. Check authorized admin permission
        if not request.user.is_staff and getattr(request.user, "role", None) != "admin":
            return Response(
                {"error": "Forbidden: Only administrators are authorized to promote or activate models."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            candidate = ModelVersion.objects.get(id=model_id)
        except ModelVersion.DoesNotExist:
            return Response({"error": f"ModelVersion {model_id} not found."}, status=status.HTTP_404_NOT_FOUND)

        # 1. Check ModelVersion.status == READY
        if candidate.status != ModelVersion.Status.READY:
            return Response(
                {"error": f"Activation safety gate failed: Model status must be READY, but is '{candidate.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Check candidate is currently inactive
        if candidate.is_active:
            return Response(
                {"error": "Activation safety gate failed: Model is already active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Check training completed successfully
        metrics = candidate.metrics if isinstance(candidate.metrics, dict) else {}
        training_status = metrics.get("training_status")
        if training_status not in ("READY", "SUCCESS"):
            return Response(
                {"error": f"Activation safety gate failed: Model training status is '{training_status}', expected 'READY'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Check required evaluation metrics exist
        test_metrics = metrics.get("metrics_final_test") or metrics.get("metrics_fused_test") or {}
        required_metric_keys = ["precision", "recall", "f1", "roc_auc"]
        missing_metrics = [k for k in required_metric_keys if k not in test_metrics or test_metrics[k] is None]
        if missing_metrics:
            return Response(
                {"error": f"Activation safety gate failed: Missing required evaluation metrics: {missing_metrics}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5. Check model.json exists and loads successfully
        if not candidate.xgboost_artifact_path:
            return Response(
                {"error": "Activation safety gate failed: xgboost_artifact_path is empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        model_file = Path(candidate.xgboost_artifact_path)
        if not model_file.exists():
            return Response(
                {"error": f"Activation safety gate failed: model.json file not found at {model_file}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if xgb is not None:
            try:
                booster = xgb.Booster()
                booster.load_model(str(model_file))
            except Exception as e:
                return Response(
                    {"error": f"Activation safety gate failed: Corrupted XGBoost model file: {e}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 6. Check encoder.joblib exists and loads successfully
        if not candidate.encoder_artifact_path:
            return Response(
                {"error": "Activation safety gate failed: encoder_artifact_path is empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        encoder_file = Path(candidate.encoder_artifact_path)
        if not encoder_file.exists():
            return Response(
                {"error": f"Activation safety gate failed: encoder.joblib file not found at {encoder_file}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            encoder = joblib.load(str(encoder_file))
            if not hasattr(encoder, "feature_names_") and not hasattr(encoder, "transform"):
                return Response(
                    {"error": "Activation safety gate failed: Loaded encoder object is invalid or unpickled improperly."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            return Response(
                {"error": f"Activation safety gate failed: Corrupted encoder.joblib file: {e}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 7. Check metadata.json exists and is internally consistent
        metadata_file = model_file.parent / "metadata.json"
        if not metadata_file.exists():
            return Response(
                {"error": f"Activation safety gate failed: metadata.json not found at {metadata_file}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with open(metadata_file) as f:
                disk_meta = json.load(f)
            if disk_meta.get("model_version") != candidate.version_label:
                return Response(
                    {"error": f"Activation safety gate failed: Metadata version mismatch ('{disk_meta.get('model_version')}' != '{candidate.version_label}')."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            return Response(
                {"error": f"Activation safety gate failed: Invalid metadata.json: {e}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 8. Check training_snapshot.json exists and is strictly linked
        snapshot_path_str = candidate.training_snapshot_path or str(model_file.parent / "training_snapshot.json")
        snapshot_file = Path(snapshot_path_str)
        if not snapshot_file.exists():
            return Response(
                {"error": f"Activation safety gate failed: training_snapshot.json not found at {snapshot_file}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with open(snapshot_file) as f:
                disk_snapshot = json.load(f)
            snapshot_id = disk_snapshot.get("snapshot_id")
            if not snapshot_id:
                return Response(
                    {"error": "Activation safety gate failed: training_snapshot.json missing 'snapshot_id'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if disk_snapshot.get("model_version_label") != candidate.version_label:
                return Response(
                    {"error": f"Activation safety gate failed: Snapshot model version mismatch ('{disk_snapshot.get('model_version_label')}' != '{candidate.version_label}')."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Verify snapshot ID linkage across metadata and snapshot
            meta_snapshot_id = disk_meta.get("training_snapshot_id")
            if meta_snapshot_id and meta_snapshot_id != snapshot_id:
                return Response(
                    {"error": f"Activation safety gate failed: Snapshot ID mismatch between metadata.json ({meta_snapshot_id}) and training_snapshot.json ({snapshot_id})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Verify dataset hash consistency
            if disk_meta.get("dataset_hash") and disk_snapshot.get("dataset_hash"):
                if disk_meta.get("dataset_hash") != disk_snapshot.get("dataset_hash"):
                    return Response(
                        {"error": "Activation safety gate failed: Dataset hash mismatch between metadata.json and training_snapshot.json."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        except Exception as e:
            return Response(
                {"error": f"Activation safety gate failed: Invalid training_snapshot.json: {e}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 9. Atomic transaction
        with transaction.atomic():
            # Deactivate currently active models and reset their status to READY
            ModelVersion.objects.filter(is_active=True).update(
                is_active=False,
                status=ModelVersion.Status.READY,
            )
            candidate.is_active = True
            candidate.status = ModelVersion.Status.ACTIVE
            candidate.save(update_fields=["is_active", "status"])

        # Invalidate cached predictor singleton so new active model loads on next prediction
        try:
            from ml_engine.model_inference import reset_active_predictor
            reset_active_predictor()
        except Exception as e:
            logger.warning("Failed to reset active predictor singleton: %s", e)

        logger.info(
            "Controlled model promotion: Candidate %s successfully promoted to ACTIVE by user %s",
            candidate.version_label, request.user.username,
        )

        return Response({
            "message": f"Candidate model {candidate.version_label} passed all 9 safety checks and was successfully activated.",
            "status": "success",
            "active_model_id": str(candidate.id),
            "version_label": candidate.version_label,
            "model_status": candidate.status,
            "is_active": candidate.is_active,
        }, status=status.HTTP_200_OK)


class ModelCompareAPIView(APIView):
    """GET /api/models/<uuid:model_id>/compare/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, model_id, *args, **kwargs):
        try:
            candidate = ModelVersion.objects.get(id=model_id)
        except ModelVersion.DoesNotExist:
            return Response({"error": f"Candidate model {model_id} not found."}, status=status.HTTP_404_NOT_FOUND)

        active = ModelVersion.objects.filter(is_active=True).first()

        def extract_comparison_data(m):
            if not m:
                return None
            met = m.metrics if isinstance(m.metrics, dict) else {}
            test_m = met.get("metrics_final_test") or met.get("metrics_fused_test") or {}
            audit = met.get("label_audit", {})
            prov = audit.get("provenance_counts", {})
            return {
                "id": str(m.id),
                "version_label": m.version_label,
                "status": m.status,
                "is_active": m.is_active,
                "trained_at": m.trained_at.isoformat() if m.trained_at else None,
                "selected_threshold": met.get("selected_threshold", 0.10),
                "precision": test_m.get("precision"),
                "recall": test_m.get("recall"),
                "f1": test_m.get("f1"),
                "f2": test_m.get("f2"),
                "roc_auc": test_m.get("roc_auc"),
                "pr_auc": test_m.get("pr_auc"),
                "false_negatives": test_m.get("false_negatives"),
                "test_sample_size": met.get("test_row_count"),
                "training_sample_size": met.get("train_row_count"),
                "total_labeled_rows": met.get("total_labeled_rows"),
                "provenance_breakdown": prov,
            }

        return Response({
            "candidate": extract_comparison_data(candidate),
            "active": extract_comparison_data(active),
        }, status=status.HTTP_200_OK)
