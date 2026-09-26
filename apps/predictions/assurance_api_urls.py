"""
URL configuration for Model Assurance REST API (Task 12).
apps/predictions/assurance_api_urls.py
"""

from django.urls import path
from . import assurance_api_views as views

urlpatterns = [
    path("", views.ModelAssuranceRootAPIView.as_view(), name="model_assurance_root"),
    path("models/", views.ModelRegistryAuditAPIView.as_view(), name="model_assurance_models"),
    path("metrics/", views.ModelMetricsAuditAPIView.as_view(), name="model_assurance_metrics"),
    path("human-review/", views.HumanReviewAuditAPIView.as_view(), name="model_assurance_human_review"),
    path("diagnostic/", views.ProductionDiagnosticAPIView.as_view(), name="model_assurance_diagnostic"),
]
