import pytest
from django.urls import reverse
from rest_framework import status

from apps.datasets.models import Dataset
from apps.datasets.column_mapping import (
    suggest_column_mapping,
    validate_column_mapping,
    find_canonical_field,
    CANONICAL_FIELDS,
)
from apps.datasets.ingestion import create_incident_from_row


def test_suggest_column_mapping_case_insensitive_and_aliases():
    columns = [
        "INCIDENT DESCRIPTION",
        "Dept Name",
        "Date of Occurrence",
        "Affected Body Part",
        "Unknown Custom Column XYZ",
    ]
    mapping = suggest_column_mapping(columns)

    assert mapping["INCIDENT DESCRIPTION"] == "description"
    assert mapping["Dept Name"] == "department"
    assert mapping["Date of Occurrence"] == "incident_date"
    assert mapping["Affected Body Part"] == "body_part"
    assert mapping["Unknown Custom Column XYZ"] == ""  # explicitly unmapped


def test_suggest_column_mapping_prevents_duplicates():
    # If two source columns both look like description, only the first gets mapped
    columns = ["Incident Description", "Description Summary"]
    mapping = suggest_column_mapping(columns)

    assert mapping["Incident Description"] == "description"
    assert mapping["Description Summary"] == ""


def test_validate_column_mapping_valid():
    valid_map = {
        "Col1": "description",
        "Col2": "department",
        "Col3": "",
    }
    errors = validate_column_mapping(valid_map)
    assert errors == []


def test_validate_column_mapping_invalid_field():
    invalid_map = {
        "Col1": "non_existent_field_123",
    }
    errors = validate_column_mapping(invalid_map)
    assert len(errors) == 1
    assert "not a valid canonical field" in errors[0]


def test_validate_column_mapping_duplicate_canonical():
    dup_map = {
        "Source1": "description",
        "Source2": "description",
    }
    errors = validate_column_mapping(dup_map)
    assert len(errors) == 1
    assert "Duplicate mapping" in errors[0]


@pytest.mark.django_db
class TestColumnMappingAPI:
    def test_save_column_mapping_success(self, safety_client, safety_user):
        dataset = Dataset.objects.create(
            name="test.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
        )
        url = reverse("datasets_api:column-mapping", kwargs={"pk": dataset.id})
        payload = {
            "column_mapping": {
                "Source Desc": "description",
                "Source Dept": "department",
                "Extra Notes": "",
            }
        }
        response = safety_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["mapped_fields"] == 2
        assert data["unmapped_fields"] == 1

        dataset.refresh_from_db()
        assert dataset.column_mapping == payload["column_mapping"]

    def test_save_column_mapping_rejects_invalid_state(self, safety_client, safety_user):
        dataset = Dataset.objects.create(
            name="test.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.COMPLETED,
        )
        url = reverse("datasets_api:column-mapping", kwargs={"pk": dataset.id})
        payload = {"column_mapping": {"Col1": "description"}}
        response = safety_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot update mapping" in response.json()["status"][0]

    def test_save_column_mapping_rejects_duplicate_canonical(self, safety_client, safety_user):
        dataset = Dataset.objects.create(
            name="test.csv",
            uploaded_by=safety_user,
            file_type="csv",
            status=Dataset.Status.MAPPING_PENDING,
        )
        url = reverse("datasets_api:column-mapping", kwargs={"pk": dataset.id})
        payload = {
            "column_mapping": {
                "ColA": "description",
                "ColB": "description",
            }
        }
        response = safety_client.post(url, payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "column_mapping" in response.json()


@pytest.mark.django_db
def test_unmapped_source_fields_preserved_in_raw_row(safety_user):
    dataset = Dataset.objects.create(
        name="test.csv",
        uploaded_by=safety_user,
        file_type="csv",
        status=Dataset.Status.MAPPING_PENDING,
    )
    source_row = {
        "Incident ID": "INC-99",
        "Incident Detail": "Scaffolding pipe slipped",
        "Contractor Name": "Acme Builders Inc.",
        "Shift Supervisor": "Jane Doe",
        "Weather Conditions": "Raining heavily",
    }
    mapping = {
        "Incident ID": "external_id",
        "Incident Detail": "description",
        "Contractor Name": "",  # Unmapped
        "Shift Supervisor": "",  # Unmapped
        "Weather Conditions": "",  # Unmapped
    }
    incident = create_incident_from_row(source_row, dataset, mapping)

    # Canonical fields populated
    assert incident.external_id == "INC-99"
    assert incident.description == "Scaffolding pipe slipped"

    # raw_row MUST preserve all original columns and values verbatim
    assert incident.raw_row == source_row
    assert incident.raw_row["Contractor Name"] == "Acme Builders Inc."
    assert incident.raw_row["Weather Conditions"] == "Raining heavily"
