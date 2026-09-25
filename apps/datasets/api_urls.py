"""datasets API URL configuration."""
from django.urls import path

from .api_views import (
    ColumnMappingView,
    DatasetCancelView,
    DatasetDeleteView,
    DatasetListView,
    DatasetPreviewView,
    DatasetStatusView,
    FileUploadView,
    ProcessDatasetView,
    RetryDatasetView,
)

app_name = "datasets_api"

urlpatterns = [
    # POST  /api/datasets/upload/           — upload file, get preview + suggestions
    path("upload/", FileUploadView.as_view(), name="upload"),

    # GET   /api/datasets/                  — paginated dataset list
    path("", DatasetListView.as_view(), name="list"),

    # DELETE /api/datasets/<pk>/           — cancel and discard uncompleted dataset
    path("<uuid:pk>/", DatasetDeleteView.as_view(), name="delete"),

    # GET   /api/datasets/<pk>/preview/     — get preview and mapping data for resume
    path("<uuid:pk>/preview/", DatasetPreviewView.as_view(), name="preview"),

    # GET   /api/datasets/<pk>/status/      — live progress for polling
    path("<uuid:pk>/status/", DatasetStatusView.as_view(), name="status"),

    # POST  /api/datasets/<pk>/column-mapping/ — save confirmed column mapping
    path("<uuid:pk>/column-mapping/", ColumnMappingView.as_view(), name="column-mapping"),

    # POST  /api/datasets/<pk>/process/    — dispatch Celery processing task
    path("<uuid:pk>/process/", ProcessDatasetView.as_view(), name="process"),

    # POST  /api/datasets/<pk>/retry/      — resume/retry processing from checkpoint
    path("<uuid:pk>/retry/", RetryDatasetView.as_view(), name="retry"),

    # POST  /api/datasets/<pk>/cancel/     — cooperative hold/cancel of active processing
    path("<uuid:pk>/cancel/", DatasetCancelView.as_view(), name="cancel"),
]
