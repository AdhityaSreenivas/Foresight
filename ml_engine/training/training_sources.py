"""
PSIF Platform — Clean Training Architecture & Eligibility Engine

User-Facing Synthetic Categories:
- SYNTHETIC: Sole category for all generated records (benchmark, unreviewed, simulated reviews)
- HUMAN_APPROVED_SYNTHETIC: The only elevated synthetic category (genuine human HSE review/adjudication)

Implementation Strategy:
- MIXED_SYNTHETIC: Internal backend implementation strategy combining SYNTHETIC + HUMAN_APPROVED_SYNTHETIC;
  not exposed as a user-facing dataset category.

Strict Rules:
1. Zero Masquerading: Synthetic data and simulated reviews NEVER count as real-world OIL ground truth.
2. Human Review INSUFFICIENT_INFORMATION is strictly excluded from binary supervised targets.
3. CRITICAL data quality records are strictly excluded from all training sources.
4. Heuristic training concept is completely eliminated; selecting HEURISTIC raises an error.
5. Active production model is NEVER automatically replaced by candidate training.
6. Human decision status is kept completely separate from provenance.
"""
import logging
import re
from typing import List, Dict, Any, Tuple, Optional
from django.db.models import Q

from apps.incidents.models import Incident, IncidentDataQuality
from apps.incidents.services.data_quality import PLACEHOLDERS, validate_incident_for_analysis

logger = logging.getLogger(__name__)


class TrainingSource:
    SYNTHETIC = "SYNTHETIC"
    HUMAN_APPROVED_SYNTHETIC = "HUMAN_APPROVED_SYNTHETIC"

    # User-facing training/provenance categories (strictly these two for synthetic data)
    USER_FACING_SOURCES = [SYNTHETIC, HUMAN_APPROVED_SYNTHETIC]

    # Internal implementation strategy only (controlled combination; never exposed as a dataset type)
    MIXED_SYNTHETIC = "MIXED_SYNTHETIC"

    ALL_SOURCES = [SYNTHETIC, HUMAN_APPROVED_SYNTHETIC, MIXED_SYNTHETIC]

    # Legacy aliases for backward compatibility with older test callers
    HUMAN = HUMAN_APPROVED_SYNTHETIC
    MIXED = MIXED_SYNTHETIC


def is_incident_quality_acceptable(incident: Incident) -> bool:
    """
    Returns True if an incident passes data-quality screening for model training.
    Rejects records with CRITICAL data-quality status, empty narrative, placeholders,
    or severe corruption.
    """
    try:
        if hasattr(incident, "data_quality") and incident.data_quality:
            if incident.data_quality.status == IncidentDataQuality.Status.CRITICAL:
                return False
    except Exception:
        pass

    # Direct narrative check
    narrative = (incident.description or incident.composite_narrative or "").strip()
    if not narrative:
        return False
    if narrative.lower() in PLACEHOLDERS or re.match(r"^(?:desc|test|sample|incident)\s*\d+$", narrative.lower()):
        return False
    if not any(c.isalnum() for c in narrative):
        return False

    return True


def get_training_eligible_incidents(
    training_source: str = TrainingSource.SYNTHETIC,
    sample_limit: Optional[int] = None,
    min_quality_status: str = "WARNING",
) -> Tuple[List[Incident], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Canonical training eligibility query engine.

    Args:
        training_source: One of "SYNTHETIC", "HUMAN_APPROVED_SYNTHETIC", "MIXED_SYNTHETIC".
        sample_limit: Optional maximum number of records to return.
        min_quality_status: Minimum quality threshold ("WARNING" allows VALID & WARNING; excludes CRITICAL).

    Returns:
        (eligible_incidents, row_provenance_list, composition_summary)

    Raises:
        ValueError if training_source is HEURISTIC or not in TrainingSource.ALL_SOURCES.
    """
    training_source = str(training_source).upper().strip()

    if training_source == "HEURISTIC":
        raise ValueError(
            "The 'HEURISTIC' training source has been eliminated. "
            "Former heuristic records were audited and reclassified as application-generated synthetic data. "
            f"Please select one of {TrainingSource.ALL_SOURCES}."
        )

    # Map legacy aliases
    if training_source == "HUMAN":
        training_source = TrainingSource.HUMAN_APPROVED_SYNTHETIC
    elif training_source == "MIXED":
        training_source = TrainingSource.MIXED_SYNTHETIC

    if training_source not in TrainingSource.ALL_SOURCES:
        raise ValueError(
            f"Invalid training_source '{training_source}'. "
            f"Must be one of {TrainingSource.ALL_SOURCES}."
        )

    logger.info("Querying training eligible incidents for source: %s", training_source)

    eligible_incidents: List[Incident] = []
    row_provenance: List[Dict[str, Any]] = []

    human_approved_count = 0
    synthetic_count = 0
    insufficient_info_excluded = 0
    critical_excluded = 0
    unknown_excluded = 0

    # ── 1. HUMAN-APPROVED SYNTHETIC SOURCE ────────────────────────────────────
    if training_source in (TrainingSource.HUMAN_APPROVED_SYNTHETIC, TrainingSource.MIXED_SYNTHETIC):
        # Must be genuine human review/adjudication (strictly excluding synthetic reviewer simulations)
        human_qs = Incident.objects.filter(
            is_synthetic=True,
            is_synthetic_adjudication=False,
        ).filter(
            Q(adjudicated_human_decision__in=[
                Incident.HumanDecision.PSIF,
                Incident.HumanDecision.NOT_PSIF,
                Incident.HumanDecision.INSUFFICIENT_INFORMATION,
            ]) |
            Q(psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC, is_psif_human_label__isnull=False)
        ).select_related("data_quality").order_by("created_at")

        for inc in human_qs:
            # Check 1: Exclude human INSUFFICIENT_INFORMATION from binary targets
            if inc.adjudicated_human_decision == Incident.HumanDecision.INSUFFICIENT_INFORMATION:
                insufficient_info_excluded += 1
                continue

            # Check 2: Data quality gate
            if not is_incident_quality_acceptable(inc):
                critical_excluded += 1
                continue

            # Determine human binary label
            if inc.adjudicated_human_decision == Incident.HumanDecision.PSIF:
                label = True
            elif inc.adjudicated_human_decision == Incident.HumanDecision.NOT_PSIF:
                label = False
            elif inc.is_psif_human_label is not None:
                label = bool(inc.is_psif_human_label)
            else:
                unknown_excluded += 1
                continue

            inc._training_label = label
            inc._training_source = "human_approved_synthetic"
            inc._dq_status = getattr(inc.data_quality, "status", "VALID") if hasattr(inc, "data_quality") and inc.data_quality else "VALID"

            eligible_incidents.append(inc)
            human_approved_count += 1
            row_provenance.append({
                "incident_id": str(inc.id),
                "label": label,
                "label_source": "human_approved_synthetic",
                "quality_status": inc._dq_status,
                "dataset_id": str(inc.dataset_id) if inc.dataset_id else None,
            })

    # ── 2. SYNTHETIC SOURCE ───────────────────────────────────────────────────
    if training_source in (TrainingSource.SYNTHETIC, TrainingSource.MIXED_SYNTHETIC):
        already_added_ids = {str(inc.id) for inc in eligible_incidents}

        # Query synthetic records (strictly excluding synthetic reviewer simulations)
        synthetic_qs = Incident.objects.filter(
            is_synthetic=True,
            is_synthetic_adjudication=False,
        ).exclude(
            # Exclude records already adjudicated with INSUFFICIENT_INFORMATION
            adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION
        ).select_related("data_quality").order_by("created_at")

        for inc in synthetic_qs.iterator(chunk_size=2000):
            if str(inc.id) in already_added_ids:
                continue

            # In MIXED mode, human adjudication decision already took precedence above
            if inc.adjudicated_human_decision in (Incident.HumanDecision.PSIF, Incident.HumanDecision.NOT_PSIF):
                continue

            # Check for explicit synthetic label in raw_row or effective_training_label
            raw = inc.raw_row or {}
            sif_val = raw.get("sif_label")

            if sif_val is not None and sif_val in (0, 1, "0", "1", True, False):
                label = True if sif_val in (1, "1", True) else False
            elif inc.effective_training_label is not None:
                label = inc.effective_training_label
            else:
                unknown_excluded += 1
                continue

            # Data quality gate
            if not is_incident_quality_acceptable(inc):
                critical_excluded += 1
                continue

            inc._training_label = label
            inc._training_source = "synthetic"
            inc._dq_status = getattr(inc.data_quality, "status", "VALID") if hasattr(inc, "data_quality") and inc.data_quality else "VALID"

            eligible_incidents.append(inc)
            synthetic_count += 1
            row_provenance.append({
                "incident_id": str(inc.id),
                "label": label,
                "label_source": "synthetic",
                "quality_status": inc._dq_status,
                "dataset_id": str(inc.dataset_id) if inc.dataset_id else None,
            })

            if sample_limit and len(eligible_incidents) >= sample_limit:
                break

    # Apply sample limit if specified and not already capped
    if sample_limit and len(eligible_incidents) > sample_limit:
        eligible_incidents = eligible_incidents[:sample_limit]
        row_provenance = row_provenance[:sample_limit]
        human_approved_count = sum(1 for p in row_provenance if p["label_source"] == "human_approved_synthetic")
        synthetic_count = sum(1 for p in row_provenance if p["label_source"] == "synthetic")

    pos_count = sum(1 for inc in eligible_incidents if inc._training_label is True)
    neg_count = sum(1 for inc in eligible_incidents if inc._training_label is False)

    composition = {
        "training_source": training_source,
        "total_eligible": len(eligible_incidents),
        "human_approved_synthetic_count": human_approved_count,
        "synthetic_count": synthetic_count,
        # Legacy/UI compatibility aliases
        "human_count": human_approved_count,
        "heuristic_count": 0,
        "positive_count": pos_count,
        "negative_count": neg_count,
        "insufficient_info_excluded": insufficient_info_excluded,
        "critical_excluded": critical_excluded,
        "unknown_excluded": unknown_excluded,
    }

    logger.info(
        "Eligible incidents resolved: total=%d (human_approved=%d, synthetic=%d, pos=%d, neg=%d)",
        len(eligible_incidents), human_approved_count, synthetic_count, pos_count, neg_count,
    )

    return eligible_incidents, row_provenance, composition


def get_training_sources_overview(use_cache: bool = True) -> Dict[str, Any]:
    """
    Returns live eligibility counts and metadata for each candidate model training source.
    Caches the calculation briefly (30s) to guarantee fast page loads and API responses.
    """
    from django.core.cache import cache

    cache_key = "training_sources_overview_cache_v1"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    # 1. Human-Approved Synthetic Count
    human_qs = Incident.objects.filter(
        is_synthetic=True,
        is_synthetic_adjudication=False,
    ).filter(
        Q(adjudicated_human_decision__in=[
            Incident.HumanDecision.PSIF,
            Incident.HumanDecision.NOT_PSIF,
        ]) |
        Q(psif_label_source=Incident.PsifLabelSource.HUMAN_APPROVED_SYNTHETIC, is_psif_human_label__isnull=False)
    ).exclude(
        adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION
    ).exclude(
        data_quality__status=IncidentDataQuality.Status.CRITICAL
    ).filter(
        Q(description__isnull=False, description__gt="") |
        Q(composite_narrative__isnull=False, composite_narrative__gt="")
    )
    human_count = human_qs.count()

    # 2. Synthetic Dataset Benchmark Count
    synth_qs = Incident.objects.filter(
        is_synthetic=True,
        is_synthetic_adjudication=False,
    ).exclude(
        adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION
    ).exclude(
        data_quality__status=IncidentDataQuality.Status.CRITICAL
    ).filter(
        Q(description__isnull=False, description__gt="") |
        Q(composite_narrative__isnull=False, composite_narrative__gt="")
    ).filter(
        raw_row__has_key="sif_label"
    )
    synthetic_count = synth_qs.count()

    data = {
        "synthetic": {
            "source": "SYNTHETIC",
            "name": "Synthetic Dataset (Benchmark / Pretraining)",
            "count": synthetic_count,
            "formatted_count": f"{synthetic_count:,}",
            "min_required": 20,
            "is_eligible": synthetic_count >= 20,
            "description": (
                f"Trains on application synthetic benchmark records across imported datasets "
                f"({synthetic_count:,} eligible records). Labels are artificial/generated, "
                f"not real-world human ground truth."
            ),
        },
        "human_approved_synthetic": {
            "source": "HUMAN_APPROVED_SYNTHETIC",
            "name": "Human-Approved Synthetic (Adjudicated Synthetic Records)",
            "count": human_count,
            "formatted_count": f"{human_count:,}",
            "min_required": 20,
            "is_eligible": human_count >= 20,
            "status_text": "meets &ge;20 requirement" if human_count >= 20 else "requires &ge;20",
            "description": (
                f"Strictly uses synthetic records reviewed and approved by a genuine human reviewer "
                f"(currently {human_count:,} eligible records; {'meets' if human_count >= 20 else 'requires'} ≥20)."
            ),
        },
    }

    if use_cache:
        cache.set(cache_key, data, timeout=30)

    return data

