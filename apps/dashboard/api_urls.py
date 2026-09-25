"""dashboard analytics API URLs."""
from django.urls import path
from .api_views import (
    AnalyticsSummaryAPIView, 
    AnalyticsTrendAPIView,
    RecurringPatternsAPIView,
    CrossSiteAlertsAPIView,
    BarrierIntelligenceAPIView,
    BarrierDetailAPIView,
)

app_name = "dashboard_api"

urlpatterns = [
    path("summary/", AnalyticsSummaryAPIView.as_view(), name="analytics_summary"),
    path("trend/", AnalyticsTrendAPIView.as_view(), name="analytics_trend"),
    path("recurring-patterns/", RecurringPatternsAPIView.as_view(), name="recurring_patterns"),
    path("cross-site-alerts/", CrossSiteAlertsAPIView.as_view(), name="cross_site_alerts"),
    path("barriers/", BarrierIntelligenceAPIView.as_view(), name="barrier_intelligence"),
    path("barriers/<str:rule_slug>/", BarrierDetailAPIView.as_view(), name="barrier_detail"),
]

