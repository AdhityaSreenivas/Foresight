"""
REST API views for Data Quality Assurance & Audit (Task 12).
apps/incidents/dq_api_views.py
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.incidents.services.dq_assurance_service import DataQualityAssuranceService


class DataQualityAuditAPIView(APIView):
    """
    GET /api/data-quality/
    Returns full Data Quality audit payload, including summary counts,
    defect category breakdowns, 4 evidence states, and ingestion pathway audit.
    Optional query parameter: ?dataset_id=<uuid>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dataset_id = request.query_params.get("dataset_id")
        summary = DataQualityAssuranceService.get_data_quality_summary(dataset_id=dataset_id)
        return Response(summary, status=status.HTTP_200_OK)


class DataQualitySummaryAPIView(APIView):
    """
    GET /api/data-quality/summary/
    Returns concise Data Quality KPI summary with counts, rates, and denominators.
    Optional query parameter: ?dataset_id=<uuid>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dataset_id = request.query_params.get("dataset_id")
        summary = DataQualityAssuranceService.get_data_quality_summary(dataset_id=dataset_id)
        return Response({
            "status": "ok",
            "scope": summary.get("scope"),
            "timestamp": summary.get("timestamp"),
            "quality_version": summary.get("quality_version"),
            "summary_metrics": summary.get("summary_metrics"),
            "methodology_statement": summary.get("methodology_statement"),
        }, status=status.HTTP_200_OK)
