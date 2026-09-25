"""
PSIF Platform — Admin Flow URLs.
Dedicated URL namespace: /admin-flow/
"""
from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "admin_flow"

urlpatterns = [
    # Root redirect within Admin Flow namespace
    path("", RedirectView.as_view(url="dashboard/", permanent=False), name="root"),

    # 1. Dashboard
    path("dashboard/", views.AdminFlowDashboardView.as_view(), name="dashboard"),

    # 2. Submit Report
    path("submit/", views.AdminFlowSubmitReportView.as_view(), name="submit"),

    # 3. Upload dataset & Live Processing
    path("upload/", views.AdminFlowUploadDatasetView.as_view(), name="upload"),
    path("live-processing/", views.AdminFlowLiveProcessingView.as_view(), name="live_processing"),
    path("live-processing/<uuid:dataset_id>/", views.AdminFlowLiveProcessingView.as_view(), name="live_processing_dataset"),

    # 4. Incidents List, Detail & Single Incident Reasoning
    path("incidents/", views.AdminFlowIncidentListView.as_view(), name="incidents"),
    path("incidents/<uuid:pk>/", views.AdminFlowIncidentDetailView.as_view(), name="incidents_detail"),
    path("incidents/<uuid:pk>/reasoning/", views.AdminFlowIncidentReasoningView.as_view(), name="incident_reasoning"),

    # 5. PSIF Classification
    path("psif/", views.AdminFlowPSIFClassificationView.as_view(), name="psif"),

    # 6. IOGP classification
    path("iogp/", views.AdminFlowIOGPClassificationView.as_view(), name="iogp"),

    # 7. Pattern Analysis (Hub, Activity, Barrier, Location dimensions)
    path("patterns/", views.AdminFlowPatternHubView.as_view(), name="patterns"),
    path("patterns/activity/", views.AdminFlowActivityPatternAnalysisView.as_view(), name="patterns_activity"),
    path("patterns/barrier/", views.AdminFlowBarrierPatternAnalysisView.as_view(), name="patterns_barrier"),
    path("patterns/location/", views.AdminFlowLocationPatternAnalysisView.as_view(), name="patterns_location"),

    # 8. Clean-Sheet Demonstration Reset
    path("reset/", views.AdminFlowResetView.as_view(), name="reset"),

    # REST APIs
    path("api/live-status/", views.AdminFlowLiveStatusAPI.as_view(), name="api_live_status"),
    path("api/live-status/<uuid:dataset_id>/", views.AdminFlowLiveStatusAPI.as_view(), name="api_live_status_dataset"),
    path("api/analytics/overview/", views.AdminFlowAnalyticsOverviewAPI.as_view(), name="api_analytics_overview"),
    path("api/psif/metrics/", views.AdminFlowPSIFMetricsAPI.as_view(), name="api_psif_metrics"),
    path("api/iogp/metrics/", views.AdminFlowIOGPMetricsAPI.as_view(), name="api_iogp_metrics"),
    path("api/iogp/portfolio/", views.AdminFlowBarrierPortfolioAPI.as_view(), name="api_iogp_portfolio"),
    path("api/patterns/", views.AdminFlowPatternsOverviewAPI.as_view(), name="api_patterns_overview"),
    path("api/patterns/activity/", views.AdminFlowActivityPatternsAPI.as_view(), name="api_patterns_activity"),
    path("api/patterns/barrier/", views.AdminFlowBarrierPatternsAPI.as_view(), name="api_patterns_barrier"),
    path("api/patterns/barriers/", views.AdminFlowBarrierPatternsAPI.as_view(), name="api_patterns_barriers"),
    path("api/patterns/location/", views.AdminFlowLocationPatternsAPI.as_view(), name="api_patterns_location"),
]
