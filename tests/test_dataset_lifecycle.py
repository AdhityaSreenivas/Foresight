import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.datasets.models import Dataset


@pytest.mark.django_db
class TestDatasetLifecycle:
    def test_dataset_initial_creation_state(self, safety_user):
        dataset = Dataset.objects.create(
            name="lifecycle.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.UPLOADED,
            total_rows=100,
        )
        assert dataset.status == Dataset.Status.UPLOADED
        assert dataset.processed_rows == 0
        assert dataset.percent_complete == 0.0
        assert dataset.completed_at is None
        assert dataset.error_log is None or dataset.error_log == ""

    def test_status_polling_endpoint(self, safety_client, safety_user):
        dataset = Dataset.objects.create(
            name="polling.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
            total_rows=200,
            processed_rows=50,
        )
        url = reverse("datasets_api:status", kwargs={"pk": dataset.id})
        response = safety_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "processing"
        assert data["total_rows"] == 200
        assert data["processed_rows"] == 50
        assert data["percent"] == 25.0

    def test_invalid_state_transitions_on_process_endpoint(self, safety_client, safety_user):
        # 1. Reject if already completed
        dataset = Dataset.objects.create(
            name="done.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.COMPLETED,
            column_mapping={"col": "description"},
        )
        url = reverse("datasets_api:process", kwargs={"pk": dataset.id})
        res1 = safety_client.post(url)
        assert res1.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been processed" in res1.json()["status"][0]

        # 2. Reject if currently processing
        dataset.status = Dataset.Status.PROCESSING
        dataset.save()
        res2 = safety_client.post(url)
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert "already being processed" in res2.json()["status"][0]

        # 3. Reject if failed
        dataset.status = Dataset.Status.FAILED
        dataset.save()
        res3 = safety_client.post(url)
        assert res3.status_code == status.HTTP_400_BAD_REQUEST
        assert "already been processed" in res3.json()["status"][0]

    def test_process_rejects_empty_mapping(self, safety_client, safety_user):
        dataset = Dataset.objects.create(
            name="nomap.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
            column_mapping={},
        )
        url = reverse("datasets_api:process", kwargs={"pk": dataset.id})
        response = safety_client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "No column mapping found" in response.json()["column_mapping"][0]

    def test_process_rejects_all_unmapped_columns(self, safety_client, safety_user):
        dataset = Dataset.objects.create(
            name="allunmapped.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
            column_mapping={"Col1": "", "Col2": ""},
        )
        url = reverse("datasets_api:process", kwargs={"pk": dataset.id})
        response = safety_client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "no fields are mapped" in response.json()["column_mapping"][0]

    def test_dataset_error_log_appending(self, safety_user):
        dataset = Dataset.objects.create(
            name="error_test.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.PROCESSING,
        )
        dataset.append_error("Error 1: Missing date")
        dataset.append_error("Error 2: Unknown category")
        dataset.save()

        assert "Error 1: Missing date" in dataset.error_log
        assert "Error 2: Unknown category" in dataset.error_log
