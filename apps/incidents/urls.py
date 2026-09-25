"""incidents URL configuration."""
from django.urls import path
from . import views

app_name = "incidents"

urlpatterns = [
    path("", views.IncidentListView.as_view(), name="list"),
    path("report/", views.IncidentReportCreateView.as_view(), name="report"),
    path("export/", views.IncidentExportView.as_view(), name="export"),
    path("<uuid:pk>/", views.IncidentDetailView.as_view(), name="detail"),
    path("<uuid:pk>/workspace/", views.IncidentInvestigationWorkspaceView.as_view(), name="workspace"),
    path("<uuid:pk>/evidence-break/", views.IncidentEvidenceBreakView.as_view(), name="evidence_break"),
    path("<uuid:pk>/adjudicate/", views.IncidentAdjudicationView.as_view(), name="adjudicate"),

]
