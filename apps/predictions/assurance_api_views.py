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
