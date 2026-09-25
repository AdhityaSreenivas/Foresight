"""datasets URL configuration."""
from django.urls import path
from . import views

app_name = "datasets"

urlpatterns = [
    path("", views.DatasetListView.as_view(), name="list"),
    path("upload/", views.UploadView.as_view(), name="upload"),
    path("<uuid:pk>/status/", views.DatasetStatusView.as_view(), name="status"),
]
