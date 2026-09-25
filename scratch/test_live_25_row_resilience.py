import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()

from django.core.files.base import ContentFile
from apps.datasets.models import Dataset
from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.datasets.recovery import check_and_recover_dataset
from django.contrib.auth import get_user_model
User = get_user_model()

def run_live_25_row_test():
    print("=== LIVE 25-ROW DATASET FORCED-FAILURE & RECOVERY TEST ===")
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        user = User.objects.first()

    # 1. Create a 25-row CSV fixture
    lines = ["ID,incident_date,department,severity_actual,severity_potential,description,corrective_actions"]
    for i in range(1, 26):
        lines.append(f"LIVE25-{i:03d},2025-02-10,Drilling,none,serious,Live test incident {i} on drilling rig,Fixed issue {i}")
    csv_content = "\n".join(lines).encode("utf-8")

    ds_id = str(uuid.uuid4())
    dataset = Dataset.objects.create(
        id=ds_id,
        name="live_resilience_test_25.csv",
        uploaded_by=user,
        file_type="csv",
        status=Dataset.Status.PROCESSING,
        total_rows=25,
        processed_rows=0,
        chunks_processed=0,
        column_mapping={
            "ID": "external_id",
            "incident_date": "incident_date",
            "department": "department",
            "severity_actual": "severity_actual",
            "severity_potential": "severity_potential",
            "description": "description",
            "corrective_actions": "corrective_actions",
        }
    )
    dataset.original_file.save("live_resilience_test_25.csv", ContentFile(csv_content), save=True)
    print(f"Created Dataset {dataset.id} with 25 rows.")

    # 2. Simulate partial work: ingest first 10 rows (checkpoint: chunk 1)
    from apps.datasets.ingestion import bulk_create_incidents
    from django.conf import settings
    chunk_size = getattr(settings, "CSV_CHUNK_SIZE", 3)
    chunk1_rows = [
        {
            "ID": f"LIVE25-{i:03d}",
            "incident_date": "2025-02-10",
            "department": "Drilling",
            "severity_actual": "none",
            "severity_potential": "serious",
            "description": f"Live test incident {i} on drilling rig",
            "corrective_actions": f"Fixed issue {i}",
        }
        for i in range(1, chunk_size + 1)
    ]
    created, errs = bulk_create_incidents(chunk1_rows, dataset, dataset.column_mapping, start_row_index=1)
    assert len(created) == chunk_size, f"Expected {chunk_size} created incidents, got {len(created)}"
    dataset.processed_rows = chunk_size
    dataset.chunks_processed = 1
    dataset.current_task_id = "simulated-crashed-task-" + str(uuid.uuid4())[:8]
    from django.utils import timezone
    from datetime import timedelta
    dataset.last_heartbeat_at = timezone.now() - timedelta(seconds=200)
    dataset.quality_summary = {"total": chunk_size, "accepted": chunk_size, "accepted_with_warnings": chunk_size, "rejected": 0}
    dataset.save()
    print(f"Checkpoint created: {chunk_size} rows processed, 1 chunk committed (last heartbeat 200s ago).")

    # 3. Simulate Worker Crash: task ID is now unknown/lost, status is still PROCESSING
    print("Simulating native worker crash (SIGSEGV / WorkerLost)...")
    # Call recovery watchdog
    recovered = check_and_recover_dataset(dataset)
    print(f"Watchdog response: {recovered}")
    dataset.refresh_from_db()
    print(f"Dataset status after watchdog: {dataset.status}, retry_count: {dataset.retry_count}, new_task_id: {dataset.current_task_id}")
    assert dataset.status in [Dataset.Status.RETRYING, Dataset.Status.PROCESSING]
    assert dataset.retry_count == 1

    # 4. Wait for Celery worker to resume and finish the remaining rows (11 to 25)
    print("Waiting for live Celery worker to resume from chunk 1 checkpoint...")
    max_wait = 40
    start = time.time()
    while time.time() - start < max_wait:
        dataset.refresh_from_db()
        print(f"  [T+{int(time.time()-start)}s] Status: {dataset.status}, Processed: {dataset.processed_rows}/{dataset.total_rows}, Chunks: {dataset.chunks_processed}")
        if dataset.status == Dataset.Status.COMPLETED:
            break
        time.sleep(2)

    dataset.refresh_from_db()
    print(f"Final status: {dataset.status}")
    print(f"Final processed rows: {dataset.processed_rows}")
    print(f"Final quality summary: {dataset.quality_summary}")
    assert dataset.status == Dataset.Status.COMPLETED, f"Expected completed, got {dataset.status}"
    assert dataset.processed_rows == 25, f"Expected 25 processed rows, got {dataset.processed_rows}"

    # 5. Verify NO duplicates
    incidents = Incident.objects.filter(dataset=dataset)
    print(f"Total Incidents for dataset: {incidents.count()}")
    assert incidents.count() == 25, f"Expected exactly 25 incidents, got {incidents.count()}"

    preds = PredictionResult.objects.filter(incident__dataset=dataset)
    print(f"Total Predictions for dataset: {preds.count()}")
    assert preds.count() == 25, f"Expected exactly 25 predictions, got {preds.count()}"

    ext_ids = set(incidents.values_list("external_id", flat=True))
    assert len(ext_ids) == 25
    print("All 25 external IDs are unique and present!")
    print("=== LIVE 25-ROW TEST PASSED PERFECTLY! ===")

if __name__ == "__main__":
    run_live_25_row_test()
