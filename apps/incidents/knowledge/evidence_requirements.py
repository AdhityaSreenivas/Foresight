"""
Authoritative Evidence Contracts & Sufficiency Requirements
apps/incidents/knowledge/evidence_requirements.py
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from apps.incidents.knowledge.energy_hazards import EnergyHazardType


@dataclass(frozen=True)
class EvidenceContract:
    """Formal evidence requirements contract governing safety rule evaluation."""
    hazard_type: str
    required_evidence: List[str]
    supporting_evidence: List[str]
    contradictory_evidence: List[str]
    disqualifying_evidence: List[str]
    missing_evidence_prompts: Dict[str, str]


@dataclass
class MissingEvidenceItem:
    """Explicit itemized missing evidence requirement for incomplete incident records."""
    what: str
    why_it_matters: str
    decision_impact: str


EVIDENCE_CONTRACTS: Dict[str, EvidenceContract] = {
    EnergyHazardType.PRESSURE_STORED: EvidenceContract(
        hazard_type=EnergyHazardType.PRESSURE_STORED,
        required_evidence=[
            "Documented pressure source (system pressure, test pressure, fluid type)",
            "Worker spatial positioning relative to line breaking or discharge point",
            "Energy isolation and bleeder verification condition",
        ],
        supporting_evidence=[
            "Pressure gauge readings or test chart",
            "Bleeder valve or drain port physical status",
            "Directional vector of pressurized fluid release",
        ],
        contradictory_evidence=[
            "Isolation claimed verified while residual pressure simultaneously blew past gasket",
            "Zero pressure certified while passing valve released pressurized mist",
        ],
        disqualifying_evidence=[
            "Verified double block and bleed with double zero gauge pressure and bleeder open",
            "Worker confirmed fully outside discharge trajectory behind certified blast shield",
        ],
        missing_evidence_prompts={
            "worker_position": "Was the worker directly in the line of fire or release trajectory when containment was breached?",
            "isolation_verification": "Was absence of pressure physically verified via bleeder port prior to loosening fittings?",
        },
    ),
    EnergyHazardType.WORKING_AT_HEIGHT: EvidenceContract(
        hazard_type=EnergyHazardType.WORKING_AT_HEIGHT,
        required_evidence=[
            "Working elevation (height above ground / reference level)",
            "Worker position relative to unguarded edge or fall vector",
            "Condition and attachment status of fall protection system",
        ],
        supporting_evidence=[
            "Scaffold tagging status and inspection log",
            "Anchor point rating and harness lanyard type (SRL / shock-absorbing)",
            "Presence of certified toe boards and mid-rails",
        ],
        contradictory_evidence=[
            "100% tie-off claimed while worker fell unarrested to grade",
            "Harness reported installed while both lanyards were unhitched during movement",
        ],
        disqualifying_evidence=[
            "Engineered permanent handrail / guardrail fully intact with no opening",
            "Dual-lanyard tie-off verified continuously anchored with zero slack",
        ],
        missing_evidence_prompts={
            "elevation": "What was the exact working elevation above grade or reference platform?",
            "tie_off_status": "Were harness lanyards physically anchored to certified points throughout the task?",
        },
    ),
    EnergyHazardType.SUSPENDED_LOADS: EvidenceContract(
        hazard_type=EnergyHazardType.SUSPENDED_LOADS,
        required_evidence=[
            "Lifted package weight and rigging arrangement",
            "Personnel positioning relative to suspended load and lift radius",
            "Integrity of exclusion zone barricading or mechanical supports",
        ],
        supporting_evidence=[
            "Lifting plan and crane load chart margin",
            "Rigging gear inspection certificate (slings, shackles)",
            "Tag line usage and standoff distance",
        ],
        contradictory_evidence=[
            "Personnel reported outside exclusion zone while report simultaneously records a direct strike",
            "Certified rigging claimed intact while hoisted package dropped uncontrollably",
        ],
        disqualifying_evidence=[
            "Hard physical segregation preventing all pedestrian encroachment into drop zone",
            "Certified mechanical jack stands or solid oak cribbing supporting load",
        ],
        missing_evidence_prompts={
            "personnel_position": "Were any personnel positioned beneath or within the dynamic swing envelope of the load?",
            "barricade_status": "Was a physical exclusion zone actively maintained around the entire lift perimeter?",
        },
    ),
    EnergyHazardType.ELECTRICAL: EvidenceContract(
        hazard_type=EnergyHazardType.ELECTRICAL,
        required_evidence=[
            "Operating voltage and system rating (> 440V, 11kV, 33kV)",
            "De-energization and lockout/tagout verification state",
            "Worker contact proximity or arc flash boundary distance",
        ],
        supporting_evidence=[
            "Calibrated voltage meter reading documenting 0V before touch",
            "Grounding cluster installation log",
            "Dead-front interlock operational status",
        ],
        contradictory_evidence=[
            "De-energization verified while arc flash blast or electrical shock occurred",
            "Breaker locked out while conductors remained energized at high voltage",
        ],
        disqualifying_evidence=[
            "Verified absence of voltage (test-before-touch) with certified ground leads attached",
            "Dead-front physical interlock preventing mechanical access to energized busbars",
        ],
        missing_evidence_prompts={
            "voltage_verification": "Was absence of voltage independently verified using a calibrated meter prior to touch?",
            "isolation_state": "Was the equipment locked, tagged, and isolated from all possible backfeeds?",
        },
    ),
    EnergyHazardType.CONFINED_SPACE: EvidenceContract(
        hazard_type=EnergyHazardType.CONFINED_SPACE,
        required_evidence=[
            "Enclosed vessel or space configuration",
            "Continuous multi-gas atmospheric monitoring records (O2, LEL, H2S, CO)",
            "Personnel entry status (plane of opening crossed)",
        ],
        supporting_evidence=[
            "Positive mechanical blind isolation of all connected process lines",
            "Forced mechanical ventilation airflow rate",
            "Standby rescue attendant log",
        ],
        contradictory_evidence=[
            "Safe atmosphere certified while entrant lost consciousness from anoxia",
            "Zero LEL recorded while flash fire ignited inside vessel",
        ],
        disqualifying_evidence=[
            "Continuous gas monitoring verifying safe atmosphere throughout entry with positive mechanical blinds",
            "Work halted and personnel evacuated prior to crossing plane of opening",
        ],
        missing_evidence_prompts={
            "gas_testing": "Was continuous atmospheric testing conducted at bottom, middle, and top of the space?",
            "entry_extent": "Did any person cross the plane of opening with their head, torso, or full body?",
        },
    ),
    EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT: EvidenceContract(
        hazard_type=EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT,
        required_evidence=[
            "Mobile equipment type, mass, and operating speed",
            "Pedestrian proximity to vehicle path or reversing zone",
            "Functioning state of physical segregation barriers or warning systems",
        ],
        supporting_evidence=[
            "Dedicated spotter / banksman log",
            "Reverse alarm decibel test or radar sensor log",
            "Traffic route segregation layout",
        ],
        contradictory_evidence=[
            "Pedestrians reported behind physical barrier while pedestrian struck occurred",
        ],
        disqualifying_evidence=[
            "Rigid continuous steel guardrail separating vehicle roadway from pedestrian walkway",
            "Vehicle interlock automatically halted motion prior to approaching worker",
        ],
        missing_evidence_prompts={
            "worker_position": "Was the pedestrian inside the travel path, blind spot, or reversing envelope?",
            "barrier_state": "Was physical barrier segregation present between moving vehicle and foot traffic?",
        },
    ),
    EnergyHazardType.ROTATING_EQUIPMENT: EvidenceContract(
        hazard_type=EnergyHazardType.ROTATING_EQUIPMENT,
        required_evidence=[
            "Rotating machine type (pump, compressor, agitator, drive shaft)",
            "Guard status (bolted in place, removed, interlock bypassed)",
            "Worker proximity to rotating nip point or coupling",
        ],
        supporting_evidence=[
            "Motive power lockout / tagout log",
            "Emergency trip-wire test log",
            "Interlock switch functional test",
        ],
        contradictory_evidence=[
            "Guard reported in place while worker clothing caught in rotating shaft",
        ],
        disqualifying_evidence=[
            "Fixed bolted steel mesh guard completely enclosing rotating assembly",
            "Mechanical lock applied with motive power isolated and proven zero rotation",
        ],
        missing_evidence_prompts={
            "guard_status": "Was the machinery guard installed, bolted, and intact during rotation?",
            "worker_reach": "Was the worker within reach of unguarded rotating components?",
        },
    ),
    EnergyHazardType.HOT_WORK_IGNITION: EvidenceContract(
        hazard_type=EnergyHazardType.HOT_WORK_IGNITION,
        required_evidence=[
            "Ignition source type (open flame, torch cutting, structural welding, grinding sparks)",
            "Presence and proximity of combustible inventory or hydrocarbon atmosphere",
            "Containment barrier state (fire blanket, spark habitat, fire watch)",
        ],
        supporting_evidence=[
            "Continuous 0% LEL combustible gas test record",
            "Dedicated fire watch log and extinguisher check",
            "Habitat pressurization test",
        ],
        contradictory_evidence=[
            "Zero LEL reported while flash fire or gas explosion occurred at torch",
        ],
        disqualifying_evidence=[
            "Certified spark habitat isolating ignition source with continuous 0% LEL verification",
            "Dedicated fire watch immediately doused isolated spatter with zero propagation",
        ],
        missing_evidence_prompts={
            "combustible_proximity": "Were flammable fluids or combustible materials within 10 meters of hot work?",
            "fire_watch": "Was a dedicated fire watch with charged extinguisher stationed throughout?",
        },
    ),
    EnergyHazardType.EXCAVATION_GROUND_COLLAPSE: EvidenceContract(
        hazard_type=EnergyHazardType.EXCAVATION_GROUND_COLLAPSE,
        required_evidence=[
            "Excavation depth (> 1.2m) and soil wall angle",
            "Worker presence inside trench bed",
            "Shoring protection state (steel trench box, hydraulic shoring, 45° sloping)",
        ],
        supporting_evidence=[
            "Daily soil classification log by competent person",
            "Spoil pile setback distance (> 1.5m)",
            "Ground vibration monitoring from nearby machinery",
        ],
        contradictory_evidence=[
            "Certified shoring reported deployed while soil collapsed directly onto worker",
        ],
        disqualifying_evidence=[
            "Certified steel shoring box fully deployed with workers operating inside shield",
            "Excavation wall sloped at stable 1:1 ratio or stepped benching",
        ],
        missing_evidence_prompts={
            "trench_depth": "What was the depth of the excavation or trench?",
            "shoring_status": "Were trench boxes or hydraulic shoring installed and protecting the work area?",
        },
    ),
    EnergyHazardType.DROPPED_OBJECTS: EvidenceContract(
        hazard_type=EnergyHazardType.DROPPED_OBJECTS,
        required_evidence=[
            "Object mass and elevation from which it dropped",
            "Worker presence below elevated workface or in drop zone",
            "Condition of secondary retention, tool lanyards, or drop netting",
        ],
        supporting_evidence=[
            "Toe board installation record (> 150mm)",
            "Tool lanyard weight rating and attachment log",
            "Hard barricading of drop zone below",
        ],
        contradictory_evidence=[
            "Drop zone reported clear while object struck worker on lower deck",
        ],
        disqualifying_evidence=[
            "Certified overhead safety netting arrested dynamic fall of object",
            "Tool lanyard arrested dropped equipment before crossing deck edge",
        ],
        missing_evidence_prompts={
            "drop_height": "From what height did the object drop?",
            "tethering_status": "Were tools tethered with lanyards, and was drop netting deployed below?",
        },
    ),
    EnergyHazardType.LINE_OF_FIRE: EvidenceContract(
        hazard_type=EnergyHazardType.LINE_OF_FIRE,
        required_evidence=[
            "Identification of stored force or projectile vector (tension, pressure, recoil)",
            "Worker presence within trajectory or snap-back zone",
            "Condition of physical deflectors, whip checks, or exclusion barriers",
        ],
        supporting_evidence=[
            "Whip check cable rating and attachment log",
            "Marked red zone boundary documentation",
            "Tension gauge or line pull record",
        ],
        contradictory_evidence=[
            "Worker claimed outside line of fire while projectile struck personnel in trajectory",
        ],
        disqualifying_evidence=[
            "Engineered whip checks and deflection barriers contained energy release",
            "Personnel remained outside snap-back danger envelope throughout operation",
        ],
        missing_evidence_prompts={
            "worker_position": "Was the worker standing in the direct line of recoil, whip, or release?",
            "containment_state": "Were whip checks, restraining cables, or blast shields deployed?",
        },
    ),
    EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE: EvidenceContract(
        hazard_type=EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE,
        required_evidence=[
            "Hydrocarbon volume, pressure, and flammability / LEL concentration",
            "Worker proximity to vapor cloud or liquid release pool",
            "Primary containment integrity and automated ESDV / isolation state",
        ],
        supporting_evidence=[
            "LEL gas detector log (< 10% LEL verified)",
            "Automated emergency shutdown valve (ESDV) closure record",
            "Ignition source isolation radius documentation",
        ],
        contradictory_evidence=[
            "Area reported gas-free while flash fire ignited at hot work interface",
        ],
        disqualifying_evidence=[
            "Automated ESDV immediately isolated hydrocarbon source prior to ignition",
            "Positive spectacle blind isolation held full line pressure without leakage",
        ],
        missing_evidence_prompts={
            "lel_concentration": "What was the measured LEL combustible gas reading in the work zone?",
            "isolation_status": "Were positive spectacle blinds or double block and bleed valves secured?",
        },
    ),
    EnergyHazardType.TOXIC_ASPHYXIANT_ATMOSPHERE: EvidenceContract(
        hazard_type=EnergyHazardType.TOXIC_ASPHYXIANT_ATMOSPHERE,
        required_evidence=[
            "Gas identity (H2S, CO, Nitrogen, SO2) and measured concentration in ppm",
            "Worker location relative to emission point or breathing zone",
            "Availability and use of supplied-air respiratory protection (SCBA)",
        ],
        supporting_evidence=[
            "Multi-gas detector data log and calibration certificate",
            "Wind sock direction and worker upwind positioning record",
            "Positive pressure breathing apparatus pressure check log",
        ],
        contradictory_evidence=[
            "Area reported non-toxic while technician suffered acute H2S inhalation poisoning",
        ],
        disqualifying_evidence=[
            "Continuous atmospheric monitoring verified 0 ppm H2S and 20.9% O2 throughout",
            "Fixed toxic detection triggered immediate plant ESD before exposure reached personnel",
        ],
        missing_evidence_prompts={
            "ppm_level": "What was the measured toxic gas concentration in parts per million (ppm)?",
            "respiratory_ppe": "Was positive pressure self-contained breathing apparatus (SCBA) worn?",
        },
    ),
    EnergyHazardType.THERMAL_ENERGY: EvidenceContract(
        hazard_type=EnergyHazardType.THERMAL_ENERGY,
        required_evidence=[
            "Operating fluid temperature (> 100°C steam or thermal oil)",
            "Worker positioning relative to valve packing, flange, or discharge jet",
            "Depressurization, cooling verification, and thermal insulation condition",
        ],
        supporting_evidence=[
            "Infrared thermography scan verifying surface temperature < 60°C",
            "Boiler house vent valve opening confirmation",
            "Thermal protective clothing and face shield deployment",
        ],
        contradictory_evidence=[
            "Line certified cooled while 180°C steam escaped upon unbolting",
        ],
        disqualifying_evidence=[
            "System verified cooled below 50°C and vented to zero pressure prior to work",
            "Worker operated remote valve actuator behind thermal deflector wall",
        ],
        missing_evidence_prompts={
            "fluid_temperature": "What was the operating temperature and pressure of the thermal fluid?",
            "cooling_verification": "Was the line verified cooled and completely vented before breaking?",
        },
    ),
    EnergyHazardType.STORED_MECHANICAL_ENERGY: EvidenceContract(
        hazard_type=EnergyHazardType.STORED_MECHANICAL_ENERGY,
        required_evidence=[
            "Source of stored energy (compressed spring, counterweight, hydraulic accumulator)",
            "Worker presence within mechanical sweep, pinch point, or release envelope",
            "Condition of mechanical lockouts, pin stops, or hydraulic bleed-off",
        ],
        supporting_evidence=[
            "Mechanical lock-pin insertion record",
            "Hydraulic accumulator pressure dump valve status",
            "Counterweight physical ground-blocking record",
        ],
        contradictory_evidence=[
            "Spring claimed de-tensioned while sudden expansion caused traumatic impact",
        ],
        disqualifying_evidence=[
            "Certified mechanical stop pins and chocks positively immobilized stored energy",
            "Hydraulic accumulator completely blown down with manual drain valve locked open",
        ],
        missing_evidence_prompts={
            "stored_mechanism": "What mechanical energy mechanism was present (spring, weight, accumulator)?",
            "de_energization": "Were mechanical stop pins inserted or accumulator pressure fully drained?",
        },
    ),
}

EVIDENCE_CONTRACTS["hydrocarbon_flammable_release"] = EVIDENCE_CONTRACTS[EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE]
EVIDENCE_CONTRACTS["chemical_flammable"] = EVIDENCE_CONTRACTS[EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE]


def get_evidence_contract(hazard_type: str) -> Optional[EvidenceContract]:
    """Retrieves authoritative evidence contract by hazard family."""
    return EVIDENCE_CONTRACTS.get(hazard_type)


def evaluate_evidence_completeness(
    hazard_type: str,
    text: str,
    exposure_state: str,
    control_state: str,
) -> Dict[str, Any]:
    """
    Evaluates evidence completeness against the authoritative evidence contract for a hazard.
    Returns completeness status, missing items, and actionable missing evidence prompts.
    """
    contract = get_evidence_contract(hazard_type)
    if not contract:
        return {
            "has_contract": False,
            "completeness": "UNKNOWN",
            "missing_evidence": [],
            "missing_prompts": [],
        }

    missing_prompts: List[str] = []
    missing_items: List[str] = []

    # Check exposure completeness
    if exposure_state in ("UNKNOWN", "INSUFFICIENT_INFORMATION"):
        missing_items.append("Worker Position / Exposure Trajectory")
        for key, prompt in contract.missing_evidence_prompts.items():
            if any(term in key for term in ["position", "proximity", "entry", "under", "exposure"]):
                missing_prompts.append(prompt)

    # Check control completeness
    if control_state in ("UNKNOWN", "NOT_VERIFIED", "INCORRECTLY_ASSUMED"):
        missing_items.append("Control / Barrier State Verification")
        for key, prompt in contract.missing_evidence_prompts.items():
            if any(term in key for term in ["isolation", "barrier", "guard", "loto", "gas", "tethering"]):
                missing_prompts.append(prompt)

    # Fallback to contract prompts if items missing
    if missing_items and not missing_prompts:
        missing_prompts = list(contract.missing_evidence_prompts.values())

    completeness = "COMPLETE" if not missing_items else ("PARTIAL" if len(missing_items) < len(contract.required_evidence) else "INSUFFICIENT")

    return {
        "has_contract": True,
        "hazard_type": hazard_type,
        "completeness": completeness,
        "missing_evidence": missing_items,
        "missing_prompts": missing_prompts,
        "required_evidence": contract.required_evidence,
        "supporting_evidence": contract.supporting_evidence,
    }
