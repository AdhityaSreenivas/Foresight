"""predictions URL configuration."""
from django.urls import path
from . import views

app_name = "predictions"

urlpatterns = [
    path("models/", views.ModelManagementView.as_view(), name="model_management"),
    path("manual/", views.ManualPredictionView.as_view(), name="manual_prediction"),
    path("predict/", views.ManualPredictionView.as_view(), name="predict"),
    path("review/", views.ReviewQueueView.as_view(), name="review_queue"),
    path("review/update/<uuid:incident_id>/", views.update_incident_status, name="update_status"),
    path("assurance/", views.ModelAssuranceView.as_view(), name="model_assurance"),
]
