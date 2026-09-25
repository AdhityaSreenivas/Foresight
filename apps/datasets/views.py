"""
PSIF Platform — Dataset Template Views (server-rendered pages)

These views render the HTML pages for the dataset ingestion flow:
  /datasets/upload/      — drag-drop upload + preview + column mapping UI
  /datasets/<id>/status/ — processing status with live polling

The actual data operations are done via the DRF API views
(apps/datasets/api_views.py).  These views simply render the page shells;
JavaScript handles all API calls.
"""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, TemplateView
from django.shortcuts import get_object_or_404

from .models import Dataset


class DatasetListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List of datasets — /datasets/"""
    queryset = Dataset.objects.filter(workspace_id__isnull=True).select_related("uploaded_by").order_by("-created_at")
    template_name = "datasets/list.html"
    context_object_name = "datasets"
    paginate_by = 25

    def test_func(self):
        return self.request.user.can_upload


class UploadView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Dataset upload page — /datasets/upload/"""
    template_name = "datasets/upload.html"
    
    def test_func(self):
        return self.request.user.can_upload

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_upload"] = getattr(self.request.user, "can_upload", False)
        ctx["resume_id"] = self.request.GET.get("resume", "")
        return ctx


class DatasetStatusView(LoginRequiredMixin, TemplateView):
    """Processing status page — /datasets/<uuid:pk>/status/"""
    template_name = "datasets/status.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dataset = get_object_or_404(Dataset, pk=kwargs["pk"])
        ctx["dataset"] = dataset
        ctx["dataset_id"] = str(dataset.id)
        return ctx
