import pytest
from django.urls import reverse
from django.core.files.base import ContentFile
from rest_framework import status
from apps.datasets.models import Dataset


@pytest.mark.django_db
class TestRolePermissions:
    @pytest.fixture
    def sample_dataset(self, safety_user):
        ds = Dataset.objects.create(
            name="perm_sample.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
            column_mapping={"Desc": "description"},
        )
        ds.original_file.save("perm.csv", ContentFile(b"Desc\nIncident text\n"), save=True)
        return ds

    # ── Upload Endpoint ───────────────────────────────────────────────────────
    def test_upload_permissions(self, api_client, viewer_client, analyst_client, safety_client, admin_client):
        url = reverse("datasets_api:upload")
        # Unauthenticated
        assert api_client.post(url, {}).status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        # Viewer
        assert viewer_client.post(url, {}).status_code == status.HTTP_403_FORBIDDEN
        # Analyst
        assert analyst_client.post(url, {}).status_code == status.HTTP_403_FORBIDDEN
        # Safety Officer & Admin allowed past permission layer (fails serializer with 400 on empty body)
        assert safety_client.post(url, {}).status_code == status.HTTP_400_BAD_REQUEST
        assert admin_client.post(url, {}).status_code == status.HTTP_400_BAD_REQUEST

    # ── List Endpoint ─────────────────────────────────────────────────────────
    def test_list_permissions_and_scoping(self, api_client, viewer_client, analyst_client, safety_client, admin_client, viewer_user, safety_user):
        url = reverse("datasets_api:list")
        # Create dataset by viewer and dataset by safety
        ds_viewer = Dataset.objects.create(name="viewer_owned.csv", uploaded_by=viewer_user, file_type="csv")
        ds_safety = Dataset.objects.create(name="safety_owned.csv", uploaded_by=safety_user, file_type="csv")

        # Unauthenticated
        assert api_client.get(url).status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

        # Viewer only sees their own
        res_v = viewer_client.get(url)
        assert res_v.status_code == status.HTTP_200_OK
        ids_v = [d["id"] for d in res_v.json()["results"]]
        assert str(ds_viewer.id) in ids_v
        assert str(ds_safety.id) not in ids_v

        # Safety officer sees all
        res_s = safety_client.get(url)
        assert res_s.status_code == status.HTTP_200_OK
        ids_s = [d["id"] for d in res_s.json()["results"]]
        assert str(ds_viewer.id) in ids_s
        assert str(ds_safety.id) in ids_s

        # Admin sees all
        res_a = admin_client.get(url)
        assert res_a.status_code == status.HTTP_200_OK
        ids_a = [d["id"] for d in res_a.json()["results"]]
        assert str(ds_viewer.id) in ids_a
        assert str(ds_safety.id) in ids_a

    # ── Status Endpoint ───────────────────────────────────────────────────────
    def test_status_permissions(self, api_client, viewer_client, analyst_client, safety_client, admin_client, sample_dataset):
        url = reverse("datasets_api:status", kwargs={"pk": sample_dataset.id})
        # Unauthenticated
        assert api_client.get(url).status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        # All authenticated users may view status
        assert viewer_client.get(url).status_code == status.HTTP_200_OK
        assert analyst_client.get(url).status_code == status.HTTP_200_OK
        assert safety_client.get(url).status_code == status.HTTP_200_OK
        assert admin_client.get(url).status_code == status.HTTP_200_OK

    # ── Column Mapping Endpoint ───────────────────────────────────────────────
    def test_column_mapping_permissions(self, api_client, viewer_client, analyst_client, safety_client, admin_client, sample_dataset):
        url = reverse("datasets_api:column-mapping", kwargs={"pk": sample_dataset.id})
        payload = {"column_mapping": {"Desc": "description"}}
        # Unauthenticated
        assert api_client.post(url, payload, format="json").status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        # Viewer & Analyst forbidden
        assert viewer_client.post(url, payload, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert analyst_client.post(url, payload, format="json").status_code == status.HTTP_403_FORBIDDEN
        # Safety & Admin allowed
        assert safety_client.post(url, payload, format="json").status_code == status.HTTP_200_OK
        assert admin_client.post(url, payload, format="json").status_code == status.HTTP_200_OK

    # ── Process Endpoint ──────────────────────────────────────────────────────
    def test_process_permissions(self, api_client, viewer_client, analyst_client, safety_client, sample_dataset):
        url = reverse("datasets_api:process", kwargs={"pk": sample_dataset.id})
        # Unauthenticated
        assert api_client.post(url).status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        # Viewer & Analyst forbidden
        assert viewer_client.post(url).status_code == status.HTTP_403_FORBIDDEN
        assert analyst_client.post(url).status_code == status.HTTP_403_FORBIDDEN
        # Safety officer allowed
        assert safety_client.post(url).status_code == status.HTTP_202_ACCEPTED
