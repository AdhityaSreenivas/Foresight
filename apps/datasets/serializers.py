"""
PSIF Platform — Dataset DRF Serializers
"""
import os
from django.conf import settings
from rest_framework import serializers

from .models import Dataset
from .column_mapping import validate_column_mapping


class DatasetListSerializer(serializers.ModelSerializer):
    """Compact serializer for dataset list views."""
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username", read_only=True, default=None
    )
    percent_complete = serializers.FloatField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    timing_summary = serializers.CharField(source="formatted_duration", read_only=True)
    timing = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = [
            "id", "name", "file_type", "status", "status_display",
            "source_provenance", "label_semantics", "is_synthetic",
            "dataset_version", "quality_version",
            "total_rows", "processed_rows", "percent_complete",
            "uploaded_by_username", "created_at", "completed_at",
            "processing_started_at", "processing_completed_at",
            "processing_duration_seconds", "upload_duration_seconds",
            "cancel_requested", "canceled_at",
            "timing_summary", "timing",
        ]
        read_only_fields = fields

    def get_timing(self, obj) -> dict:
        from .timing import calculate_dataset_timing
        return calculate_dataset_timing(obj)


class DatasetStatusSerializer(serializers.ModelSerializer):
    """Serializer for the /status/ polling endpoint with recovery diagnostics and ETA timing."""
    percent = serializers.FloatField(source="percent_complete", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    last_error = serializers.SerializerMethodField()
    psif_count = serializers.IntegerField(read_only=True)
    non_psif_count = serializers.IntegerField(read_only=True)
    timing = serializers.SerializerMethodField()

    class Meta:
        model = Dataset
        fields = [
            "status", "status_display", "processed_rows", "total_rows", "percent",
            "chunks_processed", "retry_count", "max_retries", "recovery_state",
            "last_error", "error_log", "quality_summary",
            "psif_count", "non_psif_count",
            "processing_started_at", "processing_completed_at",
            "processing_duration_seconds", "upload_duration_seconds",
            "cancel_requested", "canceled_at",
            "timing",
        ]
        read_only_fields = fields

    def get_timing(self, obj) -> dict:
        from .timing import calculate_dataset_timing
        return calculate_dataset_timing(obj)

    def get_last_error(self, obj) -> str:
        """Sanitized user-facing error message (last error line or diagnostic)."""
        if not obj.error_log:
            return ""
        # Find the last informative non-stacktrace line
        lines = [line.strip() for line in obj.error_log.strip().splitlines() if line.strip()]
        for line in reversed(lines):
            # Skip raw python traceback internals
            if line.startswith('File "') or line.startswith("Traceback (") or line.startswith("During handling"):
                continue
            return line[:300]
        return lines[-1][:300] if lines else ""


class DatasetUploadResponseSerializer(serializers.Serializer):
    """
    Response body returned immediately after a successful upload.
    Contains the dataset ID, preview data, and auto-suggested mapping.
    """
    dataset_id = serializers.UUIDField()
    name = serializers.CharField()
    file_type = serializers.CharField()
    status = serializers.CharField()
    total_rows = serializers.IntegerField(allow_null=True)
    columns = serializers.ListField(child=serializers.CharField())
    column_types = serializers.DictField(child=serializers.CharField())
    preview_rows = serializers.ListField(child=serializers.DictField())
    suggested_mapping = serializers.DictField(child=serializers.CharField(allow_blank=True))
    canonical_field_labels = serializers.DictField(child=serializers.CharField(), read_only=True)
    upload_duration_seconds = serializers.FloatField(required=False, allow_null=True)


class ColumnMappingSerializer(serializers.Serializer):
    """
    Request body for POST /api/datasets/<id>/column-mapping/
    Accepts {source_column: canonical_field_or_empty_string}.
    """
    column_mapping = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        help_text=(
            "Maps source column names to canonical Incident field names. "
            "Use an empty string to explicitly leave a column unmapped."
        ),
    )

    def validate_column_mapping(self, value: dict) -> dict:
        errors = validate_column_mapping(value)
        if errors:
            raise serializers.ValidationError(errors)
        return value


class ProcessDatasetSerializer(serializers.Serializer):
    """Response body for POST /api/datasets/<id>/process/"""
    dataset_id = serializers.UUIDField()
    status = serializers.CharField()
    task_id = serializers.CharField(allow_null=True)
    message = serializers.CharField()


class UploadFileValidator:
    """
    Validates an uploaded file before it is saved to disk.
    Checks: extension, content-type hint, and file size.
    Does NOT execute or evaluate uploaded content.
    """
    ALLOWED_EXTENSIONS = {".csv", ".json", ".jsonl"}
    MAX_SIZE_BYTES: int = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 250 * 1024 * 1024)

    def __call__(self, file):
        # Size check: dynamically resolve from settings, honoring explicit overrides (e.g. tests)
        configured_max = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", 250 * 1024 * 1024)
        max_bytes = self.MAX_SIZE_BYTES if self.MAX_SIZE_BYTES < configured_max else configured_max

        if file.size > max_bytes:
            max_mb = max_bytes // (1024 * 1024)
            raise serializers.ValidationError(
                f"File size {file.size // (1024*1024)}MB exceeds the maximum "
                f"allowed upload size of {max_mb}MB."
            )

        # Extension check
        _, ext = os.path.splitext(file.name)
        if ext.lower() not in self.ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"File type '{ext}' is not supported. "
                f"Allowed types: {sorted(self.ALLOWED_EXTENSIONS)}"
            )

        return file


class FileUploadSerializer(serializers.Serializer):
    """
    Request body for POST /api/datasets/upload/
    Only the 'file' field — no other client input is trusted.
    """
    file = serializers.FileField(
        validators=[UploadFileValidator()],
        help_text="CSV, JSON, or JSONL file to upload (max 250MB).",
    )
