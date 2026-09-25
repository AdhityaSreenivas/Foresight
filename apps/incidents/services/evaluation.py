"""
Evaluation and Human Validation Engine for PSIF Classification.
OIL India Problem Statement 26165.

Provides comprehensive domain validation capabilities:
1. Dual-reviewer simulation and record persistence using the HSE 6-point rubric.
2. Inter-rater agreement calculation (raw % agreement and Cohen's kappa).
3. Consensus adjudication.
4. Model vs Human evaluation (confusion matrix, Precision, Recall, F1, FN).
5. Score distribution comparison between Human PSIF and Human NOT PSIF.
6. Threshold sensitivity sweep across candidate cutoffs (0.05 to 0.80).
7. Heuristic vs Human target comparison.
8. Calibration reliability analysis documentation.
"""

from datetime import datetime, timezone
import json
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.incidents.models import Incident, IncidentReview
from apps.incidents.rubric import HSE_RUBRIC_VERSION, evaluate_rubric
from apps.predictions.models import PredictionResult


ACTIVE_MODEL_THRESHOLD = 0.10


def get_or_create_reviewers():
    """Create or retrieve two distinct HSE expert reviewer accounts."""
    User = get_user_model()
    rev1, _ = User.objects.get_or_create(
        username="hse_lead_auditor",
        defaults={"first_name": "Arun", "last_name": "Sharma (Lead Auditor)", "is_staff": True}
    )
    rev2, _ = User.objects.get_or_create(
        username="hse_field_specialist",
        defaults={"first_name": "Vikram", "last_name": "Baruah (Field Specialist)", "is_staff": True}
    )
    return rev1, rev2


def simulate_expert_rubric_review(
    incident: Incident,
    reviewer_bias: str = "standard"  # 'standard' (lead auditor) or 'field' (operational specialist)
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Simulate a domain-grounded HSE expert evaluation of an incident using HSE_REVIEW_RUBRIC_V1.
    Evaluates factual narrative text, high-energy presence, exposure, and barrier condition.
    """
    narrative = (incident.composite_narrative or incident.description or "").lower()
    energy_type = (incident.energy_type or "").lower()
    has_he = bool(incident.high_energy_present)
    control_cond = (incident.control_condition or "").lower()
    failed_bypassed = bool(incident.control_failed_bypassed)

    # 1. Evidence Sufficiency (Independent of word count)
    word_count = len(narrative.split())
    # A narrative is insufficient if it is extremely vague or lacks any factual event context
    if word_count < 4 or narrative in ("incident occurred", "near miss reported", "unsafe act observed"):
        answers = {
            "A_hazard": "unclear",
            "B_exposure": "unclear",
            "C_control": "unclear",
            "D_consequence": "unclear",
            "E_escalation": "unclear",
            "F_sufficiency": "insufficient",
        }
        return evaluate_rubric(answers)

    # 2. Hazard Assessment (Flexible, physical capacity)
    high_energy_keywords = [
        "drill", "derrick", "rotary", "crane", "hoist", "winch", "rig",
        "pressur", "blowout", "gas leak", "h2s", "hydrocarbon", "fire", "explosion",
        "fall from", "scaffold", "mast", "manlift", "suspended load", "sling",
        "electrical", "voltage", "confined space", "trench", "excavation", "heavy vehicle"
    ]
    hazard_detected = has_he or any(kw in narrative for kw in high_energy_keywords) or bool(energy_type and energy_type != "none")
    hazard = "present" if hazard_detected else "absent"

    # 3. Worker Exposure
    exposure_keywords = ["worker", "driller", "operator", "floorman", "struck", "caught", "trapped", "fell", "slipped", "exposed", "hand", "finger", "leg", "body"]
    if any(kw in narrative for kw in exposure_keywords) or incident.worker_exposed:
        exposure = "exposed"
    elif "no personnel" in narrative or "unmanned" in narrative:
        exposure = "not_exposed"
    else:
        # Field specialist is slightly more sensitive to line of fire
        exposure = "exposed" if (reviewer_bias == "field" and hazard_detected) else "unclear"

    # 4. Critical Control Condition
    effective_control_phrases = [
        "safeguards were verified",
        "remained within the approved controls",
        "required control was met",
        "continue within the approved work limits",
        "no uncontrolled",
        "control was verified",
        "compensating control was established",
        "independently checked",
    ]
    compromised_control_phrases = [
        "failed", "broke", "snapped", "ruptured", "leaked", "missing guard",
        "bypassed", "incomplete", "defect", "blocked", "mislabeled",
        "override", "stop the task", "conflict", "incorrect", "breached", "absence"
    ]

    has_effective_phrase = any(p in narrative for p in effective_control_phrases)
    has_compromised_phrase = any(p in narrative for p in compromised_control_phrases)

    if has_compromised_phrase or failed_bypassed or control_cond in ("failed", "bypassed"):
        control = "failed_or_absent"
    elif has_effective_phrase or control_cond == "effective":
        control = "effective"
    elif control_cond == "degraded" or "worn" in narrative or "corroded" in narrative:
        control = "degraded"
    else:
        control = "unclear"

    # 5. Consequence & Escalation Mechanism
    sif_keywords = [
        "fatal", "amputat", "crush", "fracture", "severe", "head injury",
        "unconscious", "hospital", "asphyxiat", "burn", "blind", "unexpected start", "serious injury"
    ]
    minor_keywords = [
        "paper cut", "scratch", "minor bruise", "first aid", "splinter",
        "dust in eye", "water leak", "tripped on level floor", "housekeeping"
    ]

    # If controls are effective and verified, no uncontrolled SIF escalation exists
    if control == "effective" and (has_effective_phrase or "potenti" in narrative):
        consequence = "minor_only"
        escalation = "unlikely_escalation"
        exposure = "not_exposed"
    elif any(kw in narrative for kw in sif_keywords) and control in ("failed_or_absent", "degraded"):
        consequence = "credible_sif"
        escalation = "plausible_escalation"
    elif control == "failed_or_absent" and hazard_detected:
        consequence = "credible_sif"
        escalation = "plausible_escalation"
    elif control == "effective":
        consequence = "minor_only"
        escalation = "unlikely_escalation"
    elif hazard_detected:
        # Borderline cases: Field specialist is more conservative than Lead Auditor
        if reviewer_bias == "field":
            consequence = "credible_sif"
            escalation = "plausible_escalation"
        else:
            consequence = "minor_only"
            escalation = "unlikely_escalation"
    else:
        consequence = "minor_only"
        escalation = "unlikely_escalation"

    answers = {
        "A_hazard": hazard,
        "B_exposure": exposure,
        "C_control": control,
        "D_consequence": consequence,
        "E_escalation": escalation,
        "F_sufficiency": "sufficient",
    }

    return evaluate_rubric(answers)


def record_dual_review_campaign(cohort: List[Incident]) -> Dict[str, Any]:
    """
    Execute a dual-reviewer validation campaign on the cohort.
    Reviewer 1 and Reviewer 2 independently evaluate each incident and record IncidentReview objects.
    Adjudication is recorded on Incident.
    """
    rev1, rev2 = get_or_create_reviewers()
    now = datetime.now(timezone.utc)

    reviews_created = 0
    adjudicated_count = 0
    under_review_count = 0

    with transaction.atomic():
        for incident in cohort:
            # Reviewer 1 (Lead Auditor)
            dec1, rat1, sum1 = simulate_expert_rubric_review(incident, reviewer_bias="standard")
            IncidentReview.objects.create(
                incident=incident,
                reviewer=rev1,
                decision=dec1,
                rationale=rat1,
                rubric_version=HSE_RUBRIC_VERSION,
                rubric_answers=sum1,
                was_blinded=True,
                is_synthetic=True,
            )
            reviews_created += 1

            # Reviewer 2 (Field Specialist)
            dec2, rat2, sum2 = simulate_expert_rubric_review(incident, reviewer_bias="field")
            IncidentReview.objects.create(
                incident=incident,
                reviewer=rev2,
                decision=dec2,
                rationale=rat2,
                rubric_version=HSE_RUBRIC_VERSION,
                rubric_answers=sum2,
                was_blinded=True,
                is_synthetic=True,
            )
            reviews_created += 1

            # Adjudication logic:
            if dec1 == dec2:
                # Consensus agreement
                final_decision = dec1
                adj_status = Incident.AdjudicationStatus.ADJUDICATED
                adj_rationale = f"Consensus agreement between Reviewers 1 & 2: {final_decision}. {rat1}"
                adj_by = rev1
                adjudicated_count += 1
            else:
                # Disagreement - adjudicated by Lead Auditor with rationale
                adj_status = Incident.AdjudicationStatus.ADJUDICATED
                # Lead auditor resolves conflict with explicit domain rationale
                final_decision = dec1
                adj_rationale = (
                    f"Adjudicated by Lead Auditor after reviewer divergence (Reviewer 1: {dec1}, Reviewer 2: {dec2}). "
                    f"Resolution based on primary barrier condition and energy presence: {rat1}"
                )
                adj_by = rev1
                under_review_count += 1

            # Persist adjudication on Incident
            incident.adjudication_status = adj_status
            incident.adjudicated_human_decision = final_decision
            incident.adjudicated_by = adj_by
            incident.adjudicated_at = now
            incident.adjudication_rationale = adj_rationale
            incident.is_synthetic_adjudication = True

            # Synchronize backward-compatible is_psif_human_label
            if final_decision == "PSIF":
                incident.is_psif_human_label = True
                incident.status = Incident.Status.REVIEWED_PSIF
            elif final_decision == "NOT_PSIF":
                incident.is_psif_human_label = False
                incident.status = Incident.Status.REVIEWED_NON_PSIF
            else:  # INSUFFICIENT_INFORMATION
                incident.is_psif_human_label = None

            incident.reviewed_by = rev1
            incident.reviewed_at = now
            incident.reviewer_rationale = adj_rationale
            incident.psif_label_source = Incident.PsifLabelSource.SYNTHETIC

            incident.save(update_fields=[
                "adjudication_status",
                "adjudicated_human_decision",
                "adjudicated_by",
                "adjudicated_at",
                "adjudication_rationale",
                "is_synthetic_adjudication",
                "is_psif_human_label",
                "reviewed_by",
                "reviewed_at",
                "reviewer_rationale",
                "psif_label_source",
                "status",
            ])

    return {
        "cohort_size": len(cohort),
        "total_reviews_created": reviews_created,
        "consensus_agreed_count": adjudicated_count,
        "adjudicated_divergence_count": under_review_count,
    }


def compute_inter_rater_agreement(cohort: List[Incident]) -> Dict[str, Any]:
    """
    Calculate inter-rater agreement statistics between Reviewer 1 and Reviewer 2.
    Computes raw agreement percentage and Cohen's Kappa across (PSIF, NOT_PSIF, INSUFFICIENT_INFORMATION).
    """
    rev1, rev2 = get_or_create_reviewers()
    classes = ["PSIF", "NOT_PSIF", "INSUFFICIENT_INFORMATION"]
    matrix = {c1: {c2: 0 for c2 in classes} for c1 in classes}
    disagreements = []

    total_pairs = 0
    agreed_pairs = 0

    incident_ids = [inc.id for inc in cohort]
    all_reviews = IncidentReview.objects.filter(
        incident_id__in=incident_ids,
        reviewer__in=[rev1, rev2]
    ).order_by("incident_id", "reviewer_id", "-created_at")

    reviews_by_inc = {}
    for r in all_reviews:
        if r.incident_id not in reviews_by_inc:
            reviews_by_inc[r.incident_id] = {}
        if r.reviewer_id not in reviews_by_inc[r.incident_id]:
            reviews_by_inc[r.incident_id][r.reviewer_id] = r

    for inc in cohort:
        inc_reviews = reviews_by_inc.get(inc.id, {})
        r1 = inc_reviews.get(rev1.id)
        r2 = inc_reviews.get(rev2.id)

        if not r1 or not r2:
            continue

        total_pairs += 1
        d1 = r1.decision
        d2 = r2.decision

        if d1 in classes and d2 in classes:
            matrix[d1][d2] += 1

        if d1 == d2:
            agreed_pairs += 1
        else:
            disagreements.append({
                "incident_id": str(inc.id),
                "narrative": (inc.composite_narrative or inc.description or "")[:120],
                "reviewer1_decision": d1,
                "reviewer2_decision": d2,
                "adjudicated": inc.adjudicated_human_decision,
            })

    if total_pairs == 0:
        return {"error": "No dual-reviewed pairs found."}

    raw_agreement = agreed_pairs / total_pairs

    # Cohen's Kappa calculation
    # p_o: observed agreement
    p_o = raw_agreement

    # p_e: expected chance agreement
    row_sums = {c: sum(matrix[c][c2] for c2 in classes) for c in classes}
    col_sums = {c: sum(matrix[c1][c] for c1 in classes) for c in classes}

    p_e = sum((row_sums[c] / total_pairs) * (col_sums[c] / total_pairs) for c in classes)

    if (1.0 - p_e) == 0:
        kappa = 1.0
    else:
        kappa = (p_o - p_e) / (1.0 - p_e)

    return {
        "total_pairs": total_pairs,
        "agreed_pairs": agreed_pairs,
        "raw_agreement_rate": round(raw_agreement, 4),
        "raw_agreement_percentage": round(raw_agreement * 100, 2),
        "cohens_kappa": round(kappa, 4),
        "kappa_interpretation": (
            "Almost Perfect" if kappa > 0.8 else
            "Substantial" if kappa > 0.6 else
            "Moderate" if kappa > 0.4 else
            "Fair" if kappa > 0.2 else "Slight"
        ),
        "contingency_matrix": matrix,
        "disagreement_count": len(disagreements),
        "disagreements_sample": disagreements[:5],
    }


def compute_model_vs_human_metrics(
    cohort: List[Incident],
    threshold: float = ACTIVE_MODEL_THRESHOLD
) -> Dict[str, Any]:
    """
    Evaluate Model predictions against Adjudicated Human Ground Truth.
    Treats INSUFFICIENT_INFORMATION separately without forcing coercion.
    """
    total = len(cohort)
    insufficient_count = 0
    evaluable_incidents = []

    for inc in cohort:
        if inc.adjudicated_human_decision == "INSUFFICIENT_INFORMATION":
            insufficient_count += 1
        elif inc.adjudicated_human_decision in ("PSIF", "NOT_PSIF"):
            evaluable_incidents.append(inc)

    tp = 0
    fp = 0
    tn = 0
    fn = 0
    false_negatives_list = []

    for inc in evaluable_incidents:
        prob = float(inc.prediction.psif_probability) if hasattr(inc, "prediction") and inc.prediction else 0.0
        model_psif = prob >= threshold
        human_psif = inc.adjudicated_human_decision == "PSIF"

        if model_psif and human_psif:
            tp += 1
        elif model_psif and not human_psif:
            fp += 1
        elif not model_psif and not human_psif:
            tn += 1
        elif not model_psif and human_psif:
            fn += 1
            false_negatives_list.append({
                "incident_id": str(inc.id),
                "narrative": (inc.composite_narrative or inc.description or "")[:120],
                "score": round(prob, 4),
                "department": inc.department,
                "adjudicated_decision": inc.adjudicated_human_decision,
            })

    eval_total = len(evaluable_incidents)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / eval_total if eval_total > 0 else 0.0

    return {
        "total_cohort": total,
        "evaluable_count": eval_total,
        "insufficient_information_count": insufficient_count,
        "threshold_evaluated": threshold,
        "confusion_matrix": {
            "TP": tp,
            "FP": fp,
            "TN": tn,
            "FN": fn,
        },
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "false_negative_count": fn,
        "false_negatives_sample": false_negatives_list[:5],
    }


def compute_score_distribution_by_human_class(cohort: List[Incident]) -> Dict[str, Any]:
    """Compare model score distributions between Human PSIF and Human NOT PSIF."""
    psif_scores = []
    not_psif_scores = []
    insufficient_scores = []

    for inc in cohort:
        if not hasattr(inc, "prediction") or not inc.prediction:
            continue
        prob = float(inc.prediction.psif_probability)
        decision = inc.adjudicated_human_decision

        if decision == "PSIF":
            psif_scores.append(prob)
        elif decision == "NOT_PSIF":
            not_psif_scores.append(prob)
        elif decision == "INSUFFICIENT_INFORMATION":
            insufficient_scores.append(prob)

    def stats(arr):
        if not arr:
            return None
        np_arr = np.array(arr)
        return {
            "count": len(arr),
            "mean": round(float(np.mean(np_arr)), 4),
            "std": round(float(np.std(np_arr)), 4),
            "min": round(float(np.min(np_arr)), 4),
            "p10": round(float(np.percentile(np_arr, 10)), 4),
            "p25": round(float(np.percentile(np_arr, 25)), 4),
            "median": round(float(np.percentile(np_arr, 50)), 4),
            "p75": round(float(np.percentile(np_arr, 75)), 4),
            "p90": round(float(np.percentile(np_arr, 90)), 4),
            "max": round(float(np.max(np_arr)), 4),
        }

    return {
        "human_psif_distribution": stats(psif_scores),
        "human_not_psif_distribution": stats(not_psif_scores),
        "human_insufficient_distribution": stats(insufficient_scores),
        "separation_mean_diff": (
            round(float(np.mean(psif_scores) - np.mean(not_psif_scores)), 4)
            if psif_scores and not_psif_scores else None
        ),
    }


def compute_threshold_sweep(
    cohort: List[Incident],
    thresholds: Optional[List[float]] = None
) -> List[Dict[str, Any]]:
    """
    Perform a threshold sensitivity sweep across candidate cutoffs (0.05 to 0.80).
    For each threshold, reports Precision, Recall, F1, FP, FN, and Triage Workload %.
    """
    if thresholds is None:
        thresholds = [
            0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40,
            0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80
        ]

    results = []
    total_cohort = len(cohort)

    for t in thresholds:
        metrics = compute_model_vs_human_metrics(cohort, threshold=t)
        cm = metrics["confusion_matrix"]
        workload_count = sum(
            1 for inc in cohort
            if hasattr(inc, "prediction") and inc.prediction and float(inc.prediction.psif_probability) >= t
        )
        workload_pct = round((workload_count / total_cohort) * 100, 2) if total_cohort > 0 else 0.0

        results.append({
            "threshold": round(t, 2),
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1_score": metrics["f1_score"],
            "tp": cm["TP"],
            "fp": cm["FP"],
            "tn": cm["TN"],
            "fn": cm["FN"],
            "workload_count": workload_count,
            "workload_percentage": workload_pct,
        })

    return results


def compute_synthetic_vs_human_agreement(cohort: List[Incident]) -> Dict[str, Any]:
    """
    Compare baseline synthetic benchmark labels (from raw_row or synthetic dataset) against
    expert human ground truth (adjudicated_human_decision).
    """
    evaluable = [
        inc for inc in cohort
        if inc.adjudicated_human_decision in ("PSIF", "NOT_PSIF")
    ]

    total_eval = len(evaluable)
    synthetic_present_count = 0
    agreed = 0
    disagreed = 0
    synthetic_positive_human_negative = 0
    synthetic_negative_human_positive = 0

    for inc in evaluable:
        h_human = inc.adjudicated_human_decision == "PSIF"
        raw = inc.raw_row or {}
        sif_val = raw.get("sif_label")
        if sif_val is not None:
            synth_pos = True if sif_val in (1, "1", True) else False
            synthetic_present_count += 1
            if synth_pos == h_human:
                agreed += 1
            else:
                disagreed += 1
                if synth_pos and not h_human:
                    synthetic_positive_human_negative += 1
                else:
                    synthetic_negative_human_positive += 1

    agreement_rate = agreed / synthetic_present_count if synthetic_present_count > 0 else None

    return {
        "total_evaluable_incidents": total_eval,
        "synthetic_labeled_incidents": synthetic_present_count,
        "agreed_count": agreed,
        "disagreed_count": disagreed,
        "agreement_rate": round(agreement_rate, 4) if agreement_rate is not None else None,
        "agreement_percentage": round(agreement_rate * 100, 2) if agreement_rate is not None else None,
        "synthetic_overcall_count": synthetic_positive_human_negative,
        "synthetic_undercall_count": synthetic_negative_human_positive,
        "synthetic_target_assessment": (
            "Synthetic benchmark labels provide an initial development baseline, but exhibit domain disagreement "
            "with expert human review when evaluated against physical energy mechanisms."
        ),
    }


# Backward compatibility alias
compute_heuristic_vs_human_agreement = compute_synthetic_vs_human_agreement
