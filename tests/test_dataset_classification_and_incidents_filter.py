"""
Tests for Dataset PSIF/Non-PSIF Classification Metrics and Incidents Dataset Filtering.
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.datasets.models import Dataset
from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion

User = get_user_model()


@pytest.fixture
def test_setup(db):
    user = User.objects.create_user(
        username="officer_filter_test",
        email="officer_filter@example.com",
        password="testpassword123",
        role=User.Role.SAFETY_OFFICER,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    model_version, _ = ModelVersion.objects.get_or_create(
        version_label="v1.0.0-test",
        defaults={
            "bert_model_name": "test-bert",
            "xgboost_artifact_path": "/tmp/model.json",
            "encoder_artifact_path": "/tmp/enc.joblib",
            "is_active": True,
            "status": ModelVersion.Status.ACTIVE,
            "metrics": {"f1": 0.9},
        }
    )

    # Create two distinct datasets
    ds1 = Dataset.objects.create(
        name="dataset_one.csv",
        uploaded_by=user,
        file_type="csv",
        status=Dataset.Status.COMPLETED,
        total_rows=10,
        processed_rows=10,
        quality_summary={
            "total": 10,
            "accepted": 10,
            "accepted_with_warnings": 0,
            "rejected": 0,
        }
    )

    ds2 = Dataset.objects.create(
        name="dataset_two.csv",
        uploaded_by=user,
        file_type="csv",
        status=Dataset.Status.COMPLETED,
        total_rows=5,
        processed_rows=5,
        quality_summary={
            "total": 5,
            "accepted": 5,
            "accepted_with_warnings": 0,
            "rejected": 0,
        }
    )

    # In ds1: 3 PSIF, 2 Non-PSIF
    for i in range(3):
        inc = Incident.objects.create(
            dataset=ds1,
            description=f"DS1 PSIF incident {i}",
            composite_narrative=f"Worker fell from high scaffold {i}",
            department="Operations",
            status=Incident.Status.PENDING,
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=model_version,
            psif_probability=0.88,
            psif_predicted=True,
            risk_level=PredictionResult.RiskLevel.CRITICAL,
        )

    for i in range(2):
        inc = Incident.objects.create(
            dataset=ds1,
            description=f"DS1 Non-PSIF incident {i}",
            composite_narrative=f"Minor papercut in administrative office {i}",
            department="Operations",
            status=Incident.Status.PENDING,
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=model_version,
            psif_probability=0.12,
            psif_predicted=False,
            risk_level=PredictionResult.RiskLevel.LOW,
        )

    # In ds2: 1 PSIF, 4 Non-PSIF
    for i in range(1):
        inc = Incident.objects.create(
            dataset=ds2,
            description=f"DS2 PSIF incident {i}",
            composite_narrative=f"High pressure gas release {i}",
            department="Maintenance",
            status=Incident.Status.PENDING,
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=model_version,
            psif_probability=0.92,
            psif_predicted=True,
            risk_level=PredictionResult.RiskLevel.CRITICAL,
        )

    for i in range(4):
        inc = Incident.objects.create(
            dataset=ds2,
            description=f"DS2 Non-PSIF incident {i}",
            composite_narrative=f"Minor slip on dry gravel {i}",
            department="Maintenance",
            status=Incident.Status.PENDING,
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=model_version,
            psif_probability=0.15,
            psif_predicted=False,
            risk_level=PredictionResult.RiskLevel.LOW,
        )

    return client, user, ds1, ds2


@pytest.mark.django_db
class TestDatasetClassificationMetrics:
    def test_dataset_model_psif_properties(self, test_setup):
        _, _, ds1, ds2 = test_setup
        assert ds1.psif_count == 3
        assert ds1.non_psif_count == 2

        assert ds2.psif_count == 1
        assert ds2.non_psif_count == 4

    def test_api_dataset_status_includes_psif_counts(self, test_setup):
        client, _, ds1, _ = test_setup
        res = client.get(f"/api/datasets/{ds1.id}/status/")
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["psif_count"] == 3
        assert data["non_psif_count"] == 2

    def test_status_page_html_renders_psif_summary(self, client, test_setup):
        _, user, ds1, _ = test_setup
        client.force_login(user)

        res = client.get(f"/datasets/{ds1.id}/status/")
        assert res.status_code == 200
        html = res.content.decode("utf-8")

        # Check section, cards, and labels
        assert "PSIF Classification Results" in html
        assert 'id="classification-count-psif"' in html
        assert 'id="classification-count-non-psif"' in html
        assert "PSIF CANDIDATE" in html
        assert "NON-PSIF" in html

        # Check links to filtered incidents
        assert f"/incidents/?dataset={ds1.id}" in html
        assert "View Incidents from this Dataset" in html or "Filter Incidents in Dataset" in html


@pytest.mark.django_db
class TestIncidentsDatasetFilter:
    def test_api_incidents_filter_by_dataset(self, test_setup):
        client, _, ds1, ds2 = test_setup

        # Query without dataset: returns all 10 incidents created
        res_all = client.get("/api/incidents/")
        assert res_all.status_code == 200
        assert res_all.json()["count"] >= 10

        # Query strictly for ds1: should return exactly 5 incidents
        res_ds1 = client.get(f"/api/incidents/?dataset={ds1.id}")
        assert res_ds1.status_code == 200
        data_ds1 = res_ds1.json()
        assert data_ds1["count"] == 5
        for item in data_ds1["results"]:
            assert item["dataset_id"] == str(ds1.id)
            assert item["dataset_name"] == ds1.name

        # Query strictly for ds2: should return exactly 5 incidents
        res_ds2 = client.get(f"/api/incidents/?dataset={ds2.id}")
        assert res_ds2.status_code == 200
        data_ds2 = res_ds2.json()
        assert data_ds2["count"] == 5
        for item in data_ds2["results"]:
            assert item["dataset_id"] == str(ds2.id)
            assert item["dataset_name"] == ds2.name

    def test_incidents_page_renders_dataset_filter(self, client, test_setup):
        _, user, ds1, ds2 = test_setup
        client.force_login(user)

        # 1. Base incidents page
        res = client.get("/incidents/")
        assert res.status_code == 200
        html = res.content.decode("utf-8")

        assert 'id="filter-dataset"' in html
        assert "All Datasets" in html
        assert ds1.name in html
        assert ds2.name in html
        assert "Dataset Source" in html

        # 2. Page loaded with ?dataset=<id> pre-selected
        res_filtered = client.get(f"/incidents/?dataset={ds1.id}")
        assert res_filtered.status_code == 200
        html_filtered = res_filtered.content.decode("utf-8")
        assert f'value="{ds1.id}" selected' in html_filtered

    def test_incidents_csv_export_filters_by_dataset(self, client, test_setup):
        _, user, ds1, _ = test_setup
        client.force_login(user)

        res = client.get(f"/incidents/export/?dataset={ds1.id}")
        assert res.status_code == 200
        assert res["Content-Type"] == "text/csv"
        csv_lines = res.content.decode("utf-8").strip().splitlines()
        # 1 header line + 5 data rows = 6 lines
        assert len(csv_lines) == 6
