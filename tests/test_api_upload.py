import io
import json
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from apps.datasets.models import Dataset


@pytest.mark.django_db
class TestFileUploadAPI:
    def test_upload_valid_csv(self, safety_client):
        csv_data = (
            "Incident ID,Incident Date,Department,Severity,Description\n"
            "INC-001,2025-01-10,Welding,serious,Worker burn from torch near-miss\n"
            "INC-002,2025-01-12,Logistics,first_aid,Minor cut on pallet strap\n"
        ).encode("utf-8")
        uploaded = SimpleUploadedFile("incidents.csv", csv_data, content_type="text/csv")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "dataset_id" in data
        assert data["file_type"] == "csv"
        assert data["total_rows"] == 2
        assert len(data["preview_rows"]) == 2
        assert set(data["columns"]) == {"Incident ID", "Incident Date", "Department", "Severity", "Description"}
        assert "suggested_mapping" in data
        assert data["suggested_mapping"]["Description"] == "description"

        # Verify DB object
        dataset = Dataset.objects.get(id=data["dataset_id"])
        assert dataset.name == "incidents.csv"
        assert dataset.file_type == "csv"
        assert dataset.status == Dataset.Status.MAPPING_PENDING

    def test_upload_valid_json(self, admin_client):
        records = [
            {"id": 1, "department": "Machining", "narrative": "Lathe guard slipped"},
            {"id": 2, "department": "Foundry", "narrative": "Molten splash contained"},
        ]
        json_data = json.dumps(records).encode("utf-8")
        uploaded = SimpleUploadedFile("data.json", json_data, content_type="application/json")

        url = reverse("datasets_api:upload")
        response = admin_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["file_type"] == "json"
        assert data["total_rows"] == 2
        assert len(data["preview_rows"]) == 2

    def test_upload_valid_jsonl(self, safety_client):
        lines = (
            '{"id": "A1", "desc": "Forklift horn failed"}\n'
            '{"id": "A2", "desc": "Trip over extension cord"}\n'
            '{"id": "A3", "desc": "Chemical odor in lab"}\n'
        ).encode("utf-8")
        uploaded = SimpleUploadedFile("stream.jsonl", lines, content_type="application/x-ndjson")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["file_type"] == "jsonl"
        assert data["total_rows"] == 3
        assert len(data["preview_rows"]) == 3

    def test_upload_100_row_preview_cap(self, safety_client):
        # Create 150 rows
        header = "row_id,info\n"
        rows = "".join(f"{i},Narrative detail for row {i}\n" for i in range(1, 151))
        uploaded = SimpleUploadedFile("large_preview.csv", (header + rows).encode("utf-8"), content_type="text/csv")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["total_rows"] == 150
        assert len(data["preview_rows"]) == 100  # Capped at 100 for fast sync preview

    def test_upload_unsupported_extension(self, safety_client):
        uploaded = SimpleUploadedFile("malicious.exe", b"binary content", content_type="application/octet-stream")
        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        errors = response.json()
        assert "file" in errors
        assert "not supported" in errors["file"][0]

    def test_upload_extension_content_mismatch(self, safety_client):
        # Named .json but contains CSV
        uploaded = SimpleUploadedFile("fake.json", b"col1,col2\nval1,val2\n", content_type="application/json")
        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        errors = response.json()
        assert "file" in errors
        assert "does not look like JSON" in errors["file"][0]

    def test_upload_empty_file(self, safety_client):
        uploaded = SimpleUploadedFile("empty.csv", b"", content_type="text/csv")
        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        errors = response.json()
        assert "file" in errors

    def test_upload_missing_file_field(self, safety_client):
        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "file" in response.json()

    def test_upload_unauthenticated(self, api_client):
        uploaded = SimpleUploadedFile("test.csv", b"a,b\n1,2\n", content_type="text/csv")
        url = reverse("datasets_api:upload")
        response = api_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_upload_forbidden_for_analyst_and_viewer(self, analyst_client, viewer_client):
        uploaded = SimpleUploadedFile("test.csv", b"a,b\n1,2\n", content_type="text/csv")
        url = reverse("datasets_api:upload")

        # Analyst cannot upload
        res1 = analyst_client.post(url, {"file": uploaded}, format="multipart")
        assert res1.status_code == status.HTTP_403_FORBIDDEN

        # Viewer cannot upload
        res2 = viewer_client.post(url, {"file": uploaded}, format="multipart")
        assert res2.status_code == status.HTTP_403_FORBIDDEN

    def test_upload_file_size_exceeded(self, safety_client, monkeypatch):
        # Lower MAX_SIZE_BYTES to 1KB to test rejection
        from apps.datasets.serializers import UploadFileValidator
        monkeypatch.setattr(UploadFileValidator, "MAX_SIZE_BYTES", 1024)

        large_content = b"a,b\n" + (b"x" * 2048)
        uploaded = SimpleUploadedFile("too_large.csv", large_content, content_type="text/csv")
        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "exceeds the maximum" in response.json()["file"][0]

    def test_upload_max_size_configured_to_250mb(self):
        from django.conf import settings
        from apps.datasets.serializers import UploadFileValidator
        from rest_framework import serializers

        assert settings.MAX_UPLOAD_SIZE_MB == 250
        assert settings.MAX_UPLOAD_SIZE_BYTES == 250 * 1024 * 1024
        assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 250 * 1024 * 1024
        assert settings.FILE_UPLOAD_MAX_MEMORY_SIZE == 250 * 1024 * 1024

        validator = UploadFileValidator()
        assert validator.MAX_SIZE_BYTES == 250 * 1024 * 1024

        # Mock file object with size exactly 250MB
        class MockFile:
            name = "test.csv"
            size = 250 * 1024 * 1024

        mock_file = MockFile()
        assert validator(mock_file) is mock_file

        # Mock file object with size 250MB + 1 byte
        class MockFileTooLarge:
            name = "test.csv"
            size = (250 * 1024 * 1024) + 1

        import pytest
        with pytest.raises(serializers.ValidationError) as exc_info:
            validator(MockFileTooLarge())
        assert "exceeds the maximum allowed upload size of 250MB" in str(exc_info.value)
