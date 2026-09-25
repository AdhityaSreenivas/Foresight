"""
PSIF Platform — Admin Flow Pattern Analysis Engine.
Dimension Analysis: Activity + Barrier/Control + Internal Location.

Operates exclusively over the Admin Flow demonstration dataset (workspace_id = 'admin_flow').
All uploaded incidents are assumed to belong to ONE SITE with multiple internal locations.

Defensible principles:
1. Transparency: Frequency and occurrence-based pattern detection (no opaque confidence scores).
2. Defensible Barriers: Barrier-linked observations reflect evidence-supported control states;
   never asserting causality or physical barrier failure without evidence.
3. Explicit Denominators: Percentages always state their exact denominator.
4. Independent Scoping: Operates strictly on Admin Flow data with dedicated caching.
"""

from __future__ import annotations
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Set
from django.core.cache import cache
from django.db.models import Count, Q, QuerySet

from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult
from apps.incidents.services.normalization import (
    normalize_activity,
    normalize_location,
    sanitize_string,
    CANONICAL_ACTIVITIES,
    ACTIVITY_ALIASES,
    CANONICAL_IOGP_RULES,
)
from apps.incidents.services.psif_reasoning import (
    CONTROL_EFFECTIVE_PATTERNS,
    CONTROL_COMPROMISED_PATTERNS,
    _extract_first_match_span,
)

logger = logging.getLogger(__name__)

# Canonical Admin Flow workspace identifier
ADMIN_FLOW_WORKSPACE = "admin_flow"

# Default single-site operational context
ADMIN_FLOW_SITE_NAME = "Duliajan Operational Complex"

# Evidence-supported control states that indicate a deficiency/breakdown
DEFICIENCY_CONTROL_STATES: Set[str] = {
    "ABSENT",
    "FAILED",
    "BYPASSED",
    "NOT_VERIFIED",
    "INCORRECTLY_ASSUMED",
    "PARTIALLY_EFFECTIVE",
}

# Non-deficiency states that MUST NOT be counted as failures
NON_DEFICIENCY_CONTROL_STATES: Set[str] = {
    "EFFECTIVE",
    "CONTROLLED",
    "UNKNOWN",
    "NOT_APPLICABLE",
    "PLANNED_ONLY",
    "RECOMMENDATION_ONLY",
}

# Cache configuration
CACHE_PREFIX_PATTERN_ANALYSIS = "admin_flow:pattern_analysis"
CACHE_VERSION_KEY = "admin_flow:pattern_analysis:version"
CACHE_TTL_PATTERN = 1800  # 30 minutes

# Canonical internal locations for Admin Flow single-site context
CANONICAL_INTERNAL_LOCATIONS: List[str] = [
    "Compressor Area",
    "Wellhead Area",
    "Workshop / Maintenance Bay",
    "Tank Farm",
    "Pipe Rack / Manifold",
    "Drilling Area / Rig Floor",
    "Warehouse / Storage Yard",
    "Process Area / Refining Unit",
    "Electrical Substation",
    "Control Room",
    "Flare Area",
    "Produced Water Treatment",
    "Main Gate / Access Control",
]

INTERNAL_LOCATION_ALIASES: Dict[str, str] = {
    "compressor": "Compressor Area",
    "compressor area": "Compressor Area",
    "compressor station": "Compressor Area",
    "compressor house": "Compressor Area",
    "gas compression": "Compressor Area",
    "wellhead": "Wellhead Area",
    "well head": "Wellhead Area",
    "wellhead area": "Wellhead Area",
    "wellhead platform": "Wellhead Area",
    "whp": "Wellhead Area",
    "christmas tree": "Wellhead Area",
    "workshop": "Workshop / Maintenance Bay",
    "maintenance bay": "Workshop / Maintenance Bay",
    "mech shop": "Workshop / Maintenance Bay",
    "central workshop": "Workshop / Maintenance Bay",
    "bay 1": "Workshop / Maintenance Bay",
    "bay 2": "Workshop / Maintenance Bay",
    "maintenance bay 1": "Workshop / Maintenance Bay",
    "maintenance bay 2": "Workshop / Maintenance Bay",
    "tank farm": "Tank Farm",
    "tankfarm": "Tank Farm",
    "storage tanks": "Tank Farm",
    "crude tanks": "Tank Farm",
    "pipe rack": "Pipe Rack / Manifold",
    "pipe rack area": "Pipe Rack / Manifold",
    "manifold": "Pipe Rack / Manifold",
    "pipeline row": "Pipe Rack / Manifold",
    "drilling area": "Drilling Area / Rig Floor",
    "drill floor": "Drilling Area / Rig Floor",
    "rig floor": "Drilling Area / Rig Floor",
    "derrick": "Drilling Area / Rig Floor",
    "warehouse": "Warehouse / Storage Yard",
    "storage yard": "Warehouse / Storage Yard",
    "pipe yard": "Warehouse / Storage Yard",
    "process area": "Process Area / Refining Unit",
    "process unit": "Process Area / Refining Unit",
    "refining unit": "Process Area / Refining Unit",
    "substation": "Electrical Substation",
    "electrical substation": "Electrical Substation",
    "switchgear room": "Electrical Substation",
    "transformer yard": "Electrical Substation",
    "control room": "Control Room",
    "ccr": "Control Room",
    "flare": "Flare Area",
    "flare area": "Flare Area",
    "flare pit": "Flare Area",
    "flare stack": "Flare Area",
    "water treatment": "Produced Water Treatment",
    "produced water": "Produced Water Treatment",
    "main gate": "Main Gate / Access Control",
    "gate": "Main Gate / Access Control",
    "security gate": "Main Gate / Access Control",
    "entry gate": "Main Gate / Access Control",
    "access control": "Main Gate / Access Control",
    # Legitimate observed locations outside schematic 9-grid taxonomy
    "parking area": "Parking Area",
    "parking lot": "Parking Area",
    "basement pump room": "Basement Pump Room",
    "pump room": "Pump Room",
    "loading dock": "Loading Dock",
    "loading dock a": "Loading Dock A",
    "loading dock b": "Loading Dock B",
}

# Activity alias overrides to ensure prompt specifications match exactly
EXTRA_ACTIVITY_ALIASES: Dict[str, str] = {
    "crane lifting": "Safe Mechanical Lifting",
    "material lifting": "Safe Mechanical Lifting",
    "lifting operation": "Safe Mechanical Lifting",
    "lifting operations": "Safe Mechanical Lifting",
    "crane operation": "Safe Mechanical Lifting",
    "rigging operation": "Safe Mechanical Lifting",
    "pressure-line maintenance / flange breaking": "Pressure-Line Maintenance / Flange Breaking",
    "pressure-line maintenance": "Pressure-Line Maintenance / Flange Breaking",
    "flange breaking": "Pressure-Line Maintenance / Flange Breaking",
    # ── Admin Flow dataset job_task values unmapped by normalization layer ──
    "line of fire work": "Line of Fire / Dropped Objects",
    "line of fire": "Line of Fire / Dropped Objects",
    "bypass / override work": "Bypassing Safety Controls / Defeating Devices",
    "bypass/override work": "Bypassing Safety Controls / Defeating Devices",
    "bypass override work": "Bypassing Safety Controls / Defeating Devices",
    "bypassing safety controls": "Bypassing Safety Controls / Defeating Devices",
    "overriding safety controls": "Bypassing Safety Controls / Defeating Devices",
}


@dataclass
class PatternObservation:
    """
    Reusable internal representation of an evaluated dimension observation.
    """
    incident_id: str
    workspace: str
    dimension: str                    # "activity" | "barrier" | "location"
    normalized_value: str
    date: Optional[str] = None        # "YYYY-MM-DD"
    psif_state: str = "NOT_PSIF"      # "PSIF" | "NOT_PSIF" | "INSUFFICIENT_INFORMATION"
    evidence_state: str = "ELIGIBLE"  # "ELIGIBLE" | "INSUFFICIENT_EVIDENCE"
    source_field: str = ""
    normalization_method: str = "unknown"
    # Barrier-specific attributes:
    control_state: Optional[str] = None
    control: Optional[str] = None
    iogp_rule: Optional[str] = None
    location: Optional[str] = None
    description: str = ""
    job_task: str = ""
    raw_value: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Cache Version Management ──────────────────────────────────────────────────

def get_admin_flow_pattern_cache_version() -> int:
    """Returns the current cache version number for Admin Flow pattern analysis."""
    version = cache.get(CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(CACHE_VERSION_KEY, version, timeout=None)
    return version


def invalidate_admin_flow_pattern_cache() -> None:
    """
    Increments the cache version, immediately invalidating all cached
    Admin Flow pattern analysis results without affecting global caches.
    """
    try:
        cache.incr(CACHE_VERSION_KEY)
    except Exception:
        # Fallback if key doesn't exist or backend doesn't support incr
        curr = get_admin_flow_pattern_cache_version()
        cache.set(CACHE_VERSION_KEY, curr + 1, timeout=None)
    try:
        from apps.admin_flow.barrier_service import invalidate_admin_flow_barrier_cache
        invalidate_admin_flow_barrier_cache()
    except Exception as e:
        logger.warning("Failed to invalidate barrier cache: %s", e)
    try:
        from apps.admin_flow.activity_service import invalidate_admin_flow_activity_cache
        invalidate_admin_flow_activity_cache()
    except Exception as e:
        logger.warning("Failed to invalidate activity cache: %s", e)
    logger.info("Admin Flow pattern analysis cache invalidated (version bumped).")


# ── Dimension Normalization Functions ─────────────────────────────────────────

NARRATIVE_ACTIVITY_STOP_WORDS = (
    r"(?:reported|resulted|sustained|suffered|experienced|noticed|observed|felt|"
    r"injured|slipped|tripped|dropped|fell|lost|struck|contacted|was|were)"
)

NARRATIVE_ACTIVITY_PATTERNS = [
    rf"while performing\s+([^,.;]+?)(?:\s+(?:in|at|on|near|with|during|inside)\s+|\s+{NARRATIVE_ACTIVITY_STOP_WORDS}\b|,|\.|$)",
    rf"working on\s+([^,.;]+?)(?:\s+(?:in|at|near|with|during|inside)\s+|\s+{NARRATIVE_ACTIVITY_STOP_WORDS}\b|,|\.|$)",
    rf"during\s+([^,.;]+?)(?:\s+(?:in|at|near|with|operations|activities)\s+|\s+{NARRATIVE_ACTIVITY_STOP_WORDS}\b|,|\.|$)",
    rf"while conducting\s+([^,.;]+?)(?:\s+(?:in|at|on|near|with|during)\s+|\s+{NARRATIVE_ACTIVITY_STOP_WORDS}\b|,|\.|$)",
    rf"engaged in\s+([^,.;]+?)(?:\s+(?:in|at|on|near|with|during)\s+|\s+{NARRATIVE_ACTIVITY_STOP_WORDS}\b|,|\.|$)",
    rf"carrying out\s+([^,.;]+?)(?:\s+(?:in|at|on|near|with|during)\s+|\s+{NARRATIVE_ACTIVITY_STOP_WORDS}\b|,|\.|$)",
    rf"undertaking\s+([^,.;]+?)(?:\s+(?:in|at|on|near|with|during)\s+|\s+{NARRATIVE_ACTIVITY_STOP_WORDS}\b|,|\.|$)",
]


def extract_activity_from_narrative(narrative: Optional[str]) -> Optional[str]:
    """
    Extracts an activity phrase describing the work being performed from an incident narrative.
    """
    if not narrative or not str(narrative).strip():
        return None
    text = str(narrative).strip()

    for pattern in NARRATIVE_ACTIVITY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            # Clean leading determiners and routine prefixes
            candidate = re.sub(r"^(the|a|an|routine)\s+", "", candidate, flags=re.IGNORECASE).strip()
            # Clean trailing stop words if captured
            candidate = re.sub(rf"\s+{NARRATIVE_ACTIVITY_STOP_WORDS}.*$", "", candidate, flags=re.IGNORECASE).strip()
            # Clean any trailing prepositions
            candidate = re.sub(r"\s+(?:in|at|on|near|with|during|inside)$", "", candidate, flags=re.IGNORECASE).strip()
            # Accept if concise phrase (1 to 5 words)
            if 0 < len(candidate.split()) <= 5:
                return candidate

    return None


def normalize_admin_flow_activity(
    raw_value: Optional[str] = None,
    narrative: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Normalizes an activity string or extracts it from narrative into a canonical or observed activity category.
    Returns: (canonical_or_observed_activity, normalization_method)
    Delegates to the canonical Activity Intelligence Engine.
    """
    from apps.admin_flow.activity_engine import normalize_admin_flow_activity as _norm_activity
    disp_name, cat, method = _norm_activity(raw_value=raw_value, narrative=narrative)
    return (disp_name, method)


def normalize_admin_flow_location(incident: Incident) -> Tuple[str, str, str]:
    """
    Extracts and normalizes the internal location for an Admin Flow incident.
    Assumes all incidents belong to ONE SITE (Duliajan context) with internal locations.
    Returns: (normalized_location, source_field, normalization_method)
    """
    # 1. Structured location field — but only use it if it provides meaningful
    #    sub-location information, not just the top-level site/complex name.
    raw_loc = getattr(incident, "location", None)
    if raw_loc and str(raw_loc).strip():
        cleaned = sanitize_string(raw_loc)
        cleaned_lower = cleaned.lower()

        # Skip site-level name — not an internal location; fall through to narrative.
        site_name_lower = ADMIN_FLOW_SITE_NAME.lower()
        if cleaned_lower == site_name_lower or cleaned_lower == "duliajan operational complex":
            pass  # intentional fall-through: use narrative extraction below
        else:
            if cleaned_lower in INTERNAL_LOCATION_ALIASES:
                return (INTERNAL_LOCATION_ALIASES[cleaned_lower], "location", "exact_alias")
            for alias, canon in INTERNAL_LOCATION_ALIASES.items():
                if alias in cleaned_lower:
                    return (canon, "location", "exact_alias")
            # Return title-cased structured value if not mapped to a preset
            return (cleaned.title(), "location", "structured_identity")

    # 2. Check metadata dictionary for zone/work_area/component
    meta = getattr(incident, "metadata", {}) or {}
    if isinstance(meta, dict):
        for field_key in ["work_area", "zone", "operating_area", "facility_component"]:
            val = meta.get(field_key)
            if val and str(val).strip():
                cleaned = sanitize_string(str(val))
                cleaned_lower = cleaned.lower()
                if cleaned_lower in INTERNAL_LOCATION_ALIASES:
                    return (INTERNAL_LOCATION_ALIASES[cleaned_lower], f"metadata.{field_key}", "exact_alias")
                return (cleaned.title(), f"metadata.{field_key}", "metadata_identity")

    # 3. Narrative extraction (CRITICAL: Extract from narrative BEFORE department fallback!)
    narrative = incident.composite_narrative or incident.description or ""
    narrative_lower = narrative.lower()
    for alias, canon in INTERNAL_LOCATION_ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", narrative_lower):
            return (canon, "composite_narrative", "narrative_extraction")

    # Dynamic prepositional location extraction from narrative ("in Parking Area", "at Loading Dock A")
    prep_match = re.search(r"\b(?:in|at|near|inside)\s+([A-Z][A-Za-z0-9\s/]+?)(?:\.|\,|\[|\;|\n|$)", narrative)
    if prep_match:
        cand_loc = prep_match.group(1).strip()
        cand_loc_clean = re.sub(r"^(the|a|an)\s+", "", cand_loc, flags=re.IGNORECASE).strip()
        cand_lower = cand_loc_clean.lower()
        if cand_lower in INTERNAL_LOCATION_ALIASES:
            return (INTERNAL_LOCATION_ALIASES[cand_lower], "composite_narrative", "narrative_extraction")
        ANATOMICAL_WORDS = {"left", "right", "foot", "hand", "arm", "forearm", "leg", "eye", "head", "finger", "back", "chest", "face", "none", "null", "unknown", "na"}
        words = set(cand_lower.split())
        if not (words & ANATOMICAL_WORDS) and 1 <= len(cand_loc_clean.split()) <= 4:
            return (cand_loc_clean.title(), "composite_narrative", "narrative_extraction")

    # 4. Department fallback ONLY for unambiguous physical shop/area designations
    dept = getattr(incident, "department", None)
    if dept and str(dept).strip():
        dept_lower = str(dept).strip().lower()
        if "central workshop" in dept_lower or dept_lower == "workshop":
            return ("Workshop / Maintenance Bay", "department", "inferred")
        elif "drilling rig" in dept_lower or dept_lower == "drilling":
            return ("Drilling Area / Rig Floor", "department", "inferred")
        elif dept_lower == "refinery" or dept_lower == "refining":
            return ("Process Area / Refining Unit", "department", "inferred")

    return ("UNKNOWN LOCATION", "none", "unknown")


def extract_admin_flow_barrier_observations(incident: Incident) -> List[Dict[str, Any]]:
    """
    Evaluates evidence-supported physical and operational protective barriers
    described in an incident. Uses the canonical Barrier Intelligence Engine.

    Important Principles:
    - Never asserts causality or barrier degradation without evidence.
    - DEFICIENCY STATES: ABSENT, FAILED, BYPASSED, NOT_VERIFIED, INCORRECTLY_ASSUMED, PARTIALLY_EFFECTIVE.
    - NON-DEFICIENCY STATES: EFFECTIVE, RESTORED_BEFORE_EXPOSURE, UNKNOWN, RECOMMENDATION_ONLY, PLANNED_ONLY.
    - Decouples actual protective barriers from IOGP safety rule domains.
    """
    from apps.admin_flow.barrier_engine import extract_incident_barriers

    barriers = extract_incident_barriers(incident)
    results = []
    for b in barriers:
        results.append({
            "control": b.barrier_name,
            "barrier_category": b.barrier_category,
            "barrier_name": b.barrier_name,
            "control_state": b.barrier_state,
            "barrier_state": b.barrier_state,
            "barrier_role": b.barrier_role,
            "is_deficiency": b.is_deficient,
            "is_effective": b.is_effective,
            "source_field": b.source_field,
            "evidence_span": b.evidence_span,
            "iogp_rule": b.iogp_rule,
        })
    return results


# ── Core Pattern Observation Extraction ───────────────────────────────────────

def extract_all_admin_flow_pattern_observations(
    incidents_qs: Optional[QuerySet[Incident]] = None,
) -> List[PatternObservation]:
    """
    Extracts structured PatternObservation records for all 3 dimensions
    across the Admin Flow demonstration dataset.
    """
    if incidents_qs is None:
        incidents_qs = (
            Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE)
            .select_related("prediction")
            .prefetch_related("iogp_rules")
            .order_by("-incident_date", "-created_at")
        )

    observations: List[PatternObservation] = []

    for inc in incidents_qs:
        inc_id = str(inc.id)
        inc_date = (
            inc.incident_date.isoformat()
            if hasattr(inc.incident_date, "isoformat")
            else (str(inc.incident_date) if inc.incident_date else None)
        )

        # Evaluate PSIF & evidence state
        has_pred = hasattr(inc, "prediction") and inc.prediction is not None
        if has_pred and inc.prediction.is_sparse_input:
            psif_state = "INSUFFICIENT_INFORMATION"
            evidence_state = "INSUFFICIENT_EVIDENCE"
        elif has_pred and inc.prediction.psif_predicted:
            psif_state = "PSIF"
            evidence_state = "ELIGIBLE"
        elif has_pred:
            psif_state = "NOT_PSIF"
            evidence_state = "ELIGIBLE"
        else:
            psif_state = "UNKNOWN"
            evidence_state = "ELIGIBLE"

        inc_desc = inc.description or ""
        inc_task = inc.job_task or ""

        # Normalize Location first (needed for all dimensions)
        loc_val, loc_field, loc_method = normalize_admin_flow_location(inc)

        # 1. Activity Dimension
        act_val, act_method = normalize_admin_flow_activity(
            raw_value=inc.job_task,
            narrative=inc.composite_narrative or inc.description,
        )
        act_source = "composite_narrative" if act_method == "narrative_extraction" else "job_task"
        observations.append(
            PatternObservation(
                incident_id=inc_id,
                workspace=ADMIN_FLOW_WORKSPACE,
                dimension="activity",
                normalized_value=act_val,
                date=inc_date,
                psif_state=psif_state,
                evidence_state=evidence_state,
                source_field=act_source,
                normalization_method=act_method,
                location=loc_val,
                description=inc_desc,
                job_task=inc_task,
                raw_value=inc.job_task or act_val,
            )
        )

        # 2. Location Dimension (Single-site internal locations)
        observations.append(
            PatternObservation(
                incident_id=inc_id,
                workspace=ADMIN_FLOW_WORKSPACE,
                dimension="location",
                normalized_value=loc_val,
                date=inc_date,
                psif_state=psif_state,
                evidence_state=evidence_state,
                source_field=loc_field,
                normalization_method=loc_method,
                location=loc_val,
                description=inc_desc,
                job_task=inc_task,
                raw_value=getattr(inc, "location", None) or loc_val,
            )
        )

        # 3. Barrier / Control Dimension
        barrier_data = extract_admin_flow_barrier_observations(inc)
        for b in barrier_data:
            observations.append(
                PatternObservation(
                    incident_id=inc_id,
                    workspace=ADMIN_FLOW_WORKSPACE,
                    dimension="barrier",
                    normalized_value=b["control"],
                    date=inc_date,
                    psif_state=psif_state,
                    evidence_state=evidence_state,
                    source_field=b["source_field"],
                    normalization_method="evidence_reasoning",
                    control_state=b["control_state"],
                    control=b["control"],
                    iogp_rule=b["iogp_rule"],
                    location=loc_val,
                    description=inc_desc,
                    job_task=inc_task,
                )
            )

    return observations


# ── Pattern Aggregation & Ranking Functions ───────────────────────────────────

def compute_activity_patterns(observations: List[PatternObservation]) -> List[Dict[str, Any]]:
    """
    Aggregates activity observations and returns categories sorted descending by incident count.
    PSIF-linked rate is explicitly labeled with denominator definition.
    """
    act_obs = [o for o in observations if o.dimension == "activity"]
    grouped: Dict[str, Dict[str, Any]] = {}

    for o in act_obs:
        cat = o.normalized_value
        if cat not in grouped:
            grouped[cat] = {
                "category": cat,
                "incident_ids": set(),
                "psif_incident_ids": set(),
                "normalization_method": o.normalization_method,
            }
        grouped[cat]["incident_ids"].add(o.incident_id)
        if o.psif_state == "PSIF":
            grouped[cat]["psif_incident_ids"].add(o.incident_id)

    results = []
    for cat, data in grouped.items():
        count = len(data["incident_ids"])
        psif_count = len(data["psif_incident_ids"])
        rate = round((psif_count / count) * 100, 1) if count > 0 else 0.0

        results.append({
            "category": cat,
            "incident_count": count,
            "psif_linked_count": psif_count,
            "psif_linkage_rate": rate,
            "rate_label": f"{rate}% PSIF-linked among matched Admin Flow observations (denominator: {count})",
            "is_recurring": count >= 2,
            "normalization_method": data["normalization_method"],
            "sample_incident_ids": list(data["incident_ids"])[:10],
        })

    # Sort descending by incident count, then alphabetically
    results.sort(key=lambda x: (-x["incident_count"], x["category"]))
    return results


def compute_barrier_patterns(observations: List[PatternObservation]) -> List[Dict[str, Any]]:
    """
    Aggregates barrier observations and returns categories sorted descending
    by occurrence and evidence-supported deficiency-linked incident count.
    """
    from collections import Counter
    from apps.admin_flow.barrier_engine import DEFICIENT_BARRIER_STATES, EFFECTIVE_BARRIER_STATES

    barrier_obs = [o for o in observations if o.dimension == "barrier"]
    grouped: Dict[str, Dict[str, Any]] = {}

    for o in barrier_obs:
        cat = o.normalized_value
        if cat not in grouped:
            grouped[cat] = {
                "control_domain": cat,
                "barrier_name": cat,
                "deficiency_incident_ids": set(),
                "effective_incident_ids": set(),
                "total_matched_incident_ids": set(),
                "psif_incident_ids": set(),
                "affected_locations": set(),
                "state_breakdown": Counter(),
                "iogp_rules": Counter(),
            }
        grouped[cat]["total_matched_incident_ids"].add(o.incident_id)
        grouped[cat]["state_breakdown"][o.control_state] += 1
        if o.iogp_rule and o.iogp_rule not in ["None Associated", "Unknown", "none"]:
            grouped[cat]["iogp_rules"][o.iogp_rule] += 1

        if o.control_state in EFFECTIVE_BARRIER_STATES:
            grouped[cat]["effective_incident_ids"].add(o.incident_id)

        if o.control_state in DEFICIENT_BARRIER_STATES:
            grouped[cat]["deficiency_incident_ids"].add(o.incident_id)

        if o.psif_state == "PSIF":
            grouped[cat]["psif_incident_ids"].add(o.incident_id)

        if o.location and o.location != "UNKNOWN LOCATION":
            grouped[cat]["affected_locations"].add(o.location)

    results = []
    for cat, data in grouped.items():
        total_matched = len(data["total_matched_incident_ids"])
        deficiency_count = len(data["deficiency_incident_ids"])
        effective_count = len(data["effective_incident_ids"])
        psif_count = len(data["psif_incident_ids"])

        rate = round((psif_count / total_matched) * 100, 1) if total_matched > 0 else 0.0

        aff_locs = sorted(list(data["affected_locations"]))
        aff_locs_count = len(aff_locs)

        dominant_state = data["state_breakdown"].most_common(1)[0][0] if data["state_breakdown"] else "UNKNOWN"
        top_iogp = data["iogp_rules"].most_common(1)[0][0] if data["iogp_rules"] else "None Associated"

        results.append({
            "barrier_domain": cat,
            "barrier_name": cat,
            "deficiency_linked_count": deficiency_count,
            "effective_count": effective_count,
            "total_matched_count": total_matched,
            "associated_incidents_count": total_matched,
            "psif_linked_count": psif_count,
            "psif_linkage_rate": rate,
            "rate_label": f"{rate}% PSIF-linked ({psif_count}/{total_matched})",
            "is_recurring": total_matched >= 2,
            "affected_locations": aff_locs,
            "affected_locations_count": aff_locs_count,
            "dominant_control_state": dominant_state,
            "dominant_state": dominant_state,
            "associated_iogp_rule": top_iogp,
            "is_iogp_rule": False,
            "iogp_crosslink_label": f"Associated IOGP: {top_iogp}" if top_iogp != "None Associated" else "Operational Safeguard",
            "state_breakdown": dict(data["state_breakdown"]),
            "concept_label": "Protective Barrier Observation",
            "sample_incident_ids": list(data["total_matched_incident_ids"])[:10],
        })

    # Sort descending by total associated incident count, then deficiency count
    results.sort(key=lambda x: (-x["total_matched_count"], -x["deficiency_linked_count"], x["barrier_domain"]))
    return results


def compute_location_patterns(observations: List[PatternObservation]) -> List[Dict[str, Any]]:
    """
    Aggregates internal location observations and returns locations sorted descending by incident count.
    Calculates for each location:
    - incident_count, psif_linked_count, psif_linkage_rate
    - top_activity, top_activities list
    - top_barrier_linked_signal, top_barriers list
    - pattern_chain: Location -> Top Activity -> Top Barrier-linked signal ("Observed relationship in Admin Flow data.")
    - heatmap_intensity (0.0 - 1.0 continuous scale), heat_level, heat_color
    - recent_observations: sample recent observations for drill-down
    """
    from collections import Counter

    loc_obs = [o for o in observations if o.dimension == "location"]
    grouped: Dict[str, Dict[str, Any]] = {}
    activities_by_loc: Dict[str, Counter] = {}
    barriers_by_loc: Dict[str, Counter] = {}
    iogp_by_loc: Dict[str, Counter] = {}
    incidents_by_loc: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for o in observations:
        loc = o.location or "UNKNOWN LOCATION"
        if loc not in activities_by_loc:
            activities_by_loc[loc] = Counter()
        if loc not in barriers_by_loc:
            barriers_by_loc[loc] = Counter()
        if loc not in iogp_by_loc:
            iogp_by_loc[loc] = Counter()
        if loc not in incidents_by_loc:
            incidents_by_loc[loc] = {}

        if o.dimension == "activity":
            activities_by_loc[loc][o.normalized_value] += 1
            if o.incident_id not in incidents_by_loc[loc]:
                incidents_by_loc[loc][o.incident_id] = {
                    "incident_id": o.incident_id,
                    "date": o.date or "N/A",
                    "task": o.job_task or o.normalized_value,
                    "summary": (o.description[:140] + "...") if len(o.description) > 140 else (o.description or o.normalized_value),
                    "is_psif": o.psif_state == "PSIF",
                    "activity": o.normalized_value,
                    "barrier": "None Observed",
                    "iogp_rule": "—",
                }
            else:
                incidents_by_loc[loc][o.incident_id]["activity"] = o.normalized_value

        elif o.dimension == "barrier":
            rule_name = o.iogp_rule or o.normalized_value
            if rule_name and rule_name.lower() not in ["none", "unknown", "n/a", ""]:
                iogp_by_loc[loc][rule_name] += 1

            if o.control_state in DEFICIENCY_CONTROL_STATES:
                barriers_by_loc[loc][o.normalized_value] += 1
                if o.incident_id in incidents_by_loc[loc]:
                    incidents_by_loc[loc][o.incident_id]["barrier"] = o.normalized_value
                    if rule_name:
                        incidents_by_loc[loc][o.incident_id]["iogp_rule"] = rule_name
            elif rule_name and o.incident_id in incidents_by_loc[loc]:
                if incidents_by_loc[loc][o.incident_id].get("iogp_rule") in ["—", "", None]:
                    incidents_by_loc[loc][o.incident_id]["iogp_rule"] = rule_name

    for o in loc_obs:
        loc = o.normalized_value
        if loc not in grouped:
            grouped[loc] = {
                "internal_location": loc,
                "incident_ids": set(),
                "psif_incident_ids": set(),
                "source_field": o.source_field,
            }
        grouped[loc]["incident_ids"].add(o.incident_id)
        if o.psif_state == "PSIF":
            grouped[loc]["psif_incident_ids"].add(o.incident_id)

    results = []
    max_count = max([len(d["incident_ids"]) for d in grouped.values()], default=1) or 1

    for loc, data in grouped.items():
        count = len(data["incident_ids"])
        psif_count = len(data["psif_incident_ids"])
        rate = round((psif_count / count) * 100, 1) if count > 0 else 0.0

        # Intensity score 0.0 - 1.0 for heatmap rendering
        intensity = round(count / max_count, 2) if max_count > 0 else 0.0

        # Continuous heat level and color
        if count == 0:
            heat_level = "zero"
            heat_color = "#475569"
            heat_label = "ZERO"
        elif intensity >= 0.75:
            heat_level = "critical"
            heat_color = "#C62828"
            heat_label = "VERY HIGH"
        elif intensity >= 0.50:
            heat_level = "elevated"
            heat_color = "#E65100"
            heat_label = "HIGH"
        elif intensity >= 0.25:
            heat_level = "moderate"
            heat_color = "#F57F17"
            heat_label = "MODERATE"
        else:
            heat_level = "low"
            heat_color = "#2E7D32"
            heat_label = "LOW"

        # Top activity and barrier for this location
        act_counter = activities_by_loc.get(loc, Counter())
        top_activity = act_counter.most_common(1)[0][0] if act_counter else "General Site Operations"
        top_activities = [{"activity": k, "count": v} for k, v in act_counter.most_common(5)]

        bar_counter = barriers_by_loc.get(loc, Counter())
        top_barrier = bar_counter.most_common(1)[0][0] if bar_counter else "None Observed"
        top_barriers = [{"barrier": k, "count": v} for k, v in bar_counter.most_common(5)]

        iogp_counter = iogp_by_loc.get(loc, Counter())
        top_iogp = iogp_counter.most_common(1)[0][0] if iogp_counter else "General Safety Controls"

        # Pattern relationship chain (Location -> Activity -> Barrier)
        pattern_chain = {
            "location": loc,
            "top_activity": top_activity,
            "top_barrier": top_barrier,
            "top_iogp_rule": top_iogp,
            "psif_count": psif_count,
            "relationship_label": "Observed relationship in Admin Flow data.",
        }

        # Recent observations sample (up to 15)
        recent_obs = list(incidents_by_loc.get(loc, {}).values())
        recent_obs.sort(key=lambda x: x.get("date", ""), reverse=True)
        recent_observations = recent_obs[:15]

        results.append({
            "internal_location": loc,
            "site_context": ADMIN_FLOW_SITE_NAME,
            "incident_count": count,
            "psif_linked_count": psif_count,
            "psif_linkage_rate": rate,
            "rate_label": f"{rate}% PSIF-linked among matched location observations (denominator: {count})",
            "heatmap_intensity": intensity,
            "heat_level": heat_level,
            "heat_color": heat_color,
            "heat_label": heat_label,
            "top_activity": top_activity,
            "top_activities": top_activities,
            "top_barrier_linked_signal": top_barrier,
            "top_barriers": top_barriers,
            "top_iogp_rule": top_iogp,
            "pattern_chain": pattern_chain,
            "recent_observations": recent_observations,
            "is_recurring": count >= 2,
            "sample_incident_ids": list(data["incident_ids"])[:10],
        })

    # Sort descending by incident count, then alphabetically
    results.sort(key=lambda x: (-x["incident_count"], x["internal_location"]))
    return results


def compute_temporal_patterns(observations: List[PatternObservation]) -> List[Dict[str, Any]]:
    """
    Computes transparent monthly incident and PSIF recurrence without predictive forecasting.
    """
    grouped: Dict[str, Dict[str, Any]] = {}

    for o in observations:
        if o.dimension != "activity":  # count distinct incidents once per period
            continue
        period = o.date[:7] if o.date and len(o.date) >= 7 else "Undated"
        if period not in grouped:
            grouped[period] = {
                "period": period,
                "incident_ids": set(),
                "psif_incident_ids": set(),
            }
        grouped[period]["incident_ids"].add(o.incident_id)
        if o.psif_state == "PSIF":
            grouped[period]["psif_incident_ids"].add(o.incident_id)

    results = []
    for period, data in grouped.items():
        count = len(data["incident_ids"])
        psif_count = len(data["psif_incident_ids"])
        results.append({
            "period": period,
            "incident_count": count,
            "psif_linked_count": psif_count,
        })

    results.sort(key=lambda x: x["period"])
    return results


# ── Consolidated Pattern Analysis Engine Facade ───────────────────────────────

def get_admin_flow_pattern_summary(use_cache: bool = True) -> Dict[str, Any]:
    """
    Authoritative facade returning consolidated pattern analysis across:
    1. Activity Patterns
    2. Barrier / Control-Deficiency Patterns
    3. Internal Location Patterns (Heatmap Ready)
    4. Temporal Recurrence View

    Derived strictly from Admin Flow records with scoped caching.
    """
    version = get_admin_flow_pattern_cache_version()
    cache_key = f"{CACHE_PREFIX_PATTERN_ANALYSIS}:{version}"

    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return cached

    # Query only Admin Flow records
    observations = extract_all_admin_flow_pattern_observations()

    activity_patterns = compute_activity_patterns(observations)
    barrier_patterns = compute_barrier_patterns(observations)
    location_patterns = compute_location_patterns(observations)
    temporal_patterns = compute_temporal_patterns(observations)

    total_incidents = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).count()
    distinct_recurring_activities = len([a for a in activity_patterns if a["is_recurring"]])
    distinct_recurring_barriers = len([b for b in barrier_patterns if b["is_recurring"]])
    distinct_recurring_locations = len([l for l in location_patterns if l["is_recurring"]])

    summary = {
        "workspace_id": ADMIN_FLOW_WORKSPACE,
        "site_context": ADMIN_FLOW_SITE_NAME,
        "total_incidents": total_incidents,
        "has_data": total_incidents > 0,
        "activity_patterns": activity_patterns,
        "barrier_patterns": barrier_patterns,
        "location_patterns": location_patterns,
        "temporal_patterns": temporal_patterns,
        "recurring_counts": {
            "activities": distinct_recurring_activities,
            "barriers": distinct_recurring_barriers,
            "locations": distinct_recurring_locations,
        },
        "methodology_disclaimers": {
            "scope": "Pattern analysis is performed strictly on the Admin Flow demonstration dataset.",
            "causality": "Patterns represent historical frequency and recurrence; they do not establish causation or predictive probability.",
            "barrier_semantics": (
                "Barrier-linked observations reflect evidence-grounded control deficiency associations, "
                "not automatically confirmed barrier failures or physical degradation."
            ),
        },
    }

    if use_cache:
        cache.set(cache_key, summary, timeout=CACHE_TTL_PATTERN)

    return summary


def get_admin_flow_activity_pattern_view_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    psif_filter: Optional[str] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dedicated view data builder for the Activity Pattern Analysis page.
    Delegates to the authoritative ActivityPatternService.
    """
    from apps.admin_flow.activity_service import ActivityPatternService

    data = ActivityPatternService.get_activity_pattern_view_data(
        date_from=date_from,
        date_to=date_to,
        psif_filter=psif_filter,
        query=query,
    )
    has_active_filters = bool(
        (date_from and date_from.strip()) or
        (date_to and date_to.strip()) or
        (psif_filter and psif_filter != "all") or
        (query and query.strip())
    )
    data["has_active_filters"] = has_active_filters
    data["filters"] = {
        "date_from": date_from or "",
        "date_to": date_to or "",
        "psif_filter": psif_filter or "all",
        "query": query or "",
    }
    return data


def get_admin_flow_barrier_pattern_view_data(
    psif_filter: Optional[str] = None,
    control_state_filter: Optional[str] = None,
    location_filter: Optional[str] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dedicated view data builder for the Barrier Intelligence Pattern Analysis page.
    Delegates to the canonical BarrierPatternService.
    """
    from apps.admin_flow.barrier_service import BarrierPatternService

    return BarrierPatternService.get_barrier_pattern_view_data(
        psif_filter=psif_filter,
        state_filter=control_state_filter,
        location_filter=location_filter,
        query=query,
    )



def get_admin_flow_location_pattern_view_data(
    psif_filter: Optional[str] = None,
    activity_filter: Optional[str] = None,
    barrier_filter: Optional[str] = None,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dedicated view data builder for the Location-Based Pattern Analysis page (Task 6).
    Produces:
    - Schematic Site Heatmap data (3x3 grid + auxiliary zones)
    - Location ranking table data sorted descending by incident count
    - Top location callout (Highest Observation Concentration)
    - Click drill-down details with pattern relationship chains
    - Filter support (PSIF status, query) with dynamic denominator recomputation
    """
    qs = (
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE)
        .select_related("prediction")
        .prefetch_related("iogp_rules")
        .order_by("-incident_date", "-created_at")
    )

    # 1. Query filter
    if query and query.strip():
        q_clean = query.strip()
        qs = qs.filter(
            Q(job_task__icontains=q_clean) |
            Q(description__icontains=q_clean) |
            Q(location__icontains=q_clean)
        )

    # 2. PSIF classification filter
    if psif_filter == "psif":
        qs = qs.filter(prediction__psif_predicted=True, prediction__is_sparse_input=False)
    elif psif_filter == "not_psif":
        qs = qs.filter(prediction__psif_predicted=False, prediction__is_sparse_input=False)
    elif psif_filter == "insufficient":
        qs = qs.filter(prediction__is_sparse_input=True)

    total_workspace_incidents = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).count()
    total_filtered_incidents = qs.count()

    observations = extract_all_admin_flow_pattern_observations(qs)

    # 3. Activity filter
    if activity_filter and activity_filter.strip() and activity_filter != "all":
        act_clean = activity_filter.strip().lower()
        matching_inc_ids = {
            o.incident_id for o in observations
            if o.dimension == "activity" and (act_clean in o.normalized_value.lower())
        }
        observations = [o for o in observations if o.incident_id in matching_inc_ids]
        total_filtered_incidents = len(matching_inc_ids)

    # 4. Barrier filter
    if barrier_filter and barrier_filter.strip() and barrier_filter != "all":
        bar_clean = barrier_filter.strip().lower()
        matching_inc_ids = {
            o.incident_id for o in observations
            if o.dimension == "barrier" and o.control_state in DEFICIENCY_CONTROL_STATES and (bar_clean in o.normalized_value.lower())
        }
        observations = [o for o in observations if o.incident_id in matching_inc_ids]
        total_filtered_incidents = len(matching_inc_ids)

    raw_locations = compute_location_patterns(observations)

    # Enrich locations with rank, share_of_total, and share_label
    locations = []
    for idx, loc in enumerate(raw_locations, start=1):
        count = loc["incident_count"]
        share = round((count / total_filtered_incidents) * 100, 1) if total_filtered_incidents > 0 else 0.0
        loc_entry = dict(loc)
        loc_entry["rank"] = idx
        loc_entry["share_of_total"] = share
        loc_entry["share_label"] = f"{share}% ({count}/{total_filtered_incidents})"
        locations.append(loc_entry)

    # Top Location Callout (Highest Observation Concentration)
    known_locations = [l for l in locations if l["internal_location"] != "UNKNOWN LOCATION"]
    candidate = known_locations[0] if known_locations and known_locations[0]["incident_count"] > 0 else (locations[0] if locations else None)
    if candidate and candidate["incident_count"] > 0:
        top_item = candidate
        top_location = {
            "name": top_item["internal_location"],
            "incident_count": top_item["incident_count"],
            "psif_linked_count": top_item["psif_linked_count"],
            "psif_linkage_rate": top_item["psif_linkage_rate"],
            "share_of_total": top_item["share_of_total"],
            "top_activity": top_item["top_activity"],
            "top_barrier": top_item["top_barrier_linked_signal"],
            "top_iogp_rule": top_item.get("top_iogp_rule", "General Safety Controls"),
            "pattern_chain": top_item["pattern_chain"],
            "total_locations_count": len(locations),
            "has_data": True,
            "callout_caption": "Highest observation concentration in the current Admin Flow dataset.",
        }
    else:
        top_location = {
            "name": "—",
            "incident_count": 0,
            "psif_linked_count": 0,
            "psif_linkage_rate": 0.0,
            "share_of_total": 0.0,
            "top_activity": "—",
            "top_barrier": "—",
            "top_iogp_rule": "—",
            "pattern_chain": None,
            "total_locations_count": 0,
            "has_data": False,
            "callout_caption": "No location patterns available yet.",
        }

    # Build 3x3 Schematic Site Layout
    CANONICAL_GRID_DEFS = [
        {"code": "Z-01", "name": "Workshop", "canonical": "Workshop / Maintenance Bay", "role": "Maintenance Bay", "row": 1, "col": 1},
        {"code": "Z-02", "name": "Process Area", "canonical": "Process Area / Refining Unit", "role": "Refining & Operations", "row": 1, "col": 2},
        {"code": "Z-03", "name": "Tank Farm", "canonical": "Tank Farm", "role": "Bulk Storage", "row": 1, "col": 3},
        {"code": "Z-04", "name": "Warehouse", "canonical": "Warehouse / Storage Yard", "role": "Materials & Storage", "row": 2, "col": 1},
        {"code": "Z-05", "name": "Compressor Area", "canonical": "Compressor Area", "role": "Gas Compression", "row": 2, "col": 2},
        {"code": "Z-06", "name": "Pipe Rack", "canonical": "Pipe Rack / Manifold", "role": "Piping & Manifold", "row": 2, "col": 3},
        {"code": "Z-07", "name": "Main Gate", "canonical": "Main Gate / Access Control", "role": "Security & Entry", "row": 3, "col": 1},
        {"code": "Z-08", "name": "Wellhead", "canonical": "Wellhead Area", "role": "Production Wellhead", "row": 3, "col": 2},
        {"code": "Z-09", "name": "Drilling Area", "canonical": "Drilling Area / Rig Floor", "role": "Rig Floor & Workover", "row": 3, "col": 3},
    ]

    matched_location_names = set()
    schematic_grid = []

    for g_def in CANONICAL_GRID_DEFS:
        matched = None
        for loc in locations:
            l_name = loc["internal_location"]
            if (
                l_name == g_def["canonical"] or
                l_name.lower() == g_def["name"].lower() or
                g_def["name"].lower() in l_name.lower() or
                g_def["canonical"].lower() in l_name.lower()
            ):
                matched = loc
                matched_location_names.add(l_name)
                break

        if matched:
            grid_zone = {
                "code": g_def["code"],
                "name": g_def["name"],
                "role": g_def["role"],
                "row": g_def["row"],
                "col": g_def["col"],
                "canonical_name": matched["internal_location"],
                "incident_count": matched["incident_count"],
                "psif_linked_count": matched["psif_linked_count"],
                "psif_linkage_rate": matched["psif_linkage_rate"],
                "share_of_total": matched["share_of_total"],
                "share_label": matched["share_label"],
                "top_activity": matched["top_activity"],
                "top_barrier": matched["top_barrier_linked_signal"],
                "top_iogp_rule": matched.get("top_iogp_rule", "General Safety Controls"),
                "heatmap_intensity": matched["heatmap_intensity"],
                "heat_level": matched["heat_level"],
                "heat_color": matched["heat_color"],
                "heat_label": matched["heat_label"],
                "pattern_chain": matched["pattern_chain"],
                "recent_observations": matched["recent_observations"],
                "top_activities": matched["top_activities"],
                "top_barriers": matched["top_barriers"],
                "has_observations": matched["incident_count"] > 0,
            }
        else:
            grid_zone = {
                "code": g_def["code"],
                "name": g_def["name"],
                "role": g_def["role"],
                "row": g_def["row"],
                "col": g_def["col"],
                "canonical_name": g_def["canonical"],
                "incident_count": 0,
                "psif_linked_count": 0,
                "psif_linkage_rate": 0.0,
                "share_of_total": 0.0,
                "share_label": "0.0% (0)",
                "top_activity": "—",
                "top_barrier": "—",
                "top_iogp_rule": "—",
                "heatmap_intensity": 0.0,
                "heat_level": "zero",
                "heat_color": "#475569",
                "heat_label": "ZERO",
                "pattern_chain": None,
                "recent_observations": [],
                "top_activities": [],
                "top_barriers": [],
                "has_observations": False,
            }
        schematic_grid.append(grid_zone)

    # Auxiliary zones for any observed locations not mapped in the 9 canonical grid slots
    auxiliary_zones = []
    aux_idx = 1
    for loc in locations:
        if loc["internal_location"] not in matched_location_names and loc["internal_location"] != "UNKNOWN LOCATION":
            aux_entry = dict(loc)
            aux_entry["code"] = f"AUX-0{aux_idx}" if aux_idx < 10 else f"AUX-{aux_idx}"
            aux_entry["name"] = loc["internal_location"]
            aux_entry["canonical_name"] = loc["internal_location"]
            aux_entry["has_observations"] = loc["incident_count"] > 0
            aux_entry["role"] = "Auxiliary Operational Facility"
            auxiliary_zones.append(aux_entry)
            aux_idx += 1

    # Isolated handling for Unknown / Unassigned Location
    unknown_loc_matches = [l for l in locations if l["internal_location"] == "UNKNOWN LOCATION"]
    if unknown_loc_matches:
        unknown_item = unknown_loc_matches[0]
        unknown_location_item = {
            "name": "Unassigned / General Site",
            "internal_location": "UNKNOWN LOCATION",
            "code": "LOC-UNASSIGNED",
            "incident_count": unknown_item["incident_count"],
            "psif_linked_count": unknown_item["psif_linked_count"],
            "psif_linkage_rate": unknown_item["psif_linkage_rate"],
            "share_of_total": unknown_item["share_of_total"],
            "share_label": unknown_item["share_label"],
            "top_activity": unknown_item["top_activity"],
            "top_barrier": unknown_item["top_barrier_linked_signal"],
            "top_iogp_rule": unknown_item.get("top_iogp_rule", "—"),
            "recent_observations": unknown_item["recent_observations"],
            "pattern_chain": unknown_item.get("pattern_chain"),
            "has_observations": unknown_item["incident_count"] > 0,
        }
    else:
        unknown_location_item = None

    known_incidents_count = sum(l["incident_count"] for l in known_locations)
    unknown_incidents_count = total_filtered_incidents - known_incidents_count
    coverage_pct = round((known_incidents_count / total_filtered_incidents) * 100, 1) if total_filtered_incidents > 0 else 0.0

    total_psif_linked = sum(l["psif_linked_count"] for l in locations)
    psif_rate = round((total_psif_linked / total_filtered_incidents) * 100, 1) if total_filtered_incidents > 0 else 0.0
    active_known_zones = [l for l in known_locations if l["incident_count"] > 0]

    summary_cards = {
        "card1": {
            "title": "HIGHEST CONCENTRATION",
            "name": top_location["name"],
            "incident_count": top_location["incident_count"],
            "share_of_total": top_location["share_of_total"],
            "psif_count": top_location["psif_linked_count"],
            "psif_rate": top_location["psif_linkage_rate"],
            "callout": top_location["callout_caption"],
        },
        "card2": {
            "title": "OPERATING ZONES REPRESENTED",
            "count": len(active_known_zones),
            "total_zones": len(schematic_grid) + len(auxiliary_zones),
            "label": f"{len(active_known_zones)} active zones with recorded observations",
            "subtext": "Within Duliajan Operational Complex perimeter",
        },
        "card3": {
            "title": "PSIF-LINKED CONCENTRATION",
            "count": total_psif_linked,
            "rate": psif_rate,
            "label": f"{total_psif_linked} of {total_filtered_incidents} observations",
            "subtext": f"{psif_rate}% overall PSIF precursor rate",
        },
        "card4": {
            "title": "LOCATION ATTRIBUTION RATE",
            "known_count": known_incidents_count,
            "total_count": total_filtered_incidents,
            "rate": coverage_pct,
            "unknown_count": unknown_incidents_count,
            "label": f"{known_incidents_count}/{total_filtered_incidents} mapped to internal site zones",
            "subtext": f"{unknown_incidents_count} records with general / unassigned location",
        },
    }

    # Coverage statistics
    act_obs_known = [
        o for o in observations
        if o.dimension == "activity" and o.normalized_value not in ["General Site Operations", "UNKNOWN ACTIVITY", "UNKNOWN"]
    ]
    act_known_inc_ids = set(o.incident_id for o in act_obs_known)
    act_known_count = len(act_known_inc_ids)

    bar_obs_def = [
        o for o in observations
        if o.dimension == "barrier" and o.control_state in DEFICIENCY_CONTROL_STATES
    ]
    bar_known_inc_ids = set(o.incident_id for o in bar_obs_def)
    bar_known_count = len(bar_known_inc_ids)

    coverage_stats = {
        "total_incidents": total_filtered_incidents,
        "location_identified_count": known_incidents_count,
        "location_identified_pct": coverage_pct,
        "unknown_location_count": unknown_incidents_count,
        "unknown_location_pct": round((unknown_incidents_count / total_filtered_incidents) * 100, 1) if total_filtered_incidents > 0 else 0.0,
        "activity_identified_count": act_known_count,
        "activity_identified_pct": round((act_known_count / total_filtered_incidents) * 100, 1) if total_filtered_incidents > 0 else 0.0,
        "barrier_identified_count": bar_known_count,
        "barrier_identified_pct": round((bar_known_count / total_filtered_incidents) * 100, 1) if total_filtered_incidents > 0 else 0.0,
    }

    # Cross-Dimensional Matrices
    loc_rule_counts = defaultdict(lambda: {"inc_ids": set(), "psif_ids": set()})
    for o in observations:
        if o.dimension == "barrier":
            rule = o.iogp_rule or o.normalized_value
            if not rule or rule.lower() in ["none", "unknown", "n/a", ""]:
                continue
            matched_rule = None
            for cr in CANONICAL_IOGP_RULES:
                if cr.lower() == rule.lower() or cr.lower() in rule.lower() or rule.lower() in cr.lower():
                    matched_rule = cr
                    break
            if matched_rule:
                loc = o.location or "UNKNOWN LOCATION"
                key = (loc, matched_rule)
                loc_rule_counts[key]["inc_ids"].add(o.incident_id)
                if o.psif_state == "PSIF":
                    loc_rule_counts[key]["psif_ids"].add(o.incident_id)

    matrix_locs = [l for l in locations if l["internal_location"] != "UNKNOWN LOCATION" and l["incident_count"] > 0]
    if not matrix_locs and locations:
        matrix_locs = [l for l in locations if l["incident_count"] > 0]

    iogp_matrix_rows = []
    for loc in matrix_locs:
        loc_name = loc["internal_location"]
        row_cells = []
        row_total = 0
        row_psif = 0
        for rule in CANONICAL_IOGP_RULES:
            item = loc_rule_counts.get((loc_name, rule))
            count = len(item["inc_ids"]) if item else 0
            p_count = len(item["psif_ids"]) if item else 0
            row_total += count
            row_psif += p_count

            if count == 0:
                lvl = 0
                cls_name = "cell-zero"
            elif count == 1:
                lvl = 1
                cls_name = "cell-low"
            elif count <= 3:
                lvl = 2
                cls_name = "cell-mid"
            else:
                lvl = 3
                cls_name = "cell-high"

            row_cells.append({
                "rule": rule,
                "count": count,
                "psif_count": p_count,
                "level": lvl,
                "css_class": cls_name,
                "tooltip": f"{loc_name} • {rule}: {count} observation{'s' if count != 1 else ''} ({p_count} PSIF-linked)",
            })

        iogp_matrix_rows.append({
            "location": loc_name,
            "total_incidents": loc["incident_count"],
            "psif_count": loc["psif_linked_count"],
            "row_rule_total": row_total,
            "row_rule_psif": row_psif,
            "cells": row_cells,
        })

    iogp_col_totals = []
    for idx, rule in enumerate(CANONICAL_IOGP_RULES):
        c_count = sum(r["cells"][idx]["count"] for r in iogp_matrix_rows)
        c_psif = sum(r["cells"][idx]["psif_count"] for r in iogp_matrix_rows)
        iogp_col_totals.append({
            "rule": rule,
            "count": c_count,
            "psif_count": c_psif,
        })

    iogp_matrix = {
        "columns": CANONICAL_IOGP_RULES,
        "rows": iogp_matrix_rows,
        "column_totals": iogp_col_totals,
        "total_associated": sum(c["count"] for c in iogp_col_totals),
    }

    # Top Activities matrix
    top_act_counts = Counter()
    for o in observations:
        if o.dimension == "activity" and o.normalized_value:
            top_act_counts[o.normalized_value] += 1

    top_activity_names = [k for k, v in top_act_counts.most_common(6)]
    if not top_activity_names:
        top_activity_names = ["General Site Operations"]

    loc_act_counts = defaultdict(lambda: {"inc_ids": set(), "psif_ids": set()})
    for o in observations:
        if o.dimension == "activity" and o.normalized_value in top_activity_names:
            loc = o.location or "UNKNOWN LOCATION"
            key = (loc, o.normalized_value)
            loc_act_counts[key]["inc_ids"].add(o.incident_id)
            if o.psif_state == "PSIF":
                loc_act_counts[key]["psif_ids"].add(o.incident_id)

    activity_matrix_rows = []
    for loc in matrix_locs:
        loc_name = loc["internal_location"]
        row_cells = []
        row_total = 0
        for act in top_activity_names:
            item = loc_act_counts.get((loc_name, act))
            count = len(item["inc_ids"]) if item else 0
            p_count = len(item["psif_ids"]) if item else 0
            row_total += count

            if count == 0:
                lvl = 0
                cls_name = "cell-zero"
            elif count == 1:
                lvl = 1
                cls_name = "cell-low"
            elif count <= 3:
                lvl = 2
                cls_name = "cell-mid"
            else:
                lvl = 3
                cls_name = "cell-high"

            row_cells.append({
                "activity": act,
                "count": count,
                "psif_count": p_count,
                "level": lvl,
                "css_class": cls_name,
                "tooltip": f"{loc_name} • {act}: {count} observation{'s' if count != 1 else ''} ({p_count} PSIF-linked)",
            })

        activity_matrix_rows.append({
            "location": loc_name,
            "total_incidents": loc["incident_count"],
            "row_act_total": row_total,
            "cells": row_cells,
        })

    activity_col_totals = []
    for idx, act in enumerate(top_activity_names):
        c_count = sum(r["cells"][idx]["count"] for r in activity_matrix_rows)
        activity_col_totals.append({
            "activity": act,
            "count": c_count,
        })

    activity_matrix = {
        "columns": top_activity_names,
        "rows": activity_matrix_rows,
        "column_totals": activity_col_totals,
    }

    # Horizontal Ranking Bar Data
    max_loc_count = max([l["incident_count"] for l in locations], default=1) or 1
    ranking_bars = []
    for loc in locations:
        ranking_bars.append({
            "name": loc["internal_location"],
            "rank": loc["rank"],
            "incident_count": loc["incident_count"],
            "psif_linked_count": loc["psif_linked_count"],
            "share_of_total": loc["share_of_total"],
            "share_label": loc["share_label"],
            "heat_color": loc["heat_color"],
            "heat_level": loc["heat_level"],
            "bar_width_pct": round((loc["incident_count"] / max_loc_count) * 100, 1) if max_loc_count > 0 else 0,
            "top_activity": loc["top_activity"],
            "top_barrier": loc["top_barrier_linked_signal"],
            "top_iogp_rule": loc.get("top_iogp_rule", "—"),
        })

    has_active_filters = bool(
        (psif_filter and psif_filter != "all") or
        (activity_filter and activity_filter != "all") or
        (barrier_filter and barrier_filter != "all") or
        (query and query.strip())
    )

    distinct_locations = len(locations)
    recurring_locations = len([l for l in locations if l["is_recurring"]])
    total_location_observations = sum(l["incident_count"] for l in locations)

    return {
        "workspace_id": ADMIN_FLOW_WORKSPACE,
        "site_context": ADMIN_FLOW_SITE_NAME,
        "total_workspace_incidents": total_workspace_incidents,
        "total_filtered_incidents": total_filtered_incidents,
        "total_patterns": distinct_locations,
        "recurring_count": recurring_locations,
        "distinct_locations_count": distinct_locations,
        "recurring_locations_count": recurring_locations,
        "total_location_observations": total_location_observations,
        "total_psif_linked": total_psif_linked,
        "locations": locations,
        "known_locations": known_locations,
        "top_location": top_location,
        "schematic_grid": schematic_grid,
        "auxiliary_zones": auxiliary_zones,
        "unknown_location_item": unknown_location_item,
        "summary": summary_cards,
        "coverage_stats": coverage_stats,
        "iogp_matrix": iogp_matrix,
        "activity_matrix": activity_matrix,
        "ranking_bars": ranking_bars,
        "canonical_iogp_rules": CANONICAL_IOGP_RULES,
        "has_data": len(locations) > 0,
        "has_active_filters": has_active_filters,
        "canonical_locations": CANONICAL_INTERNAL_LOCATIONS,
        "filters": {
            "psif_filter": psif_filter or "all",
            "activity_filter": activity_filter or "all",
            "barrier_filter": barrier_filter or "all",
            "query": query or "",
        },
        "legend_title": "INCIDENT OBSERVATION DENSITY",
        "methodology_note": "Intensity represents incident observation density within the single-site operational perimeter. Does not establish intrinsic operational risk or future incident likelihood.",
    }


def get_admin_flow_pattern_hub_view_data() -> Dict[str, Any]:
    """
    Authoritative view data for the Admin Flow Pattern Analysis Landing Page (Hub).
    Supplies:
    1. Top-Level Pattern Summary (Total incidents, Most frequent activity,
       Most frequent barrier signal, Highest observation concentration).
    2. Visual preview cards data for Activity, Barrier, and Location.
    3. Multi-Dimensional Relationship Flow:
       Activity -> Location -> Barrier / Control Signal -> PSIF-linked observations.
    4. Compliant, subtle methodology disclaimers.
    """
    summary = get_admin_flow_pattern_summary(use_cache=True)
    total_incidents = summary["total_incidents"]
    activity_patterns = summary["activity_patterns"]
    barrier_patterns = summary["barrier_patterns"]
    location_patterns = summary["location_patterns"]

    has_data = total_incidents > 0 and (
        len(activity_patterns) > 0 or len(barrier_patterns) > 0 or len(location_patterns) > 0
    )

    # 1. Top Activity
    if activity_patterns:
        top_act = activity_patterns[0]
        act_name = top_act.get("category") or top_act.get("activity_category") or "General Operations"
        top_activity = {
            "name": act_name,
            "count": top_act["incident_count"],
            "psif_count": top_act["psif_linked_count"],
            "share_pct": round((top_act["incident_count"] / total_incidents * 100), 1) if total_incidents > 0 else 0.0,
            "has_data": True,
        }
    else:
        top_activity = {
            "name": "None yet",
            "count": 0,
            "psif_count": 0,
            "share_pct": 0.0,
            "has_data": False,
        }

    # 2. Top Barrier Signal (Using Canonical Barrier Intelligence Engine)
    from apps.admin_flow.barrier_service import BarrierPatternService
    barrier_view_data = BarrierPatternService.get_barrier_pattern_view_data()
    top_bar = barrier_view_data.get("top_barrier_overall")
    if top_bar:
        top_barrier = {
            "name": top_bar.get("barrier_name") or "General Protective Barrier",
            "count": top_bar.get("associated_incidents_count", 0),
            "effective_count": top_bar.get("effective_count", 0),
            "deficient_count": top_bar.get("deficient_count", 0),
            "psif_count": top_bar.get("psif_linked_count", 0),
            "dominant_state": top_bar.get("dominant_state") or "EFFECTIVE",
            "share_pct": top_bar.get("share_of_dataset", 0.0),
            "has_data": True,
        }
    else:
        top_barrier = {
            "name": "None yet",
            "count": 0,
            "effective_count": 0,
            "deficient_count": 0,
            "psif_count": 0,
            "dominant_state": None,
            "share_pct": 0.0,
            "has_data": False,
        }

    # 3. Top Location
    known_locs = [l for l in location_patterns if l.get("internal_location") != "UNKNOWN LOCATION"]
    top_loc = known_locs[0] if known_locs else (location_patterns[0] if location_patterns else None)
    if top_loc:
        top_location = {
            "name": top_loc.get("internal_location") or "General Facility",
            "count": top_loc["incident_count"],
            "psif_count": top_loc["psif_linked_count"],
            "share_pct": round((top_loc["incident_count"] / total_incidents * 100), 1) if total_incidents > 0 else 0.0,
            "has_data": True,
        }
    else:
        top_location = {
            "name": "None yet",
            "count": 0,
            "psif_count": 0,
            "share_pct": 0.0,
            "has_data": False,
        }

    # 4. Dimension Previews
    # Activity Preview: top 3 with relative bar width
    max_act_count = activity_patterns[0]["incident_count"] if activity_patterns else 1
    activity_previews = [
        {
            "name": a.get("category") or a.get("activity_category") or "General Operations",
            "count": a["incident_count"],
            "psif_count": a["psif_linked_count"],
            "pct": round((a["incident_count"] / max(1, total_incidents)) * 100, 1),
            "bar_width": max(15, round((a["incident_count"] / max(1, max_act_count)) * 100)),
        }
        for a in activity_patterns[:3]
    ]

    # Barrier Preview: top 3 actual barriers with total, effective, and deficient counts
    hub_barrier_cards = barrier_view_data.get("portfolio_cards", [])
    barrier_previews = [
        {
            "name": b["barrier_name"],
            "count": b["associated_incidents_count"],
            "effective_count": b["effective_count"],
            "deficient_count": b["deficient_count"],
            "psif_count": b["psif_linked_count"],
            "dominant_state": b.get("dominant_state") or "EFFECTIVE",
            "pct": b.get("share_of_dataset", 0.0),
        }
        for b in hub_barrier_cards[:3]
    ]

    # Location Preview: top 3 zones with density and color
    location_previews = [
        {
            "name": l["internal_location"],
            "count": l["incident_count"],
            "psif_count": l["psif_linked_count"],
            "heat_level": l.get("heat_level", "low"),
            "heat_color": l.get("heat_color", "#27AE60"),
            "heat_label": l.get("heat_label", "Low Density"),
            "pct": round((l["incident_count"] / max(1, total_incidents)) * 100, 1),
        }
        for l in location_patterns[:3]
    ]

    # 5. Multi-Dimensional Relationship Flow (Activity -> Location -> Barrier -> PSIF)
    # Extract co-occurrences by incident
    relationship_pathways = []
    if has_data:
        observations = extract_all_admin_flow_pattern_observations()
        by_incident: Dict[str, Dict[str, Any]] = {}
        for o in observations:
            inc_id = o.incident_id
            if inc_id not in by_incident:
                by_incident[inc_id] = {
                    "activities": set(),
                    "locations": set(),
                    "barriers": set(),
                    "psif": (o.psif_state == "PSIF"),
                }
            if o.dimension == "activity":
                by_incident[inc_id]["activities"].add(o.normalized_value)
            elif o.dimension == "location":
                by_incident[inc_id]["locations"].add(o.normalized_value)
            elif o.dimension == "barrier" and o.control_state in DEFICIENCY_CONTROL_STATES:
                by_incident[inc_id]["barriers"].add(o.normalized_value)

        # Count 4-tuple combinations
        # RULE: Only emit a pathway when BOTH activity and location are known/valid.
        # Incidents with no evidence-backed barrier deficiency are still counted
        # under their activity+location pair, but without a fabricated barrier label.
        tuple_counts: Counter = Counter()
        UNKNOWN_SENTINELS = {"UNKNOWN ACTIVITY", "UNKNOWN LOCATION"}
        for inc_id, d in by_incident.items():
            acts = d["activities"] - UNKNOWN_SENTINELS
            locs = d["locations"] - UNKNOWN_SENTINELS
            bars = d["barriers"]  # already filtered to DEFICIENCY_CONTROL_STATES above
            psif_val = "PSIF Candidate" if d["psif"] else "Non-PSIF"

            # Skip if no known activity or no known location
            if not acts or not locs:
                continue

            if bars:
                for a in acts:
                    for l in locs:
                        for b in bars:
                            tuple_counts[(a, l, b, psif_val)] += 1
            else:
                # Known activity + known location, no barrier deficiency signal
                for a in acts:
                    for l in locs:
                        tuple_counts[(a, l, "—", psif_val)] += 1

        if tuple_counts:
            # Top 3 pathways — only show barrier column when it is a real control signal
            for (act, loc, bar, psif_str), count in tuple_counts.most_common(3):
                relationship_pathways.append({
                    "activity": act,
                    "location": loc,
                    "barrier": bar,
                    "psif_outcome": psif_str,
                    "incident_count": count,
                    "share_pct": round((count / max(1, total_incidents)) * 100, 1),
                    "is_primary": len(relationship_pathways) == 0,
                })

    # If no qualifying pathways found (all records had unknown activity/location),
    # signal the UI to show "No recurring multi-dimensional pattern established."
    has_relationships_data = len(relationship_pathways) > 0
    primary_pathway = relationship_pathways[0] if relationship_pathways else None

    return {
        "workspace_id": ADMIN_FLOW_WORKSPACE,
        "site_context": ADMIN_FLOW_SITE_NAME,
        "total_incidents": total_incidents,
        "has_data": has_data,
        "has_relationships_data": has_relationships_data,
        "top_activity": top_activity,
        "top_barrier": top_barrier,
        "top_location": top_location,
        "activity_previews": activity_previews,
        "barrier_previews": barrier_previews,
        "location_previews": location_previews,
        "relationship_pathways": relationship_pathways,
        "primary_pathway": primary_pathway,
        "recurring_counts": summary.get("recurring_counts", {}),
        "methodology_disclaimers": [
            "Pattern analysis is based on the current Admin Flow demonstration dataset.",
            "Patterns represent historical observation frequency and association.",
            "Barrier-linked observations are based on evidence-supported control states.",
            "Pattern analysis does not establish causation or predict future incidents.",
        ],
    }

