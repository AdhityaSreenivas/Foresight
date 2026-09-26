"""
REST API views for Model Assurance & Governance (Task 12).
apps/predictions/assurance_api_views.py
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.predictions.services.assurance_service import ModelAssuranceService


class ModelAssuranceRootAPIView(APIView):
    """
    GET /api/model-assurance/
    Returns platform-wide Model Assurance root payload including active model card,
    summary of registered models, human review audit, and methodology notices.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        audit = ModelAssuranceService.get_model_registry_audit()
        human_audit = ModelAssuranceService.get_human_review_audit()
        payload = {
            "status": "ok",
            "active_model": audit.get("active_model"),
            "registered_models_count": audit.get("registered_models_count"),
            "platform_predictions_summary": audit.get("platform_predictions_summary"),
            "human_review_audit": human_audit,
            "methodology_statement": audit.get("methodology_statement"),
            "score_semantics_rule": audit.get("score_semantics_rule"),
            "timestamp": audit.get("timestamp"),
        }
        return Response(payload, status=status.HTTP_200_OK)


class ModelRegistryAuditAPIView(APIView):
    """
    GET /api/model-assurance/models/
    Returns full audit of all registered models in the database.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        audit = ModelAssuranceService.get_model_registry_audit()
        return Response({
            "status": "ok",
            "count": audit.get("registered_models_count"),
            "models": audit.get("models"),
            "timestamp": audit.get("timestamp"),
        }, status=status.HTTP_200_OK)


class ModelMetricsAuditAPIView(APIView):
    """
    GET /api/model-assurance/metrics/
    Returns detailed evaluation metrics for active model with independent denominators,
    split methodology, sample counts, and leakage disclosures.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        audit = ModelAssuranceService.get_model_registry_audit()
        active = audit.get("active_model")
        if not active:
            return Response({
                "status": "warning",
                "message": "No active model version currently configured.",
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "status": "ok",
            "model_version": active["version_label"],
            "threshold": active["threshold"],
            "threshold_methodology": active["threshold_methodology"],
            "evaluation_metrics": active["evaluation_metrics"],
            "sample_counts": active["sample_counts"],
            "split_methodology": active["split_methodology"],
            "validation_basis": active["validation_basis"],
            "leakage_controls": active["leakage_controls"],
            "synthetic_artifacts_and_risks": active["synthetic_artifacts_and_risks"],
            "timestamp": audit.get("timestamp"),
        }, status=status.HTTP_200_OK)


class HumanReviewAuditAPIView(APIView):
    """
    GET /api/model-assurance/human-review/
    Returns completely honest disclosure of human review records:
    Real human validation count is strictly 0.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        audit = ModelAssuranceService.get_human_review_audit()
        return Response(audit, status=status.HTTP_200_OK)


class ProductionDiagnosticAPIView(APIView):
    """
    GET /api/model-assurance/diagnostic/
    Safe, authenticated production diagnostic endpoint.
    Restricted strictly to authenticated administrative users.
    Returns database connection metadata, table counts, artifact availability,
    and serverless runtime introspection without exposing secrets.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (request.user.is_staff or getattr(request.user, "is_admin_role", False) or getattr(request.user, "role", "") in ("admin", "admin_flow")):
            return Response({"error": "Administrative privileges required."}, status=status.HTTP_403_FORBIDDEN)

        import importlib.util
        import os
        from pathlib import Path
        from django.db import connection
        from django.conf import settings

        # 1. Database Connection Introspection
        db_info = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user, inet_server_addr(), version();")
                db_row = cursor.fetchone()
                db_info["database_name"] = db_row[0]
                db_info["current_user"] = db_row[1]
                db_info["server_addr"] = str(db_row[2])
                db_info["engine_version"] = db_row[3]

                host = connection.settings_dict.get("HOST", "")
                db_info["host"] = host
                db_info["is_neon_host"] = "neon.tech" in host
                db_info["engine"] = connection.settings_dict.get("ENGINE", "")
                db_info["vendor"] = connection.vendor

                # Table checks
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
                all_tables = [r[0] for r in cursor.fetchall()]
                db_info["total_tables"] = len(all_tables)

                key_tables = [
                    "accounts_user",
                    "incidents_incident",
                    "datasets_dataset",
                    "predictions_modelversion",
                    "predictions_predictionresult",
                    "incidents_iogpruletag",
                    "incidents_incidentreview",
                ]
                counts = {}
                for t in key_tables:
                    if t in all_tables:
                        cursor.execute(f"SELECT COUNT(*) FROM {t};")
                        counts[t] = cursor.fetchone()[0]
                    else:
                        counts[t] = "TABLE_NOT_FOUND"
                db_info["row_counts"] = counts

                # Migration state
                cursor.execute("SELECT COUNT(*) FROM django_migrations;")
                db_info["total_applied_migrations"] = cursor.fetchone()[0]

                cursor.execute("SELECT app, name, applied FROM django_migrations ORDER BY applied DESC LIMIT 5;")
                db_info["latest_migrations"] = [{"app": r[0], "name": r[1], "applied": str(r[2])} for r in cursor.fetchall()]

                db_info["status"] = "CONNECTED"
        except Exception as e:
            db_info["status"] = "ERROR"
            db_info["error"] = str(e)

        # 2. Model Version & Active Model Registry
        from apps.predictions.models import ModelVersion
        model_info = {}
        try:
            model_info["total_model_versions"] = ModelVersion.objects.count()
            active_mv = ModelVersion.objects.filter(is_active=True).first()
            if active_mv:
                model_info["active_model"] = {
                    "id": str(active_mv.id),
                    "version_label": active_mv.version_label,
                    "status": active_mv.status,
                    "is_active": active_mv.is_active,
                    "xgboost_path": active_mv.xgboost_artifact_path,
                    "encoder_path": active_mv.encoder_artifact_path,
                    "bert_model_name": active_mv.bert_model_name,
                    "trained_at": str(active_mv.trained_at),
                }
            else:
                model_info["active_model"] = None
        except Exception as e:
            model_info["error"] = str(e)

        # 3. Model Artifacts on Deployed Filesystem
        artifacts_dir = Path(settings.BASE_DIR) / "ml_engine" / "artifacts"
        artifact_probe = {
            "artifacts_dir": str(artifacts_dir),
            "artifacts_dir_exists": artifacts_dir.exists(),
            "versions_found": [],
        }
        if artifacts_dir.exists():
            for d in sorted(artifacts_dir.iterdir()):
                if d.is_dir():
                    enc_file = d / "encoder.joblib"
                    model_file = d / "model.json"
                    meta_file = d / "metadata.json"
                    snap_file = d / "training_snapshot.json"
                    artifact_probe["versions_found"].append({
                        "version": d.name,
                        "encoder_exists": enc_file.exists(),
                        "model_json_exists": model_file.exists(),
                        "metadata_exists": meta_file.exists(),
                        "snapshot_exists": snap_file.exists(),
                        "encoder_size_bytes": enc_file.stat().st_size if enc_file.exists() else 0,
                        "model_size_bytes": model_file.stat().st_size if model_file.exists() else 0,
                    })

        # 4. ML Python Libraries Availability
        ml_libs = {
            "xgboost": bool(importlib.util.find_spec("xgboost")),
            "torch": bool(importlib.util.find_spec("torch")),
            "transformers": bool(importlib.util.find_spec("transformers")),
            "shap": bool(importlib.util.find_spec("shap")),
            "joblib": bool(importlib.util.find_spec("joblib")),
            "pandas": bool(importlib.util.find_spec("pandas")),
            "numpy": bool(importlib.util.find_spec("numpy")),
        }

        # 5. Environment & Runtime Flags (NO SECRETS EXPOSED)
        env_flags = {
            "DJANGO_SETTINGS_MODULE": os.environ.get("DJANGO_SETTINGS_MODULE"),
            "DATABASE_URL_SET": bool(os.environ.get("DATABASE_URL")),
            "DATABASE_URL_POINTS_TO_NEON": "neon.tech" in os.environ.get("DATABASE_URL", ""),
            "REDIS_URL_SET": bool(os.environ.get("REDIS_URL")),
            "REDIS_URL_POINTS_TO_UPSTASH": "upstash.io" in os.environ.get("REDIS_URL", ""),
            "CELERY_BROKER_URL_SET": bool(os.environ.get("CELERY_BROKER_URL")),
            "CELERY_RESULT_BACKEND_SET": bool(os.environ.get("CELERY_RESULT_BACKEND")),
            "CELERY_TASK_ALWAYS_EAGER": getattr(settings, "CELERY_TASK_ALWAYS_EAGER", None),
            "DEBUG": settings.DEBUG,
            "VERCEL": bool(os.environ.get("VERCEL")),
            "VERCEL_ENV": os.environ.get("VERCEL_ENV"),
            "VERCEL_GIT_COMMIT_SHA": os.environ.get("VERCEL_GIT_COMMIT_SHA"),
            "VERCEL_GIT_COMMIT_REF": os.environ.get("VERCEL_GIT_COMMIT_REF"),
        }

        # 6. Filesystem Write Probes
        fs_probe = {}
        try:
            tmp_test = Path("/tmp") / "probe_test_write.tmp"
            tmp_test.write_text("ok")
            fs_probe["tmp_writable"] = True
            tmp_test.unlink(missing_ok=True)
        except Exception as e:
            fs_probe["tmp_writable"] = False
            fs_probe["tmp_error"] = str(e)

        try:
            media_test = Path(settings.MEDIA_ROOT) / "probe_test_write.tmp"
            media_test.parent.mkdir(parents=True, exist_ok=True)
            media_test.write_text("ok")
            fs_probe["media_root_writable"] = True
            media_test.unlink(missing_ok=True)
        except Exception as e:
            fs_probe["media_root_writable"] = False
            fs_probe["media_root_error"] = str(e)

        # 7. Celery Broker & Worker Probe
        celery_probe = {}
        try:
            from config.celery import app as celery_app
            inspector = celery_app.control.inspect(timeout=1.5)
            ping_res = inspector.ping() if inspector else None
            celery_probe["broker_configured"] = bool(settings.CELERY_BROKER_URL)
            celery_probe["active_workers"] = list(ping_res.keys()) if ping_res else []
            celery_probe["worker_count"] = len(ping_res) if ping_res else 0
            celery_probe["status"] = "WORKERS_ONLINE" if (ping_res and len(ping_res) > 0) else "NO_WORKERS_ONLINE"
        except Exception as e:
            celery_probe["status"] = "PROBE_FAILED"
            celery_probe["error"] = str(e)
            celery_probe["active_workers"] = []
            celery_probe["worker_count"] = 0

        return Response({
            "status": "ok",
            "database_verification": db_info,
            "model_registry": model_info,
            "artifact_probe": artifact_probe,
            "ml_libraries": ml_libs,
            "environment_flags": env_flags,
            "filesystem_probe": fs_probe,
            "celery_probe": celery_probe,
        }, status=status.HTTP_200_OK)
