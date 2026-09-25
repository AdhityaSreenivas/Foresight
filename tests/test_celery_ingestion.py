import tempfile
from pathlib import Path
import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from rest_framework import status
from unittest.mock import patch

from apps.datasets.models import Dataset
from apps.datasets.tasks import process_dataset
from apps.incidents.models import Incident


@pytest.mark.django_db
class TestCeleryIngestion:
    def test_process_dataset_task_end_to_end_csv(self, safety_user):
        # Create CSV file with 3 rows:
        # 1. Potential=serious, Actual=none -> PSIF heuristic positive
        # 2. Potential=low, Actual=first_aid -> PSIF heuristic negative
        # 3. Malformed date / partially missing fields
        csv_content = (
            "ID,Date,Dept,Actual,Potential,Narrative,Action\n"
            "INC-101,2025-01-15,Welding,none,serious,High pressure hose burst near worker,Replaced all hoses\n"
            "INC-102,2025-01-16,Assembly,first_aid,low,Minor papercut,Bandage applied\n"
            "INC-103,invalid-date,Maintenance,first_aid,moderate,Dropped wrench on boot,None\n"
        ).encode("utf-8")

        dataset = Dataset.objects.create(
            name="test_ingest.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            column_mapping={
                "ID": "external_id",
                "Date": "incident_date",
                "Dept": "department",
                "Actual": "severity_actual",
                "Potential": "severity_potential",
                "Narrative": "description",
                "Action": "corrective_actions",
            },
        )
        dataset.original_file.save("test_ingest.csv", ContentFile(csv_content), save=True)

        # Run process_dataset task directly
        result = process_dataset(str(dataset.id))

        assert result["status"] == "completed"
        assert result["processed_rows"] == 3

        dataset.refresh_from_db()
        assert dataset.status == Dataset.Status.COMPLETED
        assert dataset.processed_rows == 3
        assert dataset.completed_at is not None

        # Verify Incidents created
        incidents = Incident.objects.filter(dataset=dataset).order_by("external_id")
        assert incidents.count() == 3

        inc1 = incidents.filter(external_id="INC-101").first()
        assert inc1 is not None
        assert inc1.department == "Welding"
        assert inc1.severity_actual == Incident.SeverityActual.NONE
        assert inc1.is_synthetic is True
        assert inc1.psif_label_source == Incident.PsifLabelSource.SYNTHETIC
        assert "High pressure hose burst" in inc1.composite_narrative
        assert "Replaced all hoses" in inc1.composite_narrative
        assert inc1.raw_row["ID"] == "INC-101"

        inc2 = incidents.filter(external_id="INC-102").first()
        assert inc2 is not None
        assert inc2.is_synthetic is True
        assert inc2.psif_label_source == Incident.PsifLabelSource.SYNTHETIC

        inc3 = incidents.filter(external_id="INC-103").first()
        assert inc3 is not None
        assert inc3.incident_date is None  # invalid date gracefully coerced to None without failing

    def test_process_dataset_skips_when_not_in_processing_state(self, safety_user):
        dataset = Dataset.objects.create(
            name="already_done.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.COMPLETED,
            column_mapping={"col": "description"},
        )
        result = process_dataset(str(dataset.id))
        assert result["status"] == "skipped"

    def test_process_api_dispatch(self, safety_client, safety_user):
        dataset = Dataset.objects.create(
            name="dispatch_test.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
            column_mapping={"Desc": "description"},
        )
        csv_content = b"Desc\nSome incident narrative\n"
        dataset.original_file.save("dispatch.csv", ContentFile(csv_content), save=True)

        url = reverse("datasets_api:process", kwargs={"pk": dataset.id})
        response = safety_client.post(url)

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["dataset_id"] == str(dataset.id)
        assert data["task_id"] is not None

        dataset.refresh_from_db()
        # In test / eager mode, processing completed or is processing
        assert dataset.status in (Dataset.Status.PROCESSING, Dataset.Status.COMPLETED)

    def test_process_api_broker_failure(self, safety_client, safety_user, settings):
        settings.DEV_SYNC_FALLBACK = False  # Normal production behavior
        
        dataset = Dataset.objects.create(
            name="dispatch_fail.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
            column_mapping={"Desc": "description"},
        )
        csv_content = b"Desc\nSome incident narrative\n"
        dataset.original_file.save("dispatch.csv", ContentFile(csv_content), save=True)

        url = reverse("datasets_api:process", kwargs={"pk": dataset.id})
        
        # Mock broker delay failure
        with patch("apps.datasets.tasks.process_dataset.delay", side_effect=Exception("Redis dead")):
            response = safety_client.post(url)
            
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        dataset.refresh_from_db()
        assert dataset.status == Dataset.Status.FAILED
        assert "Redis dead" in dataset.error_log

    def test_process_api_broker_failure_sync_fallback(self, safety_client, safety_user, settings):
        settings.DEV_SYNC_FALLBACK = True  # Development explicitly turned on
        
        dataset = Dataset.objects.create(
            name="dispatch_fail.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
            column_mapping={"Desc": "description"},
        )
        csv_content = b"Desc\nSome incident narrative\n"
        dataset.original_file.save("dispatch.csv", ContentFile(csv_content), save=True)

        url = reverse("datasets_api:process", kwargs={"pk": dataset.id})
        
        # Mock broker delay failure, but it should fallback to sync execution
        with patch("apps.datasets.tasks.process_dataset.delay", side_effect=Exception("Redis dead")):
            response = safety_client.post(url)
            
        # Instead of 503, it runs synchronously and returns 202
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json()["task_id"] == "sync-executed"
        
        dataset.refresh_from_db()
        assert dataset.status == Dataset.Status.COMPLETED

