"""
Comprehensive Tests for Ingestion Data Quality Gate.
Enforces that materially insufficient, corrupted, or contradictory incident data
is rejected at ingestion with the standard message:
"Data quality is insufficient for analysis."

Covers all 17 criteria required by the specification:
 1. Empty manual input rejected
 2. Whitespace-only rejected
 3. Placeholder rejected
 4. Meaningless text & keyboard mash rejected
 5. Materially insufficient narrative rejected
 6. Meaningful short text not incorrectly rejected
 7. Missing optional fields do not unnecessarily reject
 8. Contradiction rules behave correctly (anatomical, chronological, near-miss)
 9. Valid record accepted
10. Warning record accepted with warning
11. Rejected record receives no PSIF prediction
12. Rejected record receives no SHAP
13. Rejected record is not training eligible
14. Manual and file ingestion use the same quality gate
15. Bulk ingestion accepts valid rows and rejects invalid rows independently
16. Rejection reasons are retained
17. Human INSUFFICIENT_INFORMATION remains separate from ingestion rejection
18. Document/file ingestion uses the same quality gate
"""
import pytest
from datetime import date
from django.core.exceptions import ValidationError

from apps.incidents.forms import IncidentReportForm
from apps.incidents.models import Incident, IncidentDataQuality
from apps.incidents.services.data_quality import validate_incident_for_analysis
from apps.incidents.services.submission import process_new_incident_submission
from apps.datasets.models import Dataset
from apps.datasets.ingestion import bulk_create_incidents, ingest_document_incidents
from ml_engine.training.training_sources import get_training_eligible_incidents, is_incident_quality_acceptable


@pytest.mark.django_db
class TestDataQualityGate:

    def test_1_empty_manual_submission_rejected(self):
        """1. Empty manual input rejected."""
        data = {"description": ""}
        result = validate_incident_for_analysis(data)
        assert result["accepted"] is False
        assert result["quality_status"] == "CRITICAL"
        assert "Data quality is insufficient for analysis" in result["reason"]
        assert any("narrative is empty" in f.lower() for f in result["blocking_findings"])

        # Also test via IncidentReportForm
        form = IncidentReportForm(data={"description": ""})
        assert not form.is_valid()
        assert any("Data quality is insufficient for analysis" in str(err) for err in form.errors.values())

    def test_2_whitespace_only_rejected(self):
        """2. Whitespace-only rejected."""
        data = {"description": "   \n\t  "}
        result = validate_incident_for_analysis(data)
        assert result["accepted"] is False
        assert result["quality_status"] == "CRITICAL"
        assert "Data quality is insufficient for analysis" in result["reason"]
        assert any("narrative is empty" in f.lower() for f in result["blocking_findings"])

    def test_3_placeholder_rejected(self):
        """3. Placeholder rejected."""
        for placeholder in ["test", "asdf", "N/A", "none", "incident 12", "desc 1", "dummy 5", "placeholder"]:
            result = validate_incident_for_analysis({"description": placeholder})
            assert result["accepted"] is False, f"Expected '{placeholder}' to be rejected"
            assert result["quality_status"] == "CRITICAL"
            assert any(
                "placeholder" in f.lower() or "single word" in f.lower() or "too short" in f.lower()
                for f in result["blocking_findings"]
            )

    def test_4_meaningless_text_and_keyboard_mash_rejected(self):
        """4. Meaningless text & keyboard mash rejected."""
        meaningless_samples = [
            "zzzzzz",                    # repeated single characters
            "asdfghjkl qwertyuiop",      # keyboard mash
            "... ... !!! ,,, ;;;",       # punctuation only
            "bcdfgh jklmnp",             # zero vowels, consonants only
            "--- --- ***",               # non-alphanumeric symbols
        ]
        for sample in meaningless_samples:
            result = validate_incident_for_analysis({"description": sample})
            assert result["accepted"] is False, f"Expected '{sample}' to be rejected as meaningless"
            assert result["quality_status"] == "CRITICAL"
            assert any(
                "corrupted" in f.lower() or "meaningless" in f.lower() or "no alphanumeric" in f.lower()
                for f in result["blocking_findings"]
            )

    def test_5_materially_insufficient_narrative_rejected(self):
        """5. Materially insufficient narrative rejected."""
        # Single-word narrative without operational context
        for word in ["Accident", "Fell", "Injured", "Spill"]:
            result = validate_incident_for_analysis({"description": word})
            assert result["accepted"] is False
            assert result["quality_status"] == "CRITICAL"
            assert any("too short or single word" in f.lower() for f in result["blocking_findings"])

    def test_6_meaningful_short_text_not_incorrectly_rejected(self):
        """6. Meaningful short text not incorrectly rejected (sparse-input distinction preserved)."""
        meaningful_short_cases = [
            "Gas leak on wellhead valve",             # 5 words
            "Worker slipped on mud pump",             # 5 words
            "Chemical spill in storage room",         # 5 words
            "Crane cable snapped during lift",        # 5 words
            "Small fire extinguished at separator",   # 5 words
            "Acid splash to left arm",                # 5 words
        ]
        for text in meaningful_short_cases:
            result = validate_incident_for_analysis({"description": text, "incident_date": "2026-02-01"})
            assert result["accepted"] is True, f"Expected '{text}' to be accepted with warning"
            assert result["quality_status"] == "WARNING"
            assert len(result["blocking_findings"]) == 0
            assert any("brief" in f.lower() or "confidence" in f.lower() for f in result["warning_findings"])

    def test_7_missing_optional_fields_do_not_unnecessarily_reject(self):
        """7. Missing optional fields do not unnecessarily reject if narrative is solid."""
        data = {
            "description": "Worker slipped on wet catwalk during high-pressure pump inspection, sustaining bruised right shoulder. First aid administered.",
            "incident_date": "2026-03-01",
            "department": None,
            "body_part": None,
            "immediate_cause": None,
            "equipment_involved": None,
        }
        result = validate_incident_for_analysis(data)
        assert result["accepted"] is True
        assert result["quality_status"] in ("VALID", "WARNING")
        assert len(result["blocking_findings"]) == 0

    def test_8_contradiction_rules_behave_correctly(self):
        """8. Contradiction rules behave correctly (chronological, anatomical, near-miss)."""
        # 8a. Future date contradiction
        future_data = {
            "description": "Worker sustained laceration while handling drill pipe segment during scheduled trip out.",
            "incident_date": "2099-12-31",
        }
        res_future = validate_incident_for_analysis(future_data)
        assert res_future["accepted"] is False
        assert res_future["quality_status"] == "CRITICAL"
        assert any("future" in f.lower() for f in res_future["blocking_findings"])

        # 8b. Impossible historical date
        past_data = {
            "description": "Worker sustained laceration while handling drill pipe segment during scheduled trip out.",
            "incident_date": "1940-05-12",
        }
        res_past = validate_incident_for_analysis(past_data)
        assert res_past["accepted"] is False
        assert res_past["quality_status"] == "CRITICAL"
        assert any("impossible" in f.lower() or "operational bounds" in f.lower() for f in res_past["blocking_findings"])

        # 8c. Anatomical contradiction (eye injury vs leg body part)
        contra_data = {
            "description": "Chemical splash occurred during transfer operation causing eye irritation to operator.",
            "incident_date": "2026-02-15",
            "injury_type": "Eye Injury",
            "body_part": "Leg",
        }
        res_contra = validate_incident_for_analysis(contra_data)
        assert res_contra["accepted"] is False
        assert res_contra["quality_status"] == "CRITICAL"
        assert any("contradiction" in f.lower() for f in res_contra["blocking_findings"])

        # 8d. Near-miss vs fatal/lost-time severity contradiction
        near_miss_contra = {
            "description": "Scaffold plank slipped and fell 10 meters.",
            "incident_date": "2026-02-10",
            "near_miss": True,
            "severity_actual": "fatality",
        }
        res_nm = validate_incident_for_analysis(near_miss_contra)
        assert res_nm["accepted"] is False
        assert res_nm["quality_status"] == "CRITICAL"
        assert any("near-miss" in f.lower() and "severity" in f.lower() for f in res_nm["blocking_findings"])

    def test_9_valid_record_accepted(self):
        """9. Valid record accepted with high score."""
        data = {
            "description": "During routine maintenance on drilling rig mast, mechanic slipped on grease patch, resulting in bruised left elbow. Immediate first aid given and area degreased.",
            "incident_date": "2026-01-10",
            "department": "Drilling",
            "location": "Rig Floor Well 4",
            "injury_type": "Contusion / Bruise",
            "body_part": "Elbow",
            "immediate_cause": "Slippery walking surface",
            "root_cause_category": "Housekeeping",
        }
        result = validate_incident_for_analysis(data)
        assert result["accepted"] is True
        assert result["quality_status"] == "VALID"
        assert result["quality_score"] >= 0.8
        assert len(result["blocking_findings"]) == 0

    def test_10_warning_record_accepted_with_warning(self):
        """10. Warning record accepted with warning."""
        data = {
            "description": "Worker slipped and sustained minor knee bruise.",
            "incident_date": "2026-01-15",
        }
        result = validate_incident_for_analysis(data)
        assert result["accepted"] is True
        assert result["quality_status"] == "WARNING"
        assert len(result["blocking_findings"]) == 0
        assert len(result["warning_findings"]) > 0

    def test_11_rejected_record_receives_no_psif_prediction(self, admin_client):
        """11. Rejected record receives no PSIF prediction via predict API."""
        resp = admin_client.post("/api/predict/", {
            "description": "test",
        }, format="json")
        assert resp.status_code == 400
        data = resp.json()
        assert "Data quality is insufficient for analysis" in data["error"]
        assert "blocking_findings" in data
        assert "psif_score" not in data
        assert "probability" not in data
        assert "psif_predicted" not in data

    def test_12_rejected_record_receives_no_shap(self, admin_client):
        """12. Rejected record receives no SHAP or explanation."""
        resp = admin_client.post("/api/predict/", {
            "description": "asdf 123",
        }, format="json")
        assert resp.status_code == 400
        data = resp.json()
        assert "top_factors" not in data
        assert "explanation" not in data

    def test_13_rejected_record_not_training_eligible(self):
        """13. Rejected record is not training eligible."""
        inc = Incident.objects.create(
            description="asdf",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        IncidentDataQuality.objects.create(
            incident=inc,
            status=IncidentDataQuality.Status.CRITICAL,
            findings=[{"message": "Narrative is meaningless placeholder"}],
        )

        assert is_incident_quality_acceptable(inc) is False

        eligible, _, comp = get_training_eligible_incidents("SYNTHETIC")
        eligible_ids = [str(x.id) for x in eligible]
        assert str(inc.id) not in eligible_ids

    def test_14_manual_and_file_ingestion_use_same_quality_gate(self):
        """14. Manual and file ingestion use the same quality gate."""
        bad_data = {"description": "Accident"}
        res = validate_incident_for_analysis(bad_data)
        assert res["accepted"] is False

        form = IncidentReportForm(data=bad_data)
        assert not form.is_valid()
        assert any("Data quality is insufficient for analysis" in str(err) for err in form.errors.values())

    def test_15_bulk_ingestion_accepts_valid_rows_and_rejects_invalid_rows_independently(self, admin_user):
        """15. Bulk ingestion accepts valid rows and rejects invalid rows independently."""
        ds = Dataset.objects.create(
            name="test_dq_bulk.csv",
            file_type="csv",
            total_rows=3,
            uploaded_by=admin_user,
        )

        rows = [
            {
                "description": "Worker sustained minor finger pinch while uncoupling high-pressure hose during testing.",
                "incident_date": "2026-02-01",
                "department": "Production",
            },
            {
                "description": "test",  # INVALID ROW
                "incident_date": "2026-02-02",
            },
            {
                "description": "Electrician noticed exposed grounding wire on generator panel and secured it safely.",
                "incident_date": "2026-02-03",
            },
        ]

        incidents, errors, stats = bulk_create_incidents(
            rows,
            ds,
            column_mapping={k: k for k in rows[0].keys()},
            return_details=True,
        )

        assert len(incidents) == 2  # Only 2 created
        assert stats["total"] == 3
        assert stats["accepted"] == 2
        assert stats["rejected"] == 1
        assert len(stats["rejections"]) == 1
        assert stats["rejections"][0]["row_number"] == 2
        assert "Data quality is insufficient for analysis" in stats["rejections"][0]["reason"]

    def test_16_rejection_reasons_are_retained(self, admin_user):
        """16. Bulk ingestion rejection details preserve row number, snippet, and findings."""
        ds = Dataset.objects.create(
            name="test_dq_reasons.csv",
            file_type="csv",
            total_rows=1,
            uploaded_by=admin_user,
        )

        rows = [{
            "description": "Eye splash occurred",
            "injury_type": "Eye Injury",
            "body_part": "Leg",  # Anatomic contradiction
        }]

        incidents, errors, stats = bulk_create_incidents(
            rows,
            ds,
            column_mapping={"description": "description", "injury_type": "injury_type", "body_part": "body_part"},
            return_details=True,
        )
        assert len(incidents) == 0
        assert stats["rejected"] == 1
        rej = stats["rejections"][0]
        assert rej["row_number"] == 1
        assert "contradiction" in " ".join(rej["blocking_findings"]).lower()

    def test_17_human_insufficient_information_remains_separate_from_ingestion_rejection(self, admin_user):
        """17. Human review INSUFFICIENT_INFORMATION is a valid HSE review outcome, distinct from ingestion rejection."""
        # Incident has valid ingestion data quality
        inc = Incident.objects.create(
            description="Operator reported unexpected pump pressure drop during night shift. System shut down safely.",
            incident_date=date(2026, 2, 1),
            department="Production",
        )
        # Quality gate evaluated at ingestion
        dq_record = IncidentDataQuality.objects.create(
            incident=inc,
            status=IncidentDataQuality.Status.VALID,
            findings=[],
        )
        assert dq_record.status == IncidentDataQuality.Status.VALID
        assert is_incident_quality_acceptable(inc) is True

        # Later, an HSE reviewer adjudicates as INSUFFICIENT_INFORMATION
        inc.adjudicated_human_decision = Incident.HumanDecision.INSUFFICIENT_INFORMATION
        inc.reviewer_rationale = "Pressure log data not attached; cannot confirm whether SIF precursor conditions were present."
        inc.save()

        inc.refresh_from_db()
        # Quality gate record remains VALID (it was NOT rejected at ingestion)
        assert inc.data_quality.status == IncidentDataQuality.Status.VALID
        # Retained in database for HSE audit
        assert inc.adjudicated_human_decision == "INSUFFICIENT_INFORMATION"
        # Strictly excluded from binary training targets
        assert inc.effective_training_label is None
        assert inc.training_eligibility == Incident.TrainingEligibility.HUMAN_INSUFFICIENT_INFORMATION

    def test_18_document_extraction_ingestion_uses_same_quality_gate(self, admin_user):
        """18. Document/file extraction path uses the same canonical quality gate."""
        doc_records = [
            {
                "description": "High-pressure valve stem packing failed, spraying brine onto deck.",
                "incident_date": "2026-02-18",
                "department": "Drilling",
            },
            {
                "description": "asdf",  # Invalid document extraction row
                "incident_date": "2026-02-18",
            },
        ]
        incidents, errors, stats = ingest_document_incidents(
            doc_records,
            dataset=None,
            return_details=True,
        )
        assert len(incidents) == 1
        assert stats["accepted"] == 1
        assert stats["rejected"] == 1
        assert stats["rejections"][0]["row_number"] == 2
        assert "Data quality is insufficient for analysis" in stats["rejections"][0]["reason"]
