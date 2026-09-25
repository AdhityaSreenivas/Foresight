"""
Tests for Incidents List Pagination UI and API
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.incidents.models import Incident

User = get_user_model()


@pytest.fixture
def auth_client(db):
    user = User.objects.create_user(
        username="safety_officer_test",
        email="officer@example.com",
        password="testpassword123",
        role=User.Role.SAFETY_OFFICER,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
class TestIncidentsPagination:
    def test_incidents_page_renders_pagination_controls(self, client, auth_client):
        _, user = auth_client
        client.force_login(user)

        response = client.get("/incidents/")
        assert response.status_code == 200
        content = response.content.decode()

        # Check required DOM elements for enhanced pagination
        assert 'id="pagination-container"' in content
        assert 'id="pagination-info"' in content
        assert 'id="pagination-nav"' in content
        assert 'id="page-size-select"' in content
        assert 'id="jump-page-input"' in content
        assert 'id="btn-jump-page"' in content

        # Check script functions and display format
        assert "getWindowedPageNumbers" in content
        assert "renderPagination" in content
        assert "goToPage" in content
        assert "Page <strong>" in content
        assert "Showing <strong>" in content

    def test_api_incidents_pagination_page_size_support(self, auth_client):
        api_client, _ = auth_client

        # Test default page size (25)
        res_default = api_client.get("/api/incidents/?page=1")
        assert res_default.status_code == 200
        data_default = res_default.json()
        assert "count" in data_default
        assert "results" in data_default
        assert len(data_default["results"]) <= 25

        # Test custom page size (50)
        res_50 = api_client.get("/api/incidents/?page=1&page_size=50")
        assert res_50.status_code == 200
        data_50 = res_50.json()
        assert "count" in data_50
        assert len(data_50["results"]) <= 50

        # Test custom page size (100)
        res_100 = api_client.get("/api/incidents/?page=1&page_size=100")
        assert res_100.status_code == 200
        data_100 = res_100.json()
        assert len(data_100["results"]) <= 100
