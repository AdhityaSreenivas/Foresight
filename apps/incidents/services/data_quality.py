import re
from datetime import date, datetime
from typing import Dict, Any, List, Optional

from apps.incidents.models import Incident, IncidentDataQuality

VERSION = "incident_quality_v1"
DATA_QUALITY_VERSION = VERSION


def get_data_quality_version() -> str:
    """Returns the active data quality gate version."""
    return DATA_QUALITY_VERSION

# Recognized safety and oil & gas operational terms that provide useful domain context
# even when the narrative is concise (e.g. single-word or very short narratives).
MEANINGFUL_SAFETY_TERMS = {
    "pump", "valve", "pipeline", "pipe", "leak", "fire", "fall", "crane", "drill",
    "drilling", "rig", "h2s", "gas", "pressure", "well", "tank", "wireline",
    "blowout", "scaffold", "chemical", "spill", "generator", "engine", "compressor",
    "motor", "hose", "flange", "gauge", "derrick", "winch", "cable", "slip", "trip",
    "burn", "shock", "electrical", "cut", "amputation", "fracture", "explosion",
    "injury", "hazard", "overflow", "overpressure", "corrosion", "fractured",
    "flare", "separator", "manifold", "vessel", "boil", "steam",
    "toxic", "asphyxiation", "loto", "lockout", "tagout", "ppe", "welding", "grinding",
    "excavation", "trench", "forklift", "vehicle", "rollover"
}

# Known placeholder strings that indicate test or non-genuine data
PLACEHOLDERS = {
    "test", "dummy", "asdf", "sample", "n/a", "na", "-", "--", "none", "null",
    "nil", "tbd", "xxx", "xyz", "placeholder", "testing", "nothing", "no description",
    "na na", "n/a n/a"
}

BODY_PART_PATTERNS = {
    "eye": re.compile(r"\b(eye injury|injured (?:his|her|their)?\s*eye|injury to (?:the\s+)?eye)\b", re.IGNORECASE),
    "knee": re.compile(r"\b(knee injury|injured (?:his|her|their)?\s*knee|injury to (?:the\s+)?knee)\b", re.IGNORECASE),
    "head": re.compile(r"\b(head injury|injured (?:his|her|their)?\s*head|injury to (?:the\s+)?head)\b", re.IGNORECASE),
    "hand": re.compile(r"\b(hand injury|injured (?:his|her|their)?\s*hand|injury to (?:the\s+)?hand)\b", re.IGNORECASE),
    "arm":  re.compile(r"\b(arm injury|injured (?:his|her|their)?\s*arm|injury to (?:the\s+)?arm)\b", re.IGNORECASE),
    "leg":  re.compile(r"\b(leg injury|injured (?:his|her|their)?\s*leg|injury to (?:the\s+)?leg)\b", re.IGNORECASE),
    "foot": re.compile(r"\b(foot injury|injured (?:his|her|their)?\s*foot|injury to (?:the\s+)?foot)\b", re.IGNORECASE),
}

INJURY_TYPE_PATTERNS = {
    "fracture": re.compile(r"\b(fracture|fractured|broken bone)\b", re.IGNORECASE),
    "laceration": re.compile(r"\b(laceration|deep cut|sliced)\b", re.IGNORECASE),
    "burn": re.compile(r"\b(burn|burned|chemical burn)\b", re.IGNORECASE),
}


def _parse_date_safely(val: Any) -> Optional[date]:
    """Parse date from date, datetime, or ISO string."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        val = val.strip()
        if not val or val.lower() in ("none", "null", "nan", ""):
            return None
        try:
            return date.fromisoformat(val[:10])
        except (ValueError, TypeError):
            return None
    return None


def validate_incident_for_analysis(data_or_incident: Any) -> Dict[str, Any]:
    """
    Centralized canonical data quality gate for all incident ingestion pathways.
    Accepts either an Incident model instance or a dictionary of raw/parsed fields.
    Never modifies user data.

    Returns a structured dictionary:
        accepted: bool
        quality_status: "VALID" | "WARNING" | "CRITICAL"
        quality_score: float (0.0 to 1.0)
        blocking_findings: list[str]
        warning_findings: list[str]
        missing_fields: list[str]
        reason: str | None
        quality_version: str
        findings: list[dict]
    """
    # ── 1. Extract values ─────────────────────────────────────────────────────
    if isinstance(data_or_incident, Incident):
        narrative = data_or_incident.description or ""
        comp_narrative = data_or_incident.composite_narrative or narrative
        activity = data_or_incident.job_task or ""
        department = data_or_incident.department or ""
        location = data_or_incident.location or ""
        body_part = data_or_incident.body_part or ""
        injury_type = data_or_incident.injury_type or ""
        severity_actual = data_or_incident.severity_actual or ""
        near_miss = data_or_incident.near_miss
        incident_date_val = data_or_incident.incident_date
        report_date_val = None
    elif isinstance(data_or_incident, dict):
        narrative = data_or_incident.get("description") or data_or_incident.get("report_text") or ""
        comp_narrative = (
            data_or_incident.get("composite_narrative")
            or narrative
            or data_or_incident.get("report_text")
            or ""
        )
        activity = data_or_incident.get("activity") or data_or_incident.get("job_task") or ""
        department = data_or_incident.get("department") or data_or_incident.get("site_area") or ""
        location = data_or_incident.get("location") or data_or_incident.get("site") or ""
        body_part = data_or_incident.get("body_part") or ""
        injury_type = data_or_incident.get("injury_type") or ""
        severity_actual = data_or_incident.get("severity_actual") or ""
        near_miss = data_or_incident.get("near_miss")
        incident_date_val = data_or_incident.get("incident_date")
        report_date_val = data_or_incident.get("report_date")
    else:
        narrative = ""
        comp_narrative = ""
        activity = ""
        department = ""
        location = ""
        body_part = ""
        injury_type = ""
        severity_actual = ""
        near_miss = None
        incident_date_val = None
        report_date_val = None

    findings: List[Dict[str, Any]] = []
    missing_fields: List[str] = []

    narrative_clean = str(narrative).strip()
    narrative_lower = narrative_clean.lower()
    comp_narrative_clean = str(comp_narrative).strip().lower()
    activity_clean = str(activity).strip()
    location_clean = str(location).strip()

    # ── 2. Narrative Quality & Missingness ────────────────────────────────────
    alnum_chars = [c for c in narrative_clean if c.isalnum()]
    words = [w for w in narrative_clean.split() if any(c.isalnum() for c in w)]

    if not narrative_clean:
        missing_fields.append("description")
        findings.append({
            "check_id": "MISSING_NARRATIVE",
            "severity": "critical",
            "fields": ["description"],
            "message": "Incident narrative is empty.",
            "evidence": []
        })
        if not activity_clean:
            missing_fields.append("activity")
            findings.append({
                "check_id": "MISSING_ACTIVITY",
                "severity": "critical",
                "fields": ["activity"],
                "message": "Activity is missing.",
                "evidence": []
            })
    elif "\ufffd" in narrative_clean or "\x00" in narrative_clean:
        findings.append({
            "check_id": "UNSUPPORTED_ENCODING",
            "severity": "critical",
            "fields": ["description"],
            "message": "Narrative contains corrupted or unsupported encoding characters.",
            "evidence": [narrative_clean[:60]],
        })
    elif not alnum_chars:
        findings.append({
            "check_id": "MEANINGLESS_NARRATIVE",
            "severity": "critical",
            "fields": ["description"],
            "message": "Narrative contains no alphanumeric words or recognizable content.",
            "evidence": [narrative]
        })
    elif (
        narrative_lower in PLACEHOLDERS
        or re.match(r"^(?:desc|test|sample|incident|dummy|asdf)\s*\d*$", narrative_lower)
        or (words and all(w.lower().strip(",.!?\"';:()") in PLACEHOLDERS or w.isdigit() for w in words))
    ):
        findings.append({
            "check_id": "PLACEHOLDER_NARRATIVE",
            "severity": "critical",
            "fields": ["description"],
            "message": "Narrative appears to be placeholder or test data.",
            "evidence": [narrative]
        })
    elif len(narrative_clean) >= 4 and len(set(c.lower() for c in alnum_chars)) <= 1:
        findings.append({
            "check_id": "CORRUPTED_NARRATIVE",
            "severity": "critical",
            "fields": ["description"],
            "message": "Narrative consists of repeated single characters or corrupted text.",
            "evidence": [narrative]
        })
    elif len(alnum_chars) >= 4 and not any(v in narrative_lower for v in "aeiouy"):
        findings.append({
            "check_id": "CORRUPTED_NARRATIVE",
            "severity": "critical",
            "fields": ["description"],
            "message": "Narrative appears to be corrupted or meaningless text.",
            "evidence": [narrative]
        })
    elif (
        any(k in narrative_lower for k in ["asdfghjkl", "qwertyuiop", "zxcvbnm"])
        or re.match(r"^(?:asdfghjkl|qwertyuiop|zxcvbnm|\d+|\s+)+$", narrative_clean, re.IGNORECASE)
    ):
        findings.append({
            "check_id": "MEANINGLESS_NARRATIVE",
            "severity": "critical",
            "fields": ["description"],
            "message": "Narrative appears to be keyboard mash or meaningless text.",
            "evidence": [narrative]
        })
    elif len(words) == 1:
        word = words[0].lower().strip(",.!?\"';:()")
        if len(word) > 3 and not any(v in word for v in "aeiouy"):
            findings.append({
                "check_id": "CORRUPTED_NARRATIVE",
                "severity": "critical",
                "fields": ["description"],
                "message": "Narrative appears to be corrupted or meaningless text.",
                "evidence": [narrative]
            })
        else:
            missing_fields.append("description")
            findings.append({
                "check_id": "INSUFFICIENT_NARRATIVE",
                "severity": "critical",
                "fields": ["description"],
                "message": "Incident narrative is insufficient for analysis (too short or single word without operational context).",
                "evidence": [narrative]
            })
    elif len(words) < 10:
        findings.append({
            "check_id": "SHORT_NARRATIVE",
            "severity": "warning",
            "fields": ["description"],
            "message": "Narrative is brief (< 10 words). Evidence strength is limited; prediction reliability may be reduced.",
            "evidence": [narrative]
        })

    # Non-blocking check: activity missing when narrative is present
    if narrative_clean and not activity_clean and "activity" not in missing_fields:
        findings.append({
            "check_id": "OPTIONAL_ACTIVITY_MISSING",
            "severity": "info",
            "fields": ["activity"],
            "message": "Activity not specified. Evidence strength is limited; prediction reliability may be reduced.",
            "evidence": []
        })

    # Location quality check
    loc_lower = location_clean.lower()
    if location_clean and (loc_lower in PLACEHOLDERS or loc_lower in ["test", "dummy", "unknown", "n/a", "none"]):
        findings.append({
            "check_id": "INVALID_LOCATION",
            "severity": "warning",
            "fields": ["location"],
            "message": f"Location '{location}' appears to be placeholder or test data.",
            "evidence": [location],
        })

    # ── 3. Structured Field Conflicts ─────────────────────────────────────────
    # Body part consistency
    bp_clean = str(body_part).lower().strip()
    it_clean = str(injury_type).lower().strip()

    if it_clean and bp_clean:
        if "eye" in it_clean and any(part in bp_clean for part in ["leg", "foot", "arm", "hand", "back", "knee"]):
            findings.append({
                "check_id": "INJURY_BODY_PART_CONFLICT",
                "severity": "critical",
                "fields": ["injury_type", "body_part"],
                "message": f"Contradiction between injury type '{injury_type}' and body part '{body_part}'.",
                "evidence": [str(injury_type), str(body_part)]
            })

    if bp_clean:
        for canonical_part, pattern in BODY_PART_PATTERNS.items():
            if canonical_part not in bp_clean:
                match = pattern.search(comp_narrative_clean)
                if match:
                    findings.append({
                        "check_id": "INJURY_BODY_PART_CONFLICT",
                        "severity": "critical",
                        "fields": ["description", "body_part"],
                        "message": f"Narrative describes an {canonical_part} injury while the structured body-part field is recorded as '{body_part}'.",
                        "evidence": [match.group(0), str(body_part)]
                    })

    # Injury type consistency
    if it_clean:
        for canonical_type, pattern in INJURY_TYPE_PATTERNS.items():
            if canonical_type not in it_clean:
                match = pattern.search(comp_narrative_clean)
                if match:
                    findings.append({
                        "check_id": "INJURY_TYPE_CONFLICT",
                        "severity": "warning",
                        "fields": ["description", "injury_type"],
                        "message": f"Narrative mentions '{match.group(0)}' but injury_type field is '{injury_type}'.",
                        "evidence": [match.group(0), str(injury_type)]
                    })

    # Severity consistency
    sev_clean = str(severity_actual).lower().strip()
    if sev_clean in ("none", "0"):
        if re.search(r"\b(serious fracture|hospitalized|hospitalization|fatality|serious injury)\b", comp_narrative_clean):
            findings.append({
                "check_id": "SEVERITY_NARRATIVE_CONFLICT",
                "severity": "warning",
                "fields": ["description", "severity_actual"],
                "message": "Severity is recorded as 'None' but narrative mentions serious injury or hospitalization.",
                "evidence": [str(severity_actual), "serious narrative keywords"]
            })

    # Near-miss consistency
    if near_miss is True:
        if sev_clean in ("lost_time", "fatality", "death"):
            findings.append({
                "check_id": "NEAR_MISS_SEVERITY_CONFLICT",
                "severity": "critical",
                "fields": ["near_miss", "severity_actual"],
                "message": f"Contradiction: Event classified as near-miss cannot have actual severity '{severity_actual}'.",
                "evidence": ["near_miss=True", str(severity_actual)]
            })
        elif re.search(r"\b(sustained (?:a|an)? serious injury|fracture|laceration|hospitalized)\b", comp_narrative_clean):
            findings.append({
                "check_id": "NEAR_MISS_INJURY_CONFLICT",
                "severity": "warning",
                "fields": ["description", "near_miss"],
                "message": "Incident is classified as a near-miss, but narrative explicitly describes sustaining an injury.",
                "evidence": ["near_miss=True", "injury keywords"]
            })

    # Date checks & chronological contradictions
    inc_date = _parse_date_safely(incident_date_val)
    rep_date = _parse_date_safely(report_date_val)

    if inc_date:
        if inc_date > date.today():
            findings.append({
                "check_id": "FUTURE_DATE",
                "severity": "critical",
                "fields": ["incident_date"],
                "message": f"Incident date ({inc_date.isoformat()}) is in the future.",
                "evidence": [inc_date.isoformat()]
            })
        elif inc_date.year < 1970 or inc_date.year > 2050:
            findings.append({
                "check_id": "IMPOSSIBLE_DATE",
                "severity": "critical",
                "fields": ["incident_date"],
                "message": f"Incident date ({inc_date.isoformat()}) is impossible or outside valid operational bounds.",
                "evidence": [inc_date.isoformat()]
            })
        if rep_date and inc_date > rep_date:
            findings.append({
                "check_id": "CONTRADICTORY_DATE",
                "severity": "critical",
                "fields": ["incident_date", "report_date"],
                "message": "Contradictory date fields: incident date occurs after report date.",
                "evidence": [f"incident_date={inc_date.isoformat()}", f"report_date={rep_date.isoformat()}"]
            })
    else:
        findings.append({
            "check_id": "MISSING_DATE",
            "severity": "warning",
            "fields": ["incident_date"],
            "message": "Incident date is missing.",
            "evidence": []
        })

    # ── 4. Synthesize Gate Decision ───────────────────────────────────────────
    blocking_findings = [f["message"] for f in findings if f["severity"] == "critical"]
    warning_findings = [f["message"] for f in findings if f["severity"] == "warning"]

    if blocking_findings:
        overall_status = IncidentDataQuality.Status.CRITICAL
        accepted = False
        reason = "Data quality is insufficient for analysis."
        quality_score = 0.0
    elif warning_findings:
        overall_status = IncidentDataQuality.Status.WARNING
        accepted = True
        reason = None
        quality_score = 0.75
    else:
        overall_status = IncidentDataQuality.Status.VALID
        accepted = True
        reason = None
        quality_score = 1.0

    return {
        "accepted": accepted,
        "quality_status": overall_status,
        "quality_score": quality_score,
        "blocking_findings": blocking_findings,
        "warning_findings": warning_findings,
        "missing_fields": list(dict.fromkeys(missing_fields)),
        "reason": reason,
        "quality_version": VERSION,
        "findings": findings,
    }


def validate_incident_quality(incident: Incident) -> IncidentDataQuality:
    """
    The canonical data quality validation engine for persisted Incidents.
    Evaluates incident quality via validate_incident_for_analysis and persists
    the findings to IncidentDataQuality. Never modifies the original source data.
    """
    result = validate_incident_for_analysis(incident)

    dq_record, _ = IncidentDataQuality.objects.update_or_create(
        incident=incident,
        defaults={
            "status": result["quality_status"],
            "findings": result["findings"],
            "quality_version": result["quality_version"]
        }
    )

    return dq_record


import hashlib

def compute_narrative_duplicate_hash(text: Optional[str]) -> str:
    """Computes a normalized SHA-256 fingerprint from cleaned alphanumeric text."""
    if not text:
        return ""
    words = [w.lower() for w in re.findall(r"\b[a-zA-Z0-9]+\b", str(text))]
    norm = " ".join(words)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


class DataEvidenceState:
    INVALID_DATA = "INVALID_DATA"
    SPARSE_DATA = "SPARSE_DATA"
    VALID_LOW_EVIDENCE = "VALID_LOW_EVIDENCE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    VALID = "VALID"


def classify_incident_data_evidence_state(
    incident_or_data: Any,
    dq_result: Optional[Dict[str, Any]] = None,
    reasoning_assessment: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Explicitly distinguishes four separate analytical states:
    - INVALID_DATA: Record rejected by critical DQ gate (unparseable, corrupted, severe contradictions)
    - SPARSE_DATA: Record accepted with warning due to extreme brevity (< 10 words)
    - VALID_LOW_EVIDENCE: Formally valid, but lacks specific hazard or control cues
    - INSUFFICIENT_INFORMATION: Operational reasoning state where PSIF cannot be determined
    - VALID: Fully valid with sufficient evidence for analysis
    """
    if dq_result is None:
        dq_result = validate_incident_for_analysis(incident_or_data)

    if dq_result.get("quality_status") == IncidentDataQuality.Status.CRITICAL:
        return DataEvidenceState.INVALID_DATA

    # Check for sparse narrative
    findings = dq_result.get("findings", [])
    if any(f.get("check_id") in ("SHORT_NARRATIVE", "INSUFFICIENT_NARRATIVE") for f in findings):
        return DataEvidenceState.SPARSE_DATA

    # Check if incident has is_sparse_input flagged
    if hasattr(incident_or_data, "prediction") and getattr(incident_or_data.prediction, "is_sparse_input", False):
        return DataEvidenceState.SPARSE_DATA

    # Check reasoning assessment for insufficient information
    if reasoning_assessment and reasoning_assessment.get("internal_reasoning_state") == "INSUFFICIENT_INFORMATION":
        return DataEvidenceState.INSUFFICIENT_INFORMATION

    # Check for low evidence (no hazard/energy keywords in narrative)
    narrative = ""
    if isinstance(incident_or_data, Incident):
        narrative = (incident_or_data.composite_narrative or incident_or_data.description or "").lower()
    elif isinstance(incident_or_data, dict):
        narrative = (incident_or_data.get("composite_narrative") or incident_or_data.get("description") or "").lower()

    hazard_cues = ["drill", "pipe", "pressure", "crane", "fall", "height", "gas", "h2s", "fire", "electric", "leak", "tank", "valve"]
    if not any(cue in narrative for cue in hazard_cues):
        return DataEvidenceState.VALID_LOW_EVIDENCE

    return DataEvidenceState.VALID


