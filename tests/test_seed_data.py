import pytest
from django.core.management import call_command
from apps.incidents.models import Incident
from io import StringIO


@pytest.mark.django_db
def test_seed_data_generates_default_count():
    """Test that seed_data generates exactly 750 records by default."""
    out = StringIO()
    call_command("seed_data", stdout=out)

    assert Incident.objects.count() == 750
    assert "Total incidents:    750" in out.getvalue()


@pytest.mark.django_db
def test_seed_data_generates_correct_distribution():
    """Test that seed_data generates ~20% positive and ~80% negative synthetic labels."""
    call_command("seed_data", count=100)

    total = Incident.objects.count()
    positives = Incident.objects.filter(raw_row__sif_label=1).count()
    negatives = Incident.objects.filter(raw_row__sif_label=0).count()

    assert total == 100
    assert positives == 20
    assert negatives == 80
    assert Incident.objects.filter(is_synthetic=True, psif_label_source=Incident.PsifLabelSource.SYNTHETIC).count() == 100


@pytest.mark.django_db
def test_seed_data_idempotent_with_clear():
    """Test that using --clear removes previous seed data."""
    # Run once
    call_command("seed_data", count=50)
    assert Incident.objects.filter(external_id__startswith="SEED-").count() == 50

    # Run again with clear, should still have only 50 (new ones)
    out = StringIO()
    call_command("seed_data", count=50, clear=True, stdout=out)
    assert Incident.objects.filter(external_id__startswith="SEED-").count() == 50
    assert "Deleted 50 existing seed incidents." in out.getvalue()


@pytest.mark.django_db
def test_seed_data_no_human_labels():
    """Test that synthetic seed data has NO human labels set."""
    call_command("seed_data", count=50)

    # By definition, synthetic data isn't human labeled.
    assert Incident.objects.exclude(is_psif_human_label=None).count() == 0


@pytest.mark.django_db
def test_seed_data_fields_populated():
    """Test that essential fields are correctly populated."""
    call_command("seed_data", count=10)

    incident = Incident.objects.first()
    assert incident is not None
    assert incident.department
    assert incident.location
    assert incident.job_task
    assert incident.equipment_involved
    assert incident.description
    assert incident.severity_actual
    assert incident.severity_potential
    assert incident.composite_narrative
