"""
PSIF Platform — Why NOT PSIF / Evidence-Break Workbench Engine

Core Purpose:
Allows a safety analyst investigating a NOT PSIF incident (or reviewing any candidate)
to understand:
1. Why did the model not consider this a PSIF candidate?
2. What evidence is missing or breaks the credible SIF pathway?
3. What is the evidence chain status (Hazard -> Exposure -> Control -> Consequence -> Escalation)?
4. What relevant SHAP factors influenced the model score (separated positive/negative/suppressed)?
5. What specific missing evidence would be decision-relevant?
6. Clear differentiation between:
   - Sparse analytical warnings
   - Data-quality warnings
   - Ingestion rejections
   - Human INSUFFICIENT_INFORMATION determinations

CRITICAL COMPLIANCE RULES:
- Never call the model score a probability. Terminology is 'PSIF Model Score'.
- SHAP values represent mathematical model weights, not physical causality.
- Missing evidence is never equated to affirmative proof of safety.
- Genuine insufficient information must never be treated as implicit NOT PSIF.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
import re

from apps.incidents.models import Incident, IncidentDataQuality
from apps.predictions.models import PredictionResult
from apps.incidents.services.normalization import normalize_incident_entities
from apps.incidents.services.methodology import get_methodology_notice
from apps.incidents.services.evidence import (
    AnalyticalEvidence,
    EvidenceSource,
    EvidenceType,
    EvidenceStrength,
)
from ml_engine.text_preprocessing import is_sparse_narrative
from ml_engine.explanation_engine import (
    ENERGY_PATTERNS,
    EXPOSURE_PATTERNS,
    NO_EXPOSURE_PATTERNS,
    CONTROL_FAILURE_PATTERNS,
    CONTROL_EFFECTIVE_PATTERNS,
    SIF_MECHANISMS,
    extract_matching_spans,
)


# ── Chain Link States ─────────────────────────────────────────────────────────

class ChainState:
    SUPPORTED = "SUPPORTED"      # Affirmative positive evidence present
    PARTIAL = "PARTIAL"          # Incomplete, weak, or secondary evidence present
    MISSING = "MISSING"          # Expected evidence absent; breaks the SIF pathway
    UNCERTAIN = "UNCERTAIN"      # Ambiguous, conflicting, or sparse reporting


# ── Core Analysis Dataclasses ─────────────────────────────────────────────────

@dataclass
class EvidenceChainLink:
    link_id: str                 # 'hazard_source', 'exposure', 'control', 'credible_consequence', 'escalation'
    title: str                   # 'Hazard / Energy Source', etc.
    state: str                   # ChainState
    summary: str                 # Concise state summary
    finding: str                 # Analytical finding
    traceable_items: List[Dict[str, Any]] = field(default_factory=list)
    missing_evidence: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelContributionSummary:
    positive_contributors: List[Dict[str, Any]]
    negative_contributors: List[Dict[str, Any]]
    suppressed_count: int
    suppressed_contributors: List[Dict[str, Any]]
    disclaimer: str = "Model contribution — not causality."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Evidence Break Analysis Engine ────────────────────────────────────────────

def analyze_evidence_break(incident: Incident) -> Dict[str, Any]:
    """
    Constructs the complete Why NOT PSIF / Evidence-Break Workbench payload
    for a given incident report.
    """
    prediction = getattr(incident, "prediction", None)
    
    # 1. Primary Model Decision & Score Metadata
    if prediction:
        psif_score = round(prediction.psif_score, 4)
        score_percent = round(prediction.psif_probability_percent, 1)
        binary_decision = prediction.binary_classification
        is_psif = prediction.psif_predicted
        evidence_strength = prediction.evidence_strength or "Moderate"
        model_version = prediction.model_version.version_label if prediction.model_version else "Unknown"
        threshold_val = getattr(prediction.model_version, "metrics", {}).get("selected_threshold", 0.5)
        raw_top_factors = prediction.top_factors or []
    else:
        psif_score = None
        score_percent = None
        binary_decision = "UNKNOWN"
        is_psif = False
        evidence_strength = "Unknown"
        model_version = "None"
        threshold_val = 0.5
        raw_top_factors = []

    # 2. Text & Sparse Checks
    narrative_text = incident.composite_narrative or incident.description or ""
    is_sparse = is_sparse_narrative(narrative_text, min_words=10)
    
    combined_corpus = (
        f"{narrative_text} {incident.description or ''} {incident.job_task or ''} "
        f"{incident.immediate_cause or ''} {incident.equipment_involved or ''}"
    ).lower()

    # 3. Data Quality & Ingestion Status
    dq_record = getattr(incident, "data_quality", None)
    dq_status = dq_record.status if dq_record else IncidentDataQuality.Status.VALID
    dq_findings = dq_record.findings if dq_record else []
    
    # Check human adjudication
    human_adjudication = incident.adjudication_status
    is_human_insufficient = (
        incident.is_psif_human_label is None 
        and human_adjudication == Incident.AdjudicationStatus.ADJUDICATED
    )

    # 4. Normalized Safety Entities
    norm_entities = normalize_incident_entities(incident)

    # ── Evaluate 5 Links of the SIF Evidence Chain ────────────────────────────

    # LINK 1: Hazard / High-Energy Source
    hazard_trace = []
    hazard_state = ChainState.MISSING
    hazard_summary = "No high-energy source evidenced"
    hazard_finding = "Available report does not document a high-energy hazard, heavy suspended load, or severe pressure."
    hazard_missing = "Verification of energy magnitude, operating pressure, voltage, or working height."

    # Check structured energy
    struct_energy = incident.energy_type
    struct_high_energy = incident.high_energy_present
    if struct_high_energy == "yes" or (struct_energy and struct_energy not in ("unknown", "", "none", "other")):
        hazard_state = ChainState.SUPPORTED
        hazard_summary = f"High-energy hazard: {norm_entities['energy_source'].canonical_value}"
        hazard_finding = f"Structured safety metadata confirms {norm_entities['energy_source'].canonical_value}."
        hazard_missing = None
        hazard_trace.append({
            "source_type": "structured",
            "field": "energy_type",
            "value": norm_entities["energy_source"].canonical_value,
            "raw_value": incident.energy_type,
        })

    # Check narrative energy matches
    found_energies = []
    for ename, patterns in ENERGY_PATTERNS.items():
        spans = extract_matching_spans(combined_corpus, patterns, max_spans=1)
        if spans:
            found_energies.append((ename, spans[0]))
            hazard_trace.append({
                "source_type": "narrative_quote",
                "field": "composite_narrative",
                "label": ename,
                "quote": spans[0],
            })

    if found_energies and hazard_state != ChainState.SUPPORTED:
        hazard_state = ChainState.SUPPORTED
        hazard_summary = f"High energy identified: {found_energies[0][0]}"
        hazard_finding = f"Narrative text documents high-energy indicators: {', '.join(e[0] for e in found_energies[:2])}."
        hazard_missing = None
    elif is_sparse and hazard_state == ChainState.MISSING:
        hazard_state = ChainState.UNCERTAIN
        hazard_summary = "Energy state uncertain (sparse narrative)"
        hazard_finding = "Report text contains insufficient detail to confirm or rule out high-energy presence."

    link_hazard = EvidenceChainLink(
        link_id="hazard_source",
        title="Hazard / Energy Source",
        state=hazard_state,
        summary=hazard_summary,
        finding=hazard_finding,
        traceable_items=hazard_trace,
        missing_evidence=hazard_missing,
    )

    # LINK 2: Worker Exposure
    exposure_trace = []
    exposure_state = ChainState.MISSING
    exposure_summary = "No direct worker exposure evidenced"
    exposure_finding = "Available narrative and structured records do not place a worker in the direct line of fire or exposure pathway."
    exposure_missing = "Worker location relative to the hazard, line-of-fire pathway, or presence during the event."

    struct_exposed = incident.worker_exposed
    if struct_exposed == "yes":
        exposure_state = ChainState.SUPPORTED
        exposure_summary = "Worker exposure confirmed (structured)"
        exposure_finding = "Reported structured safety attributes confirm worker was exposed."
        exposure_missing = None
        exposure_trace.append({
            "source_type": "structured",
            "field": "worker_exposed",
            "value": "Yes",
            "raw_value": struct_exposed,
        })
    elif struct_exposed == "no":
        exposure_state = ChainState.MISSING
        exposure_summary = "Worker not exposed (structured confirmation)"
        exposure_finding = "Structured safety attributes confirm worker was not exposed or in the hazard path."
        exposure_missing = "Contextual reason why worker was not exposed."
        exposure_trace.append({
            "source_type": "structured",
            "field": "worker_exposed",
            "value": "No",
            "raw_value": struct_exposed,
        })

    exp_spans = extract_matching_spans(combined_corpus, EXPOSURE_PATTERNS, max_spans=2)
    no_exp_spans = extract_matching_spans(combined_corpus, NO_EXPOSURE_PATTERNS, max_spans=1)

    if no_exp_spans:
        exposure_state = ChainState.MISSING
        exposure_summary = "No exposure confirmed in narrative"
        exposure_finding = f"Narrative text explicitly confirms absence of exposed workers: '{no_exp_spans[0]}'."
        exposure_missing = None
        exposure_trace.append({
            "source_type": "narrative_quote",
            "field": "composite_narrative",
            "label": "Exclusion / No Exposure",
            "quote": no_exp_spans[0],
        })
    elif exp_spans and struct_exposed != "no" and exposure_state != ChainState.SUPPORTED:
        exposure_state = ChainState.SUPPORTED
        exposure_summary = "Worker exposure evidenced in narrative"
        exposure_finding = f"Narrative excerpt documents worker in proximity or line of fire: '{exp_spans[0]}'."
        exposure_missing = None
        for s in exp_spans:
            exposure_trace.append({
                "source_type": "narrative_quote",
                "field": "composite_narrative",
                "label": "Worker Exposure",
                "quote": s,
            })
    elif exp_spans and struct_exposed == "no":
        for s in exp_spans:
            exposure_trace.append({
                "source_type": "narrative_quote",
                "field": "composite_narrative",
                "label": "Narrative Mention (Structured Record Confirms No Exposure)",
                "quote": s,
            })
    elif is_sparse and exposure_state == ChainState.MISSING:
        exposure_state = ChainState.UNCERTAIN
        exposure_summary = "Exposure uncertain (sparse narrative)"
        exposure_finding = "Insufficient descriptive text to verify whether personnel were present or in the line of fire."

    link_exposure = EvidenceChainLink(
        link_id="exposure",
        title="Worker Exposure",
        state=exposure_state,
        summary=exposure_summary,
        finding=exposure_finding,
        traceable_items=exposure_trace,
        missing_evidence=exposure_missing,
    )

    # LINK 3: Critical Control Integrity
    # Note: In SIF precursor science, a compromised/absent/bypassed control SUPPORTS the precursor pathway.
    # An effective control holding or intact breaks the pathway (MISSING failure).
    control_trace = []
    control_state = ChainState.MISSING
    control_summary = "No control failure or bypass evidenced"
    control_finding = "No evidence that critical controls failed, were absent, or were bypassed during the event."
    control_missing = "Documentation of whether barriers held, failed, were absent, or were overridden."

    struct_condition = incident.control_condition
    struct_failed_bypassed = incident.control_failed_bypassed

    if struct_condition in ("failed", "bypassed", "absent") or struct_failed_bypassed is True:
        control_state = ChainState.SUPPORTED
        control_summary = f"Control compromised: {norm_entities['control_condition'].canonical_value}"
        control_finding = f"Structured fields confirm critical control was {norm_entities['control_condition'].canonical_value}."
        control_missing = None
        control_trace.append({
            "source_type": "structured",
            "field": "control_condition",
            "value": norm_entities["control_condition"].canonical_value,
            "raw_value": struct_condition,
        })
        if incident.control_type:
            control_trace.append({
                "source_type": "structured",
                "field": "control_type",
                "value": norm_entities["control_type"].canonical_value,
                "raw_value": incident.control_type,
            })
    elif struct_condition == "effective":
        control_state = ChainState.MISSING
        control_summary = "Controls held effectively"
        control_finding = "Direct controls remained effective and held, preventing precursor escalation."
        control_missing = None
        control_trace.append({
            "source_type": "structured",
            "field": "control_condition",
            "value": "Effective / Held",
            "raw_value": struct_condition,
        })

    ctrl_fail_spans = extract_matching_spans(combined_corpus, CONTROL_FAILURE_PATTERNS, max_spans=2)
    ctrl_eff_spans = extract_matching_spans(combined_corpus, CONTROL_EFFECTIVE_PATTERNS, max_spans=1)

    if ctrl_fail_spans and control_state != ChainState.SUPPORTED:
        control_state = ChainState.SUPPORTED
        control_summary = "Control failure evidenced in narrative"
        control_finding = f"Narrative text documents control failure or bypass: '{ctrl_fail_spans[0]}'."
        control_missing = None
        for s in ctrl_fail_spans:
            control_trace.append({
                "source_type": "narrative_quote",
                "field": "composite_narrative",
                "label": "Control Failure/Bypass",
                "quote": s,
            })
    elif ctrl_eff_spans:
        control_state = ChainState.MISSING
        control_summary = "Control functioned properly"
        control_finding = f"Narrative text confirms safety control functioned: '{ctrl_eff_spans[0]}'."
        control_missing = None
        control_trace.append({
            "source_type": "narrative_quote",
            "field": "composite_narrative",
            "label": "Control Functioned",
            "quote": ctrl_eff_spans[0],
        })
    elif is_sparse and control_state == ChainState.MISSING:
        control_state = ChainState.UNCERTAIN
        control_summary = "Control state uncertain (sparse narrative)"
        control_finding = "Report text does not specify which critical controls were in place or whether they held."

    link_control = EvidenceChainLink(
        link_id="control",
        title="Critical Control Integrity",
        state=control_state,
        summary=control_summary,
        finding=control_finding,
        traceable_items=control_trace,
        missing_evidence=control_missing,
    )

    # LINK 4: Credible SIF Consequence Mechanism
    consequence_trace = []
    consequence_state = ChainState.MISSING
    consequence_summary = "No credible fatal/serious mechanism identified"
    consequence_finding = "The event lacks an identified mechanism capable of fatal or life-altering harm."
    consequence_missing = "Detailed physics of release, fall height, projectile speed, or toxic concentration."

    found_mechanisms = []
    for mech_name, mech_pat in SIF_MECHANISMS:
        spans = extract_matching_spans(combined_corpus, [mech_pat], max_spans=1)
        if spans:
            found_mechanisms.append((mech_name, spans[0]))
            consequence_trace.append({
                "source_type": "narrative_quote",
                "field": "composite_narrative",
                "label": mech_name,
                "quote": spans[0],
            })

    if found_mechanisms:
        consequence_state = ChainState.SUPPORTED
        consequence_summary = f"Credible SIF mechanism: {found_mechanisms[0][0]}"
        consequence_finding = f"Narrative supports credible serious consequence pathway: {found_mechanisms[0][0]}."
        consequence_missing = None
    elif incident.severity_potential in (Incident.SeverityPotential.SERIOUS, Incident.SeverityPotential.FATALITY):
        consequence_state = ChainState.PARTIAL
        consequence_summary = f"Assessed potential severity: {incident.get_severity_potential_display()}"
        consequence_finding = f"Safety officer assessed {incident.get_severity_potential_display()} potential severity, but physical mechanism is unevidenced in text."
        consequence_missing = "Physical mechanism matching the assessed potential severity."
        consequence_trace.append({
            "source_type": "structured",
            "field": "severity_potential",
            "value": incident.get_severity_potential_display(),
            "raw_value": incident.severity_potential,
        })
    elif is_sparse:
        consequence_state = ChainState.UNCERTAIN
        consequence_summary = "Consequence potential uncertain (sparse narrative)"
        consequence_finding = "Insufficient descriptive information to establish whether a fatal or serious outcome was credible."

    link_consequence = EvidenceChainLink(
        link_id="credible_consequence",
        title="Credible SIF Consequence",
        state=consequence_state,
        summary=consequence_summary,
        finding=consequence_finding,
        traceable_items=consequence_trace,
        missing_evidence=consequence_missing,
    )

    # LINK 5: Escalation Potential
    escalation_trace = []
    escalation_state = ChainState.MISSING
    escalation_summary = "No credible escalation pathway evidenced"
    escalation_finding = "The event was localized and self-limiting, without secondary escalation vectors or nearby hazards."
    escalation_missing = "Facility context, nearby active processes, secondary containment, or operational factors."

    if hazard_state == ChainState.SUPPORTED and consequence_state == ChainState.SUPPORTED:
        escalation_state = ChainState.SUPPORTED
        escalation_summary = "Plausible escalation pathway supported"
        escalation_finding = "High energy combined with credible mechanism presents plausible escalation potential."
        escalation_missing = None
    elif is_sparse:
        escalation_state = ChainState.UNCERTAIN
        escalation_summary = "Escalation uncertain (sparse narrative)"
        escalation_finding = "Report text does not describe surrounding equipment or facility layout."

    link_escalation = EvidenceChainLink(
        link_id="escalation",
        title="Escalation Potential",
        state=escalation_state,
        summary=escalation_summary,
        finding=escalation_finding,
        traceable_items=escalation_trace,
        missing_evidence=escalation_missing,
    )

    evidence_chain = [link_hazard, link_exposure, link_control, link_consequence, link_escalation]

    # ── Identify Specific Evidence Breaks ─────────────────────────────────────

    evidence_breaks = []
    what_would_change = []

    if is_sparse:
        evidence_breaks.append({
            "category": "sparse_narrative",
            "title": "Sparse Report Narrative",
            "description": "Narrative is sparse (< 10 words); conclusion is therefore evidence-limited rather than affirmative proof of safety.",
            "impact": "Limits model and analytical inference. Score may not reflect true field hazard.",
            "severity": "warning"
        })
        what_would_change.append("Comprehensive narrative detailing the work being done, exact sequence of events, and safety equipment in use.")

    if hazard_state in (ChainState.MISSING, ChainState.UNCERTAIN):
        evidence_breaks.append({
            "category": "hazard_missing",
            "title": "No High-Energy Hazard Established",
            "description": "The event does not document high-pressure lines, high voltage, elevated heights, heavy suspended loads, or toxic atmospheres.",
            "impact": "Breaks the primary foundation of the Serious Injury & Fatality (SIF) precursor model.",
            "severity": "high"
        })
        what_would_change.append("Documentation of stored energy magnitude, system operating pressure, voltage, chemical identity, or height above ground.")

    if hazard_state == ChainState.SUPPORTED and exposure_state in (ChainState.MISSING, ChainState.UNCERTAIN):
        evidence_breaks.append({
            "category": "exposure_missing",
            "title": "High Energy Mentioned, But Direct Exposure Not Established",
            "description": "A high-energy system or equipment was involved, but available evidence indicates no personnel were in the line of fire or exposure path.",
            "impact": "Without worker exposure or a credible exposure path, an event cannot constitute a fatal/serious injury precursor.",
            "severity": "high"
        })
        what_would_change.append("Specific worker position relative to the energy release, line of fire pathway, or presence within the barricaded zone.")

    if control_state in (ChainState.MISSING, ChainState.UNCERTAIN) and not is_sparse:
        evidence_breaks.append({
            "category": "control_intact",
            "title": "Critical Controls Maintained / No Barrier Failure",
            "description": "No evidence that safety interlocks, LOTO, permits, guarding, or fall protection failed or were bypassed.",
            "impact": "Effective controls prevent energy propagation to personnel.",
            "severity": "medium"
        })
        what_would_change.append("Evidence that an active control failed, was bypassed, degraded, or absent during the critical task phase.")

    if consequence_state in (ChainState.MISSING, ChainState.UNCERTAIN) and not is_sparse:
        evidence_breaks.append({
            "category": "consequence_missing",
            "title": "No Credible Serious/Fatal Mechanism Evidenced",
            "description": "The physical mechanism lacks the capacity for life-altering injury or death.",
            "impact": "Events lacking high-severity physical capacity are properly excluded from PSIF prioritization.",
            "severity": "high"
        })
        what_would_change.append("Evidence of higher consequence potential (e.g., fall distance > 2m, toxic gas concentration, projectile velocity).")

    # If no specific break was triggered (e.g. high-scoring incident), provide clear feedback
    if not evidence_breaks and is_psif:
        evidence_breaks.append({
            "category": "none_supported_psif",
            "title": "Complete SIF Pathway Supported",
            "description": "All five links of the SIF precursor pathway are supported by available evidence. The incident is classified as a PSIF candidate.",
            "impact": "Meets PSIF precursor criteria.",
            "severity": "info"
        })

    # ── Process SHAP Contributors (Separating Positive, Negative, Suppressed) ──

    positive_contributors = []
    negative_contributors = []
    suppressed_contributors = []

    for factor in raw_top_factors:
        feat_name = factor.get("feature", "")
        contrib = float(factor.get("contribution", 0.0))
        item = {
            "feature": feat_name,
            "feature_label": feat_name.replace("_", " ").title(),
            "contribution": round(contrib, 4),
            "abs_contribution": round(abs(contrib), 4),
            "direction": "positive" if contrib > 0 else ("negative" if contrib < 0 else "neutral"),
            "interpretation": (
                f"Increases PSIF model score by {abs(contrib):.3f}"
                if contrib > 0.001 else
                (f"Decreases PSIF model score by {abs(contrib):.3f}" if contrib < -0.001 else "Negligible influence")
            )
        }
        if contrib > 0.001:
            positive_contributors.append(item)
        elif contrib < -0.001:
            negative_contributors.append(item)
        else:
            suppressed_contributors.append(item)

    positive_contributors.sort(key=lambda x: x["abs_contribution"], reverse=True)
    negative_contributors.sort(key=lambda x: x["abs_contribution"], reverse=True)

    model_contributions = ModelContributionSummary(
        positive_contributors=positive_contributors,
        negative_contributors=negative_contributors,
        suppressed_count=len(suppressed_contributors),
        suppressed_contributors=suppressed_contributors,
        disclaimer="Model contribution — not causality."
    )

    # ── Assemble Clean Unified Workbench Payload ──────────────────────────────

    return {
        "incident_id": str(incident.id),
        "external_id": incident.external_id,
        "date": incident.incident_date.isoformat() if incident.incident_date else None,
        "location": incident.location,
        "department": incident.department,
        "job_task": incident.job_task,
        "equipment_involved": incident.equipment_involved,
        
        # Primary Model Status
        "prediction_summary": {
            "score": psif_score,
            "score_percent": score_percent,
            "binary_decision": binary_decision,
            "is_psif": is_psif,
            "evidence_strength": evidence_strength,
            "threshold": threshold_val,
            "model_version": model_version,
            "score_label": "PSIF Model Score",
            "score_notice": "PSIF Model Score from active model; score is not a calibrated probability."
        },

        # Evidence Chain
        "evidence_chain": [link.to_dict() for link in evidence_chain],
        "broken_links_count": sum(1 for link in evidence_chain if link.state == ChainState.MISSING),
        "uncertain_links_count": sum(1 for link in evidence_chain if link.state == ChainState.UNCERTAIN),
        "supported_links_count": sum(1 for link in evidence_chain if link.state == ChainState.SUPPORTED),

        # Why NOT PSIF Core Analysis
        "evidence_breaks": evidence_breaks,
        "what_would_change": what_would_change,

        # SHAP Model Contributions
        "model_contributions": model_contributions.to_dict(),

        # Data Quality & Governance Indicators
        "governance": {
            "is_sparse": is_sparse,
            "sparse_warning": (
                "Sparse narrative (< 10 words): Analysis is evidence-limited."
                if is_sparse else None
            ),
            "dq_status": dq_status,
            "dq_findings": dq_findings,
            "human_adjudication": human_adjudication,
            "is_human_insufficient": is_human_insufficient,
            "human_insufficient_notice": (
                "Human HSE expert has determined this record has INSUFFICIENT INFORMATION. "
                "This is not an affirmative NOT PSIF."
                if is_human_insufficient else None
            )
        },

        # Methodology Notice
        "methodology": {
            "psif_model": get_methodology_notice("psif_model"),
            "shap": get_methodology_notice("shap"),
            "data_quality": get_methodology_notice("data_quality"),
        }
    }
