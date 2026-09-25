"""
Comprehensive Test Suite for Foresight's Why NOT PSIF / Evidence-Break Workbench

Verifies:
1. Obvious NOT PSIF incident (low score, clear broken links)
2. Sparse incident (< 10 words, sparse warning, uncertain chain links, evidence-limited)
3. Missing exposure evidence (hazard present, worker exposure absent/broken)
4. Hazard without consequence (minor event lacking fatal/serious consequence mechanism)
5. Narrative vs structured evidence disagreement & traceability
6. SHAP positive and negative contributors separation
7. Suppressed zero-valued features (noise suppression)
8. Unknown vs NOT PSIF distinction (genuine insufficient information is never implicit NOT PSIF)
9. API permissions (401 unauthenticated, 404 nonexistent, 200 authenticated)
10. UI view rendering and detail page integration
"""

import uuid
import pytest
from django.urls import reverse
from django.utils import timezone
from apps.incidents.models import Incident, IncidentDataQuality
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.evidence_break import (
    analyze_evidence_break,
    ChainState,
)


@pytest.fixture
def test_model_version(db):
    return ModelVersion.objects.create(
        version_label="v1.0-test-prod",
        bert_model_name="emilyalsentzer/Bio_ClinicalBERT",
        xgboost_artifact_path="ml_engine/artifacts/v1.0-test/model.json",
        encoder_artifact_path="ml_engine/artifacts/v1.0-test/encoders.joblib",
        is_active=True,
        metrics={"selected_threshold": 0.5},
    )


@pytest.mark.django_db
class TestEvidenceBreakWorkbenchService:
    """Service-level unit tests for analyze_evidence_break()."""

    def test_obvious_not_psif_incident(self, test_model_version):
        """Incident with minor office trip, effective controls, no energy -> obvious NOT PSIF."""
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Admin Services",
            location="Headquarters Office",
            job_task="Walking to conference room",
            description="Employee tripped on carpet runner in office hallway and sustained a minor thumb sprain.",
            composite_narrative="Employee tripped on carpet runner in office hallway and sustained a minor thumb sprain. First aid applied.",
            energy_type="none",
            high_energy_present="no",
            worker_exposed="no",
            control_condition="effective",
            severity_actual=Incident.SeverityActual.FIRST_AID,
            severity_potential=Incident.SeverityPotential.LOW,
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.042,
            risk_level=PredictionResult.RiskLevel.LOW,
            psif_predicted=False,
            evidence_strength="High",
            top_factors=[
                {"feature": "office_environment", "contribution": -0.42},
                {"feature": "first_aid_only", "contribution": -0.31},
                {"feature": "minor_sprain", "contribution": -0.15},
                {"feature": "carpet_runner", "contribution": 0.0001},  # zero feature
            ]
        )

        res = analyze_evidence_break(incident)

        # Primary decision & score terminology
        assert res["prediction_summary"]["binary_decision"] == "NOT PSIF"
        assert res["prediction_summary"]["is_psif"] is False
        assert res["prediction_summary"]["score_label"] == "PSIF Model Score"
        assert "calibrated probability" in res["prediction_summary"]["score_notice"]

        # Chain links
        chain_map = {link["link_id"]: link for link in res["evidence_chain"]}
        assert chain_map["hazard_source"]["state"] == ChainState.MISSING
        assert chain_map["exposure"]["state"] == ChainState.MISSING
        assert chain_map["control"]["state"] == ChainState.MISSING  # Controls held / no failure
        assert chain_map["credible_consequence"]["state"] == ChainState.MISSING
        assert chain_map["escalation"]["state"] == ChainState.MISSING

        # Evidence breaks identified
        break_categories = [b["category"] for b in res["evidence_breaks"]]
        assert "hazard_missing" in break_categories
        assert "consequence_missing" in break_categories

        # What would change this assessment
        assert len(res["what_would_change"]) > 0
        assert any("energy" in w.lower() for w in res["what_would_change"])

        # SHAP separation and zero-suppression
        mc = res["model_contributions"]
        assert len(mc["negative_contributors"]) == 3
        assert len(mc["positive_contributors"]) == 0
        assert mc["suppressed_count"] == 1
        assert mc["suppressed_contributors"][0]["feature"] == "carpet_runner"
        assert mc["disclaimer"] == "Model contribution — not causality."

    def test_sparse_narrative_incident(self, test_model_version):
        """Incident with <10 words must be flagged as evidence-limited, not affirmative safe."""
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            description="Valve leak observed.",
            composite_narrative="Valve leak observed.",
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.15,
            risk_level=PredictionResult.RiskLevel.LOW,
            psif_predicted=False,
            evidence_strength="Low",
            is_sparse_input=True,
        )

        res = analyze_evidence_break(incident)

        # Governance & sparse warning
        assert res["governance"]["is_sparse"] is True
        assert "evidence-limited" in res["governance"]["sparse_warning"]

        # Chain states should reflect uncertainty due to sparse text
        chain_map = {link["link_id"]: link for link in res["evidence_chain"]}
        assert chain_map["hazard_source"]["state"] == ChainState.UNCERTAIN
        assert chain_map["exposure"]["state"] == ChainState.UNCERTAIN
        assert chain_map["control"]["state"] == ChainState.UNCERTAIN
        assert chain_map["credible_consequence"]["state"] == ChainState.UNCERTAIN

        # Evidence break includes sparse narrative notice
        break_categories = [b["category"] for b in res["evidence_breaks"]]
        assert "sparse_narrative" in break_categories
        sparse_break = next(b for b in res["evidence_breaks"] if b["category"] == "sparse_narrative")
        assert "evidence-limited rather than affirmative proof of safety" in sparse_break["description"]

    def test_missing_exposure_evidence(self, test_model_version):
        """High energy present (e.g. high pressure steam), but no worker exposure."""
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Steam Generation",
            location="Boiler Unit 4",
            description="High pressure steam line blew gasket during automated purge. The area was fully barricaded with no personnel present or exposed.",
            composite_narrative="High pressure steam line blew gasket during automated purge. The area was fully barricaded with no personnel present or exposed.",
            energy_type="thermal",
            high_energy_present="yes",
            worker_exposed="no",
            control_condition="failed",
            control_failed_bypassed=True,
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.38,
            risk_level=PredictionResult.RiskLevel.MEDIUM,
            psif_predicted=False,
            evidence_strength="Moderate",
            top_factors=[
                {"feature": "high_pressure_steam", "contribution": 0.35},
                {"feature": "no_personnel_exposed", "contribution": -0.45},
            ]
        )

        res = analyze_evidence_break(incident)

        chain_map = {link["link_id"]: link for link in res["evidence_chain"]}
        assert chain_map["hazard_source"]["state"] == ChainState.SUPPORTED
        assert chain_map["control"]["state"] == ChainState.SUPPORTED  # Gasket failure
        assert chain_map["exposure"]["state"] == ChainState.MISSING    # No worker exposed

        # Verify specific break for high energy but missing exposure
        break_categories = [b["category"] for b in res["evidence_breaks"]]
        assert "exposure_missing" in break_categories
        exp_break = next(b for b in res["evidence_breaks"] if b["category"] == "exposure_missing")
        assert "Direct Exposure Not Established" in exp_break["title"]

        # Actionable change recommendation focuses on worker location
        assert any("worker position" in w.lower() or "line of fire" in w.lower() for w in res["what_would_change"])

    def test_hazard_without_consequence(self, test_model_version):
        """Energy present but physical mechanism lacks serious injury / fatal capability."""
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Logistics",
            description="Small 12V battery dropped 10cm from workbench onto rubber mat. Battery case intact, no chemical release, no injury.",
            composite_narrative="Small 12V battery dropped 10cm from workbench onto rubber mat. Battery case intact, no chemical release, no injury.",
            energy_type="electrical",
            high_energy_present="no",
            worker_exposed="yes",
            severity_potential=Incident.SeverityPotential.LOW,
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.08,
            risk_level=PredictionResult.RiskLevel.LOW,
            psif_predicted=False,
            evidence_strength="High",
        )

        res = analyze_evidence_break(incident)

        chain_map = {link["link_id"]: link for link in res["evidence_chain"]}
        assert chain_map["credible_consequence"]["state"] == ChainState.MISSING
        assert "consequence_missing" in [b["category"] for b in res["evidence_breaks"]]

    def test_narrative_and_structured_disagreement_traceability(self, test_model_version):
        """Structured field says no energy, but narrative mentions 480V arc flash -> traceable evidence captures both."""
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Electrical Maintenance",
            description="Technician was inspecting MCC panel when an arc flash and high voltage explosion occurred.",
            composite_narrative="Technician was inspecting MCC panel when an arc flash and high voltage explosion occurred.",
            energy_type="none",
            high_energy_present="no",
            worker_exposed="yes",
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.78,
            risk_level=PredictionResult.RiskLevel.CRITICAL,
            psif_predicted=True,
            evidence_strength="High",
        )

        res = analyze_evidence_break(incident)

        hazard_link = next(l for l in res["evidence_chain"] if l["link_id"] == "hazard_source")
        assert hazard_link["state"] == ChainState.SUPPORTED
        
        # Verify narrative quote traceability
        trace_types = [t["source_type"] for t in hazard_link["traceable_items"]]
        assert "narrative_quote" in trace_types
        quotes = [t["quote"] for t in hazard_link["traceable_items"] if t["source_type"] == "narrative_quote"]
        assert any("arc flash" in q.lower() or "voltage" in q.lower() for q in quotes)

    def test_unknown_versus_not_psif_distinction(self):
        """An incident without a prediction must be UNKNOWN, never an implicit NOT PSIF."""
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            description="Recent unanalyzed incident report awaiting pipeline execution.",
            composite_narrative="Recent unanalyzed incident report awaiting pipeline execution.",
        )

        res = analyze_evidence_break(incident)

        assert res["prediction_summary"]["binary_decision"] == "UNKNOWN"
        assert res["prediction_summary"]["score"] is None
        assert res["prediction_summary"]["is_psif"] is False

    def test_human_insufficient_information_governance(self, test_model_version):
        """Human HSE review of INSUFFICIENT_INFORMATION must be clearly flagged and not treated as NOT PSIF."""
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            description="Contractor reported incident with missing witness statements and unclear timeline.",
            composite_narrative="Contractor reported incident with missing witness statements and unclear timeline.",
            adjudication_status=Incident.AdjudicationStatus.ADJUDICATED,
            is_psif_human_label=None,  # Insufficient information determination
            adjudicated_human_decision="INSUFFICIENT_INFORMATION",
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.22,
            risk_level=PredictionResult.RiskLevel.LOW,
            psif_predicted=False,
        )

        res = analyze_evidence_break(incident)

        assert res["governance"]["is_human_insufficient"] is True
        assert "not an affirmative NOT PSIF" in res["governance"]["human_insufficient_notice"]


@pytest.mark.django_db
class TestEvidenceBreakAPIAndUI:
    """Integration tests for the API endpoint and UI views."""

    def test_api_unauthenticated_returns_401(self, api_client):
        """Unauthenticated requests must be rejected with 401 or 403."""
        random_id = uuid.uuid4()
        url = reverse("incidents_api:incident_evidence_break", kwargs={"pk": random_id})
        response = api_client.get(url)
        assert response.status_code in (401, 403)

    def test_api_nonexistent_incident_returns_404(self, api_client, analyst_user):
        """Nonexistent incident UUID must return 404."""
        api_client.force_authenticate(user=analyst_user)
        random_id = uuid.uuid4()
        url = reverse("incidents_api:incident_evidence_break", kwargs={"pk": random_id})
        response = api_client.get(url)
        assert response.status_code == 404
        assert "Incident not found." in response.data["error"]

    def test_api_returns_complete_evidence_break_payload(self, api_client, analyst_user, test_model_version):
        """Authenticated GET returns complete payload schema with all required keys."""
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Operations",
            location="Plant 1",
            description="Valve bonnet leak during water line flush. Low pressure water, no hazard.",
            composite_narrative="Valve bonnet leak during water line flush. Low pressure water, no hazard.",
            energy_type="none",
            high_energy_present="no",
            worker_exposed="no",
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.12,
            risk_level=PredictionResult.RiskLevel.LOW,
            psif_predicted=False,
            evidence_strength="Moderate",
            top_factors=[
                {"feature": "water_flush", "contribution": -0.25},
                {"feature": "low_pressure", "contribution": -0.15},
                {"feature": "noise_feature", "contribution": 0.0002},
            ]
        )

        api_client.force_authenticate(user=analyst_user)
        url = reverse("incidents_api:incident_evidence_break", kwargs={"pk": incident.id})
        response = api_client.get(url)

        assert response.status_code == 200
        data = response.data

        # Verify key top-level keys
        assert "prediction_summary" in data
        assert "evidence_chain" in data
        assert "evidence_breaks" in data
        assert "what_would_change" in data
        assert "model_contributions" in data
        assert "governance" in data
        assert "methodology" in data

        # Verify exact required terminology
        assert data["prediction_summary"]["score_label"] == "PSIF Model Score"
        assert data["model_contributions"]["disclaimer"] == "Model contribution — not causality."
        assert len(data["evidence_chain"]) == 5
        assert data["model_contributions"]["suppressed_count"] == 1

    def test_ui_evidence_break_view_renders_successfully(self, client, analyst_user, test_model_version):
        """Dedicated UI view /incidents/<pk>/evidence-break/ renders cleanly for authorized analyst."""
        client.force_login(analyst_user)
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Drilling",
            location="Rig 7",
            description="Routine pump inspection completed with no safety anomalies.",
            composite_narrative="Routine pump inspection completed with no safety anomalies.",
            energy_type="none",
            high_energy_present="no",
            worker_exposed="no",
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.05,
            risk_level=PredictionResult.RiskLevel.LOW,
            psif_predicted=False,
            evidence_strength="High",
        )

        url = reverse("incidents:evidence_break", kwargs={"pk": incident.id})
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Verify UI contents
        assert "Why NOT PSIF / Evidence-Break Workbench" in content
        assert "SIF Precursor Evidence Chain" in content
        assert "PSIF Model Score" in content
        assert "Model contribution — not causality." in content
        assert "Methodology &amp; Provenance Disclosures" in content or "Methodology & Provenance Disclosures" in content
        assert "SUPPORTED" in content
        assert "MISSING" in content

    def test_ui_detail_page_includes_evidence_break_widget(self, client, analyst_user, test_model_version):
        """Incident detail page includes the SIF Precursor Evidence Chain widget and workbench link."""
        client.force_login(analyst_user)
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Maintenance",
            location="Refinery B",
            description="Air filter replacement on ventilation unit. Technician used step stool properly.",
            composite_narrative="Air filter replacement on ventilation unit. Technician used step stool properly.",
            energy_type="none",
            high_energy_present="no",
            worker_exposed="yes",
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.09,
            risk_level=PredictionResult.RiskLevel.LOW,
            psif_predicted=False,
            evidence_strength="High",
        )

        url = reverse("incidents:detail", kwargs={"pk": incident.id})
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Detail page widget elements
        assert "SIF Precursor Evidence Chain" in content
        assert "This is an evidence representation, not a causal claim." in content
        assert "Launch Evidence-Break Workbench" in content
        assert f"/incidents/{incident.id}/evidence-break/" in content

    def test_ui_psif_case_renders_why_psif_and_open_pathway(self, client, analyst_user, test_model_version):
        """PSIF incident renders affirmative Why PSIF analysis and open pathway explanation."""
        client.force_login(analyst_user)
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Drilling",
            location="Rig Floor",
            description="Worker struck by pressurized hydraulic hose following failed isolation valve during pipe disconnection.",
            composite_narrative="Worker struck by pressurized hydraulic hose following failed isolation valve during pipe disconnection.",
            energy_type="pressure",
            high_energy_present="yes",
            worker_exposed="yes",
            control_condition="failed",
            severity_actual=Incident.SeverityActual.LOST_TIME,
            severity_potential=Incident.SeverityPotential.FATALITY,
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.92,
            risk_level=PredictionResult.RiskLevel.CRITICAL,
            psif_predicted=True,
            evidence_strength="High",
        )

        url = reverse("incidents:evidence_break", kwargs={"pk": incident.id})
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Official decision & executive statement
        assert "PSIF" in content
        assert "An open high-energy SIF pathway is supported by the available evidence." in content
        assert "Why PSIF Analysis" in content
        assert "Pathway Remained Open" in content

        # Grounded actions rendered
        assert "Grounded Actions &amp; Next Steps" in content or "Grounded Actions & Next Steps" in content
        assert "Suggested next steps" in content

        # Source Traceability
        assert "Extracted Narrative Excerpts" in content
        assert "Structured Field Verification" in content

    def test_ui_controlled_high_energy_case_renders_interrupted_pathway(self, client, analyst_user, test_model_version):
        """Controlled high energy incident renders Why NOT PSIF and pathway interrupted."""
        client.force_login(analyst_user)
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Logistics",
            location="Crane Yard",
            description="Heavy pipe slipped from rigging during crane lift, falling into barricaded exclusion zone. Rigger remained safe outside zone.",
            composite_narrative="Heavy pipe slipped from rigging during crane lift, falling into barricaded exclusion zone. Rigger remained safe outside zone.",
            energy_type="suspended_load",
            high_energy_present="yes",
            worker_exposed="no",
            control_condition="effective",
            severity_actual=Incident.SeverityActual.NONE,
            severity_potential=Incident.SeverityPotential.MODERATE,
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.22,
            risk_level=PredictionResult.RiskLevel.LOW,
            psif_predicted=False,
            evidence_strength="High",
        )

        url = reverse("incidents:evidence_break", kwargs={"pk": incident.id})
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Official decision & executive statement
        assert "NOT PSIF" in content
        assert "The available evidence indicates that the high-energy pathway was controlled or interrupted." in content
        assert "Pathway Interrupted by Barrier" in content
        assert "Evidence Strength Matrix" in content

    def test_ui_insufficient_information_renders_checklist(self, client, analyst_user, test_model_version):
        """Sparse report with unknown isolation state renders dedicated Insufficient Information checklist."""
        client.force_login(analyst_user)
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Operations",
            location="Compressor Shed",
            description="Loud gas hiss heard near compressor manifold.",
            composite_narrative="Loud gas hiss heard near compressor manifold.",
            energy_type="pressure",
            high_energy_present="yes",
            worker_exposed="unknown",
            control_condition="unknown",
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.48,
            risk_level=PredictionResult.RiskLevel.MEDIUM,
            psif_predicted=False,
            evidence_strength="Low",
        )

        url = reverse("incidents:evidence_break", kwargs={"pk": incident.id})
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        assert "INSUFFICIENT INFORMATION" in content
        assert "Available information is insufficient to establish or refute the PSIF pathway." in content
        assert "Evidence Needed to Close the Case" in content
        assert "Human HSE Review Recommended for This Incident" in content

    def test_ui_conflicting_evidence_renders_explicit_conflict_card(self, client, analyst_user, test_model_version):
        """Incident with contradictory control statements renders explicit CONFLICTING EVIDENCE card."""
        client.force_login(analyst_user)
        incident = Incident.objects.create(
            incident_date=timezone.now().date(),
            department="Refining",
            location="Hydrotreater Unit",
            description="Isolation was verified before work commenced. However, residual pressure escaped when flange was loosened and worker was struck in the release path.",
            composite_narrative="Isolation was verified before work commenced. However, residual pressure escaped when flange was loosened and worker was struck in the release path.",
            energy_type="pressure",
            high_energy_present="yes",
            worker_exposed="yes",
            control_condition="effective",
        )
        PredictionResult.objects.create(
            incident=incident,
            model_version=test_model_version,
            psif_probability=0.74,
            risk_level=PredictionResult.RiskLevel.HIGH,
            psif_predicted=True,
            evidence_strength="Low",
        )

        url = reverse("incidents:evidence_break", kwargs={"pk": incident.id})
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode("utf-8")

        assert "CONFLICTING EVIDENCE" in content
        assert "Evidence Statement A (Reported Barrier)" in content
        assert "Evidence Statement B (Contradictory Finding)" in content
        assert "Why the conflict matters:" in content
        assert "What needs to be verified:" in content
        assert "Human Review Recommendation:" in content
        assert "Mandatory HSE Investigator Adjudication required before closing this file." in content

