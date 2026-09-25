"""
Action Mappings & Hierarchy of Controls Action Engine
apps/incidents/knowledge/action_mappings.py

Authoritative Evidence-Grounded Corrective Action & Next-Step Engine for Foresight.
Consumes the canonical structured reasoning output produced by the PSIF reasoning layer.

Operates strictly as:
INCIDENT → STRUCTURED EVIDENCE → REASONING STATE → CONTROL CONDITION → APPLICABLE RULE → ACTION MAPPING → CONTEXTUALIZED ACTION

Design Principles:
- Actions never influence PSIF inference; actions are derived strictly downstream.
- No free-form safety advice or unconstrained LLM hallucinations.
- Every action is traceable to triggering evidence, critical control, rule, and verified source.
- Action urgency is qualitatively prioritized (CRITICAL, HIGH, MEDIUM, LOW, INFO).
- Positive control learning is recommended for HIGH_ENERGY_CONTROLLED capacity cases.
- Missing evidence gathering is prioritized for INSUFFICIENT_INFORMATION.
- Neutral evidence verification is generated for CONFLICTING_EVIDENCE without assuming facts.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Set
from apps.incidents.knowledge.controls import ControlHierarchyType, ControlState
from apps.incidents.knowledge.energy_hazards import EnergyHazardType
from apps.incidents.knowledge.sources import SourceAuthority, ProvenanceTier


# ── Action Categories (7 Canonical Classes) ───────────────────────────────────

class ActionCategory:
    IMMEDIATE_ACTION = "IMMEDIATE_ACTION"
    CONTROL_RESTORATION = "CONTROL_RESTORATION"
    VERIFICATION_ACTION = "VERIFICATION_ACTION"
    CORRECTIVE_ACTION = "CORRECTIVE_ACTION"
    PREVENTIVE_ACTION = "PREVENTIVE_ACTION"
    ESCALATION_ACTION = "ESCALATION_ACTION"
    POSITIVE_LEARNING_ACTION = "POSITIVE_LEARNING_ACTION"


# Backwards compatibility alias
ActionClass = ActionCategory


# ── Qualitative Urgency Tiers ─────────────────────────────────────────────────

class ActionUrgency:
    CRITICAL = "CRITICAL"  # Immediate intervention required (active open hazard)
    HIGH = "HIGH"          # Within 24 hours / before work resumption
    MEDIUM = "MEDIUM"      # Within 7 days / standard operational planning
    LOW = "LOW"            # Within 30 days / routine maintenance & positive learning
    INFO = "INFO"          # Informational / documentation only


# ── Canonical Grounded Action Dataclass ────────────────────────────────────────

@dataclass
class ActionRecommendation:
    """
    Structured action recommendation linked to evidence, barrier hierarchy, and source provenance.
    Contains both canonical Task 6 fields and backward-compatible aliases.
    """
    action_id: str
    title: str
    action_type: str
    urgency: str
    description: str
    reason: str
    triggering_evidence: str
    hazard: str
    control: str
    control_state: str
    applicable_rule: str
    verification_steps: List[str]
    source: Dict[str, Any] = field(default_factory=lambda: {
        "source_id": SourceAuthority.FORESIGHT_ANALYTICAL,
        "provenance_tier": ProvenanceTier.FORESIGHT_ANALYTICAL,
        "citation": "Foresight Grounded Action Engine v1.0",
        "verifiable": True,
    })
    library_version: str = "action_library_v1"
    hierarchy_level: str = ControlHierarchyType.DIRECT_ENGINEERED_CONTROL
    target_barrier: Optional[str] = None
    regulatory_reference: Optional[str] = None

    # Backward-compatible property accessors
    @property
    def category(self) -> str:
        return self.action_type

    @property
    def priority(self) -> str:
        return self.urgency

    @property
    def control_addressed(self) -> str:
        return self.control

    @property
    def rule_addressed(self) -> str:
        return self.applicable_rule

    @property
    def verification_method(self) -> List[str]:
        return self.verification_steps

    @property
    def provenance(self) -> Dict[str, Any]:
        return self.source

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to complete schema containing canonical fields and compatibility aliases."""
        return {
            "action_id": self.action_id,
            "title": self.title,
            "action_type": self.action_type,
            "category": self.action_type,
            "urgency": self.urgency,
            "priority": self.urgency,
            "description": self.description,
            "reason": self.reason,
            "triggering_evidence": self.triggering_evidence,
            "hazard": self.hazard,
            "control": self.control,
            "control_addressed": self.control,
            "control_state": self.control_state,
            "applicable_rule": self.applicable_rule,
            "rule_addressed": self.applicable_rule,
            "verification_steps": list(self.verification_steps),
            "verification_method": list(self.verification_steps),
            "source": dict(self.source) if isinstance(self.source, dict) else self.source,
            "provenance": dict(self.source) if isinstance(self.source, dict) else self.source,
            "hierarchy_level": self.hierarchy_level,
            "target_barrier": self.target_barrier or self.control,
            "regulatory_reference": self.regulatory_reference,
            "library_version": self.library_version,
        }


# ── Authoritative 15-Hazard Family Grounded Action Catalogs ───────────────────

def _get_hazard_catalog_actions(
    hazard_type: str,
    control_state: str,
    internal_state: str,
    exposure_state: str,
    trigger_text: str,
    control_name: str,
    rule_name: str,
    high_priority_review: bool = False,
) -> List[ActionRecommendation]:
    """
    Returns hazard-specific, evidence-grounded action recommendations across all 15 hazard families.
    """
    actions: List[ActionRecommendation] = []
    hz = hazard_type.lower()

    # ──────────────────────────────────────────────────────────────────────────
    # 1. WORKING AT HEIGHT
    # ──────────────────────────────────────────────────────────────────────────
    if "height" in hz or "gravity" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Working at Height)",
            "section": "Rule 1: Working at Height Start Work Checks",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-WAH-IMM-01",
                title="Halt Elevated Work & Evacuate Unprotected Fall Zone",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately cease work on elevated platforms or unguarded edges. Guide workers to safe ground.",
                reason="High-energy gravity fall hazard exists with compromised fall protection and active worker exposure.",
                triggering_evidence=trigger_text or "Fall hazard over 2 meters with failed or absent fall arrest equipment.",
                hazard=EnergyHazardType.WORKING_AT_HEIGHT,
                control=control_name or "100% Fall Protection System",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Working at Height",
                verification_steps=[
                    "Confirm all workers have safely transitioned off elevated work surface",
                    "Tag out compromised scaffold or uncertified anchor point",
                    "Erect physical barricades at platform access ladder",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-WAH-RES-01",
                title="Re-establish Certified Fall Arrest System & Anchor Points",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Install certified 5000-lb (22.2 kN) anchor points and equip workers with 100% dual-tie-off self-retracting lifelines.",
                reason="Direct engineered fall protection was missing or compromised during elevated intervention.",
                triggering_evidence=f"Fall protection condition evaluated as {control_state}.",
                hazard=EnergyHazardType.WORKING_AT_HEIGHT,
                control=control_name or "Engineered Fall Arrest Anchor",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Working at Height",
                verification_steps=[
                    "Competent person structural inspection and tag sign-off of anchor beam",
                    "Pre-use inspection of full body harnesses and double lanyards",
                    "Verify 100% continuous tie-off protocol briefed at toolbox talk",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-WAH-VER-01",
                title="Conduct Pre-Climb Fall Clearance & Equipment Verification",
                action_type=ActionCategory.VERIFICATION_ACTION,
                urgency=ActionUrgency.HIGH,
                description="Calculate total fall clearance margin and verify harness fit before authorizing climb.",
                reason="Verification is mandatory before personnel re-enter elevated work zones.",
                triggering_evidence=f"Control state {control_state} requires formal pre-resumption sign-off.",
                hazard=EnergyHazardType.WORKING_AT_HEIGHT,
                control=control_name or "Fall Clearance Calculation",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Working at Height",
                verification_steps=[
                    "Calculate fall clearance margin including deceleration distance and harness stretch",
                    "Inspect lanyard snap hooks for positive double-action locking",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.PROCEDURAL_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 2. SUSPENDED LOADS / MECHANICAL LIFTING
    # ──────────────────────────────────────────────────────────────────────────
    elif "lift" in hz or "suspended" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Safe Mechanical Lifting)",
            "section": "Rule 8: Safe Mechanical Lifting Start Work Checks",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-LIFT-IMM-01",
                title="Cease Crane Hoisting & Clear Personnel from Drop Zone",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately lower suspended load to stable ground or halt crane hoist. Evacuate all personnel from the swing and drop radius.",
                reason="Suspended load presents gravitational crush potential with workers inside the drop radius.",
                triggering_evidence=trigger_text or "Worker positioned in drop radius under suspended load with failed rigging or barrier.",
                hazard=EnergyHazardType.SUSPENDED_LOADS,
                control=control_name or "Exclusion Zone Perimeter",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Safe Mechanical Lifting",
                verification_steps=[
                    "Confirm crane hoist motion stopped and load safely grounded",
                    "Verify zero personnel standing beneath suspended boom or load",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-LIFT-RES-01",
                title="Establish Hard Exclusion Barricade & Rigging Recertification",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Erect rigid physical barricading around the maximum swing radius and replace uncertified slings with load-tested rigging.",
                reason="Physical segregation barrier was breached or absent during mechanical lifting operations.",
                triggering_evidence=f"Lifting exclusion condition evaluated as {control_state}.",
                hazard=EnergyHazardType.SUSPENDED_LOADS,
                control=control_name or "Rigid Cordoned Exclusion Zone",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Safe Mechanical Lifting",
                verification_steps=[
                    "Erect rigid timber or chain barrier around 100% of load swing radius",
                    "Inspect sling inspection colour code and WLL certification tags",
                    "Deploy tag lines of adequate length to prevent manual load touching",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 3. STORED PRESSURE / LINE BREAKING
    # ──────────────────────────────────────────────────────────────────────────
    elif "pressure" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Energy Isolation)",
            "section": "Rule 3: Energy Isolation Start Work Checks",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-PRESS-IMM-01",
                title="Emergency Halt of Pressure Intervention & Line Depressurization",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately halt line breaking, unbolting, or hot tapping. Evacuate personnel from the pressurized fluid release path.",
                reason="Stored energy exceeds 100 psi with compromised isolation, presenting severe injection or blast trauma.",
                triggering_evidence=trigger_text or "Pressure line cracked without verified lockout or depressurization.",
                hazard=EnergyHazardType.PRESSURE_STORED,
                control=control_name or "Double Block and Bleed Isolation",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Close upstream root isolation valves and apply lockout padlocks",
                    "Clear personnel to safe distance outside line-of-fire",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-PRESS-RES-01",
                title="Restore Positive Double Block & Bleed with Blind Flange",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Establish positive physical isolation using spectacle blinds or slip spades and vent residual pressure to zero.",
                reason="Isolation was bypassed, unverified, or valve passed residual pressure into active work zone.",
                triggering_evidence=f"Pressure isolation state evaluated as {control_state}.",
                hazard=EnergyHazardType.PRESSURE_STORED,
                control=control_name or "Positive Mechanical Blinding",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Install certified blind spade rated for line design pressure",
                    "Lock bleed valve in open position with personal padlock",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-PRESS-VER-01",
                title="Verify Zero Stored Energy via Calibrated Gauge & Bleed Vent",
                action_type=ActionCategory.VERIFICATION_ACTION,
                urgency=ActionUrgency.HIGH,
                description="Verify zero pressure across all bleed ports using a calibrated gauge before cracking any flange bolts.",
                reason="Physical verification of zero energy is required before containment is opened.",
                triggering_evidence=f"Control state {control_state} requires definitive zero-energy test.",
                hazard=EnergyHazardType.PRESSURE_STORED,
                control=control_name or "Zero Energy Verification Protocol",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Check pressure gauge confirms 0.0 psig",
                    "Open low-point bleeder to confirm zero fluid drainage",
                    "Loosen flange bolts away from technician body (line-of-fire defense)",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.PROCEDURAL_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 4. ELECTRICAL ENERGY
    # ──────────────────────────────────────────────────────────────────────────
    elif "electr" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Energy Isolation)",
            "section": "Rule 3: Electrical Lockout and Test-Before-Touch",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-ELEC-IMM-01",
                title="Immediate Power Disconnect & Arc Flash Boundary Clearance",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Open main upstream circuit breaker immediately. Evacuate personnel outside the arc flash boundary.",
                reason="Energized electrical circuit (>50V) exposed without lockout, presenting electrocution and arc flash peril.",
                triggering_evidence=trigger_text or "Electrical intervention conducted without de-energization or lockout.",
                hazard=EnergyHazardType.ELECTRICAL,
                control=control_name or "Electrical Breaker Lockout",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Trip main electrical breaker and open physical disconnect switch",
                    "Cordon off electrical panel with danger high voltage signage",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-ELEC-RES-01",
                title="Apply Personal LOTO Padlocks & Temporary Grounding Clamps",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Attach personal safety padlocks and danger tags to circuit disconnect. Install certified protective earthing grounds.",
                reason="Electrical de-energization controls were absent or defeated.",
                triggering_evidence=f"Electrical control condition evaluated as {control_state}.",
                hazard=EnergyHazardType.ELECTRICAL,
                control=control_name or "Lockout / Tagout with Protective Grounding",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Lock disconnect handle in off position with personal master padlock",
                    "Fit danger lockout tags with authorized technician signature and contact",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-ELEC-VER-01",
                title="Execute Mandatory Three-Point Test-Before-Touch Voltage Check",
                action_type=ActionCategory.VERIFICATION_ACTION,
                urgency=ActionUrgency.HIGH,
                description="Verify zero voltage using a calibrated multi-meter: test on known live source, test target circuit, re-test known live source.",
                reason="Zero electrical energy must be physically verified before physical touch.",
                triggering_evidence=f"Control state {control_state} requires formal voltage verification.",
                hazard=EnergyHazardType.ELECTRICAL,
                control=control_name or "Test-Before-Touch Protocol",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Verify multi-meter on known live 120V/480V circuit",
                    "Test all phase-to-phase and phase-to-ground conductors on target equipment (must read 0.0V)",
                    "Re-verify multi-meter on known live circuit to confirm tester did not fail",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.PROCEDURAL_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 5. ROTATING EQUIPMENT / MECHANICAL MOTION
    # ──────────────────────────────────────────────────────────────────────────
    elif "stored" not in hz and ("rotat" in hz or "mechanical" in hz):
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Bypassing Safety Controls)",
            "section": "Rule 2: Machine Guarding and Safety Interlocks",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-MECH-IMM-01",
                title="Emergency Machinery E-Stop & Drive Motor Isolation",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Actuate emergency stop trip line immediately and shut off motor drive. Do not touch moving or jammed rotating components.",
                reason="Unguarded or unisolated rotating nip points create immediate amputation and entanglement trauma.",
                triggering_evidence=trigger_text or "Machine guard removed while conveyor or rotating shaft was running.",
                hazard=EnergyHazardType.ROTATING_EQUIPMENT,
                control=control_name or "Interlocked Machine Guarding",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Bypassing Safety Controls",
                verification_steps=[
                    "Depress emergency stop button and verify motor comes to complete standstill",
                    "Tag out electrical disconnect switch feeding machine motor",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-MECH-RES-01",
                title="Re-install and Secure Bolted Machine Guard Enclosure",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Securely fasten fixed steel guards over all drive couplings, pulleys, sprockets, and in-running nip points.",
                reason="Critical physical barrier was removed or defeated during equipment operation.",
                triggering_evidence=f"Guarding condition evaluated as {control_state}.",
                hazard=EnergyHazardType.ROTATING_EQUIPMENT,
                control=control_name or "Fixed Bolted Enclosure Guard",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Bypassing Safety Controls",
                verification_steps=[
                    "Bolt guard firmly to frame with tamper-resistant fasteners",
                    "Verify interlock limit switch cuts power when guard is opened",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 6. VEHICLE & MOBILE EQUIPMENT
    # ──────────────────────────────────────────────────────────────────────────
    elif "vehic" in hz or "mobile" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Driving)",
            "section": "Rule 7: Safe Driving & Pedestrian Segregation",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-VEH-IMM-01",
                title="Halt Mobile Equipment Operation in Shared Pedestrian Area",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Stop all forklift, loader, and heavy truck movement in the shared area. Clear ground personnel from vehicle travel paths.",
                reason="Unsegregated heavy vehicle motion creates fatal crush and impact potential.",
                triggering_evidence=trigger_text or "Pedestrian worker inside moving vehicle path without physical segregation.",
                hazard=EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT,
                control=control_name or "Physical Walkway Segregation",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Driving",
                verification_steps=[
                    "Signal equipment operators to park, set emergency brake, and shut down engines",
                    "Direct pedestrian crew to designated safe walkway zones",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-VEH-RES-01",
                title="Install Heavy-Duty Physical Barriers & Dedicated Spotter Marshalling",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Erect concrete Jersey barriers or steel guardrails separating pedestrian walkways from mobile equipment aisles.",
                reason="Physical segregation controls between mobile plant and ground personnel failed or were absent.",
                triggering_evidence=f"Vehicle segregation state evaluated as {control_state}.",
                hazard=EnergyHazardType.VEHICLE_MOBILE_EQUIPMENT,
                control=control_name or "Concrete/Steel Traffic Segregation Barrier",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Driving",
                verification_steps=[
                    "Install physical crash-rated barriers between vehicle lane and walkways",
                    "Assign dedicated traffic marshall with high-visibility vest and air horn",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 7. HOT WORK / THERMAL IGNITION
    # ──────────────────────────────────────────────────────────────────────────
    elif "hot_work" in hz or "welding" in hz or "torch" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Hot Work)",
            "section": "Rule 6: Hot Work Controls & Spark Containment",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-HW-IMM-01",
                title="Extinguish Hot Work Ignition Sources & Halt Welding Operations",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately extinguish torch flames, cut power to welding machines, and cease grinding operations.",
                reason="Thermal ignition source operating in presence of potential flammable hydrocarbons or without verified permit.",
                triggering_evidence=trigger_text or "Hot work conducted without atmospheric clearance or spark containment habitat.",
                hazard=EnergyHazardType.HOT_WORK_IGNITION,
                control=control_name or "Continuous Atmospheric Gas Testing",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Hot Work",
                verification_steps=[
                    "Shut off oxygen/acetylene gas cylinders at main manifold valves",
                    "Isolate welding transformer power supplies",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-HW-RES-01",
                title="Erect Sealed Pressurized Welding Habitat & Establish Fire Watch",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Construct fire-retardant welding habitat with positive overpressure and clear all combustibles within 15 meters.",
                reason="Spark containment barrier or atmospheric monitoring controls were degraded or missing.",
                triggering_evidence=f"Hot work control state evaluated as {control_state}.",
                hazard=EnergyHazardType.HOT_WORK_IGNITION,
                control=control_name or "Pressurized Spark Containment Habitat",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Hot Work",
                verification_steps=[
                    "Confirm positive overpressure differential inside welding habitat",
                    "Position dedicated fire watch equipped with pressurized water and dry powder extinguisher",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-HW-VER-01",
                title="Conduct Multi-Gas Atmospheric Sniffer Test (0.0% LEL)",
                action_type=ActionCategory.VERIFICATION_ACTION,
                urgency=ActionUrgency.HIGH,
                description="Sample atmosphere at potential vapor trap points using calibrated 4-gas detector before striking any arc.",
                reason="Atmosphere must be verified free of combustible vapors before hot work permits are signed.",
                triggering_evidence=f"Hot work state {control_state} requires formal gas test clearance.",
                hazard=EnergyHazardType.HOT_WORK_IGNITION,
                control=control_name or "Atmospheric Gas Clearance Test",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Hot Work",
                verification_steps=[
                    "Confirm calibrated sniffer reads 0.0% LEL across work area",
                    "Record gas tester serial number, calibration date, and readings on permit",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.PROCEDURAL_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 8. CONFINED SPACE
    # ──────────────────────────────────────────────────────────────────────────
    elif "confined" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Confined Space Entry)",
            "section": "Rule 4: Confined Space Entry Start Work Checks",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-CONF-IMM-01",
                title="Immediate Evacuation of Confined Space & Entry Prohibition",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately order all entrants out of the vessel/tank. Post sentry and barrier to prevent re-entry.",
                reason="Confined space entry conducted without verified atmospheric testing, positive isolation, or ventilation.",
                triggering_evidence=trigger_text or "Worker entered confined space without verified atmosphere monitoring.",
                hazard=EnergyHazardType.CONFINED_SPACE,
                control=control_name or "Continuous Forced Air Ventilation",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Confined Space Entry",
                verification_steps=[
                    "Confirm 100% of personnel logged on entry board are outside the manway",
                    "Place physical padlock / barrier bar across vessel manway entrance",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-CONF-RES-01",
                title="Re-establish Continuous Forced Ventilation & Positive Pipe Blinding",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Connect pneumatic air mover providing at least 20 air changes per hour and bolt spectacle blinds on all inlet nozzles.",
                reason="Direct engineering ventilation and isolation controls were absent or compromised.",
                triggering_evidence=f"Confined space control condition evaluated as {control_state}.",
                hazard=EnergyHazardType.CONFINED_SPACE,
                control=control_name or "Positive Nozzle Blinding and Air Mover",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Confined Space Entry",
                verification_steps=[
                    "Verify spectacle blinds installed on all feed, fuel, and chemical lines",
                    "Confirm air mover exhaust duct discharges to safe exterior location",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-CONF-VER-01",
                title="Execute 4-Gas Multi-Level Internal Atmospheric Survey",
                action_type=ActionCategory.VERIFICATION_ACTION,
                urgency=ActionUrgency.HIGH,
                description="Sample atmosphere at top, middle, and bottom: Oxygen (19.5–23.5%), LEL (0%), H2S (<10 ppm), CO (<25 ppm).",
                reason="Atmospheric safety must be verified and logged continuously during confined space operations.",
                triggering_evidence=f"Control state {control_state} requires certified entry gas test.",
                hazard=EnergyHazardType.CONFINED_SPACE,
                control=control_name or "Certified Multi-Level Gas Survey",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Confined Space Entry",
                verification_steps=[
                    "Record gas levels at 3 depth strata inside vessel prior to entry",
                    "Designate trained hole watch with emergency retrieval winch and horn",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.PROCEDURAL_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 9. CHEMICAL / FLAMMABLE HYDROCARBON RELEASE
    # ──────────────────────────────────────────────────────────────────────────
    elif "chemical" in hz or "hydrocarbon" in hz or "flammable" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Energy Isolation)",
            "section": "Process Safety & Containment Standards",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-CHEM-IMM-01",
                title="Activate Emergency Shutdown (ESD) & Evacuate Vapor Dispersion Area",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Trip ESD valve immediately to isolate process fluid inventory. Evacuate personnel crosswind from vapor cloud.",
                reason="Uncontrolled hydrocarbon or toxic chemical release into active work area.",
                triggering_evidence=trigger_text or "Hydrocarbon release with unisolated feed line or leaking flange.",
                hazard=EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE,
                control=control_name or "Process Emergency Shutdown Valve",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Trigger ESD push button and verify valve status panel confirms closed position",
                    "Confirm all workers muster at designated upwind assembly point",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-CHEM-RES-01",
                title="Torque Flange Fasteners or Install Certified Pipe Clamp Enclosure",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Replace degraded gasket and re-torque studs to engineered specification or install certified containment clamp.",
                reason="Containment barrier integrity failed during live process operation.",
                triggering_evidence=f"Containment control condition evaluated as {control_state}.",
                hazard=EnergyHazardType.HYDROCARBON_FLAMMABLE_RELEASE,
                control=control_name or "Engineered Flange Containment Joint",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Apply calibrated torque wrench cross-pattern bolt tightening",
                    "Conduct helium leak test or sniffer clearance before re-introducing hydrocarbons",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 10. TOXIC / ASPHYXIANT ATMOSPHERE (H2S / NITROGEN)
    # ──────────────────────────────────────────────────────────────────────────
    elif "toxic" in hz or "asphyx" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 / OISD-GDN-192",
            "section": "Toxic Gas & Asphyxiant Safety Standards",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-TOX-IMM-01",
                title="Don Escape Breathing Apparatus & Evacuate Crosswind to Muster Station",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately don 15-minute emergency escape breathing apparatus (EEBA) and evacuate crosswind to muster point.",
                reason="Toxic/asphyxiant gas detected in breathing zone without respiratory protection.",
                triggering_evidence=trigger_text or "Toxic gas release or unventilated nitrogen purge.",
                hazard=EnergyHazardType.TOXIC_ASPHYXIANT_ATMOSPHERE,
                control=control_name or "Self-Contained Breathing Apparatus & Fixed Detection",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Observe wind sock and lead crew crosswind to elevated muster point",
                    "Sound facility general alarm and initiate toxic gas response protocol",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-TOX-RES-01",
                title="Reinstate Cascade Air Breathing System & Bump-Test Personal Monitors",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Equip workers with positive-pressure supplied air respirators and bump-test all personal H2S/O2 detectors.",
                reason="Respiratory defense or detection barrier was compromised during hazardous entry.",
                triggering_evidence=f"Toxic protection state evaluated as {control_state}.",
                hazard=EnergyHazardType.TOXIC_ASPHYXIANT_ATMOSPHERE,
                control=control_name or "Supplied Cascade Breathing Air System",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Energy Isolation",
                verification_steps=[
                    "Test cascade breathing air manifold pressure and emergency escape cylinder pressures",
                    "Verify each personal detector passes bump test with calibration test gas",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 11. LINE OF FIRE / PROJECTILE / WHIPPING HOSE
    # ──────────────────────────────────────────────────────────────────────────
    elif "line_of_fire" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "IOGP Report 459 (Line of Fire)",
            "section": "Rule 5: Line of Fire Clearance and Blast Barricades",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-LOF-IMM-01",
                title="Remove Personnel from Release Trajectory & Blast Radius",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Halt line operations and direct workers out of the direct projection or whip trajectory.",
                reason="Personnel positioned directly inside release trajectory of pressurized or tensioned energy.",
                triggering_evidence=trigger_text or "Worker standing in line of fire of pressurized fitting or moving counterweight.",
                hazard=EnergyHazardType.LINE_OF_FIRE,
                control=control_name or "Deflection Shielding and Whip Checks",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Line of Fire",
                verification_steps=[
                    "Verify workers positioned outside calculated 45-degree discharge cone",
                    "Secure safety whip check cables across all high-pressure hose couplings",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-LOF-RES-01",
                title="Install Whip Checks & Physical Deflection Shields",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Fit rated whip-check cables across high-pressure hose joints and install physical blast / deflection shields between pressurized or tensioned components and work area.",
                reason="Line of fire direct barrier (deflection shielding or whip restraint) was absent, bypassed, or failed.",
                triggering_evidence=f"Line of fire direct control evaluated as {control_state}.",
                hazard=EnergyHazardType.LINE_OF_FIRE,
                control=control_name or "Deflection Shielding and Whip Checks",
                control_state=control_state,
                applicable_rule=rule_name or "IOGP Line of Fire",
                verification_steps=[
                    "Verify rated whip check cables installed with no slack across hose couplings",
                    "Verify physical deflection shield secured and covers direct line of potential release",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 12. EXCAVATION & GROUND COLLAPSE
    # ──────────────────────────────────────────────────────────────────────────
    elif "excavat" in hz or "trench" in hz:
        src = {
            "source_id": SourceAuthority.INDIAN_OISD,
            "provenance_tier": ProvenanceTier.INDIAN_REGULATORY,
            "document": "OISD-GDN-192 / OSHA 1926 Subpart P",
            "section": "Excavation & Trench Shoring Standards",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-EXC-IMM-01",
                title="Evacuate Trench Excavation Immediately & Stop Nearby Heavy Machinery",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately order workers out of the trench. Shut down excavators or trucks operating within 5 meters.",
                reason="Un-shored trench wall (>1.2m deep) presents immediate engulfment and suffocation risk.",
                triggering_evidence=trigger_text or "Personnel working in trench without certified shoring or safe benching.",
                hazard=EnergyHazardType.EXCAVATION_GROUND_COLLAPSE,
                control=control_name or "Certified Trench Shoring Box",
                control_state=control_state,
                applicable_rule=rule_name or "Excavation Safety Standard",
                verification_steps=[
                    "Confirm all workers exited trench via secured ladder",
                    "Erect perimeter warning barricade 1.5 meters from trench lip",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-EXC-RES-01",
                title="Install Engineered Trench Shield or Benching to Safe Repose Angle",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Install certified aluminum hydraulic shoring or bench soil back at a 1:1.5 slope. Set spoil pile back at least 1.0 meter.",
                reason="Trench side wall collapse protection was absent or failed.",
                triggering_evidence=f"Excavation protection state evaluated as {control_state}.",
                hazard=EnergyHazardType.EXCAVATION_GROUND_COLLAPSE,
                control=control_name or "Aluminum Hydraulic Trench Shield",
                control_state=control_state,
                applicable_rule=rule_name or "Excavation Safety Standard",
                verification_steps=[
                    "Competent person daily soil classification and shoring sign-off",
                    "Verify spoil pile is placed at least 1.0 meter from excavation edge",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 13. DROPPED OBJECTS
    # ──────────────────────────────────────────────────────────────────────────
    elif "drop" in hz:
        src = {
            "source_id": SourceAuthority.IOGP_459,
            "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
            "document": "DROPS Best Practice & IOGP Report 459",
            "section": "Dropped Object Prevention Scheme (DROPS)",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-DROP-IMM-01",
                title="Clear Lower Deck Area & Cordon Off Overhead Drop Hazard Zone",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately clear workers from lower decks beneath elevated operations. Stop elevated tool handling.",
                reason="Unsecured tools or equipment at elevation present life-threatening impact trauma to personnel below.",
                triggering_evidence=trigger_text or "Object dropped from elevation into active work deck without secondary retention.",
                hazard=EnergyHazardType.DROPPED_OBJECTS,
                control=control_name or "Tool Lanyard Retention & Safety Netting",
                control_state=control_state,
                applicable_rule=rule_name or "Dropped Object Prevention Scheme",
                verification_steps=[
                    "Verify drop area is cordoned off with red warning tape and danger signs",
                    "Confirm elevated crew tethers 100% of handheld tools",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-DROP-RES-01",
                title="Fit Certified Tool Tether Lanyards & Platform Toe-Boards",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Equip all tools with certified tethers secured to worker wrist or structure; install 4-inch solid toe-boards.",
                reason="Secondary dropped object retention barriers were missing or breached.",
                triggering_evidence=f"Dropped object controls evaluated as {control_state}.",
                hazard=EnergyHazardType.DROPPED_OBJECTS,
                control=control_name or "Tool Tether and Toe-Board Assembly",
                control_state=control_state,
                applicable_rule=rule_name or "Dropped Object Prevention Scheme",
                verification_steps=[
                    "Inspect wrist lanyards and tool attachment collars for rated tool weight",
                    "Confirm solid toe-boards installed on all open edges of elevated grating",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 14. STORED MECHANICAL ENERGY (SPRINGS / HYDRAULIC ACCUMULATORS)
    # ──────────────────────────────────────────────────────────────────────────
    elif "stored_mech" in hz or "spring" in hz:
        src = {
            "source_id": SourceAuthority.EEI_SCL,
            "provenance_tier": ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
            "document": "EEI SCL Safety Classification and Learning",
            "section": "Mechanical Energy Isolation Protocols",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-SME-IMM-01",
                title="Halt Mechanical Adjustment & Stand Clear of Spring/Tension Discharge",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Immediately cease disassembly of spring-loaded or hydraulic tensioned components. Clear workers from trajectory.",
                reason="Stored mechanical compression or accumulator tension creates violent strike or crush trauma.",
                triggering_evidence=trigger_text or "Disassembly of spring/accumulator without mechanical pin or decompression.",
                hazard=EnergyHazardType.STORED_MECHANICAL_ENERGY,
                control=control_name or "Mechanical Locking Pin and Decompression Device",
                control_state=control_state,
                applicable_rule=rule_name or "Energy Isolation Standard",
                verification_steps=[
                    "Verify workers positioned clear of spring discharge vector",
                    "Do not remove retaining bolts until mechanical locking pin is engaged",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-SME-RES-01",
                title="Engage Positive Mechanical Locking Pin & Decompress Actuator",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Insert engineered steel locking pin to physically restrain spring travel and open accumulator bleed drain.",
                reason="Mechanical energy restraining barriers were not locked or bypassed.",
                triggering_evidence=f"Stored mechanical control state evaluated as {control_state}.",
                hazard=EnergyHazardType.STORED_MECHANICAL_ENERGY,
                control=control_name or "Positive Mechanical Locking Pin",
                control_state=control_state,
                applicable_rule=rule_name or "Energy Isolation Standard",
                verification_steps=[
                    "Insert hardened steel safety pin through actuator restraining hole",
                    "Confirm accumulator hydraulic gauge reads 0 psi and drain is open",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # 15. THERMAL EXTREMES / STEAM / CRYOGENIC
    # ──────────────────────────────────────────────────────────────────────────
    elif "thermal" in hz or "steam" in hz or "cryo" in hz:
        src = {
            "source_id": SourceAuthority.EEI_SCL,
            "provenance_tier": ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
            "document": "EEI SCL Energy Framework",
            "section": "Thermal Energy Barriers",
            "verifiable": True,
        }
        if internal_state == "PSIF_PATHWAY_OPEN":
            actions.append(ActionRecommendation(
                action_id="ACT-THERM-IMM-01",
                title="Isolate Steam / Cryogenic Supply & Evacuate Thermal Hazard Zone",
                action_type=ActionCategory.IMMEDIATE_ACTION,
                urgency=ActionUrgency.CRITICAL,
                description="Shut off high-pressure steam or cryogenic liquid supply valve immediately. Clear workers from release plume.",
                reason="High-temperature steam or cryogenic fluid creates immediate life-threatening thermal destruction.",
                triggering_evidence=trigger_text or "Steam or cryogenic piping uninsulated or unisolated during worker proximity.",
                hazard=EnergyHazardType.THERMAL_ENERGY,
                control=control_name or "Thermal Insulation Blanket and Steam Trap Isolation",
                control_state=control_state,
                applicable_rule=rule_name or "Energy Isolation Standard",
                verification_steps=[
                    "Close upstream steam manifold valve and lock handle",
                    "Clear personnel to safe unheated perimeter",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
            actions.append(ActionRecommendation(
                action_id="ACT-THERM-RES-01",
                title="Re-install Removable Thermal Insulation Jacketing & Drain Condensate",
                action_type=ActionCategory.CONTROL_RESTORATION,
                urgency=ActionUrgency.HIGH,
                description="Install multi-layer ceramic insulation blankets on bare steam pipes and confirm pipe surface temperature is <50°C.",
                reason="Thermal barrier insulation was missing or damaged.",
                triggering_evidence=f"Thermal control state evaluated as {control_state}.",
                hazard=EnergyHazardType.THERMAL_ENERGY,
                control=control_name or "Ceramic Thermal Insulation Jacketing",
                control_state=control_state,
                applicable_rule=rule_name or "Energy Isolation Standard",
                verification_steps=[
                    "Fasten insulation jacket tightly with stainless steel banding straps",
                    "Verify pipe outer surface temperature is below 50°C with infrared pyrometer",
                ],
                source=src,
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))

    # ──────────────────────────────────────────────────────────────────────────
    # FALLBACK FOR UNLISTED HIGH ENERGY HAZARDS
    # ──────────────────────────────────────────────────────────────────────────
    if not actions and internal_state == "PSIF_PATHWAY_OPEN":
        src = {
            "source_id": SourceAuthority.FORESIGHT_ANALYTICAL,
            "provenance_tier": ProvenanceTier.FORESIGHT_ANALYTICAL,
            "citation": "Foresight Grounded Action Engine (High Energy SCL Framework)",
            "verifiable": True,
        }
        actions.append(ActionRecommendation(
            action_id="ACT-GEN-IMM-01",
            title=f"Stop Work & Secure {hazard_type.replace('_', ' ').title()} Hazard Zone",
            action_type=ActionCategory.IMMEDIATE_ACTION,
            urgency=ActionUrgency.CRITICAL,
            description=f"Immediately halt affected operations until direct physical control over {hazard_type} is re-established.",
            reason=f"High-energy hazard ({hazard_type}) is uncontrolled with worker exposed, presenting SIF precursor potential.",
            triggering_evidence=trigger_text or f"Uncontrolled high-energy hazard ({hazard_type}) with compromised barrier.",
            hazard=hazard_type,
            control=control_name or "Direct Critical Barrier",
            control_state=control_state,
            applicable_rule=rule_name or "Stop Work Authority",
            verification_steps=[
                "Confirm work is suspended and equipment is de-energized",
                "Erect physical barricade around hazard perimeter",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
        ))
        actions.append(ActionRecommendation(
            action_id="ACT-GEN-RES-01",
            title=f"Restore and Inspect Direct Critical Control ({control_name or 'Direct Barrier'})",
            action_type=ActionCategory.CONTROL_RESTORATION,
            urgency=ActionUrgency.HIGH,
            description=f"Re-establish the required physical barrier or positive isolation before authorizing resumption of work.",
            reason=f"Critical direct control was evaluated as {control_state}.",
            triggering_evidence=f"Critical barrier condition evaluated as {control_state}.",
            hazard=hazard_type,
            control=control_name or "Direct Critical Barrier",
            control_state=control_state,
            applicable_rule=rule_name or "Critical Barrier Standard",
            verification_steps=[
                "Perform physical inspection of restored barrier",
                "Obtain supervisor sign-off on Start Work Checks",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
        ))

    # ──────────────────────────────────────────────────────────────────────────
    # ESCALATION FOR OPEN PSIF PATHWAYS (CONDITIONAL & EVIDENCE-GROUNDED)
    # ──────────────────────────────────────────────────────────────────────────
    if internal_state == "PSIF_PATHWAY_OPEN" and (control_state in [ControlState.BYPASSED, ControlState.FAILED, ControlState.ABSENT] or high_priority_review):
        src = {
            "source_id": SourceAuthority.FORESIGHT_ANALYTICAL,
            "provenance_tier": ProvenanceTier.FORESIGHT_ANALYTICAL,
            "citation": "Foresight SIF Precursor Governance Protocol",
            "verifiable": True,
        }
        actions.append(ActionRecommendation(
            action_id="ACT-GEN-ESC-01",
            title="Escalate for Formal SIF Precursor Incident Investigation",
            action_type=ActionCategory.ESCALATION_ACTION,
            urgency=ActionUrgency.HIGH,
            description="Escalate this SIF precursor event for formal HSE investigation according to applicable organizational procedure.",
            reason="High-energy hazard pathway was open with compromised critical direct control, meeting criteria for SIF precursor investigation.",
            triggering_evidence=f"Open PSIF pathway under rule '{rule_name or 'Critical Barrier Rule'}' with control state '{control_state}'.",
            hazard=hazard_type,
            control=control_name or "Direct Control",
            control_state=control_state,
            applicable_rule=rule_name or "SIF Precursor Investigation Standard",
            verification_steps=[
                "Log SIF precursor notification in HSE management system",
                "Appoint independent lead investigator qualified in barrier failure analysis",
                "Issue preliminary notification to operational management within 24 hours",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.ADMINISTRATIVE_CONTROL,
        ))

    return actions


# ── State-Based Master Generator ──────────────────────────────────────────────

def generate_grounded_actions(
    hazard_type: str,
    control_state: str,
    exposure_state: str,
    decision: str,
    internal_state: str,
    missing_items: Optional[List[Any]] = None,
    contradiction_details: Optional[str] = None,
    control_name: Optional[str] = None,
    rule_name: Optional[str] = None,
    trigger_text: Optional[str] = None,
    all_detected_hazards: Optional[List[str]] = None,
    high_priority_review: bool = False,
    sub_pathways: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Authoritative evidence-grounded action generation function.
    Strictly maps from reasoning state, control condition, and structured evidence to prioritized actions.

    Adheres to:
    - PSIF_PATHWAY_OPEN: Immediate, Control Restoration, Verification, Corrective, Escalation.
    - HIGH_ENERGY_CONTROLLED: Positive Learning and Verification/Inspection. (No unneeded corrective action).
    - LOW_ENERGY: Proportionate maintenance/preventive actions. (No emergency shutdowns).
    - INSUFFICIENT_INFORMATION: Targeted evidence-gathering actions. (No dramatic shutdown).
    - CONFLICTING_EVIDENCE: Neutral verification & physical fact-finding. (Never assumes either side).
    - Multi-hazard: Collects sub-pathway actions and deduplicates overlapping intents.
    """
    raw_actions: List[ActionRecommendation] = []
    effective_control_name = control_name or "Direct Critical Barrier"
    effective_rule_name = rule_name or "EEI SCL Safety Standard"
    clean_trigger = trigger_text or ""

    # ── CASE 1: HIGH ENERGY CONTROLLED -> POSITIVE LEARNING & VERIFICATION ─────
    if internal_state == "HIGH_ENERGY_CONTROLLED":
        src = {
            "source_id": SourceAuthority.EEI_SCL,
            "provenance_tier": ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
            "citation": "EEI SCL Capacity & Positive Learning Framework",
            "verifiable": True,
        }
        raw_actions.append(ActionRecommendation(
            action_id="ACT-POS-01",
            title="Document & Share Effective Direct Control Learning",
            action_type=ActionCategory.POSITIVE_LEARNING_ACTION,
            urgency=ActionUrgency.LOW,
            description=(
                f"Document the successful performance of the critical direct control ({effective_control_name}) "
                f"in the site barrier register. Share as a positive safety learning across operational crews."
            ),
            reason=f"High-energy hazard ({hazard_type}) was present, but direct control functioned effectively to prevent worker harm.",
            triggering_evidence=clean_trigger or f"Direct control ({effective_control_name}) held effectively under high-energy ({hazard_type}).",
            hazard=hazard_type,
            control=effective_control_name,
            control_state=ControlState.EFFECTIVE,
            applicable_rule=effective_rule_name,
            verification_steps=[
                "Record barrier performance metrics in the asset barrier integrity database",
                "Recognize personnel who adhered to verification checks and Start Work procedures",
                "Present positive barrier defense case study in quarterly safety bulletin",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.ADMINISTRATIVE_CONTROL,
        ))
        raw_actions.append(ActionRecommendation(
            action_id="ACT-VER-CAP-01",
            title="Post-Energy-Arrest Barrier Integrity Inspection",
            action_type=ActionCategory.VERIFICATION_ACTION,
            urgency=ActionUrgency.MEDIUM,
            description=(
                f"Inspect the physical barrier ({effective_control_name}) for wear, permanent deformation, or mechanical fatigue "
                f"following energy absorption to confirm continued readiness."
            ),
            reason="Physical barriers that successfully arrest or contain hazardous energy must be inspected prior to next duty cycle.",
            triggering_evidence=f"Barrier was dynamically challenged by {hazard_type} energy.",
            hazard=hazard_type,
            control=effective_control_name,
            control_state=ControlState.EFFECTIVE,
            applicable_rule=effective_rule_name,
            verification_steps=[
                "Conduct visual and non-destructive inspection for cracks or structural deformation",
                "Re-certify barrier for continued operational service",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
        ))

    # ── CASE 2: CONFLICTING EVIDENCE -> NEUTRAL VERIFICATION & HUMAN REVIEW ────
    elif internal_state == "CONFLICTING_EVIDENCE":
        src = {
            "source_id": SourceAuthority.FORESIGHT_ANALYTICAL,
            "provenance_tier": ProvenanceTier.FORESIGHT_ANALYTICAL,
            "citation": "Foresight Contradiction Resolution Protocol",
            "verifiable": True,
        }
        detail_msg = contradiction_details or "Conflicting records exist regarding barrier status or worker positioning."
        raw_actions.append(ActionRecommendation(
            action_id="ACT-CONF-01",
            title="Reconcile Contradictory Incident Statements via Physical Inspection",
            action_type=ActionCategory.VERIFICATION_ACTION,
            urgency=ActionUrgency.HIGH,
            description=(
                "Conduct an on-site physical inspection and review contemporaneous work records to resolve "
                "contradictory evidence statements. Do not assume either statement is factually correct."
            ),
            reason="Material contradictions prevent reliable automated safety determination and require empirical verification.",
            triggering_evidence=detail_msg,
            hazard=hazard_type,
            control=effective_control_name,
            control_state=ControlState.UNKNOWN,
            applicable_rule=effective_rule_name,
            verification_steps=[
                "Inspect physical isolation points, valve handles, and padlocks on-site",
                "Examine dated LOTO permits, gas testing logs, and telemetry recordings",
                "Conduct joint interview with reporting supervisor and affected workers",
                "Submit clarified evidence packet for senior HSE human adjudication",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.ADMINISTRATIVE_CONTROL,
        ))

    # ── CASE 3: INSUFFICIENT INFORMATION -> TARGETED EVIDENCE GATHERING ────────
    elif decision == "INSUFFICIENT_INFORMATION" or internal_state == "INSUFFICIENT_INFORMATION":
        src = {
            "source_id": SourceAuthority.FORESIGHT_ANALYTICAL,
            "provenance_tier": ProvenanceTier.FORESIGHT_ANALYTICAL,
            "citation": "Foresight Evidence Completion Protocol",
            "verifiable": True,
        }
        missing_text = "; ".join([getattr(m, "what", str(m)) for m in (missing_items or [])[:3]]) if missing_items else "Clarify worker position, de-energization confirmation, and barrier condition."
        raw_actions.append(ActionRecommendation(
            action_id="ACT-REQ-01",
            title="Complete Incident Investigation to Gather Missing SIF Evidence",
            action_type=ActionCategory.VERIFICATION_ACTION,
            urgency=ActionUrgency.HIGH if high_priority_review else ActionUrgency.MEDIUM,
            description=(
                f"Gather required operational evidence before closing this case: {missing_text}"
            ),
            reason="Essential factual dimensions are missing or uncorroborated, preventing definitive PSIF determination.",
            triggering_evidence=f"Missing evidence checklist: {missing_text}",
            hazard=hazard_type,
            control=effective_control_name,
            control_state=control_state or ControlState.UNKNOWN,
            applicable_rule=effective_rule_name,
            verification_steps=[
                "Interview operating personnel regarding pre-job Start Work Checks",
                "Obtain written isolation verification logs and permit-to-work sign-offs",
                "Document exact worker standoff distance and physical barrier positions",
                "Update incident report in system with verified barrier condition data",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.ADMINISTRATIVE_CONTROL,
        ))
        raw_actions.append(ActionRecommendation(
            action_id="ACT-REQ-02",
            title="Verify Physical Control State & Worker Positioning on Scene",
            action_type=ActionCategory.VERIFICATION_ACTION,
            urgency=ActionUrgency.HIGH if high_priority_review else ActionUrgency.MEDIUM,
            description=(
                "Inspect equipment on-site, examine isolation points or physical barriers, and interview personnel to establish whether workers were within the hazard exposure envelope."
            ),
            reason="Critical control integrity and exact worker standoff distances must be verified through physical inspection and witness statements before case closure.",
            triggering_evidence=f"Uncertain control/exposure state: {missing_text}",
            hazard=hazard_type,
            control=effective_control_name,
            control_state=control_state or ControlState.UNKNOWN,
            applicable_rule=effective_rule_name,
            verification_steps=[
                "Inspect physical equipment, isolation points, and barrier hardware on scene",
                "Review contemporaneous permits-to-work, isolation tags, and gas testing logs",
                "Interview involved crew members and operating personnel to confirm sequence of events",
                "Document verified barrier condition and personnel positioning in the incident record",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.ADMINISTRATIVE_CONTROL,
        ))

    # ── CASE 4: LOW ENERGY -> PROPORTIONATE HOUSEKEEPING & MAINTENANCE ────────
    elif internal_state == "LOW_ENERGY":
        src = {
            "source_id": SourceAuthority.EEI_SCL,
            "provenance_tier": ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
            "citation": "EEI SCL Low-Energy Baseline Standards",
            "verifiable": True,
        }
        raw_actions.append(ActionRecommendation(
            action_id="ACT-RNT-01",
            title="Resolve Low-Energy Anomaly under Routine Work Order",
            action_type=ActionCategory.CORRECTIVE_ACTION,
            urgency=ActionUrgency.LOW,
            description="Address observed minor physical deficiency (e.g. slip hazard, minor fluid seep) through standard facility maintenance.",
            reason="Low-energy physical condition lacks capacity for fatal or permanent disabling outcome; operational shutdown is not warranted.",
            triggering_evidence=clean_trigger or "Low energy density incident lacking high-energy SIF precursor potential.",
            hazard=hazard_type,
            control=effective_control_name,
            control_state=control_state,
            applicable_rule=effective_rule_name,
            verification_steps=[
                "Issue routine work order to facility maintenance team",
                "Verify housekeeping or minor surface repair is completed",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.ADMINISTRATIVE_CONTROL,
        ))
        raw_actions.append(ActionRecommendation(
            action_id="ACT-PREV-01",
            title="Routine Workplace Housekeeping & Inspection",
            action_type=ActionCategory.PREVENTIVE_ACTION,
            urgency=ActionUrgency.LOW,
            description="Incorporate affected area into monthly routine safety walkthrough to prevent minor defect accumulation.",
            reason="Standard preventive maintenance is sufficient for low-energy workplace anomalies.",
            triggering_evidence="Routine low-energy event.",
            hazard=hazard_type,
            control=effective_control_name,
            control_state=control_state,
            applicable_rule=effective_rule_name,
            verification_steps=[
                "Document walkthrough in area inspection register",
            ],
            source=src,
            hierarchy_level=ControlHierarchyType.ADMINISTRATIVE_CONTROL,
        ))

    # ── CASE 5: PSIF PATHWAY OPEN -> FULL STRUCTURED ACTION SUITE ──────────────
    elif internal_state == "PSIF_PATHWAY_OPEN":
        # Check if multi-hazard sub-pathways are provided
        hazards_to_process = []
        if all_detected_hazards and len(all_detected_hazards) > 1:
            for h in all_detected_hazards:
                if h not in hazards_to_process:
                    hazards_to_process.append(h)
        else:
            hazards_to_process = [hazard_type]

        for hz in hazards_to_process:
            sub_rule = effective_rule_name
            sub_ctrl = effective_control_name
            # If sub_pathways has details for this hazard, extract
            if sub_pathways:
                for sp in sub_pathways:
                    if sp.get("hazard_family") == hz or sp.get("hazard") == hz:
                        sub_rule = sp.get("rule_name") or sub_rule
                        sub_ctrl = sp.get("control_type") or sub_ctrl
                        break

            sub_actions = _get_hazard_catalog_actions(
                hazard_type=hz,
                control_state=control_state,
                internal_state=internal_state,
                exposure_state=exposure_state,
                trigger_text=clean_trigger,
                control_name=sub_ctrl,
                rule_name=sub_rule,
                high_priority_review=high_priority_review,
            )
            raw_actions.extend(sub_actions)

    # ── BARRIER & CRITICAL-CONTROL GROUNDING (TASK 11) ─────────────────────────
    # Distinguish explicit bypass evidence from missing/unknown control evidence
    is_isolation_domain = (
        "isolat" in str(effective_rule_name).lower()
        or any("isolat" in str(h).lower() for h in (all_detected_hazards or []))
        or any(k in str(hazard_type).lower() for k in ["pressure", "electr", "stored_mech"])
    )

    if is_isolation_domain:
        has_bypass_evidence = (
            control_state in [ControlState.BYPASSED, "BYPASSED", "COMPROMISED"]
            or (clean_trigger and "bypass" in clean_trigger.lower())
        )
        if has_bypass_evidence:
            raw_actions.append(ActionRecommendation(
                action_id="ACT-ISO-BYP-01",
                title="Verify Isolation/Bypass-Control Compliance",
                action_type=ActionCategory.VERIFICATION_ACTION,
                urgency=ActionUrgency.HIGH,
                description="Verify isolation/bypass-control compliance at the identified work activity.",
                reason="Explicit bypass evidence indicates energy isolation protocols were compromised or defeated.",
                triggering_evidence=clean_trigger or "Explicit energy isolation bypass evidence detected.",
                hazard=hazard_type,
                control=effective_control_name or "Energy Isolation",
                control_state="COMPROMISED",
                applicable_rule="Energy Isolation",
                verification_steps=[
                    "Halt work activity and examine bypassed isolation point or interlock.",
                    "Confirm whether formal bypass authorization or management-of-change (MOC) was issued.",
                    "Restore full positive physical lockout before authorized work resumes.",
                ],
                source={
                    "source_id": SourceAuthority.IOGP_459,
                    "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
                    "document": "IOGP Report 459 (Energy Isolation)",
                    "verifiable": True,
                },
                hierarchy_level=ControlHierarchyType.DIRECT_ENGINEERED_CONTROL,
            ))
        elif control_state in [ControlState.UNKNOWN, "UNKNOWN"]:
            raw_actions.append(ActionRecommendation(
                action_id="ACT-ISO-UNK-01",
                title="Verify Isolation Status & Energy Isolation Evidence",
                action_type=ActionCategory.VERIFICATION_ACTION,
                urgency=ActionUrgency.MEDIUM,
                description="Verify isolation status and evidence of effective energy isolation.",
                reason="Control effectiveness could not be established from available source data; verify isolation status rather than assuming failure.",
                triggering_evidence="Control effectiveness could not be established from available source data.",
                hazard=hazard_type,
                control=effective_control_name or "Energy Isolation",
                control_state="UNKNOWN",
                applicable_rule="Energy Isolation",
                verification_steps=[
                    "Inspect physical isolation points, valve handles, and padlocks on-site.",
                    "Verify zero-energy state through pressure gauge check, bleed vent, or test-before-touch voltage meter.",
                    "Review written isolation permit and Start Work Checks before proceeding.",
                ],
                source={
                    "source_id": SourceAuthority.IOGP_459,
                    "provenance_tier": ProvenanceTier.IOGP_GUIDANCE,
                    "document": "IOGP Report 459 (Energy Isolation)",
                    "verifiable": True,
                },
                hierarchy_level=ControlHierarchyType.PROCEDURAL_CONTROL,
            ))

    # ── DEDUPLICATION & CONSOLIDATION ─────────────────────────────────────────
    deduped_actions = _deduplicate_and_prioritize_actions(raw_actions)

    return [a.to_dict() for a in deduped_actions]



# ── Action Deduplication & Merging Algorithm ──────────────────────────────────

def _deduplicate_and_prioritize_actions(
    actions: List[ActionRecommendation],
) -> List[ActionRecommendation]:
    """
    Intelligently deduplicates overlapping actions while preserving rule and hazard attribution.
    Sorts strictly by Category Order and Qualitative Urgency.
    """
    if not actions:
        return []

    merged_by_intent: Dict[str, ActionRecommendation] = {}

    for act in actions:
        # Generate an intent key based on action_type and operational keyword
        title_lower = act.title.lower()
        if (
            "halt" in title_lower
            or "cease" in title_lower
            or "stop" in title_lower
            or "evacuate" in title_lower
            or "remove personnel" in title_lower
            or "extinguish" in title_lower
            or "clear personnel" in title_lower
        ):
            intent_key = f"{act.action_type}:STOP_WORK"
        elif "re-establish" in title_lower or "restore" in title_lower or "install" in title_lower or "fit" in title_lower:
            intent_key = f"{act.action_type}:RESTORE_BARRIER"
        elif "verify" in title_lower or "survey" in title_lower or "test" in title_lower or "check" in title_lower:
            intent_key = f"{act.action_type}:VERIFY_ENERGY"
        elif "escalat" in title_lower or "investigat" in title_lower:
            intent_key = f"{act.action_type}:ESCALATE_SIF"
        elif "learning" in title_lower or "document & share" in title_lower:
            intent_key = f"{act.action_type}:POSITIVE_LEARNING"
        else:
            intent_key = f"{act.action_type}:{act.title[:25]}"

        if intent_key not in merged_by_intent:
            merged_by_intent[intent_key] = act
        else:
            # Merge into existing action
            existing = merged_by_intent[intent_key]
            # Combine hazards if distinct
            combined_hazards = list(dict.fromkeys([existing.hazard, act.hazard]))
            merged_hazard = ", ".join(combined_hazards)
            # Combine rules if distinct
            combined_rules = list(dict.fromkeys([existing.applicable_rule, act.applicable_rule]))
            merged_rule = ", ".join(combined_rules)
            # Combine verification steps (deduplicated)
            combined_steps = list(dict.fromkeys(existing.verification_steps + act.verification_steps))
            # Urgency priority
            urgency_levels = {
                ActionUrgency.CRITICAL: 0,
                ActionUrgency.HIGH: 1,
                ActionUrgency.MEDIUM: 2,
                ActionUrgency.LOW: 3,
                ActionUrgency.INFO: 4,
            }
            highest_urgency = existing.urgency if urgency_levels.get(existing.urgency, 9) <= urgency_levels.get(act.urgency, 9) else act.urgency

            # Update merged action
            merged_by_intent[intent_key] = ActionRecommendation(
                action_id=existing.action_id,
                title=existing.title,
                action_type=existing.action_type,
                urgency=highest_urgency,
                description=f"{existing.description} Additionally: {act.description}" if existing.description != act.description else existing.description,
                reason=f"{existing.reason} (Also applicable to: {act.hazard})",
                triggering_evidence=f"{existing.triggering_evidence} | {act.triggering_evidence}" if existing.triggering_evidence != act.triggering_evidence else existing.triggering_evidence,
                hazard=merged_hazard,
                control=f"{existing.control}, {act.control}" if existing.control != act.control else existing.control,
                control_state=existing.control_state,
                applicable_rule=merged_rule,
                verification_steps=combined_steps,
                source=existing.source,
                library_version=existing.library_version,
                hierarchy_level=existing.hierarchy_level,
            )

    result = list(merged_by_intent.values())

    # Sorting order
    CATEGORY_ORDER = {
        ActionCategory.IMMEDIATE_ACTION: 0,
        ActionCategory.CONTROL_RESTORATION: 1,
        ActionCategory.POSITIVE_LEARNING_ACTION: 2,
        ActionCategory.VERIFICATION_ACTION: 3,
        ActionCategory.CORRECTIVE_ACTION: 4,
        ActionCategory.ESCALATION_ACTION: 5,
        ActionCategory.PREVENTIVE_ACTION: 6,
    }
    URGENCY_ORDER = {
        ActionUrgency.CRITICAL: 0,
        ActionUrgency.HIGH: 1,
        ActionUrgency.MEDIUM: 2,
        ActionUrgency.LOW: 3,
        ActionUrgency.INFO: 4,
    }

    result.sort(key=lambda a: (
        CATEGORY_ORDER.get(a.action_type, 9),
        URGENCY_ORDER.get(a.urgency, 9)
    ))

    return result


# ── Backwards-Compatibility Mapping Function ──────────────────────────────────

def map_reasoning_to_actions(
    hazard_type: str,
    control_state: str,
    exposure_state: str,
    decision: str,
    internal_state: str,
    missing_items: Optional[List[Any]] = None,
) -> List[ActionRecommendation]:
    """
    Preserved interface for Task 4 callers.
    Returns list of ActionRecommendation objects.
    """
    dict_actions = generate_grounded_actions(
        hazard_type=hazard_type,
        control_state=control_state,
        exposure_state=exposure_state,
        decision=decision,
        internal_state=internal_state,
        missing_items=missing_items,
    )
    # Convert dicts back to ActionRecommendation objects
    obj_actions = []
    for d in dict_actions:
        obj = ActionRecommendation(
            action_id=d["action_id"],
            title=d["title"],
            action_type=d["action_type"],
            urgency=d["urgency"],
            description=d["description"],
            reason=d["reason"],
            triggering_evidence=d["triggering_evidence"],
            hazard=d["hazard"],
            control=d["control"],
            control_state=d["control_state"],
            applicable_rule=d["applicable_rule"],
            verification_steps=d["verification_steps"],
            source=d.get("source", {}),
            library_version=d.get("library_version", "action_library_v1"),
            hierarchy_level=d.get("hierarchy_level", ControlHierarchyType.DIRECT_ENGINEERED_CONTROL),
            target_barrier=d.get("target_barrier"),
            regulatory_reference=d.get("regulatory_reference"),
        )
        obj_actions.append(obj)
    return obj_actions
