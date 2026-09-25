"""
PSIF Platform — incidents app models

Incident is the central entity: one row per workplace incident report.

ER relationships:
    Dataset 1──N Incident 1──1 PredictionResult N──1 ModelVersion

┌──────────────────────────────────────────────────────────────────────────┐
│  DATA PROVENANCE & PSIF LABEL ARCHITECTURE                               │
│                                                                           │
│  1. SYNTHETIC: Artificial/generated incident records.                     │
│     Target label is provided by the synthetic benchmark dataset.          │
│     Labels are NOT real-world human ground truth.                         │
│                                                                           │
│  2. HUMAN_APPROVED_SYNTHETIC: Synthetic incident records that have been   │
│     independently reviewed and adjudicated by an HSE domain expert.      │
│     This is human-reviewed synthetic evidence, NOT real-world OIL        │
│     validation.                                                           │
│                                                                           │
│  Human decisions: PSIF, NOT_PSIF, or INSUFFICIENT_INFORMATION.             │
│  INSUFFICIENT_INFORMATION is strictly excluded from binary training.     │
│                                                                           │
│  Heuristic label concept is completely eliminated.                        │
└──────────────────────────────────────────────────────────────────────────┘
"""
import uuid
from django.conf import settings
from django.db import models


class Incident(models.Model):
    """
    Canonical representation of one workplace incident report.

    Structured fields capture the metadata captured by the EHS system.
    Free-text fields hold the narrative content.
    composite_narrative is the cleaned/combined text sent to the BERT encoder.
    raw_row stores the original source data verbatim for auditability.
    """

    # ── Severity choices ──────────────────────────────────────────────────────

    class SeverityActual(models.TextChoices):
        """What actually happened (recorded outcome)."""
        NONE = "none", "No Injury / Near Miss"
        FIRST_AID = "first_aid", "First Aid"
        MEDICAL_TREATMENT = "medical_treatment", "Medical Treatment"
        LOST_TIME = "lost_time", "Lost Time Injury"
        FATALITY = "fatality", "Fatality"

    class SeverityPotential(models.TextChoices):
        """Safety officer's assessed potential severity (what could have happened)."""
        LOW = "low", "Low"
        MODERATE = "moderate", "Moderate"
        SERIOUS = "serious", "Serious"
        FATALITY = "fatality", "Fatality"

    class PsifLabelSource(models.TextChoices):
        SYNTHETIC = "synthetic", "Synthetic"
        HUMAN_APPROVED_SYNTHETIC = "human_approved_synthetic", "Human-Approved Synthetic"
        REAL_EXTERNAL = "real_external", "Real External (Unlabeled)"
        REAL_HUMAN = "real_human", "Real Human"
        NONE = "none", "No Label Available"

    PsifLabelSource.HUMAN = PsifLabelSource.HUMAN_APPROVED_SYNTHETIC

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        REVIEWED_PSIF = "reviewed_psif", "Reviewed (PSIF)"
        REVIEWED_NON_PSIF = "reviewed_non_psif", "Reviewed (Non-PSIF)"

    # ── Report classification choices ─────────────────────────────────────────
    class ReportType(models.TextChoices):
        UNSAFE_ACT = "unsafe_act", "Unsafe Act"
        UNSAFE_CONDITION = "unsafe_condition", "Unsafe Condition"
        NEAR_MISS = "near_miss", "Near Miss"
        INCIDENT = "incident", "Incident / Event"

    # ── Safety Context & Control choices ──────────────────────────────────────
    class SafetyContextState(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        UNKNOWN = "unknown", "Unknown / Not Determined"

    class EnergyType(models.TextChoices):
        GRAVITY_HEIGHT = "gravity_height", "Gravity / Working at Height"
        ELECTRICAL = "electrical", "Electrical"
        MECHANICAL_MOTION = "mechanical_motion", "Mechanical Motion / Rotating Equipment"
        PRESSURE = "pressure", "Pressure / Stored Energy"
        CHEMICAL = "chemical", "Chemical / Toxic / Flammable"
        THERMAL = "thermal", "Thermal (Extreme Heat/Cold)"
        RADIATION = "radiation", "Radiation"
        SOUND = "sound", "Sound / Noise"
        MOTOR_VEHICLE = "motor_vehicle", "Motor Vehicle / Driving"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown / Not Determined"

    class ControlType(models.TextChoices):
        # Direct Controls (Engineered / Elimination / Physical)
        LOTO_ISOLATION = "loto_isolation", "LOTO / Energy Isolation (Direct)"
        MACHINE_GUARDING = "machine_guarding", "Machine Guarding / Interlocks (Direct)"
        PHYSICAL_BARRIER = "physical_barrier", "Physical Barrier / Exclusion Zone (Direct)"
        FALL_PROTECTION = "fall_protection", "Fall Protection / Harness / Railing (Direct)"
        PERMIT_ISOLATION = "permit_isolation", "Permit-Based Isolation / Hot Work Control (Direct)"
        VENTILATION_MONITORING = "ventilation_monitoring", "Ventilation / Atmospheric Monitoring (Direct)"
        # Indirect Controls (Administrative / Procedural / Human)
        TRAINING = "training", "Training / Competency (Indirect)"
        SIGNAGE = "signage", "Signage / Warnings (Indirect)"
        PPE = "ppe", "Personal Protective Equipment (Indirect)"
        RULES_PROCEDURES = "rules_procedures", "Rules / Safe Working Procedures (Indirect)"
        SUPERVISION = "supervision", "Supervision / Experience (Indirect)"
        OTHER = "other", "Other Control"
        UNKNOWN = "unknown", "Unknown / Not Determined"

    class ControlCondition(models.TextChoices):
        EFFECTIVE = "effective", "Effective / Held"
        FAILED = "failed", "Failed"
        ABSENT = "absent", "Absent / Not Implemented"
        BYPASSED = "bypassed", "Bypassed / Defeated"
        UNKNOWN = "unknown", "Unknown / Not Determined"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    # ── Dataset linkage ───────────────────────────────────────────────────────
    dataset = models.ForeignKey(
        "datasets.Dataset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents",
        help_text="Source dataset, if this incident was uploaded as part of a batch. "
                  "Null for manually-entered single incidents.",
    )

    # ── Workspace / Demo Scope Isolation ─────────────────────────────────────
    workspace_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default=None,
        db_index=True,
        help_text="Workspace isolation identifier. NULL for existing global dataset; 'admin_flow' for Admin Flow demo.",
    )

    # ── Source system identifiers ─────────────────────────────────────────────
    external_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        help_text="The incident ID from the source EHS system, if present.",
    )

    # ── Temporal ──────────────────────────────────────────────────────────────
    incident_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Date the incident occurred.",
    )

    # ── Location / context ────────────────────────────────────────────────────
    department = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    job_task = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Job task or activity being performed at the time of the incident.",
    )
    equipment_involved = models.CharField(max_length=255, blank=True, null=True)

    # ── Injury classification ─────────────────────────────────────────────────
    injury_type = models.CharField(max_length=255, blank=True, null=True)
    body_part = models.CharField(max_length=255, blank=True, null=True)

    # ── Causal factors ────────────────────────────────────────────────────────
    immediate_cause = models.CharField(max_length=255, blank=True, null=True)
    root_cause_category = models.CharField(max_length=255, blank=True, null=True)

    # ── Severity ──────────────────────────────────────────────────────────────
    severity_actual = models.CharField(
        max_length=30,
        choices=SeverityActual.choices,
        blank=True,
        null=True,
        db_index=True,
        help_text="Recorded outcome severity.",
    )
    severity_potential = models.CharField(
        max_length=30,
        choices=SeverityPotential.choices,
        blank=True,
        null=True,
        db_index=True,
        help_text="Safety officer's assessed potential severity.",
    )
    near_miss = models.BooleanField(
        null=True,
        blank=True,
        help_text="True if this was classified as a near-miss event.",
    )

    # ── Report classification ─────────────────────────────────────────────────
    report_type = models.CharField(
        max_length=30,
        choices=ReportType.choices,
        blank=True,
        null=True,
        db_index=True,
        help_text="Classification of the report (unsafe act, unsafe condition, near miss, incident).",
    )

    # ── Safety Context & Energy / Control fields ──────────────────────────────
    high_energy_present = models.CharField(
        max_length=10,
        choices=SafetyContextState.choices,
        default=SafetyContextState.UNKNOWN,
        blank=True,
        help_text="Presence of high energy hazard (gravity/height, pressure, electrical, etc.).",
    )
    energy_type = models.CharField(
        max_length=50,
        choices=EnergyType.choices,
        default=EnergyType.UNKNOWN,
        blank=True,
        help_text="Type of energy involved in the event or hazard.",
    )
    worker_exposed = models.CharField(
        max_length=10,
        choices=SafetyContextState.choices,
        default=SafetyContextState.UNKNOWN,
        blank=True,
        help_text="Whether a worker was in the line of fire or exposed to the energy source.",
    )
    direct_control_present = models.CharField(
        max_length=10,
        choices=SafetyContextState.choices,
        default=SafetyContextState.UNKNOWN,
        blank=True,
        help_text="Whether a direct control was present to mitigate the high-energy hazard.",
    )
    control_type = models.CharField(
        max_length=50,
        choices=ControlType.choices,
        default=ControlType.UNKNOWN,
        blank=True,
        help_text="Primary control type in place or required.",
    )
    control_condition = models.CharField(
        max_length=30,
        choices=ControlCondition.choices,
        default=ControlCondition.UNKNOWN,
        blank=True,
        help_text="Condition or performance of the control (effective, failed, absent, bypassed, unknown).",
    )
    control_failed_bypassed = models.BooleanField(
        null=True,
        blank=True,
        help_text="True if direct control condition was failed or bypassed.",
    )

    # ── Free-text narrative fields ────────────────────────────────────────────
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Main incident narrative / description.",
    )
    corrective_actions = models.TextField(
        blank=True,
        null=True,
        help_text="Corrective / preventive actions taken or planned.",
    )
    witness_statement = models.TextField(
        blank=True,
        null=True,
        help_text="Witness statement(s), if captured.",
    )

    # ── Composite narrative (BERT input) ──────────────────────────────────────
    composite_narrative = models.TextField(
        blank=True,
        null=True,
        help_text=(
            "Cleaned and combined text from all free-text fields, used as "
            "the input to the BERT encoder.  Generated at ingestion time. "
            "NOTE: BERT (distilbert-base-uncased) truncates at 512 tokens — "
            "very long narratives will be truncated.  A sliding-window or "
            "summarisation approach is a documented future improvement."
        ),
    )

    # ── Raw source row (audit trail) ──────────────────────────────────────────
    raw_row = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "The original source row exactly as it arrived, before any mapping "
            "or cleaning.  Stored verbatim for traceability and audit."
        ),
    )

    # ── PSIF labels & Provenance Architecture ─────────────────────────────────
    #
    # Architecture of Human Truth vs. Adjudication vs. Provenance:
    # 1. IncidentReview.decision (authoritative store for individual human reviews).
    # 2. Incident.adjudicated_human_decision (authoritative consensus/adjudicated decision:
    #    PSIF, NOT_PSIF, or INSUFFICIENT_INFORMATION).
    # 3. Incident.is_psif_human_label (synchronized binary boolean projection for
    #    backward compatibility with legacy test suites and analytics).
    # 4. is_synthetic (True if record is artificial/generated incident data).
    # 5. psif_label_source (exact provenance origin: SYNTHETIC, HUMAN_APPROVED_SYNTHETIC, etc.).
    #
    is_synthetic = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if this incident is artificially generated/synthetic data.",
    )
    is_psif_human_label = models.BooleanField(
        null=True,
        blank=True,
        help_text=(
            "[BACKWARD COMPATIBILITY] Binary boolean projection of adjudicated_human_decision "
            "(True for PSIF, False for NOT_PSIF, None for unreviewed or INSUFFICIENT_INFORMATION). "
            "Authoritative multi-reviewer decisions reside in IncidentReview and adjudicated_human_decision."
        ),
    )
    psif_label_source = models.CharField(
        max_length=35,
        choices=PsifLabelSource.choices,
        default=PsifLabelSource.NONE,
        db_index=True,
        help_text="Indicates the origin and reliability of the PSIF label on this incident.",
    )

    # ── Human review provenance ───────────────────────────────────────────────
    #
    # These three fields record who reviewed this incident, when, and why.
    # They are written by the PATCH /api/incidents/<id>/review/ endpoint.
    # They do NOT replace the original AI model result in PredictionResult.
    #
    reviewer_rationale = models.TextField(
        blank=True,
        null=True,
        help_text=(
            "Required when the human label overrides a prior model prediction "
            "or when confirming high-consequence edge cases."
        ),
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_reviews",
        help_text="The user who submitted the human PSIF review.",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the human PSIF review was submitted.",
    )

    # ── Adjudication & Consensus Tracking ────────────────────────────────────
    class AdjudicationStatus(models.TextChoices):
        UNREVIEWED = "UNREVIEWED", "Unreviewed"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        ADJUDICATED = "ADJUDICATED", "Adjudicated"

    class HumanDecision(models.TextChoices):
        PSIF = "PSIF", "PSIF"
        NOT_PSIF = "NOT_PSIF", "NOT PSIF"
        INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION", "Insufficient Information"

    adjudication_status = models.CharField(
        max_length=20,
        choices=AdjudicationStatus.choices,
        default=AdjudicationStatus.UNREVIEWED,
        db_index=True,
        help_text="Status of human expert review and consensus adjudication.",
    )
    adjudicated_human_decision = models.CharField(
        max_length=30,
        choices=HumanDecision.choices,
        null=True,
        blank=True,
        db_index=True,
        help_text="Adjudicated human consensus label (PSIF, NOT PSIF, or INSUFFICIENT INFORMATION).",
    )
    adjudicated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="adjudicated_incidents",
        help_text="The HSE lead/auditor who performed or finalized adjudication.",
    )
    adjudicated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when final adjudication was recorded.",
    )
    adjudication_rationale = models.TextField(
        null=True,
        blank=True,
        help_text="Formal HSE adjudication rationale resolving reviewer consensus or overrides.",
    )
    is_synthetic_adjudication = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if adjudication was performed by an automated simulation/evaluation script rather than a genuine human HSE expert.",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "incident"
        verbose_name_plural = "incidents"
        ordering = ["-incident_date", "-created_at"]
        indexes = [
            models.Index(fields=["department", "incident_date"]),
            models.Index(fields=["severity_actual", "severity_potential"]),
        ]

    def __str__(self) -> str:
        date_str = self.incident_date.isoformat() if self.incident_date else "no date"
        dept = self.department or "unknown dept"
        return f"Incident {self.id} | {dept} | {date_str}"

    def save(self, *args, **kwargs):
        # Synchronize control_failed_bypassed from control_condition if not explicitly set
        if self.control_condition in (self.ControlCondition.FAILED, self.ControlCondition.BYPASSED):
            self.control_failed_bypassed = True
        elif self.control_condition in (self.ControlCondition.EFFECTIVE, self.ControlCondition.ABSENT):
            self.control_failed_bypassed = False
        elif self.control_condition == self.ControlCondition.UNKNOWN and self.control_failed_bypassed is None:
            self.control_failed_bypassed = None

        # Synchronize near_miss boolean from report_type if near_miss is None
        if self.near_miss is None:
            if self.report_type == self.ReportType.NEAR_MISS:
                self.near_miss = True
            elif self.report_type == self.ReportType.INCIDENT and self.severity_actual not in (None, self.SeverityActual.NONE):
                self.near_miss = False

        super().save(*args, **kwargs)

    # ── Training Eligibility & Provenance ─────────────────────────────────────
    class TrainingEligibility(models.TextChoices):
        UNREVIEWED = "UNREVIEWED", "Unreviewed"
        HUMAN_PSIF = "HUMAN_PSIF", "Human-Approved PSIF"
        HUMAN_NOT_PSIF = "HUMAN_NOT_PSIF", "Human-Approved Not PSIF"
        HUMAN_INSUFFICIENT_INFORMATION = "HUMAN_INSUFFICIENT_INFORMATION", "Human Insufficient Information"
        # Provenance categories: Synthetic is the sole category for all generated records.
        # Human-Approved Synthetic is the only elevated synthetic category.
        SYNTHETIC = "SYNTHETIC", "Synthetic"
        HUMAN_APPROVED_SYNTHETIC = "HUMAN_APPROVED_SYNTHETIC", "Human-Approved Synthetic"
        REAL_EXTERNAL = "REAL_EXTERNAL", "Real External"
        REAL_HUMAN = "REAL_HUMAN", "Real Human"
        UNKNOWN_UNLABELLED = "UNKNOWN_UNLABELLED", "Unknown / Unlabelled"

    @property
    def is_human_approved_synthetic(self) -> bool:
        """
        True ONLY IF:
        1. Underlying incident is synthetic (self.is_synthetic is True)
        2. Genuine human review exists (not an automated simulation: is_synthetic_adjudication is False)
        3. Reviewer identity exists (adjudicated_by or reviewed_by)
        4. Review/adjudication timestamp exists (adjudicated_at or reviewed_at)
        5. Decision is explicit (PSIF, NOT_PSIF, or INSUFFICIENT_INFORMATION)
        
        Synthetic reviewer simulations NEVER count as human approval.
        """
        if not self.is_synthetic:
            return False
        if self.is_synthetic_adjudication:
            return False

        reviewer_exists = (self.adjudicated_by_id is not None or self.reviewed_by_id is not None)
        timestamp_exists = (self.adjudicated_at is not None or self.reviewed_at is not None)
        has_decision = (
            self.adjudicated_human_decision in (
                self.HumanDecision.PSIF,
                self.HumanDecision.NOT_PSIF,
                self.HumanDecision.INSUFFICIENT_INFORMATION,
            )
            or self.is_psif_human_label is not None
        )
        return bool(reviewer_exists and timestamp_exists and has_decision)

    @property
    def training_eligibility(self) -> str:
        """
        Distinguishes training eligibility state from human review:
        - HUMAN_PSIF: Human adjudicated as PSIF (eligible for binary supervised training)
        - HUMAN_NOT_PSIF: Human adjudicated as NOT PSIF (eligible for binary supervised training)
        - HUMAN_INSUFFICIENT_INFORMATION: Human determined insufficient information
          (strictly INELIGIBLE for binary supervised training)
        - UNREVIEWED: No human adjudication recorded
        """
        if self.is_synthetic_adjudication:
            return self.TrainingEligibility.UNREVIEWED
        if self.adjudicated_human_decision == self.HumanDecision.PSIF:
            return self.TrainingEligibility.HUMAN_PSIF
        elif self.adjudicated_human_decision == self.HumanDecision.NOT_PSIF:
            return self.TrainingEligibility.HUMAN_NOT_PSIF
        elif self.adjudicated_human_decision == self.HumanDecision.INSUFFICIENT_INFORMATION:
            return self.TrainingEligibility.HUMAN_INSUFFICIENT_INFORMATION
        if self.is_psif_human_label is True and not self.is_synthetic_adjudication and self.label_is_human_reviewed:
            return self.TrainingEligibility.HUMAN_PSIF
        elif self.is_psif_human_label is False and not self.is_synthetic_adjudication and self.label_is_human_reviewed:
            return self.TrainingEligibility.HUMAN_NOT_PSIF
        return self.TrainingEligibility.UNREVIEWED

    @property
    def provenance_category(self) -> str:
        """
        Classifies incident into exact database provenance categories:
        1. HUMAN_APPROVED_SYNTHETIC: Synthetic incidents reviewed and approved by a genuine human reviewer.
        2. SYNTHETIC: Sole category for all generated records (including unreviewed benchmark and simulated-review records).
        3. REAL_EXTERNAL: Real-world external records (e.g. OSHA).
        4. REAL_HUMAN: Genuine real-world human data.
        5. UNKNOWN_UNLABELLED: Missing provenance.

        Synthetic is the sole category for all generated records.
        Human-Approved Synthetic is the only elevated synthetic category.
        Automated reviewer simulation records remain in SYNTHETIC (never elevated to HUMAN_APPROVED_SYNTHETIC).
        """
        if self.is_human_approved_synthetic or (self.is_synthetic and self.psif_label_source == self.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC):
            return self.TrainingEligibility.HUMAN_APPROVED_SYNTHETIC

        if not self.is_synthetic:
            if self.psif_label_source == self.PsifLabelSource.REAL_EXTERNAL:
                return self.TrainingEligibility.REAL_EXTERNAL
            if self.psif_label_source == self.PsifLabelSource.REAL_HUMAN:
                return self.TrainingEligibility.REAL_HUMAN

        if self.is_synthetic:
            return self.TrainingEligibility.SYNTHETIC

        return self.TrainingEligibility.UNKNOWN_UNLABELLED

    # ── PSIF label helpers ────────────────────────────────────────────────────

    @property
    def effective_training_label(self) -> bool | None:
        """
        Return the binary label (True/False) to use for supervised model training.
        
        Strict Rules:
        1. Synthetic evaluation simulation records (is_synthetic_adjudication=True)
           MUST NEVER become binary supervised targets -> None.
        2. Real external unlabelled records (REAL_EXTERNAL) -> None.
        3. Human-approved synthetic records:
           - PSIF -> True
           - NOT_PSIF -> False
           - INSUFFICIENT_INFORMATION -> None (strictly EXCLUDED; never converted to False)
        4. Synthetic benchmark records (unreviewed):
           - raw_row['sif_label'] or dataset label where valid (1 -> True, 0 -> False).
        5. Unknown/unlabelled -> None.
        """
        # Synthetic evaluation simulation records MUST NEVER become binary supervised targets
        if self.is_synthetic_adjudication:
            return None

        # Human adjudication on synthetic record takes highest precedence
        if self.adjudicated_human_decision == self.HumanDecision.PSIF:
            return True
        elif self.adjudicated_human_decision == self.HumanDecision.NOT_PSIF:
            return False
        elif self.adjudicated_human_decision == self.HumanDecision.INSUFFICIENT_INFORMATION:
            return None

        # Backward compatibility for direct is_psif_human_label assignment
        if self.is_psif_human_label is True and not self.is_synthetic_adjudication and self.label_is_human_reviewed:
            return True
        elif self.is_psif_human_label is False and not self.is_synthetic_adjudication and self.label_is_human_reviewed:
            return False

        # If not human-approved, check synthetic dataset label if record is synthetic
        if self.is_synthetic:
            raw = self.raw_row or {}
            sif = raw.get("sif_label")
            if sif in (1, "1", True):
                return True
            elif sif in (0, "0", False):
                return False

        return None

    @property
    def label_is_human_reviewed(self) -> bool:
        """True if the incident has an approved human review/adjudication."""
        return self.is_human_approved_synthetic or self.psif_label_source in (
            self.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC,
            self.PsifLabelSource.REAL_HUMAN,
        )

    def to_prediction_record(self) -> dict:
        """
        Convert Incident instance to the canonical record dictionary expected by
        ModelInferenceService / PSIFPredictor.
        """
        return incident_to_prediction_record(self)


class IncidentReview(models.Model):
    """
    Authoritative individual HSE review record.
    Preserves each reviewer's independent evaluation, allowing multiple
    safety experts to review the same incident without race conditions or overwriting.
    """
    class HumanDecision(models.TextChoices):
        PSIF = "PSIF", "PSIF"
        NOT_PSIF = "NOT_PSIF", "NOT PSIF"
        INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION", "Insufficient Information"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="reviews",
        help_text="The incident evaluated by the reviewer.",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_reviews_authored",
        help_text="The HSE expert who submitted this review.",
    )
    decision = models.CharField(
        max_length=30,
        choices=HumanDecision.choices,
        help_text="Reviewer's domain classification (PSIF, NOT PSIF, or INSUFFICIENT INFORMATION).",
    )
    rationale = models.TextField(
        blank=True,
        default="",
        help_text="Reviewer's written domain reasoning explaining the decision.",
    )
    rubric_version = models.CharField(
        max_length=20,
        default="1.0",
        help_text="Version of the HSE rubric used during evaluation.",
    )
    rubric_answers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured answers to rubric criteria (A: hazard, B: exposure, C: control, D: consequence, E: escalation, F: sufficiency).",
    )
    was_blinded = models.BooleanField(
        default=True,
        help_text="True if the review was performed blinded (without viewing model prediction or score).",
    )
    is_synthetic = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this review was generated by an automated simulation/evaluation script rather than a genuine human HSE expert.",
    )
    evidence_notes = models.TextField(
        blank=True,
        default="",
        help_text="Reviewer observational notes, disagreement justification, or field findings.",
    )
    structured_evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured answers for hazard, exposure, control, consequence, missing evidence, IOGP rule.",
    )
    model_version = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Active ML model version at time of review.",
    )
    knowledge_base_version = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="psif_kb_v1.0",
        help_text="Version of the PSIF knowledge base.",
    )
    reasoning_ruleset_version = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="psif_ruleset_v1.0",
        help_text="Version of the safety reasoning ruleset.",
    )
    action_library_version = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="action_library_v1",
        help_text="Version of the Action Engine library.",
    )
    previous_decision = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        choices=HumanDecision.choices,
        help_text="Previous decision if this review represents an edit or amendment.",
    )
    review_provenance = models.CharField(
        max_length=50,
        default="HUMAN_EXPERT",
        help_text="Provenance of the review: HUMAN_EXPERT, SYNTHETIC_SIMULATED, HISTORICAL_AUDIT.",
    )
    agreement_state = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Computed agreement state: AGREEMENT, HUMAN_OVERRIDES_MODEL, HUMAN_OVERRIDES_RULE, etc.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "incident review"
        verbose_name_plural = "incident reviews"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["incident", "reviewer"]),
            models.Index(fields=["decision"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        reviewer_name = self.reviewer.username if self.reviewer else "Anonymous"
        return f"Review on {self.incident_id} by {reviewer_name}: {self.decision}"


def incident_to_prediction_record(incident: Incident) -> dict:
    """
    Construct the canonical record dictionary expected by PSIFPredictor / ModelInferenceService.
    Contains ONLY legitimate predictive inputs.

    Strictly EXCLUDES target and human-review fields:
      - severity_actual
      - severity_potential
      - is_psif_human_label
      - sif_label
      - sif_category
      - confidence_target
      - reason
      - evidence_phrases
      - barrier_failures
      - life_saving_rule
      - reviewer_rationale
      - reviewed_by
      - reviewed_at
    """
    return {
        "description": incident.description,
        "corrective_actions": incident.corrective_actions,
        "witness_statement": incident.witness_statement,
        "department": incident.department,
        "location": incident.location,
        "job_task": incident.job_task,
        "equipment_involved": incident.equipment_involved,
        "injury_type": incident.injury_type,
        "body_part": incident.body_part,
        "immediate_cause": incident.immediate_cause,
        "root_cause_category": incident.root_cause_category,
        "near_miss": incident.near_miss,
        "report_type": incident.report_type,
        "high_energy_present": incident.high_energy_present,
        "energy_type": incident.energy_type,
        "worker_exposed": incident.worker_exposed,
        "direct_control_present": incident.direct_control_present,
        "control_type": incident.control_type,
        "control_condition": incident.control_condition,
        "control_failed_bypassed": incident.control_failed_bypassed,
    }


class IOGPRuleTag(models.Model):
    """
    Deterministic/rule-based taxonomy tag for IOGP Life-Saving Rules.
    This preserves auditable evidence of why a rule matched.
    """
    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="iogp_rules",
        help_text="The incident this rule tag applies to."
    )
    rule = models.CharField(max_length=100, help_text="The matched IOGP Rule name.")
    matched_keywords = models.JSONField(
        default=list,
        help_text="List of phrases or keywords that triggered the rule match."
    )
    matched_fields = models.JSONField(
        default=list,
        help_text="List of incident fields that contained the triggering evidence."
    )
    classification_method = models.CharField(
        max_length=50,
        default="rule_based",
        help_text="Method used for classification (e.g., rule_based)."
    )
    classifier_version = models.CharField(
        max_length=50,
        default="iogp_rules_v1",
        help_text="Version of the taxonomy/classifier ruleset."
    )
    confidence = models.FloatField(
        default=1.0,
        help_text="Keyword rule match score. Not a statistical probability."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "IOGP Rule Tag"
        verbose_name_plural = "IOGP Rule Tags"
        # Ensure idempotent backfills: prevent duplicate exact tags per incident
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "rule", "classifier_version"],
                name="unique_incident_iogp_rule"
            )
        ]

    def __str__(self):
        return f"{self.incident.id} - {self.rule}"

class IncidentEmbedding(models.Model):
    """
    Persisted embedding for an incident's composite narrative.
    Used for similarity-based related-incident retrieval without repeated ML inference.
    """
    incident = models.OneToOneField(
        Incident,
        on_delete=models.CASCADE,
        related_name="embedding",
        help_text="The incident this embedding represents."
    )
    vector = models.JSONField(
        help_text="The dense float array representing the text embedding."
    )
    embedding_model = models.CharField(
        max_length=100,
        help_text="The model used to generate the embedding (e.g., distilbert-base-uncased)."
    )
    embedding_version = models.CharField(
        max_length=50,
        default="v1",
        help_text="Version identifier for the embedding methodology."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Incident Embedding"
        verbose_name_plural = "Incident Embeddings"

    def __str__(self):
        return f"Embedding for {self.incident.id} ({self.embedding_model})"

class IncidentDataQuality(models.Model):
    """
    Persisted data quality checks for an incident.
    """
    class Status(models.TextChoices):
        VALID = "VALID", "Valid"
        WARNING = "WARNING", "Warning"
        CRITICAL = "CRITICAL", "Critical"

    incident = models.OneToOneField(
        Incident,
        on_delete=models.CASCADE,
        related_name="data_quality",
        help_text="The incident this data quality check applies to."
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.VALID,
        help_text="The overall data quality status."
    )
    findings = models.JSONField(
        default=list,
        help_text="List of structured findings."
    )
    quality_version = models.CharField(
        max_length=50,
        default="incident_quality_v1",
        help_text="Version of the data quality ruleset."
    )
    checked_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Incident Data Quality"
        verbose_name_plural = "Incident Data Quality Checks"

    def __str__(self):
        return f"Data Quality for {self.incident.id} - {self.status}"

