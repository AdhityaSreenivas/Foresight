"""incidents API URLs."""
from django.urls import path
from .api_views import (
    IncidentListAPIView,
    IncidentDetailAPIView,
    IncidentAnalysisAPIView,
    IncidentHumanReviewView,
    IncidentReportCreateAPIView,
    IncidentEvidenceBreakAPIView,
    IncidentCorrectiveActionsAPIView,
    IncidentReasoningAPIView,
    IncidentReviewAnalyticsAPIView,
    IncidentWorkspaceAPIView,
)

app_name = "incidents_api"

urlpatterns = [
    path("", IncidentListAPIView.as_view(), name="incident_list"),
    path("report/", IncidentReportCreateAPIView.as_view(), name="incident_report"),
    path("reviews/analytics/", IncidentReviewAnalyticsAPIView.as_view(), name="review_analytics"),
    path("<uuid:pk>/", IncidentDetailAPIView.as_view(), name="incident_detail"),
    path("<uuid:pk>/analysis/", IncidentAnalysisAPIView.as_view(), name="incident_analysis"),
    path("<uuid:pk>/evidence-break/", IncidentEvidenceBreakAPIView.as_view(), name="incident_evidence_break"),
    path("<uuid:pk>/review/", IncidentHumanReviewView.as_view(), name="incident_review"),
    path("<uuid:pk>/actions/", IncidentCorrectiveActionsAPIView.as_view(), name="incident_actions"),
    path("<uuid:pk>/reasoning/", IncidentReasoningAPIView.as_view(), name="incident_reasoning"),
    path("<uuid:pk>/workspace/", IncidentWorkspaceAPIView.as_view(), name="incident_workspace"),
]

