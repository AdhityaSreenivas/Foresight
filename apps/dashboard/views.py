"""dashboard views."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from apps.dashboard.imagery import get_industrial_image
from apps.dashboard.services import get_analytics_summary, get_barrier_intelligence
import logging

logger = logging.getLogger(__name__)

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and getattr(request.user, "is_admin_flow", False):
            from django.shortcuts import redirect
            return redirect("admin_flow:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch image with fallback
        context['hero_image'] = get_industrial_image(query='industrial safety', orientation='landscape')
        try:
            context['analytics_summary'] = get_analytics_summary()
        except Exception:
            context['analytics_summary'] = None
        return context

class ReportsView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/reports.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hero_image'] = get_industrial_image(query='analytics chart office', orientation='landscape')
        try:
            context['analytics_summary'] = get_analytics_summary()
        except Exception:
            context['analytics_summary'] = None
        return context

class BarrierIntelligenceView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/barriers.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hero_image'] = get_industrial_image(query='oil refinery safety barrier inspection', orientation='landscape')
        try:
            from apps.incidents.services.barrier_service import BarrierIntelligenceService
            context['barrier_data'] = BarrierIntelligenceService.get_barrier_portfolio()
        except Exception as e:
            logger.error("Error retrieving barrier intelligence: %s", e)
            context['barrier_data'] = None
        return context


class BarrierDetailView(LoginRequiredMixin, TemplateView):
    """Detailed view for a specific IOGP Life-Saving Rule barrier domain."""
    template_name = "dashboard/barrier_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rule_slug = self.kwargs.get("rule_slug", "")
        from apps.incidents.services.barrier_service import BarrierIntelligenceService
        from apps.incidents.services.normalization import normalize_iogp_rule
        rule_norm = normalize_iogp_rule(rule_slug.replace("-", " "))
        page = int(self.request.GET.get("page", 1))
        page_size = int(self.request.GET.get("page_size", 10))

        try:
            detail_data = BarrierIntelligenceService.get_barrier_detail(
                rule_name=rule_norm.canonical_value,
                page=page,
                page_size=page_size,
            )
            context["detail"] = detail_data
        except Exception as e:
            logger.error("Error retrieving barrier detail for %s: %s", rule_slug, e)
            context["detail"] = None
            context["error_message"] = str(e)
        return context



class CrossSiteIntelligenceView(LoginRequiredMixin, TemplateView):
    """Normalized cross-site safety intelligence page."""
    template_name = "dashboard/cross_site.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.dashboard.cross_site_service import (
            get_cross_site_overview,
            get_site_comparison_table,
            get_site_iogp_matrix,
            get_site_hazard_matrix,
            get_normalized_activities_cross_site,
            get_normalized_hazards_cross_site,
            get_normalized_iogp_cross_site,
            get_cross_site_recurrence_signals,
            METHODOLOGY_DISCLOSURE,
            PLATFORM_LIMITATIONS,
        )

        context['hero_image'] = get_industrial_image(query='oil refinery operations multiple locations', orientation='landscape')
        context['methodology_notice'] = METHODOLOGY_DISCLOSURE
        context['limitations'] = PLATFORM_LIMITATIONS

        try:
            context['overview'] = get_cross_site_overview()
        except Exception as e:
            logger.error("Error loading cross-site overview: %s", e)
            context['overview'] = None

        try:
            context['site_comparison'] = get_site_comparison_table()
        except Exception as e:
            logger.error("Error loading site comparison: %s", e)
            context['site_comparison'] = []

        try:
            context['iogp_matrix'] = get_site_iogp_matrix()
        except Exception as e:
            logger.error("Error loading IOGP matrix: %s", e)
            context['iogp_matrix'] = None

        try:
            context['hazard_matrix'] = get_site_hazard_matrix()
        except Exception as e:
            logger.error("Error loading hazard matrix: %s", e)
            context['hazard_matrix'] = None

        try:
            context['activities'] = get_normalized_activities_cross_site()
        except Exception as e:
            logger.error("Error loading cross-site activities: %s", e)
            context['activities'] = []

        try:
            context['hazards'] = get_normalized_hazards_cross_site()
        except Exception as e:
            logger.error("Error loading cross-site hazards: %s", e)
            context['hazards'] = []

        try:
            context['iogp_rules'] = get_normalized_iogp_cross_site()
        except Exception as e:
            logger.error("Error loading cross-site IOGP rules: %s", e)
            context['iogp_rules'] = []

        try:
            context['recurrence_signals'] = get_cross_site_recurrence_signals()
        except Exception as e:
            logger.error("Error loading cross-site recurrence signals: %s", e)
            context['recurrence_signals'] = []

        return context


class DataQualityDashboardView(LoginRequiredMixin, TemplateView):
    """Data Quality Assurance Dashboard — platform fleet and dataset-specific DQ intelligence."""
    template_name = "dashboard/data_quality.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.incidents.services.dq_assurance_service import DataQualityAssuranceService
        from apps.datasets.models import Dataset

        dataset_id = self.request.GET.get("dataset_id")
        context["dq_summary"] = DataQualityAssuranceService.get_data_quality_summary(dataset_id=dataset_id)
        context["datasets"] = Dataset.objects.all().order_by("-created_at")[:20]
        context["selected_dataset_id"] = dataset_id or ""
        return context


