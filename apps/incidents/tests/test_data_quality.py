import pytest
from datetime import date, timedelta
from apps.incidents.models import Incident, IncidentDataQuality
from apps.incidents.services.data_quality import validate_incident_quality

@pytest.mark.django_db
def test_valid_record():
    incident = Incident.objects.create(
        incident_date=date.today() - timedelta(days=1),
        description="Worker tripped over a loose cable and fell, scratching their arm.",
        job_task="Drilling maintenance",
        body_part="Arm",
        injury_type="Laceration",
        severity_actual=Incident.SeverityActual.FIRST_AID,
        near_miss=False
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.VALID
    assert len(dq.findings) == 0

@pytest.mark.django_db
def test_missing_narrative():
    incident = Incident.objects.create(
        incident_date=date.today() - timedelta(days=1),
        description="",
        body_part="Arm",
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.CRITICAL
    assert any(f["check_id"] == "MISSING_NARRATIVE" for f in dq.findings)

@pytest.mark.django_db
def test_short_narrative():
    incident = Incident.objects.create(
        incident_date=date.today() - timedelta(days=1),
        description="Fell down",
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.WARNING
    assert any(f["check_id"] == "SHORT_NARRATIVE" for f in dq.findings)

@pytest.mark.django_db
def test_placeholder_narrative():
    incident = Incident.objects.create(
        incident_date=date.today() - timedelta(days=1),
        description="test",
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.CRITICAL
    assert any(f["check_id"] == "PLACEHOLDER_NARRATIVE" for f in dq.findings)

@pytest.mark.django_db
def test_injury_body_part_conflict():
    incident = Incident.objects.create(
        incident_date=date.today() - timedelta(days=1),
        description="Worker experienced a serious eye injury from chemical splash.",
        body_part="Knee",
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.CRITICAL
    assert any(f["check_id"] == "INJURY_BODY_PART_CONFLICT" for f in dq.findings)

@pytest.mark.django_db
def test_injury_type_conflict():
    incident = Incident.objects.create(
        incident_date=date.today() - timedelta(days=1),
        description="Worker fell from scaffolding and fractured his arm.",
        injury_type="Laceration",
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.WARNING
    assert any(f["check_id"] == "INJURY_TYPE_CONFLICT" for f in dq.findings)

@pytest.mark.django_db
def test_severity_conflict():
    incident = Incident.objects.create(
        incident_date=date.today() - timedelta(days=1),
        description="Worker was hospitalized after the explosion.",
        severity_actual=Incident.SeverityActual.NONE,
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.WARNING
    assert any(f["check_id"] == "SEVERITY_NARRATIVE_CONFLICT" for f in dq.findings)

@pytest.mark.django_db
def test_near_miss_conflict():
    incident = Incident.objects.create(
        incident_date=date.today() - timedelta(days=1),
        description="Near miss but the worker sustained a serious injury anyway.",
        near_miss=True,
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.WARNING
    assert any(f["check_id"] == "NEAR_MISS_INJURY_CONFLICT" for f in dq.findings)

@pytest.mark.django_db
def test_future_date():
    incident = Incident.objects.create(
        incident_date=date.today() + timedelta(days=1),
        description="Standard description of event.",
    )
    dq = validate_incident_quality(incident)
    assert dq.status == IncidentDataQuality.Status.CRITICAL
    assert any(f["check_id"] == "FUTURE_DATE" for f in dq.findings)
