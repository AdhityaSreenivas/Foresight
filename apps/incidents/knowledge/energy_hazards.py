"""
15 Required Hazard Families & Full State-Space Definitions
apps/incidents/knowledge/energy_hazards.py
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from apps.incidents.knowledge.sources import SourceAuthority, ProvenanceTier


class EnergyHazardType:
    """15 Canonical High-Energy Hazard Families + Low Energy Baseline."""
    WORKING_AT_HEIGHT = "working_at_height"
    SUSPENDED_LOADS = "suspended_loads"
    LINE_OF_FIRE = "line_of_fire"
    PRESSURE_STORED = "pressure_stored"
    ELECTRICAL = "electrical"
    VEHICLE_MOBILE_EQUIPMENT = "vehicle_mobile_equipment"
    ROTATING_EQUIPMENT = "rotating_equipment"
    HOT_WORK_IGNITION = "hot_work_ignition"
    CONFINED_SPACE = "confined_space"
    HYDROCARBON_FLAMMABLE_RELEASE = "chemical_flammable"
    TOXIC_ASPHYXIANT_ATMOSPHERE = "toxic_atmosphere"
    TOXIC_ASYMMETRIC_ATMOSPHERE = TOXIC_ASPHYXIANT_ATMOSPHERE
    THERMAL_ENERGY = "thermal_energy"
    STORED_MECHANICAL_ENERGY = "stored_mechanical_energy"
    EXCAVATION_GROUND_COLLAPSE = "excavation_ground_collapse"
    DROPPED_OBJECTS = "dropped_objects"
    LOW_ENERGY_GENERAL = "low_energy_general"

    # Aliases for backwards compatibility
    GRAVITY = "working_at_height"
    MECHANICAL_MOTION = "rotating_equipment"
    CHEMICAL_FLAMMABLE = "chemical_flammable"
    MOBILE_EQUIPMENT = "vehicle_mobile_equipment"


class HazardAmplifier:
    """Contextual operational conditions that compound the severity of an energy release."""
    ELEVATION_OVER_2M = "elevation_over_2m"
    HIGH_PRESSURE = "high_pressure"
    HIGH_VOLTAGE = "high_voltage"
    CONFINED_GEOMETRY = "confined_geometry"
    TOXIC_CONCENTRATION = "toxic_concentration"
    SIMULTANEOUS_OPERATIONS = "simultaneous_operations"
    POOR_VISIBILITY_OR_WEATHER = "poor_visibility_or_weather"
    SOLITARY_OR_REMOTE_WORK = "solitary_or_remote_work"


@dataclass(frozen=True)
class HazardFamilyDefinition:
    """Models the full physical and operational state space of a hazard family."""
    hazard_type: str
    name: str
    energy_manifestation: str
    release_mechanism: str
    exposure_mechanisms: List[str]
    worker_positions: List[str]
    critical_direct_controls: List[str]
    indirect_controls: List[str]
    effective_states: List[str]
    compromised_states: List[str]
    credible_consequences: List[str]
    barrier_interruption_mechanisms: List[str]
    applicable_iogp_rules: List[str]
    source_id: str
    source_section: str


@dataclass
class ExtractedHazard:
    """Structured extraction output representing an energy hazard detected in evidence."""
    hazard_type: str
    energy_present: bool
    evidence_text: Optional[str] = None
    source_field: str = "composite_narrative"
    source_reference: Optional[str] = None


HAZARD_FAMILY_CATALOG: Dict[str, HazardFamilyDefinition] = {
    EnergyHazardType.WORKING_AT_HEIGHT: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.WORKING_AT_HEIGHT,
        name="Working at Height (Gravitational Potential Energy)",
        energy_manifestation="Gravitational potential energy of elevated personnel (elevation > 1.8m / elevated pipe racks, scaffolds, ladders, derricks).",
        release_mechanism="Loss of footing, structural scaffold displacement, unanchored ladder slip, unguarded edge fall.",
        exposure_mechanisms=["Personnel working near unprotected edge", "Ascending/descending without fall arrest", "Repositioning across ledger beams without dual tie-off"],
        worker_positions=["At unprotected elevated edge", "On mobile scaffold platform", "On ladder rung", "On pipe rack beam"],
        critical_direct_controls=["100% Dual-tie-off fall arrest harness", "Self-retracting lifeline (SRL)", "Engineered guardrail with top/mid rail and toe board", "Rigid scaffolding with handrails"],
        indirect_controls=["Working at height permit", "Toolbox safety talk", "Scaffold inspection green tag"],
        effective_states=["Harness verified and 100% tie-off maintained", "Fall arrest system arrested dynamic weight", "Engineered guardrail intact and held firm"],
        compromised_states=["Harness unhitched", "Lanyard unclipped", "Guardrail missing on one side", "Scaffold floor plank missing", "Frayed lanyard"],
        credible_consequences=["FALL", "CRUSHING", "FATALITY", "PERMANENT_DISABILITY"],
        barrier_interruption_mechanisms=["Dual-point harness anchor held dynamic fall", "Perimeter guardrail stopped person at edge"],
        applicable_iogp_rules=["Working at Height"],
        source_id=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Working at Height & Start Work Checks",
    ),
    EnergyHazardType.SUSPENDED_LOADS: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.SUSPENDED_LOADS,
        name="Suspended Loads & Mechanical Lifting (Gravitational / Dynamic Energy)",
        energy_manifestation="Gravitational and kinetic energy of heavy hoisted packages, tubulars, and crane counterweights.",
        release_mechanism="Rigging sling parting, crane winch brake slippage, hook latch failure, unseated synthetic sling, mechanical shackle detachment.",
        exposure_mechanisms=["Personnel positioned directly beneath hoisted package", "Rigger inside dynamic swing radius", "Operating within blind lift zone"],
        worker_positions=["Directly underneath suspended load", "Inside crane swing envelope", "Between load and rigid obstacle"],
        critical_direct_controls=["Hard physical barricading of drop zone / lift radius", "Remote console operation outside swing path", "Certified mechanical jack stands / cribbing"],
        indirect_controls=["Lift permit", "Banksman / rigger certification", "Lifting plan review"],
        effective_states=["Exclusion zone maintained and all personnel staged outside", "Rigger behind designated safety barrier", "Remote joystick operation from safe standoff"],
        compromised_states=["Worker stood beneath load", "Entered exclusion zone", "Rigger crossed inside warning tape", "Sling parted or dropped assembly"],
        credible_consequences=["CRUSHING", "STRUCK_BY", "AMPUTATION"],
        barrier_interruption_mechanisms=["Rigid barricade physically segregated pedestrian traffic from lift path"],
        applicable_iogp_rules=["Safe Mechanical Lifting", "Line of Fire"],
        source_id=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Safe Mechanical Lifting & Report 559 Lifting Integrity",
    ),
    EnergyHazardType.PRESSURE_STORED: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.PRESSURE_STORED,
        name="Pressure & Stored Fluid Energy (Pneumatic / Hydraulic / Process Pressure)",
        energy_manifestation="Stored mechanical and thermodynamic energy in pressurized piping, manifolds, autoclaves, and hydraulic accumulators.",
        release_mechanism="Flange blowout, threaded nipple shear, valve stem packing ejection, burst piping, unbolting pressurized union.",
        exposure_mechanisms=["Worker positioned directly in line with flange split", "Tightening fittings under live pressure", "Torso or face in jet discharge vector"],
        worker_positions=["In front of valve stem", "Facing line breaking interface", "Holding whipping pneumatic hose"],
        critical_direct_controls=["Positive double block and bleed with verified zero pressure", "Blinding / spade insertion", "Spring-loaded breakaway valve", "Flange spray shield / blast curtain"],
        indirect_controls=["Pressure testing permit", "Calibration certificate", "LOTO paperwork"],
        effective_states=["Isolation valves held absolute isolation", "Depressurized to zero gauge pressure verified by bleeder", "Blast containment shield in place"],
        compromised_states=["Omitted opening bleeder port to prove zero energy", "Tightened union under live hydraulic load", "Threads stripped off projecting steel fitting", "Flange blew past gasket"],
        credible_consequences=["PRESSURE_RELEASE", "FLUID_INJECTION", "PROJECTILE", "STRUCK_BY"],
        barrier_interruption_mechanisms=["Zero energy verified before unbolting", "Spray shield deflected pressurized mist safely"],
        applicable_iogp_rules=["Energy Isolation", "Line of Fire"],
        source_id=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Stored Energy & IOGP Report 459 Energy Isolation",
    ),
    EnergyHazardType.ELECTRICAL: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.ELECTRICAL,
        name="Electrical Energy (High Voltage & Arc Flash)",
        energy_manifestation="High-voltage electrical potential (> 440V, 11kV, 33kV, busbars, transformers, switchgear cubicles).",
        release_mechanism="Insulation breakdown, dropped metal tool bridging phases, racking breaker under load, unauthorized panel opening.",
        exposure_mechanisms=["Personnel working live without interlock", "Direct physical contact with copper busbars", "Positioned inside arc flash blast boundary"],
        worker_positions=["Inside open switchgear cubicle", "Direct contact trajectory to live terminal", "Facing racking breaker"],
        critical_direct_controls=["Physical lock-out / tag-out with verified absence of voltage (test-before-touch)", "Interlocked dead-front cubicle doors", "Automatic circuit trip / ground fault relay"],
        indirect_controls=["Electrical safety permit", "Arc flash warning placard", "Switchgear operating authorization"],
        effective_states=["Verified zero hazardous voltage by calibrated meter", "Switchgear remained fully locked out throughout", "Dead-front interlock prevented panel door opening"],
        compromised_states=["Absence of voltage not maintained", "Energized-panel interface not closed off", "Lockout verification degraded", "Worked live on 11kV conductors"],
        credible_consequences=["ELECTRICAL_CONTACT", "ARC_FLASH", "EXPLOSION", "FATALITY"],
        barrier_interruption_mechanisms=["De-energization and grounding verified before touch, interrupting electrical path"],
        applicable_iogp_rules=["Energy Isolation"],
        source_id=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Electrical & IOGP Report 459 Energy Isolation",
    ),
    EnergyHazardType.CONFINED_SPACE: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.CONFINED_SPACE,
        name="Confined Space & Hazardous Atmosphere (Oxygen Deficiency / Toxic Gas)",
        energy_manifestation="Atmospheric chemical energy, nitrogen asphyxiation, toxic H2S pockets, oxygen depletion (< 19.5%).",
        release_mechanism="Inadequate purge, nitrogen pocket entrapment, sludge disturbance emitting H2S, organic decay in enclosed manhole/sewer.",
        exposure_mechanisms=["Entrant leans torso or steps into vessel", "Entering without atmospheric monitoring", "Atmosphere changes during occupancy"],
        worker_positions=["Inside storage tank", "Torso leaned through manway hatch", "Inside trench box / sewer manhole"],
        critical_direct_controls=["Continuous multi-gas atmospheric testing at all levels", "Forced mechanical air ventilation", "Positive mechanical blind isolation of all process connections", "External standby rescue watch with retrieval harness"],
        indirect_controls=["Confined space entry permit", "Entry log sheet", "Pre-job toolbox talk"],
        effective_states=["Continuous gas testing confirmed safe atmosphere throughout", "Positive mechanical blinds installed and held", "Alarm sounded and crew cleared before entry"],
        compromised_states=["Entered without continuous monitoring", "Gas testing was bypassed", "Leaned into nitrogen pocket", "Sludge released toxic gas with entrant inside"],
        credible_consequences=["ASPHYXIATION", "TOXIC_EXPOSURE", "LOSS_OF_CONSCIOUSNESS", "FATALITY"],
        barrier_interruption_mechanisms=["Continuous monitoring alarmed and halted entry before personnel crossed plane of opening"],
        applicable_iogp_rules=["Confined Space", "Energy Isolation"],
        source_id=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Confined Space Entry & Report 559 Toxic Exposure",
    ),
    EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE,
        name="Hydrocarbon & Flammable Fluid Release (Thermal / Chemical Potential)",
        energy_manifestation="Flammable crude oil, volatile natural gas, condensate, methane vapors under pressure.",
        release_mechanism="Loss of primary containment (LOPC), leaking valve packing, pinhole pipe corrosion, pig trap overpressure, tank overflow.",
        exposure_mechanisms=["Vapor cloud migration toward hot work or ignition source", "Liquid spray onto personnel", "Personnel enveloped in flash fire fireball"],
        worker_positions=["Downwind of leaking process line", "In drainage sump collecting hydrocarbons", "At separator skid interface"],
        critical_direct_controls=["Positive mechanical spectacle blinds / double block and bleed", "Automated emergency shutdown valve (ESDV)", "Fixed LEL combustible gas detection linked to auto-deluge", "Gas-tight physical segregation / vapor blanket"],
        indirect_controls=["Hot work permit", "Gas test certificate", "Visual leak inspection"],
        effective_states=["ESDV tripped and safely contained inventory", "Positive blinds held full line pressure", "Dedicated gas detector confirmed 0% LEL prior to hot work"],
        compromised_states=["Passing valve released flammable mist", "Hydrocarbon leak onto technician", "Vapor escaped and ignited flash fire", "Gasket blew out releasing gas cloud"],
        credible_consequences=["FLASH_FIRE", "FIRE", "EXPLOSION", "TOXIC_EXPOSURE"],
        barrier_interruption_mechanisms=["Automated fail-closed ESDV isolated hydrocarbon source before ignition occurred"],
        applicable_iogp_rules=["Energy Isolation", "Hot Work"],
        source_id=SourceAuthority.IOGP_559,
        source_section="IOGP Report 559 Process Safety Fundamentals — Loss of Primary Containment",
    ),
    EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT,
        name="Vehicle & Mobile Heavy Equipment (Kinetic Energy)",
        energy_manifestation="Kinetic energy of moving forklifts, articulated haulers, cranes in transit, tractor-trailers, and crew buses.",
        release_mechanism="Brake failure, blind spot reversing, operator distraction, runaway vehicle on grade, rollover on uneven surface.",
        exposure_mechanisms=["Pedestrian walking in vehicle trajectory", "Ground worker behind reversing truck", "Driver ejected during rollover"],
        worker_positions=["In vehicle travel path", "Behind reversing forklift", "Inside pinch zone between truck and loading dock"],
        critical_direct_controls=["Rigid physical pedestrian segregation barriers / crash bollards", "Autonomous emergency braking / radar reversing interlock", "Certified 3-point seatbelt with ROPS cab"],
        indirect_controls=["Traffic management plan", "Speed limit signs", "Hi-vis vest"],
        effective_states=["Continuous bolted steel barrier prevented vehicle encroaching on walkway", "Reversing alarm and spotter held throughout keeping pedestrians clear", "Worker did not enter vehicle path and remained behind barrier"],
        compromised_states=["Reverse alarm disabled or wiring severed", "Pedestrian entered vehicle path", "Forklift tire rolled over foot", "Truck rolled back without wheel chocks"],
        credible_consequences=["CRUSHING", "STRUCK_BY", "RUNOVER", "FATALITY"],
        barrier_interruption_mechanisms=["Impact-absorbing crash bollard arrested vehicle before entering pedestrian walkway"],
        applicable_iogp_rules=["Driving", "Line of Fire"],
        source_id=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Driving & Line of Fire Rules",
    ),
    EnergyHazardType.ROTATING_EQUIPMENT: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.ROTATING_EQUIPMENT,
        name="Rotating & Mechanical Equipment (Rotational Kinetic Energy)",
        energy_manifestation="Kinetic rotational energy of pump couplings, drive shafts, agitators, pulleys, drill string rotary tables, and lathes.",
        release_mechanism="Guarding removal during operation, unintended startup during maintenance, clothing/glove nip-point entanglement.",
        exposure_mechanisms=["Operator hand or clothing drawn into rotating nip point", "Performing maintenance without zero-energy lockout", "Working within rotating shaft reach"],
        worker_positions=["Adjacent to exposed drive shaft", "Reaching into pump impeller chamber", "Standing next to rotating coupling"],
        critical_direct_controls=["Fixed, interlocked, bolted machinery guarding preventing physical access", "Positive lockout / tagout with mechanical isolation of motive power", "Emergency trip-wire / safety stop interlock"],
        indirect_controls=["Machinery safety training", "Warning signs", "Pre-start inspection checklist"],
        effective_states=["Heavy steel mesh locked coupling guard was securely bolted", "Mechanical isolation held throughout and worker remained outside drive-train envelope", "Interlock immediately halted motor upon door opening"],
        compromised_states=["Coupling guard was removed and unit started", "Started without reinstalling coupling guard", "Worker drawn into rotating shaft nip point"],
        credible_consequences=["ENTANGLEMENT", "AMPUTATION", "CRUSHING", "FATALITY"],
        barrier_interruption_mechanisms=["Interlocked physical barrier prevented drive motor energization while guard was open"],
        applicable_iogp_rules=["Bypassing Safety Controls", "Energy Isolation"],
        source_id=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Mechanical Hazards & IOGP Report 459 Bypassing Controls",
    ),
    EnergyHazardType.HOT_WORK_IGNITION: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.HOT_WORK_IGNITION,
        name="Hot Work & Thermal Ignition Energy",
        energy_manifestation="Open flames, cutting torch arcs, welding sparks, and hot slag exceeding 1000°C.",
        release_mechanism="Sparks penetrating floor grating, slag contacting oily rag, flashback in oxy-acetylene hose, torch cutting near hydrocarbon line.",
        exposure_mechanisms=["Sparks contacting combustible inventory", "Flashback reaching gas cylinder", "Welder exposed to radiant flash"],
        worker_positions=["Below welding deck", "Adjacent to cutting torch", "In hazardous zone during hot work"],
        critical_direct_controls=["Certified non-combustible fire blankets fully enclosing work area", "Flashback arrestors on both torch and bottle regulators", "Dedicated fire watch with pressurized fire extinguisher on station throughout and 30 min after"],
        indirect_controls=["Hot work permit", "Atmospheric gas check log", "Pre-job risk assessment"],
        effective_states=["Dedicated fire watch immediately doused spark spatter", "Fire blanket completely sealed deck grating preventing slag drop", "Continuous gas test confirmed zero LEL"],
        compromised_states=["Hot slag rolled past inadequate fire blanket", "Torch cutting initiated without atmospheric testing", "Hot work performed adjacent to leaking hydrocarbon flange"],
        credible_consequences=["FIRE", "FLASH_FIRE", "EXPLOSION", "BURNS"],
        barrier_interruption_mechanisms=["Certified spark containment habitat completely isolated ignition source from process area"],
        applicable_iogp_rules=["Hot Work"],
        source_id=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Hot Work & Start Work Checks",
    ),
    EnergyHazardType.LINE_OF_FIRE: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.LINE_OF_FIRE,
        name="Line of Fire (Trajectory & Energy Path Vectors)",
        energy_manifestation="Kinetic vectors of whipping hoses, projectile fittings, recoiling winch cables, and heavy counterweights.",
        release_mechanism="Tension failure, pin shearing, pressurized connection separation, sudden mechanical release under load.",
        exposure_mechanisms=["Worker standing in direct recoil trajectory", "Positioned in line with pressurized cap removal", "Standing inside snap-back danger zone"],
        worker_positions=["In direct path of tensioned line", "Directly in front of pressurized bleeder", "Within cable snap-back zone"],
        critical_direct_controls=["Engineered whip checks / safety restraining cables", "Deflector shields / blast panels", "Physical exclusion barricades isolating danger vector"],
        indirect_controls=["Toolbox talk", "Line of fire awareness briefing", "Marked zone on deck floor"],
        effective_states=["Whip check cable arrested whipping hose securely", "Worker stood outside trajectory behind polycarb shield", "Exclusion zone barrier kept worker clear of recoil path"],
        compromised_states=["Worker stood directly in line of fire when pressurized fitting blew", "Whip check was absent", "Cable snapped and struck worker in trajectory"],
        credible_consequences=["STRUCK_BY", "PROJECTILE", "AMPUTATION", "FATALITY"],
        barrier_interruption_mechanisms=["Engineered whip-check cable arrested dynamic kinetic recoil of pressurized line"],
        applicable_iogp_rules=["Line of Fire"],
        source_id=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Line of Fire Rules",
    ),
    EnergyHazardType.TOXIC_ASYMMETRIC_ATMOSPHERE: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.TOXIC_ASYMMETRIC_ATMOSPHERE,
        name="Toxic & Asphyxiant Atmosphere (Chemical Toxicity)",
        energy_manifestation="Chemical reactivity of hydrogen sulfide (H2S), chlorine, carbon monoxide, ammonia, or pure nitrogen gas.",
        release_mechanism="Piping pinhole leak, sample point draining, venting acid gases, seal failure on sour crude pump.",
        exposure_mechanisms=["Inhalation of toxic vapor cloud", "Worker enveloped in invisible odorless nitrogen blanket", "High ppm H2S release"],
        worker_positions=["Downwind of vent stack", "In low-lying pit or cellar", "At sampling point without scrubber"],
        critical_direct_controls=["Positive pressure self-contained breathing apparatus (SCBA) / airline", "Fixed optical/electrochemical toxic gas detection with automatic alarm", "Caustic scrubber containment on vent system"],
        indirect_controls=["Toxic gas awareness training", "Wind sock monitoring", "H2S warning signs"],
        effective_states=["Continuous fixed H2S detector alarmed and crew evacuated safely", "Technician donned positive-pressure SCBA before sampling", "Auto-isolation valve closed on gas detection"],
        compromised_states=["Entered pit without gas detection", "H2S release blew past worker without breathing air", "Lost consciousness instantly from severe anoxia"],
        credible_consequences=["TOXIC_EXPOSURE", "ASPHYXIATION", "FATALITY"],
        barrier_interruption_mechanisms=["Positive-pressure breathing apparatus isolated worker respiratory system from toxic cloud"],
        applicable_iogp_rules=["Confined Space", "Energy Isolation"],
        source_id=SourceAuthority.IOGP_559,
        source_section="IOGP Report 559 Toxic Exposure & Barrier Integrity",
    ),
    EnergyHazardType.THERMAL_ENERGY: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.THERMAL_ENERGY,
        name="Thermal Energy (Cryogenic & Superheated Fluids)",
        energy_manifestation="Thermal energy in superheated steam (> 150°C), thermal heat transfer fluid, molten metal slag, or cryogenic LNG (-160°C).",
        release_mechanism="Steam trap rupture, thermal expansion failure, cryogenic valve freeze-fracture, uninsulated pipe contact.",
        exposure_mechanisms=["Superheated steam impingement onto personnel", "Cryogenic liquid splash causing instant freezing", "Contact with hot pipe surface"],
        worker_positions=["In steam path during trap blowdown", "Adjacent to cryogenic loading arm", "Underneath leaking thermal oil line"],
        critical_direct_controls=["Engineered thermal insulation jackets", "Double block and bleed on steam supply with verified zero pressure", "Deflector splash shrouds around flanges"],
        indirect_controls=["Thermal hazard warning labels", "Thermal gloves (PPE)", "Safe work permit"],
        effective_states=["Insulation jacket prevented personnel burn contact", "Verified cooling and venting sequence prior to valve overhaul", "Steam isolation held absolute zero pressure"],
        compromised_states=["Steam line ruptured discharging superheated steam into worker face", "Cryogenic liquid splashed technician during transfer", "Hot thermal oil sprayed uninsulated"],
        credible_consequences=["PRESSURE_RELEASE", "STRUCK_BY", "BURNS", "PERMANENT_DISABILITY"],
        barrier_interruption_mechanisms=["Automated thermal relief valve safely discharged excess steam to vent stack away from crew"],
        applicable_iogp_rules=["Energy Isolation"],
        source_id=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Thermal Energy Release",
    ),
    EnergyHazardType.STORED_MECHANICAL_ENERGY: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.STORED_MECHANICAL_ENERGY,
        name="Stored Mechanical Energy (Springs / Counterweights / Tensioned Cables)",
        energy_manifestation="Potential strain energy in compressed heavy springs, elevated counterweights, tensioned mooring cables, or accumulator bladders.",
        release_mechanism="Spring retainer fracture, counterweight cable failure, unexpected accumulator discharge during maintenance.",
        exposure_mechanisms=["Personnel in release path of compressed spring assembly", "Positioned under counterweight", "Working on hydraulic cylinder without mechanical locking"],
        worker_positions=["Facing spring pack during unbolting", "Beneath elevator counterweight", "Inside cylinder stroke path"],
        critical_direct_controls=["Positive mechanical locking pins / clamping collars", "Hydraulic accumulator manual drain-down with pressure gauge verification", "Engineered spring-compression containment jigs"],
        indirect_controls=["Spring maintenance procedure", "Pre-job risk assessment", "Warning tags"],
        effective_states=["Certified mechanical locking pin secured cylinder throughout", "Accumulator verified fully depressurized before disassembly", "Safety cribbing blocks sustained full counterweight"],
        compromised_states=["Unbolted spring retainer without mechanical compression jig", "Tensioned cable sheared projecting clamp", "Accumulator discharged unexpectedly into worker"],
        credible_consequences=["STRUCK_BY", "PROJECTILE", "CRUSHING", "AMPUTATION"],
        barrier_interruption_mechanisms=["Solid oak safety cribbing blocks sustained static weight preventing mechanical movement"],
        applicable_iogp_rules=["Energy Isolation"],
        source_id=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 2.1 Stored Mechanical Energy",
    ),
    EnergyHazardType.EXCAVATION_GROUND_COLLAPSE: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.EXCAVATION_GROUND_COLLAPSE,
        name="Excavation & Ground Collapse (Geotechnical Potential Energy)",
        energy_manifestation="Mass and gravitational force of unsupported soil walls (> 1.2m depth / vertical trench cuts).",
        release_mechanism="Soil shear failure, ground vibration from adjacent machinery, water saturation weakening trench wall, undercut spoil pile collapse.",
        exposure_mechanisms=["Pipelayers working inside vertical-cut un-shored trench", "Personnel in trench below heavy excavator", "Worker entering unsupported excavation"],
        worker_positions=["Inside un-shored trench bed", "Beneath vertical soil overhang", "At bottom of bell-hole excavation"],
        critical_direct_controls=["Certified steel trench shoring boxes / hydraulic shoring shields", "Engineered 1:1 soil benching or 45° sloping", "Spoil pile staged at least 1.5m back from trench lip"],
        indirect_controls=["Excavation permit", "Daily competent person soil inspection", "Trench safety signs"],
        effective_states=["Certified steel shoring box deployed and workers fully shielded inside", "Trench wall sloped at stable 45-degree angle", "Rock fall stopped against outer spreader bar without breaching workspace"],
        compromised_states=["Entered un-shored vertical-cut trench", "Bypassed trench shoring boxes", "Trench wall collapsed engulfing worker to waist"],
        credible_consequences=["ENGULFMENT", "ASPHYXIATION", "CRUSHING", "FATALITY"],
        barrier_interruption_mechanisms=["Engineered steel trench box sustained full lateral soil force preventing cave-in from reaching workers"],
        applicable_iogp_rules=["Work Authorization"],
        source_id=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Work Authorization & Industry Trenching Standards",
    ),
    EnergyHazardType.DROPPED_OBJECTS: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.DROPPED_OBJECTS,
        name="Dropped Objects & Overhead Hazards (Gravitational Kinetic Energy)",
        energy_manifestation="Gravitational kinetic energy of tools, scaffolding clamps, bolts, drill collars, or floodlights falling from elevated structures.",
        release_mechanism="Tool dropped from hand, structural vibration loosening bolts, hoist snagging overhead fixture, wind dislodging loose plank.",
        exposure_mechanisms=["Personnel working below elevated work platform", "Walking through un-barricaded drop zone", "Working on lower level of scaffold"],
        worker_positions=["Directly underneath overhead scaffolding", "In derrick floor red zone during mast operations", "Beneath pipe bridge"],
        critical_direct_controls=["100% Tool lanyards tethered to structure/worker", "Heavy-duty overhead drop netting / debris mesh", "Engineered toe boards (> 150mm) on all elevated decks", "Positive drop-zone red-zone physical barriers"],
        indirect_controls=["Dropped object inspection register (DROPS)", "Pre-shift overhead sweep", "Tool inventory sheet"],
        effective_states=["Tool lanyard caught dropped torque wrench preventing fall", "Drop zone netting arrested dynamic weight of fallen clamp", "Hard barricading prevented personnel entering under derrick floor"],
        compromised_states=["Drop zone netting was absent and clamp dropped into walkway", "Untethered wrench slipped and fell 12 metres", "Object fell and struck hard hat"],
        credible_consequences=["DROPPED_OBJECT", "STRUCK_BY", "CRUSHING", "FATALITY"],
        barrier_interruption_mechanisms=["Overhead safety netting arrested dynamic weight of dropped equipment before reaching personnel level"],
        applicable_iogp_rules=["Working at Height", "Safe Mechanical Lifting"],
        source_id=SourceAuthority.IOGP_459,
        source_section="IOGP Report 459 Working at Height & DROPS Guidance",
    ),
    EnergyHazardType.LOW_ENERGY_GENERAL: HazardFamilyDefinition(
        hazard_type=EnergyHazardType.LOW_ENERGY_GENERAL,
        name="Low Energy / Non-SIF Operational Activity",
        energy_manifestation="Low-density physical energy without serious injury or fatality capability (minor drips, level walking, paper handling).",
        release_mechanism="Minor leak, small tool slip at floor level, routine surface moisture.",
        exposure_mechanisms=["Normal routine plant ambulation", "Handling small hand tools on grade"],
        worker_positions=["On grade walkway", "At workshop bench", "In control room"],
        critical_direct_controls=["Standard housekeeping", "Ordinary hand tools"],
        indirect_controls=["Routine workplace walkthrough", "Daily briefing"],
        effective_states=["Condition observed and handled under routine maintenance"],
        compromised_states=["Minor drip or scratch occurred without high energy release"],
        credible_consequences=["MINOR_FIRST_AID", "NO_INJURY"],
        barrier_interruption_mechanisms=["Not applicable; no high-energy SIF vector present"],
        applicable_iogp_rules=[],
        source_id=SourceAuthority.EEI_SCL,
        source_section="EEI SCL 2021 Section 3.2 Non-High-Energy Incidents",
    ),
}

HAZARD_FAMILY_CATALOG["hydrocarbon_flammable_release"] = HAZARD_FAMILY_CATALOG[EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE]


def get_hazard_family(energy_type: str) -> Optional[HazardFamilyDefinition]:
    """Retrieves authoritative hazard family definition modeling the full state space."""
    return HAZARD_FAMILY_CATALOG.get(energy_type)


get_hazard_definition = get_hazard_family
