from django.db import models
from django.contrib.auth.models import User


class Organization(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Site(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="sites"
    )
    name = models.CharField(max_length=255)
    location = models.CharField(
        max_length=255,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Report(models.Model):
    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="reports"
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    text = models.TextField()

    activity_type = models.CharField(
        max_length=100,
        blank=True
    )

    source_file = models.FileField(
        upload_to="reports/",
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Report {self.id}"


class Prediction(models.Model):
    report = models.OneToOneField(
        Report,
        on_delete=models.CASCADE,
        related_name="prediction"
    )

    classification = models.CharField(
        max_length=50
    )

    is_sif = models.BooleanField(
        default=False
    )

    confidence = models.FloatField()

    life_saving_rule = models.CharField(
        max_length=100,
        blank=True
    )

    evidence_data = models.JSONField(
        default=list,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Prediction for Report {self.report.id}"

class SafetyReport(models.Model):
    report_text = models.TextField()
    classification = models.CharField(max_length=50)
    is_sif = models.BooleanField(default=False)
    confidence = models.FloatField(default=0.0)
    sif_probability = models.FloatField(default=0.0)
    non_sif_probability = models.FloatField(default=0.0)
    risk_level = models.CharField(max_length=50, default="LOW")
    life_saving_rule = models.CharField(max_length=150, blank=True, default="Unclassified")
    lsr_probability = models.FloatField(default=0.0)
    lsr_source = models.CharField(max_length=20, default="ml")
    activity = models.CharField(max_length=150, blank=True, default="General Operations")
    activity_probability = models.FloatField(default=0.0)
    site_area = models.CharField(max_length=150, blank=True, default="")
    precursors = models.JSONField(default=list, blank=True)
    evidence = models.JSONField(default=list, blank=True)
    barrier_failures = models.JSONField(default=list, blank=True)
    reason = models.TextField(blank=True, default="")
    potential_consequence = models.TextField(blank=True, default="")
    recommended_measures = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SafetyReport {self.id} - {self.classification}"
