import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.datasets.models import Dataset


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin_user",
        email="admin@example.com",
        password="password123",
        role=User.Role.ADMIN,
    )


@pytest.fixture
def safety_user(db):
    return User.objects.create_user(
        username="safety_user",
        email="safety@example.com",
        password="password123",
        role=User.Role.SAFETY_OFFICER,
    )


@pytest.fixture
def analyst_user(db):
    return User.objects.create_user(
        username="analyst_user",
        email="analyst@example.com",
        password="password123",
        role=User.Role.ANALYST,
    )


@pytest.fixture
def viewer_user(db):
    return User.objects.create_user(
        username="viewer_user",
        email="viewer@example.com",
        password="password123",
        role=User.Role.VIEWER,
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def safety_client(safety_user):
    client = APIClient()
    client.force_authenticate(user=safety_user)
    return client


@pytest.fixture
def analyst_client(analyst_user):
    client = APIClient()
    client.force_authenticate(user=analyst_user)
    return client


@pytest.fixture
def viewer_client(viewer_user):
    client = APIClient()
    client.force_authenticate(user=viewer_user)
    return client
