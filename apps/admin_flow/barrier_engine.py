"""
PSIF Platform — Admin Flow Barrier Intelligence Engine.
apps/admin_flow/barrier_engine.py

Architectural Principle:
A BARRIER is the actual protective measure, safeguard, control, or intervention described
in the incident that prevents, stops, absorbs, mitigates, or limits a hazardous event
from progressing to a more severe consequence.

IOGP Life-Saving Rules and PSIF classifications are separate, independent dimensions:
- HAZARD: Physical/operational energy source (e.g. Gravity, Stored Pressure)
- BARRIER: Protective measure (e.g. Safety Harness, Isolation Valve, Pedestrian Segregation)
- BARRIER STATE: Performance condition (e.g. EFFECTIVE, FAILED, ABSENT, NOT_VERIFIED)
- IOGP RULE: Associated safety rule domain (e.g. Working at Height, Energy Isolation, Driving)
- PSIF RESULT: Authoritative precursor evaluation from canonical PSIF reasoning engine
"""
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Canonical Barrier Categories (28 Categories) ──────────────────────────────

class BarrierCategory:
    FALL_ARREST_SYSTEM = "FALL_ARREST_SYSTEM"
    GUARDRAIL = "GUARDRAIL"
    SAFETY_NET = "SAFETY_NET"
    EXCLUSION_BARRIER = "EXCLUSION_BARRIER"
    MACHINE_GUARD = "MACHINE_GUARD"
    INTERLOCK = "INTERLOCK"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"
    ISOLATION_VALVE = "ISOLATION_VALVE"
    LOCKOUT_TAGOUT = "LOCKOUT_TAGOUT"
    ZERO_ENERGY_VERIFICATION = "ZERO_ENERGY_VERIFICATION"
    PRESSURE_RELIEF = "PRESSURE_RELIEF"
    GAS_DETECTION = "GAS_DETECTION"
    VENTILATION = "VENTILATION"
    FIRE_SUPPRESSION = "FIRE_SUPPRESSION"
    FIRE_WATCH = "FIRE_WATCH"
    CONTAINMENT = "CONTAINMENT"
    VEHICLE_PEDESTRIAN_SEGREGATION = "VEHICLE_PEDESTRIAN_SEGREGATION"
    SEAT_BELT = "SEAT_BELT"
    WHEEL_CHOCK = "WHEEL_CHOCK"
    PROTECTIVE_SHIELD = "PROTECTIVE_SHIELD"
    RIGGING_CONTROL = "RIGGING_CONTROL"
    LIFTING_EXCLUSION_ZONE = "LIFTING_EXCLUSION_ZONE"
    RESCUE_SYSTEM = "RESCUE_SYSTEM"
    STOP_WORK_INTERVENTION = "STOP_WORK_INTERVENTION"
    PPE_PROTECTIVE_BARRIER = "PPE_PROTECTIVE_BARRIER"
    OTHER_KNOWN_BARRIER = "OTHER_KNOWN_BARRIER"
    UNKNOWN = "UNKNOWN"


BARRIER_LABELS: Dict[str, str] = {
    BarrierCategory.FALL_ARREST_SYSTEM: "Safety Harness / Fall-Arrest System",
    BarrierCategory.GUARDRAIL: "Guardrail / Edge Protection",
    BarrierCategory.SAFETY_NET: "Safety Net / Catch Platform",
    BarrierCategory.EXCLUSION_BARRIER: "Physical Exclusion Barricade",
    BarrierCategory.MACHINE_GUARD: "Machine Guard / Equipment Shield",
    BarrierCategory.INTERLOCK: "Safety Interlock / Light Curtain",
    BarrierCategory.EMERGENCY_STOP: "Emergency Stop / Trip Wire",
    BarrierCategory.EMERGENCY_SHUTDOWN: "Emergency Shutdown System (ESD/ESDV)",
    BarrierCategory.ISOLATION_VALVE: "Isolation Valve / Positive Mechanical Blind",
    BarrierCategory.LOCKOUT_TAGOUT: "Lockout / Tagout (LOTO)",
    BarrierCategory.ZERO_ENERGY_VERIFICATION: "Zero-Energy Verification (Test-Before-Touch)",
    BarrierCategory.PRESSURE_RELIEF: "Pressure Relief Valve (PRV) / Rupture Disk",
    BarrierCategory.GAS_DETECTION: "Gas Detection / Atmospheric Monitoring",
    BarrierCategory.VENTILATION: "Mechanical Forced Air Ventilation",
    BarrierCategory.FIRE_SUPPRESSION: "Fire Suppression System / Auto-Deluge",
    BarrierCategory.FIRE_WATCH: "Dedicated Fire Watch & Extinguisher",
    BarrierCategory.CONTAINMENT: "Spill Containment / Bund / Drip Pan",
    BarrierCategory.VEHICLE_PEDESTRIAN_SEGREGATION: "Vehicle / Pedestrian Segregation Barrier",
    BarrierCategory.SEAT_BELT: "Seat Belt / Restraint Harness",
    BarrierCategory.WHEEL_CHOCK: "Wheel Chocks / Parking Brake",
    BarrierCategory.PROTECTIVE_SHIELD: "Protective Splash / Blast Shield",
    BarrierCategory.RIGGING_CONTROL: "Certified Rigging / Whip Check Safety Cable",
    BarrierCategory.LIFTING_EXCLUSION_ZONE: "Lifting Radius Exclusion Zone",
    BarrierCategory.RESCUE_SYSTEM: "Standby Rescue System / Retrieval Lifeline",
    BarrierCategory.STOP_WORK_INTERVENTION: "Stop-Work Authority Intervention",
    BarrierCategory.PPE_PROTECTIVE_BARRIER: "Task-Critical Protective Barrier PPE",
    BarrierCategory.OTHER_KNOWN_BARRIER: "Other Engineered Protective Measure",
    BarrierCategory.UNKNOWN: "No Established Protective Barrier",
}


# ── Canonical Barrier States ──────────────────────────────────────────────────

class BarrierState:
    EFFECTIVE = "EFFECTIVE"
    PARTIALLY_EFFECTIVE = "PARTIALLY_EFFECTIVE"
    FAILED = "FAILED"
    ABSENT = "ABSENT"
    BYPASSED = "BYPASSED"
    NOT_VERIFIED = "NOT_VERIFIED"
    INCORRECTLY_ASSUMED = "INCORRECTLY_ASSUMED"
    RESTORED_BEFORE_EXPOSURE = "RESTORED_BEFORE_EXPOSURE"
    RESTORED_AFTER_EXPOSURE = "RESTORED_AFTER_EXPOSURE"
    PLANNED_ONLY = "PLANNED_ONLY"
    UNKNOWN = "UNKNOWN"


DEFICIENT_BARRIER_STATES: Set[str] = {
    BarrierState.FAILED,
    BarrierState.ABSENT,
    BarrierState.BYPASSED,
    BarrierState.NOT_VERIFIED,
    BarrierState.INCORRECTLY_ASSUMED,
    BarrierState.PARTIALLY_EFFECTIVE,
}

EFFECTIVE_BARRIER_STATES: Set[str] = {
    BarrierState.EFFECTIVE,
    BarrierState.RESTORED_BEFORE_EXPOSURE,
}


# ── Canonical Barrier Roles ───────────────────────────────────────────────────

class BarrierRole:
    PREVENTIVE = "PREVENTIVE"
    DETECTIVE = "DETECTIVE"
    MITIGATIVE = "MITIGATIVE"
    RECOVERY_RESCUE = "RECOVERY_RESCUE"
    ADMINISTRATIVE_STOP_WORK = "ADMINISTRATIVE_STOP_WORK"


DEFAULT_BARRIER_ROLES: Dict[str, str] = {
    BarrierCategory.FALL_ARREST_SYSTEM: BarrierRole.RECOVERY_RESCUE,
    BarrierCategory.GUARDRAIL: BarrierRole.PREVENTIVE,
    BarrierCategory.SAFETY_NET: BarrierRole.RECOVERY_RESCUE,
    BarrierCategory.EXCLUSION_BARRIER: BarrierRole.PREVENTIVE,
    BarrierCategory.MACHINE_GUARD: BarrierRole.PREVENTIVE,
    BarrierCategory.INTERLOCK: BarrierRole.PREVENTIVE,
    BarrierCategory.EMERGENCY_STOP: BarrierRole.MITIGATIVE,
    BarrierCategory.EMERGENCY_SHUTDOWN: BarrierRole.MITIGATIVE,
    BarrierCategory.ISOLATION_VALVE: BarrierRole.PREVENTIVE,
    BarrierCategory.LOCKOUT_TAGOUT: BarrierRole.PREVENTIVE,
    BarrierCategory.ZERO_ENERGY_VERIFICATION: BarrierRole.DETECTIVE,
    BarrierCategory.PRESSURE_RELIEF: BarrierRole.MITIGATIVE,
    BarrierCategory.GAS_DETECTION: BarrierRole.DETECTIVE,
    BarrierCategory.VENTILATION: BarrierRole.MITIGATIVE,
    BarrierCategory.FIRE_SUPPRESSION: BarrierRole.MITIGATIVE,
    BarrierCategory.FIRE_WATCH: BarrierRole.DETECTIVE,
    BarrierCategory.CONTAINMENT: BarrierRole.MITIGATIVE,
    BarrierCategory.VEHICLE_PEDESTRIAN_SEGREGATION: BarrierRole.PREVENTIVE,
    BarrierCategory.SEAT_BELT: BarrierRole.MITIGATIVE,
    BarrierCategory.WHEEL_CHOCK: BarrierRole.PREVENTIVE,
    BarrierCategory.PROTECTIVE_SHIELD: BarrierRole.MITIGATIVE,
    BarrierCategory.RIGGING_CONTROL: BarrierRole.PREVENTIVE,
    BarrierCategory.LIFTING_EXCLUSION_ZONE: BarrierRole.PREVENTIVE,
    BarrierCategory.RESCUE_SYSTEM: BarrierRole.RECOVERY_RESCUE,
    BarrierCategory.STOP_WORK_INTERVENTION: BarrierRole.ADMINISTRATIVE_STOP_WORK,
    BarrierCategory.PPE_PROTECTIVE_BARRIER: BarrierRole.MITIGATIVE,
    BarrierCategory.OTHER_KNOWN_BARRIER: BarrierRole.PREVENTIVE,
    BarrierCategory.UNKNOWN: BarrierRole.PREVENTIVE,
}


# ── Canonical Barrier Observation Entity ──────────────────────────────────────

@dataclass
class BarrierObservation:
    """
    First-class canonical entity representing a concrete protective barrier
    observed within an incident report.
    """
    incident_id: str
    workspace: str
    barrier_category: str
    barrier_name: str
    barrier_state: str
    barrier_role: str
    is_effective: bool
    is_deficient: bool
    source_field: str
    evidence_span: str
    hazard: str = "Unknown Hazard"
    activity: str = "General Operations"
    location: str = "Unknown Location"
    iogp_rule: str = "None Associated"
    psif_state: str = "UNKNOWN"
    consequence_role: str = ""
    barrier_raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "workspace": self.workspace,
            "barrier_category": self.barrier_category,
            "barrier_name": self.barrier_name,
            "barrier_state": self.barrier_state,
            "barrier_role": self.barrier_role,
            "is_effective": self.is_effective,
            "is_deficient": self.is_deficient,
            "source_field": self.source_field,
            "evidence_span": self.evidence_span,
            "hazard": self.hazard,
            "activity": self.activity,
            "location": self.location,
            "iogp_rule": self.iogp_rule,
            "psif_state": self.psif_state,
            "consequence_role": self.consequence_role,
            "barrier_raw_text": self.barrier_raw_text,
        }


# ── Negative Context Filters ──────────────────────────────────────────────────

RE_STORAGE_ONLY = re.compile(
    r"\b(?:stored|kept|placed|left|located|stowed)\s+(?:in|inside|on|near|nearby|at)\s+(?:the\s+)?(?:truck|vehicle|van|cab|locker|cabinet|storeroom|toolbox|rack|shelf|trailer|box)\b|"
    r"\b(?:was\s+available\s+in\s+the\s+(?:vehicle|truck|storeroom|cabinet))\b",
    re.IGNORECASE
)

RE_RECOMMENDATION_ONLY = re.compile(
    r"\b(?:recommend(?:ed|s|ation)?(?:\s+to)?|should\s+(?:install|provide|fit|use|wear|ensure|implement)|"
    r"proposed\s+(?:barrier|control|guard|system)|action\s+item|lesson\s+learned)\b",
    re.IGNORECASE
)


# ── Semantic Barrier Extraction Definitions ───────────────────────────────────

BARRIER_EXTRACTION_RULES = [
    {
        "category": BarrierCategory.FALL_ARREST_SYSTEM,
        "triggers": [
            r"\b(?:safety\s+)?harness\b",
            r"\bfall[- ]arrest(?:\s+system)?\b",
            r"\b(?:self[- ]retracting\s+)?lifeline\b",
            r"\blanyard\b",
            r"\bSRL\b",
            r"\bfall\s+protection\s+system\b",
            r"\bdual[- ]tie[- ]off\b",
        ],
        "effective": [
            r"\b(?:harness\s+(?:caught|arrested|held|stopped|saved|supported)\s+(?:him|her|the\s+worker|them|person))\b",
            r"\b(?:helped\s+(?:him|her|them)\s+regain\s+balance)\b",
            r"\b(?:arrested\s+the\s+fall)\b",
            r"\b(?:fall\s+arrest\s+(?:system\s+)?(?:stopped|arrested|prevented|caught))\b",
            r"\b(?:lifeline\s+(?:engaged|arrested|stopped|held))\b",
            r"\b(?:tied\s+off\s+and\s+(?:prevented|stopped|held))\b",
        ],
        "deficient": [
            r"\b(?:was\s+not\s+(?:connected|tied\s+off|clipped|anchored|worn|attached))\b",
            r"\b(?:not\s+tied[- ]off|unclipped|unattached|detached)\b",
            r"\b(?:no\s+harness|without\s+(?:a\s+)?harness)\b",
            r"\b(?:harness\s+(?:\w+\s+)?(?:failed|snapped|broke|slipped|tore))\b",
            r"\b(?:lifeline\s+(?:failed|severed|broke|cut|snapped))\b",
            r"\b(?:lanyard\s+(?:severed|broke|unhooked|snapped|parted|failed))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.GUARDRAIL,
        "triggers": [
            r"\bguardrail\b",
            r"\bhandrail\b",
            r"\btoe\s*board\b",
            r"\bedge\s+protection\b",
            r"\bsafety\s+railing\b",
            r"\bscaffold\s+railing\b",
        ],
        "effective": [
            r"\b(?:guardrail\s+prevented\s+(?:the\s+worker\s+from\s+falling|fall|entry))\b",
            r"\b(?:handrail\s+(?:prevented|held|supported|stopped))\b",
            r"\b(?:edge\s+protection\s+(?:in\s+place|prevented))\b",
            r"\b(?:guardrail\s+(?:held|intact))\b",
        ],
        "deficient": [
            r"\b(?:no\s+guardrail(?:\s+was\s+installed)?)\b",
            r"\b(?:guardrail\s+(?:was\s+)?(?:missing|removed|damaged|broken|absent|collapsed))\b",
            r"\b(?:handrail\s+(?:missing|removed|broken|absent))\b",
            r"\b(?:without\s+(?:a\s+)?(?:guardrail|handrail|edge\s+protection))\b",
            r"\b(?:toe\s*board\s+(?:missing|absent))\b",
        ],
        "default_state": BarrierState.ABSENT,
    },
    {
        "category": BarrierCategory.SAFETY_NET,
        "triggers": [
            r"\bsafety\s+net\b",
            r"\bdebris\s+netting\b",
            r"\bcatch\s+platform\b",
        ],
        "effective": [
            r"\b(?:safety\s+net\s+(?:caught|arrested|stopped))\b",
            r"\b(?:fell\s+into\s+the\s+safety\s+net)\b",
        ],
        "deficient": [
            r"\b(?:safety\s+net\s+(?:failed|tore|missing|not\s+installed))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.EXCLUSION_BARRIER,
        "triggers": [
            r"\bexclusion\s+barrier\b",
            r"\bexclusion\s+zone\b",
            r"\bbarricad(?:e|ed|ing)\b",
            r"\bphysical\s+barrier\b",
            r"\bhard\s+barricading\b",
            r"\bdanger\s+zone\s+barrier\b",
            r"\bdrop\s+zone\s+barrier\b",
        ],
        "effective": [
            r"\b(?:controlled\s+within\s+the\s+barricaded\s+exclusion\s+zone)\b",
            r"\b(?:exclusion\s+zone\s+was\s+maintained)\b",
            r"\b(?:barricaded?\s+exclusion\s+zone)\b",
            r"\b(?:barrier\s+prevented\s+entry)\b",
            r"\b(?:area\s+was\s+barricaded)\b",
            r"\b(?:remained\s+outside\s+the\s+exclusion\s+zone)\b",
        ],
        "deficient": [
            r"\b(?:exclusion\s+zone\s+was\s+not\s+maintained)\b",
            r"\b(?:exclusion\s+barrier\s+was\s+not\s+maintained)\b",
            r"\b(?:barricad(?:e|ing)?\s+(?:was\s+)?(?:not\s+in\s+place|missing|absent|removed|inadequate|breached))\b",
            r"\b(?:entered\s+(?:the\s+)?(?:exclusion\s+zone|drop\s+zone|danger\s+area)\s+while)\b",
            r"\b(?:without\s+(?:an?\s+)?(?:exclusion\s+barrier|barricade))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.MACHINE_GUARD,
        "triggers": [
            r"\bmachine\s+guard\b",
            r"\bequipment\s+guard\b",
            r"\bsafety\s+guard\b",
            r"\bprotective\s+guard\b",
            r"\bguard\s+casing\b",
            r"\bcoupling\s+guard\b",
            r"\bbelt\s+guard\b",
            r"\bshaft\s+guard\b",
            r"\bphysical\s+guard\b",
            r"\boperating\s+machine\s+after\s+the\s+guard\b",
            r"\bguard\s+had\s+been\s+removed\b",
        ],
        "effective": [
            r"\b(?:guard\s+(?:prevented\s+contact|shielded|protected|in\s+place|intact))\b",
            r"\b(?:physical\s+guarding\s+prevented)\b",
        ],
        "deficient": [
            r"\b(?:guard\s+had\s+been\s+removed)\b",
            r"\b(?:guard\s+(?:was\s+)?(?:removed|missing|absent|detached|unbolted|open|damaged|defeated))\b",
            r"\b(?:unguarded\s+(?:shaft|machine|belt|equipment|rotating))\b",
            r"\b(?:without\s+(?:a\s+)?guard)\b",
            r"\b(?:guard\s+bypassed)\b",
        ],
        "default_state": BarrierState.ABSENT,
    },
    {
        "category": BarrierCategory.INTERLOCK,
        "triggers": [
            r"\binterlock(?:ed)?\b",
            r"\blight\s+curtain\b",
            r"\bsafety\s+switch\b",
            r"\bdoor\s+interlock\b",
        ],
        "effective": [
            r"\b(?:interlock\s+(?:stopped|tripped|prevented|activated))\b",
            r"\b(?:interlocked\s+door\s+prevented)\b",
        ],
        "deficient": [
            r"\b(?:interlock\s+(?:bypassed|defeated|failed|overridden|faulty|jumpered))\b",
            r"\b(?:without\s+interlock)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.EMERGENCY_STOP,
        "triggers": [
            r"\bemergency\s+stop\b",
            r"\be[- ]stop\b",
            r"\btrip[- ]wire\b",
            r"\bsafety\s+trip\b",
            r"\bkill[- ]switch\b",
        ],
        "effective": [
            r"\b(?:emergency\s+stop\s+(?:was\s+)?activated\s+before)\b",
            r"\b(?:activated\s+(?:the\s+)?emergency\s+stop)\b",
            r"\b(?:hit\s+(?:the\s+)?e[- ]stop)\b",
            r"\b(?:stopped\s+(?:the\s+machine|the\s+conveyor|motion)\s+before\s+contact)\b",
            r"\b(?:emergency\s+stop\s+(?:halted|tripped|stopped))\b",
        ],
        "deficient": [
            r"\b(?:emergency\s+stop\s+(?:failed|did\s+not\s+stop|unreachable|defective))\b",
            r"\b(?:e[- ]stop\s+(?:failed|inoperable))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.EMERGENCY_SHUTDOWN,
        "triggers": [
            r"\bemergency\s+shutdown\b",
            r"\bESDV\b",
            r"\bESD\b",
            r"\bauto[- ]shutdown\b",
            r"\bautomatic\s+trip\b",
        ],
        "effective": [
            r"\b(?:emergency\s+shutdown\s+(?:activated|closed|isolated|stopped\s+the\s+release))\b",
            r"\b(?:ESDV\s+(?:closed|tripped|isolated))\b",
            r"\b(?:emergency\s+isolation\s+valve\s+was\s+activated\s+and\s+stopped\s+the\s+flow)\b",
            r"\b(?:shutdown\s+system\s+(?:tripped|prevented|stopped))\b",
        ],
        "deficient": [
            r"\b(?:ESDV\s+(?:failed|leaked|did\s+not\s+close))\b",
            r"\b(?:emergency\s+shutdown\s+(?:bypassed|failed|overridden))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.ISOLATION_VALVE,
        "triggers": [
            r"\bisolation\s+valve\b",
            r"\bpositively\s+isolated\b",
            r"\bpositive\s+isolation\b",
            r"\bdouble\s+block\s+and\s+bleed\b",
            r"\bblind(?:ed|ing)?\b",
            r"\bspade\s+insertion\b",
            r"\bblock\s+valve\b",
            r"\bupstream\s+isolation\s+valve\b",
        ],
        "effective": [
            r"\b(?:process\s+line\s+was\s+positively\s+isolated)\b",
            r"\b(?:isolation\s+valve\s+(?:closed|held|isolated|shut))\b",
            r"\b(?:shutting\s+the\s+upstream\s+isolation\s+valve)\b",
            r"\b(?:positive\s+isolation\s+(?:in\s+place|confirmed|verified))\b",
            r"\b(?:double\s+block\s+and\s+bleed\s+(?:confirmed|verified|effective))\b",
        ],
        "deficient": [
            r"\b(?:isolation\s+valve\s+(?:had\s+not\s+been\s+locked|leaked|passing|failed|open))\b",
            r"\b(?:had\s+not\s+been\s+locked)\b",
            r"\b(?:without\s+(?:positive\s+)?isolation)\b",
            r"\b(?:valve\s+passing)\b",
            r"\b(?:isolation\s+(?:incomplete|inadequate|compromised))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.ZERO_ENERGY_VERIFICATION,
        "triggers": [
            r"\bzero[- ]energy(?:\s+verification)?\b",
            r"\btest[- ]before[- ]touch\b",
            r"\bverified\s+zero\b",
            r"\bverif(?:y|ied)\s+absence\s+of\s+voltage\b",
            r"\bzero\s+energy\s+was\s+verified\b",
        ],
        "effective": [
            r"\b(?:zero\s+energy\s+was\s+verified\s+before\s+work\s+began)\b",
            r"\b(?:zero[- ]energy\s+verification\s+(?:completed|confirmed|verified))\b",
            r"\b(?:absence\s+of\s+voltage\s+verified)\b",
            r"\b(?:residual\s+pressure\s+safely\s+relieved,\s+and\s+isolation\s+confirmed)\b",
        ],
        "deficient": [
            r"\b(?:zero[- ]energy\s+verification\s+had\s+not\s+been\s+completed)\b",
            r"\b(?:energy\s+isolation\s+was\s+not\s+verified)\b",
            r"\b(?:zero\s+energy\s+(?:not\s+verified|not\s+checked|omitted))\b",
            r"\b(?:without\s+zero[- ]energy\s+verification)\b",
            r"\b(?:failure\s+to\s+complete\s+and\s+independently\s+confirm\s+zero[- ]energy)\b",
        ],
        "default_state": BarrierState.NOT_VERIFIED,
    },
    {
        "category": BarrierCategory.LOCKOUT_TAGOUT,
        "triggers": [
            r"\blockout[ /]tagout\b",
            r"\bLOTO\b",
            r"\block\s*out\b",
            r"\btag\s*out\b",
            r"\bpadlock\b",
            r"\blockout\s+hasp\b",
        ],
        "effective": [
            r"\b(?:LOTO\s+(?:applied|implemented|confirmed|in\s+place))\b",
            r"\b(?:locked\s+out\s+and\s+tagged\s+out)\b",
            r"\b(?:padlock\s+applied)\b",
        ],
        "deficient": [
            r"\b(?:no\s+LOTO\b|LOTO\s+not\s+applied|without\s+LOTO)\b",
            r"\b(?:lock\s+(?:not\s+installed|not\s+applied|removed\s+prematurely))\b",
            r"\b(?:not\s+locked\s+out)\b",
        ],
        "default_state": BarrierState.ABSENT,
    },
    {
        "category": BarrierCategory.GAS_DETECTION,
        "triggers": [
            r"\bgas\s+test(?:ing)?\b",
            r"\bgas\s+detector\b",
            r"\batmospheric\s+test(?:ing)?\b",
            r"\batmospheric\s+monitor(?:ing)?\b",
            r"\bLEL\s+monitor(?:ing)?\b",
            r"\b4[- ]gas\s+monitor\b",
            r"\bmulti[- ]gas\b",
            r"\bH2S\s+detector\b",
        ],
        "effective": [
            r"\b(?:gas\s+testing\s+confirmed\s+safe\s+atmospheric\s+conditions)\b",
            r"\b(?:gas\s+detector\s+alarmed\s+when)\b",
            r"\b(?:atmospheric\s+testing\s+(?:confirmed\s+safe|completed|verified))\b",
            r"\b(?:gas\s+detector\s+alerted)\b",
            r"\b(?:gas\s+test\s+(?:clear|safe|completed))\b",
        ],
        "deficient": [
            r"\b(?:atmospheric\s+testing\s+was\s+not\s+verified)\b",
            r"\b(?:gas\s+test(?:ing)?\s+(?:not\s+done|omitted|not\s+performed|failed|unverified))\b",
            r"\b(?:gas\s+detector\s+(?:failed|faulty|not\s+calibrated|did\s+not\s+alarm))\b",
            r"\b(?:without\s+atmospheric\s+testing)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.VENTILATION,
        "triggers": [
            r"\bventilation\b",
            r"\bforced\s+air\s+ventilation\b",
            r"\bair\s+mover\b",
            r"\bexhaust\s+fan\b",
            r"\bblower\b",
        ],
        "effective": [
            r"\b(?:ventilation\s+(?:maintained|running|operational|effective|adequate))\b",
            r"\b(?:forced\s+air\s+ventilation\s+in\s+place)\b",
        ],
        "deficient": [
            r"\b(?:ventilation\s+was\s+inadequate)\b",
            r"\b(?:ventilation\s+(?:failed|stopped|absent|insufficient|inadequate|lacking))\b",
            r"\b(?:without\s+(?:adequate\s+)?ventilation)\b",
        ],
        "default_state": BarrierState.FAILED,
    },
    {
        "category": BarrierCategory.FIRE_WATCH,
        "triggers": [
            r"\bfire\s+watch\b",
            r"\bfire\s+extinguisher\b",
            r"\bfire\s+blanket\b",
            r"\bstandby\s+fire\s+watch\b",
        ],
        "effective": [
            r"\b(?:fire\s+watch\s+was\s+in\s+place)\b",
            r"\b(?:fire\s+watch\s+(?:extinguished|present|alert|intervened))\b",
            r"\b(?:fire\s+blanket\s+(?:contained|shielded|enclosed))\b",
            r"\b(?:extinguisher\s+on\s+hand)\b",
        ],
        "deficient": [
            r"\b(?:fire\s+watch\s+(?:absent|missing|not\s+assigned|left\s+area|inattentive))\b",
            r"\b(?:no\s+fire\s+watch)\b",
            r"\b(?:fire\s+extinguisher\s+(?:depleted|missing|inoperable))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.FIRE_SUPPRESSION,
        "triggers": [
            r"\bfire\s+suppression\b",
            r"\bdeluge\s+system\b",
            r"\bsprinkler\s+system\b",
            r"\bfoam\s+system\b",
        ],
        "effective": [
            r"\b(?:fire\s+suppression\s+(?:activated|extinguished|discharged|controlled))\b",
            r"\b(?:deluge\s+(?:activated|extinguished))\b",
        ],
        "deficient": [
            r"\b(?:fire\s+suppression\s+(?:failed|did\s+not\s+activate|isolated))\b",
            r"\b(?:deluge\s+isolated)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.CONTAINMENT,
        "triggers": [
            r"\bspill\s+containment\b",
            r"\bbund(?:ed|ing)?\b",
            r"\bdrip\s+pan\b",
            r"\bcatchment\b",
            r"\bsecondary\s+containment\b",
        ],
        "effective": [
            r"\b(?:containment\s+(?:captured|held|contained))\b",
            r"\b(?:bund\s+contained\s+the\s+release)\b",
            r"\b(?:drip\s+pan\s+captured)\b",
        ],
        "deficient": [
            r"\b(?:containment\s+(?:overflowed|breached|leaked|failed|absent))\b",
            r"\b(?:bund\s+valve\s+open)\b",
            r"\b(?:no\s+secondary\s+containment)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.VEHICLE_PEDESTRIAN_SEGREGATION,
        "triggers": [
            r"\bpedestrian\s+segregation\b",
            r"\bsegregation\s+barrier\b",
            r"\bpedestrian\s+barrier\b",
            r"\bvehicle\s+barrier\b",
            r"\bcrash\s+bollard\b",
            r"\bwalkway\s+barrier\b",
            r"\bseparating\s+the\s+vehicle\s+lane\s+from\s+the\s+walkway\b",
        ],
        "effective": [
            r"\b(?:pedestrian\s+segregation\s+was\s+maintained)\b",
            r"\b(?:worker\s+remained\s+outside\s+the\s+vehicle\s+operating\s+zone)\b",
            r"\b(?:segregation\s+barrier\s+prevented\s+entry)\b",
            r"\b(?:barrier\s+separating\s+the\s+vehicle\s+lane\s+from\s+the\s+walkway\s+stopped\s+the\s+forklift)\b",
            r"\b(?:physical\s+barrier\s+stopped\s+the\s+vehicle)\b",
            r"\b(?:bollard\s+prevented\s+intrusion)\b",
        ],
        "deficient": [
            r"\b(?:pedestrian\s+segregation\s+not\s+maintained)\b",
            r"\b(?:no\s+pedestrian\s+segregation)\b",
            r"\b(?:vehicle\s+barrier\s+(?:damaged|absent|missing|breached))\b",
            r"\b(?:entered\s+vehicle\s+lane\s+without\s+barrier)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.SEAT_BELT,
        "triggers": [
            r"\bseat[- ]belt\b",
            r"\bsafety\s+belt\b",
            r"\brestraint\s+harness\b",
        ],
        "effective": [
            r"\b(?:seat[- ]belt\s+(?:restrained|held|protected|worn))\b",
            r"\b(?:wearing\s+seat[- ]belt\s+prevented)\b",
        ],
        "deficient": [
            r"\b(?:seat[- ]belt\s+(?:not\s+worn|not\s+fastened|unbuckled|failed))\b",
            r"\b(?:without\s+seat[- ]belt)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.WHEEL_CHOCK,
        "triggers": [
            r"\bwheel\s+chock(?:s)?\b",
            r"\bchock(?:ed|ing)?\b",
            r"\bparking\s+brake\b",
        ],
        "effective": [
            r"\b(?:wheel\s+chocks\s+(?:in\s+place|prevented\s+roll|held))\b",
            r"\b(?:chocked\s+and\s+secured)\b",
        ],
        "deficient": [
            r"\b(?:wheel\s+chocks\s+(?:not\s+applied|missing|absent|slipped))\b",
            r"\b(?:without\s+wheel\s+chocks)\b",
            r"\b(?:parking\s+brake\s+not\s+set)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.PRESSURE_RELIEF,
        "triggers": [
            r"\bpressure\s+relief\s+valve\b",
            r"\bPRV\b",
            r"\bPSV\b",
            r"\brupture\s+dis[ck]\b",
            r"\bsafety\s+relief\s+valve\b",
        ],
        "effective": [
            r"\b(?:PRV\s+(?:lifted|relieved|vented|opened\s+safely))\b",
            r"\b(?:rupture\s+disk\s+burst\s+safely)\b",
            r"\b(?:relief\s+valve\s+(?:operated|functioned))\b",
        ],
        "deficient": [
            r"\b(?:PRV\s+(?:failed\s+to\s+lift|stuck|gagged|passing|isolated))\b",
            r"\b(?:relief\s+valve\s+(?:isolated|blocked|failed))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.STOP_WORK_INTERVENTION,
        "triggers": [
            r"\bstop[- ]work\b",
            r"\bcrew\s+stopped\b",
            r"\bwork\s+was\s+stopped\b",
            r"\bwork\s+stopped\s+immediately\b",
            r"\bintervened\s+and\s+stopped\b",
        ],
        "effective": [
            r"\b(?:crew\s+stopped\s+when\s+conditions\s+changed\s+and\s+resumed\s+only\s+after\s+controls\s+were\s+confirmed)\b",
            r"\b(?:work\s+was\s+stopped\s+and\s+the\s+platform\s+was\s+taken\s+out\s+of\s+service)\b",
            r"\b(?:work\s+stopped\s+immediately\s+upon\s+release)\b",
            r"\b(?:stop[- ]work\s+authority\s+(?:exercised|used|initiated))\b",
            r"\b(?:stopped\s+the\s+work\s+before\s+exposure)\b",
        ],
        "deficient": [
            r"\b(?:failed\s+to\s+stop\s+work)\b",
            r"\b(?:stop[- ]work\s+not\s+heeded)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.RIGGING_CONTROL,
        "triggers": [
            r"\brigging\b",
            r"\bsling\b",
            r"\bshackle\b",
            r"\btag[- ]line\b",
            r"\bwhip[- ]check\b",
            r"\bsafety\s+cable\b",
        ],
        "effective": [
            r"\b(?:rigging\s+remained\s+within\s+its\s+rated\s+capacity)\b",
            r"\b(?:whip[- ]check\s+(?:restrained|held))\b",
            r"\b(?:tag[- ]line\s+controlled\s+the\s+load)\b",
            r"\b(?:rigging\s+inspected\s+and\s+certified)\b",
        ],
        "deficient": [
            r"\b(?:rigging\s+(?:snapped|failed|overloaded|damaged|severed))\b",
            r"\b(?:whip[- ]check\s+(?:not\s+installed|missing|failed))\b",
            r"\b(?:sling\s+(?:parted|snapped|cut))\b",
            r"\b(?:without\s+tag[- ]line)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.LIFTING_EXCLUSION_ZONE,
        "triggers": [
            r"\blifting\s+radius(?:\s+exclusion\s+zone)?\b",
            r"\blift\s+path\b",
            r"\bsuspended[- ]load\s+(?:exclusion\s+)?zone\b",
            r"\bcrane\s+(?:swing\s+path|exclusion\s+zone)\b",
        ],
        "effective": [
            r"\b(?:no\s+worker\s+entered\s+the\s+lift\s+path)\b",
            r"\b(?:lift\s+path\s+cleared)\b",
            r"\b(?:worker\s+remained\s+outside\s+lift\s+radius)\b",
        ],
        "deficient": [
            r"\b(?:worker\s+entered\s+the\s+suspended[- ]load\s+exclusion\s+zone)\b",
            r"\b(?:entered\s+the\s+lift\s+path)\b",
            r"\b(?:positioned\s+under\s+(?:the\s+)?suspended\s+load)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.PROTECTIVE_SHIELD,
        "triggers": [
            r"\bdeflector\s+shield\b",
            r"\bblast\s+(?:shield|curtain|panel)\b",
            r"\bspray\s+shield\b",
            r"\bflange\s+shield\b",
            r"\bprotective\s+screen\b",
        ],
        "effective": [
            r"\b(?:shield\s+(?:deflected|stopped|protected|contained))\b",
            r"\b(?:spray\s+shield\s+prevented)\b",
        ],
        "deficient": [
            r"\b(?:shield\s+(?:missing|damaged|absent|omitted))\b",
            r"\b(?:without\s+(?:a\s+)?shield)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.RESCUE_SYSTEM,
        "triggers": [
            r"\brescue\s+system\b",
            r"\bretrieval\s+winch\b",
            r"\bstandby\s+rescuer\b",
            r"\btripod\s+retrieval\b",
        ],
        "effective": [
            r"\b(?:retrieval\s+system\s+(?:extracted|rescued|recovered))\b",
            r"\b(?:standby\s+rescue\s+deployed)\b",
        ],
        "deficient": [
            r"\b(?:rescue\s+system\s+(?:not\s+ready|failed|missing))\b",
            r"\b(?:no\s+standby\s+rescue)\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
    {
        "category": BarrierCategory.PPE_PROTECTIVE_BARRIER,
        "triggers": [
            r"\bSCBA\b",
            r"\bbreathing\s+apparatus\b",
            r"\barc[- ]flash\s+(?:suit|shield|hood)\b",
            r"\bchemical\s+suit\b",
            r"\bblast\s+suit\b",
        ],
        "effective": [
            r"\b(?:SCBA\s+(?:prevented\s+inhalation|protected\s+breathing))\b",
            r"\b(?:arc[- ]flash\s+suit\s+prevented\s+burns)\b",
            r"\b(?:chemical\s+suit\s+prevented\s+contact)\b",
        ],
        "deficient": [
            r"\b(?:SCBA\s+(?:depleted|failed|not\s+worn))\b",
            r"\b(?:arc[- ]flash\s+suit\s+(?:not\s+worn|failed))\b",
        ],
        "default_state": BarrierState.EFFECTIVE,
    },
]


# Compile patterns for fast repeated execution
for rule in BARRIER_EXTRACTION_RULES:
    rule["re_triggers"] = [re.compile(p, re.IGNORECASE) for p in rule["triggers"]]
    rule["re_effective"] = [re.compile(p, re.IGNORECASE) for p in rule["effective"]]
    rule["re_deficient"] = [re.compile(p, re.IGNORECASE) for p in rule["deficient"]]


# ── Context Extraction Helpers ────────────────────────────────────────────────

def _extract_context_window(text: str, match_obj: re.Match, window_chars: int = 120) -> str:
    start = max(0, match_obj.start() - window_chars)
    end = min(len(text), match_obj.end() + window_chars)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def extract_incident_barriers(
    incident: Any,
    default_hazard: str = "Unknown Hazard",
    default_activity: str = "General Operations",
    default_location: str = "Unknown Location",
    default_iogp: str = "None Associated",
    default_psif: str = "UNKNOWN",
) -> List[BarrierObservation]:
    """
    Extracts all evidence-supported physical and operational barriers
    described in an incident.

    Features:
    - Multi-barrier extraction (e.g. Machine Guard [ABSENT] + Emergency Stop [EFFECTIVE])
    - Negation & state resolution
    - Rejection of storage-only mentions ('stored in truck')
    - Rejection of post-event recommendations ('recommends guardrail')
    - Decoupled from IOGP rules and PSIF classification
    """
    narrative = str(
        getattr(incident, "composite_narrative", None)
        or getattr(incident, "description", "")
        or ""
    ).strip()

    job_task = str(getattr(incident, "job_task", "") or "").strip()
    equip = str(getattr(incident, "equipment_involved", "") or "").strip()
    imm_cause = str(getattr(incident, "immediate_cause", "") or "").strip()
    ctrl_type = str(getattr(incident, "control_type", "") or getattr(incident, "direct_control", "") or getattr(incident, "control", "") or "").strip()

    # Combined searchable text
    full_text = f"{narrative} {job_task} {equip} {imm_cause} {ctrl_type}".strip()
    if not full_text:
        return []

    inc_id = str(getattr(incident, "id", "temp"))
    workspace = getattr(incident, "workspace_id", "admin_flow")

    # Inherit context attributes if available
    loc_val = default_location if default_location and default_location != "Unknown Location" else (getattr(incident, "location", None) or "Unknown Location")
    act_val = default_activity if default_activity and default_activity != "General Operations" else (getattr(incident, "job_task", None) or "General Operations")
    psif_val = default_psif
    if hasattr(incident, "prediction") and incident.prediction is not None:
        if getattr(incident.prediction, "is_sparse_input", False):
            psif_val = "INSUFFICIENT_INFORMATION"
        elif getattr(incident.prediction, "psif_predicted", False):
            psif_val = "PSIF"
        else:
            psif_val = "NOT_PSIF"

    # IOGP rule association (stored as separate associated dimension)
    iogp_val = default_iogp
    if getattr(incident, "iogp_rule", None):
        iogp_val = str(incident.iogp_rule)

    if iogp_val == default_iogp and hasattr(incident, "iogp_rules") and hasattr(incident.iogp_rules, "all"):
        try:
            tag_rules = [getattr(t, "rule", None) or getattr(t, "rule_name", None) or str(t) for t in incident.iogp_rules.all()]
            valid = [r for r in tag_rules if r and str(r).lower() not in ["none", "unknown", "n/a"]]
            if valid:
                iogp_val = valid[0]
        except Exception:
            pass

    if iogp_val == default_iogp and getattr(incident, "control_type", None):
        iogp_val = str(incident.control_type)

    if iogp_val == default_iogp:
        from apps.incidents.services.normalization import CANONICAL_IOGP_RULES
        for rule_name in CANONICAL_IOGP_RULES:
            if re.search(r"\b" + re.escape(rule_name) + r"\b", full_text, re.IGNORECASE):
                iogp_val = rule_name
                break



    extracted_barriers: List[BarrierObservation] = []
    seen_categories: Set[str] = set()

    for rule in BARRIER_EXTRACTION_RULES:
        category = rule["category"]
        if category in seen_categories:
            continue

        # 1. Check if barrier mechanism is triggered
        trigger_match = None
        for re_trig in rule["re_triggers"]:
            m = re_trig.search(full_text)
            if m:
                trigger_match = m
                break

        if not trigger_match:
            continue

        # 2. Check for negative context (storage only or recommendation only)
        # Extract immediate context around the trigger
        window = _extract_context_window(full_text, trigger_match, window_chars=140)

        # Check for mere storage (e.g. "stored in the truck" without operational deficiency/action)
        if RE_STORAGE_ONLY.search(window):
            has_eff = any(r.search(full_text) for r in rule["re_effective"])
            has_def = any(r.search(full_text) for r in rule["re_deficient"])
            if not has_eff and not has_def:
                # Pure storage without operational context -> Skip!
                continue

        # Check for recommendation only
        if RE_RECOMMENDATION_ONLY.search(window) and not any(r.search(window) for r in rule["re_effective"]):
            # Post-incident recommendation only -> Skip!
            continue

        # 3. Determine Barrier State
        state = BarrierState.UNKNOWN
        evidence_snippet = window

        # Check deficient indicators first (or vice versa based on explicit wording)
        def_match = None
        for re_def in rule["re_deficient"]:
            m_def = re_def.search(full_text)
            if m_def:
                def_match = m_def
                break

        eff_match = None
        for re_eff in rule["re_effective"]:
            m_eff = re_eff.search(full_text)
            if m_eff:
                eff_match = m_eff
                break

        if def_match and not eff_match:
            def_text = def_match.group(0).lower()
            if "absent" in def_text or "missing" in def_text or "not installed" in def_text or "no " in def_text or "without " in def_text or "removed" in def_text:
                state = BarrierState.ABSENT
            elif "not verified" in def_text or "not completed" in def_text or "unverified" in def_text:
                state = BarrierState.NOT_VERIFIED
            elif "bypassed" in def_text or "defeated" in def_text or "overridden" in def_text:
                state = BarrierState.BYPASSED
            elif "not connected" in def_text or "not tied" in def_text or "not clipped" in def_text or "unattached" in def_text:
                state = BarrierState.ABSENT
            elif "inadequate" in def_text or "insufficient" in def_text:
                state = BarrierState.PARTIALLY_EFFECTIVE
            else:
                state = BarrierState.FAILED
            evidence_snippet = _extract_context_window(full_text, def_match, window_chars=120)

        elif eff_match and not def_match:
            state = BarrierState.EFFECTIVE
            evidence_snippet = _extract_context_window(full_text, eff_match, window_chars=120)

        elif eff_match and def_match:
            # Both present in text (e.g. guard removed + e-stop worked, or partial containment)
            dist_def = abs(trigger_match.start() - def_match.start())
            dist_eff = abs(trigger_match.start() - eff_match.start())
            if dist_def <= dist_eff:
                state = BarrierState.ABSENT if "removed" in def_match.group(0).lower() or "missing" in def_match.group(0).lower() else BarrierState.FAILED
                evidence_snippet = _extract_context_window(full_text, def_match, window_chars=120)
            else:
                state = BarrierState.EFFECTIVE
                evidence_snippet = _extract_context_window(full_text, eff_match, window_chars=120)
        else:
            # Check structured field if available
            ctrl_cond = str(getattr(incident, "control_condition", "") or "").lower().strip()
            if ctrl_cond in ["failed", "fail"]:
                state = BarrierState.FAILED
            elif ctrl_cond in ["absent", "missing"]:
                state = BarrierState.ABSENT
            elif ctrl_cond in ["bypassed", "override", "overridden"]:
                state = BarrierState.BYPASSED
            elif ctrl_cond in ["not_verified", "unverified"]:
                state = BarrierState.NOT_VERIFIED
            elif ctrl_cond in ["partially_effective", "partial"]:
                state = BarrierState.PARTIALLY_EFFECTIVE
            elif ctrl_cond in ["effective", "intact"]:
                state = BarrierState.EFFECTIVE
            else:
                # Fallback state based on rule definition
                state = rule.get("default_state", BarrierState.UNKNOWN)

        is_effective = state in EFFECTIVE_BARRIER_STATES
        is_deficient = state in DEFICIENT_BARRIER_STATES
        role = DEFAULT_BARRIER_ROLES.get(category, BarrierRole.PREVENTIVE)

        barrier_obs = BarrierObservation(
            incident_id=inc_id,
            workspace=workspace,
            barrier_category=category,
            barrier_name=BARRIER_LABELS.get(category, category),
            barrier_state=state,
            barrier_role=role,
            is_effective=is_effective,
            is_deficient=is_deficient,
            source_field="composite_narrative",
            evidence_span=evidence_snippet,
            hazard=default_hazard,
            activity=act_val,
            location=loc_val,
            iogp_rule=iogp_val,
            psif_state=psif_val,
            barrier_raw_text=trigger_match.group(0),
        )

        extracted_barriers.append(barrier_obs)
        seen_categories.add(category)

    return extracted_barriers
