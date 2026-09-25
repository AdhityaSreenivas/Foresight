from django.contrib import admin
from .models import Organization, Site, Report, Prediction


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "organization",
        "location",
        "created_at",
    )


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "site",
        "activity_type",
        "created_by",
        "created_at",
    )


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "report",
        "classification",
        "is_sif",
        "confidence",
        "life_saving_rule",
        "created_at",
    )