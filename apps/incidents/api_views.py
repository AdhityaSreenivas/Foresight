from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from apps.incidents.models import Incident, IncidentReview
from apps.incidents.rubric import HSE_RUBRIC_VERSION
from apps.datasets.permissions import CanReviewIncident
from .serializers import (
    IncidentListSerializer,
    IncidentDetailSerializer,
    HumanReviewSerializer,
    IncidentReportSubmissionSerializer,
)

class IncidentPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100

class IncidentListAPIView(generics.ListAPIView):
    serializer_class = IncidentListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = IncidentPagination
    
    def get_queryset(self):
        queryset = Incident.objects.select_related('prediction', 'dataset').all().order_by('-incident_date')
        
        # Filtering
        department = self.request.query_params.get('department')
        if department:
            queryset = queryset.filter(department=department)
            
        risk = self.request.query_params.get('risk')
        if risk:
            queryset = queryset.filter(prediction__risk_level=risk)
            
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(composite_narrative__icontains=search)
            
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        dataset = self.request.query_params.get('dataset')
        if dataset:
            queryset = queryset.filter(dataset_id=dataset)

        rule = self.request.query_params.get('rule')
        if rule:
            queryset = queryset.filter(iogp_rules__rule=rule)
            
        return queryset


class IncidentDetailAPIView(generics.RetrieveAPIView):
    queryset = Incident.objects.select_related('prediction').all()
    serializer_class = IncidentDetailSerializer
    permission_classes = [IsAuthenticated]

class IncidentAnalysisAPIView(APIView):
    """
    GET /api/incidents/<id>/analysis/
    Returns the comprehensive, evidence-grounded analytical assessment (decision trace).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        try:
            incident = Incident.objects.select_related('prediction', 'embedding').get(pk=pk)
        except Incident.DoesNotExist:
            return Response({"error": "Incident not found."}, status=status.HTTP_404_NOT_FOUND)
            
        from apps.incidents.services.decision_trace import build_analytical_assessment
        assessment = build_analytical_assessment(incident)
        
        return Response(assessment, status=status.HTTP_200_OK)


class IncidentHumanReviewView(APIView):
    """
    PATCH /api/incidents/<uuid:pk>/review/

    Writes a human reviewer's PSIF classification decision to the Incident.

    On success:
      - Incident.is_psif_human_label = submitted value
      - Incident.psif_label_source   = "human"
      - Incident.reviewer_rationale  = submitted rationale
      - Incident.reviewed_by         = request.user
      - Incident.reviewed_at         = now()
      - Incident.status              = REVIEWED_PSIF or REVIEWED_NON_PSIF

    The original PredictionResult is NOT modified; the AI/model output is
    preserved for historical comparison against the human decision.

    Permission: Admin, Safety Officer, or Analyst (via CanReviewIncident).
    Viewers cannot write ground-truth training labels.
    """
    permission_classes = [CanReviewIncident]

    def patch(self, request, pk, *args, **kwargs):
        try:
            incident = Incident.objects.select_related("prediction").get(pk=pk)
        except Incident.DoesNotExist:
            return Response(
                {"error": "Incident not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = HumanReviewSerializer(
            data=request.data,
            context={"incident": incident},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        decision = vd["decision"]
        human_label = vd["is_psif_human_label"]
        rationale = vd.get("rationale", "").strip()
        evidence_notes = vd.get("evidence_notes", "").strip()
        rubric_answers = vd.get("rubric_answers", {})
        structured_evidence = vd.get("structured_evidence", {})
        was_blinded = vd.get("was_blinded", True)
        review_prov = vd.get("review_provenance", "HUMAN_EXPERT")
        now = timezone.now()

        # Idempotency / rapid duplicate submission protection (< 3 seconds)
        previous_review = incident.reviews.first()
        if (
            previous_review
            and previous_review.reviewer == request.user
            and previous_review.decision == decision
            and previous_review.rationale == rationale
            and (now - previous_review.created_at).total_seconds() < 3.0
        ):
            review = previous_review
            prev_decision = previous_review.previous_decision
        else:
            prev_decision = vd.get("previous_decision") or (previous_review.decision if previous_review else None)

            # Model and rule assessments for reconciliation
            from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment
            from apps.incidents.services.review_reconciliation import calculate_review_reconciliation

            active_mv = None
            model_pred = None
            model_score = None
            if hasattr(incident, "prediction") and incident.prediction:
                pred = incident.prediction
                model_pred = pred.psif_predicted
                model_score = round(float(pred.psif_probability), 4)
                if pred.model_version:
                    active_mv = getattr(pred.model_version, "version_label", str(pred.model_version))

            try:
                reasoning = build_incident_reasoning_assessment(incident, prediction=getattr(incident, "prediction", None))
                rule_dec = reasoning.get("decision")
            except Exception:
                rule_dec = None

            recon = calculate_review_reconciliation(
                human_decision=decision,
                model_prediction=model_pred,
                rule_decision=rule_dec,
                model_score=model_score,
            )

            # 1. Create authoritative immutable IncidentReview audit record
            review = IncidentReview.objects.create(
                incident=incident,
                reviewer=request.user,
                decision=decision,
                rationale=rationale,
                evidence_notes=evidence_notes,
                rubric_version=HSE_RUBRIC_VERSION,
                rubric_answers=rubric_answers,
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

        # 2. Update Incident adjudication and consensus fields
        incident.adjudication_status = Incident.AdjudicationStatus.ADJUDICATED
        incident.adjudicated_human_decision = decision
        incident.adjudicated_by = request.user
        incident.adjudicated_at = now
        incident.adjudication_rationale = rationale or None

        # 3. Synchronize backward-compatible is_psif_human_label and status
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

        # 4. Optional unblind payload: Reveal model output only after human label is saved
        prediction_payload = None
        has_prediction = hasattr(incident, "prediction") and incident.prediction is not None
        if has_prediction and (request.query_params.get("unblind") in ("true", "1") or request.data.get("unblind")):
            pred = incident.prediction
            prediction_payload = {
                "psif_predicted": pred.psif_predicted,
                "psif_score": round(float(pred.psif_probability), 4),
                "evidence_strength": pred.evidence_strength,
                "is_sparse_input": pred.is_sparse_input,
                "model_version": str(pred.model_version.version_label if hasattr(pred.model_version, "version_label") else pred.model_version),
                "top_factors": pred.top_factors,
                "agreement_with_human": (
                    pred.psif_predicted == (decision == "PSIF")
                    if decision in ("PSIF", "NOT_PSIF")
                    else None
                ),
            }

        # Calculate final reconciliation details
        from apps.incidents.services.review_reconciliation import calculate_review_reconciliation
        m_pred = incident.prediction.psif_predicted if hasattr(incident, "prediction") and incident.prediction else None
        m_score = round(float(incident.prediction.psif_probability), 4) if hasattr(incident, "prediction") and incident.prediction else None
        from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment
        try:
            rs = build_incident_reasoning_assessment(incident, prediction=getattr(incident, "prediction", None)).get("decision")
        except Exception:
            rs = None
        recon_obj = calculate_review_reconciliation(decision, m_pred, rs, m_score)

        return Response({
            "incident_id": str(incident.id),
            "review_id": str(review.id),
            "decision": decision,
            "previous_decision": prev_decision,
            "is_psif_human_label": incident.is_psif_human_label,
            "adjudication_status": incident.adjudication_status,
            "adjudicated_human_decision": incident.adjudicated_human_decision,
            "psif_label_source": incident.psif_label_source,
            "status": incident.status,
            "reviewed_by": request.user.username,
            "reviewed_at": now.isoformat(),
            "model_version": review.model_version,
            "knowledge_base_version": review.knowledge_base_version,
            "reasoning_ruleset_version": review.reasoning_ruleset_version,
            "action_library_version": review.action_library_version,
            "review_provenance": review.review_provenance,
            "agreement_state": review.agreement_state,
            "reconciliation": recon_obj.to_dict(),
            "effective_training_label": incident.effective_training_label,
            "unblinded_model_prediction": prediction_payload,
            "message": (
                "Human review recorded successfully. "
                "The original model prediction has not been modified."
            ),
        }, status=status.HTTP_200_OK)


class IncidentReviewAnalyticsAPIView(APIView):
    """
    GET /api/incidents/reviews/analytics/

    Delivers aggregated review metrics, explicit denominators, and inter-rater reliability.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from apps.incidents.services.review_analytics import compute_review_analytics
        dataset_id = request.query_params.get("dataset")
        data = compute_review_analytics(dataset_id=dataset_id)
        return Response(data, status=status.HTTP_200_OK)


class IncidentReportCreateAPIView(APIView):
    """
    POST /api/incidents/report/

    Accepts field reporter safety observation / incident data with energy/control context,
    runs automated data quality screening, generates composite narrative, and runs
    background intelligence (weak labeling, IOGP classification, embeddings, model inference).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = IncidentReportSubmissionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        incident = serializer.save()

        dq_status = "VALID"
        if hasattr(incident, "data_quality"):
            dq_status = incident.data_quality.status

        return Response({
            "incident_id": str(incident.id),
            "report_type": incident.report_type,
            "status": incident.status,
            "high_energy_present": incident.high_energy_present,
            "worker_exposed": incident.worker_exposed,
            "direct_control_present": incident.direct_control_present,
            "control_condition": incident.control_condition,
            "control_failed_bypassed": incident.control_failed_bypassed,
            "data_quality_status": dq_status,
            "message": "Incident report submitted and screened successfully."
        }, status=status.HTTP_201_CREATED)


class IncidentEvidenceBreakAPIView(APIView):
    """
    GET /api/incidents/<uuid:pk>/evidence-break/

    Returns the comprehensive Why NOT PSIF / Evidence-Break Workbench payload
    for an incident, including:
    - PSIF Model Score and decision metadata (not called a probability)
    - 5-link SIF evidence chain (Hazard -> Exposure -> Control -> Consequence -> Escalation)
    - Concrete evidence breaks and physical rationales
    - What would change this assessment
    - Separated SHAP contributors (positive, negative, suppressed zero features)
    - Source traceability (narrative quotes + structured field mappings)
    - Data quality, sparse warning (<10 words), and human adjudication distinctions
    - Centralized methodology notices
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        from apps.incidents.services.evidence_break import analyze_evidence_break

        try:
            incident = Incident.objects.select_related(
                "prediction", "prediction__model_version", "data_quality"
            ).prefetch_related("iogp_rules", "reviews").get(pk=pk)
        except Incident.DoesNotExist:
            return Response(
                {"error": "Incident not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = analyze_evidence_break(incident)
        return Response(payload, status=status.HTTP_200_OK)


class IncidentCorrectiveActionsAPIView(APIView):
    """
    GET /api/incidents/<uuid:pk>/actions/

    Returns evidence-grounded corrective action recommendations for an incident.

    Actions are selected from the versioned action library based on:
    - Energy type (high_energy_present, energy_type)
    - Control condition (control_condition, control_type)
    - Matched IOGP Life-Saving Rules
    - PSIF prediction status

    No unconstrained LLM generation. All actions trace to structured templates.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        from apps.incidents.services.action_library import get_corrective_actions

        try:
            incident = Incident.objects.select_related(
                "prediction", "prediction__model_version"
            ).prefetch_related("iogp_rules").get(pk=pk)
        except Incident.DoesNotExist:
            return Response(
                {"error": "Incident not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = get_corrective_actions(incident)
        return Response(payload, status=status.HTTP_200_OK)


class IncidentReasoningAPIView(APIView):
    """
    GET /api/incidents/<uuid:pk>/reasoning/

    Returns the comprehensive PSIF Domain Knowledge & Rule-Grounded Reasoning assessment:
    - Multi-source evidence extraction (hazard, exposure, control, consequence)
    - Sequential rule evaluation against authoritative knowledge base (psif_kb_v1.0)
    - Internal reasoning state (EEI Capacity: PSIF_PATHWAY_OPEN, HIGH_ENERGY_CONTROLLED, LOW_ENERGY, INSUFFICIENT_INFORMATION)
    - Reasoning Evidence Strength Matrix
    - ML + Rule Reconciliation & Decision Policy Layer
    - Constrained Language Explanation (Why PSIF, Why NOT PSIF, What Evidence is Missing)
    - Evidence Needed to Close the Case checklist
    - Trace-grounded actions (including Positive Control Learning)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment

        try:
            incident = Incident.objects.select_related(
                "prediction", "prediction__model_version", "data_quality"
            ).prefetch_related("iogp_rules", "reviews").get(pk=pk)
        except Incident.DoesNotExist:
            return Response(
                {"error": "Incident not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        pred = getattr(incident, "prediction", None)
        dq = getattr(incident, "data_quality", None)
        payload = build_incident_reasoning_assessment(incident, prediction=pred, dq_record=dq)
        return Response(payload, status=status.HTTP_200_OK)


class IncidentWorkspaceAPIView(APIView):
    """
    GET /api/incidents/<uuid:pk>/workspace/

    Returns the unified Investigation Workspace payload composing:
    - Incident facts (strictly separated from inferences)
    - Prediction & model status (score, threshold, evidence strength)
    - PSIF domain reasoning & evidence break (why PSIF, why NOT PSIF, 5-node pathway)
    - Applicable IOGP rules (with match type and methodology)
    - Semantic similarity (bounded related incidents)
    - Historical recurrence (site and activity recurrence patterns)
    - Cross-site context (fleet-wide recurrence)
    - Barrier / control context (matched observations, PSIF-linked observations, affected sites)
    - Grounded corrective actions (immediate, corrective, preventive, verification, escalation)
    - Human review & adjudication (tripartite reconciliation, review history, inline CTA)
    - Data quality (VALID, WARNING, CRITICAL status and impact disclosure)
    - Expandable evidence inspector (audit trail linking statements to sources)
    - Factual timeline (verified timestamps only, no inferred chronology)
    - Multi-hazard summary (individual energy pathways)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        from apps.incidents.services.workspace import compose_investigation_workspace

        try:
            incident = Incident.objects.select_related(
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
            ).get(pk=pk)
        except Incident.DoesNotExist:
            return Response(
                {"error": "Incident not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = compose_investigation_workspace(incident, user=request.user)
        return Response(payload, status=status.HTTP_200_OK)

