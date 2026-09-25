"""
PSIF Platform — Dedicated SIF Explanation and Evidence Layer

Grounded in IOGP Life-Saving Rules and serious injury/fatality (SIF) precursor science:
A SIF Precursor is defined as an event or situation where high energy was present
(or stored), a worker was exposed or had a credible exposure path to that energy,
and one or more critical controls were absent, ineffective, bypassed, or degraded.

This module provides the domain-level reasoning and evidence layer for both PSIF
and Non-PSIF candidate determinations. It produces structured, auditable explanations:
1. High-Energy Source Identification
2. Worker Exposure Pathway
3. Control Failure / Condition Evaluation
4. Credible SIF Consequence Mechanism
5. Escalation Potential
6. Narrative Evidence Extraction (verbatim quotes)
7. Structured Evidence Interpretations
8. Analytical Limitations & Missing/Uncertain Information
9. Data Quality Integration
10. Separation of Model Contributors (Positive vs. Negative SHAP)
11. Evidence Strength Assessment (Strong / Moderate / Weak)
"""

import re
from typing import Any, Dict, List, Optional
from ml_engine.text_preprocessing import is_sparse_narrative


# ── High-Energy Patterns ───────────────────────────────────────────────────────

ENERGY_PATTERNS = {
    "Pressure / Stored Energy": [
        r"\b(?:high\s+pressure|pressur(?:e|ized)|psi|bar|blowout|relief\s+valve|pipe\s+burst|flange\s+leak|air\s+receiver|hydraulic|pneumatic)\b",
    ],
    "Hydrocarbons / Flammables": [
        r"\b(?:hydrocarbon|gas\s+leak|crude|methane|flammable|ignition|explosion|fire|h2s|hydrogen\s+sulfide|condensate|blowout)\b",
    ],
    "Electrical Energy": [
        r"\b(?:high\s+voltage|electrical|electrocution|arc\s+flash|live\s+wire|generator|substation|transformer|440v|11kv|33kv)\b",
    ],
    "Gravity / Working at Height": [
        r"\b(?:working\s+at\s+height|fall\s+from\s+height|scaffold(?:ing)?|ladder|mast|derrick|elevated\s+platform|manlift|fall\s+arrest|harness)\b",
    ],
    "Heavy Lifting / Suspended Load": [
        r"\b(?:crane|hoist|rigging|suspended\s+load|sling|winch|derrick|lifting\s+operation|shackle|spreader\s+bar)\b",
    ],
    "Motor Vehicle / Heavy Equipment": [
        r"\b(?:forklift|truck|heavy\s+vehicle|trailer|crane\s+movement|excavator|collision|runaway\s+vehicle|speeding|rollover)\b",
    ],
    "Confined Space": [
        r"\b(?:confined\s+space|tank\s+entry|vessel\s+entry|manhole|sewer|oxygen\s+deficien(?:cy|t)|toxic\s+atmosphere)\b",
    ],
    "Stored Mechanical / Tension": [
        r"\b(?:stored\s+mechanical|tension(?:ed)?|spring(?:-loaded)?|flywheel|whip\s+check|wire\s+rope\s+snap|recoil)\b",
    ],
    "Thermal / Hot Work": [
        r"\b(?:welding|cutting\s+torch|grinding|hot\s+work|furnace|boiler|molten|steam\s+leak)\b",
    ],
}

# ── Worker Exposure Patterns ───────────────────────────────────────────────────

EXPOSURE_PATTERNS = [
    r"\b(?:worker|scaffolder|operator|technician|helper|roustabout|rig\s+crew|electrician|welder|driver|employee|personnel|crew|line\s+of\s+fire|in\s+the\s+path|worker\s+exposed|personnel\s+present|underneath|standing\s+near|struck\s+by|caught\s+between|pinch\s+point|crush(?:ed)?|fell|falling)\b"
]

NO_EXPOSURE_PATTERNS = [
    r"\b(?:no\s+personnel\s+present|unmanned|remote\s+location|cleared\s+area|barricaded|safe\s+distance|exclusion\s+zone\s+maintained|nobody\s+exposed|no\s+injury|evacuated)\b"
]

# ── Control Failure & Effectiveness Patterns ───────────────────────────────────

CONTROL_FAILURE_PATTERNS = [
    r"\b(?:bypassed|interlock\s+bypassed|missing\s+guard|guard\s+removed|without\s+permit|no\s+loto|lockout\s+not\s+applied|isolation\s+failed|failed\s+to\s+hold|defective|corroded|deteriorated|inadequate|breach(?:ed)?|not\s+isolated|unsecured|unauthorized|failed|not\s+hooked|not\s+tied\s+off|not\s+anchored|unanchored|no\s+harness|not\s+worn)\b"
]

CONTROL_EFFECTIVE_PATTERNS = [
    r"\b(?:interlock\s+engaged|auto(?:matic)?-shutdown|trip\s+activated|relief\s+valve\s+lifted\s+safely|ppe\s+prevented|safely\s+contained|isolated\s+properly|barricade\s+prevented|alarm\s+sounded\s+and\s+crew\s+cleared)\b"
]

# ── Credible SIF Mechanism Patterns ────────────────────────────────────────────

SIF_MECHANISMS = [
    ("High-pressure release / fluid injection / projectile", r"\b(?:high\s+pressure|pressurized|rupture|projectile|injection|blowout)\b"),
    ("Fall from height (> 2m)", r"\b(?:fall(?:ing)?|working\s+at\s+height|fall\s+from\s+height|dropped\s+from\s+height|fall\s+from\s+scaffold|fall\s+from\s+ladder|mast\s+fall)\b"),
    ("Crush / pinch under heavy suspended load", r"\b(?:suspended\s+load|dropped\s+load|crush(?:ed)?|rigging\s+failed|crane\s+toppled)\b"),
    ("Hydrocarbon fire / explosion / vapor cloud ignition", r"\b(?:gas\s+leak|hydrocarbon|flash\s+fire|explosion|ignition|fire)\b"),
    ("Electrocution / arc flash blast", r"\b(?:electrocution|electric\s+shock|live\s+wire|arc\s+flash|high\s+voltage)\b"),
    ("Toxic atmosphere / asphyxiation in confined space", r"\b(?:h2s|hydrogen\s+sulfide|confined\s+space|asphyxiat(?:ion|ed)|oxygen\s+depletion)\b"),
    ("Heavy equipment / vehicle impact or rollover", r"\b(?:vehicle\s+collision|runaway|struck\s+by\s+vehicle|rollover|forklift\s+impact)\b"),
]


def extract_matching_spans(text: str, patterns: List[str], max_spans: int = 3) -> List[str]:
    """
    Extract short sentence or phrase spans around matching regex patterns.
    """
    if not text:
        return []

    spans = []
    # Split text into rough clauses/sentences
    sentences = re.split(r"[.\n;!]+", text)

    for sentence in sentences:
        cleaned = sentence.strip()
        if not cleaned:
            continue
        for pat in patterns:
            if re.search(pat, cleaned, re.IGNORECASE):
                # Format span cleanly
                span_text = " ".join(cleaned.split())
                if len(span_text) > 120:
                    span_text = span_text[:117] + "..."
                if span_text not in spans:
                    spans.append(span_text)
                if len(spans) >= max_spans:
                    return spans
    return spans


def generate_explanation(
    record: Dict[str, Any],
    narrative: str,
    psif_score: float,
    psif_predicted: bool,
    threshold: float,
    shap_factors: Optional[List[Dict[str, Any]]] = None,
    dq_findings: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Generate an auditable, safety-science grounded SIF explanation payload.
    """
    combined_text = f"{narrative} {record.get('description', '')} {record.get('immediate_cause', '')} {record.get('equipment_involved', '')}".lower()
    is_sparse = is_sparse_narrative(narrative)

    # ── 1. High-Energy Source Identification ───────────────────────────────────
    identified_energies = []
    energy_spans = []

    # Check structured fields
    struct_energy = record.get("energy_type")
    if struct_energy and struct_energy not in ("unknown", "", None):
        identified_energies.append(struct_energy.replace("_", " ").title())

    struct_high_energy = record.get("high_energy_present")
    if struct_high_energy == "yes" and "High Energy Present" not in identified_energies:
        identified_energies.append("High Energy Confirmed (Structured)")

    # Check text patterns
    for energy_name, patterns in ENERGY_PATTERNS.items():
        matched_spans = extract_matching_spans(combined_text, patterns, max_spans=1)
        if matched_spans:
            if energy_name not in identified_energies:
                identified_energies.append(energy_name)
            energy_spans.extend(matched_spans)

    high_energy_identified = len(identified_energies) > 0

    # ── 2. Worker Exposure Pathway ─────────────────────────────────────────────
    worker_exposure_identified = False
    exposure_spans = []
    no_exposure_spans = []

    struct_exposure = record.get("worker_exposed")
    if struct_exposure == "yes":
        worker_exposure_identified = True
    elif struct_exposure == "no":
        worker_exposure_identified = False

    matched_exp = extract_matching_spans(combined_text, EXPOSURE_PATTERNS, max_spans=2)
    if matched_exp:
        exposure_spans.extend(matched_exp)
        worker_exposure_identified = True

    matched_no_exp = extract_matching_spans(combined_text, NO_EXPOSURE_PATTERNS, max_spans=1)
    if matched_no_exp:
        no_exposure_spans.extend(matched_no_exp)
        if struct_exposure != "yes":
            worker_exposure_identified = False

    # ── 3. Critical Control Condition ──────────────────────────────────────────
    control_failure_identified = False
    control_spans = []
    effective_control_spans = []

    struct_condition = record.get("control_condition")
    if struct_condition in ("failed", "bypassed", "absent"):
        control_failure_identified = True
    elif struct_condition == "effective":
        control_failure_identified = False

    if record.get("control_failed_bypassed") is True:
        control_failure_identified = True

    matched_ctrl_fail = extract_matching_spans(combined_text, CONTROL_FAILURE_PATTERNS, max_spans=2)
    if matched_ctrl_fail:
        control_spans.extend(matched_ctrl_fail)
        control_failure_identified = True

    matched_ctrl_eff = extract_matching_spans(combined_text, CONTROL_EFFECTIVE_PATTERNS, max_spans=1)
    if matched_ctrl_eff:
        effective_control_spans.extend(matched_ctrl_eff)
        if struct_condition not in ("failed", "bypassed", "absent"):
            control_failure_identified = False

    # ── 4. Credible SIF Consequence Mechanism ──────────────────────────────────
    identified_mechanisms = []
    for mech_name, pat in SIF_MECHANISMS:
        if re.search(pat, combined_text, re.IGNORECASE):
            identified_mechanisms.append(mech_name)

    credible_mechanism_identified = (
        len(identified_mechanisms) > 0 and (high_energy_identified or worker_exposure_identified)
    )

    # ── 5. Escalation Potential ────────────────────────────────────────────────
    escalation_identified = False
    escalation_desc = "No immediate credible escalation pathway identified."
    if high_energy_identified and control_failure_identified:
        escalation_identified = True
        escalation_desc = (
            "Credible escalation pathway exists: high-energy source with compromised "
            "or absent controls can lead directly to uncontrolled energy release."
        )
    elif high_energy_identified and worker_exposure_identified:
        escalation_identified = True
        escalation_desc = (
            "Worker in active line-of-fire or proximity to high-energy source; "
            "minor disturbance can escalate to serious impact."
        )

    # ── 6. Narrative Evidence Spans ────────────────────────────────────────────
    narrative_evidence = []
    for sp in energy_spans + exposure_spans + control_spans:
        if sp not in narrative_evidence:
            narrative_evidence.append(sp)

    # Contradicting evidence
    contradicting_evidence = []
    for sp in no_exposure_spans:
        contradicting_evidence.append(f"Personnel isolated/unexposed: “{sp}”")
    for sp in effective_control_spans:
        contradicting_evidence.append(f"Engineered control operated effectively: “{sp}”")

    # ── 7. Structured Evidence ─────────────────────────────────────────────────
    structured_evidence = []
    field_mappings = [
        ("Department", record.get("department")),
        ("Job Task", record.get("job_task")),
        ("Equipment Involved", record.get("equipment_involved")),
        ("Immediate Cause", record.get("immediate_cause")),
        ("Root Cause", record.get("root_cause_category")),
        ("High Energy Present", record.get("high_energy_present")),
        ("Energy Type", record.get("energy_type")),
        ("Worker Exposed", record.get("worker_exposed")),
        ("Control Type", record.get("control_type")),
        ("Control Condition", record.get("control_condition")),
        ("Near Miss", "Yes" if record.get("near_miss") is True else ("No" if record.get("near_miss") is False else None)),
    ]
    for label, val in field_mappings:
        if val and val not in ("unknown", "None", ""):
            structured_evidence.append({
                "field": label,
                "value": str(val).replace("_", " ").title() if isinstance(val, str) else str(val)
            })

    # ── 8. Missing / Uncertain Information ─────────────────────────────────────
    missing_information = []
    if not record.get("energy_type") or record.get("energy_type") == "unknown":
        missing_information.append("Energy source type not specified in structured record.")
    if not record.get("worker_exposed") or record.get("worker_exposed") == "unknown":
        missing_information.append("Worker exposure status not definitively recorded.")
    if not record.get("control_condition") or record.get("control_condition") == "unknown":
        missing_information.append("Critical control condition (effective/failed/absent) unverified.")
    if not record.get("job_task"):
        missing_information.append("Specific job task omitted.")
    if not record.get("immediate_cause"):
        missing_information.append("Immediate cause not recorded.")
    if is_sparse:
        missing_information.append("Incident narrative is sparse (< 10 words), limiting contextual analysis.")

    # ── 9. Analytical Limitations ──────────────────────────────────────────────
    analytical_limitations = []
    if is_sparse:
        analytical_limitations.append(
            "Sparse input text: the description contains too few words to reliably verify physical precursor conditions."
        )
    if dq_findings:
        analytical_limitations.append(
            "Source record contains data quality warnings / anomalies which may affect assessment reliability."
        )
    analytical_limitations.append(
        "PSIF Candidate determination is a statistical model assessment and requires human HSE validation."
    )

    # ── 10. Supporting Evidence & Reasoning ────────────────────────────────────
    supporting_evidence = []
    reasoning = []

    if psif_predicted:
        if high_energy_identified:
            supporting_evidence.append(f"High-energy source identified ({', '.join(identified_energies[:2])}).")
        if worker_exposure_identified:
            supporting_evidence.append("Worker exposure pathway identified.")
        if control_failure_identified:
            supporting_evidence.append("Critical control weakness, bypass, or absence identified.")
        if credible_mechanism_identified:
            supporting_evidence.append(f"Credible SIF consequence mechanism identified ({identified_mechanisms[0]}).")
        if escalation_identified:
            supporting_evidence.append("Plausible escalation potential present.")

        if not supporting_evidence:
            supporting_evidence.append("Statistical feature pattern aligned with high-potential precursor events.")

        reasoning = list(supporting_evidence)
    else:
        if not high_energy_identified:
            reasoning.append("No credible high-energy exposure identified.")
        if not worker_exposure_identified:
            reasoning.append("No worker exposure mechanism identified.")
        if not control_failure_identified:
            reasoning.append("Critical controls appear effective or hazard was low-energy.")
        if not credible_mechanism_identified:
            reasoning.append("No credible serious/fatal escalation mechanism established.")

        if is_sparse:
            reasoning = [
                "The narrative does not contain enough information to establish worker exposure or a credible SIF mechanism.",
                "Notice: This is insufficient evidence, not affirmative proof that the incident was safe."
            ]

    # ── 11. Evidence Strength & Analytical Status ──────────────────────────────
    if is_sparse:
        analytical_status = "INSUFFICIENT_EVIDENCE"
        evidence_strength = "Weak"
    elif psif_predicted:
        score_diff = psif_score - threshold
        confirmed_count = sum([high_energy_identified, worker_exposure_identified, control_failure_identified])
        if confirmed_count >= 2 and score_diff >= 0.2:
            evidence_strength = "Strong"
        elif confirmed_count >= 1 or score_diff >= 0.05:
            evidence_strength = "Moderate"
        else:
            evidence_strength = "Weak"
        analytical_status = "AVAILABLE"
    else:
        # Not PSIF
        score_diff = threshold - psif_score
        unconfirmed_count = sum([not high_energy_identified, not worker_exposure_identified, not control_failure_identified])
        if unconfirmed_count >= 2 and score_diff >= 0.2 and not is_sparse:
            evidence_strength = "Strong"
        elif unconfirmed_count >= 1 and score_diff >= 0.05:
            evidence_strength = "Moderate"
        else:
            evidence_strength = "Weak"
        analytical_status = "AVAILABLE"

    # ── 12. SHAP Model Contributors (Separated Positive & Negative) ────────────
    positive_contributors = []
    negative_contributors = []

    if shap_factors:
        for factor in shap_factors:
            f_name = factor.get("feature", "")
            f_val = float(factor.get("contribution", 0.0))
            item = {
                "feature": f_name,
                "contribution": round(f_val, 4),
                "interpretation": "Increases PSIF model score" if f_val > 0 else "Decreases PSIF model score"
            }
            if f_val > 0:
                positive_contributors.append(item)
            elif f_val < 0:
                negative_contributors.append(item)

    # Sort each list by absolute contribution descending
    positive_contributors.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    negative_contributors.sort(key=lambda x: abs(x["contribution"]), reverse=True)

    # Normalize data quality findings payload
    dq_payload = dq_findings if isinstance(dq_findings, dict) else {
        "has_warnings": bool(dq_findings),
        "findings": dq_findings if isinstance(dq_findings, list) else ([] if not dq_findings else [str(dq_findings)])
    }

    return {
        "psif_classification": "PSIF" if psif_predicted else "NOT PSIF",
        "psif_model_score": round(psif_score, 4),
        "threshold_used": round(threshold, 4),
        "evidence_strength": evidence_strength,
        "analytical_status": analytical_status,
        "high_energy_source": {
            "identified": high_energy_identified,
            "source_type": identified_energies[0].lower() if identified_energies else "none",
            "energy_types": identified_energies,
            "summary": f"High-energy source: {', '.join(identified_energies)}" if high_energy_identified else "None identified",
        },
        "worker_exposure": {
            "identified": worker_exposure_identified,
            "summary": "Worker exposed or in line of fire" if worker_exposure_identified else "No direct exposure identified",
        },
        "control_condition": {
            "identified": control_failure_identified,
            "condition": "bypassed_or_failed" if control_failure_identified else ("effective" if struct_condition and "effective" in struct_condition else (struct_condition or "unknown")),
            "summary": "Critical control failure, bypass, or absence identified" if control_failure_identified else "Controls appear held or not compromised",
        },
        "control_failure": {
            "identified": control_failure_identified,
            "condition": struct_condition or "unknown",
            "summary": "Critical control failure, bypass, or absence identified" if control_failure_identified else "Controls appear held or not compromised",
        },
        "credible_mechanism": {
            "identified": credible_mechanism_identified,
            "credible": credible_mechanism_identified,
            "mechanisms": identified_mechanisms,
            "summary": identified_mechanisms[0] if identified_mechanisms else "No credible SIF mechanism established",
        },
        "credible_sif_consequence": {
            "identified": credible_mechanism_identified,
            "credible": credible_mechanism_identified,
            "mechanisms": identified_mechanisms,
            "summary": identified_mechanisms[0] if identified_mechanisms else "No credible SIF consequence mechanism established",
        },
        "escalation_potential": {
            "identified": escalation_identified,
            "credible": escalation_identified,
            "description": escalation_desc,
        },
        "supporting_evidence": supporting_evidence,
        "contradicting_evidence": contradicting_evidence,
        "narrative_evidence": narrative_evidence[:3],
        "structured_evidence": structured_evidence,
        "missing_information": missing_information,
        "missing_or_uncertain_info": missing_information,
        "data_quality_findings": dq_payload,
        "analytical_limitations": analytical_limitations,
        "reasoning": reasoning,
        "model_contributors": {
            "positive": positive_contributors[:5],
            "negative": negative_contributors[:5],
            "positive_contributors": positive_contributors[:5],
            "negative_contributors": negative_contributors[:5],
            "interpretation": "Relative feature contributions to PSIF model score. Non-causal.",
            "disclaimer": "Model feature contributions reflect statistical model weights, not physical causality."
        },
        "disclaimer": (
            "PSIF Model Score reflects statistical precursor pattern strength and is NOT a calibrated "
            "real-world probability of injury or fatality."
        )
    }
