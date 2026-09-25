"""
PSIF Platform — Dataset Ingestion

Converts source rows (from CSV/JSON/JSONL parsing) into Incident model
instances, applying column mapping, type normalization, text preprocessing,
and weak PSIF labeling.

This module is the single code path for row → Incident conversion, used by:
  - The Celery batch processing task (apps/datasets/tasks.py)
  - (Future) manual ingestion utilities / management commands

Design principles:
  - Never crash on a single bad row; log and count errors instead.
  - Preserve the complete original row in Incident.raw_row regardless of
    mapping quality.
  - Apply weak PSIF labels during ingestion so training data is ready
    immediately after import.
  - Do NOT run BERT inference here (Phase 4 concern); composite_narrative
    is built and stored, ready for the inference pass.
"""
import logging
import uuid
from datetime import date, datetime
from typing import Optional

import pandas as pd

from ml_engine.text_preprocessing import build_composite_narrative

logger = logging.getLogger(__name__)

# ── Severity normalisation maps ────────────────────────────────────────────────
# Map common free-text severity values from source systems to Incident choices.

_SEVERITY_ACTUAL_MAP: dict[str, str] = {
    # none / near miss
    "none": "none",
    "no injury": "none",
    "no-injury": "none",
    "no injury / near miss": "none",
    "near miss": "none",
    "near-miss": "none",
    "property damage only": "none",
    "0": "none",
    # first aid
    "first aid": "first_aid",
    "first-aid": "first_aid",
    "firstaid": "first_aid",
    "fa": "first_aid",
    "1 - first aid": "first_aid",
    "1": "first_aid",
    # medical treatment
    "medical treatment": "medical_treatment",
    "medical treatment injury": "medical_treatment",
    "medical": "medical_treatment",
    "mti": "medical_treatment",
    "recordable": "medical_treatment",
    "2 - medical treatment": "medical_treatment",
    "2": "medical_treatment",
    # lost time
    "lost time": "lost_time",
    "lost time injury": "lost_time",
    "lost-time": "lost_time",
    "lti": "lost_time",
    "restricted duty": "lost_time",
    "restricted work": "lost_time",
    "3 - restricted work": "lost_time",
    "3": "lost_time",
    "4 - lost time": "lost_time",
    "4": "lost_time",
    # fatality
    "fatality": "fatality",
    "fatal": "fatality",
    "death": "fatality",
    "5 - fatality": "fatality",
    "5": "fatality",
}

_SEVERITY_POTENTIAL_MAP: dict[str, str] = {
    "low": "low",
    "minor": "low",
    "negligible": "low",
    "1": "low",
    "moderate": "moderate",
    "medium": "moderate",
    "significant": "moderate",
    "2": "moderate",
    "serious": "serious",
    "high": "serious",
    "major": "serious",
    "severe": "serious",
    "critical": "serious",
    "3": "serious",
    "fatality": "fatality",
    "fatal": "fatality",
    "catastrophic": "fatality",
    "life threatening": "fatality",
    "life-threatening": "fatality",
    "4": "fatality",
}

# Valid choice sets (mirrors Incident model choices)
_VALID_SEVERITY_ACTUAL = {"none", "first_aid", "medical_treatment", "lost_time", "fatality"}
_VALID_SEVERITY_POTENTIAL = {"low", "moderate", "serious", "fatality"}


def _normalise_severity_actual(val) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().lower()
    if not s:
        return None
    normalised = _SEVERITY_ACTUAL_MAP.get(s)
    if normalised:
        return normalised
    # Try prefix match for partial values
    for key, mapped in _SEVERITY_ACTUAL_MAP.items():
        if s.startswith(key) or key.startswith(s):
            return mapped
    # If the raw value is already a valid choice, accept it
    if s in _VALID_SEVERITY_ACTUAL:
        return s
    # Otherwise keep as-is, truncated to fit the field
    logger.debug("Unknown severity_actual value: %r — storing raw", val)
    return str(val)[:30]


def _normalise_severity_potential(val) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().lower()
    if not s:
        return None
    normalised = _SEVERITY_POTENTIAL_MAP.get(s)
    if normalised:
        return normalised
    for key, mapped in _SEVERITY_POTENTIAL_MAP.items():
        if s.startswith(key) or key.startswith(s):
            return mapped
    if s in _VALID_SEVERITY_POTENTIAL:
        return s
    logger.debug("Unknown severity_potential value: %r — storing raw", val)
    return str(val)[:30]


def _normalise_near_miss(val) -> Optional[bool]:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if pd.isna(val) if isinstance(val, float) else False:
            return None
        return bool(int(val))
    s = str(val).strip().lower()
    if s in ("true", "yes", "y", "1", "x", "✓", "near miss", "near-miss"):
        return True
    if s in ("false", "no", "n", "0", ""):
        return False
    return None


def _normalise_date(val) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, float) and pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "nan", "nat", ""):
        return None
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def _coerce_str(val, max_len: int = 255) -> Optional[str]:
    """Convert a value to a stripped string, or None if empty/NaN."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    s = str(val).strip()
    return s[:max_len] if s else None


def _row_to_serialisable(row: dict) -> dict:
    """Convert a row dict to a JSON-serialisable form for raw_row storage."""
    result = {}
    for k, v in row.items():
        if v is None:
            result[str(k)] = None
        elif isinstance(v, float) and pd.isna(v):
            result[str(k)] = None
        elif isinstance(v, (date, datetime)):
            result[str(k)] = v.isoformat()
        else:
            try:
                result[str(k)] = str(v) if not isinstance(v, (int, float, bool, str)) else v
            except Exception:
                result[str(k)] = repr(v)
    return result


# Fields that may be set from the column mapping
_SETTABLE_TEXT_FIELDS = {
    "external_id", "department", "location", "job_task", "equipment_involved",
    "injury_type", "body_part", "immediate_cause", "root_cause_category",
    "description", "corrective_actions", "witness_statement",
    "report_type", "high_energy_present", "energy_type", "worker_exposed",
    "direct_control_present", "control_type", "control_condition",
}
_LONG_TEXT_FIELDS = {"description", "corrective_actions", "witness_statement"}


def create_incident_from_row(
    row: dict,
    dataset,  # apps.datasets.models.Dataset — avoid circular import
    column_mapping: dict,
    row_index: Optional[int] = None,
) -> "Incident":  # noqa: F821
    """
    Build an UNSAVED Incident instance from a source data row.

    Args:
        row:            Dict of {source_column_name: raw_value} for one row.
        dataset:        The parent Dataset object.
        column_mapping: {source_column: canonical_field} mapping from Dataset.
        row_index:      1-indexed row number in the dataset for deterministic ID.

    Returns:
        Unsaved Incident instance, ready for bulk_create or .save().

    Notes:
        - raw_row is always set to the full source row, regardless of mapping.
        - composite_narrative is built from the three text fields if present.
        - Dataset provenance and synthetic status are assigned.
        - Generates a deterministic UUID based on dataset + external_id/row_index
          to ensure idempotent retries without row duplication.
    """
    from apps.incidents.models import Incident  # avoid circular import

    # ── Map source columns to canonical fields ────────────────────────────────
    canonical: dict = {}
    for source_col, canonical_field in column_mapping.items():
        if not canonical_field:  # explicitly unmapped
            continue
        if source_col in row:
            canonical[canonical_field] = row[source_col]

    # ── Type normalisation ────────────────────────────────────────────────────
    field_kwargs: dict = {}

    # Short text fields (max 255)
    for field in _SETTABLE_TEXT_FIELDS:
        if field in canonical:
            max_len = 4096 if field in _LONG_TEXT_FIELDS else 255
            field_kwargs[field] = _coerce_str(canonical[field], max_len=max_len)

    # Long text fields (no length cap in the model, but guard against extreme values)
    for field in _LONG_TEXT_FIELDS:
        if field in canonical:
            val = canonical[field]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                field_kwargs[field] = None
            else:
                field_kwargs[field] = str(val).strip() or None

    # Date
    if "incident_date" in canonical:
        field_kwargs["incident_date"] = _normalise_date(canonical["incident_date"])

    # Boolean
    if "near_miss" in canonical:
        field_kwargs["near_miss"] = _normalise_near_miss(canonical["near_miss"])

    # Severity choices
    if "severity_actual" in canonical:
        field_kwargs["severity_actual"] = _normalise_severity_actual(canonical["severity_actual"])
    if "severity_potential" in canonical:
        field_kwargs["severity_potential"] = _normalise_severity_potential(canonical["severity_potential"])

    # ── Build composite narrative ─────────────────────────────────────────────
    composite = build_composite_narrative(
        description=field_kwargs.get("description"),
        corrective_actions=field_kwargs.get("corrective_actions"),
        witness_statement=field_kwargs.get("witness_statement"),
    )

    # ── Deterministic Identity ────────────────────────────────────────────────
    ext_id = field_kwargs.get("external_id")
    dataset_id = getattr(dataset, "id", None)
    if dataset_id and ext_id:
        incident_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{dataset_id}:ext:{ext_id}")
    elif dataset_id and row_index is not None:
        incident_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"{dataset_id}:row:{row_index}")
    else:
        incident_id = uuid.uuid4()

    # ── Construct Incident ────────────────────────────────────────────────────
    incident = Incident(
        id=incident_id,
        dataset=dataset,
        raw_row=_row_to_serialisable(row),
        composite_narrative=composite or None,
        # Explicit unreviewed initial state for human-review fields
        reviewer_rationale=None,
        reviewed_by=None,
        reviewed_at=None,
        is_psif_human_label=None,
        status=Incident.Status.PENDING,
        **field_kwargs,
    )

    # ── Provenance & Workspace Assignment from Dataset ────────────────────────
    if dataset:
        if getattr(dataset, "workspace_id", None):
            incident.workspace_id = dataset.workspace_id
        is_synth = dataset.is_synthetic if hasattr(dataset, "is_synthetic") else True
        incident.is_synthetic = is_synth
        if hasattr(dataset, "source_provenance"):
            if dataset.source_provenance == "REAL_EXTERNAL":
                incident.psif_label_source = Incident.PsifLabelSource.REAL_EXTERNAL
            elif dataset.source_provenance == "REAL_HUMAN":
                incident.psif_label_source = Incident.PsifLabelSource.REAL_HUMAN
            elif dataset.source_provenance == "SYNTHETIC":
                incident.psif_label_source = Incident.PsifLabelSource.SYNTHETIC
            else:
                incident.psif_label_source = Incident.PsifLabelSource.NONE
        else:
            incident.psif_label_source = Incident.PsifLabelSource.SYNTHETIC if is_synth else Incident.PsifLabelSource.NONE
    else:
        incident.is_synthetic = False
        incident.psif_label_source = Incident.PsifLabelSource.NONE

    return incident


def bulk_create_incidents(
    rows: list[dict],
    dataset,
    column_mapping: dict,
    start_row_index: int = 1,
    return_details: bool = False,
) -> tuple:
    """
    Convert a list of row dicts into Incident objects and bulk-insert them.
    Enforces the centralized data quality gate on each individual row.
    Records with CRITICAL quality are rejected and not persisted as analyzable incidents.
    Idempotently skips already existing incident records.

    Args:
        rows:            List of source row dicts.
        dataset:         Parent Dataset object.
        column_mapping:  {source_column: canonical_field}.
        start_row_index: 1-indexed row number offset for audit reporting.
        return_details:  If True, returns (incidents, errors, dq_summary).

    Returns:
        (created_incidents_list, error_count) or
        (created_incidents_list, error_count, dq_summary) tuple.
    """
    from apps.incidents.models import Incident, IncidentDataQuality  # avoid circular import
    from apps.incidents.services.data_quality import validate_incident_for_analysis, VERSION

    incidents = []
    errors = 0
    warning_count = 0
    rejection_details = []

    for i, row in enumerate(rows):
        row_num = start_row_index + i
        try:
            incident = create_incident_from_row(row, dataset, column_mapping, row_index=row_num)

            # Centralized canonical data quality gate
            gate_res = validate_incident_for_analysis(incident)

            if not gate_res["accepted"]:
                # CRITICAL data quality: Reject at ingestion
                errors += 1
                reason = gate_res.get("reason") or "Data quality is insufficient for analysis."
                blocking = gate_res.get("blocking_findings", [])
                rejection_details.append({
                    "row": row_num,
                    "row_number": row_num,
                    "reason": reason,
                    "findings": blocking,
                    "blocking_findings": blocking,
                    "missing_fields": gate_res.get("missing_fields", []),
                })
                logger.info(
                    "dataset=%s row=%d REJECTED by data quality gate: %s",
                    getattr(dataset, "id", "adhoc"), row_num, blocking,
                )
                continue

            if gate_res["quality_status"] == IncidentDataQuality.Status.WARNING:
                warning_count += 1

            # Attach quality status and findings for persistence
            incident._dq_status = gate_res["quality_status"]
            incident._dq_findings = gate_res["findings"]
            incidents.append(incident)

        except Exception as exc:
            errors += 1
            rejection_details.append({
                "row": row_num,
                "row_number": row_num,
                "reason": f"Row processing error: {exc}",
                "findings": [str(exc)],
                "blocking_findings": [str(exc)],
                "missing_fields": [],
            })
            logger.warning(
                "dataset=%s row=%d ingestion error (skipping): %s",
                getattr(dataset, "id", "adhoc"), row_num, exc,
            )

    if incidents:
        # Check for existing incident IDs to guarantee idempotency on retry
        candidate_ids = [inc.id for inc in incidents]
        existing_ids = set(Incident.objects.filter(id__in=candidate_ids).values_list("id", flat=True))
        new_incidents = [inc for inc in incidents if inc.id not in existing_ids]

        if new_incidents:
            Incident.objects.bulk_create(new_incidents, batch_size=500)

            # Persist IncidentDataQuality records
            dq_records = [
                IncidentDataQuality(
                    incident=inc,
                    status=getattr(inc, "_dq_status", IncidentDataQuality.Status.VALID),
                    findings=getattr(inc, "_dq_findings", []),
                    quality_version=VERSION,
                )
                for inc in new_incidents
            ]
            IncidentDataQuality.objects.bulk_create(dq_records, batch_size=500, ignore_conflicts=True)

            from apps.incidents.services.embedding import generate_and_persist_embeddings
            generate_and_persist_embeddings(new_incidents)

    if return_details:
        dq_summary = {
            "total": len(rows),
            "accepted": len(incidents),
            "accepted_with_warnings": warning_count,
            "rejected": errors,
            "rejections": rejection_details,
        }
        return incidents, errors, dq_summary

    return incidents, errors


def ingest_document_incidents(
    document_records: list[dict],
    dataset=None,
    column_mapping: Optional[dict] = None,
    return_details: bool = True,
) -> tuple:
    """
    Unified canonical ingestion path for incidents extracted from documents or files.
    Enforces the identical canonical data quality gate and row-level rejection logic
    as CSV, JSON, and JSONL ingestion paths.
    """
    if column_mapping is None:
        if document_records:
            column_mapping = {k: k for k in document_records[0].keys()}
        else:
            column_mapping = {}

    return bulk_create_incidents(
        rows=document_records,
        dataset=dataset,
        column_mapping=column_mapping,
        start_row_index=1,
        return_details=return_details,
    )
