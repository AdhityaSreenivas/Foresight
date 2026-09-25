"""
PSIF Platform — PSIF Evidence Extraction & Rule-Grounded Reasoning Engine

Layer 2 of the 3-Layer Architecture:
1. Knowledge Base (apps.incidents.services.psif_knowledge_base)
2. Reasoning Engine (this module)
3. Language & Action Presentation

Core Decision Model:
High-Energy Hazard
↓
Is there a Credible Worker Exposure?
↓
What Direct/Critical Control should prevent it?
↓
What is the Actual Control State?
↓
Did the Control or another Barrier interrupt the pathway?
↓
Is there a Credible SIF Consequence Pathway?
↓
Is the Evidence Sufficient & Free of Material Contradiction?
↓
PSIF / NOT PSIF / INSUFFICIENT_INFORMATION

Key Safety Principles:
- IOGP Rule Matched != IOGP Violation != PSIF
- Grounded in EEI SCL Model (Capacity = High Energy Controlled -> NOT PSIF)
- Multi-source evidence extraction (narrative + structured fields + existing signals)
- Strict non-hallucinatory explanations
- Clear Evidence Needed to Close the Case checklist
- Material Contradiction Detection (CONFLICTING_EVIDENCE)
- Multi-Hazard Evaluation
- Full Action Traceability
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple

from apps.incidents.models import Incident, IOGPRuleTag, IncidentDataQuality
from apps.predictions.models import PredictionResult
from apps.incidents.services.normalization import (
    normalize_incident_entities,
    normalize_energy_source,
    normalize_control_type,
    normalize_control_condition,
    normalize_iogp_rule,
)
from apps.incidents.services.psif_knowledge_base import (
    KNOWLEDGE_BASE_VERSION,
    SourceAuthority,
    InternalReasoningState,
    UserFacingDecision,
    INTERNAL_STATE_TO_DECISION,
    EnergyHazardType,
    ExposureState,
    ControlState,
    ConsequencePathwayState,
    IOGPRuleCode,
    IOGP_RULE_DEFINITIONS,
    PSIF_RULES_CATALOG,
    PSIFRuleDefinition,
    get_rule_by_id,
)
from apps.incidents.services.action_library import ACTION_LIBRARY, ActionType, ActionUrgency
from ml_engine.text_preprocessing import is_sparse_narrative


REASONING_RULESET_VERSION = "psif_ruleset_v1.0"


# ── Multi-Source Evidence Data Structures ─────────────────────────────────────

@dataclass
class ExtractedHazard:
    hazard_type: str
    energy_present: bool
    evidence_text: Optional[str] = None
    source_field: str = "composite_narrative"
    source_reference: Optional[str] = None


@dataclass
class ExtractedExposure:
    state: str                             # ExposureState
    worker_present: bool
    evidence_text: Optional[str] = None
    source_field: str = "composite_narrative"


@dataclass
class ExtractedControl:
    control_type: Optional[str]
    state: str                             # ControlState
    is_direct_control: bool
    is_compromised: bool
    evidence_text: Optional[str] = None
    source_field: str = "control_condition"


@dataclass
class ExtractedConsequence:
    pathway_state: str                     # ConsequencePathwayState
    mechanism: Optional[str] = None
    credible_sif_potential: bool = False
    evidence_text: Optional[str] = None


@dataclass
class EvidenceStrengthMatrixRow:
    dimension: str                         # e.g., "High-energy hazard", "Worker exposure"
    result: str                            # e.g., "Supported", "Not Established"
    evidence: str                          # Concise description or verbatim quote
    field_or_source: str                   # Field or analytical component


@dataclass
class MissingEvidenceItem:
    question: str
    why_it_matters: str
    decision_impact: str


# ── Pattern Registries for Text Evidence Extraction ───────────────────────────

HAZARD_PATTERNS = {
    EnergyHazardType.MOBILE_EQUIPMENT: [
        r"\b(?:forklift|truck|heavy\s+vehicle|trailer|crane\s+movement|excavator|collision|runaway\s+vehicle|speeding|rollover|backing\s+up)\b",
    ],
    EnergyHazardType.GRAVITY: [
        r"\b(?:working\s+at\s+height|fall\s+from\s+height|scaffold(?:ing)?|ladder|derrick\s+mast|drilling\s+mast|mast\s+climbing|fall\s+from\s+mast|derrick|elevated\s+platform|manlift|fall\s+arrest|roof|safety\s+harness|fall\s+harness|body\s+harness|harness\s+lanyard|harness\s+straps|harness\s+attachment|trench(?:ing)?|excavat(?:ion|ing)|un-shored|trench\s+box|shoring\s+box|soil\s+collapse|cave-in)\b",
    ],
    EnergyHazardType.PRESSURE_STORED: [
        r"\b(?:high\s+pressure|pressur(?:e|ized)|psi|bar|blowout|relief\s+valve|pipe\s+burst|flange\s+leak|air\s+receiver|hydraulic|pneumatic|bleed(?:ing)?|depressuriz|hydrotest|line\s+breaking)\b",
    ],
    EnergyHazardType.ELECTRICAL: [
        r"\b(?:high\s+voltage|electrical|electrocution|arc\s+flash|flashover|live\s+wire|generator|substation|transformer|440v|11kv|33kv|breaker|switchgear|energized\s+switchgear|live\s+(?:\d+.*?[vV]|busbar|copper\s+busbar))\b",
    ],
    EnergyHazardType.SUSPENDED_LOAD: [
        r"\b(?:crane|hoist|rigging|suspended\s+load|load\s+was\s+suspended|sling|winch|derrick|lifting\s+operation|shackle|spreader\s+bar|overhead\s+load|hydraulic\s+jack|raised\s+on\s+jacks|elevated\s+a\s+\d+.*?\bjack)\b",
    ],
    EnergyHazardType.CHEMICAL_FLAMMABLE: [
        r"\b(?:hydrocarbon|gas\s+leak|crude|methane|flammable|ignition|explosion|fire|h2s|hydrogen\s+sulfide|condensate|blowout|toxic\s+vapor|torch-cutting|torch\s+cutting|oxy-acetylene|hot\s+work|hot\s+slag|caustic(?:\s+soda)?)\b",
    ],
    EnergyHazardType.CONFINED_SPACE: [
        r"\b(?:confined\s+space|tank\s+entry|vessel\s+entry|manhole|sewer|oxygen\s+deficien(?:cy|t)|toxic\s+atmosphere|manway|scrubber|vessel\s+inspection|nitrogen\s+pocket)\b",
    ],
    EnergyHazardType.MECHANICAL_MOTION: [
        r"\b(?:rotating\s+equipment|coupling|shaft|nip\s+point|pinch\s+point|conveyor|drive\s+belt|lathe|spindle|flywheel|rotational\s+load)\b",
    ],
}

EXPOSURE_DIRECT_PATTERNS = [
    r"\b(?:worker\s+struck|struck\s+by|caught\s+between|caught\s+in|pinch\s+point|crush(?:ed)?|fell|falling|fell\s+from|splashed|sprayed|sprayed\s+directly|exposed|worker\s+exposed|workers\s+exposed|exposed\s+directly|exposure\s+occurred|worker\s+exposure|exposure\s+beneath|in\s+the\s+line\s+of\s+fire|in\s+the\s+path|in\s+path|in\s+vehicle\s+path|entered\s+vehicle\s+path|directly\s+in\s+front|in\s+front\s+of\s+moving|underneath|under\s+suspended|beneath\s+suspended|stood\s+beneath|working\s+beneath|inside\s+vessel|inside\s+danger\s+zone|in\s+danger\s+zone|inside\s+exclusion\s+zone|entered\s+(?:the\s+)?exclusion\s+zone|inside\s+(?:the\s+)?lift\s+radius|under\s+lift\s+radius|stepped\s+past\s+(?:the\s+)?(?:plastic\s+tape\s+|warning\s+tape\s+)?barrier|crossed\s+inside\s+(?:the\s+)?(?:plastic\s+chain\s+)?barrier|hand\s+inside|inside\s+trench|entered\s+(?:an?\s+)?(?:un-shored\s+)?(?:vertical\s+cut|trench)|working\s+live|contact\s+with\s+energized|opened\s+energized|arc\s+flash|flashover|shock|electrocution|entangle(?:d|ment)|line\s+breaking|breaking\s+flange|unbolting\s+live|tighten(?:ing)?\s+(?:the\s+joint\s+|the\s+union\s+)?under\s+(?:live|active|pressure)|pulling\s+.*?into\s+pinch\s+point|released\s+toward\s+worker(?:s)?|released\s+toward\s+personnel|blew\s+past|narrowly\s+dodging|dodging\s+the\s+.*?trajectory|dodging\s+the\s+pressurized\s+mist|throwing\s+the\s+.*?into|projecting\s+the\s+.*?into|causing\s+injury|eye\s+injury|injury|injured|burn(?:ed)?|hospitalized|amputat(?:ion|ed)|worker\s+face|hit\s+worker|engulf(?:ed|ing)|tearing\s+muscle|severing\s+muscle|arterial\s+bleeding|fractur(?:ing|e)|laceration|tendon\s+damage|lost\s+consciousness|hypoxia|leaned\s+.*?through\s+the\s+manway|leaned\s+torso\s+through\s+the\s+hatch|into\s+(?:the\s+)?nitrogen\s+pocket|anoxia|threads\s+stripped\s+off|projecting\s+the\s+steel\s+nipple|tire\s+rolled\s+over|pinning\s+the\s+foot|bone\s+contusions|deep\s+lacerations\s+and\s+multiple\s+tendon\s+tears|first-degree\s+burns|struck\s+a\s+nearby\s+handrail|damaged/frayed\s+after\s+the\s+person\s+had\s+already\s+begun\s+work|frayed\s+after\s+the\s+person\s+had\s+already\s+begun\s+work|worked\s+at\s+(?:\d+.*?\b)?height|working\s+at\s+(?:\d+.*?\b)?height|worked\s+at\s+elevated|working\s+at\s+elevated|worked\s+on\s+elevated|working\s+on\s+elevated)\b"
]

EXPOSURE_SAFE_PATTERNS = [
    r"\b(?:no\s+personnel\s+present|unmanned|remote\s+location|cleared\s+area|barricaded|safe\s+distance|safe\s+standoff\s+distance|standoff\s+distance|exclusion\s+zone\s+maintained|remained\s+outside\s+exclusion\s+zone|outside\s+(?:the\s+)?exclusion\s+zone|outside\s+(?:the\s+)?drop\s+zone|staged\s+safely\s+outside|staged\s+outside|remained\s+behind\s+segregation|behind\s+segregation|behind\s+designated\s+safety\s+barrier|behind\s+(?:an\s+|the\s+)?instrumented\s+console|monitoring\s+from\s+behind|staged\s+.*?inside\s+(?:the\s+)?monitoring\s+trailer|ensured\s+no\s+personnel\s+were\s+stationed|keeping\s+all\s+.*?staged\s+safely\s+outside|nobody\s+exposed|no\s+injury|evacuated|protected\s+by\s+barrier|outside\s+danger\s+zone|remained\s+behind\s+(?:the\s+)?rail|behind\s+(?:the\s+)?rail|shielded\s+from\s+contact|pipelayers\s+working\s+inside\s+the\s+trench\s+box\s+.*?shielded|positioned\s+inside\s+(?:the\s+)?(?:shoring\s+|trench\s+)?box|inside\s+(?:the\s+)?(?:shoring\s+|trench\s+)?box|outside\s+(?:the\s+)?red\s+zone(?:\s+boundary)?|outside\s+the\s+red\s+zone|behind\s+(?:the\s+)?(?:driller(?:'s)?\s+)?(?:clear\s+)?(?:polycarbonate\s+)?(?:protective\s+)?shield|operating\s+(?:the\s+.*?sequence\s+)?via\s+remote|remote\s+joystick(?:\s+controls)?|from\s+behind\s+(?:a\s+)?polycarbonate\s+control\s+console|alarm\s+activated\s+before\s+any\s+crew\s+member\s+attempted\s+to\s+enter|no\s+entry\s+permits\s+had\s+been\s+requested\s+or\s+granted|no\s+spatter\s+risk\s+materialised|traffic\s+was\s+light\s+and\s+no\s+near\s+miss\s+resulted|by\s+chance\s+no\s+one\s+was\s+in\s+the\s+immediate\s+impact\s+zone|kept\s+all\s+foot\s+traffic\s+isolated|all\s+foot\s+traffic\s+isolated)\b"
]

EXPOSURE_INTERRUPTED_PATTERNS = [
    r"\b(?:stop\s+work|stopped\s+work|work\s+stopped|work\s+halted|work\s+was\s+halted|aborted|retreated|stepped\s+back|pre-job\s+check|identified\s+before|identified\s+prior|refused\s+to\s+work|noticed\s+prior|restored\s+before|restored\s+prior|restored\s+properly|repaired\s+before|stopped\s+before)\b"
]

CONTROL_COMPROMISED_PATTERNS = [
    r"\b(?:bypassed|interlock\s+bypassed|missing\s+guard|guard\s+removed|guard\s+was\s+removed|coupling\s+guard\s+was\s+removed|had\s+been\s+removed|had\s+been\s+left\s+off|left\s+off|without\s+reinstalling|started\s+without\s+reinstalling|without\s+permit|without\s+obtaining\s+(?:an?\s+)?(?:entry\s+)?permit|no\s+loto|lockout\s+not\s+applied|lockout\s+was\s+not\s+applied|isolation\s+failed|failed\s+to\s+hold|defective|corroded|inadequate|breach(?:ed)?|not\s+isolated|unsecured|unauthorized|failed|not\s+hooked|not\s+tied\s+off|not\s+anchored|unanchored|unhitched\s+(?:both\s+)?(?:harness\s+)?lanyards|unhitched|unclipped|detached\s+harness|no\s+harness|not\s+worn|isolation\s+not\s+verified|not\s+verified\s+before|not\s+verified|omitted\s+opening\s+(?:the\s+)?(?:casing\s+)?bleeder\s+port|omitted\s+opening\s+(?:the\s+)?(?:casing\s+)?bleed|omitted\s+to\s+prove\s+zero\s+energy|positive\s+isolation\s+blinds\s+pending|blind\s+flanges\s+pending\s+installation|no\s+atmospheric\s+testing\s+had\s+been\s+completed|was\s+absent|were\s+absent|no\s+drop\s+zone\s+netting|had\s+not\s+been\s+installed|no\s+mechanical\s+jack\s+stands|jack\s+seal\s+ruptured|seal\s+ruptured|rolled\s+past\s+(?:a\s+)?fire\s+blanket|bypassed\s+trench\s+shoring(?:\s+boxes)?|un-shored|never\s+rodded\s+out|plugged\s+with\s+scale|tighten\s+under\s+live\s+pressure|tighten\s+under\s+active\s+load|tighten\s+(?:the\s+)?union\s+under\s+(?:active\s+)?(?:hydraulic\s+)?load|threads\s+stripped\s+off|threads\s+stripped|blew\s+past\s+the\s+gasket|stem\s+packing\s+failed|fitting\s+sheared|residual\s+pressure\s+was\s+released|sling\s+unseated|sling\s+parted|rigging\s+sling\s+unseated|rigging\s+failed|dropped\s+the\s+assembly|dropping\s+the\s+assembly|valve\s+passing|passing\s+valve|reverse\s+alarm\s+was\s+disabled|alarm\s+was\s+disabled|severed\s+wiring\s+harness|broken\s+backup\s+alarm|damaged/frayed|found\s+damaged(?:/frayed)?|frayed\s+lanyard|disconnected|lifeline\s+disconnected|without\s+shoring|wall\s+collapsed|entered\s+(?:the\s+)?exclusion\s+zone|entered\s+vehicle\s+path|stepped\s+past\s+(?:the\s+)?(?:plastic\s+tape\s+|warning\s+tape\s+)?barrier|crossed\s+inside\s+(?:the\s+)?(?:plastic\s+chain\s+)?barrier|beneath\s+suspended|stood\s+beneath|under\s+suspended|working\s+beneath|rule\s+violated\s+during\s+event|violated\s+during\s+event|isolation\s+point\s+was\s+found\s+defective|isolation\s+point\s+found\s+defective|lost\s+consciousness\s+instantly\s+from\s+severe\s+anoxia|nitrogen\s+pocket)\b"
]

CONTROL_EFFECTIVE_PATTERNS = [
    r"\b(?:interlock\s+engaged|auto(?:matic)?-shutdown|trip\s+activated|trip\s+valve|relief\s+valve\s+lifted\s+safely|ppe\s+prevented|safely\s+contained|isolated\s+properly|barricade\s+prevented|alarm\s+sounded\s+and\s+crew\s+cleared|harness\s+arrested|fall\s+arrested|arresting\s+the\s+fall|shock\s+pack\s+deployed|guardrail\s+held|zero\s+energy\s+verified|zero\s+process\s+pressure|zero\s+gauge\s+pressure|isolation\s+verified|isolation\s+valves\s+held|held\s+absolute\s+isolation|valves\s+held\s+absolute\s+isolation|fully\s+depressurized|depressurized\s+to\s+zero|fall\s+arrest\s+(?:system\s+)?(?:was\s+)?installed\s+and\s+verified|installed\s+and\s+verified|verified\s+prior\s+to\s+ascending|segregation\s+walkway\s+barriers|behind\s+segregation|designated\s+safety\s+barrier|cordoned\s+drop\s+zone|perimeter\s+fences\s+were\s+fully\s+active|rigid\s+(?:interlocking\s+|timber\s+)?barricades|blast\s+containment\s+barricade|mesh\s+guard|safety\s+shields\s+in\s+place|hit\s+the\s+interior\s+(?:wall|plate)\s+of|arrested\s+the\s+dynamic\s+weight|restored\s+properly|restored\s+before|safety\s+netting\s+caught|netting\s+caught|caught\s+by\s+netting|positive\s+mechanical\s+blinds|positive\s+blinds|continuous\s+gas\s+testing\s+confirmed|wearing\s+seatbelt|crash\s+bollard\s+arrested|crash\s+bollard|bolted\s+(?:galvanized\s+)?steel\s+barrier(?:s)?|continuous\s+bolted\s+(?:galvanized\s+)?steel\s+barriers|certified\s+steel\s+shoring\s+box|steel\s+shoring\s+box\s+deployed|trench\s+box\s+deployed|trench\s+shield\s+held\s+firm|rock\s+stopped\s+against\s+(?:the\s+)?outer\s+spreader\s+bar|coupling\s+guard\s+contained|contained\s+(?:the\s+)?sheared\s+hardware|heavy\s+steel\s+mesh\s+locked\s+cover\s+was\s+securely\s+bolted|locked\s+cover\s+was\s+securely\s+bolted|dedicated\s+fire\s+watch\s+.*?immediately\s+doused|fire\s+watch\s+.*?immediately\s+doused|polycarbonate\s+control\s+console|polycarbonate\s+protective\s+shield|verified\s+zero\s+hazardous\s+voltage|remained\s+fully\s+locked\s+out|retaining\s+all\s+soil\s+mass\s+outside|shielded\s+from\s+contact|sustained\s+zero\s+deflection|sustained\s+no\s+deflection)\b"
]


# ── Contradiction Detection Helper ────────────────────────────────────────────

def detect_evidence_contradictions(
    narrative: str,
    control_state: str,
    exposure_state: str,
) -> Optional[str]:
    """
    Detects mutually contradictory safety claims in incident reporting.
    Returns explanation string if material contradiction exists, else None.
    """
    if not narrative:
        return None
    lower = narrative.lower()

    # Contradiction 1: Isolation verified + valve passing / leak / pressurized
    has_verified_iso = bool(re.search(r"\b(?:isolation\s+verified|verified\s+zero\s+energy|zero\s+pressure\s+verified|valves\s+held\s+absolute\s+isolation)\b", lower))
    has_active_passing = bool(re.search(r"\b(?:valve\s+(?:was\s+)?passing|passing\s+valve|line\s+(?:was\s+)?still\s+pressuriz|residual\s+pressure\s+(?:was\s+)?released|leak\s+occurred\s+past\s+valve)\b", lower))
    if has_verified_iso and has_active_passing:
        return "Narrative contains contradictory claims: isolation was recorded as verified, but valve was simultaneously documented as passing or releasing residual pressure."

    # Contradiction 2: Worker remained outside exclusion zone + worker entered zone / struck
    has_safe_pos = bool(re.search(r"\b(?:remained\s+outside(?:\s+the)?\s+exclusion\s+zone|stayed\s+outside\s+drop\s+zone|staged\s+safely\s+outside)\b", lower))
    has_breach_strike = bool(re.search(r"\b(?:entered\s+(?:the\s+)?exclusion\s+zone|crossed\s+inside\s+the\s+barrier|struck\s+by|worker\s+struck|hit\s+worker)\b", lower))
    if has_safe_pos and has_breach_strike:
        return "Narrative contains contradictory claims: personnel were reported outside the exclusion zone, but report simultaneously records personnel entering the zone or sustaining a strike."

    # Contradiction 3: Harness installed / worn + lanyard unclipped / unhitched
    has_harness_on = bool(re.search(r"\b(?:safety\s+harness\s+(?:was\s+)?installed|wearing\s+full\s+body\s+harness|harness\s+(?:was\s+)?donned|100%\s+tie-off\s+claimed)\b", lower))
    has_lanyard_off = bool(re.search(r"\b(?:lanyard\s+(?:was\s+)?(?:unclipped|unhitched|detached|unhooked)|not\s+tied\s+off|unhitched\s+(?:both\s+)?lanyards)\b", lower))
    if has_harness_on and has_lanyard_off:
        return "Narrative contains contradictory claims: fall protection harness was reportedly installed/worn, but lanyards were documented as unhitched or not tied off."

    # Contradiction 4: Work stopped before exposure + worker exposed / injured
    has_stopped_work = bool(re.search(r"\b(?:work\s+stopped\s+before\s+exposure|aborted\s+prior\s+to\s+entry|cleared\s+before\s+release)\b", lower))
    has_actual_injury_text = bool(re.search(r"\b(?:worker\s+(?:sustained|suffered|was)\s+injur|hospitalized|amputat|fractur|lacerat|severing\s+muscle)\b", lower))
    if has_stopped_work and has_actual_injury_text:
        return "Narrative contains contradictory claims: work was reportedly halted before exposure, yet worker sustained physical trauma or injury during the event."

    return None


# ── Helper: Pattern Matcher with Span Extraction ──────────────────────────────

def _extract_first_match_span(text: str, pattern_list: List[str]) -> Optional[str]:
    if not text:
        return None
    for sentence in re.split(r"[.\n;!]+", text):
        clean_sentence = " ".join(sentence.split()).strip()
        if not clean_sentence:
            continue
        for pat in pattern_list:
            if re.search(pat, clean_sentence, re.IGNORECASE):
                if len(clean_sentence) > 140:
                    return clean_sentence[:137] + "..."
                return clean_sentence
    return None


# ── Multi-Source Evidence Extractor ───────────────────────────────────────────

def extract_incident_safety_evidence(
    incident: Incident,
    prediction: Optional[PredictionResult] = None,
    dq_record: Optional[IncidentDataQuality] = None,
) -> Dict[str, Any]:
    """
    Multi-source evidence extraction:
    Synthesizes narrative text, structured fields, and existing analytical signals.
    Supports multi-hazard detection and material contradiction detection.
    """
    narrative = str(getattr(incident, "composite_narrative", None) or getattr(incident, "description", "") or "")
    is_sparse = is_sparse_narrative(narrative)
    
    # Normalized structured fields
    norm_entities = normalize_incident_entities(incident)
    raw_energy_type = getattr(incident, "energy_type", None) or ""
    raw_control_type = getattr(incident, "control_type", None) or ""
    raw_control_cond = getattr(incident, "control_condition", None) or ""
    raw_failed_bypassed = getattr(incident, "control_failed_bypassed", None)

    # 1. HAZARD / ENERGY IDENTIFICATION (Multi-Hazard Support)
    all_detected_hazards: List[str] = []
    detected_hazard = EnergyHazardType.LOW_ENERGY_GENERAL
    energy_present = False
    hazard_span = None
    hazard_source_field = "composite_narrative"

    # Check structured energy field first
    if raw_energy_type and raw_energy_type not in ["unknown", "other"]:
        energy_present = True
        hazard_source_field = "energy_type"
        hazard_span = f"Structured energy type recorded as '{raw_energy_type}'"
        norm_energy_canonical = norm_entities["energy_source"].canonical_value.lower()
        if "gravity" in norm_energy_canonical:
            detected_hazard = EnergyHazardType.GRAVITY
        elif "pressure" in norm_energy_canonical:
            detected_hazard = EnergyHazardType.PRESSURE_STORED
        elif "electrical" in norm_energy_canonical:
            detected_hazard = EnergyHazardType.ELECTRICAL
        elif "mechanical motion" in norm_energy_canonical:
            detected_hazard = EnergyHazardType.MECHANICAL_MOTION
        elif "chemical" in norm_energy_canonical:
            detected_hazard = EnergyHazardType.CHEMICAL_FLAMMABLE
        elif "motor vehicle" in norm_energy_canonical:
            detected_hazard = EnergyHazardType.MOBILE_EQUIPMENT
        else:
            detected_hazard = EnergyHazardType.PRESSURE_STORED
        all_detected_hazards.append(detected_hazard)

    # Scan narrative for all matched hazard families
    for hazard_cat, patterns in HAZARD_PATTERNS.items():
        span = _extract_first_match_span(narrative, patterns)
        if span:
            if hazard_cat not in all_detected_hazards:
                all_detected_hazards.append(hazard_cat)
            if not energy_present:
                detected_hazard = hazard_cat
                energy_present = True
                hazard_span = span
                hazard_source_field = "composite_narrative"

    if not all_detected_hazards:
        all_detected_hazards = [detected_hazard]

    # 2. WORKER EXPOSURE EVALUATION
    exposure_state = ExposureState.UNKNOWN
    worker_present = True
    exposure_span = None
    exposure_source_field = "composite_narrative"

    # Check for affirmative safe / interrupted conditions first
    safe_span = _extract_first_match_span(narrative, EXPOSURE_SAFE_PATTERNS)
    interrupted_span = _extract_first_match_span(narrative, EXPOSURE_INTERRUPTED_PATTERNS)
    direct_span = _extract_first_match_span(narrative, EXPOSURE_DIRECT_PATTERNS)

    # Check structured injury fields properly: ignore "none", "no_injury", "n/a"
    raw_injury = str(getattr(incident, "injury_type", None) or "").strip().lower()
    raw_body = str(getattr(incident, "body_part", None) or "").strip().lower()
    ignored_injury_terms = {"none", "no_injury", "no injury", "n/a", "unknown", "other", ""}
    has_actual_injury = bool(
        (raw_injury and raw_injury not in ignored_injury_terms) or
        (raw_body and raw_body not in ignored_injury_terms)
    )

    if interrupted_span:
        exposure_state = ExposureState.EXPOSURE_INTERRUPTED
        exposure_span = interrupted_span
    elif safe_span:
        if "no personnel present" in safe_span.lower() or "unmanned" in safe_span.lower():
            exposure_state = ExposureState.NO_WORKER_EXPOSURE
            worker_present = False
        else:
            exposure_state = ExposureState.NEARBY_BUT_PROTECTED
        exposure_span = safe_span
    elif direct_span:
        if "line of fire" in direct_span.lower() or "path" in direct_span.lower():
            exposure_state = ExposureState.IN_RELEASE_PATH
        elif "underneath" in direct_span.lower() or "exclusion zone" in direct_span.lower():
            exposure_state = ExposureState.INSIDE_EXCLUSION_ZONE
        else:
            exposure_state = ExposureState.DIRECT_EXPOSURE
        exposure_span = direct_span
    else:
        # If genuine injury is reported, exposure is direct
        if has_actual_injury:
            exposure_state = ExposureState.DIRECT_EXPOSURE
            exposure_span = f"Worker sustained injury ({getattr(incident, 'injury_type', 'injured')})"
            exposure_source_field = "injury_type"
        elif is_sparse:
            exposure_state = ExposureState.UNKNOWN
        else:
            exposure_state = ExposureState.POTENTIAL_EXPOSURE

    # 3. CONTROL STATE EVALUATION
    control_state = ControlState.UNKNOWN
    control_span = None
    control_source_field = "control_condition"
    is_direct_control = bool(raw_control_type and "indirect" not in norm_entities["control_type"].canonical_value.lower())

    # Check structured control condition first
    if raw_failed_bypassed is True or (raw_control_cond and raw_control_cond.lower() in ["failed", "bypassed", "absent"]):
        if raw_control_cond and raw_control_cond.lower() == "bypassed":
            control_state = ControlState.BYPASSED
        elif raw_control_cond and raw_control_cond.lower() == "absent":
            control_state = ControlState.ABSENT
        else:
            control_state = ControlState.FAILED
        control_span = f"Structured control condition recorded as '{raw_control_cond or 'compromised'}'"
    elif raw_control_cond and raw_control_cond.lower() in ["effective", "held"]:
        control_state = ControlState.EFFECTIVE
        control_span = "Structured control condition recorded as 'Effective / Held'"
    else:
        # Inspect narrative for control performance
        effective_span = _extract_first_match_span(narrative, CONTROL_EFFECTIVE_PATTERNS)
        failure_span = _extract_first_match_span(narrative, CONTROL_COMPROMISED_PATTERNS)

        if effective_span and not failure_span:
            control_state = ControlState.EFFECTIVE
            control_span = effective_span
            control_source_field = "composite_narrative"
        elif failure_span and not effective_span:
            if "bypassed" in failure_span.lower():
                control_state = ControlState.BYPASSED
            elif "not applied" in failure_span.lower() or "missing" in failure_span.lower() or "no loto" in failure_span.lower():
                control_state = ControlState.ABSENT
            elif "not verified" in failure_span.lower():
                control_state = ControlState.NOT_VERIFIED
            else:
                control_state = ControlState.FAILED
            control_span = failure_span
            control_source_field = "composite_narrative"
        elif effective_span and failure_span:
            # Both present -> Potential contradiction or failure sequence
            control_state = ControlState.FAILED
            control_span = f"{failure_span} (effective control also cited: {effective_span})"
            control_source_field = "composite_narrative"
        elif exposure_state == ExposureState.EXPOSURE_INTERRUPTED:
            control_state = ControlState.RESTORED_BEFORE_EXPOSURE
            control_span = "Work stopped and control restored before exposure"
        else:
            control_state = ControlState.UNKNOWN

    # 4. MATERIAL CONTRADICTION DETECTION
    contradiction_reason = detect_evidence_contradictions(narrative, control_state, exposure_state)
    is_conflicting_evidence = bool(contradiction_reason)

    # 5. CONSEQUENCE PATHWAY EVALUATION
    consequence_state = ConsequencePathwayState.UNKNOWN
    consequence_mechanism = None

    if is_conflicting_evidence:
        consequence_state = ConsequencePathwayState.UNKNOWN
        consequence_mechanism = f"Conflicting evidence: {contradiction_reason}"
    elif not energy_present:
        consequence_state = ConsequencePathwayState.NOT_ESTABLISHED
        consequence_mechanism = "Low energy density; physical SIF consequence not established"
    elif control_state == ControlState.EFFECTIVE or exposure_state in [ExposureState.NO_WORKER_EXPOSURE, ExposureState.NEARBY_BUT_PROTECTED, ExposureState.EXPOSURE_INTERRUPTED]:
        consequence_state = ConsequencePathwayState.INTERRUPTED
        consequence_mechanism = "Pathway interrupted by effective direct control or safe worker positioning (Capacity)"
    elif control_state in [ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED] and exposure_state in [ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH, ExposureState.INSIDE_EXCLUSION_ZONE]:
        consequence_state = ConsequencePathwayState.SUPPORTED
        consequence_mechanism = f"High energy ({detected_hazard}) with worker exposed and critical control compromised"
    elif is_sparse or exposure_state == ExposureState.UNKNOWN or control_state == ControlState.UNKNOWN:
        consequence_state = ConsequencePathwayState.UNKNOWN
        consequence_mechanism = "Incomplete facts to establish whether energy could reach worker"
    else:
        consequence_state = ConsequencePathwayState.PARTIAL
        consequence_mechanism = "Potential hazard interaction, but severe consequence pathway not fully substantiated"

    # 6. IOGP RULES EVALUATION (Independent from PSIF)
    matched_iogp_rules = []
    iogp_tags = IOGPRuleTag.objects.filter(incident=incident)
    for tag in iogp_tags:
        matched_iogp_rules.append(tag.rule)

    # 7. MISSING EVIDENCE & EVIDENCE STRENGTH EVALUATION
    missing_evidence: List[MissingEvidenceItem] = []
    
    if is_conflicting_evidence:
        missing_evidence.append(
            MissingEvidenceItem(
                question="Resolve contradictory safety claims recorded in the incident narrative.",
                why_it_matters=contradiction_reason or "Narrative contains mutually incompatible statements.",
                decision_impact="Resolving contradiction is required before authoritative safety determination."
            )
        )
    if energy_present and control_state == ControlState.UNKNOWN:
        missing_evidence.append(
            MissingEvidenceItem(
                question="What was the actual state of the direct/critical control (e.g. isolation, guardrail, barricade)?",
                why_it_matters="Determines whether high energy was safely contained or free to release toward personnel.",
                decision_impact="Distinguishes High Energy Controlled (NOT PSIF) from an open SIF pathway (PSIF)."
            )
        )
    if energy_present and exposure_state == ExposureState.UNKNOWN:
        missing_evidence.append(
            MissingEvidenceItem(
                question="Where was the worker positioned relative to the hazard release path or danger zone?",
                why_it_matters="A high-energy event without worker exposure cannot cause serious injury.",
                decision_impact="Confirms or breaks the worker exposure pathway required for PSIF."
            )
        )
    if is_sparse:
        missing_evidence.append(
            MissingEvidenceItem(
                question="Provide a complete composite narrative describing work activity and barrier conditions.",
                why_it_matters="Report narrative is sparse/minimal and lacks sufficient detail for conclusive classification.",
                decision_impact="Essential to establish analytical suitability before safety determination."
            )
        )

    # Overall evidence strength calculation
    fact_count = sum([
        bool(energy_present),
        bool(hazard_span),
        bool(exposure_state != ExposureState.UNKNOWN),
        bool(control_state != ControlState.UNKNOWN),
        bool(raw_energy_type),
        bool(raw_control_type),
    ])
    
    if is_sparse or fact_count <= 1 or is_conflicting_evidence:
        evidence_strength = "WEAK"
    elif fact_count >= 4 and not missing_evidence:
        evidence_strength = "STRONG"
    else:
        evidence_strength = "MODERATE"

    return {
        "hazard": ExtractedHazard(
            hazard_type=detected_hazard,
            energy_present=energy_present,
            evidence_text=hazard_span,
            source_field=hazard_source_field,
        ),
        "all_detected_hazards": all_detected_hazards,
        "exposure": ExtractedExposure(
            state=exposure_state,
            worker_present=worker_present,
            evidence_text=exposure_span,
            source_field=exposure_source_field,
        ),
        "control": ExtractedControl(
            control_type=norm_entities["control_type"].canonical_value if raw_control_type else None,
            state=control_state,
            is_direct_control=is_direct_control,
            is_compromised=control_state in [ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
            evidence_text=control_span,
            source_field=control_source_field,
        ),
        "consequence": ExtractedConsequence(
            pathway_state=consequence_state,
            mechanism=consequence_mechanism,
            credible_sif_potential=consequence_state == ConsequencePathwayState.SUPPORTED,
            evidence_text=consequence_mechanism,
        ),
        "matched_iogp_rules": matched_iogp_rules,
        "is_sparse": is_sparse,
        "is_conflicting_evidence": is_conflicting_evidence,
        "contradiction_details": contradiction_reason,
        "missing_evidence": missing_evidence,
        "evidence_strength": evidence_strength,
    }


# ── Structured Rule Evaluator ─────────────────────────────────────────────────

def evaluate_psif_rules(evidence: Dict[str, Any]) -> Tuple[str, str, Optional[PSIFRuleDefinition], List[EvidenceStrengthMatrixRow]]:
    """
    Evaluates the authoritative safety rules catalog against extracted multi-source evidence.

    Returns:
        (internal_state, user_decision, matched_rule, evidence_matrix)
    """
    hazard: ExtractedHazard = evidence["hazard"]
    exposure: ExtractedExposure = evidence["exposure"]
    control: ExtractedControl = evidence["control"]
    consequence: ExtractedConsequence = evidence["consequence"]
    missing: List[MissingEvidenceItem] = evidence["missing_evidence"]
    is_sparse: bool = evidence["is_sparse"]
    is_conflicting: bool = evidence.get("is_conflicting_evidence", False)

    # Construct Evidence Strength Matrix Rows
    matrix: List[EvidenceStrengthMatrixRow] = [
        EvidenceStrengthMatrixRow(
            dimension="High-energy hazard",
            result="Supported" if hazard.energy_present else "Not Established",
            evidence=hazard.evidence_text or f"Hazard type: {hazard.hazard_type}",
            field_or_source=hazard.source_field,
        ),
        EvidenceStrengthMatrixRow(
            dimension="Worker exposure",
            result=exposure.state.replace("_", " ").title(),
            evidence=exposure.evidence_text or f"Exposure state: {exposure.state}",
            field_or_source=exposure.source_field,
        ),
        EvidenceStrengthMatrixRow(
            dimension="Critical control",
            result=control.control_type or "Identified from context",
            evidence=control.evidence_text or f"Control state: {control.state}",
            field_or_source=control.source_field,
        ),
        EvidenceStrengthMatrixRow(
            dimension="Control state",
            result=control.state.replace("_", " ").title(),
            evidence="Compromised / Ineffective" if control.is_compromised else ("Effective / Held" if control.state == ControlState.EFFECTIVE else "Uncertain"),
            field_or_source=control.source_field,
        ),
        EvidenceStrengthMatrixRow(
            dimension="SIF pathway",
            result=consequence.pathway_state.replace("_", " ").title(),
            evidence=consequence.mechanism or "Pathway evaluated against EEI SCL criteria",
            field_or_source="rule_engine",
        ),
        EvidenceStrengthMatrixRow(
            dimension="Evidence sufficiency",
            result=evidence["evidence_strength"].title(),
            evidence=f"{len(missing)} missing items identified" if missing else "Sufficient multi-source corroboration",
            field_or_source="evidence_extractor",
        ),
    ]

    # 0. Check for Contradictory Evidence
    if is_conflicting:
        return (
            InternalReasoningState.CONFLICTING_EVIDENCE,
            UserFacingDecision.INSUFFICIENT_INFORMATION,
            None,
            matrix,
        )

    # 1. Check for Insufficient Information / Sparse Reporting
    has_explicit_facts = bool(
        hazard.energy_present
        and control.state in [ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.EFFECTIVE, ControlState.RESTORED_BEFORE_EXPOSURE]
        and exposure.state in [
            ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH, ExposureState.INSIDE_EXCLUSION_ZONE,
            ExposureState.NO_WORKER_EXPOSURE, ExposureState.NEARBY_BUT_PROTECTED, ExposureState.EXPOSURE_INTERRUPTED
        ]
    )

    if (is_sparse and not has_explicit_facts) or (hazard.energy_present and (exposure.state == ExposureState.UNKNOWN or (control.state == ControlState.UNKNOWN and len(missing) >= 2))):
        return (
            InternalReasoningState.INSUFFICIENT_INFORMATION,
            UserFacingDecision.INSUFFICIENT_INFORMATION,
            None,
            matrix,
        )

    # 2. Check for Low Energy Hazard
    if not hazard.energy_present or hazard.hazard_type == EnergyHazardType.LOW_ENERGY_GENERAL:
        rule = get_rule_by_id("PSIF-R-10")
        return (
            InternalReasoningState.LOW_ENERGY,
            UserFacingDecision.NOT_PSIF,
            rule,
            matrix,
        )

    # 3. Check for Interrupted / Controlled Pathway (EEI Capacity / High Energy Controlled)
    # Cases: Hazard aborted before exposure, control held effectively, or worker safely positioned
    if exposure.state in [ExposureState.NO_WORKER_EXPOSURE, ExposureState.NEARBY_BUT_PROTECTED, ExposureState.EXPOSURE_INTERRUPTED] or control.state in [ControlState.EFFECTIVE, ControlState.RESTORED_BEFORE_EXPOSURE]:
        if exposure.state == ExposureState.EXPOSURE_INTERRUPTED or control.state == ControlState.RESTORED_BEFORE_EXPOSURE:
            rule = get_rule_by_id("PSIF-R-09") or get_rule_by_id("PSIF-R-08")
        else:
            rule = get_rule_by_id("PSIF-R-08")
        return (
            InternalReasoningState.HIGH_ENERGY_CONTROLLED,
            UserFacingDecision.NOT_PSIF,
            rule,
            matrix,
        )

    # 4. Check for Open SIF Pathway (PSIF Precursor)
    # High energy present + worker exposed (direct/line-of-fire/zone) + control compromised
    if control.is_compromised and exposure.state in [ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH, ExposureState.INSIDE_EXCLUSION_ZONE]:
        # Match specific hazard rule
        matched_rule = None
        for r in PSIF_RULES_CATALOG:
            if hazard.hazard_type in r.applicable_hazards and r.decision_effect == InternalReasoningState.PSIF_PATHWAY_OPEN:
                matched_rule = r
                break
        if not matched_rule:
            matched_rule = get_rule_by_id("PSIF-R-02") or PSIF_RULES_CATALOG[0]
            
        return (
            InternalReasoningState.PSIF_PATHWAY_OPEN,
            UserFacingDecision.PSIF,
            matched_rule,
            matrix,
        )

    # Fallback: if evidence is incomplete or ambiguous, output INSUFFICIENT_INFORMATION
    return (
        InternalReasoningState.INSUFFICIENT_INFORMATION,
        UserFacingDecision.INSUFFICIENT_INFORMATION,
        None,
        matrix,
    )


# ── ML + Rule Reconciliation & Decision Policy Layer ──────────────────────────

class AgreementState:
    MODEL_AND_RULE_AGREE = "MODEL_AND_RULE_AGREE"
    MODEL_STRONGER_THAN_RULE_EVIDENCE = "MODEL_STRONGER_THAN_RULE_EVIDENCE"
    RULE_EVIDENCE_STRONGER_THAN_MODEL = "RULE_EVIDENCE_STRONGER_THAN_MODEL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DATA_QUALITY_BLOCKED = "DATA_QUALITY_BLOCKED"


@dataclass
class ReconciliationResult:
    model_prediction: Optional[str]        # "PSIF" / "NOT_PSIF"
    model_score: Optional[float]           # Float 0.0 - 1.0 (PSIF Model Score)
    rule_assessment: str                   # UserFacingDecision ("PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION")
    internal_reasoning_state: str          # InternalReasoningState
    evidence_strength: str                 # "STRONG", "MODERATE", "WEAK"
    agreement_state: str                   # AgreementState
    disagreement_reason: Optional[str] = None
    disagreement_type: Optional[str] = None # "POTENTIAL_FALSE_NEGATIVE" / "POTENTIAL_FALSE_POSITIVE" / None
    high_priority_review: bool = False
    policy_final_decision: str = UserFacingDecision.INSUFFICIENT_INFORMATION
    policy_rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def reconcile_model_and_rules(
    prediction: Optional[PredictionResult],
    rule_decision: str,
    internal_state: str,
    evidence_strength: str,
    dq_record: Optional[IncidentDataQuality] = None,
) -> ReconciliationResult:
    """
    Explicit Decision Policy Layer:
    Reconciles the statistical machine learning model prediction with the domain rule assessment.
    Identifies high-priority human review cases without silent blind overrides.
    Labels disagreements as POTENTIAL_FALSE_NEGATIVE or POTENTIAL_FALSE_POSITIVE.
    """
    # 1. Data Quality Gate Check
    if dq_record and dq_record.status == IncidentDataQuality.Status.CRITICAL:
        return ReconciliationResult(
            model_prediction=prediction.binary_classification if prediction else None,
            model_score=round(prediction.psif_score, 4) if prediction else None,
            rule_assessment=rule_decision,
            internal_reasoning_state=internal_state,
            evidence_strength=evidence_strength,
            agreement_state=AgreementState.DATA_QUALITY_BLOCKED,
            disagreement_reason="Critical data quality gate failure blocks reliable automated determination.",
            disagreement_type=None,
            high_priority_review=True,
            policy_final_decision=UserFacingDecision.INSUFFICIENT_INFORMATION,
            policy_rationale="Analytical suitability gate blocked due to critical data quality issues.",
        )

    # 2. Insufficient / Conflicting Evidence Check
    if rule_decision == UserFacingDecision.INSUFFICIENT_INFORMATION:
        is_conflict = internal_state == InternalReasoningState.CONFLICTING_EVIDENCE
        reason = (
            "Narrative contains mutually contradictory safety statements that require investigator clarification."
            if is_conflict else
            "Essential facts regarding exposure or barrier condition are missing from the report."
        )
        return ReconciliationResult(
            model_prediction=prediction.binary_classification if prediction else None,
            model_score=round(prediction.psif_score, 4) if prediction else None,
            rule_assessment=rule_decision,
            internal_reasoning_state=internal_state,
            evidence_strength=evidence_strength,
            agreement_state=AgreementState.INSUFFICIENT_EVIDENCE,
            disagreement_reason=reason,
            disagreement_type=None,
            high_priority_review=True,
            policy_final_decision=UserFacingDecision.INSUFFICIENT_INFORMATION,
            policy_rationale="Report lacks necessary corroborating evidence to establish or refute the SIF precursor pathway.",
        )

    if not prediction:
        return ReconciliationResult(
            model_prediction=None,
            model_score=None,
            rule_assessment=rule_decision,
            internal_reasoning_state=internal_state,
            evidence_strength=evidence_strength,
            agreement_state=AgreementState.MODEL_AND_RULE_AGREE,
            disagreement_type=None,
            high_priority_review=False,
            policy_final_decision=rule_decision,
            policy_rationale="Evaluated purely via deterministic domain rules (statistical model result unavailable).",
        )

    model_pred = prediction.binary_classification
    model_decision = UserFacingDecision.PSIF if prediction.psif_predicted else UserFacingDecision.NOT_PSIF
    model_score = round(prediction.psif_score, 4)

    # 3. Model and Rule Agree
    if model_decision == rule_decision:
        return ReconciliationResult(
            model_prediction=model_pred,
            model_score=model_score,
            rule_assessment=rule_decision,
            internal_reasoning_state=internal_state,
            evidence_strength=evidence_strength,
            agreement_state=AgreementState.MODEL_AND_RULE_AGREE,
            disagreement_reason=None,
            disagreement_type=None,
            high_priority_review=False,
            policy_final_decision=rule_decision,
            policy_rationale=f"Both the statistical model (score {model_score}) and rule-grounded reasoning reach {rule_decision}.",
        )

    # 4. Disagreement: Rule says PSIF, Model says NOT_PSIF (POTENTIAL_FALSE_NEGATIVE)
    if rule_decision == UserFacingDecision.PSIF and model_decision == UserFacingDecision.NOT_PSIF:
        return ReconciliationResult(
            model_prediction=model_pred,
            model_score=model_score,
            rule_assessment=rule_decision,
            internal_reasoning_state=internal_state,
            evidence_strength=evidence_strength,
            agreement_state=AgreementState.RULE_EVIDENCE_STRONGER_THAN_MODEL,
            disagreement_reason=(
                f"Rule-grounded evidence establishes an open SIF pathway (high energy with control failure and worker exposed), "
                f"but the statistical model score ({model_score}) fell below the classification threshold. Potential false-negative."
            ),
            disagreement_type="POTENTIAL_FALSE_NEGATIVE",
            high_priority_review=True,
            policy_final_decision=UserFacingDecision.PSIF,
            policy_rationale="Safety-first principle: Verified high energy + worker exposure + control failure overrides lower statistical model score for review.",
        )

    # 5. Disagreement: Model says PSIF, Rule says NOT_PSIF (POTENTIAL_FALSE_POSITIVE)
    if rule_decision == UserFacingDecision.NOT_PSIF and model_decision == UserFacingDecision.PSIF:
        is_capacity = internal_state == InternalReasoningState.HIGH_ENERGY_CONTROLLED
        reason = (
            f"The statistical model assigned a high score ({model_score}) likely triggered by high-energy keywords, "
            f"but rule reasoning confirms the pathway was interrupted: {'direct controls functioned effectively (EEI Capacity)' if is_capacity else 'no worker exposure occurred'}."
        )
        return ReconciliationResult(
            model_prediction=model_pred,
            model_score=model_score,
            rule_assessment=rule_decision,
            internal_reasoning_state=internal_state,
            evidence_strength=evidence_strength,
            agreement_state=AgreementState.MODEL_STRONGER_THAN_RULE_EVIDENCE,
            disagreement_reason=reason,
            disagreement_type="POTENTIAL_FALSE_POSITIVE",
            high_priority_review=True,
            policy_final_decision=UserFacingDecision.NOT_PSIF,
            policy_rationale="Direct control held effectively (EEI Capacity) or worker was protected; high energy keywords alone do not constitute an open PSIF pathway.",
        )

    return ReconciliationResult(
        model_prediction=model_pred,
        model_score=model_score,
        rule_assessment=rule_decision,
        internal_reasoning_state=internal_state,
        evidence_strength=evidence_strength,
        agreement_state=AgreementState.INSUFFICIENT_EVIDENCE,
        disagreement_reason="Ambiguous state reconciliation.",
        disagreement_type=None,
        high_priority_review=True,
        policy_final_decision=UserFacingDecision.INSUFFICIENT_INFORMATION,
        policy_rationale="Review advised due to ambiguous alignment.",
    )


# ── Constrained Language Presentation Generator ───────────────────────────────

def generate_constrained_explanation(
    evidence: Dict[str, Any],
    internal_state: str,
    rule_decision: str,
    matched_rule: Optional[PSIFRuleDefinition],
    reconciliation: ReconciliationResult,
) -> Dict[str, Any]:
    """
    Generates constrained, non-hallucinatory explanations strictly grounded in
    structured evidence, the versioned knowledge base, and reconciliation state.
    Provides structured What is Known, What is Unknown, Why it Matters, and What Would Close Case.
    """
    hazard: ExtractedHazard = evidence["hazard"]
    exposure: ExtractedExposure = evidence["exposure"]
    control: ExtractedControl = evidence["control"]
    consequence: ExtractedConsequence = evidence["consequence"]
    missing: List[MissingEvidenceItem] = evidence["missing_evidence"]
    is_conflicting: bool = evidence.get("is_conflicting_evidence", False)
    conflict_desc: Optional[str] = evidence.get("contradiction_details")

    # 1. Structured What is Known
    what_is_known: List[Dict[str, str]] = []
    if hazard.energy_present:
        what_is_known.append({
            "dimension": "High-Energy Hazard",
            "fact": f"High energy present: {hazard.hazard_type.replace('_', ' ').title()}",
            "evidence": hazard.evidence_text or "Identified from operational context",
        })
    if exposure.state != ExposureState.UNKNOWN:
        what_is_known.append({
            "dimension": "Worker Proximity / Line of Fire",
            "fact": f"Worker positioning evaluated as {exposure.state.replace('_', ' ').title()}",
            "evidence": exposure.evidence_text or f"Exposure state: {exposure.state}",
        })
    if control.state != ControlState.UNKNOWN:
        what_is_known.append({
            "dimension": "Direct Control Condition",
            "fact": f"Control status evaluated as {control.state.replace('_', ' ').title()}",
            "evidence": control.evidence_text or f"Control: {control.control_type or 'Critical Barrier'}",
        })
    if consequence.pathway_state != ConsequencePathwayState.UNKNOWN:
        what_is_known.append({
            "dimension": "Consequence Pathway",
            "fact": f"SIF pathway: {consequence.pathway_state.replace('_', ' ').title()}",
            "evidence": consequence.mechanism or "Assessed against EEI SCL criteria",
        })

    # 2. Structured What is Unknown
    what_is_unknown: List[Dict[str, str]] = []
    if is_conflicting:
        what_is_unknown.append({
            "dimension": "Contradictory Safety Evidence",
            "missing_item": "Resolution of mutually contradictory statements in incident narrative",
            "why_it_matters": conflict_desc or "Conflicting claims prevent reliable classification.",
        })
    for m in missing:
        what_is_unknown.append({
            "dimension": m.decision_impact,
            "missing_item": m.question,
            "why_it_matters": m.why_it_matters,
        })

    # 3. Why Unknown Matters & What Information Would Close the Case
    if is_conflicting:
        why_unknown_matters = f"Contradictory evidence: {conflict_desc}"
        what_would_close_case = ["Conduct witness interviews to clarify conflicting statements", "Verify physical barrier inspection logs"]
    elif missing:
        why_unknown_matters = "; ".join([f"{item.question} ({item.why_it_matters})" for item in missing])
        what_would_close_case = [item.question for item in missing]
    else:
        why_unknown_matters = "Multi-source evidence is sufficient across hazard, exposure, and control dimensions."
        what_would_close_case = []

    # 4. HSE-Analyst 10-Point Structured Why PSIF Summary
    if rule_decision == UserFacingDecision.PSIF:
        rule_name = matched_rule.name if matched_rule else "High-Energy Hazard"
        source_cite = f" [{matched_rule.source_section}]" if matched_rule else ""
        why_psif = (
            f"The incident presents an open PSIF precursor pathway under rule '{rule_name}'{source_cite}. "
            f"High energy ({hazard.hazard_type}) was present, worker exposure was {exposure.state.replace('_', ' ').lower()}, "
            f"and critical barrier condition was evaluated as {control.state.replace('_', ' ').lower()}. "
            f"Consequence pathway to serious injury was physically supported with direct line-of-fire exposure."
        )
    else:
        why_psif = "Not classified as PSIF because the physical precursor pathway was interrupted, controlled, or lacking high energy."

    # 5. Grounded Why NOT PSIF Summary
    if rule_decision == UserFacingDecision.NOT_PSIF:
        if internal_state == InternalReasoningState.HIGH_ENERGY_CONTROLLED:
            if exposure.state in [ExposureState.NEARBY_BUT_PROTECTED, ExposureState.NO_WORKER_EXPOSURE]:
                interruption_reason = "personnel were physically protected behind engineered barriers or positioned outside the danger zone"
            elif control.state in [ControlState.EFFECTIVE, ControlState.RESTORED_BEFORE_EXPOSURE]:
                interruption_reason = f"an engineered direct control ({control.control_type or 'critical barrier'}) functioned effectively to absorb and contain the energy"
            elif exposure.state == ExposureState.EXPOSURE_INTERRUPTED:
                interruption_reason = "work was safely halted before personnel entered the line-of-fire"
            else:
                interruption_reason = "the consequence pathway was physically broken before serious injury could occur"

            why_not_psif = (
                f"High-energy hazard ({hazard.hazard_type}) was present, but {interruption_reason} "
                f"(EEI Capacity framework). Worker exposure was {exposure.state.replace('_', ' ').lower()}."
            )
        elif internal_state == InternalReasoningState.LOW_ENERGY:
            why_not_psif = (
                "The incident involved low energy density lacking physical capacity to cause permanent disabling or fatal injury."
            )
        else:
            why_not_psif = "Precursor pathway was interrupted prior to worker exposure."
    else:
        why_not_psif = "Not classified as NOT PSIF because evidence indicates an open high-energy release pathway with compromised controls."

    # 6. Which Rules Apply
    rules_applied = []
    if matched_rule:
        rules_applied.append(f"{matched_rule.rule_id}: {matched_rule.name} (Source: {matched_rule.source_section})")
    for r_code in evidence["matched_iogp_rules"]:
        rules_applied.append(f"IOGP Rule: {r_code} (Report 459 Start Work Checks)")
    if not rules_applied:
        rules_applied.append("General SIF Precursor Assessment (EEI SCL 2021)")

    # 7. Which Control Matters
    control_matters = (
        f"Primary Direct Control: {control.control_type or 'Engineered physical barrier'}. "
        f"Current status: {control.state.replace('_', ' ').title()}. "
        f"Critical requirement: Must provide physical containment or positive energy isolation independent of human error."
    )

    # 8. What Would Change Assessment
    if rule_decision == UserFacingDecision.PSIF:
        what_changes = (
            "Confirmation that an unmentioned engineered secondary barrier remained intact, or proof that "
            "personnel were completely outside the release trajectory (e.g. remotely operated)."
        )
    elif rule_decision == UserFacingDecision.NOT_PSIF:
        what_changes = (
            "Discovery that the direct control actually failed or was defeated, or evidence that workers were "
            "positioned in the line of fire without positive isolation."
        )
    else:
        what_changes = "Providing the missing facts or resolving the contradictory claims identified in the case closure checklist."

    return {
        "why_psif": why_psif,
        "why_not_psif": why_not_psif,
        "what_is_known": what_is_known,
        "what_is_unknown": what_is_unknown,
        "why_unknown_matters": why_unknown_matters,
        "what_information_would_close_case": what_would_close_case,
        "what_evidence_is_missing": why_unknown_matters,
        "what_is_missing": why_unknown_matters,
        "what_rules_apply": rules_applied,
        "what_control_matters": control_matters,
        "what_would_change_assessment": what_changes,
        "missing_evidence_checklist": [asdict(m) for m in missing],
    }


# ── Action Engine Trace Consumer (Full Action Traceability) ───────────────────

def select_grounded_actions(
    evidence: Dict[str, Any],
    internal_state: str,
    rule_decision: str,
    matched_rule: Optional[PSIFRuleDefinition],
) -> List[Dict[str, Any]]:
    """
    Deterministically selects safety actions strictly from the structured reasoning trace:
    (hazard, exposure, critical_control, control_state, consequence_pathway, iogp_rule, evidence_strength).
    Provides full action traceability: triggering evidence, control addressed, rule addressed, verification method.
    """
    hazard: ExtractedHazard = evidence["hazard"]
    control: ExtractedControl = evidence["control"]
    selected_actions = []

    # Case 1: High Energy Controlled -> POSITIVE CONTROL LEARNING
    if internal_state == InternalReasoningState.HIGH_ENERGY_CONTROLLED:
        return [{
            "action_id": "ACT-POS-01",
            "title": "Document & Share Effective Direct Control Learning",
            "action_type": ActionType.POSITIVE_LEARNING,
            "urgency": ActionUrgency.LOW,
            "triggering_evidence": f"High energy ({hazard.hazard_type}) present, but direct control ({control.control_type or 'engineered barrier'}) functioned effectively (EEI Capacity).",
            "control_addressed": control.control_type or "Engineered direct barrier",
            "rule_addressed": matched_rule.name if matched_rule else "EEI Capacity Framework",
            "description": (
                f"Maintain and document the effective performance of the critical control ({control.control_type or 'Engineered direct barrier'}) "
                f"which successfully prevented serious harm during exposure to high energy ({hazard.hazard_type}). Share as a positive safety learning."
            ),
            "verification_method": [
                "Record barrier performance data in the site barrier integrity register",
                "Recognize personnel who adhered to verification checks",
                "Share positive operational feedback during toolbox talks",
            ],
            "library_version": "action_library_v1",
        }]

    # Case 2: Insufficient Information / Conflicting Evidence
    if rule_decision == UserFacingDecision.INSUFFICIENT_INFORMATION:
        is_conflict = internal_state == InternalReasoningState.CONFLICTING_EVIDENCE
        return [{
            "action_id": "ACT-VERIF-01",
            "title": "Resolve Conflicting Evidence and Complete Investigation" if is_conflict else "Complete Incident Investigation to Gather Missing SIF Evidence",
            "action_type": ActionType.VERIFICATION,
            "urgency": ActionUrgency.HIGH,
            "triggering_evidence": evidence.get("contradiction_details") or "Essential evidence regarding isolation or worker positioning is missing.",
            "control_addressed": control.control_type or "Critical Control Verification",
            "rule_addressed": matched_rule.name if matched_rule else "Investigation Standard",
            "description": "Gather required evidence regarding isolation verification, worker positioning, and barrier integrity before case closure.",
            "verification_method": [
                "Conduct physical inspection of the equipment and energy isolation points",
                "Interview operating personnel regarding pre-job Start Work Checks",
                "Update incident report with conclusive barrier condition data",
            ],
            "library_version": "action_library_v1",
        }]

    # Case 3: PSIF Pathway Open -> Evidence-Grounded Corrective Actions
    hazard_key = hazard.hazard_type.lower()
    for tpl in ACTION_LIBRARY:
        # Check hazard match
        hazard_match = "any" in tpl.applicable_hazard or any(h.lower() in hazard_key for h in tpl.applicable_hazard)
        # Check failure state match
        state_match = "any" in tpl.control_failure_state or control.state.lower() in [s.lower() for s in tpl.control_failure_state]
        
        if hazard_match and state_match:
            d = tpl.to_dict()
            d["triggering_evidence"] = f"Control state evaluated as {control.state} with worker exposed to {hazard.hazard_type}."
            d["control_addressed"] = control.control_type or (tpl.applicable_control[0] if tpl.applicable_control else "Direct Control")
            d["rule_addressed"] = tpl.applicable_rule or (matched_rule.name if matched_rule else "IOGP Life-Saving Rule")
            d["verification_method"] = tpl.verification_steps
            selected_actions.append(d)
            if len(selected_actions) >= 4:
                break

    # If no library template matched directly, build deterministic core set
    if not selected_actions:
        selected_actions = [
            {
                "action_id": "ACT-IMM-01",
                "title": f"Stop Work and Secure {hazard.hazard_type.replace('_', ' ').title()} Hazard",
                "action_type": ActionType.IMMEDIATE,
                "urgency": ActionUrgency.CRITICAL,
                "triggering_evidence": f"Uncontrolled high-energy hazard ({hazard.hazard_type}) with compromised critical barrier.",
                "control_addressed": control.control_type or "Direct Isolation / Guarding",
                "rule_addressed": matched_rule.name if matched_rule else "Stop Work Authority",
                "description": f"Immediately halt affected operations until physical direct control over {hazard.hazard_type} is restored and verified.",
                "verification_method": ["Confirm equipment is shut down and locked out", "Erect physical exclusion barricades"],
                "library_version": "action_library_v1",
            },
            {
                "action_id": "ACT-CORR-01",
                "title": f"Restore and Inspect Critical Barrier ({control.control_type or 'Direct Control'})",
                "action_type": ActionType.CORRECTIVE,
                "urgency": ActionUrgency.HIGH,
                "triggering_evidence": f"Critical barrier condition evaluated as {control.state}.",
                "control_addressed": control.control_type or "Direct Control",
                "rule_addressed": matched_rule.name if matched_rule else "Critical Barrier Standard",
                "description": "Rectify the compromised control condition prior to authorizing restart of work.",
                "verification_method": ["Engineering sign-off on barrier integrity", "Perform Start Work Checks"],
                "library_version": "action_library_v1",
            }
        ]

    return selected_actions


# ── Master Orchestrator: Comprehensive Incident Reasoning Assessment ─────────

def build_incident_reasoning_assessment(
    incident: Incident,
    prediction: Optional[PredictionResult] = None,
    dq_record: Optional[IncidentDataQuality] = None,
) -> Dict[str, Any]:
    """
    Main entrypoint for Foresight's PSIF Domain Knowledge & Rule-Grounded Reasoning Engine.
    Executes the full authoritative reasoning pipeline and returns an auditable structured payload.
    Provides complete top-level schema for the Why PSIF / Why NOT PSIF frontend workspace.
    """
    # 1. Multi-source evidence extraction
    evidence = extract_incident_safety_evidence(incident, prediction, dq_record)

    # 2. Structured rule evaluation
    internal_state, rule_decision, matched_rule, matrix = evaluate_psif_rules(evidence)

    # 3. ML + Rule Reconciliation & Decision Policy
    reconciliation = reconcile_model_and_rules(
        prediction=prediction,
        rule_decision=rule_decision,
        internal_state=internal_state,
        evidence_strength=evidence["evidence_strength"],
        dq_record=dq_record,
    )

    # 4. Constrained language explanation
    explanation = generate_constrained_explanation(
        evidence=evidence,
        internal_state=internal_state,
        rule_decision=rule_decision,
        matched_rule=matched_rule,
        reconciliation=reconciliation,
    )

    # 5. Deterministic action selection from trace
    actions = select_grounded_actions(
        evidence=evidence,
        internal_state=internal_state,
        rule_decision=rule_decision,
        matched_rule=matched_rule,
    )

    # 6. Build step-by-step reasoning chain
    reasoning_chain = [
        {
            "step": "Hazard Identification",
            "finding": f"High energy ({evidence['hazard'].hazard_type}) present: {evidence['hazard'].energy_present}",
            "status": "Identified" if evidence['hazard'].energy_present else "Low Energy",
            "evidence": evidence['hazard'].evidence_text,
        },
        {
            "step": "Worker Exposure",
            "finding": f"Worker positioning: {evidence['exposure'].state.replace('_', ' ').title()}",
            "status": "Exposed" if evidence['exposure'].state in [ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH, ExposureState.INSIDE_EXCLUSION_ZONE] else ("Protected" if evidence['exposure'].state in [ExposureState.NEARBY_BUT_PROTECTED, ExposureState.NO_WORKER_EXPOSURE, ExposureState.EXPOSURE_INTERRUPTED] else "Unknown"),
            "evidence": evidence['exposure'].evidence_text,
        },
        {
            "step": "Critical Control State",
            "finding": f"Control status: {evidence['control'].state.replace('_', ' ').title()}",
            "status": "Compromised" if evidence['control'].is_compromised else ("Effective" if evidence['control'].state == ControlState.EFFECTIVE else "Unknown"),
            "evidence": evidence['control'].evidence_text,
        },
        {
            "step": "Barrier Interruption",
            "finding": "Pathway interrupted by engineered barrier / safe positioning" if internal_state == InternalReasoningState.HIGH_ENERGY_CONTROLLED else ("Pathway open" if internal_state == InternalReasoningState.PSIF_PATHWAY_OPEN else "Uncertain"),
            "status": "Interrupted" if internal_state == InternalReasoningState.HIGH_ENERGY_CONTROLLED else ("Open" if internal_state == InternalReasoningState.PSIF_PATHWAY_OPEN else "Not Established"),
            "evidence": evidence['consequence'].mechanism,
        },
        {
            "step": "Consequence Pathway",
            "finding": f"SIF Consequence potential: {evidence['consequence'].pathway_state.replace('_', ' ').title()}",
            "status": "Supported" if evidence['consequence'].credible_sif_potential else "Not Established",
            "evidence": evidence['consequence'].mechanism,
        },
        {
            "step": "Evidence Sufficiency",
            "finding": f"Evidence strength: {evidence['evidence_strength'].title()}",
            "status": evidence['evidence_strength'].title(),
            "evidence": f"{len(evidence['missing_evidence'])} missing items" if evidence['missing_evidence'] else "Sufficient corroboration",
        },
        {
            "step": "Rule Assessment",
            "finding": f"Rule decision: {rule_decision} (State: {internal_state})",
            "status": rule_decision,
            "evidence": matched_rule.name if matched_rule else "General SCL Rule",
        },
        {
            "step": "Model Reconciliation",
            "finding": f"Alignment: {reconciliation.agreement_state.replace('_', ' ').title()} -> Policy: {reconciliation.policy_final_decision}",
            "status": reconciliation.agreement_state,
            "evidence": reconciliation.policy_rationale,
        },
    ]

    # 7. Assemble auditable reasoning payload matching Section 11 API contract
    return {
        "incident_id": str(incident.id),
        "decision": reconciliation.policy_final_decision,
        "internal_reasoning_state": internal_state,
        "evidence_strength": evidence["evidence_strength"],
        "reasoning_chain": reasoning_chain,
        "evidence_matrix": [asdict(r) for r in matrix],
        "what_is_known": explanation["what_is_known"],
        "what_is_missing": explanation["what_is_missing"],
        "why_psif": explanation["why_psif"],
        "why_not_psif": explanation["why_not_psif"],
        "rules_applied": explanation["what_rules_apply"],
        "control": {
            "control_type": evidence["control"].control_type,
            "state": evidence["control"].state,
            "is_direct_control": evidence["control"].is_direct_control,
            "is_compromised": evidence["control"].is_compromised,
            "evidence_text": evidence["control"].evidence_text,
        },
        "consequence_pathway": {
            "pathway_state": evidence["consequence"].pathway_state,
            "mechanism": evidence["consequence"].mechanism,
            "credible_sif_potential": evidence["consequence"].credible_sif_potential,
        },
        "reconciliation": reconciliation.to_dict(),
        "high_priority_review": reconciliation.high_priority_review,
        "grounded_actions": actions,
        "multi_hazard": {
            "primary_hazard": evidence["hazard"].hazard_type,
            "secondary_hazards": [h for h in evidence.get("all_detected_hazards", []) if h != evidence["hazard"].hazard_type],
            "all_detected_hazards": evidence.get("all_detected_hazards", [evidence["hazard"].hazard_type]),
        },
        "knowledge_base_version": KNOWLEDGE_BASE_VERSION,
        "reasoning_ruleset_version": REASONING_RULESET_VERSION,
        "action_library_version": "action_library_v1",
        "source_provenance": [
            {
                "source_id": matched_rule.source,
                "source_section": matched_rule.source_section,
                "rule_id": matched_rule.rule_id,
                "rule_name": matched_rule.name,
            } if matched_rule else {
                "source_id": "EEI_SCL_2021",
                "source_section": "EEI SCL Model (2021) General SIF Framework",
                "rule_id": "GEN-01",
                "rule_name": "General Safety Classification and Learning",
            }
        ],
        # Backwards-compatible aliases for existing consumers
        "final_policy_decision": reconciliation.policy_final_decision,
        "rule_decision": rule_decision,
        "is_sparse_report": evidence["is_sparse"],
        "matched_rule": {
            "rule_id": matched_rule.rule_id,
            "name": matched_rule.name,
            "source": matched_rule.source,
            "source_section": matched_rule.source_section,
        } if matched_rule else None,
        "constrained_explanation": explanation,
        "evidence_summary": {
            "hazard_type": evidence["hazard"].hazard_type,
            "energy_present": evidence["hazard"].energy_present,
            "exposure_state": evidence["exposure"].state,
            "control_type": evidence["control"].control_type,
            "control_state": evidence["control"].state,
            "consequence_pathway": evidence["consequence"].pathway_state,
            "matched_iogp_rules": evidence["matched_iogp_rules"],
            "all_detected_hazards": evidence.get("all_detected_hazards", [evidence["hazard"].hazard_type]),
        },
    }
