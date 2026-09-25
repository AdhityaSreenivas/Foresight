"""
PSIF Platform — Incidents views
"""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse
from django.contrib import messages

from .models import Incident
from .forms import IncidentReportForm


class IncidentReportCreateView(LoginRequiredMixin, CreateView):
    """
    Field reporter submission form view.
    Allows authenticated users to submit safety reports with rich energy,
    exposure, and control context.
    """
    model = Incident
    form_class = IncidentReportForm
    template_name = "incidents/report_form.html"

    def form_valid(self, form):
        self.object = form.save()
        messages.success(
            self.request,
            f"Safety observation report #{self.object.id} submitted successfully. Automated data quality screening completed."
        )
        return super().form_valid(form)

    def get_success_url(self):
        if self.request.user.is_viewer:
            return reverse("dashboard:home")
        return reverse("incidents:detail", kwargs={"pk": self.object.pk})


class IncidentListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List view of all ingested incidents."""
    model = Incident
    template_name = "incidents/list.html"
    context_object_name = "incidents"
    paginate_by = 25
    ordering = ["-incident_date"]
    
    def test_func(self):
        return not self.request.user.is_viewer

    def get_queryset(self):
        qs = super().get_queryset().filter(workspace_id__isnull=True)
        
        # Search by description, department, injury_type
        search_query = self.request.GET.get('q')
        if search_query:
            from django.db.models import Q
            qs = qs.filter(
                Q(description__icontains=search_query) |
                Q(department__icontains=search_query) |
                Q(injury_type__icontains=search_query)
            )
            
        # Filter by status
        status = self.request.GET.get('status')
        if status in [c[0] for c in Incident.Status.choices]:
            qs = qs.filter(status=status)

        # Filter by dataset
        dataset_id = self.request.GET.get('dataset')
        if dataset_id:
            qs = qs.filter(dataset_id=dataset_id)

        # Filter by IOGP Life-Saving Rule (Barrier)
        rule = self.request.GET.get('rule')
        if rule:
            qs = qs.filter(iogp_rules__rule=rule)
            
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['current_rule'] = self.request.GET.get('rule', '')
        context['status_choices'] = Incident.Status.choices
        
        from apps.datasets.models import Dataset
        context['datasets'] = Dataset.objects.filter(incidents__isnull=False).distinct().order_by('-created_at')
        context['selected_dataset'] = self.request.GET.get('dataset', '')
        return context


class IncidentDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Detail view of a specific incident."""
    model = Incident
    template_name = "incidents/detail.html"
    context_object_name = "incident"
    
    def test_func(self):
        return not self.request.user.is_viewer

    def get_queryset(self):
        return super().get_queryset().filter(workspace_id__isnull=True)
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.incidents.services.decision_trace import build_analytical_assessment
        from apps.incidents.services.evidence_break import analyze_evidence_break
        from apps.incidents.rubric import HSE_REVIEW_RUBRIC_V1
        context['analytical_assessment'] = build_analytical_assessment(self.object)
        context['evidence_break'] = analyze_evidence_break(self.object)
        reviews = self.object.reviews.select_related('reviewer').order_by('-created_at')
        context['incident_reviews'] = reviews
        context['has_human_review'] = reviews.exists() or self.object.adjudication_status == Incident.AdjudicationStatus.ADJUDICATED
        context['is_blinded_mode'] = not context['has_human_review']
        context['rubric'] = HSE_REVIEW_RUBRIC_V1
        return context


class IncidentEvidenceBreakView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Analyst-facing Why NOT PSIF / Evidence-Break Workbench view."""
    model = Incident
    template_name = "incidents/evidence_break.html"
    context_object_name = "incident"

    def test_func(self):
        return not self.request.user.is_viewer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        import json
        from apps.incidents.services.evidence_break import analyze_evidence_break
        from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment

        incident = self.object
        prediction = getattr(incident, "prediction", None)
        dq = getattr(incident, "data_quality", None)
        context["workbench"] = analyze_evidence_break(incident)
        reasoning = build_incident_reasoning_assessment(incident, prediction=prediction, dq_record=dq)
        context["reasoning"] = reasoning
        context["reasoning_json"] = json.dumps(reasoning, default=str)
        return context


class IncidentAdjudicationView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Authoritative Human Review & Adjudication Workbench.
    Provides a genuine, focused human-in-the-loop HSE review experience:
    - CASE HEADER (metadata, dates, classification, data quality)
    - MODEL ASSESSMENT (statistical score, factors, blind review toggle)
    - RULE ASSESSMENT (deterministic rule decision, EEI capacity, IOGP matches)
    - EVIDENCE (narrative, energy type, direct control, severity, body part)
    - REASONING TRACE (7-node sequential logic verification)
    - REVIEW DECISION (PSIF, NOT_PSIF, INSUFFICIENT_INFORMATION)
    - RATIONALE (mandatory substantive justification)
    - REVIEWER EVIDENCE NOTES (annotated disagreement/field observations)
    - GROUNDED ACTIONS (rule-grounded corrective recommendations)
    - SUBMISSION & AUDIT TRAIL
    """
    model = Incident
    template_name = "incidents/adjudication.html"
    context_object_name = "incident"

    def test_func(self):
        return not self.request.user.is_viewer

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        import json
        from apps.incidents.services.evidence_break import analyze_evidence_break
        from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment
        from apps.incidents.services.action_library import get_corrective_actions
        from apps.incidents.services.review_reconciliation import calculate_review_reconciliation
        from apps.predictions.models import ModelVersion

        incident = self.object
        prediction = getattr(incident, "prediction", None)
        dq = getattr(incident, "data_quality", None)

        context["evidence_break"] = analyze_evidence_break(incident)
        reasoning = build_incident_reasoning_assessment(incident, prediction=prediction, dq_record=dq)
        context["reasoning"] = reasoning
        context["reasoning_json"] = json.dumps(reasoning, default=str)
        context["actions"] = get_corrective_actions(incident)

        reviews = incident.reviews.select_related("reviewer").order_by("-created_at")
        context["reviews_history"] = reviews
        context["latest_review"] = reviews.first()
        context["has_review"] = reviews.exists()

        active_model = ModelVersion.objects.filter(is_active=True).first()
        context["active_model_version"] = (
            getattr(active_model, "version_label", str(active_model))
            if active_model
            else (prediction.model_version.version_label if prediction and prediction.model_version else "psif_rf_v1.0")
        )
        context["knowledge_base_version"] = "psif_kb_v1.0"
        context["reasoning_ruleset_version"] = "psif_ruleset_v1.0"
        context["action_library_version"] = "action_library_v1"

        # If already reviewed, calculate real-time reconciliation state
        if context["latest_review"]:
            m_pred = prediction.psif_predicted if prediction else None
            m_score = round(float(prediction.psif_probability), 4) if prediction else None
            r_dec = reasoning.get("decision")
            context["reconciliation"] = calculate_review_reconciliation(
                context["latest_review"].decision,
                m_pred,
                r_dec,
                m_score,
            )
        else:
            context["reconciliation"] = None

        return context

    def post(self, request, *args, **kwargs):
        from django.utils import timezone
        from django.shortcuts import redirect
        from apps.incidents.models import IncidentReview
        from apps.incidents.services.review_reconciliation import calculate_review_reconciliation
        from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment
        from apps.predictions.models import ModelVersion

        incident = self.get_object()
        decision = request.POST.get("decision", "").strip().upper()
        rationale = request.POST.get("rationale", "").strip()
        evidence_notes = request.POST.get("evidence_notes", "").strip()
        was_blinded = request.POST.get("was_blinded") in ("true", "1", "on")

        if decision not in ("PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION"):
            messages.error(request, "Invalid decision. Choose PSIF, NOT_PSIF, or INSUFFICIENT_INFORMATION.")
            return redirect("incidents:adjudicate", pk=incident.pk)

        if not rationale or len(rationale) < 10:
            messages.error(request, "A meaningful rationale (at least 10 characters) is required.")
            return redirect("incidents:adjudicate", pk=incident.pk)

        structured_evidence = {
            "high_energy_hazard": request.POST.get("high_energy_hazard", "").strip(),
            "worker_exposure": request.POST.get("worker_exposure", "").strip(),
            "critical_control": request.POST.get("critical_control", "").strip(),
            "control_state": request.POST.get("control_state", "").strip(),
            "consequence_pathway": request.POST.get("consequence_pathway", "").strip(),
            "missing_evidence": request.POST.get("missing_evidence", "").strip(),
            "iogp_rule": request.POST.get("iogp_rule", "").strip(),
            "other_reasoning": request.POST.get("other_reasoning", "").strip(),
        }

        prev_review = incident.reviews.order_by("-created_at").first()
        prev_decision = prev_review.decision if prev_review else None

        active_model = ModelVersion.objects.filter(is_active=True).first()
        active_mv = getattr(active_model, "version_label", str(active_model)) if active_model else "psif_rf_v1.0"

        # Model and Rule decisions for reconciliation
        m_pred = incident.prediction.psif_predicted if hasattr(incident, "prediction") and incident.prediction else None
        m_score = round(float(incident.prediction.psif_probability), 4) if hasattr(incident, "prediction") and incident.prediction else None
        try:
            reasoning = build_incident_reasoning_assessment(incident, prediction=getattr(incident, "prediction", None))
            r_dec = reasoning.get("decision")
        except Exception:
            r_dec = None

        recon = calculate_review_reconciliation(
            human_decision=decision,
            model_prediction=m_pred,
            rule_decision=r_dec,
            model_score=m_score,
        )

        review_prov = "HUMAN_EXPERT"
        now = timezone.now()

        # Create immutable IncidentReview audit record
        IncidentReview.objects.create(
            incident=incident,
            reviewer=request.user,
            decision=decision,
            rationale=rationale,
            evidence_notes=evidence_notes,
            rubric_version="1.0",
            structured_evidence=structured_evidence,
            was_blinded=was_blinded,
            model_version=active_mv,
            knowledge_base_version="psif_kb_v1.0",
            reasoning_ruleset_version="psif_ruleset_v1.0",
            action_library_version="action_library_v1",
            previous_decision=prev_decision,
            review_provenance=review_prov,
            agreement_state=recon.agreement_state,
        )

        # Update Incident adjudication metadata WITHOUT modifying PredictionResult
        incident.adjudication_status = Incident.AdjudicationStatus.ADJUDICATED
        incident.adjudicated_human_decision = decision
        incident.adjudicated_by = request.user
        incident.adjudicated_at = now
        incident.adjudication_rationale = rationale or None

        human_label = True if decision == "PSIF" else False if decision == "NOT_PSIF" else None
        incident.is_psif_human_label = human_label
        incident.psif_label_source = (
            Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC
            if incident.is_synthetic
            else Incident.PsifLabelSource.REAL_HUMAN
        )
        incident.reviewer_rationale = rationale or None
        incident.reviewed_by = request.user
        incident.reviewed_at = now

        if decision == "PSIF":
            incident.status = Incident.Status.REVIEWED_PSIF
        elif decision == "NOT_PSIF":
            incident.status = Incident.Status.REVIEWED_NON_PSIF

        incident.save(update_fields=[
            "adjudication_status",
            "adjudicated_human_decision",
            "adjudicated_by",
            "adjudicated_at",
            "adjudication_rationale",
            "is_psif_human_label",
            "psif_label_source",
            "reviewer_rationale",
            "reviewed_by",
            "reviewed_at",
            "status",
        ])

        messages.success(
            request,
            f"Adjudication successfully recorded: {decision}. Reconciliation State: {recon.agreement_state.replace('_', ' ')}."
        )
        return redirect("incidents:adjudicate", pk=incident.pk)


import csv
from django.http import HttpResponse
from django.views import View
from django.db.models import Q

class IncidentExportView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Export incidents to CSV."""
    
    def test_func(self):
        return not self.request.user.is_viewer
        
    def get(self, request, *args, **kwargs):
        qs = Incident.objects.select_related('prediction').all().order_by('-incident_date')
        
        department = request.GET.get('department')
        if department:
            qs = qs.filter(department=department)
            
        risk = request.GET.get('risk')
        if risk:
            qs = qs.filter(prediction__risk_level=risk)
            
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
            
        search = request.GET.get('search')
        if search:
            qs = qs.filter(composite_narrative__icontains=search)

        dataset = request.GET.get('dataset')
        if dataset:
            qs = qs.filter(dataset_id=dataset)

        rule = request.GET.get('rule')
        if rule:
            qs = qs.filter(iogp_rules__rule=rule)
            
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="incidents_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['ID', 'Date', 'Department', 'Status', 'Risk Level', 'PSIF Predicted', 'Probability', 'Narrative'])
        
        for inc in qs:
            risk_level = inc.prediction.risk_level if hasattr(inc, 'prediction') else 'Unknown'
            psif_predicted = inc.prediction.psif_predicted if hasattr(inc, 'prediction') else False
            probability = inc.prediction.psif_probability if hasattr(inc, 'prediction') else 0.0
            
            writer.writerow([
                inc.id,
                inc.incident_date,
                inc.department,
                inc.get_status_display(),
                risk_level,
                psif_predicted,
                f"{probability:.4f}",
                inc.composite_narrative
            ])
            
        return response


class IncidentInvestigationWorkspaceView(LoginRequiredMixin, DetailView):
    """
    Unified Investigation Workspace View (Task 9).
    Provides one coherent investigation console where an HSE analyst can examine:
    DETECTION → REASONING → EVIDENCE → RELATED SIGNALS → ACTION → HUMAN REVIEW
    without jumping across unrelated pages.
    """
    model = Incident
    template_name = "incidents/workspace.html"
    context_object_name = "incident"

    def get_queryset(self):
        return Incident.objects.select_related(
            "prediction",
            "prediction__model_version",
            "data_quality",
            "dataset",
            "embedding",
            "reviewed_by",
            "adjudicated_by",
        ).prefetch_related(
            "iogp_rules",
            "reviews",
            "reviews__reviewer",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        import json
        from apps.incidents.services.workspace import compose_investigation_workspace

        workspace_data = compose_investigation_workspace(self.object, user=self.request.user)
        context["workspace"] = workspace_data
        context["workspace_json"] = json.dumps(workspace_data, default=str)
        return context

