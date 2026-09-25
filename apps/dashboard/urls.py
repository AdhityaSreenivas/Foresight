"""dashboard URL configuration."""
from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="home"),
    path("reports/", views.ReportsView.as_view(), name="reports"),
    path("barriers/", views.BarrierIntelligenceView.as_view(), name="barriers"),
    path("barriers/<str:rule_slug>/", views.BarrierDetailView.as_view(), name="barrier_detail"),
    path("cross-site/", views.CrossSiteIntelligenceView.as_view(), name="cross_site"),
    path("data-quality/", views.DataQualityDashboardView.as_view(), name="data_quality"),
]

