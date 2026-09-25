"""
PSIF Platform — Admin Flow Activity Intelligence Engine.
apps/admin_flow/activity_engine.py

Architectural Principle:
ACTIVITY answers: "What work was being performed or operational task taking place?"
IOGP answers:     "Which Life-Saving Rule domain was associated?"
BARRIER answers:  "What protective measure stood between the hazard and consequence?"
LOCATION answers: "Where did it happen?"
PSIF answers:     "Does the evidence support a potential serious-injury/fatality pathway?"

NEVER collapse these dimensions into one another.
- An IOGP rule (e.g. Hot Work, Energy Isolation) is NOT an activity.
- A barrier (e.g. Safety Harness, Gas Detector) is NOT an activity.
- A hazard (e.g. Stored Pressure, Gravity) is NOT an activity.
- Equipment (e.g. Pump, Compressor) is NOT an activity.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Canonical Activity Taxonomy (20 Operational Categories) ───────────────────

class ActivityCategory:
    PAINTING = "PAINTING"
    CLEANING = "CLEANING"
    DIGGING_EXCAVATION = "DIGGING_EXCAVATION"
    LABORATORY_RESEARCH = "LABORATORY_RESEARCH"
    VEHICLE_PARKING_OPERATIONS = "VEHICLE_PARKING_OPERATIONS"
    EQUIPMENT_MAINTENANCE = "EQUIPMENT_MAINTENANCE"
    LIFTING_OPERATION = "LIFTING_OPERATION"
    WELDING_HOT_WORK = "WELDING_HOT_WORK"
    ELEVATED_WORK_SCAFFOLDING = "ELEVATED_WORK_SCAFFOLDING"
    INTERNAL_VESSEL_WORK = "INTERNAL_VESSEL_WORK"
    PIPELINE_MAINTENANCE = "PIPELINE_MAINTENANCE"
    ELECTRICAL_MAINTENANCE = "ELECTRICAL_MAINTENANCE"
    MATERIAL_HANDLING = "MATERIAL_HANDLING"
    INSPECTION_AUDITING = "INSPECTION_AUDITING"
    DRILLING_OPERATIONS = "DRILLING_OPERATIONS"
    SAMPLING_TESTING = "SAMPLING_TESTING"
    CHEMICAL_HANDLING = "CHEMICAL_HANDLING"
    CONSTRUCTION_FABRICATION = "CONSTRUCTION_FABRICATION"
    OTHER_KNOWN_ACTIVITY = "OTHER_KNOWN_ACTIVITY"
    UNKNOWN_ACTIVITY = "UNKNOWN_ACTIVITY"


ACTIVITY_DISPLAY_NAMES: Dict[str, str] = {
    ActivityCategory.PAINTING: "Painting & Surface Coating",
    ActivityCategory.CLEANING: "Cleaning & Housekeeping",
    ActivityCategory.DIGGING_EXCAVATION: "Digging / Excavation",
    ActivityCategory.LABORATORY_RESEARCH: "Laboratory / Research",
    ActivityCategory.VEHICLE_PARKING_OPERATIONS: "Vehicle / Parking Operations",
    ActivityCategory.EQUIPMENT_MAINTENANCE: "Equipment Maintenance & Servicing",
    ActivityCategory.LIFTING_OPERATION: "Lifting Operation / Crane Work",
    ActivityCategory.WELDING_HOT_WORK: "Welding, Cutting & Hot Work",
    ActivityCategory.ELEVATED_WORK_SCAFFOLDING: "Work at Height / Scaffolding",
    ActivityCategory.INTERNAL_VESSEL_WORK: "Internal Vessel Cleaning & Inspection",
    ActivityCategory.PIPELINE_MAINTENANCE: "Pipeline Maintenance & Valve Work",
    ActivityCategory.ELECTRICAL_MAINTENANCE: "Electrical Maintenance & Troubleshooting",
    ActivityCategory.MATERIAL_HANDLING: "Material Handling & Staging",
    ActivityCategory.INSPECTION_AUDITING: "Inspection & Quality Auditing",
    ActivityCategory.DRILLING_OPERATIONS: "Drilling & Well Operations",
    ActivityCategory.SAMPLING_TESTING: "Sampling & Hydrotesting",
    ActivityCategory.CHEMICAL_HANDLING: "Chemical Handling & Transfer",
    ActivityCategory.CONSTRUCTION_FABRICATION: "Structural Construction & Fabrication",
    ActivityCategory.OTHER_KNOWN_ACTIVITY: "Other Operational Task",
    ActivityCategory.UNKNOWN_ACTIVITY: "UNKNOWN ACTIVITY",
}


# ── Anti-Contamination Lists ──────────────────────────────────────────────────
# Items in these sets must NEVER be treated as activity names.

FORBIDDEN_IOGP_RULE_NAMES: Set[str] = {
    "hot work",
    "energy isolation",
    "safe mechanical lifting",
    "working at height",
    "driving",
    "confined space",
    "confined space entry",
    "line of fire",
    "line of fire work",
    "work authorization",
    "bypassing safety controls",
    "bypass / override work",
    "bypass override work",
    "overriding safety controls",
}

FORBIDDEN_BARRIER_NAMES: Set[str] = {
    "safety harness",
    "fall arrest",
    "fall-arrest system",
    "guardrail",
    "safety net",
    "gas detector",
    "gas detection",
    "fire watch",
    "fire suppression",
    "emergency shutdown",
    "esd",
    "lockout tagout",
    "loto",
    "isolation valve",
    "pressure relief valve",
    "prv",
    "interlock",
    "seat belt",
    "wheel chock",
    "trench shoring",
    "shored trench box",
    "exclusion barricade",
    "machine guard",
    "spill containment",
}

FORBIDDEN_HAZARD_NAMES: Set[str] = {
    "gravity",
    "stored pressure",
    "pressure",
    "toxic gas",
    "h2s",
    "hydrocarbon",
    "electricity",
    "high voltage",
    "flammable vapor",
    "moving vehicle",
    "suspended load",
    "rotating equipment",
    "extreme temperature",
}

FORBIDDEN_EQUIPMENT_ONLY: Set[str] = {
    "pump",
    "centrifugal pump",
    "compressor",
    "gas compressor",
    "separator",
    "storage tank",
    "tank",
    "crane",
    "excavator",
    "forklift",
    "truck",
    "boiler",
    "heat exchanger",
    "pipeline",
    "valve",
    "generator",
}


# ── Canonical Activity Aliases ─────────────────────────────────────────────────

ACTIVITY_ALIASES: Dict[str, str] = {
    # Painting
    "painting": ActivityCategory.PAINTING,
    "paint application": ActivityCategory.PAINTING,
    "painting work": ActivityCategory.PAINTING,
    "spray painting": ActivityCategory.PAINTING,
    "surface coating": ActivityCategory.PAINTING,
    "coating application": ActivityCategory.PAINTING,
    "grit blasting and painting": ActivityCategory.PAINTING,
    "sandblasting": ActivityCategory.PAINTING,
    "touch up painting": ActivityCategory.PAINTING,
    "primer application": ActivityCategory.PAINTING,
    "pipe painting": ActivityCategory.PAINTING,
    "tank painting": ActivityCategory.PAINTING,

    # Cleaning / Housekeeping
    "cleaning": ActivityCategory.CLEANING,
    "cleaning activity": ActivityCategory.CLEANING,
    "housekeeping": ActivityCategory.CLEANING,
    "workshop cleaning": ActivityCategory.CLEANING,
    "floor cleaning": ActivityCategory.CLEANING,
    "washing": ActivityCategory.CLEANING,
    "washing equipment": ActivityCategory.CLEANING,
    "pressure washing": ActivityCategory.CLEANING,
    "degreasing": ActivityCategory.CLEANING,
    "spill cleanup": ActivityCategory.CLEANING,
    "sweeping": ActivityCategory.CLEANING,
    "waste disposal": ActivityCategory.CLEANING,
    "scrubbing": ActivityCategory.CLEANING,
    "decontamination": ActivityCategory.CLEANING,

    # Digging / Excavation
    "digging": ActivityCategory.DIGGING_EXCAVATION,
    "excavation": ActivityCategory.DIGGING_EXCAVATION,
    "digging / excavation": ActivityCategory.DIGGING_EXCAVATION,
    "trench digging": ActivityCategory.DIGGING_EXCAVATION,
    "trench excavation": ActivityCategory.DIGGING_EXCAVATION,
    "earthwork": ActivityCategory.DIGGING_EXCAVATION,
    "trenching": ActivityCategory.DIGGING_EXCAVATION,
    "cable trenching": ActivityCategory.DIGGING_EXCAVATION,
    "pipeline excavation": ActivityCategory.DIGGING_EXCAVATION,
    "backhoe excavation": ActivityCategory.DIGGING_EXCAVATION,
    "potholing": ActivityCategory.DIGGING_EXCAVATION,
    "grading": ActivityCategory.DIGGING_EXCAVATION,

    # Laboratory / Research
    "laboratory": ActivityCategory.LABORATORY_RESEARCH,
    "laboratory / research": ActivityCategory.LABORATORY_RESEARCH,
    "lab work": ActivityCategory.LABORATORY_RESEARCH,
    "laboratory testing": ActivityCategory.LABORATORY_RESEARCH,
    "sample analysis": ActivityCategory.LABORATORY_RESEARCH,
    "glassware cleaning": ActivityCategory.LABORATORY_RESEARCH,
    "chemical analysis": ActivityCategory.LABORATORY_RESEARCH,
    "quality control testing": ActivityCategory.LABORATORY_RESEARCH,
    "spectrometry": ActivityCategory.LABORATORY_RESEARCH,
    "titration": ActivityCategory.LABORATORY_RESEARCH,
    "research testing": ActivityCategory.LABORATORY_RESEARCH,

    # Vehicle / Parking Operations
    "vehicle / parking operations": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "parking vehicle": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "vehicle movement": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "vehicle operation": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "vehicle operation / road transport": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "parking": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "vehicle parking": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "truck driving": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "forklift driving": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "forklift operation": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "reversing vehicle": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "bus transit": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "crew transport": ActivityCategory.VEHICLE_PARKING_OPERATIONS,
    "light vehicle transit": ActivityCategory.VEHICLE_PARKING_OPERATIONS,

    # Equipment Maintenance
    "equipment maintenance": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "equipment maintenance & servicing": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "equipment repair": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "maintenance": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "mechanical maintenance": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "routine maintenance": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "preventive maintenance": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "filter replacement": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "pump overhaul": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "compressor overhaul": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "valve replacement": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "bearing replacement": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "lubrication": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "greasing": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "seal replacement": ActivityCategory.EQUIPMENT_MAINTENANCE,
    "machining": ActivityCategory.EQUIPMENT_MAINTENANCE,

    # Lifting Operation / Crane Work
    "lifting operation": ActivityCategory.LIFTING_OPERATION,
    "lifting operations": ActivityCategory.LIFTING_OPERATION,
    "lifting operation / crane work": ActivityCategory.LIFTING_OPERATION,
    "crane lifting": ActivityCategory.LIFTING_OPERATION,
    "crane operation": ActivityCategory.LIFTING_OPERATION,
    "rigging": ActivityCategory.LIFTING_OPERATION,
    "rigging operation": ActivityCategory.LIFTING_OPERATION,
    "tandem lift": ActivityCategory.LIFTING_OPERATION,
    "material lifting": ActivityCategory.LIFTING_OPERATION,
    "hoisting": ActivityCategory.LIFTING_OPERATION,
    "pipe bundle lift": ActivityCategory.LIFTING_OPERATION,

    # Welding, Cutting & Hot Work
    "welding": ActivityCategory.WELDING_HOT_WORK,
    "welding, cutting & hot work": ActivityCategory.WELDING_HOT_WORK,
    "welding and cutting": ActivityCategory.WELDING_HOT_WORK,
    "torch cutting": ActivityCategory.WELDING_HOT_WORK,
    "grinding": ActivityCategory.WELDING_HOT_WORK,
    "brazing": ActivityCategory.WELDING_HOT_WORK,
    "gouging": ActivityCategory.WELDING_HOT_WORK,
    "hot work in classified area": ActivityCategory.WELDING_HOT_WORK,
    "pipe welding": ActivityCategory.WELDING_HOT_WORK,
    "structural welding": ActivityCategory.WELDING_HOT_WORK,

    # Work at Height / Scaffolding
    "work at height": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "work at height / scaffolding": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "scaffolding": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "scaffolding erection": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "scaffold dismantling": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "elevated maintenance": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "ladder work": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "roof maintenance": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "window cleaning": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "window cleaning at height": ActivityCategory.ELEVATED_WORK_SCAFFOLDING,
    "painting at height": ActivityCategory.PAINTING,  # Primary work task is Painting

    # Internal Vessel Work
    "internal vessel work": ActivityCategory.INTERNAL_VESSEL_WORK,
    "internal vessel cleaning & inspection": ActivityCategory.INTERNAL_VESSEL_WORK,
    "confined space vessel entry": ActivityCategory.INTERNAL_VESSEL_WORK,
    "vessel descaling": ActivityCategory.INTERNAL_VESSEL_WORK,
    "tank entry work": ActivityCategory.INTERNAL_VESSEL_WORK,
    "tank internal cleaning": ActivityCategory.INTERNAL_VESSEL_WORK,
    "column tray inspection": ActivityCategory.INTERNAL_VESSEL_WORK,
    "boiler internal inspection": ActivityCategory.INTERNAL_VESSEL_WORK,

    # Pipeline Maintenance
    "pipeline maintenance": ActivityCategory.PIPELINE_MAINTENANCE,
    "pipeline maintenance & valve work": ActivityCategory.PIPELINE_MAINTENANCE,
    "flange breaking": ActivityCategory.PIPELINE_MAINTENANCE,
    "pressure-line maintenance": ActivityCategory.PIPELINE_MAINTENANCE,
    "pressure-line maintenance / flange breaking": ActivityCategory.PIPELINE_MAINTENANCE,
    "pipeline pigging": ActivityCategory.PIPELINE_MAINTENANCE,
    "line clearing": ActivityCategory.PIPELINE_MAINTENANCE,
    "spool replacement": ActivityCategory.PIPELINE_MAINTENANCE,
    "valve packing replacement": ActivityCategory.PIPELINE_MAINTENANCE,

    # Electrical Maintenance
    "electrical maintenance": ActivityCategory.ELECTRICAL_MAINTENANCE,
    "electrical maintenance & troubleshooting": ActivityCategory.ELECTRICAL_MAINTENANCE,
    "electrical troubleshooting": ActivityCategory.ELECTRICAL_MAINTENANCE,
    "breaker servicing": ActivityCategory.ELECTRICAL_MAINTENANCE,
    "cable pulling": ActivityCategory.ELECTRICAL_MAINTENANCE,
    "motor rewinding": ActivityCategory.ELECTRICAL_MAINTENANCE,
    "switchgear maintenance": ActivityCategory.ELECTRICAL_MAINTENANCE,
    "transformer servicing": ActivityCategory.ELECTRICAL_MAINTENANCE,

    # Material Handling
    "material handling": ActivityCategory.MATERIAL_HANDLING,
    "material handling & staging": ActivityCategory.MATERIAL_HANDLING,
    "loading": ActivityCategory.MATERIAL_HANDLING,
    "unloading": ActivityCategory.MATERIAL_HANDLING,
    "loading / unloading": ActivityCategory.MATERIAL_HANDLING,
    "pipe offloading": ActivityCategory.MATERIAL_HANDLING,
    "cargo staging": ActivityCategory.MATERIAL_HANDLING,
    "pallet staging": ActivityCategory.MATERIAL_HANDLING,
    "warehouse stocking": ActivityCategory.MATERIAL_HANDLING,

    # Inspection / Auditing
    "inspection": ActivityCategory.INSPECTION_AUDITING,
    "inspection & quality auditing": ActivityCategory.INSPECTION_AUDITING,
    "visual inspection": ActivityCategory.INSPECTION_AUDITING,
    "ndt inspection": ActivityCategory.INSPECTION_AUDITING,
    "ultrasonic thickness testing": ActivityCategory.INSPECTION_AUDITING,
    "weld inspection": ActivityCategory.INSPECTION_AUDITING,
    "safety audit": ActivityCategory.INSPECTION_AUDITING,
    "walkthrough audit": ActivityCategory.INSPECTION_AUDITING,

    # Drilling Operations
    "drilling": ActivityCategory.DRILLING_OPERATIONS,
    "drilling & well operations": ActivityCategory.DRILLING_OPERATIONS,
    "tripping pipe": ActivityCategory.DRILLING_OPERATIONS,
    "casing running": ActivityCategory.DRILLING_OPERATIONS,
    "mud mixing": ActivityCategory.DRILLING_OPERATIONS,
    "well logging": ActivityCategory.DRILLING_OPERATIONS,
    "blowout preventer testing": ActivityCategory.DRILLING_OPERATIONS,

    # Sampling / Testing
    "sampling": ActivityCategory.SAMPLING_TESTING,
    "sampling & hydrotesting": ActivityCategory.SAMPLING_TESTING,
    "pressure testing": ActivityCategory.SAMPLING_TESTING,
    "hydrostatic testing": ActivityCategory.SAMPLING_TESTING,
    "hydrotesting": ActivityCategory.SAMPLING_TESTING,
    "fluid sampling": ActivityCategory.SAMPLING_TESTING,
    "oil sampling": ActivityCategory.SAMPLING_TESTING,
    "leak testing": ActivityCategory.SAMPLING_TESTING,
    "calibration": ActivityCategory.SAMPLING_TESTING,

    # Chemical Handling
    "chemical handling": ActivityCategory.CHEMICAL_HANDLING,
    "chemical handling & transfer": ActivityCategory.CHEMICAL_HANDLING,
    "chemical dosing": ActivityCategory.CHEMICAL_HANDLING,
    "acid transfer": ActivityCategory.CHEMICAL_HANDLING,
    "inhibitor replenishment": ActivityCategory.CHEMICAL_HANDLING,
    "biocide injection": ActivityCategory.CHEMICAL_HANDLING,

    # Construction
    "construction": ActivityCategory.CONSTRUCTION_FABRICATION,
    "structural construction & fabrication": ActivityCategory.CONSTRUCTION_FABRICATION,
    "civil construction": ActivityCategory.CONSTRUCTION_FABRICATION,
    "concreting": ActivityCategory.CONSTRUCTION_FABRICATION,
    "formwork installation": ActivityCategory.CONSTRUCTION_FABRICATION,
    "pipe fabrication": ActivityCategory.CONSTRUCTION_FABRICATION,
    "structural erection": ActivityCategory.CONSTRUCTION_FABRICATION,
}


# ── Narrative Grammar Patterns for Temporal Activity Extraction ───────────────

TEMPORAL_SEQUENCE_PATTERNS = [
    # "After completing welding, workers began cleaning." -> cleaning is the activity at event time
    r"(?:after|following|upon)\s+(?:completing|finishing|conclusion of)\s+[^,.;]+?,\s*(?:workers|personnel|the crew|technicians|operators)?\s*(?:began|started|were|proceeded to)\s+([^,.;]+?)(?:\s+(?:in|at|near|on|inside)\b|,|\.|$)",
    # "Before starting maintenance, workers were cleaning..."
    r"(?:before|prior to)\s+(?:starting|commencing|beginning)\s+[^,.;]+?,\s*(?:workers|personnel|operators)?\s*(?:were|began)\s+([^,.;]+?)(?:\s+(?:in|at|near|on|inside)\b|,|\.|$)",
]

ACTIVE_NARRATIVE_ACTIVITY_PATTERNS = [
    r"\bwhile\s+(?:performing|conducting|carrying out|undertaking|doing)\s+([^,.;]+?)(?:\s+(?:in|at|on|near|with|during|inside)\b|,|\.|$)",
    r"\bwhile\s+([a-z]+ing(?:\s+[a-z]+)?)\b(?:\s+(?:equipment|line|tank|floor|pipe|vessel|spool|bay|area)\b)?",
    r"\bduring\s+([a-z\s/]+?(?:maintenance|repair|servicing|cleaning|inspection|overhaul|painting|excavation|digging|testing|sampling|lifting|welding|movement|transit|drilling|operation|handling|transfer|alignment|loading|unloading|delivery|survey|installation|commissioning))\b",
    r"\bengaged in\s+([^,.;]+?)(?:\s+(?:in|at|on|near|with|during|inside)\b|,|\.|$)",
    r"\bworking on\s+([^,.;]+?)(?:\s+(?:in|at|near|with|during|inside|reported|experienced|resulted|sustained|suffered|when)\b|,|\.|$)",
    r"\bworkers?\s+(?:were|was)\s+([a-z]+ing(?:\s+[a-z]+)?)\b",
    r"\btechnicians?\s+(?:were|was)\s+([a-z]+ing(?:\s+[a-z]+)?)\b",
]

STOP_WORDS = {
    "reported", "resulted", "sustained", "suffered", "experienced", "noticed",
    "observed", "felt", "injured", "slipped", "tripped", "dropped", "fell",
    "lost", "struck", "contacted", "was", "were", "occurred", "happened",
    "incident", "accident", "near", "miss", "potential", "sif",
}


def sanitize_input(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def extract_activity_from_narrative(narrative: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extracts the operational activity being performed at the time of the incident from narrative text.
    Returns: (matched_category_or_phrase, extraction_method)
    """
    if not narrative or not str(narrative).strip():
        return (None, None)

    clean_text = sanitize_input(narrative)
    text_lower = clean_text.lower()

    # 1. Temporal Sequence Check: prioritize what was happening at event time
    for pat in TEMPORAL_SEQUENCE_PATTERNS:
        m = re.search(pat, text_lower, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            candidate = re.sub(r"^(the|a|an|routine)\s+", "", candidate).strip()
            if candidate in ACTIVITY_ALIASES:
                return (ACTIVITY_ALIASES[candidate], "temporal_narrative_alias")
            for alias, cat in ACTIVITY_ALIASES.items():
                if alias in candidate:
                    return (cat, "temporal_narrative_subphrase")

    # 2. Direct keyword pattern search on clean narrative
    # Painting
    if re.search(r"\b(painting|paint application|spray painting|sandblasting|surface coating)\b", text_lower):
        return (ActivityCategory.PAINTING, "narrative_keyword_painting")

    # Laboratory / Research
    if re.search(r"\b(laboratory|lab testing|glassware cleaning|sample analysis|titration|chemical assay)\b", text_lower):
        return (ActivityCategory.LABORATORY_RESEARCH, "narrative_keyword_laboratory")

    # Cleaning / Housekeeping
    if re.search(r"\b(cleaning|housekeeping|washed|washing floor|degreasing|sweeping|spill cleanup)\b", text_lower):
        return (ActivityCategory.CLEANING, "narrative_keyword_cleaning")

    # Digging / Excavation
    if re.search(r"\b(trench excavation|digging a trench|digging|excavator was used|excavating|trenching|earthwork)\b", text_lower):
        return (ActivityCategory.DIGGING_EXCAVATION, "narrative_keyword_excavation")

    # Vehicle / Parking Operations
    if re.search(r"\b(parking vehicle|vehicle movement|vehicle operation|driving truck|forklift movement|reversing truck)\b", text_lower):
        return (ActivityCategory.VEHICLE_PARKING_OPERATIONS, "narrative_keyword_vehicle")

    # Lifting Operation / Crane Work
    if re.search(r"\b(lifting operation|crane lift|rigging load|suspended load lift|crane was carrying|hoisting)\b", text_lower):
        return (ActivityCategory.LIFTING_OPERATION, "narrative_keyword_lifting")

    # Welding / Hot Work
    if re.search(r"\b(welding|torch cutting|grinding flange|brazing|hot work was performed)\b", text_lower):
        return (ActivityCategory.WELDING_HOT_WORK, "narrative_keyword_welding")

    # Elevated Work / Scaffolding
    if re.search(r"\b(elevated maintenance|scaffolding|working at height|ladder work|roof access)\b", text_lower):
        return (ActivityCategory.ELEVATED_WORK_SCAFFOLDING, "narrative_keyword_elevated")

    # Internal Vessel Work
    if re.search(r"\b(confined-space entry|vessel entry|inside the tank|tank descaling|column entry)\b", text_lower):
        return (ActivityCategory.INTERNAL_VESSEL_WORK, "narrative_keyword_vessel")

    # Pipeline Maintenance
    if re.search(r"\b(pipeline maintenance|flange breaking|pressurized release while|pipe spool|valve servicing)\b", text_lower):
        return (ActivityCategory.PIPELINE_MAINTENANCE, "narrative_keyword_pipeline")

    # Electrical Maintenance
    if re.search(r"\b(electrical maintenance|troubleshooting|safety interlock|switchgear|breaker repair|wiring)\b", text_lower):
        return (ActivityCategory.ELECTRICAL_MAINTENANCE, "narrative_keyword_electrical")

    # General Equipment Maintenance
    if re.search(r"\b(maintenance|equipment servicing|pump repair|filter replacement|overhaul)\b", text_lower):
        return (ActivityCategory.EQUIPMENT_MAINTENANCE, "narrative_keyword_maintenance")

    # 3. Active narrative patterns regex
    for pat in ACTIVE_NARRATIVE_ACTIVITY_PATTERNS:
        match = re.search(pat, text_lower, re.IGNORECASE)
        if match:
            phrase = match.group(1).strip()
            phrase = re.sub(r"^(the|a|an|routine)\s+", "", phrase).strip()
            words = phrase.split()
            if any(w in STOP_WORDS for w in words):
                continue
            if phrase in ACTIVITY_ALIASES:
                return (ACTIVITY_ALIASES[phrase], "active_pattern_alias")
            for alias, cat in ACTIVITY_ALIASES.items():
                if alias in phrase:
                    return (cat, "active_pattern_substring")

    return (None, None)


def normalize_admin_flow_activity(
    raw_value: Optional[str] = None,
    narrative: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Normalizes an activity candidate or extracts it from narrative into a canonical operational activity category.
    Returns: (display_name, category_key, normalization_method)

    Hierarchy:
    1. Structured Activity / Job Task field (if valid and not an IOGP/barrier/hazard placeholder)
    2. Normalized Activity alias
    3. Narrative extraction (temporal & active grammar)
    4. UNKNOWN ACTIVITY (only when genuinely indeterminate)
    """
    raw_str = sanitize_input(raw_value)
    raw_lower = raw_str.lower()
    narrative_str = sanitize_input(narrative)

    # ── Step 1: Filter out uninformative sentinels ──
    if raw_lower in ["", "n/a", "na", "none", "unknown", "other", "unclassified", "not specified", "null"]:
        raw_str = ""
        raw_lower = ""

    # ── Step 2: Anti-contamination check for raw_value ──
    # If raw_value is strictly an IOGP rule name, barrier, hazard, or lone equipment name,
    # DO NOT accept it blindly as the activity! Extract genuine activity from narrative.
    is_contaminated = False
    if raw_lower:
        if raw_lower in FORBIDDEN_IOGP_RULE_NAMES:
            is_contaminated = True
        elif raw_lower in FORBIDDEN_BARRIER_NAMES:
            is_contaminated = True
        elif raw_lower in FORBIDDEN_HAZARD_NAMES:
            is_contaminated = True
        elif raw_lower in FORBIDDEN_EQUIPMENT_ONLY:
            is_contaminated = True

    # If not contaminated and matches an alias directly:
    if raw_lower and not is_contaminated:
        if raw_lower in ACTIVITY_ALIASES:
            cat = ACTIVITY_ALIASES[raw_lower]
            # If the user explicitly provided a recognized detailed task string, preserve it for compatibility
            if raw_lower in [
                "safe mechanical lifting",
                "vehicle operation / road transport",
                "hot work in classified area",
                "confined space vessel entry",
            ]:
                return (raw_str, cat, "exact_alias")
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "exact_alias")
        for alias, cat in ACTIVITY_ALIASES.items():
            if alias in raw_lower or raw_lower in alias:
                return (ACTIVITY_DISPLAY_NAMES[cat], cat, "substring_alias")

    # ── Step 3: Narrative Extraction ──
    if narrative_str:
        cat_extracted, method = extract_activity_from_narrative(narrative_str)
        if cat_extracted:
            return (ACTIVITY_DISPLAY_NAMES[cat_extracted], cat_extracted, method)

    # ── Step 4: If contaminated raw_value had an operational equivalent (e.g. driving -> vehicle operations) ──
    if is_contaminated:
        if raw_lower in ["driving"]:
            cat = ActivityCategory.VEHICLE_PARKING_OPERATIONS
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_driving")
        if raw_lower in ["safe mechanical lifting"]:
            cat = ActivityCategory.LIFTING_OPERATION
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_lifting")
        if raw_lower in ["energy isolation"]:
            cat = ActivityCategory.EQUIPMENT_MAINTENANCE
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_maintenance")
        if raw_lower in ["working at height"]:
            cat = ActivityCategory.ELEVATED_WORK_SCAFFOLDING
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_elevated")
        if raw_lower in ["hot work"]:
            cat = ActivityCategory.WELDING_HOT_WORK
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_hotwork")
        if raw_lower in ["confined space", "confined space entry"]:
            cat = ActivityCategory.INTERNAL_VESSEL_WORK
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_confined")
        if raw_lower in ["line of fire", "line of fire work"]:
            cat = ActivityCategory.PIPELINE_MAINTENANCE
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_lineoffire")
        if raw_lower in ["work authorization"]:
            cat = ActivityCategory.DIGGING_EXCAVATION
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_excavation")
        if raw_lower in ["bypassing safety controls", "bypass / override work"]:
            cat = ActivityCategory.ELECTRICAL_MAINTENANCE
            return (ACTIVITY_DISPLAY_NAMES[cat], cat, "operational_remapping_electrical")

    # If raw string was provided and wasn't contaminated, return title-cased custom activity
    if raw_str and not is_contaminated and len(raw_str.split()) <= 4:
        return (raw_str.title(), ActivityCategory.OTHER_KNOWN_ACTIVITY, "structured_identity")

    # ── Step 5: Legitimate UNKNOWN ACTIVITY ──
    return (
        ACTIVITY_DISPLAY_NAMES[ActivityCategory.UNKNOWN_ACTIVITY],
        ActivityCategory.UNKNOWN_ACTIVITY,
        "unknown_indeterminate",
    )


@dataclass
class ActivityObservation:
    """
    Evaluated observation of an operational work activity from an incident.
    """
    incident_id: str
    workspace_id: str
    activity_name: str
    activity_category: str
    source_field: str
    normalization_method: str
    is_psif: bool
    location: str
    associated_barrier: Optional[str] = None
    associated_barrier_state: Optional[str] = None
    associated_iogp_rule: Optional[str] = None
    narrative_snippet: str = ""
    incident_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "workspace_id": self.workspace_id,
            "activity_name": self.activity_name,
            "activity_category": self.activity_category,
            "source_field": self.source_field,
            "normalization_method": self.normalization_method,
            "is_psif": self.is_psif,
            "location": self.location,
            "associated_barrier": self.associated_barrier,
            "associated_barrier_state": self.associated_barrier_state,
            "associated_iogp_rule": self.associated_iogp_rule,
            "narrative_snippet": self.narrative_snippet,
            "incident_date": self.incident_date,
        }
