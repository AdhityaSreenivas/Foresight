"""predictions API URLs."""
from django.urls import path
from .api_views import PredictView

app_name = "predictions_api"

urlpatterns = [
    path("", PredictView.as_view(), name="predict"),
]
