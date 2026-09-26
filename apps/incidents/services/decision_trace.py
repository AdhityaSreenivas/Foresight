import math
from typing import Dict, Any, List
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.db.models import Q

from apps.incidents.models import Incident, IOGPRuleTag, IncidentDataQuality
from apps.predictions.models import PredictionResult
from apps.incidents.services.data_quality import validate_incident_quality
from apps.incidents.services.normalization import normalize_incident_entities
from apps.incidents.services.methodology import get_all_methodology_notices
from apps.incidents.services.evidence import (
    evidence_from_shap,
    evidence_from_incident_field,
    evidence_from_iogp_tag,
    evidence_from_similar_incident,
    evidence_from_recurrence_pattern,
    evidence_from_control_status,
    evidence_from_data_quality,
)
from ml_engine.text_preprocessing import is_sparse_narrative

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)

def find_related_incidents(
    target_incident: Incident,
    top_k: int = None,
    min_similarity: float = None,
    max_days: int = None,
    same_department: bool = None
) -> List[Dict[str, Any]]:
    """
    Retrieve related observations using cosine similarity of the persisted embeddings.
    """
    if top_k is None:
        top_k = getattr(settings, "RELATED_INCIDENT_TOP_K", 5)
    if min_similarity is None:
        min_similarity = getattr(settings, "RELATED_INCIDENT_MIN_SIMILARITY", 0.75)
    if max_days is None:
        max_days = getattr(settings, "RELATED_INCIDENT_DAYS", 30)
    if same_department is None:
        same_department = getattr(settings, "RELATED_INCIDENT_SAME_DEPARTMENT", True)

    try:
        target_embedding = target_incident.embedding
        if not target_embedding or not target_embedding.vector:
            return []
    except Incident.embedding.RelatedObjectDoesNotExist:
        return []

    # Exclude the target itself
    candidates_qs = Incident.objects.exclude(id=target_incident.id).select_related('embedding')

    # Bounded Search by Date
    if max_days:
        ref_date = target_incident.incident_date or target_incident.created_at.date()
        cutoff_date = ref_date - timedelta(days=max_days)
        candidates_qs = candidates_qs.filter(
            Q(incident_date__gte=cutoff_date) |
            Q(incident_date__isnull=True, created_at__date__gte=cutoff_date)
        )
    
    if same_department and target_incident.department:
        candidates_qs = candidates_qs.filter(department=target_incident.department)

    # Cap candidate search pool to avoid unbounded linear in-memory scan over hundreds of thousands of rows
    max_candidates = getattr(settings, "RELATED_INCIDENT_MAX_CANDIDATES", 500)
    candidates_qs = candidates_qs.order_by('-created_at')[:max_candidates]

    candidates = list(candidates_qs)
    if not candidates:
        return []

    valid_candidates = []
    vectors = []
    target_vec = target_embedding.vector

    for candidate in candidates:
        try:
            cand_embedding = candidate.embedding
            if not cand_embedding or not cand_embedding.vector:
                continue
            # Gate 8: Ensure we're comparing embeddings from the same encoder
            if cand_embedding.embedding_model != target_embedding.embedding_model:
                continue
            valid_candidates.append(candidate)
            vectors.append(cand_embedding.vector)
        except Incident.embedding.RelatedObjectDoesNotExist:
            continue

    if not valid_candidates:
        return []

    # Vectorized cosine similarity using NumPy if available
    try:
        import numpy as np
        use_numpy = True
    except ImportError:
        use_numpy = False

    if use_numpy:
        import numpy as np
        matrix = np.array(vectors, dtype=np.float32)
        target_arr = np.array(target_vec, dtype=np.float32)
        target_norm = np.linalg.norm(target_arr)
        if target_norm == 0:
            return []
        target_normed = target_arr / target_norm

        matrix_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix_norms[matrix_norms == 0] = 1.0
        matrix_normed = matrix / matrix_norms

        sim_scores = np.dot(matrix_normed, target_normed)

        matched_indices = np.where(sim_scores >= min_similarity)[0]
        if len(matched_indices) == 0:
            return []

        sorted_order = np.argsort(-sim_scores[matched_indices])
        top_indices = matched_indices[sorted_order][:top_k]

        filtered_candidates = [valid_candidates[i] for i in top_indices]
        scores = [float(sim_scores[i]) for i in top_indices]
    else:
        scored = []
        for cand, vec in zip(valid_candidates, vectors):
            sim = cosine_similarity(target_vec, vec)
            if sim >= min_similarity:
                scored.append((cand, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        filtered_candidates = [x[0] for x in scored[:top_k]]
        scores = [x[1] for x in scored[:top_k]]

    if not filtered_candidates:
        return []

    # Batch fetch associated IOGP rules for top_k matches only (eliminates N+1)
    cand_ids = [c.id for c in filtered_candidates]
    tags_by_cand = {cid: [] for cid in cand_ids}
    for tag in IOGPRuleTag.objects.filter(incident_id__in=cand_ids):
        tags_by_cand[tag.incident_id].append(tag.rule)

    results = []
    for candidate, sim in zip(filtered_candidates, scores):
        snippet = ""
        if candidate.composite_narrative:
            snippet = candidate.composite_narrative[:100].strip() + ("..." if len(candidate.composite_narrative) > 100 else "")

        date_val = candidate.incident_date.isoformat() if candidate.incident_date else None

        results.append({
            "incident_id": str(candidate.id),
            "similarity_score": round(sim, 3),
            "similarity_percent": f"{round(sim * 100)}%",
            "incident_date": date_val,
            "location": candidate.location,
            "department": candidate.department,
            "job_task": candidate.job_task,
            "iogp_rules": tags_by_cand.get(candidate.id, []),
            "short_narrative_snippet": snippet
        })

    return results


def evaluate_psif_sufficiency(incident: Incident, dq_record=None, prediction=None) -> tuple[str, str]:
    if prediction is None:
        try:
            prediction = incident.prediction
        except Exception:
            prediction = None
    if dq_record is None:
        try:
            dq_record = incident.data_quality
        except Exception:
            dq_record = None

    if not prediction:
        return "NOT_AVAILABLE", "No PSIF prediction exists for this incident."
    if prediction.is_sparse_input:
        return (
            "INSUFFICIENT_EVIDENCE",
            "The narrative does not contain enough information to establish worker exposure or a credible SIF mechanism. "
            "This must not be interpreted as strong evidence that the incident is genuinely non-PSIF."
        )
    if dq_record and dq_record.status == IncidentDataQuality.Status.CRITICAL:
        return "AVAILABLE_WITH_WARNING", "Source record contains a critical data-quality contradiction."
    return "AVAILABLE", None

def evaluate_similarity_sufficiency(incident: Incident, dq_record, prediction) -> tuple[str, str]:
    if prediction:
        if prediction.is_sparse_input:
            return "NOT_RUN", "Sparse input — semantic similarity is not meaningful."
    elif is_sparse_narrative(incident.composite_narrative):
        return "NOT_RUN", "Insufficient narrative for semantic similarity."

    # Readiness check: confirm incident embedding exists and is ready
    has_embedding = False
    try:
        has_embedding = hasattr(incident, "embedding") and incident.embedding is not None and bool(incident.embedding.vector)
    except (Incident.embedding.RelatedObjectDoesNotExist, AttributeError):
        has_embedding = False

    if not has_embedding:
        return "NOT_READY", "Embedding not generated yet — semantic similarity unavailable until embedded."

    if dq_record and dq_record.status == IncidentDataQuality.Status.CRITICAL:
        return "AVAILABLE_WITH_WARNING", "Source record contains a data-quality contradiction."
    return "AVAILABLE", None

def evaluate_recurrence_sufficiency(incident: Incident, dq_record) -> tuple[str, str]:
    if not incident.department:
        return "NOT_RUN", "Insufficient event information (missing site/department)."
    if dq_record and dq_record.status == IncidentDataQuality.Status.CRITICAL:
        return "AVAILABLE_WITH_WARNING", "Source record contains a data-quality contradiction."
    return "AVAILABLE", None

def evaluate_iogp_sufficiency(incident: Incident, dq_record) -> tuple[str, str]:
    # IOGP can run on any text fields, but if it's completely sparse we might still run it on what we have.
    # We'll just flag data quality.
    if dq_record and dq_record.status == IncidentDataQuality.Status.CRITICAL:
        return "AVAILABLE_WITH_WARNING", "Source record contains a data-quality contradiction."
    return "AVAILABLE", None

def build_analytical_assessment(incident: Incident) -> Dict[str, Any]:
    """
    The canonical aggregation layer for incident analysis.
    Produces a structured payload that represents the true decision trace.
    """
    assessment = {
        "data_quality": {
            "status": "VALID",
            "findings": []
        },
        "psif_model": {
            "status": "NOT_RUN",
            "reason": None,
            "score": None,
            "classification": None,
            "prioritization_band": None,
            "threshold": None,
            "model_version": None,
            "evidence": []
        },
        "iogp": {
            "status": "NOT_RUN",
            "reason": None,
            "items": []
        },
        "similarity": {
            "status": "NOT_RUN",
            "reason": None,
            "items": []
        },
        "recurrence": {
            "status": "NOT_RUN",
            "reason": None,
            "items": []
        },
        "multi_site_recurrence": {
            "status": "NOT_RUN",
            "reason": None,
            "items": []
        },
        "incident_evidence": [],
        "canonical_evidence": [],
        "normalized_entities": {},
        "methodology_disclosures": {},
        "limitations": [],
        "provenance": []
    }
    
    # 0. Data Quality
    try:
        dq_record = incident.data_quality
    except Exception:
        dq_record = validate_incident_quality(incident)
    assessment["data_quality"] = {
        "status": dq_record.status,
        "quality_version": dq_record.quality_version,
        "findings": dq_record.findings
    }
    
    if dq_record.status == IncidentDataQuality.Status.CRITICAL:
        assessment["limitations"].append({
            "type": "critical_data_quality",
            "message": "The source record contains critical data-quality conflicts. The analytical result should be reviewed before being treated as reliable incident information."
        })
    elif dq_record.status == IncidentDataQuality.Status.WARNING:
        assessment["limitations"].append({
            "type": "warning_data_quality",
            "message": "The source record contains data-quality warnings. The analytical result may depend on incomplete or ambiguous information."
        })
    
    # Limitation for Prototype (General)
    assessment["limitations"].append({
        "type": "prototype_model",
        "message": "The PSIF predictive model is a prototype. These signals are provided to support human HSE review and do not establish physical causation or confirm that a PSIF event occurred."
    })

    # Fetch prediction if available
    prediction = getattr(incident, 'prediction', None)

    # 1. PSIF MODEL
    psif_status, psif_reason = evaluate_psif_sufficiency(incident, dq_record, prediction)
    assessment["psif_model"]["status"] = psif_status
    assessment["psif_model"]["reason"] = psif_reason
    
    if psif_status in ["AVAILABLE", "AVAILABLE_WITH_WARNING", "INSUFFICIENT_EVIDENCE"] and prediction:
        threshold_val = getattr(settings, "PSIF_THRESHOLD", 0.5)
        if prediction.model_version and prediction.model_version.metrics:
            threshold_val = prediction.model_version.metrics.get(
                "selected_threshold",
                prediction.model_version.metrics.get("optimal_threshold", threshold_val)
            )

        explanation = getattr(prediction, "explanation_detail", {})
        if not explanation:
            from ml_engine.explanation_engine import generate_explanation
            explanation = generate_explanation(
                record={
                    "department": incident.department,
                    "location": incident.location,
                    "job_task": incident.job_task,
                    "equipment_involved": incident.equipment_involved,
                    "immediate_cause": incident.immediate_cause,
                    "root_cause_category": incident.root_cause_category,
                    "high_energy_present": incident.high_energy_present,
                    "energy_type": incident.energy_type,
                    "worker_exposed": incident.worker_exposed,
                    "control_type": incident.control_type,
                    "control_condition": incident.control_condition,
                    "control_failed_bypassed": incident.control_failed_bypassed,
                    "near_miss": incident.near_miss,
                },
                narrative=incident.composite_narrative or incident.description or "",
                psif_score=prediction.psif_probability,
                psif_predicted=prediction.psif_predicted,
                threshold=threshold_val,
                shap_factors=prediction.top_factors,
                dq_findings=dq_record.findings if dq_record else None
            )

        evidence_strength = getattr(prediction, "evidence_strength", None) or explanation.get("evidence_strength", "Moderate")

        assessment["psif_model"].update({
            "score": round(prediction.psif_probability_percent, 1),
            "psif_score": round(prediction.psif_score, 4),
            "score_percent": round(prediction.psif_probability_percent, 1),
            "classification": prediction.binary_classification,
            "binary_decision": prediction.binary_classification,
            "is_psif": prediction.psif_predicted,
            "evidence_strength": evidence_strength,
            "prioritization_band": prediction.risk_level.title() if prediction.risk_level else "Legacy",
            "threshold": threshold_val,
            "model_version": prediction.model_version.version_label,
            "explanation": explanation,
            "positive_contributors": explanation.get("model_contributors", {}).get("positive", []),
            "negative_contributors": explanation.get("model_contributors", {}).get("negative", []),
            "supporting_evidence": explanation.get("supporting_evidence", []),
            "contradicting_evidence": explanation.get("contradicting_evidence", []),
            "narrative_evidence": explanation.get("narrative_evidence", []),
            "structured_evidence": explanation.get("structured_evidence", []),
            "missing_information": explanation.get("missing_information", []),
            "analytical_limitations": explanation.get("analytical_limitations", []),
            "reasoning": explanation.get("reasoning", []),
        })
        assessment["analytical_status"] = psif_status
        assessment["binary_decision"] = prediction.binary_classification
        assessment["evidence_strength"] = evidence_strength
        assessment["provenance"].append({
            "source": "model_prediction",
            "model_version": prediction.model_version.version_label,
            "prediction_timestamp": prediction.created_at.isoformat()
        })
        for factor in prediction.top_factors:
            feature_name = factor.get("feature", "")
            contrib = factor.get("contribution", 0)
            direction = "Increased model score" if contrib > 0 else "Decreased model score"
            assessment["psif_model"]["evidence"].append({
                "feature": feature_name,
                "contribution": round(contrib, 3),
                "direction": direction,
                "source": "SHAP feature attribution"
            })

    # 2. INCIDENT EVIDENCE (RAW FACTS)
    fields_to_check = [
        ("Department", incident.department),
        ("Location", incident.location),
        ("Job Task", incident.job_task),
        ("Equipment", incident.equipment_involved),
        ("Injury Type", incident.injury_type),
        ("Body Part", incident.body_part),
        ("Immediate Cause", incident.immediate_cause),
        ("Root Cause", incident.root_cause_category),
        ("Actual Severity", incident.get_severity_actual_display() if incident.severity_actual else None),
        ("Potential Severity", incident.get_severity_potential_display() if incident.severity_potential else None),
    ]
    for label, val in fields_to_check:
        if val:
            assessment["incident_evidence"].append({
                "field": label,
                "value": val,
                "source": "incident_record"
            })

    # 3. IOGP EVIDENCE
    iogp_status, iogp_reason = evaluate_iogp_sufficiency(incident, dq_record)
    assessment["iogp"]["status"] = iogp_status
    assessment["iogp"]["reason"] = iogp_reason
    
    if iogp_status in ["AVAILABLE", "AVAILABLE_WITH_WARNING"]:
        iogp_tags = IOGPRuleTag.objects.filter(incident=incident)
        for tag in iogp_tags:
            assessment["iogp"]["items"].append({
                "rule": tag.rule,
                "matched_phrases": tag.matched_keywords,
                "matched_fields": tag.matched_fields,
                "method": tag.classification_method,
                "match_strength": tag.confidence,
                "classifier_version": tag.classifier_version
            })
            assessment["provenance"].append({
                "source": "iogp_classification",
                "rule": tag.rule,
                "classifier_version": tag.classifier_version
            })

    # 4. SIMILARITY EVIDENCE
    sim_status, sim_reason = evaluate_similarity_sufficiency(incident, dq_record, prediction)
    assessment["similarity"]["status"] = sim_status
    assessment["similarity"]["reason"] = sim_reason
    
    if sim_status in ["AVAILABLE", "AVAILABLE_WITH_WARNING"]:
        related = find_related_incidents(incident)
        assessment["similarity"]["items"] = related
        for r in related:
            assessment["provenance"].append({
                "source": "related_incident",
                "incident_id": r["incident_id"],
                "similarity_score": r["similarity_score"]
            })

    # 5. RECURRENCE EVIDENCE
    rec_status, rec_reason = evaluate_recurrence_sufficiency(incident, dq_record)
    assessment["recurrence"]["status"] = rec_status
    assessment["recurrence"]["reason"] = rec_reason
    assessment["multi_site_recurrence"]["status"] = rec_status # Using same sufficiency for multi-site
    assessment["multi_site_recurrence"]["reason"] = rec_reason
    
    if rec_status in ["AVAILABLE", "AVAILABLE_WITH_WARNING"]:
        from apps.dashboard.pattern_detection import detect_recurring_patterns, detect_multi_site_recurrence
        
        # Scoped recurrence detection for this incident's department and job task
        site_patterns = detect_recurring_patterns(
            site=incident.department,
            activity=incident.job_task if incident.job_task else None
        )
        my_patterns = []
        for p in site_patterns:
            if str(incident.id) in p.get("incident_ids", []):
                # Calculate dq warnings for pattern in batch
                pattern_dq_warnings = 0
                pattern_inc_ids = p.get("incident_ids", [])
                dq_statuses = dict(
                    IncidentDataQuality.objects.filter(incident_id__in=pattern_inc_ids)
                    .values_list("incident_id", "status")
                )
                for p_inc_id in pattern_inc_ids:
                    q_status = dq_statuses.get(p_inc_id)
                    if q_status is None:
                        try:
                            import uuid
                            q_status = dq_statuses.get(uuid.UUID(p_inc_id))
                        except Exception:
                            pass
                    if q_status in [IncidentDataQuality.Status.WARNING, IncidentDataQuality.Status.CRITICAL]:
                        pattern_dq_warnings += 1
                p["dq_warnings_count"] = pattern_dq_warnings
                my_patterns.append(p)
                assessment["provenance"].append({
                    "source": "recurrence_pattern",
                    "site": p["site"],
                    "activity": p["activity"],
                    "rule": p["rule"]
                })
        
        assessment["recurrence"]["items"] = my_patterns
        
        # get rules for this incident if it was available
        my_iogp_rules = []
        if iogp_status in ["AVAILABLE", "AVAILABLE_WITH_WARNING"]:
            my_iogp_rules = [t["rule"] for t in assessment["iogp"]["items"]]
            
        if my_iogp_rules:
            site_multi_site = detect_multi_site_recurrence(rules=my_iogp_rules)
            my_multi_site = []
            for p in site_multi_site:
                if incident.department in p.get("sites", []):
                    my_multi_site.append(p)
            assessment["multi_site_recurrence"]["items"] = my_multi_site
        else:
            assessment["multi_site_recurrence"]["items"] = []

    # 6. CANONICAL NORMALIZATION & EVIDENCE SYNTHESIS
    norm_entities = normalize_incident_entities(incident)
    assessment["normalized_entities"] = {k: v.to_dict() for k, v in norm_entities.items()}
    assessment["methodology_disclosures"] = get_all_methodology_notices()

    canonical_evidence_list = []

    # Data Quality findings
    for finding in assessment["data_quality"].get("findings", []):
        canonical_evidence_list.append(evidence_from_data_quality(finding).to_dict())

    # PSIF Model factors
    if prediction and getattr(prediction, "top_factors", None):
        for factor in prediction.top_factors:
            canonical_evidence_list.append(evidence_from_shap(factor).to_dict())

    # Incident Structured Facts
    for label, val in fields_to_check:
        if val:
            canonical_evidence_list.append(
                evidence_from_incident_field(
                    field_name=label.lower().replace(" ", "_"),
                    value=val,
                    label=label
                ).to_dict()
            )

    # Barrier / Control Condition
    if incident.control_type or incident.control_condition:
        canonical_evidence_list.append(
            evidence_from_control_status(
                control_type=incident.control_type,
                control_condition=incident.control_condition,
                failed_or_bypassed=incident.control_failed_bypassed
            ).to_dict()
        )

    # IOGP rule matches
    for iogp_item in assessment["iogp"].get("items", []):
        canonical_evidence_list.append(evidence_from_iogp_tag(iogp_item).to_dict())

    # Similar incidents
    for sim_item in assessment["similarity"].get("items", []):
        canonical_evidence_list.append(evidence_from_similar_incident(sim_item).to_dict())

    # Recurrence patterns
    for rec_item in assessment["recurrence"].get("items", []):
        canonical_evidence_list.append(evidence_from_recurrence_pattern(rec_item).to_dict())

    assessment["canonical_evidence"] = canonical_evidence_list

    # Attach structured PSIF domain reasoning engine assessment
    try:
        from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment
        assessment["psif_reasoning"] = build_incident_reasoning_assessment(
            incident, prediction=prediction, dq_record=dq_record
        )
    except Exception:
        assessment["psif_reasoning"] = None

    # Canonical 3-Stage Information Hierarchy
    # Stage 1: MODEL OUTPUT
    # Stage 2: EVIDENCE ASSESSMENT
    # Stage 3: FINAL TRIAGE STATUS
    stages_payload = build_triage_stages(
        incident=incident,
        prediction=prediction,
        psif_reasoning=assessment.get("psif_reasoning"),
        dq_record=dq_record,
    )
    assessment["triage_stages"] = stages_payload
    if "psif_model" in assessment and isinstance(assessment["psif_model"], dict):
        assessment["psif_model"]["triage_stages"] = stages_payload

    return assessment


def build_triage_stages(
    incident: Incident,
    prediction=None,
    psif_reasoning=None,
    dq_record=None,
) -> Dict[str, Any]:
    """
    Canonical 3-stage information hierarchy builder:
    1. MODEL OUTPUT: ML model candidate & score before evidence-based safety reconciliation.
    2. EVIDENCE ASSESSMENT: Physical controls, exposure, hazard energy, and pathway state.
    3. FINAL TRIAGE STATUS: Authoritative system decision (PSIF, NOT PSIF, or INSUFFICIENT INFORMATION).
    """
    # ── 1. STAGE 1: MODEL OUTPUT ───────────────────────────────────────────────
    is_sparse = bool(
        getattr(prediction, "is_sparse_input", False)
        or (dq_record and dq_record.status == IncidentDataQuality.Status.CRITICAL)
    )
    is_model_candidate = bool(prediction and prediction.psif_predicted and not is_sparse)

    if is_sparse:
        candidate_label = "INSUFFICIENT INFORMATION"
    elif is_model_candidate:
        candidate_label = "PSIF CANDIDATE"
    elif prediction:
        candidate_label = "NOT PSIF"
    else:
        candidate_label = "PENDING INFERENCE"

    score_val = prediction.psif_probability if prediction and prediction.psif_probability is not None else None
    score_formatted = f"{score_val:.3f}" if score_val is not None else "—"

    model_output = {
        "heading": "MODEL OUTPUT",
        "candidate_label": candidate_label,
        "is_candidate": is_model_candidate,
        "score": score_val,
        "score_formatted": score_formatted,
        "score_label": "PSIF MODEL SCORE",
        "explanation": "ML model assessment before evidence-based safety reconciliation.",
        "candidate_note": "Model candidate — not the final triage decision.",
        "evidence_strength": getattr(prediction, "evidence_strength", "Moderate") if prediction else "Moderate",
        "is_sparse": is_sparse,
    }

    # ── 2. STAGE 2: EVIDENCE ASSESSMENT ────────────────────────────────────────
    ev_summary = psif_reasoning.get("evidence_summary", {}) if isinstance(psif_reasoning, dict) else {}
    recon = psif_reasoning.get("reconciliation") if isinstance(psif_reasoning, dict) else None

    # Hazard
    raw_hazard = ev_summary.get("hazard_type") or incident.energy_type
    if raw_hazard:
        hazard_fmt = str(raw_hazard).replace("_", " ").title()
        if "pressure" in str(raw_hazard).lower():
            hazard_fmt = "Stored Pressure / Pneumatic"
        elif "gravity" in str(raw_hazard).lower() or "fall" in str(raw_hazard).lower():
            hazard_fmt = "Fall from Elevation / Gravity"
        elif "motion" in str(raw_hazard).lower() or "kinetic" in str(raw_hazard).lower():
            hazard_fmt = "Mobile Equipment / Kinetic"
        elif "electrical" in str(raw_hazard).lower():
            hazard_fmt = "Electrical / High Voltage"
    elif incident.high_energy_present == "yes":
        hazard_fmt = "High Energy Present"
    else:
        hazard_fmt = "Low / Contained Energy Evaluated"

    # Worker Exposure
    raw_exposure = ev_summary.get("exposure_state")
    if raw_exposure:
        raw_exp_str = str(raw_exposure).replace("_", " ").title()
        if "Direct" in raw_exp_str:
            exposure_fmt = "Direct Exposure (Line of Fire)"
        elif "Interrupted" in raw_exp_str or "Segregated" in raw_exp_str or "Isolated" in raw_exp_str:
            exposure_fmt = "Segregated / Safeguarded Zone"
        else:
            exposure_fmt = raw_exp_str
    elif incident.worker_exposed == "yes":
        exposure_fmt = "Direct Exposure"
    else:
        exposure_fmt = "No Direct Line of Fire Identified"

    # Barrier / Control
    raw_control = ev_summary.get("control_type") or incident.control_type
    if raw_control:
        barrier_fmt = str(raw_control).replace("_", " ").title()
    elif incident.control_condition:
        barrier_fmt = f"Primary Safeguard ({incident.control_condition.title()})"
    else:
        barrier_fmt = "Physical / Engineering Barrier"

    # Barrier State
    raw_state = ev_summary.get("control_state") or incident.control_condition
    if raw_state:
        state_str = str(raw_state).upper()
        if "EFFECTIVE" in state_str or "HELD" in state_str or "INTACT" in state_str:
            barrier_state_fmt = "Effective / Intact"
        elif "FAILED" in state_str or "COMPROMISED" in state_str or "BYPASS" in state_str:
            barrier_state_fmt = "Compromised / Failed"
        elif "ABSENT" in state_str or "MISSING" in state_str:
            barrier_state_fmt = "Absent / Not Deployed"
        else:
            barrier_state_fmt = str(raw_state).replace("_", " ").title()
    else:
        barrier_state_fmt = "Evaluated via Safety Rules"

    # Consequence Pathway
    raw_pathway = ev_summary.get("consequence_pathway")
    if raw_pathway:
        p_str = str(raw_pathway).upper()
        if "INTERRUPTED" in p_str or "CONTAINED" in p_str:
            pathway_fmt = "Interrupted"
        elif "OPEN" in p_str or "ESCALAT" in p_str:
            pathway_fmt = "Open"
        elif "UNKNOWN" in p_str or "INSUFFICIENT" in p_str:
            pathway_fmt = "Undetermined"
        else:
            pathway_fmt = str(raw_pathway).replace("_", " ").title()
    else:
        pathway_fmt = "Under Verification"

    evidence_assessment = {
        "heading": "EVIDENCE ASSESSMENT",
        "hazard": hazard_fmt,
        "exposure": exposure_fmt,
        "barrier": barrier_fmt,
        "barrier_state": barrier_state_fmt,
        "consequence_pathway": pathway_fmt,
        "explanation": "Evidence assessment determines whether the conditions support an open PSIF pathway.",
        "why_psif": psif_reasoning.get("WHY_PSIF") if isinstance(psif_reasoning, dict) else "",
        "why_not_psif": psif_reasoning.get("WHY_NOT_PSIF") if isinstance(psif_reasoning, dict) else "",
        "what_is_missing": psif_reasoning.get("WHAT_IS_MISSING") if isinstance(psif_reasoning, dict) else "",
    }

    # ── 3. STAGE 3: FINAL TRIAGE STATUS ────────────────────────────────────────
    raw_final = None
    if isinstance(psif_reasoning, dict) and psif_reasoning.get("final_policy_decision"):
        raw_final = psif_reasoning.get("final_policy_decision")
    elif is_sparse:
        raw_final = "INSUFFICIENT INFORMATION"
    elif prediction:
        raw_final = "PSIF" if prediction.psif_predicted else "NOT PSIF"

    # Canonical normalization to ONE and ONLY ONE of: PSIF, NOT PSIF, INSUFFICIENT INFORMATION
    if raw_final:
        norm = str(raw_final).replace("_", " ").strip().upper()
        if "INSUFFICIENT" in norm:
            final_status = "INSUFFICIENT INFORMATION"
        elif norm == "PSIF":
            final_status = "PSIF"
        else:
            final_status = "NOT PSIF"
    else:
        final_status = "PENDING INFERENCE"

    # Rationale derivation
    recon_rationale = (
        getattr(recon, "policy_rationale", None)
        or (recon.get("policy_rationale") if isinstance(recon, dict) else None)
    )

    if final_status == "NOT PSIF":
        if pathway_fmt != "Interrupted" and raw_pathway is None:
            evidence_assessment["consequence_pathway"] = "Interrupted"
        final_reason = (
            evidence_assessment["why_not_psif"]
            or recon_rationale
            or "Evidence indicates the serious-consequence pathway was interrupted by an effective control or contained energy."
        )
    elif final_status == "PSIF":
        if pathway_fmt != "Open" and raw_pathway is None:
            evidence_assessment["consequence_pathway"] = "Open"
        final_reason = (
            evidence_assessment["why_psif"]
            or recon_rationale
            or "Evidence confirms an open serious-consequence pathway with direct personnel exposure and compromised barriers."
        )
    elif final_status == "INSUFFICIENT INFORMATION":
        if pathway_fmt == "Under Verification":
            evidence_assessment["consequence_pathway"] = "Undetermined"
        final_reason = (
            evidence_assessment["what_is_missing"]
            or "Available evidence is insufficient to establish or exclude a serious-consequence pathway."
        )
    else:
        final_reason = "Awaiting model prediction and evidence evaluation."

    # Reconciliation Progression Summary
    if is_model_candidate and final_status == "NOT PSIF":
        reconciliation_summary = (
            "ML model flagged precursor patterns, but evidence assessment verified that the serious-consequence "
            "pathway was interrupted by effective safeguards."
        )
    elif is_model_candidate and final_status == "PSIF":
        reconciliation_summary = (
            "ML model flagged precursor signals, and safety evidence confirmed an active, unmitigated "
            "high-energy exposure pathway."
        )
    elif not is_model_candidate and final_status == "PSIF":
        reconciliation_summary = (
            "Rule-grounded safety engineering identified an open serious-consequence pathway despite lower "
            "statistical model scoring."
        )
    elif final_status == "INSUFFICIENT INFORMATION":
        reconciliation_summary = (
            "Narrative information is insufficient to confirm or exclude a serious-consequence pathway. "
            "Quarantined from binary classification."
        )
    else:
        reconciliation_summary = (
            "Model score and evidence assessment concordantly indicate a routine / controlled observation."
        )

    final_triage = {
        "heading": "FINAL TRIAGE STATUS",
        "status": final_status,
        "reason": final_reason,
        "reconciliation_summary": reconciliation_summary,
        "internal_state": getattr(recon, "internal_reasoning_state", None) or (psif_reasoning.get("internal_reasoning_state") if isinstance(psif_reasoning, dict) else None),
    }

    return {
        "model_output": model_output,
        "evidence_assessment": evidence_assessment,
        "final_triage": final_triage,
    }


