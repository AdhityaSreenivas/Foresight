import pytest
from unittest.mock import MagicMock
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.datasets.models import Dataset
from apps.datasets.tasks import process_dataset
from apps.incidents.models import Incident
from apps.predictions.models import ModelVersion, PredictionResult


from unittest.mock import patch

@pytest.fixture
def mock_predict_batch():
    class MockOutput:
        def __init__(self):
            self.psif_probability = 0.90
            self.psif_predicted = True
            self.risk_level = "critical"
            self.top_factors = []
            
    class MockPredictor:
        def predict_batch(self, records):
            return [MockOutput() for _ in records]
            
    with patch("ml_engine.model_inference.get_active_predictor", return_value=MockPredictor()):
        yield MockPredictor


@pytest.fixture
def sample_dataset():
    # Make enough rows for 3 chunks (chunk size is 1000 so we'll need to mock iter_file_chunks if we want real multiple chunks with a small file)
    # Actually, we can just patch iter_file_chunks to yield small chunks for testing.
    csv_content = b"description,severity_actual\nIncident A,medical_treatment\nIncident B,first_aid"
    f = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
    dataset = Dataset.objects.create(
        original_file=f,
        file_type=Dataset.FileType.CSV,
        status=Dataset.Status.PROCESSING,
        column_mapping={"description": "description", "severity_actual": "severity_actual"}
    )
    return dataset


@pytest.mark.django_db
def test_process_dataset_with_active_model(sample_dataset, mock_predict_batch):
    # Create active model version
    model_ver = ModelVersion.objects.create(
        version_label="v_active",
        is_active=True,
        xgboost_artifact_path="fake",
        encoder_artifact_path="fake",
        bert_model_name="fake",
    )
    
    # Process dataset
    result = process_dataset(dataset_id=str(sample_dataset.id))
    
    assert result["status"] == "completed"
    assert result["processed_rows"] == 2
    
    # Check that PredictionResult was created for each Incident
    incidents = Incident.objects.filter(dataset=sample_dataset)
    assert incidents.count() == 2
    
    predictions = PredictionResult.objects.filter(incident__in=incidents)
    assert predictions.count() == 2
    
    for p in predictions:
        assert p.model_version == model_ver
        assert p.psif_predicted is True


@pytest.mark.django_db
def test_process_dataset_no_active_model(sample_dataset):
    # Ensure no active models exist
    ModelVersion.objects.all().delete()
    
    result = process_dataset(dataset_id=str(sample_dataset.id))
    
    # Should complete successfully but with predictions skipped
    assert result["status"] == "completed"
    
    # Check dataset log for warning
    sample_dataset.refresh_from_db()
    assert "Predictions skipped" in sample_dataset.error_log
    
    # Check that Incidents were created but NO predictions
    incidents = Incident.objects.filter(dataset=sample_dataset)
    assert incidents.count() == 2
    assert PredictionResult.objects.count() == 0


@pytest.mark.django_db
def test_process_dataset_idempotency(sample_dataset, mock_predict_batch):
    model_ver = ModelVersion.objects.create(
        version_label="v_active",
        is_active=True,
        xgboost_artifact_path="fake",
        encoder_artifact_path="fake",
        bert_model_name="fake",
    )
    
    # Run once
    process_dataset(dataset_id=str(sample_dataset.id))
    assert PredictionResult.objects.count() == 2
    assert Incident.objects.count() == 2
    
    # Simulate a full retry by resetting status back to PROCESSING (without clearing chunks_processed)
    sample_dataset.refresh_from_db()
    assert sample_dataset.chunks_processed == 1
    sample_dataset.status = Dataset.Status.PROCESSING
    sample_dataset.save()
    
    # Re-run task
    process_dataset(dataset_id=str(sample_dataset.id))
    
    # Total incidents should still be 2 because the chunk is skipped
    assert Incident.objects.filter(dataset=sample_dataset).count() == 2
    assert PredictionResult.objects.count() == 2


@pytest.mark.django_db
def test_process_dataset_partial_failure_resume(sample_dataset, mock_predict_batch):
    model_ver = ModelVersion.objects.create(
        version_label="v_active",
        is_active=True,
        xgboost_artifact_path="fake",
        encoder_artifact_path="fake",
        bert_model_name="fake",
    )
    
    # We mock iter_file_chunks to yield two chunks.
    # The first one succeeds, the second one raises an exception.
    calls = []
    
    def fake_iter_file_chunks(path, type):
        yield ([{"description": "Worker slipped on catwalk stairs and sustained minor elbow contusion", "severity_actual": "first_aid"}], 0)
        yield ([{"description": "Mechanic caught finger in machinery guard sustaining small cut requiring stitches", "severity_actual": "medical_treatment"}], 0)
    
    # Run first time with an error in bulk_create_incidents during chunk 2
    orig_bulk = __import__("apps.datasets.ingestion").datasets.ingestion.bulk_create_incidents
    
    def failing_bulk(rows, dataset, mapping, *args, **kwargs):
        calls.append(len(rows))
        if len(calls) == 2:
            raise RuntimeError("Fake db crash")
        return orig_bulk(rows, dataset, mapping, *args, **kwargs)
        
    with patch("apps.datasets.parsers.iter_file_chunks", side_effect=fake_iter_file_chunks):
        with patch("apps.datasets.ingestion.bulk_create_incidents", side_effect=failing_bulk):
            with pytest.raises(RuntimeError):
                process_dataset(dataset_id=str(sample_dataset.id))
                
    # Verify partial progress
    sample_dataset.refresh_from_db()
    assert sample_dataset.status == Dataset.Status.FAILED
    assert sample_dataset.chunks_processed == 1
    assert sample_dataset.processed_rows == 1
    assert Incident.objects.count() == 1
    assert PredictionResult.objects.count() == 1
    
    # Reset status for retry
    sample_dataset.status = Dataset.Status.PROCESSING
    sample_dataset.save()
    
    # Re-run with the error removed
    with patch("apps.datasets.parsers.iter_file_chunks", side_effect=fake_iter_file_chunks):
        process_dataset(dataset_id=str(sample_dataset.id))
        
    # Verify completion
    sample_dataset.refresh_from_db()
    assert sample_dataset.status == Dataset.Status.COMPLETED
    assert sample_dataset.chunks_processed == 2
    assert sample_dataset.processed_rows == 2
    assert Incident.objects.count() == 2
    assert PredictionResult.objects.count() == 2
