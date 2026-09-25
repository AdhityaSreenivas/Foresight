"""predictions model management API URLs."""
from django.urls import path
from .api_views import (
    ModelListAPIView,
    ModelRetrainAPIView,
    ModelStatusAPIView,
    ModelActivateAPIView,
    ModelCompareAPIView,
    ModelTrainingSourcesAPIView,
    CancelTrainingAPIView,
)

app_name = "model_api"

urlpatterns = [
    path("", ModelListAPIView.as_view(), name="list"),
    path("sources/", ModelTrainingSourcesAPIView.as_view(), name="training_sources"),
    path("training-sources/", ModelTrainingSourcesAPIView.as_view(), name="training_sources_alt"),
    path("retrain/", ModelRetrainAPIView.as_view(), name="retrain"),
    path("<uuid:model_id>/status/", ModelStatusAPIView.as_view(), name="status"),
    path("<uuid:model_id>/activate/", ModelActivateAPIView.as_view(), name="activate"),
    path("<uuid:model_id>/compare/", ModelCompareAPIView.as_view(), name="compare"),
    path("<uuid:model_id>/cancel/", CancelTrainingAPIView.as_view(), name="cancel"),
]
