from django.contrib import admin
from .models import Dataset


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ["name", "uploaded_by", "file_type", "status", "total_rows", "processed_rows", "created_at"]
    list_filter = ["status", "file_type"]
    search_fields = ["name"]
    readonly_fields = ["id", "created_at", "completed_at", "processed_rows", "percent_complete"]

    def percent_complete(self, obj):
        return f"{obj.percent_complete}%"
    percent_complete.short_description = "% Complete"
