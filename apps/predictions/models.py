"""
PSIF Platform — predictions app models

ModelVersion   — versioned ML model artifacts + training metrics
PredictionResult — per-incident PSIF prediction output

ER relationships:
    Dataset 1──N Incident 1──1 PredictionResult N──1 ModelVersion

Risk level bands (defined here as class constants to serve as the single
source of truth — the same values must be used in serializers, views, and
frontend badge colouring).  The probability boundaries are loaded from settings
so they can be adjusted via environment variables without code changes.

    low:      [0,     RISK_LOW_MAX)    e.g. < 0.25
    medium:   [RISK_LOW_MAX, RISK_MEDIUM_MAX)   e.g. 0.25–0.50
    high:     [RISK_MEDIUM_MAX, RISK_HIGH_MAX)  e.g. 0.50–0.75
    critical: [RISK_HIGH_MAX, 1.0]              e.g. ≥ 0.75
"""
import uuid
from django.conf import settings
from django.db import models


def probability_to_risk_level(probability: float) -> str:
    """
    Map a PSIF probability (0–1) to a risk level string.

    This is the single, canonical implementation — imported by model_inference.py
    and used in serializers and templates.  The probability bands are read from
    settings.RISK_BANDS so they can be configured via .env.
    """
    bands = settings.RISK_BANDS
    if probability < bands["LOW_MAX"]:
        return PredictionResult.RiskLevel.LOW
    elif probability < bands["MEDIUM_MAX"]:
        return PredictionResult.RiskLevel.MEDIUM
    elif probability < bands["HIGH_MAX"]:
        return PredictionResult.RiskLevel.HIGH
    else:
        return PredictionResult.RiskLevel.CRITICAL


class ModelVersion(models.Model):
    """
    A trained, versioned XGBoost + BERT model combination.

    Artifacts are stored on disk (not as database blobs) under:
        ml_engine/artifacts/<version_label>/
            model.json          — XGBoost native format
            encoders.joblib     — fitted scikit-learn encoders
            metadata.json       — training metrics, feature list, dates

    Only one ModelVersion should have is_active=True at a time.
    The inference engine always loads the active version.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    version_label = models.CharField(
        max_length=100,
        unique=True,
        help_text='Unique version identifier, e.g. "v1.0" or "20240115_143022".',
    )
    bert_model_name = models.CharField(
        max_length=255,
        help_text="HuggingFace model name used as the text encoder (frozen).",
    )
    xgboost_artifact_path = models.CharField(
        max_length=500,
        help_text="Absolute or project-relative path to the XGBoost model.json file.",
    )
    encoder_artifact_path = models.CharField(
        max_length=500,
        help_text="Absolute or project-relative path to the fitted encoders.joblib file.",
    )

    trained_at = models.DateTimeField(auto_now_add=True)

    # Training metrics stored as a JSON blob, e.g.:
    # {
    #   "precision": 0.72, "recall": 0.88, "f2": 0.84,
    #   "roc_auc": 0.91,
    #   "confusion_matrix": [[tn, fp], [fn, tp]],
    #   "training_set_size": 750,
    #   "positive_class_count": 120,
    #   "negative_class_count": 630,
    #   "feature_list": ["bert_embedding_0", ..., "severity_potential_serious", ...]
    # }
    metrics = models.JSONField(
        default=dict,
        help_text="Training and validation metrics for this model version.",
    )

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        READY = "READY", "Ready"
        ACTIVE = "ACTIVE", "Active"
        FAILED = "FAILED", "Failed"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Lifecycle status of this model version.",
    )

    training_snapshot_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Path to the immutable training snapshot JSON artifact.",
    )

    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "Only one ModelVersion is active at a time. "
            "Active version is used for all new predictions."
        ),
    )

    class Meta:
        verbose_name = "model version"
        verbose_name_plural = "model versions"
        ordering = ["-trained_at"]

    def __str__(self) -> str:
        active_marker = " [ACTIVE]" if self.is_active else ""
        return f"ModelVersion {self.version_label} ({self.status}){active_marker}"

    def save(self, *args, **kwargs):
        if self.is_active:
            ModelVersion.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def activate(self) -> None:
        """
        Set this version as active, deactivating all others.
        Wrapped in a transaction for safety.
        """
        from django.db import transaction

        with transaction.atomic():
            ModelVersion.objects.filter(is_active=True).update(is_active=False, status=self.Status.READY)
            self.is_active = True
            self.status = self.Status.ACTIVE
            self.save(update_fields=["is_active", "status"])


class PredictionResult(models.Model):
    """
    The output of the ML pipeline for a single incident.

    One PredictionResult per Incident (one-to-one enforced at the DB level).
    Multiple predictions per incident are not stored — re-running inference
    replaces the existing result.

    top_factors stores the SHAP-derived explanation, e.g.:
    [
      {"feature": "severity_potential_serious", "contribution": 0.42},
      {"feature": "near_miss", "contribution": 0.28},
      {"feature": "narrative_content", "contribution": 0.18},
      ...
    ]
    The "narrative_content" entry aggregates SHAP values across all 768 BERT
    embedding dimensions — individual embedding dimensions are not
    human-interpretable and are not surfaced individually.
    """

    class RiskLevel(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    # ── Risk level colour mapping (used consistently in templates) ─────────────
    # Frontend badge CSS classes: risk-badge--low, risk-badge--medium, etc.
    RISK_LEVEL_COLORS = {
        RiskLevel.LOW: "#22c55e",       # green
        RiskLevel.MEDIUM: "#f59e0b",    # amber
        RiskLevel.HIGH: "#f97316",      # orange
        RiskLevel.CRITICAL: "#ef4444",  # red
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    incident = models.OneToOneField(
        "incidents.Incident",
        on_delete=models.CASCADE,
        related_name="prediction",
        help_text="The incident this prediction is for (one-to-one).",
    )
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.PROTECT,
        related_name="predictions",
        help_text="The model version that generated this prediction.",
    )

    # ── Prediction output ─────────────────────────────────────────────────────
    psif_probability = models.FloatField(
        help_text="PSIF probability output from XGBoost predict_proba (0–1).",
    )
    psif_predicted = models.BooleanField(
        help_text="True if psif_probability ≥ configured threshold (default 0.5).",
    )
    risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        db_index=True,
        help_text="[DEPRECATED LEGACY BAND] Derived from psif_probability using legacy risk band thresholds.",
    )

    # ── Explainability & Binary SIF Evidence ──────────────────────────────────
    evidence_strength = models.CharField(
        max_length=20,
        default="Moderate",
        help_text="Categorical evidence strength: Strong, Moderate, or Weak.",
    )
    explanation_detail = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full SIF explanation payload: energy source, exposure, control failure, mechanism, quotes, missing info.",
    )

    # Top ~5 contributing factors, ordered by |contribution| descending.
    top_factors = models.JSONField(
        default=list,
        help_text=(
            "SHAP-derived top contributing features for this prediction. "
            "Each entry: {feature: str, contribution: float}. "
            "BERT embedding dimensions are aggregated as 'narrative_content'."
        ),
    )

    is_sparse_input = models.BooleanField(
        default=False,
        help_text="True if the input narrative was extremely sparse/empty, meaning the score may be uninformative."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def psif_score(self) -> float:
        """PSIF Model Score (0.0 - 1.0). Not a calibrated real-world injury probability."""
        return self.psif_probability

    @property
    def binary_classification(self) -> str:
        """Primary binary classification: 'PSIF' or 'NOT PSIF'."""
        return "PSIF" if self.psif_predicted else "NOT PSIF"

    @property
    def psif_probability_percent(self) -> float:
        """Returns the psif_probability formatted as a percentage (0-100)."""
        if self.psif_probability is None:
            return 0.0
        return self.psif_probability * 100

    class Meta:
        verbose_name = "prediction result"
        verbose_name_plural = "prediction results"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["psif_predicted", "psif_probability"]),
            models.Index(fields=["is_sparse_input"]),
            models.Index(fields=["evidence_strength"]),
            models.Index(fields=["-psif_probability"]),
            models.Index(fields=["model_version"]),
        ]

    def __str__(self) -> str:
        return (
            f"Prediction for {self.incident_id} | "
            f"{self.binary_classification} | "
            f"score={self.psif_score:.3f} | "
            f"strength={self.evidence_strength}"
        )
