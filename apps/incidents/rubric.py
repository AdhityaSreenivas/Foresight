"""
HSE Review Rubric for PSIF (Potential Serious Injury & Fatality) Classification.
OIL India Problem Statement 26165.

This module formalizes the domain-grounded evaluation framework for human safety
professionals reviewing unsafe act, unsafe condition, and near-miss reports.

IMPORTANT PRINCIPLES:
1. Flexible domain criteria, NOT rigid numeric thresholds:
   High-energy sources are judged by credible physical potential to cause fatal trauma
   or life-altering impairment in context of equipment, geometry, and exposure,
   not arbitrary cutoffs (e.g. pressure > 100 psi or height > 1.8m are contextual
   indicators, never deterministic gates).
2. Independent evidence sufficiency:
   The machine's < 10 words analytical warning does NOT dictate the human call.
   Reviewers independently assess narrative sufficiency. A concise report like
   "Worker fell from scaffold" can legitimately be recognized as a valid PSIF event.
3. Three-state human annotation:
   - PSIF: Credible high-energy hazard + worker exposure + control failure/absence + credible SIF consequence.
   - NOT PSIF: Low-energy hazard, robust/effective barriers, or minor non-escalating condition.
   - INSUFFICIENT INFORMATION: Narrative lacks essential facts to make a defensible determination.
"""

from typing import Any, Dict, List, Optional, Tuple


HSE_RUBRIC_VERSION = "1.0"

RUBRIC_CRITERIA = {
    "A_hazard": {
        "name": "High-Energy Hazard",
        "description": (
            "Was a credible high-energy source present? "
            "(e.g., heavy rotating/moving machinery, working at elevated heights, "
            "pressurized fluid or gas systems, electrical potential, toxic or flammable "
            "hydrocarbons, suspended loads, confined space with atmospheric hazard, etc.). "
            "Judged by credible physical capacity to cause fatal trauma or permanent disability, "
            "not rigid numeric thresholds."
        ),
        "options": ["present", "absent", "unclear"],
    },
    "B_exposure": {
        "name": "Worker Exposure",
        "description": (
            "Was a worker exposed or was there a credible exposure pathway? "
            "(e.g., worker inside line of fire, within hazard envelope, unmitigated trajectory, "
            "or direct interaction with the release zone)."
        ),
        "options": ["exposed", "not_exposed", "unclear"],
    },
    "C_control": {
        "name": "Critical Control Condition",
        "description": (
            "Was a primary barrier or critical safety control absent, failed, breached, "
            "bypassed, ineffective, or degraded? "
            "(e.g., missing guard, defective relief valve, failed lock-out/tag-out, bypassed interlock)."
        ),
        "options": ["failed_or_absent", "effective", "degraded", "none_required", "unclear"],
    },
    "D_consequence": {
        "name": "SIF Consequence Mechanism",
        "description": (
            "Is there a credible physical mechanism for serious injury or fatality? "
            "(e.g., blunt force trauma, crush injury, amputation, severe burns, electrocution, asphyxiation)."
        ),
        "options": ["credible_sif", "minor_only", "unclear"],
    },
    "E_escalation": {
        "name": "Escalation Pathway",
        "description": (
            "Could the reported near-miss or unsafe condition plausibly escalate to a severe/fatal "
            "outcome under routine operational variability or realistic worst-case conditions?"
        ),
        "options": ["plausible_escalation", "unlikely_escalation", "unclear"],
    },
    "F_sufficiency": {
        "name": "Evidence Sufficiency",
        "description": (
            "Does the report contain enough factual context to reach a defensible classification? "
            "Evaluated by domain judgment independently of character or word counts."
        ),
        "options": ["sufficient", "insufficient"],
    },
}

HSE_REVIEW_RUBRIC_V1 = {
    "version": HSE_RUBRIC_VERSION,
    "criteria": RUBRIC_CRITERIA,
}


def evaluate_rubric(rubric_answers: Dict[str, Any]) -> Tuple[str, str, Dict[str, Any]]:
    """
    Evaluate structured rubric answers and compute a recommended classification and rationale.

    Returns:
        (recommended_decision, suggested_rationale, summary_dict)
        where recommended_decision is one of 'PSIF', 'NOT_PSIF', 'INSUFFICIENT_INFORMATION'.
    """
    answers = rubric_answers or {}
    
    sufficiency = answers.get("F_sufficiency", "sufficient")
    hazard = answers.get("A_hazard")
    exposure = answers.get("B_exposure")
    control = answers.get("C_control")
    consequence = answers.get("D_consequence")
    escalation = answers.get("E_escalation")

    summary = {
        "rubric_version": HSE_RUBRIC_VERSION,
        "is_sufficient": sufficiency == "sufficient",
        "has_high_energy": hazard == "present",
        "has_exposure": exposure == "exposed",
        "has_control_compromise": control in ("failed_or_absent", "degraded"),
        "has_credible_sif": consequence == "credible_sif",
        "has_escalation": escalation == "plausible_escalation",
    }

    # 1. If reviewer explicitly flags evidence as insufficient, recommend INSUFFICIENT_INFORMATION
    if sufficiency == "insufficient":
        rationale = (
            "Report lacks sufficient operational or factual context to defensibly establish "
            "the presence of high-energy hazard, barrier conditions, or exposure pathways."
        )
        return "INSUFFICIENT_INFORMATION", rationale, summary

    # 2. Strong PSIF Precursor profile:
    # High energy + (exposure or plausible escalation) + (control compromise or absent) + credible SIF mechanism
    if (
        hazard == "present"
        and consequence == "credible_sif"
        and (exposure == "exposed" or escalation == "plausible_escalation")
        and control in ("failed_or_absent", "degraded", "unclear")
    ):
        rationale = (
            "High-energy hazard present with worker exposure/escalation potential and "
            "compromised/absent critical control, representing a credible SIF mechanism."
        )
        return "PSIF", rationale, summary

    # 3. Clear NOT PSIF profile:
    # Absent high energy, or effective controls with no exposure and no plausible escalation
    if (
        hazard == "absent"
        or (consequence == "minor_only" and escalation == "unlikely_escalation")
        or (control == "effective" and exposure == "not_exposed" and escalation == "unlikely_escalation")
    ):
        rationale = (
            "Low energy potential, effective barriers, or absence of credible worker exposure "
            "and escalation pathways."
        )
        return "NOT_PSIF", rationale, summary

    # 4. Ambiguous or borderline case requiring expert judgment:
    if "unclear" in (hazard, exposure, consequence):
        rationale = (
            "Essential incident elements (hazard presence, exposure, or consequence) remain "
            "unclear in narrative; human review judgment required."
        )
        return "INSUFFICIENT_INFORMATION", rationale, summary

    # Default fallback based on consequence & escalation
    if consequence == "credible_sif" or escalation == "plausible_escalation":
        return "PSIF", "Credible SIF consequence or plausible escalation potential identified.", summary
    else:
        return "NOT_PSIF", "No credible SIF mechanism or escalation pathway identified.", summary


def validate_rubric_answers(answers: Dict[str, Any]) -> List[str]:
    """Validate rubric answer keys and option values against the schema."""
    errors = []
    if not isinstance(answers, dict):
        return ["Rubric answers must be a JSON object."]

    for criterion_key, config in RUBRIC_CRITERIA.items():
        val = answers.get(criterion_key)
        if val is not None and val not in config["options"]:
            errors.append(
                f"Invalid value '{val}' for criterion '{criterion_key}'. "
                f"Allowed options: {', '.join(config['options'])}"
            )

    return errors
