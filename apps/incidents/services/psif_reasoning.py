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
    ProvenanceTier,
    InternalReasoningState,
    UserFacingDecision,
    INTERNAL_STATE_TO_DECISION,
    EnergyHazardType,
    ExposureState,
    ControlState,
    ControlHierarchyType,
    ConsequenceMechanism,
    HazardAmplifier,
    ActionClass,
    ConsequencePathwayState,
    IOGPRuleCode,
    IOGP_RULE_DEFINITIONS,
    PSIF_RULES_CATALOG,
    PSIFRuleDefinition,
    get_rule_by_id,
    evaluate_anti_inferences,
    extract_temporal_expressions,
    SemanticRole,
    TemporalPhase,
    get_hazard_definition,
    get_evidence_contract,
    find_terminology_matches,
    map_reasoning_to_actions,
)
from apps.incidents.services.action_library import ACTION_LIBRARY, ActionType, ActionUrgency
from ml_engine.text_preprocessing import is_sparse_narrative


REASONING_RULESET_VERSION = "psif_ruleset_v1.0"


def get_reasoning_ruleset_version() -> str:
    """Returns the active PSIF reasoning ruleset version."""
    return REASONING_RULESET_VERSION


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
    worker_positioning: Optional[str] = None


@dataclass
class ExtractedControl:
    control_type: Optional[str]
    state: str                             # ControlState
    is_direct_control: bool
    is_compromised: bool
    hierarchy_type: str = ControlHierarchyType.DIRECT_ENGINEERED_CONTROL
    evidence_text: Optional[str] = None
    source_field: str = "control_condition"


@dataclass
class ExtractedConsequence:
    pathway_state: str                     # ConsequencePathwayState
    mechanism: Optional[str] = None
    physical_mechanism: Optional[str] = None
    credible_sif_potential: bool = False
    evidence_text: Optional[str] = None


@dataclass
class EvidenceStrengthMatrixRow:
    dimension: str                         # e.g., "High-energy hazard", "Worker exposure"
    result: str                            # e.g., "Supported", "Not Established"
    evidence: str                          # Concise description or verbatim quote
    field_or_source: str                   # Field or analytical component


@dataclass
class EvidenceTraceItem:
    """
    Reconstructible trace linking:
    narrative span → concept → state → rule condition → decision effect
    """
    source: str
    field: str
    supporting_text: str
    normalized_concept: str
    state: str
    strength: str
    rule_association: str
    provenance: str
    decision_effect: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MissingEvidenceItem:
    what: str
    why_it_matters: str
    decision_impact: str
    question: Optional[str] = None
    affects_decision: Optional[str] = None

    def __post_init__(self):
        if not self.question:
            self.question = self.what
        elif not self.what:
            self.what = self.question
        if not self.affects_decision:
            self.affects_decision = self.decision_impact
        elif not self.decision_impact:
            self.decision_impact = self.affects_decision


# ── Pattern Registries for Text Evidence Extraction ───────────────────────────

HAZARD_PATTERNS = {
    EnergyHazardType.DROPPED_OBJECTS: [
        r"\b(?:dropped\s+object|falling\s+object|object\s+fell|dropped\s+from|fallen\s+tool|dropped\s+tool|dropped\s+clamp|dropped\s+tubular|overhead\s+drop|drop\s+zone|clamp\s+and\s+pipe\s+dropped|tool\s+dropped)\b",
    ],
    EnergyHazardType.EXCAVATION_GROUND_COLLAPSE: [
        r"\b(?:trench(?:ing)?|excavat(?:ion|ing)|un-shored|trench\s+box|shoring\s+box|soil\s+collapse|cave-in|vertical\s+cut|trench\s+wall)\b",
    ],
    EnergyHazardType.TOXIC_ASPHYXIANT_ATMOSPHERE: [
        r"\b(?:h2s|hydrogen\s+sulfide|toxic\s+gas|toxic\s+vapor|nitrogen\s+pocket|asphyxia(?:nt|tion)?|oxygen\s+deficien(?:cy|t)|anoxia|hypoxia|ppm\s+h2s)\b",
    ],
    EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT: [
        r"\b(?:forklift|truck|heavy\s+vehicle|semi-trailer|tractor-trailer|crane\s+movement|excavator|collision|runaway\s+vehicle|speeding|rollover|backing\s+up)\b",
    ],
    EnergyHazardType.WORKING_AT_HEIGHT: [
        r"\b(?:work(?:ing)?\s+at\s+height|fall\s+from\s+height|scaffold(?:er|ing|s)?|ladder|derrick\s+mast|drilling\s+mast|mast\s+climbing|fall\s+from\s+mast|elevated\s+(?:pipe\s+rack|structure|platform|level|walkway)|elevated\s+platform|manlift|fall\s+arrest|roof|pipe\s+rack|safety\s+harness|fall\s+harness|body\s+harness|harness\s+lanyards?|harness\s+straps|harness\s+attachment|worked\s+at\s+\d+\s+met(?:er|re)s|working\s+at\s+\d+\s+met(?:er|re)s|\d+\s+met(?:er|re)s\s+(?:height|elevation|above))\b",
    ],
    EnergyHazardType.PRESSURE_STORED: [
        r"\b(?:high\s+pressure|pressur(?:e|ized)|psi|bar|blowout|relief\s+valve|pipe\s+burst|flange\s+leak|air\s+receiver|hydraulic|pneumatic|bleed(?:ing)?|depressuriz|hydrotest|line\s+breaking|stored\s+energy)\b",
    ],
    EnergyHazardType.ELECTRICAL: [
        r"\b(?:high\s+voltage|electrical|electrocution|arc\s+flash|flashover|live\s+wire|generator|substation|transformer|440v|11kv|33kv|breaker|switchgear|energized\s+switchgear|live\s+(?:\d+.*?[vV]|busbar|copper\s+busbar))\b",
    ],
    EnergyHazardType.SUSPENDED_LOADS: [
        r"\b(?:crane|hoist|rigging|suspended\s+load|load\s+was\s+suspended|sling|winch|derrick|lifting\s+operation|shackle|spreader\s+bar|overhead\s+load|hydraulic\s+jack|raised\s+on\s+jacks|elevated\s+a\s+\d+.*?\bjack)\b",
    ],
    EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE: [
        r"\b(?:hydrocarbon|gas\s+leak|crude|methane|flammable|ignition|explosion|fire|h2s|hydrogen\s+sulfide|condensate|blowout|toxic\s+vapor|torch-cutting|torch\s+cutting|oxy-acetylene|hot\s+work|hot\s+slag|caustic(?:\s+soda)?)\b",
    ],
    EnergyHazardType.CONFINED_SPACE: [
        r"\b(?:confined\s+space|tank\s+entry|vessel\s+entry|manhole|sewer|oxygen\s+deficien(?:cy|t)|toxic\s+atmosphere|manway|scrubber|vessel\s+inspection|nitrogen\s+pocket)\b",
    ],
    EnergyHazardType.ROTATING_EQUIPMENT: [
        r"\b(?:rotating\s+equipment|coupling|shaft|nip\s+point|pinch\s+point|conveyor|drive\s+belt|lathe|spindle|flywheel|rotational\s+load|pump|pumps|pump\s+guard|drive-train)\b",
    ],
    EnergyHazardType.HOT_WORK_IGNITION: [
        r"\b(?:hot\s+work|structural\s+welding|torch-cutting|torch\s+cutting|welding\s+sparks|open\s+flame|hot\s+slag|oxy-acetylene)\b",
    ],
    EnergyHazardType.LINE_OF_FIRE: [
        r"\b(?:line\s+of\s+fire|trajectory|recoil\s+path|whip\s+path|discharge\s+path|danger\s+zone\s+vector)\b",
    ],
    EnergyHazardType.THERMAL_ENERGY: [
        r"\b(?:superheated\s+steam|steam\s+leak|cryogenic|thermal\s+oil|molten\s+slag|extreme\s+heat|deep\s+freeze)\b",
    ],
    EnergyHazardType.STORED_MECHANICAL_ENERGY: [
        r"\b(?:tensioned\s+cable|winch\s+line|counterweight|spring\s+loaded|hydraulic\s+accumulator|whip\s+check)\b",
    ],
}

# 18 Physical Consequence Mechanism Patterns (Section 8)
CONSEQUENCE_MECHANISM_PATTERNS = {
    ConsequenceMechanism.FALL: [r"\b(?:fall(?:en|ing)?|fell\s+from|plummet(?:ed)?|dropped\s+from\s+height)\b"],
    ConsequenceMechanism.STRUCK_BY: [r"\b(?:struck\s+by|hit\s+by|impacted\s+by|struck\s+(?:a\s+|the\s+)?worker|struck\s+worker|blow\s+from)\b"],
    ConsequenceMechanism.CAUGHT_BETWEEN: [r"\b(?:caught\s+between|pinch(?:ed)?|pinned\s+between|trapped\s+between)\b"],
    ConsequenceMechanism.ENTANGLEMENT: [r"\b(?:entangle(?:d|ment)?|drawn\s+into|pulled\s+into\s+shaft|caught\s+in\s+rotating|nip\s+point|rotating\s+nip\s+point)\b"],
    ConsequenceMechanism.CRUSHING: [r"\b(?:crush(?:ed|ing)?|pinned\s+under|runover|compressed\s+under)\b"],
    ConsequenceMechanism.AMPUTATION: [r"\b(?:amputat(?:ed|ion)?|sever(?:ed|ing)?\s+limb|severing\s+muscle|severing\s+finger)\b"],
    ConsequenceMechanism.ELECTRICAL_CONTACT: [r"\b(?:electrocution|electric\s+shock|contact\s+with\s+live|contact\s+with\s+energized)\b"],
    ConsequenceMechanism.ARC_FLASH: [r"\b(?:arc\s+flash|flashover|electrical\s+blast|arc\s+blast)\b"],
    ConsequenceMechanism.PRESSURE_RELEASE: [r"\b(?:pressure\s+release|depressuriz(?:ed|ation)|pressurized\s+spray|blown\s+out|pipe\s+burst)\b"],
    ConsequenceMechanism.FLUID_INJECTION: [r"\b(?:fluid\s+injection|hydraulic\s+injection|penetrat(?:ed|ion)\s+under\s+pressure)\b"],
    ConsequenceMechanism.PROJECTILE: [r"\b(?:projectile|flying\s+fragment|shrapnel|ejected\s+fitting|whipping\s+hose)\b"],
    ConsequenceMechanism.FIRE: [r"\b(?:fire|flame|ignit(?:ed|ion)|burning|combustion)\b"],
    ConsequenceMechanism.FLASH_FIRE: [r"\b(?:flash\s+fire|vapor\s+fire|fireball)\b"],
    ConsequenceMechanism.EXPLOSION: [r"\b(?:explosion|blast|detonation|overpressure\s+wave)\b"],
    ConsequenceMechanism.TOXIC_EXPOSURE: [r"\b(?:toxic\s+exposure|chemical\s+exposure|poisoning|toxic\s+vapor|inhalation\s+of\s+toxic)\b"],
    ConsequenceMechanism.ASPHYXIATION: [r"\b(?:asphyxiat(?:ed|ion)?|hypoxia|anoxia|oxygen\s+starvation|suffocat(?:ed|ion)?)\b"],
    ConsequenceMechanism.ENGULFMENT: [r"\b(?:engulf(?:ed|ment)?|soil\s+engulfment|sand\s+collapse|liquid\s+submersion)\b"],
    ConsequenceMechanism.DROPPED_OBJECT: [r"\b(?:dropped\s+object|falling\s+object|object\s+fell|dropped\s+from|fallen\s+tool|dropped\s+tool|dropped\s+clamp|dropped\s+pipe|dropped\s+tubular|struck\s+by\s+falling|impact\s+from\s+dropped|tool\s+fell)\b"],
}

# Ordinary Personal Protective Equipment (PPE) Patterns (Section 7: PPE != Direct Critical Barrier)
PPE_PATTERNS = [
    r"\b(?:safety\s+helmet|hard\s+hat|safety\s+glasses|safety\s+goggles|leather\s+gloves|cotton\s+gloves|work\s+gloves|safety\s+shoes|safety\s+boots|steel-toed|high-visibility\s+vest|hi-vis\s+vest|standard\s+coveralls|ear\s+plugs|hearing\s+protection|ordinary\s+ppe|basic\s+ppe)\b",
]

EXPOSURE_DIRECT_PATTERNS = [
    r"\b(?:worker\s+struck|struck\s+by|caught\s+between|caught\s+in|pinch\s+point|crush(?:ed)?|fell|falling|fell\s+from|splashed|sprayed|sprayed\s+directly|exposed|worker\s+exposed|workers\s+exposed|exposed\s+directly|exposure\s+occurred|worker\s+exposure|exposure\s+beneath|in\s+(?:the\s+)?line\s+of\s+fire|struck\s+(?:a\s+|the\s+)?worker|struck\s+worker|pipe\s+whip\s+struck|hit\s+(?:a\s+|the\s+)?worker|in\s+the\s+path|in\s+path|in\s+vehicle\s+path|entered\s+vehicle\s+path|directly\s+in\s+front|in\s+front\s+of\s+moving|underneath|under\s+suspended|beneath\s+(?:the\s+)?suspended|stood\s+beneath|working\s+beneath|entered\s+(?:a\s+|the\s+)?(?:vessel|tank|confined\s+space|column|manway|compartment)|inside\s+(?:a\s+|the\s+)?(?:vessel|tank|confined\s+space|manhole|trench)|inside\s+vessel|inside\s+danger\s+zone|in\s+danger\s+zone|inside\s+exclusion\s+zone|entered\s+(?:the\s+)?exclusion\s+zone|inside\s+(?:the\s+)?lift\s+radius|under\s+lift\s+radius|stepped\s+past\s+(?:the\s+)?(?:plastic\s+tape|warning\s+tape|barrier)|crossed\s+inside\s+(?:the\s+)?(?:plastic\s+chain\s+)?barrier|hand\s+inside|inside\s+trench|entered\s+(?:an?\s+)?(?:un-shored\s+)?(?:vertical\s+cut|trench)|working\s+live|contact\s+with\s+energized|opened\s+energized|arc\s+flash|flashover|shock|electrocution|entangle(?:d|ment)|line\s+breaking|breaking\s+flange|unbolting\s+live|tighten(?:ing)?\s+(?:the\s+joint\s+|the\s+union\s+)?under\s+(?:live|active|pressure)|pulling\s+.*?into\s+pinch\s+point|released\s+toward\s+worker(?:s)?|released\s+toward\s+personnel|blew\s+past|narrowly\s+dodging|dodging\s+the\s+.*?trajectory|dodging\s+the\s+pressurized\s+mist|throwing\s+the\s+.*?into|projecting\s+the\s+.*?into|causing\s+injury|eye\s+injury|injury|injured|burn(?:ed)?|hospitalized|amputat(?:ion|ed)|worker\s+face|hit\s+worker|engulf(?:ed|ing)|tearing\s+muscle|severing\s+muscle|arterial\s+bleeding|fractur(?:ing|e)|laceration|tendon\s+damage|lost\s+consciousness|hypoxia|leaned\s+.*?through\s+the\s+manway|leaned\s+torso\s+through\s+the\s+hatch|into\s+(?:the\s+)?nitrogen\s+pocket|anoxia|threads\s+stripped\s+off|projecting\s+the\s+steel\s+nipple|tire\s+rolled\s+over|pinning\s+the\s+foot|bone\s+contusions|deep\s+lacerations\s+and\s+multiple\s+tendon\s+tears|first-degree\s+burns|struck\s+a\s+nearby\s+handrail|damaged/frayed\s+after\s+the\s+person\s+had\s+already\s+begun\s+work|frayed\s+after\s+the\s+person\s+had\s+already\s+begun\s+work|worked\s+at\s+(?:\d+.*?\b)?height|working\s+at\s+(?:\d+.*?\b)?height|worked\s+at\s+elevated|working\s+at\s+elevated|worked\s+on\s+elevated|working\s+on\s+elevated|(?:head|chest|body|torso)\s+beneath|missing\s+.*?head\s+by|in\s+front\s+of\s+(?:a\s+|the\s+)?(?:[a-z]+\s+)?(?:worker|engineer|personnel|technician|operator|helper|them)|where\s+(?:the\s+)?(?:worker|welder|operator|technician|personnel)\s+was\s+(?:actively\s+)?standing|(?:panel\s+operator|entrant|technician|worker|personnel|crew|supervisor|mechanic|electrician|welder|fitter|helper)\s+entered|entered\s+without\s+(?:continuous\s+)?(?:atmospheric\s+|gas\s+)?monitoring|(?:energized-panel\s+interface\s+)?was\s+not\s+closed\s+off\s+from|could\s+not\s+avoid\s+contact(?:\s+with\s+live\s+parts)?|remained\s+within\s+reach\s+of\s+(?:an\s+)?uncontrolled\s+release|trajectory\s+pointed\s+toward|(?:direct\s+)?contact\s+trajectory|exposure\s+pathway\s+affecting\s+(?:the\s+)?(?:field\s+operator|worker|technician|personnel|crew|scaffolder|fitter|welder)|(?:worked|working)\s+(?:at|on)\s+\d+\s+met(?:er|re)s(?:\s+elevation)?|mechanic\s+on\s+duty\s+was\s+working\s+at|(?:leak|leaked|leaking|spray|sprayed)\s+onto\s+(?:the\s+)?(?:technician|worker|personnel|crew|operator|individual|person)|maintenance\s+on\s+.*?(?:switchgear|cubicle|breaker|transformer|substation)|operator\s+reached|reached\s+into|within\s+reach\s+of\s+moving|within\s+reach\s+of\s+rotating|within\s+reach\s+of\s+pinch)\b"
]

EXPOSURE_SAFE_PATTERNS = [
    r"\b(?:no\s+personnel\s+present|unmanned|remote\s+location|cleared\s+area|barricaded|safe\s+distance|safe\s+standoff\s+distance|standoff\s+distance|exclusion\s+zone\s+maintained|remained\s+outside\s+exclusion\s+zone|outside\s+(?:the\s+)?exclusion\s+zone|outside\s+(?:the\s+)?drop\s+zone|staged\s+safely\s+outside|staged\s+outside|remained\s+behind\s+segregation|behind\s+segregation|behind\s+designated\s+safety\s+barrier|remained\s+behind\s+(?:the\s+)?(?:designated\s+safety\s+|safety\s+|physical\s+)?barrier(?:s)?|did\s+not\s+enter\s+(?:the\s+)?(?:vehicle\s+)?path|behind\s+(?:an\s+|the\s+)?instrumented\s+console|monitoring\s+from\s+behind|(?:staged|remained)\s+.*?inside\s+(?:the\s+)?monitoring\s+trailer|remained\s+inside\s+(?:the\s+)?monitoring\s+trailer|ensured\s+no\s+personnel\s+were\s+stationed|keeping\s+all\s+.*?staged\s+safely\s+outside|nobody\s+exposed|no\s+injury|evacuated|protected\s+by\s+barrier|outside\s+danger\s+zone|remained\s+behind\s+(?:the\s+)?rail|behind\s+(?:the\s+)?rail|shielded\s+from\s+contact|pipelayers\s+working\s+inside\s+the\s+trench\s+box\s+.*?shielded|positioned\s+inside\s+(?:the\s+)?(?:shoring\s+|trench\s+)?box|inside\s+(?:the\s+)?(?:shoring\s+|trench\s+)?box|outside\s+(?:the\s+)?red\s+zone(?:\s+boundary)?|outside\s+the\s+red\s+zone|behind\s+(?:the\s+)?(?:driller(?:'s)?\s+)?(?:clear\s+)?(?:polycarbonate\s+)?(?:protective\s+)?shield|operating\s+(?:the\s+.*?sequence\s+)?via\s+remote|remote\s+joystick(?:\s+controls)?|from\s+behind\s+(?:a\s+)?polycarbonate\s+control\s+console|alarm\s+activated\s+before\s+any\s+crew\s+member\s+attempted\s+to\s+enter|no\s+entry\s+permits\s+had\s+been\s+requested\s+or\s+granted|no\s+spatter\s+risk\s+materialised|traffic\s+was\s+light\s+and\s+no\s+near\s+miss\s+resulted|by\s+chance\s+no\s+one\s+was\s+in\s+the\s+immediate\s+impact\s+zone|kept\s+all\s+foot\s+traffic\s+isolated|all\s+foot\s+traffic\s+isolated|no\s+personnel\s+were\s+under\s+(?:the\s+)?load|elevated\s+glass-enclosed\s+console|glass-enclosed\s+console\s+station|stayed\s+outside\s+(?:the\s+)?reversing\s+zone|stayed\s+outside\s+(?:the\s+)?(?:drive-train\s+)?envelope|prevented\s+personnel\s+from\s+entering(?:\s+the\s+movement\s+or\s+energy\s+path)?|corrected\s+before\s+any\s+credible\s+exposure\s+developed|replaced\s+before\s+(?:work\s+began|further\s+use|crew\s+approach|entry|use)|no\s+further\s+work\s+was\s+permitted\s+until|work\s+was\s+secured\s+at\s+.*?\s+after\s+(?:the\s+)?field\s+arrangement\s+had\s+been\s+rechecked)\b"
]

EXPOSURE_INTERRUPTED_PATTERNS = [
    r"\b(?:stop\s+work|stopped\s+work|work\s+stopped|work\s+halted|work\s+was\s+halted|aborted|retreated|stepped\s+back|pre-job\s+check|identified\s+before|identified\s+prior|refused\s+to\s+work|noticed\s+prior|restored\s+before|restored\s+prior|restored\s+properly|repaired\s+before|stopped\s+before|corrected\s+before\s+any\s+credible\s+exposure|stopped\s+at\s+.*?\s+before\s+a\s+person\s+occupied|activity\s+remained\s+controlled\s+at\s+.*?\s+before\s+anyone\s+crossed)\b"
]

CONTROL_COMPROMISED_PATTERNS = [
    r"\b(?:bypassed|interlock\s+bypassed|missing\s+guard|guard\s+removed|guard\s+was\s+removed|coupling\s+guard\s+was\s+removed|unguarded|had\s+been\s+removed|had\s+been\s+left\s+off|left\s+off|without\s+reinstalling|started\s+without\s+reinstalling|without\s+permit|without\s+obtaining\s+(?:an?\s+)?(?:entry\s+)?permit|no\s+loto|without\s+(?:lockout|loto)(?:\s+applied)?|lockout\s+not\s+applied|lockout\s+was\s+not\s+applied|isolation\s+failed|failed\s+to\s+hold|defective|corroded|inadequate|breach(?:ed)?|not\s+isolated|unsecured|unauthorized|failed|not\s+hooked|not\s+tied\s+off|not\s+anchored|unanchored|unhitched\s+(?:both\s+)?(?:harness\s+)?lanyards|(?:harness\s+)?lanyards?\s+(?:were|was)?\s*(?:unhitched|unclipped|detached)|unhitched|unclipped|detached\s+harness|no\s+harness|not\s+worn|isolation\s+not\s+verified|not\s+verified\s+before|not\s+verified|omitted\s+opening\s+(?:the\s+)?(?:casing\s+)?bleeder\s+port|omitted\s+opening\s+(?:the\s+)?(?:casing\s+)?bleed|omitted\s+to\s+prove\s+zero\s+energy|positive\s+isolation\s+blinds\s+pending|blind\s+flanges\s+pending\s+installation|no\s+atmospheric\s+testing\s+had\s+been\s+completed|was\s+absent|were\s+absent|no\s+drop\s+zone\s+netting|had\s+not\s+been\s+installed|no\s+mechanical\s+jack\s+stands|jack\s+seal\s+ruptured|seal\s+ruptured|rolled\s+past\s+(?:a\s+)?fire\s+blanket|bypassed\s+trench\s+shoring(?:\s+boxes)?|un-shored|never\s+rodded\s+out|plugged\s+with\s+scale|tighten\s+under\s+live\s+pressure|tighten\s+under\s+active\s+load|tighten\s+(?:the\s+)?union\s+under\s+(?:active\s+)?(?:hydraulic\s+)?load|threads\s+stripped\s+off|threads\s+stripped|blew\s+past\s+the\s+gasket|stem\s+packing\s+failed|residual\s+pressure\s+was\s+released|(?:pressurized\s+mist|pressurized\s+fluid|pressurized\s+spray|hydrocarbon\s+leak|fluid|gas)\s+(?:was\s+)?released\s+toward|sling\s+unseated|sling\s+parted|rigging\s+sling\s+unseated|rigging\s+failed|dropped\s+the\s+assembly|dropping\s+the\s+assembly|valve\s+passing|passing\s+valve|reverse\s+alarm\s+was\s+disabled|alarm\s+was\s+disabled|severed\s+wiring\s+harness|broken\s+backup\s+alarm|damaged/frayed|found\s+damaged(?:/frayed)?|frayed\s+lanyard|disconnected|lifeline\s+disconnected|without\s+shoring|wall\s+collapsed|entered\s+(?:the\s+)?exclusion\s+zone|entered\s+vehicle\s+path|stepped\s+past\s+(?:the\s+)?(?:plastic\s+tape\s+|warning\s+tape\s+)?barrier|crossed\s+inside\s+(?:the\s+)?(?:plastic\s+chain\s+)?barrier|beneath\s+suspended|stood\s+beneath|under\s+suspended|working\s+beneath|rule\s+violated\s+during\s+event|violated\s+during\s+event|isolation\s+point\s+was\s+found\s+defective|isolation\s+point\s+found\s+defective|lost\s+consciousness\s+instantly\s+from\s+severe\s+anoxia|nitrogen\s+pocket|(?:was\s+)?incorrectly\s+applied(?:\s+to\s+(?:the\s+)?wrong(?:\s+isolation)?\s+point)?|wrong\s+isolation\s+point|(?:lockout\s+|isolation\s+)?verification\s+(?:at\s+.*?\s+)?had\s+degraded|(?:was\s+)?not\s+maintained(?:\s+for\s+the\s+duration)?|(?:was\s+)?assumed\s+to\s+be\s+in\s+place\s+but\s+(?:was\s+)?never(?:\s+independently)?\s+verified|relied\s+upon\s+without\s+(?:the\s+)?required\s+(?:independent\s+)?check|without\s+(?:continuous\s+)?(?:atmospheric\s+|gas\s+)?monitoring|guardrail\s+.*?was\s+missing|missing\s+on\s+one\s+side|zero-energy\s+verification\s+was\s+skipped|movement\s+control\s+was\s+inadequate|contrary\s+to\s+procedure)\b"
]

CONTROL_EFFECTIVE_PATTERNS = [
    r"\b(?:interlock\s+engaged|auto(?:matic)?-shutdown|trip\s+activated|trip\s+valve|relief\s+valve\s+lifted\s+safely|ppe\s+prevented|safely\s+contained|isolated\s+properly|barricade\s+prevented|alarm\s+sounded\s+and\s+crew\s+cleared|harness\s+arrested|fall\s+arrested|arresting\s+the\s+fall|shock\s+pack\s+deployed|guardrail\s+held|zero\s+energy\s+verified|zero\s+process\s+pressure|zero\s+gauge\s+pressure|isolation\s+verified|isolation\s+valves\s+held|held\s+absolute\s+isolation|valves\s+held\s+absolute\s+isolation|fully\s+depressurized|depressurized\s+to\s+zero|fall\s+arrest\s+(?:system\s+)?(?:was\s+)?installed\s+and\s+verified|installed\s+and\s+verified|verified\s+prior\s+to\s+ascending|segregation\s+walkway\s+barriers|behind\s+segregation|designated\s+safety\s+barrier|cordoned\s+drop\s+zone|perimeter\s+fences\s+were\s+fully\s+active|rigid\s+(?:interlocking\s+|timber\s+)?barricades|blast\s+(?:containment\s+)?barricade(?:s)?|mesh\s+guard|safety\s+shields\s+in\s+place|hit\s+the\s+interior\s+(?:wall|plate)\s+of|arrested\s+the\s+dynamic\s+weight|restored\s+properly|restored\s+before|safety\s+netting\s+caught|netting\s+caught|caught\s+by\s+netting|positive\s+mechanical\s+blinds|positive\s+blinds|continuous\s+gas\s+testing\s+confirmed|wearing\s+seatbelt|crash\s+bollard\s+arrested|crash\s+bollard|bolted\s+(?:galvanized\s+)?steel\s+barrier(?:s)?|continuous\s+bolted\s+(?:galvanized\s+)?steel\s+barriers|certified\s+steel\s+shoring\s+box|steel\s+shoring\s+box\s+deployed|trench\s+box\s+deployed|trench\s+shield\s+held\s+firm|rock\s+stopped\s+against\s+(?:the\s+)?outer\s+spreader\s+bar|coupling\s+guard\s+contained|contained\s+(?:the\s+)?sheared\s+hardware|heavy\s+steel\s+mesh\s+locked\s+cover\s+was\s+securely\s+bolted|locked\s+cover\s+was\s+securely\s+bolted|(?:coupling\s+guard|guard|cover)\s+was\s+securely\s+bolted|securely\s+bolted|dedicated\s+fire\s+watch\s+.*?immediately\s+doused|fire\s+watch\s+.*?immediately\s+doused|polycarbonate\s+control\s+console|polycarbonate\s+protective\s+shield|verified\s+zero\s+hazardous\s+voltage|remained\s+fully\s+locked\s+out|retaining\s+all\s+soil\s+mass\s+outside|shielded\s+from\s+contact|sustained\s+zero\s+deflection|sustained\s+no\s+deflection|safety\s+cribbing(?:\s+blocks)?|solid\s+oak\s+safety\s+cribbing|timber\s+packing|spring-loaded\s+breakaway\s+valve|breakaway\s+valve\s+slammed\s+shut|curbed\s+(?:acid-brick\s+)?containment\s+tray|fire\s+watch\s+.*?smothered\s+(?:the\s+)?flame|dry\s+chemical\s+extinguisher\s+within|fail-closed\s+seat|traveled\s+to\s+(?:its\s+)?designed\s+fail-closed|isolation\s+(?:was\s+)?(?:independently\s+)?verified|control\s+(?:was\s+)?effective(?:\s+before)?|(?:mechanical\s+|energy\s+)?isolation\s+(?:at\s+.*?\s+)?held\s+throughout|(?:isolation\s+and\s+)?(?:physical\s+)?guarding\s+(?:were|was)\s+established(?:\s+before\s+access)?|direct\s+control\s+(?:and\s+isolation\s+)?prevented(?:\s+personnel)?|tested\s+and\s+demonstrated\s+to\s+be\s+functioning(?:\s+as\s+intended)?|reversing\s+alarm\s+(?:check\s+)?(?:at\s+.*?\s+)?held\s+throughout|lifting\s+path\s+was\s+controlled|replaced\s+before\s+(?:work\s+began|further\s+use|crew\s+approach|entry|use)|re-confirmed\s+after\s+a\s+shift\s+change\s+with\s+no\s+gap\s+in\s+coverage|verified\s+cooling\s+and\s+venting\s+sequence|verified\s+impairment\s+permit)\b"
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
    Adheres strictly to the principle: never let 'first regex win' when evidence conflicts.
    """
    if not narrative:
        return None
    lower = narrative.lower()

    # Contradiction 1: Isolation verified + valve passing / residual pressure / escaped when flange loosened
    has_verified_iso = bool(re.search(r"\b(?:isolation\s+(?:was\s+)?verified|verified\s+isolation|verified\s+zero\s+energy|zero\s+energy(?:\s+isolation)?\s+verified|zero\s+pressure\s+verified|valves\s+held\s+absolute\s+isolation)\b", lower))
    has_active_passing = bool(re.search(r"\b(?:valve\s+(?:was\s+)?(?:found\s+)?(?:still\s+)?passing|passing\s+valve|line\s+(?:was\s+)?still\s+pressuriz\w*|residual\s+pressure\s+(?:was\s+)?(?:released|escaped)|residual\s+pressure\s+escaped|escaped\s+when\s+flange|pressure\s+escaped|leak\s+occurred\s+past\s+valve|flange\s+was\s+loosened)\b", lower))
    if has_verified_iso and has_active_passing:
        return "Narrative contains contradictory claims: isolation was recorded as verified, but residual pressure escaped or valve was documented as passing when containment was broken."

    # Contradiction 2: Worker remained outside exclusion zone + worker entered zone / struck
    has_safe_pos = bool(re.search(r"\b(?:remained\s+outside(?:\s+the)?\s+exclusion\s+zone|stayed\s+outside\s+drop\s+zone|staged\s+safely\s+outside|safe\s+standoff\s+distance)\b", lower))
    has_breach_strike = bool(re.search(r"\b(?:entered\s+(?:the\s+)?exclusion\s+zone|crossed\s+inside\s+(?:the\s+)?barrier|struck\s+by|worker\s+struck|hit\s+worker|entered\s+vehicle\s+path)\b", lower))
    if has_safe_pos and has_breach_strike:
        return "Narrative contains contradictory claims: personnel were reported outside the exclusion zone, but report simultaneously records personnel entering the zone or sustaining a strike."

    # Contradiction 3: Harness installed / worn + lanyard unclipped / unhitched
    has_harness_on = bool(re.search(r"\b(?:(?:full\s+body\s+|safety\s+)?harness\s+(?:was\s+)?installed|wearing\s+(?:full\s+body\s+)?harness|harness\s+(?:was\s+)?donned|100%\s+tie-off\s+claimed)\b", lower))
    has_lanyard_off = bool(re.search(r"\b(?:lanyard\s+(?:was\s+)?(?:unclipped|unhitched|detached|unhooked)|not\s+tied\s+off|unhitched\s+(?:both\s+)?(?:harness\s+)?lanyards)\b", lower))
    if has_harness_on and has_lanyard_off:
        return "Narrative contains contradictory claims: fall protection harness was reportedly installed/worn, but lanyards were documented as unhitched or not tied off."

    # Contradiction 4: Work stopped before exposure + worker exposed / injured
    has_stopped_work = bool(re.search(r"\b(?:(?:enacted|invoked|exercised|called)\s+stop\s+work(?:\s+authority)?\s+before\s+(?:worker\s+)?exposure|work\s+stopped\s+before\s+(?:worker\s+)?exposure|stop\s+work.*?before\s+(?:worker\s+)?exposure|aborted\s+prior\s+to\s+entry|cleared\s+before\s+release)\b", lower))
    has_actual_injury_text = bool(re.search(r"\b(?:worker\s+(?:sustained|suffered|was)\s+injur\w*|hospitalized|amputat\w*|fractur\w*|lacerat\w*|struck\s+in\s+the\s+face|severing\s+muscle)\b", lower))
    if has_stopped_work and has_actual_injury_text:
        return "Narrative contains contradictory claims: work was reportedly halted before exposure, yet worker sustained physical trauma or injury during the event."

    # Contradiction 5: Fixed guard installed / intact vs guard removed / missing / caught in moving parts
    has_guard_on = bool(re.search(r"\b(?:fixed\s+guard\s+(?:was\s+)?installed|guard\s+in\s+place|protective\s+mesh\s+coupling\s+guard\s+was\s+installed|fully\s+guarded)\b", lower))
    has_guard_off = bool(re.search(r"\b(?:guard\s+(?:was\s+)?removed|guard\s+had\s+been\s+removed|missing\s+guard|shaft\s+was\s+fully\s+exposed|coupling\s+guard\s+was\s+removed)\b", lower))
    if has_guard_on and has_guard_off:
        return "Narrative contains contradictory claims: machinery guarding was reported installed, but coupling guard was simultaneously documented as removed or absent."

    # Contradiction 6: Gas test zero LEL verified vs gas release / toxic gas detected / flash fire
    has_gas_safe = bool(re.search(r"\b(?:gas\s+test(?:ing)?\s+(?:showed|confirmed|was)\s+zero|0%\s*lel|tested\s+safe\s+atmosphere|continuous\s+gas\s+testing\s+confirmed)\b", lower))
    has_gas_danger = bool(re.search(r"\b(?:gas\s+(?:was\s+)?detected|h2s\s+(?:was\s+)?detected|flammable\s+vapor\s+escaped|ignited\s+a\s+flash\s+fire|flash\s+fire|gas\s+cloud)\b", lower))
    if has_gas_safe and has_gas_danger:
        return "Narrative contains contradictory claims: atmosphere was reportedly tested zero LEL / safe, but hazardous gas release or flash fire simultaneously occurred."

    # Contradiction 7: De-energized / verified zero voltage vs electrical contact / live shock
    has_deenergized = bool(re.search(r"\b(?:verified\s+zero\s+(?:hazardous\s+)?voltage|de-energiz(?:ed|ation)\s+verified|breaker\s+locked\s+out)\b", lower))
    has_electric_contact = bool(re.search(r"\b(?:arc\s+flash|flashover|live\s+wire|shock|electrocution|conductor\s+was\s+energized)\b", lower))
    if has_deenergized and has_electric_contact:
        return "Narrative contains contradictory claims: electrical apparatus was reported de-energized, but live contact or arc flash blast was documented."

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

    # Check structured job_task if raw_energy_type was absent
    raw_job_task = getattr(incident, "job_task", None) or ""
    if not energy_present and raw_job_task and raw_job_task.strip().lower() not in ["unknown", "other", "routine operations"]:
        jt_lower = raw_job_task.strip().lower()
        if any(w in jt_lower for w in ["confined space", "tank entry", "vessel entry", "manway"]):
            detected_hazard = EnergyHazardType.CONFINED_SPACE
            energy_present = True
            hazard_source_field = "job_task"
            hazard_span = f"Structured job task recorded as '{raw_job_task}'"
            all_detected_hazards.append(detected_hazard)
        elif any(w in jt_lower for w in ["height", "scaffold", "roof", "mast"]):
            detected_hazard = EnergyHazardType.WORKING_AT_HEIGHT
            energy_present = True
            hazard_source_field = "job_task"
            hazard_span = f"Structured job task recorded as '{raw_job_task}'"
            all_detected_hazards.append(detected_hazard)
        elif any(w in jt_lower for w in ["lifting", "crane", "rigging"]):
            detected_hazard = EnergyHazardType.SUSPENDED_LOADS
            energy_present = True
            hazard_source_field = "job_task"
            hazard_span = f"Structured job task recorded as '{raw_job_task}'"
            all_detected_hazards.append(detected_hazard)
        elif any(w in jt_lower for w in ["electrical", "substation", "switchgear"]):
            detected_hazard = EnergyHazardType.ELECTRICAL
            energy_present = True
            hazard_source_field = "job_task"
            hazard_span = f"Structured job task recorded as '{raw_job_task}'"
            all_detected_hazards.append(detected_hazard)
        elif any(w in jt_lower for w in ["hot work", "welding", "torch"]):
            detected_hazard = EnergyHazardType.HOT_WORK_IGNITION
            energy_present = True
            hazard_source_field = "job_task"
            hazard_span = f"Structured job task recorded as '{raw_job_task}'"
            all_detected_hazards.append(detected_hazard)
        elif any(w in jt_lower for w in ["excavation", "trench"]):
            detected_hazard = EnergyHazardType.EXCAVATION_GROUND_COLLAPSE
            energy_present = True
            hazard_source_field = "job_task"
            hazard_span = f"Structured job task recorded as '{raw_job_task}'"
            all_detected_hazards.append(detected_hazard)
        elif any(w in jt_lower for w in ["line breaking", "pressure", "hydrotest", "depressur", "energy isolation"]):
            detected_hazard = EnergyHazardType.PRESSURE_STORED
            energy_present = True
            hazard_source_field = "job_task"
            hazard_span = f"Structured job task recorded as '{raw_job_task}'"
            all_detected_hazards.append(detected_hazard)
        elif any(w in jt_lower for w in ["vehicle", "driving", "transport"]):
            detected_hazard = EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT
            energy_present = True
            hazard_source_field = "job_task"
            hazard_span = f"Structured job task recorded as '{raw_job_task}'"
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
    hierarchy_type = ControlHierarchyType.DIRECT_ENGINEERED_CONTROL

    # Check for ordinary PPE (Section 7: PPE is never equivalent to an engineered direct barrier)
    ppe_span = _extract_first_match_span(narrative, PPE_PATTERNS)
    is_ppe = bool(ppe_span or (raw_control_type and any(p in raw_control_type.lower() for p in ["ppe", "helmet", "gloves", "boots", "glasses", "goggles", "vest"])))

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
        elif _extract_first_match_span(narrative, [r"\b(?:repaired\s+after|restored\s+after\s+the\s+event|restored\s+following\s+incident)\b"]):
            control_state = ControlState.RESTORED_AFTER_EXPOSURE
            control_span = "Control restored after incident occurred"
        elif _extract_first_match_span(narrative, [r"\b(?:recommend(?:ed|ation)(?:\s+to)?|recommend(?:ed|ation)\s+(?:installing|fitting|replacing|upgrading|reviewing|verifying|adding)|should\s+install|proposed\s+barrier)\b"]):
            control_state = ControlState.RECOMMENDATION_ONLY
            control_span = "Control exists only as a post-incident recommendation"
        elif _extract_first_match_span(narrative, [r"\b(?:was\s+planned|scheduled\s+for\s+installation|intended\s+control)\b"]):
            control_state = ControlState.PLANNED_ONLY
            control_span = "Control was planned on paper but not in place"
        else:
            control_state = ControlState.UNKNOWN

    # Determine control hierarchy tier
    if is_ppe and not _extract_first_match_span(narrative, CONTROL_EFFECTIVE_PATTERNS):
        hierarchy_type = ControlHierarchyType.PPE
        is_direct_control = False  # Ordinary PPE is NEVER a direct critical barrier
        if control_state in [ControlState.UNKNOWN, ControlState.EFFECTIVE]:
            control_state = ControlState.ABSENT
            control_span = f"Only ordinary PPE ({ppe_span or 'PPE'}) present; direct engineered barrier absent"
            control_source_field = "composite_narrative"
    elif raw_control_type and any(p in raw_control_type.lower() for p in ["permit", "procedure", "check", "briefing", "talk"]):
        hierarchy_type = ControlHierarchyType.PROCEDURAL_CONTROL
    elif raw_control_type and any(p in raw_control_type.lower() for p in ["sign", "warning", "training"]):
        hierarchy_type = ControlHierarchyType.ADMINISTRATIVE_CONTROL
    else:
        hierarchy_type = ControlHierarchyType.DIRECT_ENGINEERED_CONTROL

    # 4. MATERIAL CONTRADICTION DETECTION
    contradiction_reason = detect_evidence_contradictions(narrative, control_state, exposure_state)
    is_conflicting_evidence = bool(contradiction_reason)
    if is_conflicting_evidence:
        # Contradictions strictly invalidate affirmative 'effective' claims
        if control_state == ControlState.EFFECTIVE:
            control_state = ControlState.FAILED

    # 5. CONSEQUENCE PATHWAY EVALUATION
    consequence_state = ConsequencePathwayState.UNKNOWN
    consequence_mechanism = None

    # Detect physical mechanism from 18 canonical mechanisms
    detected_phys_mech = None
    for mech_enum, mech_patterns in CONSEQUENCE_MECHANISM_PATTERNS.items():
        m_span = _extract_first_match_span(narrative, mech_patterns)
        if m_span:
            detected_phys_mech = mech_enum
            break

    if is_conflicting_evidence:
        consequence_state = ConsequencePathwayState.UNKNOWN
        consequence_mechanism = f"Conflicting evidence: {contradiction_reason}"
    elif not energy_present:
        consequence_state = ConsequencePathwayState.NOT_ESTABLISHED
        consequence_mechanism = "Low energy density; physical SIF consequence not established"
    elif control_state == ControlState.EFFECTIVE or exposure_state in [ExposureState.NO_WORKER_EXPOSURE, ExposureState.NEARBY_BUT_PROTECTED, ExposureState.EXPOSURE_INTERRUPTED]:
        consequence_state = ConsequencePathwayState.INTERRUPTED
        consequence_mechanism = "Pathway interrupted by effective direct control or safe worker positioning (Capacity)"
    elif control_state in [ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED, ControlState.INCORRECTLY_ASSUMED] and exposure_state in [ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH, ExposureState.INSIDE_EXCLUSION_ZONE]:
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
    if getattr(incident, "id", None):
        iogp_tags = IOGPRuleTag.objects.filter(incident=incident)
        for tag in iogp_tags:
            matched_iogp_rules.append(tag.rule)

    if not matched_iogp_rules:
        # Infer applicable IOGP rule from detected hazard / activity
        rule_map = {
            EnergyHazardType.WORKING_AT_HEIGHT: IOGPRuleCode.WORKING_AT_HEIGHT,
            EnergyHazardType.PRESSURE_STORED: IOGPRuleCode.ENERGY_ISOLATION,
            EnergyHazardType.ELECTRICAL: IOGPRuleCode.ENERGY_ISOLATION,
            EnergyHazardType.SUSPENDED_LOADS: IOGPRuleCode.SAFE_MECHANICAL_LIFTING,
            EnergyHazardType.CONFINED_SPACE: IOGPRuleCode.CONFINED_SPACE,
            EnergyHazardType.HOT_WORK_IGNITION: IOGPRuleCode.HOT_WORK,
            EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT: IOGPRuleCode.DRIVING,
            EnergyHazardType.LINE_OF_FIRE: IOGPRuleCode.LINE_OF_FIRE,
            EnergyHazardType.ROTATING_EQUIPMENT: IOGPRuleCode.BYPASSING_SAFETY_CONTROLS,
            EnergyHazardType.STORED_MECHANICAL_ENERGY: IOGPRuleCode.ENERGY_ISOLATION,
            EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE: IOGPRuleCode.ENERGY_ISOLATION,
        }
        if detected_hazard in rule_map:
            matched_iogp_rules.append(rule_map[detected_hazard])

    # 7. MISSING EVIDENCE & EVIDENCE STRENGTH EVALUATION
    missing_evidence: List[MissingEvidenceItem] = []
    
    if is_conflicting_evidence:
        missing_evidence.append(
            MissingEvidenceItem(
                what="Resolve contradictory safety claims recorded in the incident narrative.",
                why_it_matters=contradiction_reason or "Narrative contains mutually incompatible statements.",
                decision_impact="Resolving contradiction is required before authoritative safety determination."
            )
        )
    if energy_present and control_state == ControlState.UNKNOWN:
        missing_evidence.append(
            MissingEvidenceItem(
                what="What was the actual state of the direct/critical control (e.g. isolation, guardrail, barricade)?",
                why_it_matters="Determines whether high energy was safely contained or free to release toward personnel.",
                decision_impact="Distinguishes High Energy Controlled (NOT PSIF) from an open SIF pathway (PSIF)."
            )
        )
    if energy_present and exposure_state == ExposureState.UNKNOWN:
        missing_evidence.append(
            MissingEvidenceItem(
                what="Where was the worker positioned relative to the hazard release path or danger zone?",
                why_it_matters="A high-energy event without worker exposure cannot cause serious injury.",
                decision_impact="Confirms or breaks the worker exposure pathway required for PSIF."
            )
        )
    if is_sparse:
        missing_evidence.append(
            MissingEvidenceItem(
                what="Provide a complete composite narrative describing work activity and barrier conditions.",
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
            worker_positioning=exposure_span,
        ),
        "control": ExtractedControl(
            control_type=norm_entities["control_type"].canonical_value if raw_control_type else None,
            state=control_state,
            is_direct_control=is_direct_control,
            is_compromised=control_state in [
                ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT,
                ControlState.NOT_VERIFIED, ControlState.INCORRECTLY_ASSUMED,
                ControlState.RECOMMENDATION_ONLY, ControlState.PLANNED_ONLY
            ],
            hierarchy_type=hierarchy_type,
            evidence_text=control_span,
            source_field=control_source_field,
        ),
        "consequence": ExtractedConsequence(
            pathway_state=consequence_state,
            mechanism=consequence_mechanism,
            physical_mechanism=detected_phys_mech,
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
        d = asdict(self)
        d["rule_decision"] = self.rule_assessment
        return d


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
        # Authoritative uppercase keys per Section 15 contract
        "WHY_PSIF": why_psif,
        "WHY_NOT_PSIF": why_not_psif,
        "WHAT_IS_MISSING": why_unknown_matters,
        "WHAT_RULES_APPLY": rules_applied,
        "WHAT_CONTROL_MATTERS": control_matters,
        "WHAT_WOULD_CHANGE_ASSESSMENT": what_changes,
    }


# ── Action Engine Trace Consumer (Full Action Traceability) ───────────────────

def select_grounded_actions(
    evidence: Dict[str, Any],
    internal_state: str,
    rule_decision: str,
    matched_rule: Optional[PSIFRuleDefinition],
    high_priority_review: bool = False,
) -> List[Dict[str, Any]]:
    """
    Deterministically selects safety actions strictly from the structured reasoning trace:
    (hazard, exposure, critical_control, control_state, consequence_pathway, iogp_rule, evidence_strength).
    Provides full action traceability: triggering evidence, control addressed, rule addressed, verification method.
    Delegates to the authoritative 15-hazard family Action Engine in apps.incidents.knowledge.action_mappings.
    """
    from apps.incidents.knowledge.action_mappings import generate_grounded_actions

    hazard: ExtractedHazard = evidence["hazard"]
    control: ExtractedControl = evidence["control"]
    exposure: ExtractedExposure = evidence["exposure"]
    missing_items = evidence.get("missing_evidence", [])
    contradiction_details = evidence.get("contradiction_details")
    trigger_text = control.evidence_text or hazard.evidence_text or exposure.evidence_text or ""
    all_detected_hazards = evidence.get("all_detected_hazards", [hazard.hazard_type])
    sub_pathways = evidence.get("sub_pathways", [])

    actions = generate_grounded_actions(
        hazard_type=hazard.hazard_type,
        control_state=control.state,
        exposure_state=exposure.state,
        decision=rule_decision,
        internal_state=internal_state,
        missing_items=missing_items,
        contradiction_details=contradiction_details,
        control_name=control.control_type,
        rule_name=matched_rule.name if matched_rule else None,
        trigger_text=trigger_text,
        all_detected_hazards=all_detected_hazards,
        high_priority_review=high_priority_review,
        sub_pathways=sub_pathways,
    )
    return actions


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
        high_priority_review=reconciliation.high_priority_review,
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

    # 7. Build Reconstructible Evidence Trace (Section 11)
    evidence_trace: List[Dict[str, Any]] = [
        EvidenceTraceItem(
            source=evidence["hazard"].source_field,
            field="hazard",
            supporting_text=evidence["hazard"].evidence_text or f"Hazard type: {evidence['hazard'].hazard_type}",
            normalized_concept=evidence["hazard"].hazard_type,
            state="ENERGY_PRESENT" if evidence["hazard"].energy_present else "LOW_ENERGY",
            strength="STRONG" if evidence["hazard"].evidence_text else "MODERATE",
            rule_association=matched_rule.rule_id if matched_rule else "GENERAL_SIF",
            provenance=matched_rule.source if matched_rule else "EEI_SCL_2021",
            decision_effect=internal_state,
        ).to_dict(),
        EvidenceTraceItem(
            source=evidence["exposure"].source_field,
            field="exposure",
            supporting_text=evidence["exposure"].evidence_text or f"Worker positioning: {evidence['exposure'].state}",
            normalized_concept="worker_positioning",
            state=evidence["exposure"].state,
            strength="STRONG" if evidence["exposure"].evidence_text else "WEAK",
            rule_association=matched_rule.rule_id if matched_rule else "GENERAL_SIF",
            provenance=matched_rule.source if matched_rule else "EEI_SCL_2021",
            decision_effect=internal_state,
        ).to_dict(),
        EvidenceTraceItem(
            source=evidence["control"].source_field,
            field="control",
            supporting_text=evidence["control"].evidence_text or f"Control state: {evidence['control'].state}",
            normalized_concept="critical_barrier",
            state=evidence["control"].state,
            strength="STRONG" if evidence["control"].evidence_text else "MODERATE",
            rule_association=matched_rule.rule_id if matched_rule else "GENERAL_SIF",
            provenance=matched_rule.source if matched_rule else "EEI_SCL_2021",
            decision_effect=internal_state,
        ).to_dict(),
        EvidenceTraceItem(
            source="rule_engine",
            field="consequence_pathway",
            supporting_text=evidence["consequence"].mechanism or f"Pathway state: {evidence['consequence'].pathway_state}",
            normalized_concept="sif_pathway",
            state=evidence["consequence"].pathway_state,
            strength=evidence["evidence_strength"],
            rule_association=matched_rule.rule_id if matched_rule else "GENERAL_SIF",
            provenance=matched_rule.source if matched_rule else "EEI_SCL_2021",
            decision_effect=internal_state,
        ).to_dict(),
    ]

    # 8. Downstream Action Engine Interface (Section 16)
    action_interface: Dict[str, Any] = {
        "hazard": evidence["hazard"].hazard_type,
        "exposure": evidence["exposure"].state,
        "control": evidence["control"].control_type or "Engineered Barrier",
        "control_state": evidence["control"].state,
        "consequence": evidence["consequence"].pathway_state,
        "rule": matched_rule.rule_id if matched_rule else "GENERAL_SIF",
        "evidence_strength": evidence["evidence_strength"],
        "decision": reconciliation.policy_final_decision,
        "recommended_actions": actions,
    }

    # 9. IOGP Life-Saving Rules Separation (Section 9)
    iogp_separation: Dict[str, Any] = {
        "iogp_rule_matched": bool(evidence["matched_iogp_rules"]),
        "iogp_applicability": evidence["matched_iogp_rules"],
        "rule_adherence": "COMPLIANT" if evidence["control"].state in [ControlState.EFFECTIVE, ControlState.RESTORED_BEFORE_EXPOSURE] else ("VIOLATED" if evidence["control"].is_compromised else "UNKNOWN"),
        "worker_exposure": evidence["exposure"].state,
        "control_state": evidence["control"].state,
        "sif_pathway": evidence["consequence"].pathway_state,
        "psif_decision": reconciliation.policy_final_decision,
        "separation_rationale": "IOGP life-saving rule applicability reflects operational activity type; violation or PSIF requires independent evidence of exposed personnel and compromised barrier.",
    }

    # 10. Task 4 Declarative Anti-Inferences & Temporal Semantics Evaluation
    narrative_text = str(incident.composite_narrative or incident.description or "")
    anti_inferences = evaluate_anti_inferences(
        text=narrative_text,
        hazard_detected=evidence["hazard"].energy_present,
        exposure_state=evidence["exposure"].state,
        control_state=evidence["control"].state,
        iogp_matches=evidence.get("matched_iogp_rules", []),
    )
    temporal_exprs = extract_temporal_expressions(text=narrative_text)
    terminology_matches = find_terminology_matches(text=narrative_text)

    # 11. Task 4 Reasoning Provenance Graph (source -> semantic role -> concept -> state -> rule -> effect)
    provenance_graph: List[Dict[str, Any]] = [
        {
            "source_text": evidence["hazard"].evidence_text or f"Hazard type: {evidence['hazard'].hazard_type}",
            "semantic_role": SemanticRole.EVENT if evidence["hazard"].energy_present else SemanticRole.OBSERVED_STATE,
            "normalized_concept": evidence["hazard"].hazard_type,
            "state": "ENERGY_PRESENT" if evidence["hazard"].energy_present else "LOW_ENERGY",
            "applicable_rule": matched_rule.rule_id if matched_rule else "GENERAL_SIF",
            "evidence_contribution": "ESTABLISHES_HIGH_ENERGY_POTENTIAL" if evidence["hazard"].energy_present else "LOW_ENERGY_BASELINE",
            "decision_effect": internal_state,
        },
        {
            "source_text": evidence["exposure"].evidence_text or f"Worker positioning: {evidence['exposure'].state}",
            "semantic_role": SemanticRole.EVENT if evidence["exposure"].state in [ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH] else SemanticRole.OBSERVED_STATE,
            "normalized_concept": "worker_exposure",
            "state": evidence["exposure"].state,
            "applicable_rule": matched_rule.rule_id if matched_rule else "GENERAL_SIF",
            "evidence_contribution": "EXPOSURE_PATHWAY_OPEN" if evidence["exposure"].state in [ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH] else "EXPOSURE_INTERRUPTED_OR_ABSENT",
            "decision_effect": internal_state,
        },
        {
            "source_text": evidence["control"].evidence_text or f"Control state: {evidence['control'].state}",
            "semantic_role": SemanticRole.EVENT if evidence["control"].is_compromised else (SemanticRole.VERIFIED_STATE if evidence["control"].state == ControlState.EFFECTIVE else SemanticRole.OBSERVED_STATE),
            "normalized_concept": evidence["control"].control_type or "critical_barrier",
            "state": evidence["control"].state,
            "applicable_rule": matched_rule.rule_id if matched_rule else "GENERAL_SIF",
            "evidence_contribution": "BARRIER_COMPROMISED" if evidence["control"].is_compromised else ("BARRIER_EFFECTIVE" if evidence["control"].state == ControlState.EFFECTIVE else "BARRIER_UNVERIFIED"),
            "decision_effect": internal_state,
        },
        {
            "source_text": evidence["consequence"].mechanism or f"Pathway state: {evidence['consequence'].pathway_state}",
            "semantic_role": SemanticRole.EVENT if evidence["consequence"].credible_sif_potential else SemanticRole.OBSERVED_STATE,
            "normalized_concept": evidence["consequence"].physical_mechanism or "sif_consequence",
            "state": evidence["consequence"].pathway_state,
            "applicable_rule": matched_rule.rule_id if matched_rule else "GENERAL_SIF",
            "evidence_contribution": "SIF_CONSEQUENCE_CREDIBLE" if evidence["consequence"].credible_sif_potential else "PATHWAY_INTERRUPTED",
            "decision_effect": internal_state,
        },
    ]
    for ai in anti_inferences:
        if ai.is_inference_prevented:
            provenance_graph.append({
                "source_text": ai.rule_name,
                "semantic_role": "ANTI_INFERENCE_CONSTRAINT",
                "normalized_concept": ai.rule_code,
                "state": "INFERENCE_PREVENTED",
                "applicable_rule": ai.rule_code,
                "evidence_contribution": f"PREVENTED_FALSE_INFERENCE: {ai.prohibited_inference}",
                "decision_effect": internal_state,
            })

    # 12. Task 4 Multi-Hazard Structured Pathways
    multi_hazard_pathways = []
    for h_type in evidence.get("all_detected_hazards", []):
        h_def = get_hazard_definition(h_type)
        h_contract = get_evidence_contract(h_type)
        multi_hazard_pathways.append({
            "hazard_type": h_type,
            "hazard_name": h_def.name if h_def else h_type.replace("_", " ").title(),
            "energy_manifestation": h_def.energy_manifestation if h_def else "High energy vector",
            "applicable_iogp_rules": h_def.applicable_iogp_rules if h_def else [],
            "required_evidence": h_contract.required_evidence if h_contract else [],
        })

    # 13. Assemble auditable reasoning payload matching Section 11 API contract
    return {
        "incident_id": str(incident.id),
        "decision": reconciliation.policy_final_decision,
        "internal_reasoning_state": internal_state,
        "evidence_strength": evidence["evidence_strength"],
        "reasoning_chain": reasoning_chain,
        "evidence_matrix": [asdict(r) for r in matrix],
        "evidence_trace": evidence_trace,
        "provenance_graph": provenance_graph,
        "anti_inferences": [asdict(ai) for ai in anti_inferences],
        "temporal_expressions": [asdict(te) for te in temporal_exprs],
        "terminology_matches": [asdict(tm) for tm in terminology_matches],
        "action_interface": action_interface,
        "iogp_separation": iogp_separation,
        "what_is_known": explanation["what_is_known"],
        "what_is_missing": explanation["what_is_missing"],
        "what_is_unknown": explanation["what_is_unknown"],
        "why_unknown_matters": explanation["why_unknown_matters"],
        "what_information_would_close_case": explanation["what_information_would_close_case"],
        "evidence_needed_to_close": explanation["what_information_would_close_case"],
        "why_psif": explanation["why_psif"],
        "why_not_psif": explanation["why_not_psif"],
        "rules_applied": explanation["what_rules_apply"],
        "control": {
            "control_type": evidence["control"].control_type,
            "state": evidence["control"].state,
            "is_direct_control": evidence["control"].is_direct_control,
            "is_compromised": evidence["control"].is_compromised,
            "hierarchy_type": evidence["control"].hierarchy_type,
            "evidence_text": evidence["control"].evidence_text,
        },
        "control_assessment": {
            "control_type": evidence["control"].control_type,
            "state": evidence["control"].state,
            "is_direct_control": evidence["control"].is_direct_control,
            "is_compromised": evidence["control"].is_compromised,
            "hierarchy_type": evidence["control"].hierarchy_type,
            "evidence_text": evidence["control"].evidence_text,
        },
        "consequence_pathway": {
            "pathway_state": evidence["consequence"].pathway_state,
            "mechanism": evidence["consequence"].mechanism,
            "physical_mechanism": evidence["consequence"].physical_mechanism,
            "credible_sif_potential": evidence["consequence"].credible_sif_potential,
        },
        "reconciliation": reconciliation.to_dict(),
        "high_priority_review": reconciliation.high_priority_review,
        "grounded_actions": actions,
        "multi_hazard": {
            "primary_hazard": evidence["hazard"].hazard_type,
            "secondary_hazards": [h for h in evidence.get("all_detected_hazards", []) if h != evidence["hazard"].hazard_type],
            "all_detected_hazards": evidence.get("all_detected_hazards", [evidence["hazard"].hazard_type]),
            "pathways": multi_hazard_pathways,
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
                "provenance_tier": matched_rule.provenance_tier,
            } if matched_rule else {
                "source_id": "EEI_SCL_2021",
                "source_section": "EEI SCL Model (2021) General SIF Framework",
                "rule_id": "GEN-01",
                "rule_name": "General Safety Classification and Learning",
                "provenance_tier": "DOMAIN_SIF_FRAMEWORK",
            }
        ],
        # Section 15 Authoritative Uppercase Keys
        "WHY_PSIF": explanation["WHY_PSIF"],
        "WHY_NOT_PSIF": explanation["WHY_NOT_PSIF"],
        "WHAT_IS_MISSING": explanation["WHAT_IS_MISSING"],
        "WHAT_RULES_APPLY": explanation["WHAT_RULES_APPLY"],
        "WHAT_CONTROL_MATTERS": explanation["WHAT_CONTROL_MATTERS"],
        "WHAT_WOULD_CHANGE_ASSESSMENT": explanation["WHAT_WOULD_CHANGE_ASSESSMENT"],
        "ACTION_INTERFACE": action_interface,
        "IOGP_SEPARATION": iogp_separation,
        "EVIDENCE_TRACE": evidence_trace,
        # Backwards-compatible aliases for existing consumers
        "final_policy_decision": reconciliation.policy_final_decision,
        "rule_decision": rule_decision,
        "is_sparse_report": evidence["is_sparse"],
        "matched_rule": {
            "rule_id": matched_rule.rule_id,
            "name": matched_rule.name,
            "source": matched_rule.source,
            "source_section": matched_rule.source_section,
            "provenance_tier": matched_rule.provenance_tier,
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


# Authoritative public contract aliases
evaluate_incident_psif_reasoning = build_incident_reasoning_assessment
reconcile_prediction_and_rules = reconcile_model_and_rules
