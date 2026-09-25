from django.contrib import admin
from .models import Incident


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = [
        "id", "department", "incident_date", "severity_actual",
        "severity_potential", "near_miss", "is_synthetic", "psif_label_source", "created_at",
    ]
    list_filter = [
        "is_synthetic", "psif_label_source", "severity_actual", "severity_potential",
        "near_miss", "department",
    ]
    search_fields = ["description", "external_id", "department"]
    readonly_fields = ["id", "composite_narrative", "created_at", "is_synthetic", "psif_label_source"]

    fieldsets = [
        ("Source & Provenance", {"fields": ["id", "dataset", "external_id", "is_synthetic", "psif_label_source", "raw_row"]}),
        ("Incident Details", {
            "fields": [
                "incident_date", "department", "location", "job_task",
                "equipment_involved", "injury_type", "body_part",
                "immediate_cause", "root_cause_category",
            ],
        }),
        ("Severity", {
            "fields": ["severity_actual", "severity_potential", "near_miss"],
        }),
        ("Narrative", {
            "fields": ["description", "corrective_actions", "witness_statement", "composite_narrative"],
        }),
        ("HSE Review & Adjudication", {
            "description": (
                "Data Provenance indicates whether the incident is Synthetic or Human-Approved Synthetic. "
                "Human approval of synthetic incidents indicates human review of generated examples; "
                "it is not equivalent to validation against real-world OIL HSE records."
            ),
            "fields": [
                "is_psif_human_label",
                "adjudication_status",
                "adjudicated_human_decision",
                "adjudicated_by",
                "adjudicated_at",
                "adjudication_rationale",
            ],
        }),
        ("Metadata", {"fields": ["created_at"]}),
    ]
