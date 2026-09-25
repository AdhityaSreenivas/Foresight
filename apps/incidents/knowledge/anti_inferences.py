"""
Declarative Anti-Inference Knowledge Layer
apps/incidents/knowledge/anti_inferences.py

Prevents spurious reasoning, false barrier inferences, and linguistic hallucinations.
Every anti-inference principle protects against a specific real-world cognitive bias.
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from apps.incidents.knowledge.sources import SourceAuthority, ProvenanceTier


class AntiInferenceCode:
    HAZARD_MENTION_NOT_EXPOSURE = "HAZARD_MENTION_NOT_EXPOSURE"
    IOGP_MATCH_NOT_VIOLATION = "IOGP_MATCH_NOT_VIOLATION"
    IOGP_VIOLATION_NOT_PSIF = "IOGP_VIOLATION_NOT_PSIF"
    CONTROL_MENTION_NOT_EFFECTIVENESS = "CONTROL_MENTION_NOT_EFFECTIVENESS"
    CONTROL_NAME_NOT_FAILURE = "CONTROL_NAME_NOT_FAILURE"
    CORRECTIVE_ACTION_NOT_EVENT_EVIDENCE = "CORRECTIVE_ACTION_NOT_EVENT_EVIDENCE"
    PLANNED_ACTION_NOT_COMPLETED_CONTROL = "PLANNED_ACTION_NOT_COMPLETED_CONTROL"
    PPE_AVAILABILITY_NOT_USE = "PPE_AVAILABILITY_NOT_USE"
    PPE_USE_NOT_DIRECT_CONTROL = "PPE_USE_NOT_DIRECT_CONTROL"
    LOTO_MENTION_NOT_ZERO_ENERGY_VERIFIED = "LOTO_MENTION_NOT_ZERO_ENERGY_VERIFIED"
    NEAR_MISS_NOT_PSIF = "NEAR_MISS_NOT_PSIF"
    HIGH_ENERGY_EQUIPMENT_NOT_PSIF = "HIGH_ENERGY_EQUIPMENT_NOT_PSIF"
    SERIOUS_LANGUAGE_NOT_PSIF = "SERIOUS_LANGUAGE_NOT_PSIF"


@dataclass(frozen=True)
class AntiInferenceRule:
    """Explicit declarative anti-inference constraint governing the reasoning engine."""
    code: str
    name: str
    description: str
    prohibited_inference: str
    required_corroboration: str
    forensic_rationale: str
    source_id: str = SourceAuthority.FORESIGHT_ANALYTICAL
    source_section: str = "Anti-Inference Layer Specification"


ANTI_INFERENCE_CATALOG: Dict[str, AntiInferenceRule] = {
    AntiInferenceCode.HAZARD_MENTION_NOT_EXPOSURE: AntiInferenceRule(
        code=AntiInferenceCode.HAZARD_MENTION_NOT_EXPOSURE,
        name="Hazard Mention != Exposure",
        description="Mentioning a high-energy hazard source does not establish that any worker was exposed to its release path.",
        prohibited_inference="Inferring direct exposure or line of fire merely because a high-voltage line, crane lift, or pressure vessel is described.",
        required_corroboration="Explicit spatial or physical positioning evidence establishing that personnel occupied the release trajectory or danger zone.",
        forensic_rationale="Prevents false positives on unexposed or remotely controlled operations where high energy is present but workers remain outside the envelope.",
    ),
    AntiInferenceCode.IOGP_MATCH_NOT_VIOLATION: AntiInferenceRule(
        code=AntiInferenceCode.IOGP_MATCH_NOT_VIOLATION,
        name="IOGP Rule Match != Rule Violation",
        description="Classifying an incident under an IOGP Life-Saving Rule reflects the operational activity type, not that the rule was breached.",
        prohibited_inference="Inferring a safety rule violation simply because an incident relates to 'Working at Height' or 'Energy Isolation'.",
        required_corroboration="Documented non-conformance, bypass, or procedural failure during the event.",
        forensic_rationale="IOGP rules define operational activity boundaries; an incident where a rule was fully adhered to and prevented harm must not be flagged as a violation.",
    ),
    AntiInferenceCode.IOGP_VIOLATION_NOT_PSIF: AntiInferenceRule(
        code=AntiInferenceCode.IOGP_VIOLATION_NOT_PSIF,
        name="IOGP Rule Violation != PSIF",
        description="A life-saving rule violation does not constitute a PSIF precursor unless an open high-energy SIF consequence pathway is substantiated.",
        prohibited_inference="Classifying an administrative or low-energy rule non-conformance as a PSIF precursor.",
        required_corroboration="High-energy hazard presence combined with credible exposure and unmitigated SIF consequence capability.",
        forensic_rationale="Adheres to EEI SCL and IOGP Report 459: rule infractions without high energy or open pathways are not high-potential SIF events.",
    ),
    AntiInferenceCode.CONTROL_MENTION_NOT_EFFECTIVENESS: AntiInferenceRule(
        code=AntiInferenceCode.CONTROL_MENTION_NOT_EFFECTIVENESS,
        name="Control Mention != Control Effectiveness",
        description="Citing the name of a control, procedure, or barrier does not prove it functioned effectively during the energy release.",
        prohibited_inference="Crediting a control as 'Effective' merely because 'permit was issued' or 'guard was present on machine'.",
        required_corroboration="Corroborated evidence that the barrier sustained the physical release force and interrupted the consequence pathway.",
        forensic_rationale="Prevents paper safety; administrative mention of controls must not obscure actual barrier bypass or mechanical failure.",
    ),
    AntiInferenceCode.CONTROL_NAME_NOT_FAILURE: AntiInferenceRule(
        code=AntiInferenceCode.CONTROL_NAME_NOT_FAILURE,
        name="Control Name Mention != Control Failure",
        description="Mentioning a control device or safety talk in a narrative does not infer that the control failed or degraded.",
        prohibited_inference="Inferring a guard failure or isolation failure merely because the word 'guard' or 'lockout' appears in the text.",
        required_corroboration="Explicit failure verbs (removed, bypassed, unhitched, ruptured, passing, omitted, degraded).",
        forensic_rationale="Prevents false alarms on benign walkthrough notes like 'Pump guard was intact and rigid barricades were held in place'.",
    ),
    AntiInferenceCode.CORRECTIVE_ACTION_NOT_EVENT_EVIDENCE: AntiInferenceRule(
        code=AntiInferenceCode.CORRECTIVE_ACTION_NOT_EVENT_EVIDENCE,
        name="Corrective Action != Event State Evidence",
        description="Downstream corrective actions describe post-incident recommendations, which must not pollute or alter the reconstructed event state.",
        prohibited_inference="Inferring that a barrier failed during the event because a supervisor recommended upgrading or replacing it next month.",
        required_corroboration="Physical event narrative and contemporaneous condition records.",
        forensic_rationale="Field investigations frequently recommend secondary barrier enhancements even when original controls held; this must never fabricate event failures.",
    ),
    AntiInferenceCode.PLANNED_ACTION_NOT_COMPLETED_CONTROL: AntiInferenceRule(
        code=AntiInferenceCode.PLANNED_ACTION_NOT_COMPLETED_CONTROL,
        name="Planned Action != Completed Control",
        description="A barrier scheduled for future installation or planned on paper cannot be credited as an active barrier during the incident.",
        prohibited_inference="Evaluating a planned barrier as 'Effective' or 'Present' during the energy release.",
        required_corroboration="Verification that the control was physically installed and functional prior to personnel exposure.",
        forensic_rationale="Prevents crediting future intentions ('guard will be installed tomorrow') as contemporaneous physical protection.",
    ),
    AntiInferenceCode.PPE_AVAILABILITY_NOT_USE: AntiInferenceRule(
        code=AntiInferenceCode.PPE_AVAILABILITY_NOT_USE,
        name="PPE Availability != PPE Deployment",
        description="The availability or issuance of personal protective equipment does not confirm that it was properly donned, attached, or tied off.",
        prohibited_inference="Assuming 100% tie-off or respiratory protection merely because a worker was issued a harness or respirator.",
        required_corroboration="Direct documentation of proper connection, latching, and deployment during the hazardous exposure.",
        forensic_rationale="A harness worn with lanyards unhitched provides zero fall arrest capacity; tie-off must be independently verified.",
    ),
    AntiInferenceCode.PPE_USE_NOT_DIRECT_CONTROL: AntiInferenceRule(
        code=AntiInferenceCode.PPE_USE_NOT_DIRECT_CONTROL,
        name="Ordinary PPE != Direct Critical Engineered Barrier",
        description="Ordinary PPE (hard hat, safety boots, standard coveralls, leather gloves, safety glasses) is never equivalent to a direct critical engineered barrier.",
        prohibited_inference="Evaluating ordinary PPE as a direct barrier capable of downgrading a high-energy release from PSIF to Controlled.",
        required_corroboration="Direct engineered barriers (physical guarding, positive isolation blinds, shoring boxes, interlocked dead-fronts).",
        forensic_rationale="Hard hats do not stop falling 15-ton crane loads; safety boots do not interrupt 11kV electrical flashovers. PPE is secondary mitigation, never primary prevention.",
    ),
    AntiInferenceCode.LOTO_MENTION_NOT_ZERO_ENERGY_VERIFIED: AntiInferenceRule(
        code=AntiInferenceCode.LOTO_MENTION_NOT_ZERO_ENERGY_VERIFIED,
        name="LOTO Mention != Zero Energy Verified",
        description="Mentioning that lockout/tagout was applied or assigned does not prove absence of voltage or zero residual pressure.",
        prohibited_inference="Assuming zero hazardous energy without explicit test-before-touch or bleeder opening verification.",
        required_corroboration="Documented instrumented verification: voltage meter reading 0V, casing bleeder port opened, or double-block pressure gauge 0 psi.",
        forensic_rationale="Locking a switch does not prove the downstream busbar is de-energized; backfeeds and wrong breaker tags cause fatal electrical contacts.",
    ),
    AntiInferenceCode.NEAR_MISS_NOT_PSIF: AntiInferenceRule(
        code=AntiInferenceCode.NEAR_MISS_NOT_PSIF,
        name="Near Miss != PSIF Precursor",
        description="A near miss event does not automatically qualify as a PSIF precursor unless a high-energy SIF pathway was materially open.",
        prohibited_inference="Automatically classifying every near miss report as a PSIF event.",
        required_corroboration="Evidence establishing that high energy was released and that barrier failure brought personnel within potential injury reach.",
        forensic_rationale="Near misses include low-energy events (tripping on level ground, dropped pencil); PSIF classification requires credible SIF physical capacity.",
    ),
    AntiInferenceCode.HIGH_ENERGY_EQUIPMENT_NOT_PSIF: AntiInferenceRule(
        code=AntiInferenceCode.HIGH_ENERGY_EQUIPMENT_NOT_PSIF,
        name="High-Energy Equipment != PSIF Precursor",
        description="Working on high-energy industrial machinery does not establish a PSIF precursor when critical engineered controls are verified effective.",
        prohibited_inference="Classifying safe maintenance on a high-pressure line or 11kV transformer as PSIF when positive isolation is fully intact.",
        required_corroboration="Evidence of compromised barrier or direct worker exposure inside an uncontrolled energy path.",
        forensic_rationale="High-energy operations with robust barrier capacity represent 'High Energy Controlled' (Capacity), not failure precursors.",
    ),
    AntiInferenceCode.SERIOUS_LANGUAGE_NOT_PSIF: AntiInferenceRule(
        code=AntiInferenceCode.SERIOUS_LANGUAGE_NOT_PSIF,
        name="Serious Language != SIF Potential",
        description="Dramatic narrative adjectives, alarming rhetoric, or general severity warnings do not establish physical SIF capability.",
        prohibited_inference="Classifying an incident as PSIF based on words like 'catastrophic', 'critical', 'disastrous' without physical high energy.",
        required_corroboration="Objective physical energy release vector meeting EEI SCL high-energy threshold criteria.",
        forensic_rationale="Protects against reporting hyperbole; safety decisions must be grounded strictly in objective physical energy and barrier evidence.",
    ),
}


def get_anti_inference(code: str) -> Optional[AntiInferenceRule]:
    """Retrieves authoritative anti-inference rule by code."""
    return ANTI_INFERENCE_CATALOG.get(code)


get_anti_inference_rule = get_anti_inference


@dataclass
class AntiInferenceEvaluation:
    """Outcome of evaluating an anti-inference principle against incident evidence."""
    rule_code: str
    rule_name: str
    is_applicable: bool
    prohibited_inference: str
    required_corroboration: str
    is_inference_prevented: bool
    explanation: str


def evaluate_anti_inferences(
    text: str,
    hazard_detected: bool,
    exposure_state: str,
    control_state: str,
    iogp_matches: List[str],
) -> List[AntiInferenceEvaluation]:
    """
    Evaluates anti-inference rules against incident context to prevent cognitive reasoning errors.
    Returns list of evaluated anti-inferences.
    """
    evaluations: List[AntiInferenceEvaluation] = []
    text_lower = text.lower() if text else ""

    # 1. HAZARD_MENTION_NOT_EXPOSURE: High energy mentioned, but exposure not established
    rule = ANTI_INFERENCE_CATALOG[AntiInferenceCode.HAZARD_MENTION_NOT_EXPOSURE]
    applies = hazard_detected and exposure_state in ("UNKNOWN", "INSUFFICIENT_INFORMATION", "NO_EXPOSURE", "PROTECTED_POSITION")
    evaluations.append(AntiInferenceEvaluation(
        rule_code=rule.code,
        rule_name=rule.name,
        is_applicable=applies,
        prohibited_inference=rule.prohibited_inference,
        required_corroboration=rule.required_corroboration,
        is_inference_prevented=applies,
        explanation="Hazard source is mentioned but worker exposure trajectory is not established." if applies else "Worker exposure was independently evaluated.",
    ))

    # 2. IOGP_MATCH_NOT_VIOLATION: IOGP rule matched, but no violation documented
    rule = ANTI_INFERENCE_CATALOG[AntiInferenceCode.IOGP_MATCH_NOT_VIOLATION]
    has_iogp = len(iogp_matches) > 0
    applies = has_iogp and ("violation" not in text_lower and "breach" not in text_lower and "bypassed" not in text_lower and "failed" not in text_lower)
    evaluations.append(AntiInferenceEvaluation(
        rule_code=rule.code,
        rule_name=rule.name,
        is_applicable=applies,
        prohibited_inference=rule.prohibited_inference,
        required_corroboration=rule.required_corroboration,
        is_inference_prevented=applies,
        explanation="IOGP activity context matched without evidence of procedural violation." if applies else "IOGP classification evaluated.",
    ))

    # 3. CONTROL_MENTION_NOT_EFFECTIVENESS: Control named, but effectiveness not verified
    rule = ANTI_INFERENCE_CATALOG[AntiInferenceCode.CONTROL_MENTION_NOT_EFFECTIVENESS]
    applies = any(w in text_lower for w in ["control", "barrier", "guard", "scaffold", "lanyard", "loto"]) and control_state in ("UNKNOWN", "NOT_VERIFIED", "INCORRECTLY_ASSUMED")
    evaluations.append(AntiInferenceEvaluation(
        rule_code=rule.code,
        rule_name=rule.name,
        is_applicable=applies,
        prohibited_inference=rule.prohibited_inference,
        required_corroboration=rule.required_corroboration,
        is_inference_prevented=applies,
        explanation="Control was mentioned by name but functional effectiveness was unverified." if applies else "Control effectiveness verified or absent.",
    ))

    # 4. PLANNED_ACTION_NOT_COMPLETED_CONTROL: Future intention vs completed control
    rule = ANTI_INFERENCE_CATALOG[AntiInferenceCode.PLANNED_ACTION_NOT_COMPLETED_CONTROL]
    applies = any(kw in text_lower for kw in ["will be", "should be", "planned to", "to be installed", "proposed to", "recommended to"])
    evaluations.append(AntiInferenceEvaluation(
        rule_code=rule.code,
        rule_name=rule.name,
        is_applicable=applies,
        prohibited_inference=rule.prohibited_inference,
        required_corroboration=rule.required_corroboration,
        is_inference_prevented=applies,
        explanation="Planned or recommended safety action distinguished from effective operational barrier." if applies else "No planned action conflation detected.",
    ))

    # 5. PPE_USE_NOT_DIRECT_CONTROL: PPE treated as mitigation, not direct physical barrier
    rule = ANTI_INFERENCE_CATALOG[AntiInferenceCode.PPE_USE_NOT_DIRECT_CONTROL]
    applies = any(kw in text_lower for kw in ["ppe", "helmet", "gloves", "safety shoes", "goggles", "hard hat"])
    evaluations.append(AntiInferenceEvaluation(
        rule_code=rule.code,
        rule_name=rule.name,
        is_applicable=applies,
        prohibited_inference=rule.prohibited_inference,
        required_corroboration=rule.required_corroboration,
        is_inference_prevented=applies,
        explanation="PPE availability or use recognized as secondary mitigation, not direct high-energy barrier." if applies else "Direct engineered controls evaluated.",
    ))

    # 6. HIGH_ENERGY_EQUIPMENT_NOT_PSIF: Equipment presence != PSIF precursor
    rule = ANTI_INFERENCE_CATALOG[AntiInferenceCode.HIGH_ENERGY_EQUIPMENT_NOT_PSIF]
    applies = hazard_detected and control_state in ("EFFECTIVE", "VERIFIED")
    evaluations.append(AntiInferenceEvaluation(
        rule_code=rule.code,
        rule_name=rule.name,
        is_applicable=applies,
        prohibited_inference=rule.prohibited_inference,
        required_corroboration=rule.required_corroboration,
        is_inference_prevented=applies,
        explanation="High-energy equipment present with verified controls classified as Capacity (Controlled), not PSIF precursor." if applies else "Direct barrier health evaluated.",
    ))

    return evaluations
