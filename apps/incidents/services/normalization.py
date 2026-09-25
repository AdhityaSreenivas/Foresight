"""
PSIF Platform — Safety Entity Normalization & Canonical Terminology Service

Architecture:
    raw value
    → normalized/canonical value
    → normalization method
    → optional alias
    → confidence/status
    → provenance

Conservative Principles:
1. Raw values are ALWAYS preserved for traceability.
2. Exact canonical matches and exact alias lookups take precedence.
3. Bounded fuzzy matching requires a high similarity threshold (>= 0.88)
   and tags suggestions with 'suggested' or 'uncertain' without silent blind mergers.
4. If no reliable canonical mapping is found, values retain 'identity' mapping
   with status 'uncertain' rather than being incorrectly merged.
"""

from dataclasses import dataclass, field, asdict
import difflib
import functools
import re
from typing import Optional, Dict, Any, List, Tuple


NORMALIZATION_VERSION = "deterministic_taxonomy_v1"
CROSS_SITE_NORMALIZATION_VERSION = "cross_site_taxonomy_v1"


# ── Enumerations & Constants ──────────────────────────────────────────────────

class NormalizationMethod:
    EXACT_ALIAS = "exact_alias"              # Mapped via verified domain alias table
    NORMALIZED = "normalized"                # Canonical match (syntax/spacing/case normalized)
    BOUNDED_FUZZY = "bounded_fuzzy"          # High-confidence similarity match against explicit candidate pool
    IDENTITY = "identity"                    # Unmapped raw string preserved as-is
    UNKNOWN = "unknown"                      # Missing, empty, or null raw value

    # Backward-compatibility aliases
    EXACT = "normalized"
    EXACT_CANONICAL = "normalized"
    NORMALIZED_SYNTAX = "normalized"
    UNMAPPED = "unknown"


class NormalizationStatus:
    CANONICAL = "canonical"                  # Value is the official canonical term
    MAPPED = "mapped"                        # Mapped with high certainty to canonical (exact alias)
    SUGGESTED = "suggested"                  # Bounded fuzzy candidate suggested (explicit review advised)
    UNCERTAIN = "uncertain"                  # Kept as identity to prevent unverified merging
    UNKNOWN = "unknown"                      # Missing, empty, or explicitly unknown input

    # Defensible status codes (Task 10)
    EXACT = "canonical"
    ALIAS = "mapped"
    NORMALIZED = "normalized"

    STATUS_EXACT = "EXACT"
    STATUS_ALIAS = "ALIAS"
    STATUS_NORMALIZED = "NORMALIZED"
    STATUS_UNKNOWN = "UNKNOWN"
    STATUS_UNCERTAIN = "UNCERTAIN"

    # Backward-compatibility aliases
    RESOLVED = "mapped"
    UNMAPPED = "unknown"


@dataclass(frozen=True)
class NormalizedEntity:
    raw_value: Optional[str]
    canonical_value: str
    entity_type: str
    method: str
    status: str
    confidence: float
    alias_matched: Optional[str] = None
    provenance: str = NORMALIZATION_VERSION
    source_field: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["normalized_value"] = self.normalized_value
        d["status_code"] = self.status_code
        d["normalization_method"] = self.normalization_method
        d["normalization_version"] = self.normalization_version
        d["version"] = self.normalization_version
        return d

    @property
    def normalized_value(self) -> str:
        return self.canonical_value

    @property
    def normalization_method(self) -> str:
        return self.method

    @property
    def normalization_version(self) -> str:
        return self.provenance

    @property
    def status_code(self) -> str:
        """Returns standard uppercase status: EXACT, ALIAS, NORMALIZED, UNKNOWN, UNCERTAIN."""
        if self.status in (NormalizationStatus.CANONICAL, "canonical", "EXACT"):
            return NormalizationStatus.STATUS_EXACT
        elif self.status in (NormalizationStatus.MAPPED, "mapped", "resolved", "ALIAS"):
            return NormalizationStatus.STATUS_ALIAS
        elif self.status in (NormalizationStatus.SUGGESTED, "suggested", "NORMALIZED", "normalized"):
            return NormalizationStatus.STATUS_NORMALIZED
        elif self.status in (NormalizationStatus.UNKNOWN, "unknown", "unmapped", "UNKNOWN"):
            return NormalizationStatus.STATUS_UNKNOWN
        elif self.status in (NormalizationStatus.UNCERTAIN, "uncertain", "UNCERTAIN"):
            return NormalizationStatus.STATUS_UNCERTAIN
        return NormalizationStatus.STATUS_NORMALIZED if self.canonical_value else NormalizationStatus.STATUS_UNKNOWN

    @property
    def is_exact(self) -> bool:
        return self.status_code == NormalizationStatus.STATUS_EXACT

    @property
    def is_alias(self) -> bool:
        return self.status_code == NormalizationStatus.STATUS_ALIAS

    @property
    def is_normalized(self) -> bool:
        return self.status_code in (
            NormalizationStatus.STATUS_EXACT,
            NormalizationStatus.STATUS_ALIAS,
            NormalizationStatus.STATUS_NORMALIZED,
        )

    @property
    def is_canonical(self) -> bool:
        return self.status == NormalizationStatus.CANONICAL

    @property
    def is_mapped(self) -> bool:
        return self.status in (NormalizationStatus.MAPPED, "resolved")

    @property
    def is_suggested(self) -> bool:
        return self.status == NormalizationStatus.SUGGESTED

    @property
    def is_uncertain(self) -> bool:
        return self.status == NormalizationStatus.UNCERTAIN

    @property
    def is_unknown(self) -> bool:
        return self.status in (NormalizationStatus.UNKNOWN, "unmapped", "UNKNOWN")


# ── Syntax Sanitization Helper ────────────────────────────────────────────────

def sanitize_string(val: Optional[str]) -> str:
    """
    Strips leading/trailing whitespace, collapses internal whitespace,
    and strips dangerous or non-printable characters.
    """
    if val is None:
        return ""
    # Normalize internal whitespace and strip
    cleaned = re.sub(r"\s+", " ", str(val)).strip()
    return cleaned


def normalize_lookup_key(val: Optional[str]) -> str:
    """
    Produces a normalized lower-case alphanumeric key with single spaces
    for robust dictionary lookup.
    """
    if not val:
        return ""
    # Lowercase and replace non-alphanumeric (except space) with spaces
    s = str(val).lower()
    s = re.sub(r"[_\-/\\.,;:()[\]{}&+#%*]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ── Domain Taxonomies & Alias Registries ──────────────────────────────────────

# 1a. Operational Geographic / Field Sites Taxonomy (SIH PS 26165 OIL Sites)
CANONICAL_OPERATIONAL_SITES = [
    "DULIAJAN",
    "NUMALIGARH",
    "MORAN",
    "NAHARKATIYA",
    "KUMCHAI",
    "BAGHJAN",
    "TENGAKHAT",
    "MAKUM",
    "SILCHAR",
    "DIGBOI",
    "GUWAHATI",
    "JORAJAN",
    "UPPER ASSAM FIELD",
    "DULIAJAN-DIGBOI PIPELINE",
    "DULIAJAN-BARAUNI PIPELINE",
    "OFFSHORE PLATFORM ALPHA",
    "DRILLING RIG 9",
    "DRILLING RIG 14",
    "DRILLING RIG 21",
    "WORKOVER RIG 3",
    "WORKOVER RIG 7",
    "GULF COAST FACILITY",
    "PERMIAN BASIN",
]

OPERATIONAL_SITE_ALIASES = {
    # Duliajan Field HQ & Installations
    "duliajan": "DULIAJAN",
    "duliajan site": "DULIAJAN",
    "duliajan-site": "DULIAJAN",
    "site duliajan": "DULIAJAN",
    "ctf duliajan": "DULIAJAN",
    "central tank farm duliajan": "DULIAJAN",
    "field hq duliajan": "DULIAJAN",
    "central workshop duliajan": "DULIAJAN",
    # Moran
    "moran": "MORAN",
    "moran site": "MORAN",
    "moran-site": "MORAN",
    "ggs moran": "MORAN",
    "group gathering station moran": "MORAN",
    # Numaligarh
    "numaligarh": "NUMALIGARH",
    "numaligarh site": "NUMALIGARH",
    "numaligarh refinery": "NUMALIGARH",
    "numaligarh refinery tank farm": "NUMALIGARH",
    "numaligarh refinery - tank farm": "NUMALIGARH",
    # Naharkatiya
    "naharkatiya": "NAHARKATIYA",
    "naharkatiya site": "NAHARKATIYA",
    "nhk": "NAHARKATIYA",
    # Kumchai
    "kumchai": "KUMCHAI",
    "kumchai field": "KUMCHAI",
    # Baghjan
    "baghjan": "BAGHJAN",
    "baghjan site": "BAGHJAN",
    "eps baghjan": "BAGHJAN",
    "early production system baghjan": "BAGHJAN",
    # Tengakhat
    "tengakhat": "TENGAKHAT",
    "tengakhat site": "TENGAKHAT",
    # Makum
    "makum": "MAKUM",
    "makum site": "MAKUM",
    "gas compressor station makum": "MAKUM",
    # Silchar
    "silchar": "SILCHAR",
    "silchar site": "SILCHAR",
    # Digboi
    "digboi": "DIGBOI",
    "digboi field": "DIGBOI",
    # Guwahati
    "guwahati": "GUWAHATI",
    "guwahati sector": "GUWAHATI",
    # Jorajan
    "jorajan": "JORAJAN",
    "jorajan field": "JORAJAN",
    # Upper Assam
    "upper assam field": "UPPER ASSAM FIELD",
    "upper assam": "UPPER ASSAM FIELD",
    # Pipelines
    "duliajan digboi pipeline": "DULIAJAN-DIGBOI PIPELINE",
    "duliajan-digboi section": "DULIAJAN-DIGBOI PIPELINE",
    "duliajan digboi section": "DULIAJAN-DIGBOI PIPELINE",
    "duliajan barauni pipeline": "DULIAJAN-BARAUNI PIPELINE",
    "duliajan-barauni section": "DULIAJAN-BARAUNI PIPELINE",
    "duliajan barauni section": "DULIAJAN-BARAUNI PIPELINE",
    # Rigs & Facilities
    "offshore platform alpha": "OFFSHORE PLATFORM ALPHA",
    "platform alpha": "OFFSHORE PLATFORM ALPHA",
    "drilling rig 9": "DRILLING RIG 9",
    "rig 9": "DRILLING RIG 9",
    "rig 9 drilling": "DRILLING RIG 9",
    "rig-9 (drilling)": "DRILLING RIG 9",
    "drilling rig 14": "DRILLING RIG 14",
    "rig 14": "DRILLING RIG 14",
    "drilling rig 21": "DRILLING RIG 21",
    "rig 21": "DRILLING RIG 21",
    "workover rig 3": "WORKOVER RIG 3",
    "rig 3 workover": "WORKOVER RIG 3",
    "workover rig 7": "WORKOVER RIG 7",
    "rig 7 workover": "WORKOVER RIG 7",
    "gulf coast facility": "GULF COAST FACILITY",
    "permian basin": "PERMIAN BASIN",
}

# 1b. Site / Location Functional Work Areas Taxonomy
CANONICAL_LOCATIONS = [
    "Loading Rack",
    "Workshop/Maintenance Bay",
    "Tank Farm",
    "Produced Water Treatment",
    "Jetty/Marine Terminal",
    "Cooling Tower Area",
    "Compressor Station",
    "Wellhead Platform",
    "Pipeline ROW",
    "Mud Pit Area",
    "Sand Trap Area",
    "Drill Floor",
    "Electrical Substation",
    "Flare Area",
    "Warehouse / Storage Yard",
    "Control Room",
    "Offsite / Public Road",
]

LOCATION_ALIASES = {
    # Jetty / Marine
    "jetty": "Jetty/Marine Terminal",
    "marine terminal": "Jetty/Marine Terminal",
    "marine jetty": "Jetty/Marine Terminal",
    "dock": "Jetty/Marine Terminal",
    "wharf": "Jetty/Marine Terminal",
    "berth": "Jetty/Marine Terminal",
    # Tank farm
    "tank farm": "Tank Farm",
    "tankfarm": "Tank Farm",
    "tanks": "Tank Farm",
    "storage tank area": "Tank Farm",
    "tank battery": "Tank Farm",
    # Drill Floor
    "drill floor": "Drill Floor",
    "rig floor": "Drill Floor",
    "derrick": "Drill Floor",
    "derrick floor": "Drill Floor",
    "rotary table area": "Drill Floor",
    # Wellhead
    "wellhead": "Wellhead Platform",
    "well head": "Wellhead Platform",
    "wellhead platform": "Wellhead Platform",
    "whp": "Wellhead Platform",
    "christmas tree area": "Wellhead Platform",
    # Compressor
    "compressor station": "Compressor Station",
    "compressor": "Compressor Station",
    "comp station": "Compressor Station",
    "gas compression": "Compressor Station",
    # Cooling tower
    "cooling tower": "Cooling Tower Area",
    "cooling tower area": "Cooling Tower Area",
    # Workshop / Maintenance
    "workshop": "Workshop/Maintenance Bay",
    "maintenance bay": "Workshop/Maintenance Bay",
    "maint bay": "Workshop/Maintenance Bay",
    "mech shop": "Workshop/Maintenance Bay",
    "fab shop": "Workshop/Maintenance Bay",
    # Loading rack
    "loading rack": "Loading Rack",
    "truck loading rack": "Loading Rack",
    "loading bay": "Loading Rack",
    "gantry": "Loading Rack",
    # Pipeline ROW
    "pipeline row": "Pipeline ROW",
    "pipeline": "Pipeline ROW",
    "right of way": "Pipeline ROW",
    "flowline": "Pipeline ROW",
    "manifold area": "Pipeline ROW",
    # Water treatment
    "produced water treatment": "Produced Water Treatment",
    "water treatment": "Produced Water Treatment",
    "pwt": "Produced Water Treatment",
    "effluent treatment": "Produced Water Treatment",
    # Mud / Sand
    "mud pit": "Mud Pit Area",
    "mud pit area": "Mud Pit Area",
    "mud pits": "Mud Pit Area",
    "sand trap": "Sand Trap Area",
    "sand trap area": "Sand Trap Area",
    # Substation
    "substation": "Electrical Substation",
    "switchgear room": "Electrical Substation",
    "transformer yard": "Electrical Substation",
    # Flare
    "flare": "Flare Area",
    "flare pit": "Flare Area",
    "flare stack": "Flare Area",
    # Warehouse
    "warehouse": "Warehouse / Storage Yard",
    "storage yard": "Warehouse / Storage Yard",
    "pipe yard": "Warehouse / Storage Yard",
    "stores": "Warehouse / Storage Yard",
    # Control Room
    "control room": "Control Room",
    "ccr": "Control Room",
}

# Unified Sites (combines operational sites and functional work areas for backward compatibility)
CANONICAL_SITES = CANONICAL_OPERATIONAL_SITES + [loc for loc in CANONICAL_LOCATIONS if loc not in CANONICAL_OPERATIONAL_SITES]
SITE_ALIASES = {**LOCATION_ALIASES, **OPERATIONAL_SITE_ALIASES}


# 2. Department Taxonomy
CANONICAL_DEPARTMENTS = [
    "Drilling",
    "Workover",
    "Refinery Operations",
    "Mechanical Maintenance",
    "Electrical Maintenance",
    "Instrumentation",
    "Civil",
    "Logistics & Stores",
    "Security",
    "HSE / Safety",
    "Production Operations",
    "Pipeline Operations",
]

DEPARTMENT_ALIASES = {
    "drilling": "Drilling",
    "drill ops": "Drilling",
    "drilling operations": "Drilling",
    "rig operations": "Drilling",
    "workover": "Workover",
    "well intervention": "Workover",
    "snubbing": "Workover",
    "wireline": "Workover",
    "refinery": "Refinery Operations",
    "refinery operations": "Refinery Operations",
    "refinery ops": "Refinery Operations",
    "refining": "Refinery Operations",
    "process operations": "Refinery Operations",
    "mechanical": "Mechanical Maintenance",
    "mechanical maintenance": "Mechanical Maintenance",
    "mech": "Mechanical Maintenance",
    "mech maint": "Mechanical Maintenance",
    "electrical": "Electrical Maintenance",
    "electrical maintenance": "Electrical Maintenance",
    "elec": "Electrical Maintenance",
    "elec maint": "Electrical Maintenance",
    "instrumentation": "Instrumentation",
    "i c": "Instrumentation",
    "instrumentation and control": "Instrumentation",
    "inst": "Instrumentation",
    "civil": "Civil",
    "civil engineering": "Civil",
    "construction": "Civil",
    "logistics": "Logistics & Stores",
    "logistics stores": "Logistics & Stores",
    "stores": "Logistics & Stores",
    "supply chain": "Logistics & Stores",
    "materials": "Logistics & Stores",
    "security": "Security",
    "hse": "HSE / Safety",
    "safety": "HSE / Safety",
    "ehs": "HSE / Safety",
    "occupational health": "HSE / Safety",
    "production": "Production Operations",
    "production operations": "Production Operations",
    "operations": "Production Operations",
    "pipeline": "Pipeline Operations",
    "pipeline operations": "Pipeline Operations",
}


# 3. Activity / Job Task Taxonomy
CANONICAL_ACTIVITIES = [
    "Hot Work in Classified Area",
    "Confined Space Vessel Entry",
    "Work at Height / Scaffold Work",
    "Lifting Operations / Rigging",
    "Safe Mechanical Lifting",
    "Energy Isolation / LOTO",
    "Wellhead Pressure Control Intervention",
    "Pipeline Tie-In / Hot Tap",
    "Marine Hydrocarbon Transfer",
    "Internal Pressure Vessel Cleaning",
    "Excavation / Trenching",
    "Vehicle Operation / Road Transport",
    "Vehicle Maintenance / Servicing",
    "Electrical Maintenance / Switching",
    "Chemical Handling / Sampling",
    "Permit to Work / Work Authorization",
    "Routine Maintenance / Inspection",
]

ACTIVITY_ALIASES = {
    "hot work in a hydrocarbon classified area": "Hot Work in Classified Area",
    "hot work in classified area": "Hot Work in Classified Area",
    "hot work": "Hot Work in Classified Area",
    "welding": "Hot Work in Classified Area",
    "cutting and welding": "Hot Work in Classified Area",
    "torch cutting": "Hot Work in Classified Area",
    "confined space vessel entry": "Confined Space Vessel Entry",
    "confined space entry": "Confined Space Vessel Entry",
    "tank entry": "Confined Space Vessel Entry",
    "vessel entry": "Confined Space Vessel Entry",
    "manhole entry": "Confined Space Vessel Entry",
    "work at height scaffold work": "Work at Height / Scaffold Work",
    "work at height": "Work at Height / Scaffold Work",
    "working at height": "Work at Height / Scaffold Work",
    "scaffolding": "Work at Height / Scaffold Work",
    "scaffold erection": "Work at Height / Scaffold Work",
    "work on a floating or fixed tank roof": "Work at Height / Scaffold Work",
    "tank roof work": "Work at Height / Scaffold Work",
    "lifting operations rigging": "Lifting Operations / Rigging",
    "lifting operations": "Lifting Operations / Rigging",
    "lifting operation": "Safe Mechanical Lifting",
    "material lifting": "Safe Mechanical Lifting",
    "lifting materials": "Safe Mechanical Lifting",
    "safe mechanical lifting": "Safe Mechanical Lifting",
    "mechanical lifting": "Safe Mechanical Lifting",
    "lifting": "Safe Mechanical Lifting",
    "safe lifting": "Safe Mechanical Lifting",
    "crane lift": "Lifting Operations / Rigging",
    "crane operation": "Lifting Operations / Rigging",
    "rigging": "Lifting Operations / Rigging",
    "heavy lift": "Lifting Operations / Rigging",
    "energy isolation loto": "Energy Isolation / LOTO",
    "energy isolation": "Energy Isolation / LOTO",
    "loto": "Energy Isolation / LOTO",
    "lockout tagout": "Energy Isolation / LOTO",
    "isolation and de energization": "Energy Isolation / LOTO",
    "wellhead pressure control intervention": "Wellhead Pressure Control Intervention",
    "wellhead intervention": "Wellhead Pressure Control Intervention",
    "pressure control": "Wellhead Pressure Control Intervention",
    "bop testing": "Wellhead Pressure Control Intervention",
    "pipeline tie in hot tap operation": "Pipeline Tie-In / Hot Tap",
    "pipeline tie in hot tap": "Pipeline Tie-In / Hot Tap",
    "hot tap": "Pipeline Tie-In / Hot Tap",
    "pipeline tie in": "Pipeline Tie-In / Hot Tap",
    "marine hydrocarbon transfer at the jetty": "Marine Hydrocarbon Transfer",
    "marine hydrocarbon transfer": "Marine Hydrocarbon Transfer",
    "jetty loading": "Marine Hydrocarbon Transfer",
    "bunkering": "Marine Hydrocarbon Transfer",
    "ship to shore transfer": "Marine Hydrocarbon Transfer",
    "internal cleaning of a pressure vessel": "Internal Pressure Vessel Cleaning",
    "internal pressure vessel cleaning": "Internal Pressure Vessel Cleaning",
    "vessel descaling": "Internal Pressure Vessel Cleaning",
    "tank cleaning": "Internal Pressure Vessel Cleaning",
    "excavation trenching": "Excavation / Trenching",
    "excavation": "Excavation / Trenching",
    "trenching": "Excavation / Trenching",
    "digging": "Excavation / Trenching",
    "vehicle operation road transport": "Vehicle Operation / Road Transport",
    "driving": "Vehicle Operation / Road Transport",
    "vehicle transport": "Vehicle Operation / Road Transport",
    "road haulage": "Vehicle Operation / Road Transport",
    "vehicle maintenance": "Vehicle Maintenance / Servicing",
    "truck maintenance": "Vehicle Maintenance / Servicing",
    "fleet maintenance": "Vehicle Maintenance / Servicing",
    "fleet servicing": "Vehicle Maintenance / Servicing",
    "vehicle servicing": "Vehicle Maintenance / Servicing",
    "electrical maintenance switching": "Electrical Maintenance / Switching",
    "electrical switching": "Electrical Maintenance / Switching",
    "breaker servicing": "Electrical Maintenance / Switching",
    "chemical handling sampling": "Chemical Handling / Sampling",
    "chemical sampling": "Chemical Handling / Sampling",
    "permit to work": "Permit to Work / Work Authorization",
    "work permit": "Permit to Work / Work Authorization",
    "ptw": "Permit to Work / Work Authorization",
    "work authorization": "Permit to Work / Work Authorization",
    "work authorisation": "Permit to Work / Work Authorization",
    "permit": "Permit to Work / Work Authorization",
    "authorization": "Permit to Work / Work Authorization",
    "routine maintenance inspection": "Routine Maintenance / Inspection",
    "inspection": "Routine Maintenance / Inspection",
}


# 4. Equipment / Asset Taxonomy
CANONICAL_EQUIPMENT_CLASSES = [
    "Chemical Pump",
    "Hydraulic Press",
    "Electrical Panel",
    "Portable Generator",
    "Step Ladder",
    "Extension Ladder",
    "Hand Truck",
    "Angle Grinder",
    "Pressure Washer",
    "Compressed Air Line",
    "Boom Lift / MEWP",
    "Crane / Hoist",
    "Storage Tank",
    "Pressure Vessel",
    "Compressor",
    "Forklift",
    "Scaffolding",
    "Welding Machine",
    "Heat Exchanger",
    "Centrifugal Separator",
]

# Regex to detect asset tags such as CP-12, HP-100, EP-7, PG-5, PW-3000, BL-40
ASSET_TAG_REGEX = re.compile(r"\b([A-Z]{1,4}-\d{1,5})\b", re.IGNORECASE)

EQUIPMENT_CLASS_ALIASES = {
    "chemical pump": "Chemical Pump",
    "pump": "Chemical Pump",
    "dosing pump": "Chemical Pump",
    "hydraulic press": "Hydraulic Press",
    "press": "Hydraulic Press",
    "electrical panel": "Electrical Panel",
    "panel": "Electrical Panel",
    "switchboard": "Electrical Panel",
    "mcc": "Electrical Panel",
    "portable generator": "Portable Generator",
    "generator": "Portable Generator",
    "genset": "Portable Generator",
    "step ladder": "Step Ladder",
    "ladder": "Step Ladder",
    "extension ladder": "Extension Ladder",
    "hand truck": "Hand Truck",
    "dolly": "Hand Truck",
    "trolley": "Hand Truck",
    "angle grinder": "Angle Grinder",
    "grinder": "Angle Grinder",
    "disc cutter": "Angle Grinder",
    "pressure washer": "Pressure Washer",
    "hydrojet": "Pressure Washer",
    "power washer": "Pressure Washer",
    "compressed air line": "Compressed Air Line",
    "air line": "Compressed Air Line",
    "pneumatic hose": "Compressed Air Line",
    "boom lift mewp": "Boom Lift / MEWP",
    "boom lift": "Boom Lift / MEWP",
    "mewp": "Boom Lift / MEWP",
    "cherry picker": "Boom Lift / MEWP",
    "manlift": "Boom Lift / MEWP",
    "scissor lift": "Boom Lift / MEWP",
    "crane hoist": "Crane / Hoist",
    "crane": "Crane / Hoist",
    "overhead crane": "Crane / Hoist",
    "hoist": "Crane / Hoist",
    "winch": "Crane / Hoist",
    "storage tank": "Storage Tank",
    "tank": "Storage Tank",
    "pressure vessel": "Pressure Vessel",
    "vessel": "Pressure Vessel",
    "separator": "Centrifugal Separator",
    "centrifugal separator": "Centrifugal Separator",
    "compressor": "Compressor",
    "forklift": "Forklift",
    "fork lift": "Forklift",
    "scaffolding": "Scaffolding",
    "scaffold": "Scaffolding",
    "welding machine": "Welding Machine",
    "welder": "Welding Machine",
    "heat exchanger": "Heat Exchanger",
}


# 5. Energy Source Taxonomy (Matches Incident.EnergyType choices)
CANONICAL_ENERGY_SOURCES = [
    "Gravity / Working at Height",
    "Electrical",
    "Mechanical Motion / Rotating Equipment",
    "Pressure / Stored Energy",
    "Chemical / Toxic / Flammable",
    "Thermal (Extreme Heat/Cold)",
    "Radiation",
    "Sound / Noise",
    "Motor Vehicle / Driving",
    "Other",
    "Unknown / Not Determined",
]

ENERGY_SOURCE_ALIASES = {
    # database choice keys
    "gravity_height": "Gravity / Working at Height",
    "gravity height": "Gravity / Working at Height",
    "gravity": "Gravity / Working at Height",
    "height": "Gravity / Working at Height",
    "fall": "Gravity / Working at Height",
    "electrical": "Electrical",
    "electric": "Electrical",
    "high voltage": "Electrical",
    "arc flash": "Electrical",
    "mechanical_motion": "Mechanical Motion / Rotating Equipment",
    "mechanical motion": "Mechanical Motion / Rotating Equipment",
    "mechanical": "Mechanical Motion / Rotating Equipment",
    "rotating equipment": "Mechanical Motion / Rotating Equipment",
    "pinch point": "Mechanical Motion / Rotating Equipment",
    "pressure": "Pressure / Stored Energy",
    "stored energy": "Pressure / Stored Energy",
    "high pressure": "Pressure / Stored Energy",
    "hydraulic": "Pressure / Stored Energy",
    "pneumatic": "Pressure / Stored Energy",
    "chemical": "Chemical / Toxic / Flammable",
    "toxic": "Chemical / Toxic / Flammable",
    "flammable": "Chemical / Toxic / Flammable",
    "hydrocarbon": "Chemical / Toxic / Flammable",
    "h2s": "Chemical / Toxic / Flammable",
    "thermal": "Thermal (Extreme Heat/Cold)",
    "heat": "Thermal (Extreme Heat/Cold)",
    "cold": "Thermal (Extreme Heat/Cold)",
    "hot surface": "Thermal (Extreme Heat/Cold)",
    "radiation": "Radiation",
    "sound": "Sound / Noise",
    "noise": "Sound / Noise",
    "motor_vehicle": "Motor Vehicle / Driving",
    "motor vehicle": "Motor Vehicle / Driving",
    "driving": "Motor Vehicle / Driving",
    "vehicle": "Motor Vehicle / Driving",
    "other": "Other",
    "unknown": "Unknown / Not Determined",
}


# 6. Barrier / Control Terminology
CANONICAL_CONTROL_TYPES = [
    "LOTO / Energy Isolation (Direct)",
    "Machine Guarding / Interlocks (Direct)",
    "Physical Barrier / Exclusion Zone (Direct)",
    "Fall Protection / Harness / Railing (Direct)",
    "Permit-Based Isolation / Hot Work Control (Direct)",
    "Ventilation / Atmospheric Monitoring (Direct)",
    "Training / Competency (Indirect)",
    "Signage / Warnings (Indirect)",
    "Personal Protective Equipment (Indirect)",
    "Rules / Safe Working Procedures (Indirect)",
    "Supervision / Experience (Indirect)",
    "Other Control",
    "Unknown / Not Determined",
]

CONTROL_TYPE_ALIASES = {
    "loto_isolation": "LOTO / Energy Isolation (Direct)",
    "loto isolation": "LOTO / Energy Isolation (Direct)",
    "loto": "LOTO / Energy Isolation (Direct)",
    "lockout tagout": "LOTO / Energy Isolation (Direct)",
    "isolation": "LOTO / Energy Isolation (Direct)",
    "machine_guarding": "Machine Guarding / Interlocks (Direct)",
    "machine guarding": "Machine Guarding / Interlocks (Direct)",
    "guard": "Machine Guarding / Interlocks (Direct)",
    "guarding": "Machine Guarding / Interlocks (Direct)",
    "interlock": "Machine Guarding / Interlocks (Direct)",
    "physical_barrier": "Physical Barrier / Exclusion Zone (Direct)",
    "physical barrier": "Physical Barrier / Exclusion Zone (Direct)",
    "barrier": "Physical Barrier / Exclusion Zone (Direct)",
    "barricade": "Physical Barrier / Exclusion Zone (Direct)",
    "exclusion zone": "Physical Barrier / Exclusion Zone (Direct)",
    "fall_protection": "Fall Protection / Harness / Railing (Direct)",
    "fall protection": "Fall Protection / Harness / Railing (Direct)",
    "harness": "Fall Protection / Harness / Railing (Direct)",
    "lifeline": "Fall Protection / Harness / Railing (Direct)",
    "railing": "Fall Protection / Harness / Railing (Direct)",
    "permit_isolation": "Permit-Based Isolation / Hot Work Control (Direct)",
    "permit isolation": "Permit-Based Isolation / Hot Work Control (Direct)",
    "permit to work": "Permit-Based Isolation / Hot Work Control (Direct)",
    "ptw": "Permit-Based Isolation / Hot Work Control (Direct)",
    "ventilation_monitoring": "Ventilation / Atmospheric Monitoring (Direct)",
    "ventilation monitoring": "Ventilation / Atmospheric Monitoring (Direct)",
    "gas testing": "Ventilation / Atmospheric Monitoring (Direct)",
    "gas detection": "Ventilation / Atmospheric Monitoring (Direct)",
    "training": "Training / Competency (Indirect)",
    "competency": "Training / Competency (Indirect)",
    "signage": "Signage / Warnings (Indirect)",
    "warning sign": "Signage / Warnings (Indirect)",
    "ppe": "Personal Protective Equipment (Indirect)",
    "personal protective equipment": "Personal Protective Equipment (Indirect)",
    "safety glasses": "Personal Protective Equipment (Indirect)",
    "rules_procedures": "Rules / Safe Working Procedures (Indirect)",
    "rules procedures": "Rules / Safe Working Procedures (Indirect)",
    "sop": "Rules / Safe Working Procedures (Indirect)",
    "supervision": "Supervision / Experience (Indirect)",
    "other": "Other Control",
    "unknown": "Unknown / Not Determined",
}

CANONICAL_CONTROL_CONDITIONS = [
    "Effective / Held",
    "Failed",
    "Absent / Not Implemented",
    "Bypassed / Defeated",
    "Unknown / Not Determined",
]

CONTROL_CONDITION_ALIASES = {
    "effective": "Effective / Held",
    "held": "Effective / Held",
    "prevented": "Effective / Held",
    "intact": "Effective / Held",
    "failed": "Failed",
    "failure": "Failed",
    "broke": "Failed",
    "malfunctioned": "Failed",
    "inadequate": "Failed",
    "absent": "Absent / Not Implemented",
    "missing": "Absent / Not Implemented",
    "not implemented": "Absent / Not Implemented",
    "none": "Absent / Not Implemented",
    "bypassed": "Bypassed / Defeated",
    "defeated": "Bypassed / Defeated",
    "overridden": "Bypassed / Defeated",
    "disabled": "Bypassed / Defeated",
    "unknown": "Unknown / Not Determined",
}


# 7. IOGP Life-Saving Rules Taxonomy (Official 9 Rules)
CANONICAL_IOGP_RULES = [
    "Bypassing Safety Controls",
    "Confined Space",
    "Driving",
    "Energy Isolation",
    "Hot Work",
    "Line of Fire",
    "Safe Mechanical Lifting",
    "Work Authorization",
    "Working at Height",
]

IOGP_RULE_ALIASES = {
    "bypassing safety controls": "Bypassing Safety Controls",
    "bypassing controls": "Bypassing Safety Controls",
    "bypass controls": "Bypassing Safety Controls",
    "bypassing": "Bypassing Safety Controls",
    "confined space": "Confined Space",
    "confined spaces": "Confined Space",
    "confined space entry": "Confined Space",
    "driving": "Driving",
    "safe driving": "Driving",
    "energy isolation": "Energy Isolation",
    "isolation": "Energy Isolation",
    "loto": "Energy Isolation",
    "lockout tagout": "Energy Isolation",
    "hot work": "Hot Work",
    "hotwork": "Hot Work",
    "line of fire": "Line of Fire",
    "line-of-fire": "Line of Fire",
    "struck by": "Line of Fire",
    "safe mechanical lifting": "Safe Mechanical Lifting",
    "mechanical lifting": "Safe Mechanical Lifting",
    "lifting": "Safe Mechanical Lifting",
    "safe lifting": "Safe Mechanical Lifting",
    "work authorization": "Work Authorization",
    "work permit": "Work Authorization",
    "permit to work": "Work Authorization",
    "ptw": "Work Authorization",
    "working at height": "Working at Height",
    "work at height": "Working at Height",
    "height": "Working at Height",
    "fall protection": "Working at Height",
}


# 8. Canonical Energy Hazard Families (15 Canonical Families per IOGP / Energy Wheel)
CANONICAL_HAZARDS = [
    "Working at Height",
    "Suspended Loads / Mechanical Lifting",
    "Line of Fire",
    "Pressure / Stored Energy Release",
    "Electrical Energy / Arc Flash",
    "Vehicle & Mobile Equipment",
    "Rotating Equipment / Mechanical In-Running Nips",
    "Hot Work & Ignition Sources",
    "Confined Space / Engulfment",
    "Hydrocarbon & Flammable Chemical Release",
    "Toxic & Asphyxiant Atmosphere",
    "Thermal Energy (Extreme Heat / Cryogenic)",
    "Stored Mechanical Energy (Springs / Tension)",
    "Excavation & Ground Collapse",
    "Dropped Objects (Dynamic Gravity Impact)",
]

HAZARD_ALIASES = {
    "working at height": "Working at Height",
    "work at height": "Working at Height",
    "fall from height": "Working at Height",
    "fall from elevation": "Working at Height",
    "gravity": "Working at Height",
    "suspended loads": "Suspended Loads / Mechanical Lifting",
    "crane lift hazard": "Suspended Loads / Mechanical Lifting",
    "rigging failure": "Suspended Loads / Mechanical Lifting",
    "suspended load": "Suspended Loads / Mechanical Lifting",
    "line of fire": "Line of Fire",
    "line-of-fire": "Line of Fire",
    "struck by moving object": "Line of Fire",
    "struck by": "Line of Fire",
    "pressure release": "Pressure / Stored Energy Release",
    "pressurized line": "Pressure / Stored Energy Release",
    "high pressure release": "Pressure / Stored Energy Release",
    "overpressurization": "Pressure / Stored Energy Release",
    "uncontrolled pressure release": "Pressure / Stored Energy Release",
    "pressure stored": "Pressure / Stored Energy Release",
    "electrical hazard": "Electrical Energy / Arc Flash",
    "arc flash": "Electrical Energy / Arc Flash",
    "high voltage": "Electrical Energy / Arc Flash",
    "electrocution hazard": "Electrical Energy / Arc Flash",
    "electrical": "Electrical Energy / Arc Flash",
    "vehicle hazard": "Vehicle & Mobile Equipment",
    "mobile equipment": "Vehicle & Mobile Equipment",
    "vehicle impact": "Vehicle & Mobile Equipment",
    "forklift hazard": "Vehicle & Mobile Equipment",
    "motor vehicle": "Vehicle & Mobile Equipment",
    "rotating equipment": "Rotating Equipment / Mechanical In-Running Nips",
    "in running nips": "Rotating Equipment / Mechanical In-Running Nips",
    "nip point": "Rotating Equipment / Mechanical In-Running Nips",
    "entanglement": "Rotating Equipment / Mechanical In-Running Nips",
    "mechanical motion": "Rotating Equipment / Mechanical In-Running Nips",
    "hot work hazard": "Hot Work & Ignition Sources",
    "ignition source": "Hot Work & Ignition Sources",
    "sparks near flammable": "Hot Work & Ignition Sources",
    "hot work ignition": "Hot Work & Ignition Sources",
    "confined space": "Confined Space / Engulfment",
    "confined space hazard": "Confined Space / Engulfment",
    "engulfment": "Confined Space / Engulfment",
    "hydrocarbon release": "Hydrocarbon & Flammable Chemical Release",
    "gas leak": "Hydrocarbon & Flammable Chemical Release",
    "fuel spill": "Hydrocarbon & Flammable Chemical Release",
    "flammable release": "Hydrocarbon & Flammable Chemical Release",
    "chemical flammable": "Hydrocarbon & Flammable Chemical Release",
    "toxic atmosphere": "Toxic & Asphyxiant Atmosphere",
    "h2s exposure": "Toxic & Asphyxiant Atmosphere",
    "h2s gas": "Toxic & Asphyxiant Atmosphere",
    "asphyxiation": "Toxic & Asphyxiant Atmosphere",
    "thermal energy": "Thermal Energy (Extreme Heat / Cryogenic)",
    "extreme heat": "Thermal Energy (Extreme Heat / Cryogenic)",
    "steam leak": "Thermal Energy (Extreme Heat / Cryogenic)",
    "cryogenic exposure": "Thermal Energy (Extreme Heat / Cryogenic)",
    "stored mechanical energy": "Stored Mechanical Energy (Springs / Tension)",
    "spring tension": "Stored Mechanical Energy (Springs / Tension)",
    "hydraulic recoil": "Stored Mechanical Energy (Springs / Tension)",
    "excavation collapse": "Excavation & Ground Collapse",
    "trench collapse": "Excavation & Ground Collapse",
    "cave in": "Excavation & Ground Collapse",
    "dropped object": "Dropped Objects (Dynamic Gravity Impact)",
    "dropped objects": "Dropped Objects (Dynamic Gravity Impact)",
    "falling object": "Dropped Objects (Dynamic Gravity Impact)",
    "gravity dropped object": "Dropped Objects (Dynamic Gravity Impact)",
    "kinetic vehicle": "Vehicle & Mobile Equipment",
    "kinetic moving object vehicle": "Vehicle & Mobile Equipment",
    "kinetic": "Vehicle & Mobile Equipment",
    "mechanical rotating equipment": "Rotating Equipment / Mechanical In-Running Nips",
    "mechanical": "Rotating Equipment / Mechanical In-Running Nips",
    "pressure": "Pressure / Stored Energy Release",
    "hydrocarbon": "Hydrocarbon & Flammable Chemical Release",
    "hydrocarbon flammable atmosphere": "Hydrocarbon & Flammable Chemical Release",
    "chemical toxic h2s": "Toxic & Asphyxiant Atmosphere",
    "atmospheric oxygen deficiency": "Confined Space / Engulfment",
    "thermal": "Thermal Energy (Extreme Heat / Cryogenic)",
}


# 9. Canonical Upstream / Midstream / Downstream Operations
CANONICAL_OPERATIONS = [
    "Drilling Operations",
    "Workover & Well Servicing",
    "Production Operations",
    "Refinery Process Operations",
    "Pipeline Transportation",
    "Maintenance & Overhaul",
    "Construction & Commissioning",
    "Logistics & Marine Transfer",
    "Facility Shutdown / Turnaround",
]

OPERATION_ALIASES = {
    "drilling": "Drilling Operations",
    "drilling ops": "Drilling Operations",
    "drilling operations": "Drilling Operations",
    "workover": "Workover & Well Servicing",
    "well servicing": "Workover & Well Servicing",
    "well intervention": "Workover & Well Servicing",
    "production": "Production Operations",
    "production operations": "Production Operations",
    "oil production": "Production Operations",
    "gas production": "Production Operations",
    "refining": "Refinery Process Operations",
    "refinery": "Refinery Process Operations",
    "refinery operations": "Refinery Process Operations",
    "pipeline": "Pipeline Transportation",
    "pipeline operations": "Pipeline Transportation",
    "pipeline transportation": "Pipeline Transportation",
    "maintenance": "Maintenance & Overhaul",
    "mechanical maintenance": "Maintenance & Overhaul",
    "overhaul": "Maintenance & Overhaul",
    "construction": "Construction & Commissioning",
    "commissioning": "Construction & Commissioning",
    "marine transfer": "Logistics & Marine Transfer",
    "logistics": "Logistics & Marine Transfer",
    "shutdown": "Facility Shutdown / Turnaround",
    "turnaround": "Facility Shutdown / Turnaround",
}


# Registry of taxonomies and aliases by entity_type
TAXONOMY_REGISTRY: Dict[str, Tuple[List[str], Dict[str, str]]] = {
    "site": (CANONICAL_SITES, SITE_ALIASES),
    "operational_site": (CANONICAL_OPERATIONAL_SITES, OPERATIONAL_SITE_ALIASES),
    "location": (CANONICAL_LOCATIONS, LOCATION_ALIASES),
    "department": (CANONICAL_DEPARTMENTS, DEPARTMENT_ALIASES),
    "activity": (CANONICAL_ACTIVITIES, ACTIVITY_ALIASES),
    "job_task": (CANONICAL_ACTIVITIES, ACTIVITY_ALIASES),
    "equipment": (CANONICAL_EQUIPMENT_CLASSES, EQUIPMENT_CLASS_ALIASES),
    "asset": (CANONICAL_EQUIPMENT_CLASSES, EQUIPMENT_CLASS_ALIASES),
    "energy_source": (CANONICAL_ENERGY_SOURCES, ENERGY_SOURCE_ALIASES),
    "hazard": (CANONICAL_HAZARDS, HAZARD_ALIASES),
    "operation": (CANONICAL_OPERATIONS, OPERATION_ALIASES),
    "control_type": (CANONICAL_CONTROL_TYPES, CONTROL_TYPE_ALIASES),
    "control": (CANONICAL_CONTROL_TYPES, CONTROL_TYPE_ALIASES),
    "barrier": (CANONICAL_CONTROL_TYPES, CONTROL_TYPE_ALIASES),
    "control_condition": (CANONICAL_CONTROL_CONDITIONS, CONTROL_CONDITION_ALIASES),
    "iogp_rule": (CANONICAL_IOGP_RULES, IOGP_RULE_ALIASES),
}


# ── Core Normalization Engine ─────────────────────────────────────────────────

@functools.lru_cache(maxsize=8192)
def _normalize_entity_cached(
    raw_value: Optional[str],
    entity_type: str,
    fuzzy_threshold: float = 0.88,
    source_field: str = "",
) -> NormalizedEntity:
    """
    Internal cached implementation of the entity normalizer.
    Takes pure immutable types to enable high-performance LRU caching.
    """
    norm_entity_type = entity_type.lower()
    if norm_entity_type not in TAXONOMY_REGISTRY:
        raise ValueError(
            f"Unsupported entity_type '{entity_type}'. Supported types: {list(TAXONOMY_REGISTRY.keys())}"
        )

    # 1. Check for missing / empty value
    if raw_value is None:
        return NormalizedEntity(
            raw_value=None,
            canonical_value="UNKNOWN" if norm_entity_type in ("site", "operational_site") else "",
            entity_type=norm_entity_type,
            method=NormalizationMethod.UNKNOWN,
            status=NormalizationStatus.UNKNOWN,
            confidence=0.0,
            provenance=NORMALIZATION_VERSION,
            source_field=source_field,
        )

    cleaned_raw = sanitize_string(raw_value)
    if not cleaned_raw:
        return NormalizedEntity(
            raw_value=raw_value,
            canonical_value="UNKNOWN" if norm_entity_type in ("site", "operational_site") else "",
            entity_type=norm_entity_type,
            method=NormalizationMethod.UNKNOWN,
            status=NormalizationStatus.UNKNOWN,
            confidence=0.0,
            provenance=NORMALIZATION_VERSION,
            source_field=source_field,
        )

    lookup_key = normalize_lookup_key(cleaned_raw)

    # Explicit unknown / missing marker handling
    if lookup_key in ("unknown", "n a", "na", "none", "not available", "not applicable", "unspecified", "not specified", "null", "undefined", "generic area", "generic work area", "unassigned"):
        return NormalizedEntity(
            raw_value=raw_value,
            canonical_value="UNKNOWN" if norm_entity_type in ("site", "operational_site") else "",
            entity_type=norm_entity_type,
            method=NormalizationMethod.UNKNOWN,
            status=NormalizationStatus.UNKNOWN,
            confidence=0.0,
            provenance=NORMALIZATION_VERSION,
            source_field=source_field,
        )

    canonical_list, alias_dict = TAXONOMY_REGISTRY[norm_entity_type]

    # Special handling for equipment: check for embedded asset tags
    metadata: Dict[str, Any] = {}
    if norm_entity_type in ("equipment", "asset"):
        tag_match = ASSET_TAG_REGEX.search(cleaned_raw)
        if tag_match:
            metadata["asset_tag"] = tag_match.group(1).upper()

    # 2. Check exact canonical match (case-insensitive)
    for canonical in canonical_list:
        if lookup_key == normalize_lookup_key(canonical):
            return NormalizedEntity(
                raw_value=raw_value,
                canonical_value=canonical,
                entity_type=norm_entity_type,
                method=NormalizationMethod.NORMALIZED,
                status=NormalizationStatus.CANONICAL,
                confidence=1.0,
                provenance=NORMALIZATION_VERSION,
                source_field=source_field,
                metadata=metadata,
            )

    # 3. Check exact alias table match
    if lookup_key in alias_dict:
        canonical_target = alias_dict[lookup_key]
        return NormalizedEntity(
            raw_value=raw_value,
            canonical_value=canonical_target,
            entity_type=norm_entity_type,
            method=NormalizationMethod.EXACT_ALIAS,
            status=NormalizationStatus.MAPPED,
            confidence=1.0,
            alias_matched=lookup_key,
            provenance=NORMALIZATION_VERSION,
            source_field=source_field,
            metadata=metadata,
        )

    # 3b. Prefix/containment check for Equipment classes
    # (e.g. "Chemical Pump CP-12" -> "Chemical Pump", "Boom Lift BL-40" -> "Boom Lift / MEWP")
    if norm_entity_type in ("equipment", "asset"):
        candidates = []
        for eq_class in canonical_list:
            candidates.append((normalize_lookup_key(eq_class), eq_class))
        for alias_k, canonical_target in alias_dict.items():
            candidates.append((alias_k, canonical_target))
        # Sort by candidate length descending so more specific terms match first
        candidates.sort(key=lambda x: len(x[0]), reverse=True)

        for candidate_key, canonical_target in candidates:
            # Word-bounded containment check
            pattern = rf"\b{re.escape(candidate_key)}\b"
            if re.search(pattern, lookup_key):
                return NormalizedEntity(
                    raw_value=raw_value,
                    canonical_value=canonical_target,
                    entity_type=norm_entity_type,
                    method=NormalizationMethod.EXACT_ALIAS,
                    status=NormalizationStatus.MAPPED,
                    confidence=0.98,
                    alias_matched=candidate_key,
                    provenance=NORMALIZATION_VERSION,
                    source_field=source_field,
                    metadata=metadata,
                )

    # 4. Conservative Bounded Fuzzy Matching & Ambiguity Check
    # Only attempted if the normalized string is meaningful (length >= 4)
    # and strictly against the explicit canonical dictionary.
    # Never silently marks fuzzy matches as canonical/mapped.
    if len(lookup_key) >= 4:
        scored_candidates: List[Tuple[float, str]] = []
        for canonical in canonical_list:
            canonical_norm = normalize_lookup_key(canonical)
            ratio = difflib.SequenceMatcher(None, lookup_key, canonical_norm).ratio()
            if ratio >= fuzzy_threshold:
                scored_candidates.append((ratio, canonical))

        if scored_candidates:
            scored_candidates.sort(key=lambda x: x[0], reverse=True)
            top_score, top_match = scored_candidates[0]

            # Ambiguity check: if multiple candidates are within 0.03 of each other
            close_candidates = [c for s, c in scored_candidates if abs(s - top_score) <= 0.03]
            if len(close_candidates) > 1:
                # Ambiguous: retain raw value, mark as UNCERTAIN identity to prevent false mergers
                metadata["ambiguous_candidates"] = close_candidates
                return NormalizedEntity(
                    raw_value=raw_value,
                    canonical_value=cleaned_raw,
                    entity_type=norm_entity_type,
                    method=NormalizationMethod.IDENTITY,
                    status=NormalizationStatus.UNCERTAIN,
                    confidence=round(top_score, 2),
                    provenance=NORMALIZATION_VERSION,
                    source_field=source_field,
                    metadata=metadata,
                )

            # Explicit bounded fuzzy suggestion (never silent authoritative mapped)
            return NormalizedEntity(
                raw_value=raw_value,
                canonical_value=top_match,
                entity_type=norm_entity_type,
                method=NormalizationMethod.BOUNDED_FUZZY,
                status=NormalizationStatus.SUGGESTED,
                confidence=round(top_score, 2),
                alias_matched=f"fuzzy:{top_match} ({top_score:.2f})",
                provenance=NORMALIZATION_VERSION,
                source_field=source_field,
                metadata=metadata,
            )

    # 5. Fallback Identity Mapping
    # Retain the sanitized raw value, marked UNCERTAIN with confidence 0.5.
    # We DO NOT merge with any arbitrary candidate.
    return NormalizedEntity(
        raw_value=raw_value,
        canonical_value=cleaned_raw,
        entity_type=norm_entity_type,
        method=NormalizationMethod.IDENTITY,
        status=NormalizationStatus.UNCERTAIN,
        confidence=0.5,
        provenance=NORMALIZATION_VERSION,
        source_field=source_field,
        metadata=metadata,
    )


def get_normalization_version() -> str:
    """Returns the active canonical taxonomy version."""
    return NORMALIZATION_VERSION


def normalize_entity(
    raw_value: Optional[str],
    entity_type: str,
    fuzzy_threshold: float = 0.88,
    source_field: str = "",
) -> NormalizedEntity:
    """
    Public entrypoint for safety entity normalization.
    """
    return _normalize_entity_cached(raw_value, entity_type, fuzzy_threshold, source_field)


# ── Specialized Normalization Helpers ─────────────────────────────────────────

def normalize_site(raw_value: Optional[str], source_field: str = "site") -> NormalizedEntity:
    return normalize_entity(raw_value, "site", source_field=source_field)

def normalize_operational_site(raw_value: Optional[str], source_field: str = "operational_site") -> NormalizedEntity:
    return normalize_entity(raw_value, "operational_site", source_field=source_field)

def normalize_location(raw_value: Optional[str], source_field: str = "location") -> NormalizedEntity:
    return normalize_entity(raw_value, "location", source_field=source_field)

def normalize_department(raw_value: Optional[str], source_field: str = "department") -> NormalizedEntity:
    return normalize_entity(raw_value, "department", source_field=source_field)

def normalize_activity(raw_value: Optional[str], source_field: str = "activity") -> NormalizedEntity:
    return normalize_entity(raw_value, "activity", source_field=source_field)

def normalize_job_task(raw_value: Optional[str], source_field: str = "job_task") -> NormalizedEntity:
    return normalize_entity(raw_value, "job_task", source_field=source_field)

def normalize_equipment(raw_value: Optional[str], source_field: str = "equipment") -> NormalizedEntity:
    return normalize_entity(raw_value, "equipment", source_field=source_field)

def normalize_asset(raw_value: Optional[str], source_field: str = "asset") -> NormalizedEntity:
    return normalize_entity(raw_value, "asset", source_field=source_field)

def normalize_energy_source(raw_value: Optional[str], source_field: str = "energy_source") -> NormalizedEntity:
    return normalize_entity(raw_value, "energy_source", source_field=source_field)

def normalize_hazard(raw_value: Optional[str], source_field: str = "hazard") -> NormalizedEntity:
    return normalize_entity(raw_value, "hazard", source_field=source_field)

def normalize_operation(raw_value: Optional[str], source_field: str = "operation") -> NormalizedEntity:
    return normalize_entity(raw_value, "operation", source_field=source_field)

def normalize_control_type(raw_value: Optional[str], source_field: str = "control_type") -> NormalizedEntity:
    return normalize_entity(raw_value, "control_type", source_field=source_field)

def normalize_control(raw_value: Optional[str], source_field: str = "control") -> NormalizedEntity:
    return normalize_entity(raw_value, "control_type", source_field=source_field)

def normalize_barrier(raw_value: Optional[str], source_field: str = "barrier") -> NormalizedEntity:
    return normalize_entity(raw_value, "barrier", source_field=source_field)

def normalize_control_condition(raw_value: Optional[str], source_field: str = "control_condition") -> NormalizedEntity:
    return normalize_entity(raw_value, "control_condition", source_field=source_field)

def normalize_iogp_rule(raw_value: Optional[str], source_field: str = "iogp_rule") -> NormalizedEntity:
    return normalize_entity(raw_value, "iogp_rule", source_field=source_field)


# ── Operational Site Resolution ───────────────────────────────────────────────

def resolve_operational_site(incident: Any) -> NormalizedEntity:
    """
    Determines the canonical operational site for an incident record.
    Checks in priority order:
    1. raw_row.region_field (ground-truth OIL region, e.g. 'Duliajan', 'Numaligarh')
    2. raw_row.site_installation
    3. incident.location (e.g. 'Numaligarh Refinery - Tank Farm', 'CTF Duliajan')
    4. incident.department (if it references a recognized site)

    If a recognized site is found, returns the canonical operational site (e.g. DULIAJAN).
    If no recognized operational site is found, returns an UNKNOWN entity.
    Never guesses or creates false mergers.
    """
    raw_row = getattr(incident, "raw_row", None) or {}
    if not isinstance(raw_row, dict):
        raw_row = {}

    # 1. Direct region_field from raw_row
    region_raw = raw_row.get("region_field")
    if region_raw:
        ent = normalize_operational_site(str(region_raw), source_field="raw_row.region_field")
        if ent.is_normalized:
            return ent

    # 2. site_installation from raw_row
    installation_raw = raw_row.get("site_installation")
    if installation_raw:
        ent = normalize_operational_site(str(installation_raw), source_field="raw_row.site_installation")
        if ent.is_normalized:
            return ent

    # 3. incident.location
    location_raw = getattr(incident, "location", None)
    if location_raw:
        ent = normalize_operational_site(str(location_raw), source_field="incident.location")
        if ent.is_normalized:
            return ent

    # 4. incident.department (rarely contains site name)
    dept_raw = getattr(incident, "department", None)
    if dept_raw:
        ent = normalize_operational_site(str(dept_raw), source_field="incident.department")
        if ent.is_normalized:
            return ent

    # None found: preserve UNKNOWN
    return NormalizedEntity(
        raw_value=location_raw or region_raw or None,
        canonical_value="UNKNOWN",
        entity_type="operational_site",
        method=NormalizationMethod.UNKNOWN,
        status=NormalizationStatus.UNKNOWN,
        confidence=0.0,
        source_field="incident.location",
        provenance=NORMALIZATION_VERSION,
    )


# ── Incident Aggregate Normalizer ─────────────────────────────────────────────

def normalize_incident_entities(incident: Any, include_operational_site: bool = False) -> Dict[str, NormalizedEntity]:
    """
    Normalizes all structured safety entities for a given incident instance,
    preserving all raw values and providing canonical representations.

    Returns:
        Dict mapping field names to their respective NormalizedEntity instances:
        - 'site': location normalized
        - 'department': department normalized
        - 'activity': job_task normalized
        - 'equipment': equipment_involved normalized
        - 'energy_source': energy_type normalized
        - 'control_type': control_type normalized
        - 'control_condition': control_condition normalized
        - Optional 'operational_site': resolved operational site
    """
    entities = {
        "site": normalize_location(getattr(incident, "location", None), source_field="incident.location"),
        "department": normalize_department(getattr(incident, "department", None), source_field="incident.department"),
        "activity": normalize_job_task(getattr(incident, "job_task", None), source_field="incident.job_task"),
        "equipment": normalize_equipment(getattr(incident, "equipment_involved", None), source_field="incident.equipment_involved"),
        "energy_source": normalize_energy_source(getattr(incident, "energy_type", None), source_field="incident.energy_type"),
        "control_type": normalize_control_type(getattr(incident, "control_type", None), source_field="incident.control_type"),
        "control_condition": normalize_control_condition(getattr(incident, "control_condition", None), source_field="incident.control_condition"),
    }
    if include_operational_site:
        entities["operational_site"] = resolve_operational_site(incident)
    return entities

