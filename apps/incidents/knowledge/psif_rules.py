"""
16 Authoritative PSIF Safety Rules Catalog & Full State-Space Definitions
apps/incidents/knowledge/psif_rules.py
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from apps.incidents.knowledge.sources import SourceAuthority, ProvenanceTier
from apps.incidents.knowledge.energy_hazards import EnergyHazardType
from apps.incidents.knowledge.exposures import ExposureState
from apps.incidents.knowledge.controls import ControlState


class InternalReasoningState:
    """Canonical internal fivefold reasoning states."""
    PSIF_PATHWAY_OPEN = "PSIF_PATHWAY_OPEN"
    HIGH_ENERGY_CONTROLLED = "HIGH_ENERGY_CONTROLLED"
    LOW_ENERGY = "LOW_ENERGY"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class UserFacingDecision:
    """Authoritative three-way user facing decisions."""
    PSIF = "PSIF"
    NOT_PSIF = "NOT_PSIF"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"


INTERNAL_STATE_TO_DECISION: Dict[str, str] = {
    InternalReasoningState.PSIF_PATHWAY_OPEN: UserFacingDecision.PSIF,
    InternalReasoningState.HIGH_ENERGY_CONTROLLED: UserFacingDecision.NOT_PSIF,
    InternalReasoningState.LOW_ENERGY: UserFacingDecision.NOT_PSIF,
    InternalReasoningState.INSUFFICIENT_INFORMATION: UserFacingDecision.INSUFFICIENT_INFORMATION,
    InternalReasoningState.CONFLICTING_EVIDENCE: UserFacingDecision.INSUFFICIENT_INFORMATION,
}


@dataclass(frozen=True)
class PSIFRuleDefinition:
    """Immutable authoritative safety rule definition."""
    rule_id: str
    title: str
    description: str
    source_authority: str
    source_section: str
    provenance_tier: str
    applicable_hazards: List[str]
    required_exposure_states: List[str]
    required_control_states: List[str]
    decision_effect: str
    user_facing_decision: str
    applicable_iogp_rules: List[str] = field(default_factory=list)
    counterexamples: Dict[str, str] = field(default_factory=dict)
    rationale: str = ""

    @property
    def name(self) -> str:
        return self.title

    @property
    def source(self) -> str:
        return self.source_authority


PSIF_RULES_CATALOG: List[PSIFRuleDefinition] = [
    PSIFRuleDefinition(
        rule_id="PSIF-R-01",
        title="Working at Height Uncontrolled Fall Pathway",
        description="A worker at an elevated level (> 1.8m) without continuous 100% tie-off or engineered guardrail establishes an open gravitational SIF pathway.",
        source_authority=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Working at Height & Start Work Checks",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[EnergyHazardType.WORKING_AT_HEIGHT],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Working at Height"],
        counterexamples={
            "PSIF": "Scaffolder worked at 8 metres on elevated pipe rack; harness lanyards were unhitched while repositioning.",
            "NOT_PSIF": "Scaffolder worked at 8 metres; fall arrest was installed and verified with 100% tie-off maintained throughout.",
            "INSUFFICIENT": "Scaffolding structure C-412 was erected at elevated level; worker harness connection unrecorded.",
            "CONFLICTING": "Harness was reported worn and verified, but worker fell unarrested to grade with lanyard unhitched.",
        },
        rationale="Gravitational potential energy at elevation without anchored fall arrest presents an unmitigated fatal fall vector.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-02",
        title="Suspended Load Crane Drop Zone Intrusion",
        description="Personnel stationed beneath or within the unmitigated swing radius of a suspended crane load establish an open crushing SIF pathway.",
        source_authority=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Safe Mechanical Lifting & Line of Fire",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[EnergyHazardType.SUSPENDED_LOADS, EnergyHazardType.LINE_OF_FIRE],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.INSIDE_EXCLUSION_ZONE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Safe Mechanical Lifting", "Line of Fire"],
        counterexamples={
            "PSIF": "During 15-ton crane lift, rigger stood beneath suspended load while adjusting synthetic slings.",
            "NOT_PSIF": "During 15-ton crane lift, rigger remained outside exclusion zone behind designated safety barrier.",
            "INSUFFICIENT": "Crane hoisting of steel beam package was scheduled at laydown area; worker positioning unrecorded.",
            "CONFLICTING": "Rigger reported staged safely outside drop zone, but was simultaneously struck by fallen load.",
        },
        rationale="Heavy suspended mass possesses immense gravitational kinetic energy; ordinary PPE offers zero protection.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-03",
        title="Stored Pressure Line Breaking Without Verified Isolation",
        description="Breaking containment on a pressurized process or test line without verified zero energy and double block & bleed establishes an open release vector.",
        source_authority=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Stored Energy Release",
        provenance_tier=ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        applicable_hazards=[EnergyHazardType.PRESSURE_STORED, EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Energy Isolation", "Line of Fire"],
        counterexamples={
            "PSIF": "Technician unbolted 150 bar line when casing bleeder was omitted and spray blew toward worker face.",
            "NOT_PSIF": "Technician unbolted line; double block and bleed held zero pressure verified by casing bleeder.",
            "INSUFFICIENT": "Pressure manifold testing underway at 200 bar; isolation status and worker positioning unrecorded.",
            "CONFLICTING": "Isolation reported verified zero energy, but residual pressure blew past gasket when unbolted.",
        },
        rationale="Uncontrolled pneumatic/hydraulic discharge creates fluid injection, projectile shrapnel, and fatal trauma.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-04",
        title="High Voltage Electrical Direct Contact Trajectory",
        description="Maintenance or access to energized electrical apparatus (> 440V, 11kV) without verified absence of voltage establishes an open arc flash pathway.",
        source_authority=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Electrical Hazards",
        provenance_tier=ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        applicable_hazards=[EnergyHazardType.ELECTRICAL],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Energy Isolation"],
        counterexamples={
            "PSIF": "Electrician began maintenance on 11kV switchgear cubicle; absence of voltage was not maintained.",
            "NOT_PSIF": "Electrician verified zero hazardous voltage with calibrated meter; switchgear remained fully locked out.",
            "INSUFFICIENT": "Substation breaker racking initiated; isolation verification condition not documented.",
            "CONFLICTING": "Switchgear reported de-energized, but arc flash explosion occurred during contact.",
        },
        rationale="High voltage contact or arc blast causes instant fatal electrocution or massive thermal trauma.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-05",
        title="Confined Space Atmospheric Asphyxiation Pathway",
        description="Entry into a vessel, tank, or confined space without continuous atmospheric testing or positive mechanical blinds establishes an open asphyxiation vector.",
        source_authority=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Confined Space Entry",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[EnergyHazardType.CONFINED_SPACE],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.INSIDE_EXCLUSION_ZONE],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Confined Space", "Energy Isolation"],
        counterexamples={
            "PSIF": "Operator entered vessel without continuous atmospheric monitoring and leaned into nitrogen pocket.",
            "NOT_PSIF": "Continuous gas monitoring verified safe atmosphere and alarm sounded clearing crew before entry.",
            "INSUFFICIENT": "Vessel inspection planned on column C-12; entrant monitoring records not documented.",
            "CONFLICTING": "Atmosphere reported verified safe, but worker lost consciousness instantly from severe anoxia.",
        },
        rationale="Oxygen-deficient or toxic atmospheres cause rapid loss of consciousness within seconds with zero escape ability.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-06",
        title="Hot Work Ignition Near Flammable Inventory",
        description="Open flame or cutting torch operation near hydrocarbon atmosphere without positive spark containment or continuous gas monitoring establishes an open flash fire pathway.",
        source_authority=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Hot Work & Start Work Checks",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[EnergyHazardType.HOT_WORK_IGNITION, EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Hot Work", "Energy Isolation"],
        counterexamples={
            "PSIF": "Torch cutting initiated adjacent to hydrocarbon line without gas testing and slag rolled past fire blanket.",
            "NOT_PSIF": "Certified spark habitat isolated hot work with dedicated fire watch and continuous 0% LEL confirmed.",
            "INSUFFICIENT": "Structural welding scheduled on deck grating; combustible proximity not documented.",
            "CONFLICTING": "Atmosphere certified zero LEL, but flash fire ignited immediately upon striking welding arc.",
        },
        rationale="Welding sparks contacting flammable vapors produce instant uncontained vapor cloud explosions.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-07",
        title="Mobile Equipment Pedestrian Trajectory Intrusion",
        description="Pedestrian personnel entering the travel path or reversing blind spot of heavy vehicles without physical barrier segregation establishes an open crushing pathway.",
        source_authority=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Driving & Line of Fire",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT, EnergyHazardType.LINE_OF_FIRE],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Driving", "Line of Fire"],
        counterexamples={
            "PSIF": "Forklift reversing in loading bay with broken backup alarm; pedestrian entered travel path.",
            "NOT_PSIF": "Worker did not enter vehicle path and remained behind designated safety barrier.",
            "INSUFFICIENT": "Delivery truck moving in yard; pedestrian presence and barrier layout unrecorded.",
            "CONFLICTING": "Worker reported behind segregation rail, but was simultaneously run over by forklift wheel.",
        },
        rationale="Heavy mobile machinery possesses momentum exceeding human biological impact tolerance.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-08",
        title="High Energy Controlled / Demonstrated Capacity",
        description="High-energy hazard present, but direct critical engineered control functioned effectively or worker positioning completely interrupted the consequence vector.",
        source_authority=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 3.2 Capacity / Direct Controls Functioned",
        provenance_tier=ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        applicable_hazards=[
            EnergyHazardType.WORKING_AT_HEIGHT, EnergyHazardType.SUSPENDED_LOADS,
            EnergyHazardType.PRESSURE_STORED, EnergyHazardType.ELECTRICAL,
            EnergyHazardType.CONFINED_SPACE, EnergyHazardType.ROTATING_EQUIPMENT,
            EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT, EnergyHazardType.HOT_WORK_IGNITION,
        ],
        required_exposure_states=[ExposureState.NEARBY_BUT_PROTECTED, ExposureState.NO_WORKER_EXPOSURE, ExposureState.EXPOSURE_INTERRUPTED],
        required_control_states=[ControlState.EFFECTIVE, ControlState.RESTORED_BEFORE_EXPOSURE],
        decision_effect=InternalReasoningState.HIGH_ENERGY_CONTROLLED,
        user_facing_decision=UserFacingDecision.NOT_PSIF,
        applicable_iogp_rules=[],
        counterexamples={
            "CAPACITY": "Heavy crane lifting 20 tons; rigger remained outside exclusion zone behind certified barriers.",
            "FAILURE": "Rigger stepped beneath load while synthetic slings slipped.",
        },
        rationale="Core EEI SCL principle: capacity is demonstrated when direct controls successfully arrest energy release.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-09",
        title="Stop-Work Authority Interruption Prior to Exposure",
        description="Hazard was manifested or identified, but work was halted and control restored prior to personnel exposure or line opening.",
        source_authority=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Start Work Checks — Stop Work Authority",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[
            EnergyHazardType.PRESSURE_STORED, EnergyHazardType.ELECTRICAL,
            EnergyHazardType.CONFINED_SPACE, EnergyHazardType.ROTATING_EQUIPMENT,
        ],
        required_exposure_states=[ExposureState.EXPOSURE_INTERRUPTED, ExposureState.NO_WORKER_EXPOSURE],
        required_control_states=[ControlState.RESTORED_BEFORE_EXPOSURE, ControlState.EFFECTIVE],
        decision_effect=InternalReasoningState.HIGH_ENERGY_CONTROLLED,
        user_facing_decision=UserFacingDecision.NOT_PSIF,
        applicable_iogp_rules=["Work Authorization"],
        counterexamples={
            "STOP_WORK": "Passing valve identified on crude manifold; control was restored before exposure of work crew.",
            "POST_INCIDENT": "Passing valve caused leak onto technician; flange was repaired after the event.",
        },
        rationale="Interruption prior to worker exposure completely prevents human consequence vector.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-10",
        title="Low Energy / Non-SIF Operational Activity",
        description="Incident or condition involves low energy density without credible physical SIF consequence potential (minor drips, level walking, paper handling).",
        source_authority=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 3.2 Non-High-Energy Incidents",
        provenance_tier=ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        applicable_hazards=[EnergyHazardType.LOW_ENERGY_GENERAL],
        required_exposure_states=[ExposureState.NO_WORKER_EXPOSURE, ExposureState.NEARBY_BUT_PROTECTED, ExposureState.DIRECT_EXPOSURE],
        required_control_states=[ControlState.EFFECTIVE, ControlState.UNKNOWN],
        decision_effect=InternalReasoningState.LOW_ENERGY,
        user_facing_decision=UserFacingDecision.NOT_PSIF,
        applicable_iogp_rules=[],
        counterexamples={
            "LOW_ENERGY": "Operator observed minor condensation drip on cold water line during routine rounds.",
            "HIGH_ENERGY": "Operator unbolting pressurized 100 bar condensate line without isolation.",
        },
        rationale="Without high physical energy density, serious injury or fatality cannot physically materialize.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-11",
        title="Insufficient Information / Incomplete Physical Evidence",
        description="Essential facts regarding energy manifestation, worker positioning, or barrier verification state are unrecorded or missing in field reporting.",
        source_authority=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 3.1 Data Sufficiency & Unknown Barrier Evaluation",
        provenance_tier=ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        applicable_hazards=[
            EnergyHazardType.PRESSURE_STORED, EnergyHazardType.ELECTRICAL,
            EnergyHazardType.WORKING_AT_HEIGHT, EnergyHazardType.SUSPENDED_LOADS,
            EnergyHazardType.CONFINED_SPACE, EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT,
        ],
        required_exposure_states=[ExposureState.UNKNOWN, ExposureState.POTENTIAL_EXPOSURE],
        required_control_states=[ControlState.UNKNOWN],
        decision_effect=InternalReasoningState.INSUFFICIENT_INFORMATION,
        user_facing_decision=UserFacingDecision.INSUFFICIENT_INFORMATION,
        applicable_iogp_rules=[],
        counterexamples={
            "INSUFFICIENT": "Work order WO-13760 covered pre-job setup on sump.",
            "SUFFICIENT": "Operator entered vessel without continuous gas monitoring and sustained anoxia.",
        },
        rationale="A high-integrity safety platform must never guess or hallucinate SIF decisions when critical barrier facts are absent.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-12",
        title="Rotating Equipment Guarding Bypass",
        description="Machinery started or operated with coupling/shaft guard removed or interlock defeated while personnel are within reach of moving parts.",
        source_authority=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Mechanical Hazards",
        provenance_tier=ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        applicable_hazards=[EnergyHazardType.ROTATING_EQUIPMENT],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Bypassing Safety Controls", "Energy Isolation"],
        counterexamples={
            "PSIF": "Compressor started without reinstalling coupling guard and technician was within pinch point.",
            "NOT_PSIF": "Mechanical isolation held throughout and maintenance supervisor stayed outside drive-train envelope.",
            "INSUFFICIENT": "Pump overhaul scheduled at workshop; guard status unrecorded.",
        },
        rationale="High-speed rotating equipment exerts irreversible mechanical force causing traumatic amputation or fatal entanglement.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-13",
        title="Excavation Vertical Cut Shoring Bypass",
        description="Personnel entering vertical-cut trench (> 1.2m depth) without certified trench boxes, hydraulic shoring, or 45-degree soil benching.",
        source_authority=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Work Authorization & Trenching Safety",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[EnergyHazardType.EXCAVATION_GROUND_COLLAPSE],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Work Authorization"],
        counterexamples={
            "PSIF": "Pipelayers entered un-shored 2.5m vertical-cut trench before wall collapsed.",
            "NOT_PSIF": "Pipelayers worked inside certified steel shoring box fully shielded from lateral ground collapse.",
            "INSUFFICIENT": "Trench excavation underway; shoring installation records unrecorded.",
        },
        rationale="Soil collapse produces thousands of kilograms of lateral force causing fatal asphyxiation or crush trauma.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-14",
        title="Dropped Objects Overhead Kinetic Release",
        description="Heavy equipment or tools dropped from elevated structures into un-barricaded work areas with personnel present below.",
        source_authority=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Working at Height & DROPS Guidance",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[EnergyHazardType.DROPPED_OBJECTS, EnergyHazardType.SUSPENDED_LOADS],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Working at Height", "Safe Mechanical Lifting"],
        counterexamples={
            "PSIF": "Untethered heavy scaffold clamp fell 14 metres through grating into active walkway.",
            "NOT_PSIF": "Tool lanyard arrested dynamic weight of wrench; drop netting caught clamp.",
            "INSUFFICIENT": "Scaffolding modification in utility area; overhead drop precautions unrecorded.",
        },
        rationale="Free-falling objects attain high terminal velocity and kinetic impact exceeding ordinary PPE defense.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-15",
        title="Toxic Hydrogen Sulfide / Asphyxiant Release",
        description="Release of hydrogen sulfide (H2S), toxic gas, or inert nitrogen into breathing zone without positive pressure breathing apparatus.",
        source_authority=SourceAuthority.IOGP_559,
        source_section="IOGP Report 559 Toxic Exposure & Loss of Primary Containment",
        provenance_tier=ProvenanceTier.IOGP_GUIDANCE,
        applicable_hazards=[EnergyHazardType.TOXIC_ASYMMETRIC_ATMOSPHERE, EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT, ControlState.NOT_VERIFIED],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Confined Space", "Energy Isolation"],
        counterexamples={
            "PSIF": "Sour gas manifold leaked H2S blowing directly past technician working without respiratory protection.",
            "NOT_PSIF": "Continuous fixed H2S detection alarmed and auto-shutdown isolated line before exposure occurred.",
            "INSUFFICIENT": "Gas odor reported near compressor building; concentration and worker location unrecorded.",
        },
        rationale="Toxic gases paralyze olfactory and respiratory systems causing rapid fatal pulmonary arrest.",
    ),
    PSIFRuleDefinition(
        rule_id="PSIF-R-16",
        title="Thermal Energy Superheated Fluid Release",
        description="Superheated steam (> 150°C) or thermal fluid release directly contacting worker during line breaking or seal blowout.",
        source_authority=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Thermal Energy Release",
        provenance_tier=ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        applicable_hazards=[EnergyHazardType.THERMAL_ENERGY, EnergyHazardType.PRESSURE_STORED],
        required_exposure_states=[ExposureState.DIRECT_EXPOSURE, ExposureState.IN_RELEASE_PATH],
        required_control_states=[ControlState.FAILED, ControlState.BYPASSED, ControlState.ABSENT],
        decision_effect=InternalReasoningState.PSIF_PATHWAY_OPEN,
        user_facing_decision=UserFacingDecision.PSIF,
        applicable_iogp_rules=["Energy Isolation"],
        counterexamples={
            "PSIF": "Superheated steam valve stem packing failed releasing 180°C steam jet into worker torso.",
            "NOT_PSIF": "Verified cooling and venting sequence executed; thermal isolation held absolute zero pressure.",
            "INSUFFICIENT": "Steam trap inspection in boiler house; thermal condition unrecorded.",
        },
        rationale="Superheated fluid carries massive thermodynamic enthalpy causing full-thickness third-degree burns.",
    ),
]


def get_rule_by_id(rule_id: str) -> Optional[PSIFRuleDefinition]:
    """Retrieves authoritative safety rule definition by unique ID."""
    for rule in PSIF_RULES_CATALOG:
        if rule.rule_id == rule_id:
            return rule
    return None


def get_rules_for_hazard(hazard_type: str) -> List[PSIFRuleDefinition]:
    """Returns all authoritative rules applicable to a specific hazard family."""
    return [r for r in PSIF_RULES_CATALOG if hazard_type in r.applicable_hazards]


def get_rules_for_iogp(rule_code: str) -> List[PSIFRuleDefinition]:
    """Returns all authoritative rules tied to an IOGP Life-Saving Rule."""
    return [r for r in PSIF_RULES_CATALOG if rule_code in r.applicable_iogp_rules]
