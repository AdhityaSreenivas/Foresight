"""
PSIF Platform — Root URL Configuration
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.shortcuts import redirect

urlpatterns = [
    # Django admin (superuser management)
    path("admin/", admin.site.urls),

    # Auth pages (login, logout, password change)
    path("accounts/", include("apps.accounts.urls")),

    # Dashboard (home page for authenticated users)
    path("dashboard/", include("apps.dashboard.urls")),

    # Dataset management pages
    path("datasets/", include("apps.datasets.urls")),

    # Incident list / detail pages
    path("incidents/", include("apps.incidents.urls")),

    # Predictions / model management pages
    path("predictions/", include("apps.predictions.urls")),

    # REST API endpoints
    path("api/", include([
        path("auth/", include("apps.accounts.api_urls")),
        path("datasets/", include("apps.datasets.api_urls")),
        path("incidents/", include("apps.incidents.api_urls")),
        path("predict/", include("apps.predictions.api_urls")),
        path("analytics/", include("apps.dashboard.api_urls")),
        path("models/", include("apps.predictions.model_api_urls")),
        path("cross-site/", include("apps.dashboard.cross_site_api_urls")),
        path("model-assurance/", include("apps.predictions.assurance_api_urls")),
        path("data-quality/", include("apps.incidents.dq_api_urls")),
    ])),

    # Dedicated Admin Flow namespace for evaluator demonstration
    path("admin-flow/", include("apps.admin_flow.urls")),

    # Root redirect → admin-flow dashboard if admin_flow user, else dashboard
    path("", lambda req: redirect("admin_flow:dashboard") if req.user.is_authenticated and getattr(req.user, "is_admin_flow", False) else redirect("dashboard:home")),
    path("login/", RedirectView.as_view(url="/accounts/login/", permanent=False)),
    path("reports/", RedirectView.as_view(url="/dashboard/reports/", permanent=False)),
    path("barriers/", RedirectView.as_view(url="/dashboard/barriers/", permanent=False)),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
