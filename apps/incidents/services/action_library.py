"""
PSIF Platform — Evidence-Grounded Corrective Action Engine (v1)

Architecture:
    Incident Evidence State
    → Control Deficiency Detection
    → Applicable IOGP Rule
    → Action Library Lookup
    → Contextualized Recommendation

Design Principles:
- Actions are versioned, structured templates. The LLM does not invent safety instructions.
- Every action traces to an applicable_hazard, applicable_control, and control_failure_state.
- Actions carry an IOGP rule reference where applicable.
- Urgency, action type, and verification steps are explicitly declared per template.
- The engine maps incident evidence (structured fields + IOGP match) to the relevant action set.

Action Types:
    IMMEDIATE_ACTION     — Stop/isolate/evacuate; highest urgency
    CORRECTIVE_ACTION    — Fix the identified deficiency; medium urgency
    PREVENTIVE_ACTION    — Systemic prevention; medium-long urgency
    VERIFICATION_ACTION  — Confirm the fix worked; medium urgency
    ESCALATION_ACTION    — Escalate beyond local team; high urgency
    POSITIVE_LEARNING_ACTION — Capture and share what worked; low urgency

Terminology:
- "PSIF Model Score" (not "probability")
- "precursor candidate" (not "PSIF confirmed")
- IOGP rules are "matched" by deterministic keyword classification
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ── Action Type Constants ─────────────────────────────────────────────────────

class ActionType:
    IMMEDIATE = "IMMEDIATE_ACTION"
    CORRECTIVE = "CORRECTIVE_ACTION"
    PREVENTIVE = "PREVENTIVE_ACTION"
    VERIFICATION = "VERIFICATION_ACTION"
    ESCALATION = "ESCALATION_ACTION"
    POSITIVE_LEARNING = "POSITIVE_LEARNING_ACTION"


# ── Urgency Constants ─────────────────────────────────────────────────────────

class ActionUrgency:
    CRITICAL = "critical"     # Within hours
    HIGH = "high"             # Within 24 hours
    MEDIUM = "medium"         # Within 7 days
    LOW = "low"               # Within 30 days


# ── Control Failure States ────────────────────────────────────────────────────

class ControlFailureState:
    ABSENT = "absent"
    FAILED = "failed"
    BYPASSED = "bypassed"
    UNKNOWN = "unknown"
    EFFECTIVE = "effective"   # For positive-learning actions


# ── Action Library Version ────────────────────────────────────────────────────

ACTION_LIBRARY_VERSION = "action_library_v1"


def get_action_library_version() -> str:
    """Returns the active corrective action library version."""
    return ACTION_LIBRARY_VERSION


# ── Action Template Dataclass ─────────────────────────────────────────────────

@dataclass
class ActionTemplate:
    """
    Versioned, structured corrective action template.
    All fields are declarative — no runtime LLM generation.
    """
    action_id: str
    title: str
    description: str
    action_type: str                     # Member of ActionType
    urgency: str                         # Member of ActionUrgency
    applicable_hazard: List[str]         # EnergyType values or 'any'
    applicable_control: List[str]        # ControlType values or 'any'
    control_failure_state: List[str]     # ControlFailureState values
    applicable_rule: Optional[str]       # IOGP Life-Saving Rule name or None
    verification_steps: List[str]        # Concrete verification criteria
    library_version: str = ACTION_LIBRARY_VERSION
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Master Action Library ─────────────────────────────────────────────────────

ACTION_LIBRARY: List[ActionTemplate] = [

    # ── Work at Height / Fall Protection ─────────────────────────────────────

    ActionTemplate(
        action_id="WAH-IMM-001",
        title="Cease Work at Height — Uncontrolled Fall Hazard",
        description=(
            "Immediately stop all work at height. Secure any unsecured tools or materials. "
            "Evacuate the elevated area. Do not resume until fall protection controls are inspected, "
            "confirmed in-place, and formally authorized."
        ),
        action_type=ActionType.IMMEDIATE,
        urgency=ActionUrgency.CRITICAL,
        applicable_hazard=["gravity_height"],
        applicable_control=["fall_protection"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.BYPASSED],
        applicable_rule="Working at Height",
        verification_steps=[
            "Confirm all workers have exited the elevated work zone.",
            "Verify fall protection equipment (harness, guardrail, safety net) is physically present and connected.",
            "Inspect for any unsecured loads or tools that could become dropped objects.",
        ],
    ),

    ActionTemplate(
        action_id="WAH-COR-001",
        title="Restore and Inspect Fall Protection Controls",
        description=(
            "Inspect all fall protection equipment in the affected area: harnesses, lanyards, anchor points, "
            "guardrails, and safety nets. Replace any failed, missing, or improperly connected equipment. "
            "Document findings and corrective actions taken."
        ),
        action_type=ActionType.CORRECTIVE,
        urgency=ActionUrgency.HIGH,
        applicable_hazard=["gravity_height"],
        applicable_control=["fall_protection"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED],
        applicable_rule="Working at Height",
        verification_steps=[
            "Verify all fall protection is rated for the task load and height.",
            "Confirm anchor points are inspected and certified.",
            "Sign-off by competent person before resuming work.",
        ],
    ),

    ActionTemplate(
        action_id="WAH-PREV-001",
        title="Pre-Task Fall Hazard Assessment and Barrier Survey",
        description=(
            "Before resuming work at height, conduct a documented pre-task assessment: identify all fall hazards, "
            "verify that fall protection is task-appropriate (passive barriers preferred over PPE), "
            "and confirm that a competent person has authorized the method of access."
        ),
        action_type=ActionType.PREVENTIVE,
        urgency=ActionUrgency.MEDIUM,
        applicable_hazard=["gravity_height"],
        applicable_control=["fall_protection"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.UNKNOWN],
        applicable_rule="Working at Height",
        verification_steps=[
            "Pre-task assessment form is completed and signed.",
            "Fall protection hierarchy (elimination → substitution → engineering → administrative → PPE) is documented.",
        ],
    ),

    ActionTemplate(
        action_id="WAH-ESC-001",
        title="Escalate Repeated Fall Control Failures to Site Management",
        description=(
            "Where fall protection has failed, been absent, or been bypassed on more than one occasion, "
            "escalate to site HSE management and department leadership. A formal corrective action plan "
            "must be produced within 48 hours."
        ),
        action_type=ActionType.ESCALATION,
        urgency=ActionUrgency.HIGH,
        applicable_hazard=["gravity_height"],
        applicable_control=["fall_protection"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.BYPASSED],
        applicable_rule="Working at Height",
        verification_steps=[
            "Escalation logged in the HSE management system.",
            "Site HSE manager has acknowledged receipt.",
            "Corrective action plan assigned with owner and due date.",
        ],
    ),

    # ── Energy Isolation / LOTO ───────────────────────────────────────────────

    ActionTemplate(
        action_id="LOTO-IMM-001",
        title="Emergency De-energize — LOTO Not Applied",
        description=(
            "Where Lockout/Tagout (LOTO) or energy isolation has not been applied before maintenance or "
            "inspection tasks, immediately stop work, warn all personnel in the zone, "
            "and isolate all energy sources before continuing. "
            "No work on energized equipment without verified energy isolation."
        ),
        action_type=ActionType.IMMEDIATE,
        urgency=ActionUrgency.CRITICAL,
        applicable_hazard=["electrical", "mechanical_motion", "pressure"],
        applicable_control=["loto_isolation"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.BYPASSED],
        applicable_rule="Isolation of Energy",
        verification_steps=[
            "All energy sources (electrical, pneumatic, hydraulic, thermal, gravity) are identified and isolated.",
            "LOTO devices applied by the authorized person for each energy source.",
            "Zero energy state verified by test (attempt to operate, pressure gauge reads zero, etc.).",
        ],
    ),

    ActionTemplate(
        action_id="LOTO-COR-001",
        title="Implement/Restore LOTO Program Compliance",
        description=(
            "Review and reinstate the site energy control procedure. Ensure all energy isolation points "
            "are identified on the equipment-specific LOTO procedure. Retrain affected workers on the "
            "site LOTO program if compliance gaps are found."
        ),
        action_type=ActionType.CORRECTIVE,
        urgency=ActionUrgency.HIGH,
        applicable_hazard=["electrical", "mechanical_motion", "pressure"],
        applicable_control=["loto_isolation"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.BYPASSED],
        applicable_rule="Isolation of Energy",
        verification_steps=[
            "Equipment-specific LOTO procedure is available and current.",
            "All energy isolation points are labeled.",
            "Affected workers are re-qualified on LOTO within 5 working days.",
        ],
    ),

    ActionTemplate(
        action_id="LOTO-PREV-001",
        title="Energy Isolation Audit — All Maintenance Tasks",
        description=(
            "Audit a sample of active maintenance work orders to verify that LOTO/energy isolation is "
            "documented and applied before work begins. "
            "Correct any systematic gaps in pre-task isolation planning."
        ),
        action_type=ActionType.PREVENTIVE,
        urgency=ActionUrgency.MEDIUM,
        applicable_hazard=["electrical", "mechanical_motion", "pressure"],
        applicable_control=["loto_isolation"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.BYPASSED, ControlFailureState.UNKNOWN],
        applicable_rule="Energy Isolation",
        verification_steps=[
            "At least 20% of active work orders audited within 30 days.",
            "Audit findings documented and tracked to closure.",
        ],
    ),

    ActionTemplate(
        action_id="LOTO-VER-001",
        title="Verify Isolation Status & Effective Energy Isolation",
        description="Verify isolation status and evidence of effective energy isolation.",
        action_type=ActionType.VERIFICATION,
        urgency=ActionUrgency.MEDIUM,
        applicable_hazard=["electrical", "mechanical_motion", "pressure", "any"],
        applicable_control=["loto_isolation", "any"],
        control_failure_state=[ControlFailureState.UNKNOWN],
        applicable_rule="Energy Isolation",
        verification_steps=[
            "Inspect physical isolation points, valve handles, and padlocks on-site.",
            "Verify zero-energy state through pressure gauge check, bleed vent, or test-before-touch voltage meter.",
            "Review written isolation permit and Start Work Checks before proceeding.",
        ],
    ),

    ActionTemplate(
        action_id="LOTO-VER-002",
        title="Verify Isolation/Bypass-Control Compliance",
        description="Verify isolation/bypass-control compliance at the identified work activity.",
        action_type=ActionType.VERIFICATION,
        urgency=ActionUrgency.HIGH,
        applicable_hazard=["electrical", "mechanical_motion", "pressure", "any"],
        applicable_control=["loto_isolation", "any"],
        control_failure_state=[ControlFailureState.BYPASSED],
        applicable_rule="Energy Isolation",
        verification_steps=[
            "Halt work activity and examine bypassed isolation point or interlock.",
            "Confirm whether formal bypass authorization or management-of-change (MOC) was issued.",
            "Restore full positive physical lockout before authorized work resumes.",
        ],
    ),


    # ── Machine Guarding ──────────────────────────────────────────────────────

    ActionTemplate(
        action_id="GUARD-IMM-001",
        title="Stop Rotating Equipment — Missing or Defeated Guard",
        description=(
            "Where machine guarding has been removed, defeated, or is absent: "
            "immediately shut down the equipment. "
            "Tag out the machine. Do not restart until guarding is reinstated and inspected."
        ),
        action_type=ActionType.IMMEDIATE,
        urgency=ActionUrgency.CRITICAL,
        applicable_hazard=["mechanical_motion"],
        applicable_control=["machine_guarding"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.BYPASSED, ControlFailureState.FAILED],
        applicable_rule="Bypassing of Safety Controls",
        verification_steps=[
            "Equipment is shut down and tagged out before guard reinstatement.",
            "Reinstated guard is physically attached and interlocked (where applicable).",
            "Equipment owner sign-off before restart.",
        ],
    ),

    ActionTemplate(
        action_id="GUARD-COR-001",
        title="Reinstate Machine Guards and Inspect Interlocks",
        description=(
            "Replace or repair all missing or damaged guards on rotating or moving equipment. "
            "Test all safety interlock systems to confirm they stop the machine when the guard is opened. "
            "Document the inspection."
        ),
        action_type=ActionType.CORRECTIVE,
        urgency=ActionUrgency.HIGH,
        applicable_hazard=["mechanical_motion"],
        applicable_control=["machine_guarding"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED],
        applicable_rule="Bypassing of Safety Controls",
        verification_steps=[
            "All guards installed per OEM specifications.",
            "Interlock test record completed and signed.",
        ],
    ),

    # ── Hot Work / Fire / Permit ──────────────────────────────────────────────

    ActionTemplate(
        action_id="HW-IMM-001",
        title="Cease Hot Work — Atmosphere Not Cleared or Permit Absent",
        description=(
            "Immediately stop all hot work (welding, cutting, grinding). "
            "Where an atmospheric test has not been conducted, or a valid hot work permit is absent, "
            "no hot work may continue. "
            "Remove ignition sources. Ventilate the area. Re-test atmosphere before resuming."
        ),
        action_type=ActionType.IMMEDIATE,
        urgency=ActionUrgency.CRITICAL,
        applicable_hazard=["chemical", "thermal"],
        applicable_control=["permit_isolation", "ventilation_monitoring"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED],
        applicable_rule="Hot Work",
        verification_steps=[
            "Hot work stopped and all ignition sources removed.",
            "Atmospheric test (LEL, O2, H2S) result documented and within safe range.",
            "Valid hot work permit issued before resumption.",
        ],
    ),

    ActionTemplate(
        action_id="HW-COR-001",
        title="Verify and Issue Hot Work Permit",
        description=(
            "Ensure that a valid hot work permit is issued for all work producing heat, flame, or spark. "
            "The permit must identify the specific area, time window, fire watch requirements, "
            "and atmospheric monitoring frequency."
        ),
        action_type=ActionType.CORRECTIVE,
        urgency=ActionUrgency.HIGH,
        applicable_hazard=["chemical", "thermal"],
        applicable_control=["permit_isolation"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED],
        applicable_rule="Hot Work",
        verification_steps=[
            "Hot work permit signed by issuer, area authority, and worker.",
            "Fire watch in place for the duration of hot work and for the post-work cool-down period.",
            "Fire extinguisher/suppression present and accessible.",
        ],
    ),

    # ── Line of Fire / Exclusion Zone ─────────────────────────────────────────

    ActionTemplate(
        action_id="LOF-IMM-001",
        title="Remove Worker from Line of Fire",
        description=(
            "Where a worker is in the direct path of an energized hazard (suspended load, "
            "pressurized line, moving equipment): immediately halt operations and direct the "
            "worker out of the line of fire. Establish a physical exclusion zone before continuing."
        ),
        action_type=ActionType.IMMEDIATE,
        urgency=ActionUrgency.CRITICAL,
        applicable_hazard=["gravity_height", "mechanical_motion", "pressure"],
        applicable_control=["physical_barrier"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED],
        applicable_rule="Line of Fire",
        verification_steps=[
            "All workers are physically outside the hazard zone.",
            "Exclusion zone is demarcated with barriers or cones.",
            "Signage is posted at all access points.",
        ],
    ),

    ActionTemplate(
        action_id="LOF-PREV-001",
        title="Pre-Task Line of Fire Assessment",
        description=(
            "Before tasks involving suspended loads, moving equipment, or pressurized lines, "
            "conduct a documented pre-task line-of-fire assessment: "
            "identify all potential line-of-fire positions, "
            "establish and mark exclusion zones, "
            "and brief all workers on restricted positions."
        ),
        action_type=ActionType.PREVENTIVE,
        urgency=ActionUrgency.MEDIUM,
        applicable_hazard=["gravity_height", "mechanical_motion", "pressure"],
        applicable_control=["physical_barrier"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.UNKNOWN],
        applicable_rule="Line of Fire",
        verification_steps=[
            "Pre-task assessment form completed and signed by crew.",
            "Exclusion zones defined on the task plan or sketch.",
            "Toolbox talk covering line-of-fire hazards is documented.",
        ],
    ),

    # ── Driving / Motor Vehicle ────────────────────────────────────────────────

    ActionTemplate(
        action_id="DRIVE-IMM-001",
        title="Cease Driving Operation — Journey Risk Not Assessed",
        description=(
            "Where a vehicle journey has commenced without a documented journey management plan "
            "or fitness-for-drive check: halt the journey and complete the required risk assessment "
            "before continuing."
        ),
        action_type=ActionType.IMMEDIATE,
        urgency=ActionUrgency.HIGH,
        applicable_hazard=["motor_vehicle"],
        applicable_control=["rules_procedures"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.BYPASSED],
        applicable_rule="Driving",
        verification_steps=[
            "Journey management plan completed and authorized.",
            "Driver fitness confirmed (no fatigue, alcohol, or medication impairment).",
            "Vehicle pre-use inspection completed and recorded.",
        ],
    ),

    ActionTemplate(
        action_id="DRIVE-PREV-001",
        title="Journey Risk Management — Review and Reinstate Controls",
        description=(
            "Review the site journey risk management procedure. Audit recent journeys for "
            "compliance with journey planning, authorized routes, and check-in requirements. "
            "Retrain drivers where gaps are found."
        ),
        action_type=ActionType.PREVENTIVE,
        urgency=ActionUrgency.MEDIUM,
        applicable_hazard=["motor_vehicle"],
        applicable_control=["rules_procedures", "training"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.UNKNOWN],
        applicable_rule="Driving",
        verification_steps=[
            "Journey management audit covering at least 20 journeys in the last 30 days.",
            "Driver compliance rate documented.",
            "Refresher training completed for non-compliant drivers.",
        ],
    ),

    # ── Generic High-Energy Hazard (Fallback) ─────────────────────────────────

    ActionTemplate(
        action_id="GEN-IMM-001",
        title="Halt Operations — Uncontrolled High-Energy Hazard",
        description=(
            "Where an uncontrolled high-energy hazard is present and direct controls are absent or failed: "
            "halt all operations in the affected area. Evacuate personnel from the hazard zone. "
            "Do not resume until controls are confirmed in-place and the area is declared safe by a "
            "competent person."
        ),
        action_type=ActionType.IMMEDIATE,
        urgency=ActionUrgency.CRITICAL,
        applicable_hazard=["any"],
        applicable_control=["any"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.BYPASSED],
        applicable_rule=None,
        verification_steps=[
            "All workers have exited the hazard zone.",
            "Energy source is isolated or contained.",
            "Competent person confirms area is safe before resuming.",
        ],
    ),

    ActionTemplate(
        action_id="GEN-PREV-001",
        title="Conduct Barrier Health Assessment — Critical Controls",
        description=(
            "For the affected department and task type, conduct a formal assessment of all "
            "critical barriers relevant to the energy type involved. "
            "Confirm that each critical barrier is functional, documented, and understood by the work team. "
            "Record findings."
        ),
        action_type=ActionType.PREVENTIVE,
        urgency=ActionUrgency.MEDIUM,
        applicable_hazard=["any"],
        applicable_control=["any"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.UNKNOWN],
        applicable_rule=None,
        verification_steps=[
            "Barrier assessment completed for all critical controls relevant to the task.",
            "Any failed or degraded barriers documented and assigned for corrective action.",
            "Findings reviewed with department supervisor.",
        ],
    ),

    ActionTemplate(
        action_id="GEN-POS-001",
        title="Capture and Share Effective Control Learnings",
        description=(
            "Where effective controls were present and held, capture the specific controls that "
            "prevented escalation to a serious outcome. "
            "Share this learning with other teams performing similar tasks or working in similar environments. "
            "Document in the site learning-from-incidents register."
        ),
        action_type=ActionType.POSITIVE_LEARNING,
        urgency=ActionUrgency.LOW,
        applicable_hazard=["any"],
        applicable_control=["any"],
        control_failure_state=[ControlFailureState.EFFECTIVE],
        applicable_rule=None,
        verification_steps=[
            "Learning captured in writing: what worked, why it worked, who was involved.",
            "Learning shared with at least one other team or department.",
            "Entry made in the site learning-from-incidents register.",
        ],
    ),

    ActionTemplate(
        action_id="GEN-VER-001",
        title="Post-Corrective-Action Verification Inspection",
        description=(
            "After corrective actions have been implemented, conduct a formal verification inspection "
            "to confirm that the identified control deficiency has been resolved and that the "
            "corrective action has not introduced new hazards."
        ),
        action_type=ActionType.VERIFICATION,
        urgency=ActionUrgency.MEDIUM,
        applicable_hazard=["any"],
        applicable_control=["any"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.BYPASSED],
        applicable_rule=None,
        verification_steps=[
            "Physical inspection of the corrected control is completed and documented.",
            "Inspector is independent of the person who performed the corrective action.",
            "Sign-off recorded in the action tracking system.",
        ],
    ),

    # ── Supervisor / Rules-Based Escalation ────────────────────────────────────

    ActionTemplate(
        action_id="SUP-ESC-001",
        title="Escalate PSIF Precursor to HSE Management",
        description=(
            "This incident has been classified as a PSIF precursor candidate by the model. "
            "Escalate to site HSE management and department head within 24 hours. "
            "A formal investigation should be initiated to determine whether a critical barrier "
            "was absent or failed."
        ),
        action_type=ActionType.ESCALATION,
        urgency=ActionUrgency.HIGH,
        applicable_hazard=["any"],
        applicable_control=["any"],
        control_failure_state=[ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.BYPASSED, ControlFailureState.UNKNOWN],
        applicable_rule=None,
        verification_steps=[
            "HSE management notified in writing within 24 hours.",
            "Investigation lead assigned.",
            "Investigation timeline confirmed.",
        ],
        notes=(
            "Note: Classification as a PSIF precursor candidate is based on the PSIF Model Score "
            "and supporting evidence signals. It does not constitute a determination that a "
            "Serious Injury or Fatality would have occurred."
        ),
    ),
]


# ── Action Index (for fast lookup) ───────────────────────────────────────────

_ACTION_BY_ID: Dict[str, ActionTemplate] = {a.action_id: a for a in ACTION_LIBRARY}


def get_action_by_id(action_id: str) -> Optional[ActionTemplate]:
    return _ACTION_BY_ID.get(action_id)


# ── Core Matching Logic ───────────────────────────────────────────────────────

def _matches_hazard(template: ActionTemplate, energy_type: Optional[str]) -> bool:
    """Returns True if the template applies to this energy type."""
    if "any" in template.applicable_hazard:
        return True
    if not energy_type or energy_type == "unknown":
        return False
    return energy_type in template.applicable_hazard


def _matches_control(template: ActionTemplate, control_type: Optional[str]) -> bool:
    """Returns True if the template applies to this control type."""
    if "any" in template.applicable_control:
        return True
    if not control_type or control_type == "unknown":
        return True  # Generic actions apply when control is unknown
    return control_type in template.applicable_control


def _matches_failure_state(template: ActionTemplate, control_condition: Optional[str]) -> bool:
    """Returns True if the template addresses this control condition."""
    if not control_condition or control_condition == "unknown":
        control_condition = ControlFailureState.UNKNOWN
    return control_condition in template.control_failure_state


def _matches_iogp_rule(template: ActionTemplate, iogp_rule_names: List[str]) -> bool:
    """Returns True if the template matches any matched IOGP rule (supports canonical normalization)."""
    if template.applicable_rule is None:
        return True  # Generic actions apply regardless of IOGP match
    if template.applicable_rule in iogp_rule_names:
        return True
    from apps.incidents.services.normalization import normalize_iogp_rule
    template_canon = normalize_iogp_rule(template.applicable_rule).canonical_value
    for r in iogp_rule_names:
        if normalize_iogp_rule(r).canonical_value == template_canon:
            return True
    return False



def get_corrective_actions(incident) -> Dict[str, Any]:
    """
    Given an Incident instance, return a dict of prioritized corrective actions.
    Consumes the authoritative PSIF Domain Reasoning assessment.
    """
    try:
        from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment
        assessment = build_incident_reasoning_assessment(incident)
        grounded_actions = assessment.get("grounded_actions", [])
        pred = getattr(incident, "prediction", None)
        psif_predicted = getattr(pred, "psif_predicted", False) if pred else False
        iogp_tags = list(incident.iogp_rules.all()) if hasattr(incident, 'iogp_rules') else []
        iogp_rule_names = [tag.rule for tag in iogp_tags]

        return {
            "incident_id": str(getattr(incident, "id", "")),
            "psif_predicted": psif_predicted,
            "energy_type": getattr(incident, "energy_type", None),
            "control_type": getattr(incident, "control_type", None),
            "control_condition": getattr(incident, "control_condition", "unknown"),
            "high_energy_present": getattr(incident, "high_energy_present", "unknown"),
            "worker_exposed": getattr(incident, "worker_exposed", "unknown"),
            "iogp_rules": iogp_rule_names,
            "actions": grounded_actions,
            "action_count": len(grounded_actions),
            "library_version": ACTION_LIBRARY_VERSION,
            "internal_reasoning_state": assessment.get("internal_reasoning_state"),
            "decision": assessment.get("decision"),
            "methodology_notice": (
                "Corrective actions are selected from a versioned, rule-grounded action library. "
                "Actions are matched to the incident's energy type, control condition, and IOGP rule signals. "
                "These templates do not replace site-specific risk assessment or regulatory obligations. "
                "PSIF Model Score is not a calibrated probability."
            ),
        }
    except Exception:
        pass

    from apps.predictions.models import PredictionResult

    # ── Gather Evidence State (Fallback) ──────────────────────────────────────
    energy_type = incident.energy_type or "unknown"
    if energy_type == "unknown" or not energy_type:
        energy_type = None

    control_type = incident.control_type or "unknown"
    if control_type == "unknown" or not control_type:
        control_type = None

    control_condition = incident.control_condition or "unknown"

    high_energy = incident.high_energy_present or "unknown"
    worker_exposed = incident.worker_exposed or "unknown"

    # ── Get matched IOGP rules ────────────────────────────────────────────────
    iogp_tags = list(incident.iogp_rules.all()) if hasattr(incident, 'iogp_rules') else []
    iogp_rule_names = [tag.rule for tag in iogp_tags]

    # ── Get prediction result ─────────────────────────────────────────────────
    psif_predicted = False
    try:
        pred = incident.prediction
        psif_predicted = pred.psif_predicted
    except Exception:
        pass

    # ── Match Actions ─────────────────────────────────────────────────────────
    matched: List[ActionTemplate] = []
    # IDs excluded from generic matching (conditionally added below)
    CONDITIONAL_ACTION_IDS = {"SUP-ESC-001", "GEN-POS-001", "GEN-VER-001"}

    for template in ACTION_LIBRARY:
        if template.action_id in CONDITIONAL_ACTION_IDS:
            continue  # handled explicitly below
        if not _matches_failure_state(template, control_condition):
            continue
        if not _matches_hazard(template, energy_type):
            continue
        if not _matches_control(template, control_type):
            continue
        if not _matches_iogp_rule(template, iogp_rule_names):
            continue
        matched.append(template)

    # ── If PSIF predicted, always include escalation ──────────────────────────
    if psif_predicted:
        esc_action = get_action_by_id("SUP-ESC-001")
        if esc_action:
            matched.append(esc_action)

    # Always include verification and positive-learning actions (de-duplicated)
    gen_ver = get_action_by_id("GEN-VER-001")
    if gen_ver and gen_ver not in matched and control_condition in (
        ControlFailureState.ABSENT, ControlFailureState.FAILED, ControlFailureState.BYPASSED, "unknown"
    ):
        matched.append(gen_ver)

    if control_condition == ControlFailureState.EFFECTIVE:
        pos_learn = get_action_by_id("GEN-POS-001")
        if pos_learn and pos_learn not in matched:
            matched.append(pos_learn)

    # ── Priority Sort: IMMEDIATE > ESCALATION > CORRECTIVE > PREVENTIVE > VERIFICATION > POSITIVE ──
    TYPE_ORDER = {
        ActionType.IMMEDIATE: 0,
        ActionType.ESCALATION: 1,
        ActionType.CORRECTIVE: 2,
        ActionType.PREVENTIVE: 3,
        ActionType.VERIFICATION: 4,
        ActionType.POSITIVE_LEARNING: 5,
    }
    URGENCY_ORDER = {
        ActionUrgency.CRITICAL: 0,
        ActionUrgency.HIGH: 1,
        ActionUrgency.MEDIUM: 2,
        ActionUrgency.LOW: 3,
    }

    matched.sort(key=lambda a: (TYPE_ORDER.get(a.action_type, 9), URGENCY_ORDER.get(a.urgency, 9)))

    return {
        "incident_id": str(incident.id),
        "psif_predicted": psif_predicted,
        "energy_type": energy_type,
        "control_type": control_type,
        "control_condition": control_condition,
        "high_energy_present": high_energy,
        "worker_exposed": worker_exposed,
        "iogp_rules": iogp_rule_names,
        "actions": [a.to_dict() for a in matched],
        "action_count": len(matched),
        "library_version": ACTION_LIBRARY_VERSION,
        "methodology_notice": (
            "Corrective actions are selected from a versioned, rule-grounded action library. "
            "Actions are matched to the incident's energy type, control condition, and IOGP rule signals. "
            "These templates do not replace site-specific risk assessment or regulatory obligations. "
            "PSIF Model Score is not a calibrated probability."
        ),
    }
