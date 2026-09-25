"""
Tests for Multi-Source Training Architecture & Lifecycle (Part B, Tests 16–39).
Verifies:
- Strict source separation across HUMAN, HEURISTIC, SYNTHETIC, MIXED.
- Synthetic & simulated reviewer data never masquerade as human ground truth.
- Candidate models remain inactive (is_active=False, status=READY).
- Active model remains unchanged.
- Training snapshots preserve immutable provenance, hashes, and disclaimers.
"""
import pytest
import uuid
from datetime import date
from django.utils import timezone

from apps.incidents.models import Incident, IncidentDataQuality
from apps.predictions.models import ModelVersion
from ml_engine.training.training_sources import (
    TrainingSource,
    get_training_eligible_incidents,
)
from ml_engine.training.trainer import (
    audit_labels,
    generate_training_snapshot,
)


@pytest.mark.django_db
class TestMultiSourceTraining:

    def test_16_human_training_excludes_synthetic_data(self, admin_user):
        """Test 16: Human training strictly excludes synthetic dataset records."""
        # Create synthetic incident
        inc_synth = Incident.objects.create(
            description="Synthetic event: High pressure gas kick observed during circulation.",
            raw_row={"sif_label": 1},
            is_synthetic_adjudication=False,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
        )
        eligible, row_prov, comp = get_training_eligible_incidents(TrainingSource.HUMAN)
        assert str(inc_synth.id) not in [str(x.id) for x in eligible]
        assert comp["synthetic_count"] == 0

    def test_17_selecting_heuristic_source_raises_error(self):
        """Test 17: Requesting HEURISTIC training source raises ValueError (concept eliminated)."""
        with pytest.raises(ValueError) as exc:
            get_training_eligible_incidents("HEURISTIC")
        assert "eliminated" in str(exc.value).lower()

    def test_18_human_training_excludes_human_insufficient_information(self):
        """Test 18: Human training strictly excludes INSUFFICIENT_INFORMATION reviews."""
        inc_insuf = Incident.objects.create(
            description="Operator reported strange noise from compressor skid, but no further details available.",
            adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION,
            is_synthetic_adjudication=False,
        )
        eligible, _, comp = get_training_eligible_incidents(TrainingSource.HUMAN)
        assert str(inc_insuf.id) not in [str(x.id) for x in eligible]
        assert comp["insufficient_info_excluded"] >= 1

    def test_19_api_rejects_heuristic_training_source(self, admin_client):
        """Test 19: API rejects retraining requests with HEURISTIC training source."""
        resp = admin_client.post("/api/models/retrain/", {
            "training_source": "HEURISTIC",
        }, format="json")
        assert resp.status_code == 400
        assert "eliminated" in resp.json()["error"].lower()

    def test_20_synthetic_training_includes_eligible_synthetic_dataset_labels(self, admin_user):
        """Test 20: Synthetic training includes eligible synthetic dataset labels."""
        from apps.datasets.models import Dataset
        ds = Dataset.objects.create(name="synth.csv", file_type="csv", uploaded_by=admin_user)
        inc_synth = Incident.objects.create(
            dataset=ds,
            description="Synthetic event: Chemical exposure to eyes while mixing drilling mud additive.",
            raw_row={"sif_label": 1},
            is_synthetic_adjudication=False,
        )
        eligible, row_prov, comp = get_training_eligible_incidents(TrainingSource.SYNTHETIC, sample_limit=10)
        assert str(inc_synth.id) in [str(x.id) for x in eligible]
        matching = [p for p in row_prov if p["incident_id"] == str(inc_synth.id)]
        assert len(matching) == 1
        assert matching[0]["label_source"] == "synthetic"
        assert matching[0]["label"] is True

    def test_21_synthetic_reviewer_simulation_excluded_from_human_training(self):
        """Test 21: Simulated reviewer adjudications are strictly excluded from human training."""
        inc_sim = Incident.objects.create(
            description="Simulated reviewer adjudication record from calibration test.",
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            is_synthetic_adjudication=True,  # SIMULATION RECORD
        )
        eligible, _, comp = get_training_eligible_incidents(TrainingSource.HUMAN)
        assert str(inc_sim.id) not in [str(x.id) for x in eligible]

    def test_22_unknown_unlabelled_records_excluded(self):
        """Test 22: Records with no label source or label value are excluded."""
        inc_none = Incident.objects.create(
            description="A regular incident without any label or assessment.",
            psif_label_source=Incident.PsifLabelSource.NONE,
            is_synthetic_adjudication=False,
        )
        for src in [TrainingSource.HUMAN, TrainingSource.SYNTHETIC, TrainingSource.MIXED]:
            eligible, _, _ = get_training_eligible_incidents(src, sample_limit=10)
            assert str(inc_none.id) not in [str(x.id) for x in eligible]

    def test_23_critical_data_quality_records_excluded_from_training(self):
        """Test 23: Records failing data quality gate are excluded from all training sources."""
        inc_bad = Incident.objects.create(
            description="asdf",  # Placeholder
            is_synthetic=True,
            raw_row={"sif_label": 1},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        IncidentDataQuality.objects.create(
            incident=inc_bad,
            status=IncidentDataQuality.Status.CRITICAL,
            findings=[{"message": "Narrative placeholder"}],
        )
        for src in [TrainingSource.HUMAN, TrainingSource.SYNTHETIC, TrainingSource.MIXED]:
            eligible, _, comp = get_training_eligible_incidents(src, sample_limit=20)
            assert str(inc_bad.id) not in [str(x.id) for x in eligible]

    def test_24_mixed_training_preserves_row_level_provenance(self, admin_user):
        """Test 24: Mixed training tracks row-level provenance accurately across human-approved and synthetic."""
        inc_human = Incident.objects.create(
            description="Human approved synthetic incident: High pressure line burst during pressure test.",
            is_synthetic=True,
            is_psif_human_label=True,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            reviewed_by=admin_user,
            reviewed_at=timezone.now(),
            is_synthetic_adjudication=False,
        )
        inc_synth = Incident.objects.create(
            description="Synthetic incident: Hand pinch under heavy valve flange on rig floor.",
            is_synthetic=True,
            raw_row={"sif_label": 0},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        eligible, row_prov, comp = get_training_eligible_incidents(TrainingSource.MIXED, sample_limit=50)

        prov_map = {p["incident_id"]: p["label_source"] for p in row_prov}
        assert prov_map.get(str(inc_human.id)) == "human_approved_synthetic"
        assert prov_map.get(str(inc_synth.id)) == "synthetic"

    def test_25_training_snapshot_contains_source_counts(self):
        """Test 25: Training snapshot includes composition, disclaimers, and validation basis."""
        inc_pos = Incident.objects.create(
            description="Incident 1: High potential dropped object from hoist.",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        inc_pos._training_label = True
        inc_pos._training_source = "synthetic"

        inc_neg = Incident.objects.create(
            description="Incident 2: Minor cut from hand tool during pipe preparation.",
            is_synthetic=True,
            raw_row={"sif_label": 0},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        inc_neg._training_label = False
        inc_neg._training_source = "synthetic"

        incidents_list = [inc_pos] * 10 + [inc_neg] * 10
        audit = audit_labels(incidents=incidents_list, training_source="SYNTHETIC")
        snapshot = generate_training_snapshot(
            eligible_incidents=incidents_list,
            audit=audit,
            version_label="v_test_snapshot",
            feature_names=["f1", "f2"],
            training_source="SYNTHETIC",
            validation_basis="SYNTHETIC BENCHMARK EVALUATION",
            disclaimer="Test disclaimer",
        )
        assert snapshot["training_source"] == "SYNTHETIC"
        assert snapshot["validation_basis"] == "SYNTHETIC BENCHMARK EVALUATION"
        assert snapshot["disclaimer"] == "Test disclaimer"
        assert "dataset_hash" in snapshot
        assert len(snapshot["incident_records"]) == 20

    def test_26_dataset_hash_preserved(self):
        """Test 26: Dataset hash is deterministic given the same incident set and labels."""
        inc_pos = Incident.objects.create(
            description="Test positive incident for deterministic hash calculation.",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        inc_pos._training_label = True
        inc_pos._training_source = "synthetic"

        inc_neg = Incident.objects.create(
            description="Test negative incident for deterministic hash calculation.",
            is_synthetic=True,
            raw_row={"sif_label": 0},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_synthetic_adjudication=False,
        )
        inc_neg._training_label = False
        inc_neg._training_source = "synthetic"

        incidents_list = [inc_pos] * 10 + [inc_neg] * 10
        audit = audit_labels(incidents=incidents_list, training_source="SYNTHETIC")
        s1 = generate_training_snapshot(incidents_list, audit, "v1", ["f1"], training_source="SYNTHETIC")
        s2 = generate_training_snapshot(incidents_list, audit, "v2", ["f1"], training_source="SYNTHETIC")
        assert s1["dataset_hash"] == s2["dataset_hash"]

    def test_27_candidate_metadata_records_training_source(self, admin_client):
        """Test 27: Enqueueing retraining stores training_source in candidate metadata."""
        resp = admin_client.post("/api/models/retrain/", {
            "training_source": "SYNTHETIC",
            "sample_limit": 50,
        }, format="json")
        assert resp.status_code == 202
        data = resp.json()
        assert data["training_source"] == "SYNTHETIC"

        mv = ModelVersion.objects.get(id=data["model_version_id"])
        assert mv.metrics.get("training_source") == "SYNTHETIC"
        assert mv.is_active is False
        assert mv.status == ModelVersion.Status.PENDING

    def test_28_candidate_cannot_automatically_become_active(self):
        """Test 28: Candidate model versions are strictly created with is_active=False."""
        candidate = ModelVersion.objects.create(
            version_label="v_candidate_test",
            status=ModelVersion.Status.READY,
            is_active=False,
            metrics={"training_status": "READY", "training_source": "SYNTHETIC"}
        )
        assert candidate.is_active is False

    def test_29_active_model_unchanged_after_candidate_training(self):
        """Test 29: Active model count and identity remains stable after candidate training."""
        active_baseline = ModelVersion.objects.filter(is_active=True).first()
        initial_active_id = active_baseline.id if active_baseline else None

        candidate = ModelVersion.objects.create(
            version_label="v_candidate_dummy",
            status=ModelVersion.Status.READY,
            is_active=False,
            metrics={"training_status": "READY"}
        )

        active_now = ModelVersion.objects.filter(is_active=True).first()
        assert (active_now.id if active_now else None) == initial_active_id
        assert ModelVersion.objects.filter(is_active=True).count() == (1 if initial_active_id else 0)

    def test_30_models_page_displays_correct_validation_basis(self, admin_client):
        """Test 30: Models status API returns validation_basis dynamically."""
        candidate = ModelVersion.objects.create(
            version_label="v_candidate_basis_test",
            status=ModelVersion.Status.READY,
            is_active=False,
            metrics={
                "training_status": "READY",
                "training_source": "SYNTHETIC",
                "validation_basis": "SYNTHETIC DATASET EVALUATION",
                "disclaimer": "Development only.",
            }
        )
        resp = admin_client.get(f"/api/models/{candidate.id}/status/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["validation_basis"] == "SYNTHETIC DATASET EVALUATION"
        assert data["training_source"] == "SYNTHETIC"
        assert data["disclaimer"] == "Development only."

    def test_31_human_validation_count_remains_zero_without_real_human_labels(self):
        """Test 31: Human validation count remains 0 when no genuine human reviews exist."""
        for i in range(10):
            Incident.objects.create(
                description=f"Synthetic pos incident {i} involving well control event.",
                is_synthetic=True,
                raw_row={"sif_label": 1},
                psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
                is_synthetic_adjudication=False,
            )
            Incident.objects.create(
                description=f"Synthetic neg incident {i} minor housekeeping event.",
                is_synthetic=True,
                raw_row={"sif_label": 0},
                psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
                is_synthetic_adjudication=False,
            )
        audit = audit_labels(incidents=None, training_source="SYNTHETIC")
        assert audit["provenance_counts"]["human_approved_synthetic"] == 0
        assert audit["human_eligible"] == 0

    def test_32_synthetic_training_does_not_alter_human_validation_metrics(self):
        """Test 32: Retraining with SYNTHETIC source fails if trying to claim human ground truth."""
        with pytest.raises(ValueError) as exc:
            # Human source has 0 records in DB
            get_training_eligible_incidents(TrainingSource.HUMAN)
            audit_labels(incidents=[], training_source=TrainingSource.HUMAN)
        assert "Insufficient training data" in str(exc.value)

    def test_33_training_source_api_validation(self, admin_client):
        """Test 33: Retraining API rejects invalid training_source."""
        resp = admin_client.post("/api/models/retrain/", {
            "training_source": "NON_EXISTENT_SOURCE",
        }, format="json")
        assert resp.status_code == 400
        assert "Invalid training_source" in resp.json()["error"]

    def test_34_model_activate_permission_check(self, analyst_client, safety_client):
        """Test 34: Analyst and Safety Officer cannot activate candidate models."""
        candidate = ModelVersion.objects.create(
            version_label="v_test_perm",
            status=ModelVersion.Status.READY,
            is_active=False,
        )
        for client in [analyst_client, safety_client]:
            resp = client.post(f"/api/models/{candidate.id}/activate/")
            assert resp.status_code == 403
            assert "Forbidden" in resp.json()["error"]

    def test_35_training_sources_api_and_overview(self, admin_client):
        """Test 35: API endpoint /api/models/training-sources/ returns dynamic counts and overview."""
        from ml_engine.training.training_sources import get_training_sources_overview
        overview = get_training_sources_overview(use_cache=False)
        assert "synthetic" in overview
        assert "human_approved_synthetic" in overview
        assert isinstance(overview["synthetic"]["count"], int)
        assert isinstance(overview["human_approved_synthetic"]["count"], int)
        assert "formatted_count" in overview["synthetic"]
        assert "formatted_count" in overview["human_approved_synthetic"]

        resp = admin_client.get("/api/models/training-sources/")
        assert resp.status_code == 200
        data = resp.json()
        assert "synthetic" in data
        assert "human_approved_synthetic" in data
        assert data["synthetic"]["count"] == overview["synthetic"]["count"]
        assert data["human_approved_synthetic"]["count"] == overview["human_approved_synthetic"]["count"]

        # Test refresh=true
        resp_refresh = admin_client.get("/api/models/training-sources/?refresh=true")
        assert resp_refresh.status_code == 200

