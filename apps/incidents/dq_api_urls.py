"""
URL configuration for Data Quality REST API (Task 12).
apps/incidents/dq_api_urls.py
"""

from django.urls import path
from . import dq_api_views as views

urlpatterns = [
    path("", views.DataQualityAuditAPIView.as_view(), name="data_quality_audit"),
    path("summary/", views.DataQualitySummaryAPIView.as_view(), name="data_quality_summary"),
]
