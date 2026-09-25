"""predictions views."""
import logging
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView, ListView
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from apps.incidents.models import Incident

logger = logging.getLogger(__name__)


class ModelManagementView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "predictions/models.html"

    def test_func(self):
        return self.request.user.can_retrain

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from ml_engine.training.training_sources import get_training_sources_overview
        try:
            context["training_sources"] = get_training_sources_overview()
        except Exception as e:
            logger.error("Failed to fetch training sources overview: %s", e)
            context["training_sources"] = {}
        return context


class ManualPredictionView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "predictions/predict.html"

    def test_func(self):
        return self.request.user.can_predict


class ReviewQueueView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    template_name = "predictions/review.html"
    context_object_name = "incidents"
    paginate_by = 50

    def test_func(self):
        return self.request.user.can_predict

    def get_paginate_by(self, queryset):
        page_size = self.request.GET.get("page_size")
        if page_size in ["25", "50", "100"]:
            return int(page_size)
        return self.paginate_by

    def get_queryset(self):
        from django.db.models import Case, When, Value, IntegerField, Q

        # Base query with optimized bulk loading (no N+1 queries)
        qs = (
            Incident.objects.all()
            .select_related("prediction", "prediction__model_version", "data_quality", "reviewed_by", "adjudicated_by")
            .prefetch_related("iogp_rules", "reviews", "reviews__reviewer")
            .distinct()
        )

        # 1. Filter: Review State (pending, reviewed, all)
        review_state = self.request.GET.get("review_state")
        decision_filter = self.request.GET.get("decision")
        agreement_filter = self.request.GET.get("agreement_state")

        if review_state == "pending":
            qs = qs.filter(adjudication_status=Incident.AdjudicationStatus.UNREVIEWED)
        elif review_state == "reviewed":
            qs = qs.filter(adjudication_status=Incident.AdjudicationStatus.ADJUDICATED)
        elif not review_state and not decision_filter and not agreement_filter:
            # Default to pending review queue if no specific review status/decision is requested
            qs = qs.filter(adjudication_status=Incident.AdjudicationStatus.UNREVIEWED)

        # 2. Filter: Decision (PSIF, NOT_PSIF, INSUFFICIENT_INFORMATION, unreviewed)
        if decision_filter in ["PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION"]:
            qs = qs.filter(adjudicated_human_decision=decision_filter)
        elif decision_filter == "unreviewed":
            qs = qs.filter(adjudicated_human_decision__isnull=True)

        # 3. Filter: Agreement State
        if agreement_filter:
            qs = qs.filter(reviews__agreement_state=agreement_filter)

        # 4. Filter: Evidence Strength (Strong, Moderate, Weak)
        strength = self.request.GET.get("evidence_strength")
        if strength in ["Strong", "Moderate", "Weak"]:
            qs = qs.filter(prediction__evidence_strength__iexact=strength)

        # 5. Filter: Data Quality Warning
        if self.request.GET.get("dq_warning") == "true":
            qs = qs.filter(data_quality__status__in=["WARNING", "CRITICAL"])

        # 6. Filter: Sparse / Insufficient Input
        sparse = self.request.GET.get("sparse")
        if sparse in ["true", "yes", "1"]:
            qs = qs.filter(prediction__is_sparse_input=True)
        elif sparse in ["false", "no", "0"]:
            qs = qs.filter(prediction__is_sparse_input=False)

        # 7. Filter: PSIF Model Candidate
        psif_filter = self.request.GET.get("psif")
        if psif_filter in ["true", "yes", "1"]:
            qs = qs.filter(prediction__psif_predicted=True)
        elif psif_filter in ["false", "no", "0"]:
            qs = qs.filter(prediction__psif_predicted=False)

        # 8. Filter: IOGP Life-Saving Rule
        iogp_rule = self.request.GET.get("iogp_rule")
        if iogp_rule:
            qs = qs.filter(iogp_rules__rule__icontains=iogp_rule)

        # 9. Filter: Site / Department
        site = self.request.GET.get("site") or self.request.GET.get("department")
        if site:
            qs = qs.filter(Q(department__icontains=site) | Q(location__icontains=site))

        # 10. Filter: Date Range
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        if date_from:
            qs = qs.filter(incident_date__gte=date_from)
        if date_to:
            qs = qs.filter(incident_date__lte=date_to)

        # 11. Filter: Activity / Narrative Search
        activity = self.request.GET.get("activity")
        if activity:
            qs = qs.filter(
                Q(activity__icontains=activity)
                | Q(injury_type__icontains=activity)
                | Q(composite_narrative__icontains=activity)
            )

        # ── Deterministic Sorting (Section 13) ───────────────────────────────
        sort_by = self.request.GET.get("sort", "priority")

        if sort_by == "newest":
            qs = qs.order_by("-incident_date", "-created_at")
        elif sort_by == "weak_evidence":
            qs = qs.order_by(
                Case(
                    When(prediction__evidence_strength__iexact="Weak", then=Value(1)),
                    When(prediction__evidence_strength__iexact="Moderate", then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                ),
                "-prediction__psif_probability",
                "-incident_date",
            )
        elif sort_by == "disagreement":
            qs = qs.order_by(
                Case(
                    When(reviews__agreement_state__in=[
                        "THREE_WAY_DISAGREEMENT",
                        "HUMAN_OVERRIDES_MODEL",
                        "HUMAN_OVERRIDES_RULE",
                    ], then=Value(1)),
                    When(reviews__agreement_state__isnull=False, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                ),
                "-created_at",
            )
        elif sort_by == "unreviewed":
            qs = qs.order_by(
                Case(
                    When(adjudication_status=Incident.AdjudicationStatus.UNREVIEWED, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                ),
                "-prediction__psif_probability",
                "-incident_date",
            )
        else:
            # "priority" (default): derived strictly from structured domain criteria
            # Priority 1: High-priority Disagreement / Overrides
            # Priority 2: Weak evidence PSIF candidates
            # Priority 3: Pending unreviewed PSIF predictions
            # Priority 4: All other pending cases
            # Priority 5: Already adjudicated cases
            qs = qs.annotate(
                priority_tier=Case(
                    When(reviews__agreement_state__in=[
                        "THREE_WAY_DISAGREEMENT",
                        "HUMAN_OVERRIDES_MODEL",
                        "HUMAN_OVERRIDES_RULE",
                    ], then=Value(1)),
                    When(prediction__psif_predicted=True, prediction__evidence_strength__iexact="Weak", then=Value(2)),
                    When(prediction__psif_predicted=True, adjudication_status=Incident.AdjudicationStatus.UNREVIEWED, then=Value(3)),
                    When(adjudication_status=Incident.AdjudicationStatus.UNREVIEWED, then=Value(4)),
                    default=Value(5),
                    output_field=IntegerField(),
                )
            ).order_by("priority_tier", "-prediction__psif_probability", "-incident_date", "-created_at")

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.incidents.services.review_analytics import compute_review_analytics

        context["current_page_size"] = self.get_paginate_by(self.object_list)
        context["selected_psif"] = self.request.GET.get("psif", "")
        context["selected_dq"] = self.request.GET.get("dq_warning", "")
        context["selected_strength"] = self.request.GET.get("evidence_strength", "")
        context["selected_sparse"] = self.request.GET.get("sparse", "")
        context["selected_review_state"] = self.request.GET.get("review_state", "")
        context["selected_decision"] = self.request.GET.get("decision", "")
        context["selected_agreement"] = self.request.GET.get("agreement_state", "")
        context["selected_sort"] = self.request.GET.get("sort", "priority")
        context["selected_site"] = self.request.GET.get("site") or self.request.GET.get("department", "")
        context["selected_iogp"] = self.request.GET.get("iogp_rule", "")
        context["selected_activity"] = self.request.GET.get("activity", "")
        context["selected_date_from"] = self.request.GET.get("date_from", "")
        context["selected_date_to"] = self.request.GET.get("date_to", "")

        # Real Review Analytics with explicit denominators & inter-rater safety guard
        try:
            context["review_analytics"] = compute_review_analytics()
        except Exception as e:
            logger.error("Failed to compute review analytics: %s", e)
            context["review_analytics"] = None

        # Build query string for pagination links preserving active filters
        params = self.request.GET.copy()
        if "page" in params:
            del params["page"]
        context["filter_params"] = params.urlencode()

        return context


def update_incident_status(request, incident_id):
    if not request.user.is_authenticated or not request.user.can_predict:
        return HttpResponse("Unauthorized", status=403)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in [Incident.Status.REVIEWED_PSIF, Incident.Status.REVIEWED_NON_PSIF]:
            incident = get_object_or_404(Incident, id=incident_id)
            incident.status = new_status
            incident.save(update_fields=["status"])
            return HttpResponse("")
    return HttpResponse("Bad Request", status=400)


class ModelAssuranceView(LoginRequiredMixin, TemplateView):
    """
    Model Assurance & Governance Center.
    Displays real model card, audit metrics, DQ statistics, human review audit,
    and methodology disclosures. Reads dynamically from database via ModelAssuranceService.
    """
    template_name = "predictions/model_assurance.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.predictions.services.assurance_service import ModelAssuranceService
        from apps.incidents.services.dq_assurance_service import DataQualityAssuranceService
        from apps.incidents.models import Incident
        from apps.predictions.models import ModelVersion

        # 1. Model Registry & Active Model Audit (computes independent denominator binary metrics)
        registry_audit = ModelAssuranceService.get_model_registry_audit()
        context["registry_audit"] = registry_audit
        context["active_model_audit"] = registry_audit.get("active_model")
        context["models_audit_list"] = registry_audit.get("models", [])
        context["platform_predictions_summary"] = registry_audit.get("platform_predictions_summary")

        # 2. Human Review Audit (strictly reports 0 genuine OIL field validations)
        context["human_audit"] = ModelAssuranceService.get_human_review_audit()

        # 3. Fleet Data Quality Summary
        context["dq_summary"] = DataQualityAssuranceService.get_data_quality_summary()

        # 4. Drift Check on active model
        active_model = ModelVersion.objects.filter(is_active=True).first()
        context["active_model"] = active_model
        if active_model:
            context["drift_audit"] = ModelAssuranceService.detect_model_drift_or_change(active_model)
        else:
            context["drift_audit"] = None

        # 5. Representative Model / Rule Reconciliation Sample
        sample_incident = (
            Incident.objects.filter(iogp_rules__isnull=False, prediction__isnull=False)
            .prefetch_related("iogp_rules")
            .select_related("prediction")
            .first()
        )
        if sample_incident:
            context["reconciliation_sample"] = ModelAssuranceService.evaluate_model_rule_reconciliation(sample_incident)
            context["reconciliation_incident"] = sample_incident
        else:
            context["reconciliation_sample"] = None
            context["reconciliation_incident"] = None

        return context


