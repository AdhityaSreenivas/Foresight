import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.incidents.models import Incident
from apps.predictions.models import ModelVersion, PredictionResult
from apps.accounts.models import User


@pytest.fixture
def auth_client():
    client = APIClient()
    user = User.objects.create(email="analyst@example.com", role="analyst")
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_client():
    client = APIClient()
    user = User.objects.create(email="admin@example.com", role="admin")
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def safety_client():
    client = APIClient()
    user = User.objects.create(email="safety@example.com", role="safety_officer")
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def viewer_client():
    client = APIClient()
    user = User.objects.create(email="viewer@example.com", role="viewer")
    client.force_authenticate(user=user)
    return client


from unittest.mock import patch

@pytest.fixture
def mock_predictor():
    """Mocks the get_active_predictor to return a mock predictor."""
    class MockOutput:
        psif_probability = 0.85
        psif_predicted = True
        risk_level = "high"
        top_factors = [{"feature": "test", "contribution": 0.5}]
        
    class MockPredictor:
        def predict(self, record):
            return MockOutput()
            
    with patch("apps.predictions.api_views.get_active_predictor", return_value=MockPredictor()):
        yield


@pytest.mark.django_db
def test_predict_view_success(auth_client, mock_predictor):
    # Setup an active model
    ModelVersion.objects.create(
        version_label="v_test_active",
        is_active=True,
        xgboost_artifact_path="fake/path",
        encoder_artifact_path="fake/path",
        bert_model_name="distilbert-base-uncased",
    )

    payload = {
        "description": "Test description of an incident",
        "severity_actual": "medical_treatment",
        "near_miss": False,
    }

    url = reverse("predictions_api:predict")
    response = auth_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["model_version"] == "v_test_active"
    assert data["psif_score"] == 0.85
    assert "probability" not in data  # Semantic Contract: model score is not probability
    assert data["psif_predicted"] is True
    assert data["risk_level"] == "high"
    
    # Check that incident and prediction were saved
    incident_id = data["incident_id"]
    incident = Incident.objects.get(id=incident_id)
    assert incident.description == "Test description of an incident"
    assert incident.dataset is None
    assert incident.raw_row.get("_manual_prediction") is True
    
    prediction = PredictionResult.objects.get(incident=incident)
    assert prediction.psif_probability == 0.85
    assert prediction.model_version.version_label == "v_test_active"


@pytest.mark.django_db
def test_predict_view_no_active_model(auth_client):
    # No active model version is created
    payload = {
        "description": "Worker slipped on greasy drilling floor and sustained minor knee contusion.",
        "incident_date": "2026-02-01",
    }
    url = reverse("predictions_api:predict")
    response = auth_client.post(url, payload, format="json")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "No active model" in response.json()["error"]


@pytest.mark.django_db
@pytest.mark.parametrize("client_fixture, expected_status", [
    ("admin_client", status.HTTP_200_OK),
    ("safety_client", status.HTTP_200_OK),
    ("auth_client", status.HTTP_200_OK),  # Analyst
    ("viewer_client", status.HTTP_403_FORBIDDEN),
])
def test_predict_view_permissions(client_fixture, expected_status, request, mock_predictor):
    client = request.getfixturevalue(client_fixture)
    ModelVersion.objects.create(
        version_label="v_test_active",
        is_active=True,
        xgboost_artifact_path="fake/path",
        encoder_artifact_path="fake/path",
        bert_model_name="distilbert-base-uncased",
    )

    payload = {"description": "Test permission check"}
    url = reverse("predictions_api:predict")
    response = client.post(url, payload, format="json")

    assert response.status_code == expected_status


@pytest.mark.django_db
def test_predict_view_malformed_input(auth_client, mock_predictor):
    ModelVersion.objects.create(
        version_label="v_test_active",
        is_active=True,
        xgboost_artifact_path="fake/path",
        encoder_artifact_path="fake/path",
        bert_model_name="distilbert-base-uncased",
    )

    # invalid near_miss (string instead of boolean)
    payload = {"near_miss": "not_a_boolean"}
    url = reverse("predictions_api:predict")
    response = auth_client.post(url, payload, format="json")
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
