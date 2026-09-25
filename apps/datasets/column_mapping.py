"""
PSIF Platform — Column Mapping Utilities

Provides:
  - CANONICAL_FIELDS: the set of valid canonical Incident field names
    that a source column may be mapped to.
  - suggest_column_mapping(): auto-suggest mapping for source columns
    using case-insensitive substring and alias matching.
"""

# ── Canonical field definitions ───────────────────────────────────────────────
# These are the Incident model fields that may be populated from a dataset.
# System fields (id, dataset, composite_narrative, raw_row, is_psif_*, etc.)
# are NOT in this set — they are generated automatically during ingestion.

CANONICAL_FIELDS: set[str] = {
    "external_id",
    "incident_date",
    "department",
    "location",
    "job_task",
    "equipment_involved",
    "injury_type",
    "body_part",
    "immediate_cause",
    "root_cause_category",
    "severity_actual",
    "severity_potential",
    "near_miss",
    "description",
    "corrective_actions",
    "witness_statement",
}

# Human-readable labels shown in the column-mapping UI dropdowns
CANONICAL_FIELD_LABELS: dict[str, str] = {
    "external_id": "External / Source ID",
    "incident_date": "Incident Date",
    "department": "Department",
    "location": "Location / Site",
    "job_task": "Job / Task",
    "equipment_involved": "Equipment Involved",
    "injury_type": "Injury Type",
    "body_part": "Body Part Affected",
    "immediate_cause": "Immediate Cause",
    "root_cause_category": "Root Cause Category",
    "severity_actual": "Severity — Actual Outcome",
    "severity_potential": "Severity — Potential (Max)",
    "near_miss": "Near Miss Flag",
    "description": "Incident Description / Narrative",
    "corrective_actions": "Corrective Actions",
    "witness_statement": "Witness Statement",
}

# ── Alias table for auto-suggestion ──────────────────────────────────────────
# Each key is a canonical field name; values are lowercase substrings that
# should trigger a match against a source column name.
# Matching is done with case-insensitive substring search (most specific wins).

_FIELD_ALIASES: dict[str, list[str]] = {
    "description": [
        "incident description", "incident detail", "incident narrative",
        "description", "narrative", "details", "summary", "what happened",
        "event description", "report details", "report_text", "report text",
        "report_narrative",
    ],
    "incident_date": [
        "incident date", "date of incident", "date of occurrence", "occurrence date",
        "event date", "accident date", "date occurred", "reported date", "report date",
        "incident_date", "occurrence",
    ],
    "department": [
        "department name", "department", "dept name", "dept",
        "division", "business unit", "section",
    ],
    "location": [
        "incident location", "work location", "work area", "location",
        "site name", "site", "facility", "area", "place",
    ],
    "job_task": [
        "job task", "work task", "activity performed", "task description",
        "job/task", "work activity", "task", "job", "activity",
    ],
    "equipment_involved": [
        "equipment involved", "equipment name", "machinery",
        "equipment", "machine", "vehicle", "tool", "asset",
    ],
    "injury_type": [
        "nature of injury", "injury classification", "injury category",
        "type of injury", "injury type", "harm type", "injury",
    ],
    "body_part": [
        "body part injured", "affected body part", "injured body part",
        "part of body", "body part", "body area", "body",
    ],
    "immediate_cause": [
        "immediate cause of incident", "proximate cause", "direct cause",
        "primary cause", "immediate cause",
    ],
    "root_cause_category": [
        "root cause category", "causal factor", "contributing factor",
        "underlying cause", "root cause type", "root cause",
        "cause category",
    ],
    "severity_actual": [
        "actual injury severity", "outcome severity", "recorded severity",
        "actual outcome", "actual severity", "severity actual",
        "severity of injury", "severity", "actual",
    ],
    "severity_potential": [
        "maximum potential severity", "potential consequence",
        "worst case severity", "potential outcome", "potential severity",
        "severity potential", "potential",
    ],
    "near_miss": [
        "near miss event", "near-miss", "close call", "near hit",
        "near miss", "nearmiss", "near_miss",
    ],
    "corrective_actions": [
        "corrective measures", "preventive actions", "action taken",
        "actions taken", "corrective action", "corrective actions",
        "remediation", "controls",
    ],
    "witness_statement": [
        "witness account", "witness testimony", "witness statement",
        "witnesses", "witness",
    ],
    "external_id": [
        "incident number", "incident ref", "report number", "case number",
        "record id", "case id", "report id", "incident id", "reference",
        "incident_id", "ref", "id",
    ],
}

# Pre-compute: (alias_string → canonical_field) sorted by alias length
# (longer aliases are more specific and should match first)
_ALIAS_INDEX: list[tuple[str, str]] = sorted(
    [
        (alias.lower(), canonical)
        for canonical, aliases in _FIELD_ALIASES.items()
        for alias in aliases
    ],
    key=lambda x: -len(x[0]),  # longest match first
)


def _normalise(s: str) -> str:
    """Lowercase and strip a column name for comparison."""
    return s.strip().lower().replace("_", " ").replace("-", " ")


def find_canonical_field(source_column: str) -> str | None:
    """
    Given a source column name, return the best-matching canonical field name
    or None if no match is found.

    Matching strategy:
      1. Exact match (case-insensitive, after normalising underscores/dashes)
      2. Source column is a substring of an alias (or vice-versa)
      3. No match → return None
    """
    norm = _normalise(source_column)

    # 1. Exact canonical field name match
    if norm.replace(" ", "_") in CANONICAL_FIELDS:
        return norm.replace(" ", "_")

    # 2. Alias substring match (longer aliases checked first for specificity)
    for alias, canonical in _ALIAS_INDEX:
        if alias == norm or alias in norm or norm in alias:
            return canonical

    return None


def suggest_column_mapping(source_columns: list[str]) -> dict[str, str]:
    """
    Return a suggested {source_column: canonical_field} mapping for a list
    of source column names.

    Columns with no match are included with an empty string value, so the
    frontend can show "-- not mapped --" for them.

    The result is safe to store directly in Dataset.column_mapping.
    """
    mapping: dict[str, str] = {}
    used_canonical: set[str] = set()  # prevent duplicate assignments

    for col in source_columns:
        canonical = find_canonical_field(col)
        if canonical and canonical not in used_canonical:
            mapping[col] = canonical
            used_canonical.add(canonical)
        else:
            mapping[col] = ""  # explicitly unmapped

    return mapping


def validate_column_mapping(mapping: dict) -> list[str]:
    """
    Validate a user-submitted column mapping.

    Returns a list of error messages (empty list = valid).
    Rules:
      - Values must be valid canonical field names or empty string (unmapped).
      - No two source columns may map to the same canonical field.
    """
    errors: list[str] = []
    canonical_usage: dict[str, str] = {}  # canonical → first source col using it

    for source_col, canonical_field in mapping.items():
        if canonical_field == "" or canonical_field is None:
            continue  # explicitly unmapped — OK

        if canonical_field not in CANONICAL_FIELDS:
            errors.append(
                f"'{canonical_field}' is not a valid canonical field. "
                f"Valid fields: {sorted(CANONICAL_FIELDS)}"
            )
            continue

        if canonical_field in canonical_usage:
            errors.append(
                f"Duplicate mapping: both '{canonical_usage[canonical_field]}' and "
                f"'{source_col}' map to '{canonical_field}'. "
                "Each canonical field may only be mapped once."
            )
        else:
            canonical_usage[canonical_field] = source_col

    return errors
