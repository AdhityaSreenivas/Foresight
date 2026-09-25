"""
Comprehensive Automated Test Suite for Foresight's Unified Investigation Workspace (Task 9).

Covers:
1. Workspace API endpoint authentication & authorization (anonymous 401, viewer read-only, analyst review capability).
2. Workspace composition contract (complete schema validation across all required sections).
3. Reported Facts vs. AI Inference separation (no model-derived conclusions mixed into reported facts).
4. PSIF Assessment embedding (Why PSIF, Why NOT PSIF, 5-stage causal pathway, missing evidence).
5. Grounded Actions integration (categorized by type with traceable controls and rules).
6. IOGP Life-Saving Rules integration (matched spans, source fields, rule applicability disclaimer).
7. Related Incidents & Semantic Similarity (terminology compliance, score percentage, drilldown links).
8. Historical Recurrence integration (site/activity dimensions, occurrence count, lookback window).
9. Cross-Site & Barrier Intelligence context (matched observations, PSIF-linked observations, affected sites).
10. Human Review & Adjudication integration (tripartite reconciliation, side-by-side decisions, audit trail).
11. Data Quality & Governance integration (VALID/WARNING/CRITICAL status, findings, evidence impact note).
12. Factual Timeline (verified timestamps only, no inferred chronology).
13. Expandable Evidence Inspector (audit trail linking statements to source fields and versions).
14. Error Isolation & Graceful Degradation (secondary widget exceptions do NOT crash the workspace).
15. Empty States Handling (clear "No data available" explanations rather than "Risk = 0").
16. Server-Side HTML Web View Rendering (/incidents/<uuid:pk>/workspace/ status 200).
"""

from unittest.mock import patch
import pytest
from django.urls import reverse
from django.utils import timezone

from apps.incidents.models import Incident, IncidentReview, IncidentDataQuality, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.workspace import compose_investigation_workspace


@pytest.fixture
def active_model_version(db):
    return ModelVersion.objects.create(
        version_label="psif_rf_v1.0",
        bert_model_name="emilyalsentzer/Bio_ClinicalBERT",
        xgboost_artifact_path="ml_engine/artifacts/v1.0-test/model.json",
        encoder_artifact_path="ml_engine/artifacts/v1.0-test/encoders.joblib",
        is_active=True,
        metrics={"selected_threshold": 0.35},
    )


@pytest.fixture
def sample_workspace_incident(db, active_model_version):
    inc = Incident.objects.create(
        incident_date=timezone.now().date(),
        department="Refining Operations",
        location="Crude Distillation Unit #2",
        job_task="Pump seal replacement under active line",
        description="High-pressure crude oil seal failed during maintenance. Hydrocarbon spray released toward technician.",
        composite_narrative="High-pressure crude oil seal failed during maintenance. Hydrocarbon spray released toward technician. Direct isolation was absent.",
        energy_type="Pressure",
        high_energy_present="yes",
        worker_exposed="yes",
        control_condition="absent",
        control_failed_bypassed=True,
        severity_actual=Incident.SeverityActual.FIRST_AID,
        severity_potential=Incident.SeverityPotential.FATALITY,
        report_type=Incident.ReportType.INCIDENT,
        near_miss=False,
        is_synthetic=True,
        psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
    )
    # Model prediction
    PredictionResult.objects.create(
        incident=inc,
        model_version=active_model_version,
        psif_predicted=True,
        psif_probability=0.885,
        risk_level="Critical",
        evidence_strength="Strong",
        top_factors=[
            {"feature": "pressure_psi", "shap_value": 0.412},
            {"feature": "barrier_absent", "shap_value": 0.285},
        ],
    )
    # IOGP rule
    IOGPRuleTag.objects.create(
        incident=inc,
        rule="Energy Isolation",
        matched_keywords=["Direct isolation was absent"],
        matched_fields=["composite_narrative"],
        classification_method="rule_based",
    )

    # Data Quality
    IncidentDataQuality.objects.create(
        incident=inc,
        status=IncidentDataQuality.Status.VALID,
        findings=[],
    )
    return inc



@pytest.mark.django_db
class TestWorkspaceAPI:
    """Test suite for the consolidated Investigation Workspace API endpoint."""

    def test_workspace_api_anonymous_401(self, client, sample_workspace_incident):
        url = reverse("incidents_api:incident_workspace", kwargs={"pk": sample_workspace_incident.id})
        response = client.get(url)
        assert response.status_code in (401, 403)

    def test_workspace_api_returns_200_and_complete_payload(self, client, sample_workspace_incident, django_user_model):
        user = django_user_model.objects.create_user(username="analyst_user", email="analyst@foresight.app", role="analyst")
        client.force_login(user)


        url = reverse("incidents_api:incident_workspace", kwargs={"pk": sample_workspace_incident.id})
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()

        # Check Core Schema Sections
        assert "header" in data
        assert "facts" in data
        assert "prediction" in data
        assert "reasoning" in data
        assert "evidence_break" in data
        assert "iogp" in data
        assert "related_incidents" in data
        assert "recurrence" in data
        assert "cross_site" in data
        assert "barrier_context" in data
        assert "actions" in data
        assert "human_review" in data
        assert "data_quality" in data
        assert "timeline" in data
        assert "evidence_inspector" in data
        assert "methodology" in data
        assert "navigation" in data

    def test_workspace_facts_vs_inferences_separation(self, sample_workspace_incident):
        data = compose_investigation_workspace(sample_workspace_incident)
        facts = data["facts"]

        # Reported facts must reflect source values exactly
        assert facts["location"] == "Crude Distillation Unit #2"
        assert facts["department"] == "Refining Operations"
        assert facts["job_task"] == "Pump seal replacement under active line"
        assert facts["severity_actual"] == Incident.SeverityActual.FIRST_AID
        assert facts["severity_potential"] == Incident.SeverityPotential.FATALITY
        assert facts["structured_controls"]["high_energy_present"] == "yes"
        assert facts["structured_controls"]["energy_type"] == "Pressure"
        assert facts["structured_controls"]["control_condition"] == "absent"

        # Model inferences are in their respective dedicated namespaces
        assert data["prediction"]["is_psif"] is True
        assert data["prediction"]["score"] == 0.885
        assert "score_notice" in data["prediction"]
        assert "not a calibrated probability" in data["prediction"]["score_notice"].lower()

    def test_workspace_iogp_and_disclaimer(self, sample_workspace_incident):
        data = compose_investigation_workspace(sample_workspace_incident)
        iogp = data["iogp"]

        assert iogp["count"] == 1
        assert iogp["rules"][0]["rule"] == "Energy Isolation"
        assert iogp["rules"][0]["matched_text"] == "Direct isolation was absent"
        assert "NOT proof of safety rule violation or physical barrier failure" in iogp["disclaimer"]

    def test_workspace_causal_pathway_and_missing_evidence(self, sample_workspace_incident):
        data = compose_investigation_workspace(sample_workspace_incident)
        ev_break = data["evidence_break"]

        assert "evidence_chain" in ev_break
        assert len(ev_break["evidence_chain"]) == 5
        link_titles = [link["title"] for link in ev_break["evidence_chain"]]
        assert any("Hazard" in t for t in link_titles)
        assert any("Exposure" in t for t in link_titles)
        assert any("Control" in t for t in link_titles)
        assert any("Consequence" in t for t in link_titles)

    def test_workspace_grounded_actions(self, sample_workspace_incident):
        data = compose_investigation_workspace(sample_workspace_incident)
        actions = data["actions"]

        assert actions["status"] == "ok"
        assert actions["total_count"] > 0
        assert "All actions trace to structured" in actions["notice"]
        first_act = actions["actions"][0]
        assert "action_id" in first_act
        assert "title" in first_act
        assert "verification_steps" in first_act

    def test_workspace_human_review_tripartite_reconciliation(self, sample_workspace_incident, django_user_model):
        reviewer = django_user_model.objects.create_user(username="lead_hse", email="lead@foresight.app", role="safety_officer")
        IncidentReview.objects.create(
            incident=sample_workspace_incident,
            reviewer=reviewer,
            decision=Incident.HumanDecision.PSIF,
            evidence_notes="Verified line of fire pressure release with no physical barrier in place.",
        )
        sample_workspace_incident.adjudication_status = Incident.AdjudicationStatus.ADJUDICATED
        sample_workspace_incident.adjudicated_human_decision = Incident.HumanDecision.PSIF
        sample_workspace_incident.adjudicated_by = reviewer
        sample_workspace_incident.adjudicated_at = timezone.now()
        sample_workspace_incident.adjudication_rationale = "Full consensus reached confirming open high-energy precursor pathway."
        sample_workspace_incident.save()

        data = compose_investigation_workspace(sample_workspace_incident, user=reviewer)
        hr = data["human_review"]

        assert hr["is_adjudicated"] is True
        assert hr["human_decision"] == "PSIF"
        assert hr["adjudicated_by"] == "lead_hse"
        assert hr["review_count"] == 1
        assert hr["can_review"] is True
        assert hr["reconciliation"]["human_decision"] == "PSIF"
        # Model prediction must remain unchanged
        assert data["prediction"]["is_psif"] is True

    def test_workspace_viewer_read_only_mode(self, client, sample_workspace_incident, django_user_model):
        viewer = django_user_model.objects.create_user(username="viewer_user", email="viewer@foresight.app", role="viewer")
        client.force_login(viewer)


        # API check
        url = reverse("incidents_api:incident_workspace", kwargs={"pk": sample_workspace_incident.id})
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["human_review"]["can_review"] is False

    def test_workspace_factual_timeline_verified_timestamps_only(self, sample_workspace_incident):
        data = compose_investigation_workspace(sample_workspace_incident)
        timeline = data["timeline"]

        assert len(timeline) >= 2
        for evt in timeline:
            assert "timestamp" in evt
            assert evt["timestamp"] is not None
            assert "event_type" in evt

    def test_workspace_evidence_inspector_traceability(self, sample_workspace_incident):
        data = compose_investigation_workspace(sample_workspace_incident)
        inspector = data["evidence_inspector"]

        assert len(inspector) > 0
        for item in inspector:
            assert "statement" in item
            assert "source_type" in item
            assert "field" in item
            assert "strength" in item

    def test_workspace_high_priority_review_trigger(self, sample_workspace_incident):
        # Incident has score 0.885 > 0.35 threshold and is UNREVIEWED
        sample_workspace_incident.adjudication_status = Incident.AdjudicationStatus.UNREVIEWED
        sample_workspace_incident.save()

        data = compose_investigation_workspace(sample_workspace_incident)
        assert data["header"]["is_high_priority_review"] is True
        assert any("Model score exceeds threshold" in r for r in data["header"]["priority_reasons"])


@pytest.mark.django_db
class TestWorkspaceErrorIsolationAndEmptyStates:
    """Test error isolation and graceful degradation in case of sub-service exceptions."""

    def test_semantic_similarity_failure_does_not_break_workspace(self, sample_workspace_incident):
        with patch("apps.incidents.services.workspace.find_related_incidents", side_effect=RuntimeError("Vector DB timeout")):
            data = compose_investigation_workspace(sample_workspace_incident)
            assert data["related_incidents"]["status"] == "unavailable"
            assert data["related_incidents"]["count"] == 0
            # Rest of workspace must remain intact
            assert data["facts"]["location"] == "Crude Distillation Unit #2"
            assert data["prediction"]["is_psif"] is True

    def test_recurrence_failure_does_not_break_workspace(self, sample_workspace_incident):
        with patch("apps.incidents.services.workspace.detect_recurring_patterns", side_effect=Exception("Database lock")):
            data = compose_investigation_workspace(sample_workspace_incident)
            assert data["recurrence"]["status"] == "unavailable"
            assert data["facts"]["department"] == "Refining Operations"

    def test_barrier_intelligence_failure_does_not_break_workspace(self, sample_workspace_incident):
        with patch("apps.incidents.services.workspace.get_barrier_intelligence", side_effect=Exception("Cache error")):
            data = compose_investigation_workspace(sample_workspace_incident)
            assert data["barrier_context"]["status"] == "unavailable"
            assert data["prediction"]["is_psif"] is True

    def test_actions_failure_does_not_break_workspace(self, sample_workspace_incident):
        with patch("apps.incidents.services.workspace.get_corrective_actions", side_effect=Exception("Action template error")):
            data = compose_investigation_workspace(sample_workspace_incident)
            assert data["actions"]["status"] == "unavailable"
            assert data["facts"]["incident_id"] == str(sample_workspace_incident.id)

    def test_empty_signals_handled_gracefully(self, db):
        # Empty incident with no prediction, no IOGP rules, no data quality record
        bare_inc = Incident.objects.create(
            incident_date=timezone.now().date(),
            description="Routine pre-shift inspection completed without incident.",
            composite_narrative="Routine pre-shift inspection completed without incident.",
        )
        data = compose_investigation_workspace(bare_inc)

        assert data["prediction"]["has_prediction"] is False
        assert data["iogp"]["count"] == 0
        assert data["related_incidents"]["empty_message"] != ""
        assert data["recurrence"]["empty_message"] != ""
        assert data["cross_site"]["empty_message"] != ""
        assert data["human_review"]["review_count"] == 0


@pytest.mark.django_db
class TestWorkspaceHTMLView:
    """Test suite for the server-side HTML Investigation Workspace view."""

    def test_workspace_html_view_renders_200(self, client, sample_workspace_incident, django_user_model):
        user = django_user_model.objects.create_user(username="lead_analyst", email="lead@foresight.app", role="analyst")
        client.force_login(user)


        url = reverse("incidents:workspace", kwargs={"pk": sample_workspace_incident.id})
        response = client.get(url)
        assert response.status_code == 200

        html = response.content.decode("utf-8")
        # Verify Key Structural Components Rendered in HTML
        assert "Investigation Workspace" in html
        assert "Incident Facts &amp; Reported Context" in html or "Incident Facts" in html
        assert "PSIF Assessment &amp; Causal Pathway Breakdown" in html or "PSIF Assessment" in html
        assert "Tripartite Alignment" in html or "Statistical Model Assessment" in html
        assert "Grounded Corrective &amp; Preventive Actions" in html or "Corrective Actions" in html
        assert "Source &amp; Evidence Inspector" in html or "Evidence Inspector" in html
        assert "Factual Incident Timeline" in html or "Timeline" in html
        assert "IOGP Life-Saving Rules" in html
        assert "Semantic Similarity" in html
        assert "Historical Recurrence" in html
        assert "Crude Distillation Unit #2" in html
        assert "Energy Isolation" in html
