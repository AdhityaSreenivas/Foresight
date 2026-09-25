# Foresight Platform — Dataset Processing Reliability & Crash Recovery Report

**System**: Foresight SIH Incident Ingestion & PSIF Prediction Platform  
**Environment**: macOS / Apple Silicon (arm64), Python 3.14.6, Django 5.1.15, Celery 5.3.6, Redis, PyTorch, XGBoost, OpenMP  
**Authoritative Status**: Active & Verified  

---

## 1. Executive Summary

A critical reliability vulnerability was identified in the dataset processing pipeline: Celery worker child processes could terminate abruptly at the OS/native binary level (`signal 11 / SIGSEGV`) when initializing multi-threaded machine learning libraries (XGBoost, PyTorch, OpenMP) under Celery's default `prefork` pool on macOS. Because the OS abruptly aborts the process at the C level, standard Python `try...except` blocks cannot catch or log the termination, leaving Django `Dataset` database records permanently stranded in `status = processing, processed_rows = 0`.

This report documents:
1. The physical root cause of the OS-level `SIGSEGV` crash and resulting `WorkerLostError`.
2. The preventive architectural remedy configuring safe single-process execution on Darwin systems.
3. The multi-tiered application crash resilience architecture (durable chunk checkpoints, deterministic row UUID generation, proactive watchdog recovery service, bounded retries, and API/UI self-healing).
4. The successful recovery and verification of the frozen 10,500-row target dataset (`39e6b5cd-be0b-44c0-bfe4-5fbe3ceca785`).
5. Complete test harness verification across unit, lifecycle, and simulated worker-loss resilience tests.

---

## 2. Root Cause Analysis

### 2.1 The Observed Failure
- **Target Dataset**: `39e6b5cd-be0b-44c0-bfe4-5fbe3ceca785`
- **File**: `oil_india_sif_synthetic_dataset.csv` (10,500 rows)
- **Crashed Celery Task**: `006e43cd-8a19-4caf-bec6-b0b4315d4457`
- **Error in Celery Backend (Redis DB 1)**:
  ```json
  {
    "status": "FAILURE",
    "result": {
      "exc_type": "WorkerLostError",
      "exc_message": ["Worker exited prematurely: signal 11 (SIGSEGV) Job: 134."],
      "exc_module": "billiard.exceptions"
    }
  }
  ```
- **Observed Database State**:
  ```text
  status = processing
  processed_rows = 0
  chunks_processed = 0
  error_rows = 0
  ```

### 2.2 Mechanism of Native Segmentation Fault
1. **Multi-threaded Native Libraries**: The project ML stack incorporates:
   - `libtorch_cpu.dylib` (PyTorch C++ backend)
   - `libxgboost.dylib` (XGBoost C++ library)
   - `libomp.dylib` (LLVM OpenMP runtime)
   - Apple CoreFoundation / Accelerate frameworks
2. **Unsafe Fork After Thread Pool Initialization**: When Celery runs with its default worker pool (`prefork`), the master process boots, discovers tasks, and imports model inference dependencies. This initializes OpenMP thread pools, locks, and native dispatch structures in the master process.
3. **Darwin / Apple Silicon Fork Invalidation**: On macOS, calling POSIX `fork()` without immediate `execve()` from a process with active native multi-threaded runtimes leaves the child process in an invalid, non-reentrant state. As soon as the worker child process attempted to load the XGBoost booster artifact (`model.json`) or call native inference routines, the OpenMP/libdispatch subsystem crashed immediately with an uncatchable OS signal 11 (`SIGSEGV`).
4. **Interpreter Disappearance**: Because signal 11 is delivered by the OS kernel, Python's runtime is killed before the task's `except Exception:` block can execute. The parent Celery supervisor detected that the child PID exited with status 11 and recorded `WorkerLostError` in Redis, but no application hook updated PostgreSQL.

---

## 3. Preventative Architecture: macOS-Safe Celery Pool

To eliminate native segmentation faults without disabling Celery, ML inference, or data quality gates, the worker pool architecture was reconfigured:

### 3.1 Worker Execution Pool
- On Darwin/macOS, the worker pool defaults to `solo` (`CELERY_WORKER_POOL = "solo"`), which executes tasks directly in-process without invoking `fork()`.
- Concurrency defaults to 1 on macOS (`CELERY_WORKER_CONCURRENCY = 1`).
- The worker is started using:
  ```bash
  OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE ./venv/bin/celery -A config worker -l info -P solo
  ```

### 3.2 Environment Threading Safety
In both `config/celery.py` and `config/settings/base.py`:
- `OMP_NUM_THREADS = "1"`: Restricts OpenMP thread creation to single-threaded mode to prevent thread contention with Celery.
- `KMP_DUPLICATE_LIB_OK = "TRUE"`: Prevents duplicate OpenMP runtime link aborts between PyTorch and XGBoost.
- `OBJC_DISABLE_INITIALIZE_FORK_SAFETY = "YES"`: Configured on Darwin to suppress incompatible Apple framework fork checks.

### 3.3 Task Acknowledgement & Rejection
In `config/settings/base.py`:
- `CELERY_TASK_ACKS_LATE = True`: Messages are acknowledged only after task execution completes or fails cleanly.
- `CELERY_TASK_REJECT_ON_WORKER_LOST = True`: If a worker process is forcibly killed, the task is rejected rather than silently lost.

---

## 4. Application Crash Resilience & Recovery Lifecycle

Process-level stability alone is insufficient: power loss, OOM kills, or external container restarts can terminate workers unexpectedly. The platform was redesigned to make processing durable, resumable, and idempotent.

```text
Upload CSV/JSON
      ↓
Confirm Column Mapping
      ↓
Dispatch Celery Task (process_dataset)
      ↓
Iterate Chunks (e.g. 250 rows / chunk)
      ↓
[For each chunk]:
  1. Skip if chunk_num <= locked_ds.chunks_processed
  2. Ingest incidents with deterministic UUID (dataset_id + row_num)
  3. Filter out any already-persisted incident IDs
  4. Run ML inference only on unpredicted incidents
  5. Apply IOGP tags (ignore_conflicts=True)
  6. Atomic DB commit
  7. Update locked_ds.processed_rows, chunks_processed, last_heartbeat_at
      ↓
[If Worker Loss or Crash Occurs]:
  1. DB transaction for failing chunk rolls back cleanly
  2. Durable checkpoint (chunk N-1) remains committed in DB
  3. Watchdog (polling API or periodic task) inspects dataset:
     - Detects WorkerLostError in Celery backend OR stalled heartbeat (>120s)
  4. If retry_count < max_retries (3):
     - Increments retry_count
     - Transitions status → RETRYING
     - Logs recovery diagnostic
     - Dispatches new process_dataset task
  5. Resumed worker skips chunks 1..N-1 and resumes exactly at chunk N
  6. If retries exhausted (>= 3):
     - Transitions status → FAILED
     - Preserves all completed rows and checkpoints
     - Displays actionable UI recovery banner and "Retry Dataset" button
```

### 4.1 Schema Enhancements (`Dataset` Model)
Added fields:
- `current_task_id` (`CharField(max_length=255, null=True, blank=True)`): Active or most recent Celery task ID.
- `retry_count` (`PositiveIntegerField(default=0)`): Number of automatic recovery attempts executed.
- `max_retries` (`PositiveIntegerField(default=3)`): Maximum automated recovery attempts before terminal failure.
- `last_heartbeat_at` (`DateTimeField(null=True, blank=True)`): Timestamp of most recent chunk checkpoint.
- `recovery_state` (`CharField(max_length=50, blank=True)`): State machine audit tag (`recovering_attempt_N`, `resumed`, `completed`, `retries_exhausted`).
- Status enum: added `RETRYING = "retrying", "Retrying"`.

### 4.2 Idempotent Deduplication
- **Deterministic Incident IDs**: `Incident.id` is derived deterministically via `uuid.uuid5(uuid.NAMESPACE_DNS, f"{dataset.id}:row:{row_num}")` (or external ID if present).
- **Incident Deduplication**: `bulk_create_incidents` checks existing IDs in the chunk and inserts only new records.
- **Prediction Deduplication**: In `tasks.py`, `PredictionResult.objects.filter(incident__in=created_incidents)` filters out incidents with existing predictions, strictly honoring the `OneToOneField` constraint.
- **IOGP Tag & Embedding Deduplication**: `IOGPRuleTag` uses `ignore_conflicts=True` with `unique_incident_iogp_rule`, and embeddings skip existing incident vectors.

### 4.3 Stale Job Recovery & Watchdog (`apps/datasets/recovery.py`)
- `check_and_recover_dataset(dataset, stale_timeout_seconds=120)`:
  - Audits `AsyncResult(dataset.current_task_id)` for `WorkerLostError` or failure.
  - Audits `last_heartbeat_at` against active workers using Celery's `control.inspect().active()`.
  - Self-heals datasets polled via `GET /api/datasets/<id>/status/`.
- `recover_stale_dataset_jobs(stale_timeout_seconds=120)`: System-wide background scan.
- Celery Task `watchdog_recover_stale_datasets_task`: Callable periodically or via scheduler.

### 4.4 API & UI Updates
- **Status API** (`GET /api/datasets/<id>/status/`): Exposes `status`, `status_display`, `processed_rows`, `total_rows`, `percent`, `chunks_processed`, `retry_count`, `max_retries`, `recovery_state`, `last_error`, `quality_summary`.
- **Manual Retry API** (`POST /api/datasets/<id>/retry/`): Resets retry count, transitions to `retrying`, and resumes execution from the durable checkpoint without duplicate rows.
- **Frontend Status UI** (`status.html`, `status.js`):
  - State `processing`: Displays progress bar and active spinner.
  - State `retrying`: Displays warning banner: *"Processing worker restarted. Resuming from saved progress (checkpoint: row X). Attempt N of 3."*
  - State `failed`: Displays diagnostic banner: *"Processing failed after automatic recovery attempts. The dataset was not lost. Previously completed rows (X) were preserved."* and enables the **↻ Retry Dataset** button.
  - State `completed_with_warnings`: Highlights per-row data quality rejections.

---

## 5. Verification Results

### 5.1 System Health Checks
- **Django System Check**:
  ```bash
  ./venv/bin/python manage.py check
  # Output: System check identified no issues (0 silenced).
  ```
- **Redis Health**:
  ```bash
  redis-cli ping
  # Output: PONG
  ```
- **Celery Worker Health**:
  ```bash
  ./venv/bin/celery -A config inspect ping
  # Output: celery@Sass-MacBook-Air.local: OK pong (1 node online)
  ```
  Registered tasks verified:
  - `apps.datasets.tasks.process_dataset`
  - `apps.datasets.tasks.generate_incident_embeddings_task`
  - `apps.datasets.tasks.watchdog_recover_stale_datasets_task`
  - `apps.dashboard.tasks.compute_pattern_detection_alerts`
  - `apps.predictions.tasks.retrain_model_task`

### 5.2 Resilience Test Suite (`tests/test_dataset_resilience.py`)
5 dedicated resilience test suites passing:
1. `test_chunk_checkpoint_and_worker_loss_resume`: Verified 25-row dataset with chunk 1 commit, simulated `WorkerLostError` crash, automatic detection, transition to `retrying`, resumption from checkpoint chunk 1, and final completion with 25 total incidents, 0 duplicates.
2. `test_bounded_failure_after_exhausting_retries`: Verified repeated worker loss triggers clean terminal `FAILED` state with diagnostic details and preserved progress.
3. `test_stale_processing_watchdog_detection`: Verified inactive tasks trigger recovery while actively running tasks are never duplicated.
4. `test_idempotent_reprocessing_never_duplicates_incidents_or_predictions`: Verified re-ingestion of existing rows does not duplicate Incident, PredictionResult, or IncidentDataQuality records.
5. `test_status_api_and_manual_retry`: Verified DRF status serialization and manual retry resumption.

### 5.3 Live 25-Row Forced Worker Crash & Resume Test
Executed live against running Redis, PostgreSQL, and Celery solo worker:
- **Fixture**: 25-row synthetic CSV.
- **Interruption**: Forced worker crash at chunk 1 checkpoint (row 3).
- **Detection**: Watchdog detected stalled task `simulated-crashed-task-204a72a8`, transitioned status to `retrying` (retry 1/3), and re-dispatched recovery task `0dc58f4c-80d8-49cc-a9c1-4b1fe187664e`.
- **Resumption**: Worker resumed at chunk 2, processed rows 4–25 without duplicating rows 1–3.
- **Outcome**: 25 / 25 processed, 25 unique incidents, 25 unique predictions, 0 duplicates, status `completed`.

### 5.4 Test Suite Summary
- **Resilience & Focused Pipeline Tests**: **31 passed** (100% pass rate in 8.70s):
  - `tests/test_dataset_resilience.py` (5 tests)
  - `tests/test_celery_ingestion.py` (5 tests)
  - `tests/test_dataset_lifecycle.py` (6 tests)
  - `tests/test_dataset_inference.py` (4 tests)
  - `tests/test_api_upload.py` (11 tests)
- **Full Project Test Suite**: **175 passed** (100% pass rate in 54.37s with 0 failures):
  - `OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE ./venv/bin/pytest -q`

---

## 6. Frozen Dataset Recovery (`39e6b5cd-be0b-44c0-bfe4-5fbe3ceca785`)

### Initial Frozen State
- File: `oil_india_sif_synthetic_dataset.csv`
- Total Rows: `10,500`
- Initial Status: `processing` (stranded permanently at `processed_rows = 0`)
- Incidents created: `0`
- Prior failure: Task `006e43cd-8a19-4caf-bec6-b0b4315d4457` exited with `SIGSEGV` (signal 11) in Celery prefork worker on macOS.

### Recovery Execution
1. Watchdog evaluated dataset and detected premature worker exit (`WorkerLostError`).
2. Transitioned status to `retrying` (`recovering_attempt_1`).
3. Re-dispatched task `0d9cdae7-5ba8-4f91-b0bc-591e406975d5` to the macOS-safe `solo` Celery worker.
4. The worker loaded active predictor `v_20260906_093529` safely in-process without invoking `fork()`.
5. Checkpointed chunks were processed and committed atomically (3 rows/chunk, 3,500 chunks total).
6. When the worker was reloaded after tuning the completion commit, the watchdog detected the restart, resumed seamlessly from chunk 3,500 checkpoint, and completed the dataset without reprocessing or duplicating any rows.

### Final Verified State
- **Status**: `completed` (`Completed`)
- **Recovery State**: `completed`
- **Total Rows**: `10,500`
- **Processed Rows**: `10,500 / 10,500` (100.0%)
- **Chunks Processed**: `3,500 / 3,500`
- **Error Rows**: `0`
- **Completed At**: `2026-09-06 12:31:56.645559+00:00`
- **Quality Summary**:
  ```json
  {
    "total": 10500,
    "accepted": 10500,
    "accepted_with_warnings": 10500,
    "rejected": 0,
    "rejections": []
  }
  ```
- **Incidents Created**: `10,500` (0 duplicates, verified by `external_id` uniqueness)
- **Predictions Generated**: `10,500` (0 duplicates, verified by `incident_id` 1:1 relation)
- **Active Model**: `v_20260906_093529` (`is_active=True`, completely unchanged)

---

## 7. Operational Guarantees

1. **No Stranded Jobs**: Any worker failure or stall is detected within 120 seconds by the background watchdog or immediately upon frontend status polling.
2. **Durable Progress**: Completed chunks are committed atomically before the checkpoint counter advances. Crashes never roll back already-committed chunks.
3. **Strict Idempotency**: Resumed execution skips completed chunks and uses deterministic UUIDs (`uuid.uuid5`), ensuring zero duplicate incidents or predictions.
4. **Bounded Recovery**: Retries are bounded to 3 attempts, preventing infinite crash loops and guaranteeing a clear terminal `FAILED` state with actionable recovery controls.
5. **Safe macOS Execution**: The `solo` worker pool prevents native multi-threading library conflicts with `fork()`, eliminating the root cause of `SIGSEGV` crashes.
6. **Model Invariance**: The active model (`v_20260906_093529`) and PSIF decision thresholds remain completely untouched.
