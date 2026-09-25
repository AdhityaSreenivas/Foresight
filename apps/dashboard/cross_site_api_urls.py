"""
PSIF Platform — Cross-Site Intelligence REST API URL Configuration
apps/dashboard/cross_site_api_urls.py
"""

from django.urls import path
from . import cross_site_api_views as views

app_name = "cross_site_api"

urlpatterns = [
    path("overview/", views.CrossSiteOverviewAPIView.as_view(), name="overview"),
    path("sites/", views.CrossSiteSitesAPIView.as_view(), name="sites"),
    path("sites/<str:site_id>/", views.CrossSiteSiteDetailAPIView.as_view(), name="site_detail"),
    path("activities/", views.CrossSiteActivitiesAPIView.as_view(), name="activities"),
    path("hazards/", views.CrossSiteHazardsAPIView.as_view(), name="hazards"),
    path("iogp/", views.CrossSiteIOGPAPIView.as_view(), name="iogp"),
    path("compare/", views.CrossSiteCompareAPIView.as_view(), name="compare"),
    path("recurrence/", views.CrossSiteRecurrenceAPIView.as_view(), name="recurrence"),
]
