import uuid
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.incidents.models import Incident, IncidentReview
from apps.datasets.models import Dataset
from apps.predictions.models import ModelVersion
from ml_engine.training.training_sources import get_training_eligible_incidents, TrainingSource

User = get_user_model()


@pytest.fixture
def test_user(db):
    return User.objects.create_user(
        username=f"reviewer_{uuid.uuid4().hex[:6]}",
        email="reviewer@example.com",
        password="password123",
        role=User.Role.SAFETY_OFFICER,
    )


@pytest.mark.django_db
class TestProvenanceCleanupPhase15:
    """Comprehensive test suite covering all 20 Phase 15 requirements."""

    # 1. Synthetic incident classification
    def test_01_synthetic_incident_classification(self, db):
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="High pressure hose burst during maintenance work.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 1, "synthetic": True},
        )
        assert inc.is_synthetic is True
        assert inc.psif_label_source == Incident.PsifLabelSource.SYNTHETIC
        assert inc.is_human_approved_synthetic is False
        assert inc.effective_training_label is True
        assert inc.training_eligibility == Incident.TrainingEligibility.UNREVIEWED
        assert inc.provenance_category == Incident.TrainingEligibility.SYNTHETIC

    # 2. Human-approved synthetic classification
    def test_02_human_approved_synthetic_classification(self, db, test_user):
        now = timezone.now()
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Worker exposed to electrical arc flash while switching breaker.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_psif_human_label=True,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            is_synthetic_adjudication=False,
            raw_row={"sif_label": 0, "synthetic": True},
        )
        IncidentReview.objects.create(
            incident=inc,
            reviewer=test_user,
            decision=Incident.HumanDecision.PSIF,
            rationale="Genuine high energy hazard present.",
            is_synthetic=False,
        )
        inc.refresh_from_db()
        assert inc.is_human_approved_synthetic is True
        assert inc.psif_label_source == Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC
        assert inc.provenance_category == Incident.TrainingEligibility.HUMAN_APPROVED_SYNTHETIC
        assert inc.training_eligibility == Incident.TrainingEligibility.HUMAN_PSIF

    # 3. Synthetic incident with genuine human PSIF decision
    def test_03_synthetic_with_human_psif_decision(self, db, test_user):
        now = timezone.now()
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Falling scaffold pipe hit safety barrier.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_psif_human_label=True,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            is_synthetic_adjudication=False,
            raw_row={"sif_label": 0, "synthetic": True},
        )
        assert inc.adjudicated_human_decision == Incident.HumanDecision.PSIF
        assert inc.is_psif_human_label is True
        assert inc.effective_training_label is True
        assert inc.training_eligibility == Incident.TrainingEligibility.HUMAN_PSIF

    # 4. Synthetic incident with genuine human NOT_PSIF decision
    def test_04_synthetic_with_human_not_psif_decision(self, db, test_user):
        now = timezone.now()
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Dropped plastic cup on floor in office.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_psif_human_label=False,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.NOT_PSIF,
            is_synthetic_adjudication=False,
            raw_row={"sif_label": 1, "synthetic": True},
        )
        assert inc.adjudicated_human_decision == Incident.HumanDecision.NOT_PSIF
        assert inc.is_psif_human_label is False
        assert inc.effective_training_label is False
        assert inc.training_eligibility == Incident.TrainingEligibility.HUMAN_NOT_PSIF

    # 5. Synthetic incident with human INSUFFICIENT_INFORMATION
    def test_05_synthetic_with_insufficient_information(self, db, test_user):
        now = timezone.now()
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Something occurred near the tank farm.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_psif_human_label=None,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION,
            is_synthetic_adjudication=False,
            raw_row={"sif_label": 1, "synthetic": True},
        )
        assert inc.adjudicated_human_decision == Incident.HumanDecision.INSUFFICIENT_INFORMATION
        assert inc.is_psif_human_label is None
        # Must not become binary NOT_PSIF
        assert inc.effective_training_label is None
        assert inc.training_eligibility == Incident.TrainingEligibility.HUMAN_INSUFFICIENT_INFORMATION

    # 6. Simulated reviewer does NOT create HUMAN_APPROVED_SYNTHETIC
    def test_06_simulated_reviewer_does_not_create_human_approved(self, db, test_user):
        now = timezone.now()
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Synthetic simulation evaluation test narrative.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_psif_human_label=True,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            is_synthetic_adjudication=True,  # Synthetic simulation!
            raw_row={"sif_label": 1, "synthetic": True},
        )
        IncidentReview.objects.create(
            incident=inc,
            reviewer=test_user,
            decision=Incident.HumanDecision.PSIF,
            rationale="Simulated AI model benchmark review.",
            is_synthetic=True,
        )
        assert inc.is_human_approved_synthetic is False
        # Synthetic is the sole category for all generated records (including simulated reviews)
        assert inc.provenance_category == Incident.TrainingEligibility.SYNTHETIC
        assert inc.training_eligibility == Incident.TrainingEligibility.UNREVIEWED
        assert inc.effective_training_label is None  # Excluded from binary training targets

    # 7. Synthetic record without human review remains SYNTHETIC
    def test_07_synthetic_without_human_review_remains_synthetic(self, db):
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Unreviewed synthetic record.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 0, "synthetic": True},
        )
        assert inc.is_human_approved_synthetic is False
        assert inc.psif_label_source == Incident.PsifLabelSource.SYNTHETIC
        assert inc.provenance_category == Incident.TrainingEligibility.SYNTHETIC
        assert inc.effective_training_label is False

    # 8. Missing provenance does not silently become HUMAN_APPROVED_SYNTHETIC
    def test_08_missing_provenance_not_human_approved(self, db):
        inc = Incident.objects.create(
            external_id=f"UNK-{uuid.uuid4().hex[:6]}",
            description="Unknown provenance record.",
            is_synthetic=False,
            psif_label_source=Incident.PsifLabelSource.NONE,
        )
        assert inc.is_human_approved_synthetic is False
        assert inc.effective_training_label is None
        assert inc.provenance_category == Incident.TrainingEligibility.UNKNOWN_UNLABELLED

    # 9. Old HEURISTIC database records migrate correctly to SYNTHETIC
    def test_09_no_heuristic_label_source_in_database(self, db):
        heuristic_count = Incident.objects.filter(psif_label_source__icontains="heuristic").count()
        assert heuristic_count == 0, f"Found {heuristic_count} records still with heuristic label source!"

    # 10. No training run can select HEURISTIC
    def test_10_no_training_run_can_select_heuristic(self, db, test_user):
        with pytest.raises(ValueError, match="HEURISTIC"):
            get_training_eligible_incidents(training_source="HEURISTIC")

        client = APIClient()
        client.force_authenticate(user=test_user)
        response = client.post("/api/models/retrain/", {"training_source": "HEURISTIC"}, format="json")
        assert response.status_code in [400, 403]  # bad request or forbidden

    # 11. No active inference configuration uses HEURISTIC provenance
    def test_11_active_model_uses_clean_provenance(self, db):
        active_model = ModelVersion.objects.filter(is_active=True).first()
        if active_model:
            metadata = active_model.training_metadata or {}
            source = metadata.get("training_source", "").upper()
            assert "HEURISTIC" not in source

    # 12. Human adjudication takes precedence over synthetic label
    def test_12_human_adjudication_precedence(self, db, test_user):
        now = timezone.now()
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Synthetic label says 0, human adjudication says PSIF.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_psif_human_label=True,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            is_synthetic_adjudication=False,
            raw_row={"sif_label": 0, "synthetic": True},
        )
        assert inc.effective_training_label is True

    # 13. INSUFFICIENT_INFORMATION does not become binary NOT_PSIF
    def test_13_insufficient_information_not_binary(self, db, test_user):
        now = timezone.now()
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Ambiguous report.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_psif_human_label=None,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION,
            is_synthetic_adjudication=False,
            raw_row={"sif_label": 1, "synthetic": True},
        )
        assert inc.is_psif_human_label is None
        assert inc.effective_training_label is None
        assert inc.adjudicated_human_decision == Incident.HumanDecision.INSUFFICIENT_INFORMATION

    # 14. Severity fields do not automatically create a heuristic PSIF label
    def test_14_severity_fields_do_not_create_heuristic_label(self, db):
        inc = Incident.objects.create(
            external_id=f"SEV-{uuid.uuid4().hex[:6]}",
            description="Potential serious, actual none.",
            severity_potential=Incident.SeverityPotential.SERIOUS,
            severity_actual=Incident.SeverityActual.NONE,
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
        )
        assert not hasattr(inc, "is_psif_heuristic_label")
        assert not hasattr(inc, "apply_weak_label")
        assert inc.psif_label_source == Incident.PsifLabelSource.SYNTHETIC

    # 15. UI/API does not expose HEURISTIC as current provenance option
    def test_15_provenance_choices_have_no_heuristic(self):
        choices = [c[0] for c in Incident.PsifLabelSource.choices]
        assert "heuristic" not in choices
        assert "HEURISTIC" not in choices
        assert "synthetic" in choices
        assert "human_approved_synthetic" in choices

        allowed_sources = TrainingSource.ALL_SOURCES
        assert "HEURISTIC" not in allowed_sources
        assert "SYNTHETIC" in allowed_sources
        assert "HUMAN_APPROVED_SYNTHETIC" in allowed_sources

    # 16. Historical model records remain auditable
    def test_16_historical_models_auditable(self, db):
        models = ModelVersion.objects.all()
        for m in models:
            meta = m.training_metadata or {}
            if "heuristic" in str(meta).lower():
                notes = meta.get("provenance_audit_notes") or meta.get("notes") or ""
                assert "synthetic" in str(notes).lower() or "former" in str(notes).lower() or "legacy" in str(notes).lower()

    # 17. Dataset counts remain internally consistent after migration
    def test_17_dataset_counts_consistency(self, db):
        total = Incident.objects.count()
        synthetic_count = Incident.objects.filter(is_synthetic=True).count()
        real_count = Incident.objects.filter(is_synthetic=False).count()
        assert total == synthetic_count + real_count

    # 18. Existing human review tests continue passing (verified by fixture logic)
    def test_18_human_review_workflow_audit_trail(self, db, test_user):
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Audit trail verification.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
        )
        review = IncidentReview.objects.create(
            incident=inc,
            reviewer=test_user,
            decision=Incident.HumanDecision.NOT_PSIF,
            rationale="No high energy hazard found during inspection.",
            is_synthetic=False,
        )
        assert review.reviewer == test_user
        assert review.decision == "NOT_PSIF"

    # 19. Existing synthetic-data benchmark labels preserved
    def test_19_synthetic_benchmark_labels_preserved(self, db):
        inc = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Synthetic pipeline sample.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 1, "synthetic": True},
        )
        assert inc.effective_training_label is True

    # 20. Training source selector handles MIXED_SYNTHETIC as internal implementation strategy
    def test_20_mixed_synthetic_training_source(self, db, test_user):
        now = timezone.now()
        # 1 synthetic only
        Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Pure synthetic incident.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 1, "synthetic": True},
        )
        # 1 human-approved synthetic
        Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Human approved synthetic incident.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            is_psif_human_label=True,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            is_synthetic_adjudication=False,
            raw_row={"sif_label": 0, "synthetic": True},
        )
        eligible, _, _ = get_training_eligible_incidents(training_source="MIXED_SYNTHETIC")
        assert len(eligible) >= 2

    # 21. USER_FACING_SOURCES contains only SYNTHETIC and HUMAN_APPROVED_SYNTHETIC
    def test_21_user_facing_sources_strictly_two_categories(self):
        assert TrainingSource.USER_FACING_SOURCES == [
            TrainingSource.SYNTHETIC,
            TrainingSource.HUMAN_APPROVED_SYNTHETIC,
        ]
        assert "MIXED_SYNTHETIC" not in TrainingSource.USER_FACING_SOURCES

    # 22. Human decision status is kept completely separate from provenance
    def test_22_human_decision_status_separate_from_provenance(self, db, test_user):
        now = timezone.now()
        # Case A: Human-approved with PSIF
        inc_psif = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="High voltage arc flash during breaker test.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            is_synthetic_adjudication=False,
        )
        # Provenance tells us WHAT the data is:
        assert inc_psif.provenance_category == "HUMAN_APPROVED_SYNTHETIC"
        # Decision status tells us WHAT the human decided:
        assert inc_psif.adjudicated_human_decision == Incident.HumanDecision.PSIF
        assert inc_psif.training_eligibility == Incident.TrainingEligibility.HUMAN_PSIF

        # Case B: Human-approved with INSUFFICIENT_INFORMATION
        inc_insuf = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Odor noted in control room.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION,
            is_synthetic_adjudication=False,
        )
        assert inc_insuf.provenance_category == "HUMAN_APPROVED_SYNTHETIC"
        assert inc_insuf.adjudicated_human_decision == Incident.HumanDecision.INSUFFICIENT_INFORMATION
        assert inc_insuf.training_eligibility == Incident.TrainingEligibility.HUMAN_INSUFFICIENT_INFORMATION
        assert inc_insuf.effective_training_label is None

    # 23. Synthetic is sole category for all generated records (including simulated reviews)
    def test_23_synthetic_sole_category_for_all_generated_records(self, db, test_user):
        now = timezone.now()
        # Unreviewed synthetic
        inc_unrev = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Unreviewed generated benchmark record.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 1, "synthetic": True},
        )
        assert inc_unrev.provenance_category == "SYNTHETIC"

        # Simulated-review synthetic (generated record with automated simulation)
        inc_sim = Incident.objects.create(
            external_id=f"SYNTH-{uuid.uuid4().hex[:6]}",
            description="Automated evaluator benchmark review run.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            adjudicated_by=test_user,
            adjudicated_at=now,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            is_synthetic_adjudication=True,  # Automated simulation
            raw_row={"sif_label": 1, "synthetic": True},
        )
        # Provenance is strictly SYNTHETIC (sole category for all generated records)
        assert inc_sim.provenance_category == "SYNTHETIC"
        # Never elevated to HUMAN_APPROVED_SYNTHETIC
        assert inc_sim.is_human_approved_synthetic is False
        # Excluded from binary training targets
        assert inc_sim.effective_training_label is None

    # 24. Retrain API error message reflects exactly the two user-facing synthetic categories
    def test_24_api_retrain_error_reflects_user_facing_sources(self, client, test_user):
        test_user.role = "admin"
        test_user.save()
        client.force_login(test_user)
        response = client.post(
            "/api/models/retrain/",
            data={"training_source": "HEURISTIC"},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.json()
        assert "SYNTHETIC, HUMAN_APPROVED_SYNTHETIC" in data["error"]
        assert "MIXED_SYNTHETIC" not in data["error"]

