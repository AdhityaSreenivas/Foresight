import uuid
from datetime import date
import numpy as np
from unittest.mock import patch

from django.test import TestCase
from apps.incidents.models import Incident, IncidentEmbedding, IncidentDataQuality
from apps.incidents.services.decision_trace import build_analytical_assessment, find_related_incidents
from apps.incidents.services.embedding import generate_and_persist_embeddings
from apps.datasets.tasks import generate_incident_embeddings_task


class BatchEmbeddingAvailabilityTests(TestCase):
    """
    Validation suite for P2-2 Batch Embedding Availability (Spec §37–§41).
    Covers:
      A. Batch-imported incident receives an embedding.
      B. Similarity can retrieve it.
      C. Retry does not duplicate embedding (idempotence).
      D. Embedding readiness state (NOT_READY) and failure visibility.
      E. Existing manually generated embeddings remain valid.
    """

    def setUp(self):
        self.incident_a = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 1),
            department="Drilling",
            job_task="Tripping pipe",
            description="Drill pipe slipped during tripping operation near rotary table on drilling rig floor.",
            composite_narrative="Drill pipe slipped during tripping operation near rotary table on drilling rig floor.",
            status="investigation"
        )
        self.incident_b = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 2),
            department="Drilling",
            job_task="Tripping pipe",
            description="Drill pipe slipped during tripping operation near rotary table on drilling rig floor.",
            composite_narrative="Drill pipe slipped during tripping operation near rotary table on drilling rig floor.",
            status="investigation"
        )

    def test_a_batch_incident_receives_embedding(self):
        """A: New batch-imported incident receives an embedding via the task."""
        self.assertFalse(hasattr(self.incident_a, "embedding") and self.incident_a.embedding is not None)

        # Execute embedding task
        res = generate_incident_embeddings_task([str(self.incident_a.id)])
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["created_count"], 1)

        self.incident_a.refresh_from_db()
        self.assertTrue(hasattr(self.incident_a, "embedding"))
        self.assertIsNotNone(self.incident_a.embedding)
        self.assertEqual(len(self.incident_a.embedding.vector), 768)
        self.assertEqual(self.incident_a.embedding.embedding_model, "distilbert-base-uncased")
        self.assertEqual(self.incident_a.embedding.embedding_version, "v1")

    def test_b_similarity_can_retrieve_batch_embedding(self):
        """B: Semantic similarity correctly retrieves batch-embedded incidents."""
        # Generate embeddings for both incidents
        generate_incident_embeddings_task([str(self.incident_a.id), str(self.incident_b.id)])

        self.incident_a.refresh_from_db()
        self.incident_b.refresh_from_db()

        # Target incident A should retrieve incident B as similar
        related = find_related_incidents(self.incident_a, min_similarity=0.7)
        self.assertTrue(len(related) > 0)
        self.assertEqual(related[0]["incident_id"], str(self.incident_b.id))
        self.assertIn("similarity_score", related[0])

        # Analytical assessment should mark similarity AVAILABLE
        assessment = build_analytical_assessment(self.incident_a)
        self.assertEqual(assessment["similarity"]["status"], "AVAILABLE")
        self.assertTrue(len(assessment["similarity"]["items"]) > 0)

    def test_c_retry_does_not_duplicate_embedding(self):
        """C: Retrying embedding generation is strictly idempotent and does not duplicate records."""
        # First execution
        res1 = generate_incident_embeddings_task([str(self.incident_a.id)])
        self.assertEqual(res1["created_count"], 1)
        self.assertEqual(IncidentEmbedding.objects.filter(incident=self.incident_a).count(), 1)

        original_embedding = IncidentEmbedding.objects.get(incident=self.incident_a)
        original_created_at = original_embedding.created_at

        # Second execution (retry / re-queue)
        res2 = generate_incident_embeddings_task([str(self.incident_a.id)])
        self.assertEqual(res2["created_count"], 0)
        self.assertEqual(IncidentEmbedding.objects.filter(incident=self.incident_a).count(), 1)

        current_embedding = IncidentEmbedding.objects.get(incident=self.incident_a)
        self.assertEqual(current_embedding.id, original_embedding.id)
        self.assertEqual(current_embedding.created_at, original_created_at)

    def test_d_embedding_not_ready_and_failure_visibility(self):
        """D: Not-yet-embedded incidents report NOT_READY rather than silent empty results, and task failures are visible."""
        # Incident A has no embedding yet
        self.assertEqual(IncidentEmbedding.objects.filter(incident=self.incident_a).count(), 0)

        assessment = build_analytical_assessment(self.incident_a)
        # Spec §40: Do not silently produce [] when real state is embedding not generated yet
        self.assertEqual(assessment["similarity"]["status"], "NOT_READY")
        self.assertIn("Embedding not generated yet", assessment["similarity"]["reason"])
        self.assertEqual(len(assessment["similarity"]["items"]), 0)

        # Test failure visibility when encode_texts raises an exception
        with patch("apps.incidents.services.embedding.encode_texts", side_effect=RuntimeError("GPU OOM")):
            with self.assertRaises(Exception):
                # When run without Celery worker retry context, the exception bubbles up visibly
                generate_and_persist_embeddings([self.incident_a])

    def test_e_existing_manually_generated_embeddings_remain_valid(self):
        """E: Manually created embeddings remain valid and are not overwritten by automated batch tasks."""
        manual_vector = np.random.rand(768).tolist()
        manual_embedding = IncidentEmbedding.objects.create(
            incident=self.incident_a,
            vector=manual_vector,
            embedding_model="distilbert-base-uncased",
            embedding_version="v1"
        )

        # Run task on incident_a
        res = generate_incident_embeddings_task([str(self.incident_a.id)])
        self.assertEqual(res["created_count"], 0)

        # Verify manual vector remains untouched
        self.incident_a.refresh_from_db()
        self.assertEqual(self.incident_a.embedding.id, manual_embedding.id)
        self.assertEqual(self.incident_a.embedding.vector, manual_vector)


class BulkIngestionSchemaCompatibilityTests(TestCase):
    """
    Regression test suite for reviewer_rationale nullable schema contract
    and unreviewed newly imported incidents.
    """

    def setUp(self):
        from apps.datasets.models import Dataset
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(username="hse_reviewer", password="password123")
        self.dataset = Dataset.objects.create(
            name="test_schema_compat.jsonl",
            file_type="jsonl",
            status="uploaded",
        )

    def test_bulk_create_unreviewed_incident_succeeds_with_null_rationale(self):
        """
        Representative imported incident with no human review fields succeeds in bulk_create.
        Asserts human review fields are NULL/None and status is PENDING.
        """
        from apps.datasets.ingestion import bulk_create_incidents

        rows = [
            {
                "report_id": "RV3_000001",
                "report_type": "Safety Observation",
                "site_area": "Maintenance Shop",
                "report_text": "Technician setting up work. Unexpected start risk.",
                "activity": "Mechanical Maintenance",
                "potential_consequence": "serious",
                "severity_actual": "none",
            }
        ]
        column_mapping = {
            "report_id": "external_id",
            "site_area": "location",
            "report_text": "description",
            "activity": "job_task",
            "potential_consequence": "severity_potential",
            "severity_actual": "severity_actual",
        }

        created_incidents, errors = bulk_create_incidents(rows, self.dataset, column_mapping)
        self.assertEqual(errors, 0)
        self.assertEqual(len(created_incidents), 1)

        inc = Incident.objects.get(id=created_incidents[0].id)
        # Contract checks:
        self.assertIsNone(inc.reviewer_rationale)
        self.assertIsNone(inc.reviewed_by)
        self.assertIsNone(inc.reviewed_at)
        self.assertIsNone(inc.is_psif_human_label)
        self.assertEqual(inc.status, Incident.Status.PENDING)
        # Provenance checks:
        self.assertTrue(inc.is_synthetic)
        self.assertEqual(inc.psif_label_source, Incident.PsifLabelSource.SYNTHETIC)

    def test_explicit_none_reviewer_rationale_in_bulk_create_does_not_violate_constraint(self):
        """
        Directly passes reviewer_rationale=None into bulk_create to verify PostgreSQL
        NOT NULL constraint was successfully dropped.
        """
        inc = Incident(
            dataset=self.dataset,
            external_id="EXPLICIT_NONE_01",
            description="Testing explicit None reviewer_rationale",
            reviewer_rationale=None,
            reviewed_by=None,
            reviewed_at=None,
            is_psif_human_label=None,
        )
        Incident.objects.bulk_create([inc])

        persisted = Incident.objects.get(external_id="EXPLICIT_NONE_01")
        self.assertIsNone(persisted.reviewer_rationale)
        self.assertIsNone(persisted.reviewed_by)
        self.assertIsNone(persisted.reviewed_at)
        self.assertIsNone(persisted.is_psif_human_label)

    def test_subsequent_human_review_preserves_rationale_and_precedence(self):
        """
        An unreviewed synthetic incident can subsequently be reviewed by an HSE expert,
        storing rationale, reviewer identity, timestamp, and human-approved synthetic label.
        """
        from django.utils import timezone
        inc = Incident.objects.create(
            dataset=self.dataset,
            external_id="TO_BE_REVIEWED",
            description="Work near high voltage line.",
            is_synthetic=True,
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            raw_row={"sif_label": 1},
            reviewer_rationale=None,
        )
        self.assertIsNone(inc.reviewer_rationale)
        self.assertIsNone(inc.is_psif_human_label)

        # Reviewer submits decision
        now = timezone.now()
        inc.is_psif_human_label = False
        inc.psif_label_source = Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC
        inc.reviewer_rationale = "Line was verified de-energized, locked, and tagged. No hazard present."
        inc.reviewed_by = self.user
        inc.reviewed_at = now
        inc.status = Incident.Status.REVIEWED_NON_PSIF
        inc.save()

        refreshed = Incident.objects.get(id=inc.id)
        self.assertEqual(refreshed.reviewer_rationale, "Line was verified de-energized, locked, and tagged. No hazard present.")
        self.assertEqual(refreshed.reviewed_by, self.user)
        self.assertFalse(refreshed.is_psif_human_label)
        self.assertEqual(refreshed.psif_label_source, Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC)
        self.assertEqual(refreshed.effective_training_label, False)
        self.assertTrue(refreshed.is_human_approved_synthetic)


class DatasetCancellationTests(TestCase):
    """
    Tests for canceling / discarding dataset uploads safely without disturbing
    existing data or ongoing uploads.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.datasets.models import Dataset
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIClient

        User = get_user_model()
        self.client = APIClient()
        self.safety_officer = User.objects.create_user(
            username="safety_officer_cancel",
            password="password123",
            role=User.Role.SAFETY_OFFICER,
        )
        self.viewer = User.objects.create_user(
            username="viewer_cancel",
            password="password123",
            role=User.Role.VIEWER,
        )

        test_file = SimpleUploadedFile("test_cancel.csv", b"col1,col2\nval1,val2\n", content_type="text/csv")
        self.pending_dataset = Dataset.objects.create(
            name="test_cancel.csv",
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
            uploaded_by=self.safety_officer,
            original_file=test_file,
        )

    def test_cancel_mapping_pending_dataset_success(self):
        """User can cancel and discard a dataset awaiting mapping."""
        self.client.force_authenticate(user=self.safety_officer)

        res = self.client.delete(f"/api/datasets/{self.pending_dataset.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "deleted")

        from apps.datasets.models import Dataset
        self.assertFalse(Dataset.objects.filter(id=self.pending_dataset.id).exists())

    def test_cannot_cancel_actively_processing_dataset(self):
        """Ongoing uploads (processing or retrying) cannot be cancelled or deleted."""
        from apps.datasets.models import Dataset
        self.pending_dataset.status = Dataset.Status.PROCESSING
        self.pending_dataset.save()

        self.client.force_authenticate(user=self.safety_officer)
        res = self.client.delete(f"/api/datasets/{self.pending_dataset.id}/")
        self.assertEqual(res.status_code, 409)
        self.assertIn("processing or retrying", res.data["detail"])
        self.assertTrue(Dataset.objects.filter(id=self.pending_dataset.id).exists())

    def test_cannot_cancel_retrying_dataset(self):
        """Retrying datasets return 409 and are protected from deletion."""
        from apps.datasets.models import Dataset
        self.pending_dataset.status = Dataset.Status.RETRYING
        self.pending_dataset.save()

        self.client.force_authenticate(user=self.safety_officer)
        res = self.client.delete(f"/api/datasets/{self.pending_dataset.id}/")
        self.assertEqual(res.status_code, 409)
        self.assertIn("processing or retrying", res.data["detail"])
        self.assertTrue(Dataset.objects.filter(id=self.pending_dataset.id).exists())

    def test_cannot_cancel_completed_dataset_with_or_without_incidents(self):
        """Completed operational datasets cannot be discarded."""
        from apps.datasets.models import Dataset
        self.pending_dataset.status = Dataset.Status.COMPLETED
        self.pending_dataset.save()

        self.client.force_authenticate(user=self.safety_officer)
        res = self.client.delete(f"/api/datasets/{self.pending_dataset.id}/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Historical operational datasets", res.data["detail"])
        self.assertTrue(Dataset.objects.filter(id=self.pending_dataset.id).exists())

    def test_cannot_cancel_dataset_with_incidents(self):
        """Any dataset that has created incident records is protected from deletion."""
        from apps.datasets.models import Dataset
        from apps.incidents.models import Incident
        import uuid
        from datetime import date

        Incident.objects.create(
            id=uuid.uuid4(),
            dataset=self.pending_dataset,
            incident_date=date(2026, 9, 1),
            description="Existing incident record",
            composite_narrative="Existing incident record",
        )

        self.client.force_authenticate(user=self.safety_officer)
        res = self.client.delete(f"/api/datasets/{self.pending_dataset.id}/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("existing incident records", res.data["detail"])
        self.assertTrue(Dataset.objects.filter(id=self.pending_dataset.id).exists())
        self.assertEqual(self.pending_dataset.incidents.count(), 1)

    def test_cancel_uploaded_and_failed_datasets_succeed(self):
        """Datasets in 'uploaded' and 'failed' states (0 incidents) can be discarded."""
        from apps.datasets.models import Dataset

        self.pending_dataset.status = Dataset.Status.UPLOADED
        self.pending_dataset.save()
        self.client.force_authenticate(user=self.safety_officer)
        res = self.client.delete(f"/api/datasets/{self.pending_dataset.id}/")
        self.assertEqual(res.status_code, 200)

        # Create failed dataset with 0 incidents
        from django.core.files.uploadedfile import SimpleUploadedFile
        f2 = SimpleUploadedFile("fail.csv", b"a,b\n1,2\n", content_type="text/csv")
        failed_ds = Dataset.objects.create(
            name="fail.csv",
            file_type="csv",
            status=Dataset.Status.FAILED,
            uploaded_by=self.safety_officer,
            original_file=f2,
        )
        res2 = self.client.delete(f"/api/datasets/{failed_ds.id}/")
        self.assertEqual(res2.status_code, 200)
        self.assertFalse(Dataset.objects.filter(id=failed_ds.id).exists())

    def test_unauthorized_viewer_cannot_cancel(self):
        """Viewer without can_upload permission cannot cancel datasets."""
        self.client.force_authenticate(user=self.viewer)
        res = self.client.delete(f"/api/datasets/{self.pending_dataset.id}/")
        self.assertEqual(res.status_code, 403)

    def test_list_view_renders_discard_only_for_safe_states(self):
        """List view renders Discard for mapping_pending/uploaded/failed, not processing/retrying/completed."""
        from django.test import Client
        from apps.datasets.models import Dataset
        from django.core.files.uploadedfile import SimpleUploadedFile

        c = Client()
        c.force_login(self.safety_officer)

        # 1. mapping_pending
        self.pending_dataset.status = Dataset.Status.MAPPING_PENDING
        self.pending_dataset.save()
        res = c.get("/datasets/")
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn(f'data-id="{self.pending_dataset.id}"', content)
        self.assertIn("btn-discard-dataset", content)

        # 2. processing
        self.pending_dataset.status = Dataset.Status.PROCESSING
        self.pending_dataset.save()
        res = c.get("/datasets/")
        content = res.content.decode("utf-8")
        self.assertNotIn(f'data-id="{self.pending_dataset.id}"', content)

        # 3. retrying
        self.pending_dataset.status = Dataset.Status.RETRYING
        self.pending_dataset.save()
        res = c.get("/datasets/")
        content = res.content.decode("utf-8")
        self.assertNotIn(f'data-id="{self.pending_dataset.id}"', content)

        # 4. completed
        self.pending_dataset.status = Dataset.Status.COMPLETED
        self.pending_dataset.save()
        res = c.get("/datasets/")
        content = res.content.decode("utf-8")
        self.assertNotIn(f'data-id="{self.pending_dataset.id}"', content)

        # 5. uploaded
        self.pending_dataset.status = Dataset.Status.UPLOADED
        self.pending_dataset.save()
        res = c.get("/datasets/")
        content = res.content.decode("utf-8")
        self.assertIn(f'data-id="{self.pending_dataset.id}"', content)

        # 6. failed
        self.pending_dataset.status = Dataset.Status.FAILED
        self.pending_dataset.save()
        res = c.get("/datasets/")
        content = res.content.decode("utf-8")
        self.assertIn(f'data-id="{self.pending_dataset.id}"', content)

    def test_upload_view_contains_cancel_controls(self):
        """Upload template contains Cancel Upload and Cancel & Discard buttons."""
        from django.test import Client
        c = Client()
        c.force_login(self.safety_officer)
        res = c.get("/datasets/upload/")
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("Cancel Upload", content)
        self.assertIn("Cancel &amp; Discard", content)
        self.assertIn("btn-cancel-mapping", content)
        self.assertIn("btn-save-mapping", content)

    def test_preview_endpoint_supports_resume(self):
        """GET /api/datasets/<id>/preview/ returns preview data for resuming."""
        self.client.force_authenticate(user=self.safety_officer)
        res = self.client.get(f"/api/datasets/{self.pending_dataset.id}/preview/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["dataset_id"], str(self.pending_dataset.id))
        self.assertIn("columns", res.data)
        self.assertIn("preview_rows", res.data)
        self.assertIn("suggested_mapping", res.data)


