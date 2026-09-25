import pytest
from django.db import connection
from django.urls import reverse
from rest_framework import status

from apps.datasets.models import Dataset
from apps.incidents.models import Incident


@pytest.mark.django_db
class TestDataIntegrityAndPostgreSQL:
    def test_foreign_key_dataset_set_null_on_delete(self, safety_user):
        """Deleting a dataset should SET_NULL on incident.dataset, not crash or delete incidents."""
        dataset = Dataset.objects.create(
            name="delete_test.csv",
            uploaded_by=safety_user,
            file_type="csv",
        )
        incident = Incident.objects.create(
            dataset=dataset,
            description="Test incident for FK cascade check",
        )
        dataset_id = dataset.id
        dataset.delete()

        incident.refresh_from_db()
        assert incident.dataset is None
        assert Incident.objects.filter(id=incident.id).exists()

    def test_raw_row_json_persistence(self, safety_user):
        """JSONField in PostgreSQL must serialize and store arbitrary nested dictionaries."""
        complex_data = {
            "str_key": "val",
            "num_key": 123.45,
            "bool_key": True,
            "nested": {"a": [1, 2, 3]},
            "unicode": "Échafaudage ⚠️",
        }
        incident = Incident.objects.create(
            description="JSON test",
            raw_row=complex_data,
        )
        incident.refresh_from_db()
        assert incident.raw_row == complex_data
        assert incident.raw_row["unicode"] == "Échafaudage ⚠️"
        assert incident.raw_row["nested"]["a"] == [1, 2, 3]

    def test_label_provenance_separation(self):
        """
        Verify the strict distinction between human-approved synthetic labels,
        synthetic benchmark labels, and unlabelled incidents.
        """
        # 1. Human confirmed True on synthetic incident
        inc_human = Incident(
            description="Human reviewed PSIF",
            severity_actual=Incident.SeverityActual.FIRST_AID,
            severity_potential=Incident.SeverityPotential.SERIOUS,
            is_synthetic=True,
            is_psif_human_label=True,
            adjudicated_human_decision=Incident.HumanDecision.PSIF,
            psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
        )
        assert inc_human.is_psif_human_label is True
        assert inc_human.psif_label_source == Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC
        assert inc_human.label_is_human_reviewed is True
        assert inc_human.effective_training_label is True
        assert inc_human.provenance_category == "HUMAN_APPROVED_SYNTHETIC"

        # 2. Synthetic positive benchmark
        inc_synthetic = Incident(
            description="Synthetic benchmark near miss",
            is_synthetic=True,
            raw_row={"sif_label": 1},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_psif_human_label=None,
        )
        assert inc_synthetic.is_psif_human_label is None
        assert inc_synthetic.psif_label_source == Incident.PsifLabelSource.SYNTHETIC
        assert inc_synthetic.label_is_human_reviewed is False
        assert inc_synthetic.effective_training_label is True
        assert inc_synthetic.provenance_category == "SYNTHETIC"

        # 3. Synthetic negative benchmark
        inc_minor = Incident(
            description="Minor incident",
            is_synthetic=True,
            raw_row={"sif_label": 0},
            psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
            is_psif_human_label=None,
        )
        assert inc_minor.is_psif_human_label is None
        assert inc_minor.psif_label_source == Incident.PsifLabelSource.SYNTHETIC
        assert inc_minor.effective_training_label is False
        assert inc_minor.provenance_category == "SYNTHETIC"

    def test_dataset_list_query_efficiency(self, admin_client, safety_user, django_assert_num_queries):
        """
        Verify DatasetListView uses select_related('uploaded_by') to avoid N+1 queries.
        """
        for i in range(10):
            Dataset.objects.create(
                name=f"dataset_{i}.csv",
                uploaded_by=safety_user,
                file_type="csv",
            )

        url = reverse("datasets_api:list")
        # 1 query for count (paginator) + 1 query for datasets with select_related uploaded_by = exactly 2 queries
        with django_assert_num_queries(2):
            response = admin_client.get(url)
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["count"] == 10
