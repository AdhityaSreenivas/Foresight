from django.contrib import admin
from .models import ModelVersion, PredictionResult


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ["version_label", "bert_model_name", "is_active", "trained_at"]
    list_filter = ["is_active"]
    readonly_fields = ["id", "trained_at"]
    actions = ["activate_version"]

    @admin.action(description="Activate selected model version")
    def activate_version(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one version to activate.", level="error")
            return
        queryset.first().activate()
        self.message_user(request, "Model version activated.")


@admin.register(PredictionResult)
class PredictionResultAdmin(admin.ModelAdmin):
    list_display = ["incident", "risk_level", "psif_probability", "psif_predicted", "model_version", "created_at"]
    list_filter = ["risk_level", "psif_predicted", "model_version"]
    readonly_fields = ["id", "created_at"]
