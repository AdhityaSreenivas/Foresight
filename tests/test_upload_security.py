import json
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from apps.datasets.models import Dataset


@pytest.mark.django_db
class TestUploadSecurity:
    def test_path_traversal_filename_sanitized(self, safety_client):
        """Ensure path traversal characters in filename do not escape media/uploads directory."""
        traversal_name = "../../../etc/passwd.csv"
        csv_data = b"col1,col2\nval1,val2\n"
        uploaded = SimpleUploadedFile(traversal_name, csv_data, content_type="text/csv")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        dataset = Dataset.objects.get(id=response.json()["dataset_id"])
        # Check actual stored path
        stored_path = dataset.original_file.path
        assert ".." not in stored_path
        assert "uploads/" in stored_path
        assert "/etc/passwd" not in stored_path

    def test_mime_spoofing_binary_as_csv(self, safety_client):
        """Content-Type says text/csv, but payload is binary ELF/executable header."""
        binary_payload = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        uploaded = SimpleUploadedFile("binary.csv", binary_payload, content_type="text/csv")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        # Either parsed without executing or rejected
        # Crucially, it must not execute or crash the server
        assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)

    def test_extension_spoofing_csv_named_json(self, safety_client):
        """File is named data.json but contains CSV text."""
        csv_data = b"col_a,col_b\n1,2\n"
        uploaded = SimpleUploadedFile("data.json", csv_data, content_type="application/json")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not look like JSON" in response.json()["file"][0]

    def test_api_response_does_not_leak_filesystem_paths_or_secrets(self, safety_client):
        """Ensure no server filesystem paths (e.g. /Users/...) or SECRET_KEY are in JSON response."""
        csv_data = b"id,desc\n1,Routine maintenance\n"
        uploaded = SimpleUploadedFile("safe.csv", csv_data, content_type="text/csv")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        response_text = response.content.decode("utf-8")
        assert "/media/" not in response_text
        assert "/Users/" not in response_text
        assert "/home/" not in response_text
        assert "password" not in response_text.lower()
        assert "secret" not in response_text.lower()

    def test_xss_payload_remains_inert_data(self, safety_client):
        """Ensure script tags and event handlers in columns or values are treated as pure text."""
        xss_csv = (
            '<script>alert("XSS")</script>,payload_col\n'
            '<img src=x onerror=alert(1)>,<svg onload=alert(document.cookie)>\n'
        ).encode("utf-8")
        uploaded = SimpleUploadedFile("xss.csv", xss_csv, content_type="text/csv")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        # Script tags are present verbatim as data, not executed or altered
        assert '<script>alert("XSS")</script>' in data["columns"]
        assert '<img src=x onerror=alert(1)>' in str(data["preview_rows"])

    def test_no_eval_or_exec_on_python_code_in_uploaded_file(self, safety_client):
        """Python code syntax in CSV should simply be parsed as text."""
        py_payload = (
            "col1,col2\n"
            '__import__("os").system("echo hacked"),eval("1+1")\n'
        ).encode("utf-8")
        uploaded = SimpleUploadedFile("code.csv", py_payload, content_type="text/csv")

        url = reverse("datasets_api:upload")
        response = safety_client.post(url, {"file": uploaded}, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert '__import__("os").system("echo hacked")' in data["preview_rows"][0]["col1"]
