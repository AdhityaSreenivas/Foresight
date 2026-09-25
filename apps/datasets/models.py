"""
PSIF Platform — datasets app models

Dataset represents a single uploaded file (CSV, JSON, JSONL).
It tracks the ingestion lifecycle: upload → column mapping → processing → complete/failed.

ER relationships:
    Dataset 1──N Incident 1──1 PredictionResult N──1 ModelVersion
"""
import uuid
from django.db import models
from django.conf import settings


def dataset_upload_path(instance, filename: str) -> str:
    """Store uploaded files under media/uploads/<dataset_uuid>/<original_filename>."""
    return f"uploads/{instance.id}/{filename}"


class Dataset(models.Model):
    """
    Represents a single uploaded incident data file.

    Lifecycle:
        uploaded        → file saved, preview parsed (synchronous)
        mapping_pending → waiting for user to confirm column mapping
        processing      → Celery batch tasks running
        completed       → all rows ingested and predicted
        failed          → unrecoverable error (see error_log)
    """

    class FileType(models.TextChoices):
        CSV = "csv", "CSV"
        JSON = "json", "JSON"
        JSONL = "jsonl", "JSON Lines"

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        MAPPING_PENDING = "mapping_pending", "Awaiting Column Mapping"
        PROCESSING = "processing", "Processing"
        RETRYING = "retrying", "Retrying"
        CANCEL_REQUESTED = "cancel_requested", "Cancellation Requested"
        CANCELED = "canceled", "Canceled"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class SourceProvenance(models.TextChoices):
        SYNTHETIC = "SYNTHETIC", "Synthetic"
        HUMAN_APPROVED_SYNTHETIC = "HUMAN_APPROVED_SYNTHETIC", "Human-Approved Synthetic"
        REAL_EXTERNAL = "REAL_EXTERNAL", "Real External"
        REAL_HUMAN = "REAL_HUMAN", "Real Human"

    class LabelSemantics(models.TextChoices):
        SYNTHETIC_GENERATED_LABEL = "SYNTHETIC_GENERATED_LABEL", "Synthetic Generated Label"
        HUMAN_ADJUDICATED_ON_SYNTHETIC = "HUMAN_ADJUDICATED_ON_SYNTHETIC_RECORD", "Human Adjudicated on Synthetic Record"
        UNLABELED = "UNLABELED", "Unlabeled"

    # Use UUID as primary key for external-facing IDs (avoids enumeration attacks)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(
        max_length=255,
        help_text="Human-readable name for this dataset (auto-filled from filename).",
    )
    dataset_version = models.CharField(
        max_length=50,
        default="1.0",
        help_text="Dataset version identifier.",
    )
    source_provenance = models.CharField(
        max_length=50,
        choices=SourceProvenance.choices,
        default=SourceProvenance.SYNTHETIC,
        help_text="Origin of the records in this dataset.",
    )
    label_semantics = models.CharField(
        max_length=100,
        choices=LabelSemantics.choices,
        default=LabelSemantics.SYNTHETIC_GENERATED_LABEL,
        help_text="Semantics of the target labels in this dataset.",
    )
    is_synthetic = models.BooleanField(
        default=True,
        help_text="True if this dataset contains artificially generated records.",
    )
    quality_version = models.CharField(
        max_length=50,
        default="1.0",
        help_text="Data quality rule version used during screening.",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="datasets",
        help_text="User who uploaded the file.",
    )
    workspace_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default=None,
        db_index=True,
        help_text="Workspace isolation identifier. NULL for existing global dataset; 'admin_flow' for Admin Flow demo.",
    )
    original_file = models.FileField(
        upload_to=dataset_upload_path,
        help_text="The original uploaded file, stored under media/uploads/.",
    )
    file_type = models.CharField(
        max_length=10,
        choices=FileType.choices,
        help_text="Detected file format.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
        db_index=True,
    )

    # Column mapping: source column name → canonical Incident field name.
    # e.g. {"Incident Description": "description", "Dept": "department", ...}
    # Populated after the user confirms the mapping in the UI.
    column_mapping = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Maps source column names to canonical Incident schema field names. "
            "Set after user confirms the column-mapping step."
        ),
    )

    # Progress tracking
    total_rows = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total number of data rows in the file (estimated from header scan).",
    )
    processed_rows = models.PositiveIntegerField(
        default=0,
        help_text="Number of rows successfully ingested and predicted so far.",
    )
    chunks_processed = models.PositiveIntegerField(
        default=0,
        help_text="Number of file chunks completely processed (for idempotency and resumes).",
    )
    error_rows = models.PositiveIntegerField(
        default=0,
        help_text="Cumulative number of skipped or errored rows across all processed chunks.",
    )

    # Recovery & worker-loss tracking
    current_task_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Active or most recent Celery task ID executing processing.",
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of automatic retry attempts following worker loss or unexpected failure.",
    )
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Maximum allowed automatic recovery retries before transitioning to terminal FAILED.",
    )
    last_heartbeat_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent chunk checkpoint or heartbeat during processing.",
    )
    recovery_state = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="State machine tag for recovery lifecycle (e.g. 'recovering', 'worker_lost_detected', 'resumed').",
    )

    # Error reporting
    error_log = models.TextField(
        blank=True,
        null=True,
        help_text=(
            "Log of non-fatal errors (skipped rows, encoding issues, etc.). "
            "If status=failed, contains the fatal error that halted processing."
        ),
    )

    # Data quality summary & audit of rejected rows
    quality_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Summary of data quality screening (accepted, warning, rejected counts and rejection details).",
    )

    # Timestamps & Timing Durations
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When processing finished (successfully or with failure).",
    )
    processing_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when asynchronous dataset processing started.",
    )
    processing_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when dataset processing reached a terminal state.",
    )
    processing_duration_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Total elapsed processing duration in seconds once completed or failed.",
    )
    upload_duration_seconds = models.FloatField(
        null=True,
        blank=True,
        help_text="Time taken in seconds to transfer raw file to server storage.",
    )
    cancel_requested = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Flag set when cooperative cancellation is requested for an active processing job.",
    )
    canceled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when cooperative processing cancellation was finalized.",
    )

    class Meta:
        verbose_name = "dataset"
        verbose_name_plural = "datasets"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} [{self.get_status_display()}]"

    @property
    def percent_complete(self) -> float:
        """Processing completion percentage (0–100)."""
        if not self.total_rows:
            return 0.0
        return round((self.processed_rows / self.total_rows) * 100, 1)

    @property
    def processing_elapsed_seconds(self):
        """Derive elapsed processing duration in seconds."""
        from .timing import calculate_dataset_timing
        return calculate_dataset_timing(self).get("elapsed_seconds")

    @property
    def formatted_duration(self) -> str:
        """Human-readable processing duration or status summary."""
        from .timing import calculate_dataset_timing
        return calculate_dataset_timing(self).get("summary", "")

    @property
    def get_timing_info(self) -> dict:
        """Return full timing metrics, throughput, and predictive ETA."""
        from .timing import calculate_dataset_timing
        return calculate_dataset_timing(self)

    @property
    def psif_count(self) -> int:
        """Total incidents in this dataset classified as PSIF Candidate."""
        if isinstance(self.quality_summary, dict) and "psif_count" in self.quality_summary:
            return self.quality_summary["psif_count"]
        return self.incidents.filter(prediction__psif_predicted=True).count()

    @property
    def non_psif_count(self) -> int:
        """Total incidents in this dataset classified as Non-PSIF."""
        if isinstance(self.quality_summary, dict) and "non_psif_count" in self.quality_summary:
            return self.quality_summary["non_psif_count"]
        return self.incidents.filter(prediction__psif_predicted=False).count()

    def append_error(self, message: str) -> None:
        """Append a line to the error log (non-destructive)."""
        if self.error_log:
            self.error_log = f"{self.error_log}\n{message}"
        else:
            self.error_log = message
