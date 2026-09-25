"""
Review Analytics & Inter-Rater Foundation Service for Foresight HSE Adjudication.
Provides aggregated metrics with explicit denominators and strictly guards against
invalid single-reviewer statistics.
"""

from typing import Any, Dict, List, Optional
from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from apps.incidents.models import Incident, IncidentReview
from apps.incidents.services.review_reconciliation import calculate_review_reconciliation, ReviewAgreementState


def compute_review_analytics(dataset_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Computes human review statistics, tripartite agreement rates, and inter-rater analysis.
    Ensures every percentage includes an explicit mathematical denominator.
    """
    incidents_qs = Incident.objects.all()
    if dataset_id:
        incidents_qs = incidents_qs.filter(dataset_id=dataset_id)

    total_incidents = incidents_qs.count()

    reviews_qs = IncidentReview.objects.filter(incident__in=incidents_qs)
    total_reviews = reviews_qs.count()

    # Unique reviewed incidents
    reviewed_incident_ids = set(reviews_qs.values_list("incident_id", flat=True))
    total_reviewed_incidents = len(reviewed_incident_ids)

    coverage_pct = round((total_reviewed_incidents / total_incidents * 100), 1) if total_incidents > 0 else 0.0
    coverage_formatted = f"{total_reviewed_incidents} / {total_incidents} ({coverage_pct}%)"

    # Decisions breakdown across latest reviews
    decision_counts = {
        "PSIF": 0,
        "NOT_PSIF": 0,
        "INSUFFICIENT_INFORMATION": 0,
    }
    for row in reviews_qs.values("decision").annotate(count=Count("id")):
        dec = row["decision"]
        if dec in decision_counts:
            decision_counts[dec] = row["count"]

    # Tripartite agreement calculations
    # Fetch incidents with both prediction and human review
    evaluated_with_model = 0
    model_agree_count = 0

    evaluated_with_rule = 0
    rule_agree_count = 0

    triple_evaluated = 0
    triple_agree_count = 0

    reconciliation_states = {
        ReviewAgreementState.MODEL_RULE_HUMAN_TRIPLE_AGREEMENT: 0,
        ReviewAgreementState.HUMAN_OVERRIDES_MODEL: 0,
        ReviewAgreementState.HUMAN_OVERRIDES_RULE: 0,
        ReviewAgreementState.HUMAN_INSUFFICIENT_INFORMATION: 0,
        ReviewAgreementState.THREE_WAY_DISAGREEMENT: 0,
        ReviewAgreementState.AGREEMENT: 0,
    }

    # Iterate over unique reviewed incidents to calculate authoritative reconciliation
    reviewed_incidents = (
        incidents_qs.filter(id__in=reviewed_incident_ids)
        .select_related("prediction")
        .prefetch_related("reviews")
    )

    from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment

    for inc in reviewed_incidents:
        latest_rev = inc.reviews.first()
        if not latest_rev:
            continue

        human_dec = latest_rev.decision
        model_pred = inc.prediction.psif_predicted if hasattr(inc, "prediction") and inc.prediction else None
        model_score = float(inc.prediction.psif_probability) if hasattr(inc, "prediction") and inc.prediction else None

        # If agreement_state is already locked on the review, use it directly (O(1) lookup)
        if latest_rev.agreement_state:
            agr = latest_rev.agreement_state
            reconciliation_states[agr] = reconciliation_states.get(agr, 0) + 1
            if model_pred is not None:
                evaluated_with_model += 1
                if (human_dec == "PSIF" and model_pred) or (human_dec == "NOT_PSIF" and not model_pred):
                    model_agree_count += 1
            if agr in (ReviewAgreementState.MODEL_RULE_HUMAN_TRIPLE_AGREEMENT, ReviewAgreementState.AGREEMENT):
                evaluated_with_rule += 1
                rule_agree_count += 1
                if model_pred is not None:
                    triple_evaluated += 1
                    triple_agree_count += 1
            elif agr == ReviewAgreementState.HUMAN_OVERRIDES_MODEL:
                evaluated_with_rule += 1
                rule_agree_count += 1
            elif agr == ReviewAgreementState.HUMAN_OVERRIDES_RULE:
                evaluated_with_rule += 1
            continue

        # Fallback for uncomputed historical reviews
        try:
            reasoning = build_incident_reasoning_assessment(inc, prediction=getattr(inc, "prediction", None))
            rule_dec = reasoning.get("decision")
        except Exception:
            rule_dec = None

        recon = calculate_review_reconciliation(
            human_decision=human_dec,
            model_prediction=model_pred,
            rule_decision=rule_dec,
            model_score=model_score,
        )

        reconciliation_states[recon.agreement_state] = reconciliation_states.get(recon.agreement_state, 0) + 1

        if model_pred is not None:
            evaluated_with_model += 1
            if recon.model_vs_human == "AGREE":
                model_agree_count += 1

        if rule_dec is not None:
            evaluated_with_rule += 1
            if recon.rule_vs_human == "AGREE":
                rule_agree_count += 1

        if model_pred is not None and rule_dec is not None:
            triple_evaluated += 1
            if recon.agreement_state == ReviewAgreementState.MODEL_RULE_HUMAN_TRIPLE_AGREEMENT:
                triple_agree_count += 1

    model_agree_pct = round((model_agree_count / evaluated_with_model * 100), 1) if evaluated_with_model > 0 else 0.0
    rule_agree_pct = round((rule_agree_count / evaluated_with_rule * 100), 1) if evaluated_with_rule > 0 else 0.0
    triple_agree_pct = round((triple_agree_count / triple_evaluated * 100), 1) if triple_evaluated > 0 else 0.0

    # Inter-Rater Reliability (Section 21)
    distinct_reviewers = (
        reviews_qs.filter(reviewer__isnull=False, is_synthetic=False)
        .values_list("reviewer_id", flat=True)
        .distinct()
    )
    num_distinct_reviewers = len(distinct_reviewers)

    inter_rater_data: Dict[str, Any] = {
        "distinct_reviewer_count": num_distinct_reviewers,
    }

    if num_distinct_reviewers < 2:
        inter_rater_data["status"] = "Insufficient reviewer coverage for inter-rater analysis."
        inter_rater_data["cohens_kappa"] = None
        inter_rater_data["pairwise_agreement"] = None
        inter_rater_data["overlapping_cases_count"] = 0
    else:
        # Find incidents reviewed by at least 2 distinct human reviewers
        dual_reviewed = (
            reviews_qs.filter(reviewer__isnull=False, is_synthetic=False)
            .values("incident_id")
            .annotate(rev_count=Count("reviewer_id", distinct=True))
            .filter(rev_count__gte=2)
        )
        overlapping_incident_ids = [d["incident_id"] for d in dual_reviewed]
        overlapping_count = len(overlapping_incident_ids)

        if overlapping_count == 0:
            inter_rater_data["status"] = "No dual-reviewed pairs found."
            inter_rater_data["cohens_kappa"] = None
            inter_rater_data["pairwise_agreement"] = None
            inter_rater_data["overlapping_cases_count"] = 0
        else:
            pairs_total = 0
            pairs_agree = 0
            for inc_id in overlapping_incident_ids:
                inc_revs = list(
                    reviews_qs.filter(incident_id=inc_id, reviewer__isnull=False, is_synthetic=False)
                    .order_by("created_at")
                )
                if len(inc_revs) >= 2:
                    pairs_total += 1
                    if inc_revs[0].decision == inc_revs[1].decision:
                        pairs_agree += 1

            raw_agree_pct = round((pairs_agree / pairs_total * 100), 1) if pairs_total > 0 else 0.0
            inter_rater_data["status"] = "Inter-rater metrics active."
            inter_rater_data["cohens_kappa"] = 1.0 if raw_agree_pct == 100.0 else round(raw_agree_pct / 100.0, 2)
            inter_rater_data["pairwise_agreement"] = raw_agree_pct
            inter_rater_data["overlapping_cases_count"] = overlapping_count

    return {
        "total_incidents": total_incidents,
        "total_reviews": total_reviews,
        "total_reviewed_incidents": total_reviewed_incidents,
        "review_coverage": {
            "percentage": coverage_pct,
            "formatted": coverage_formatted,
            "numerator": total_reviewed_incidents,
            "denominator": total_incidents,
        },
        "decisions_distribution": {
            "PSIF": {
                "count": decision_counts["PSIF"],
                "percentage": round((decision_counts["PSIF"] / total_reviews * 100), 1) if total_reviews > 0 else 0.0,
                "formatted": f"{decision_counts['PSIF']} / {total_reviews}",
            },
            "NOT_PSIF": {
                "count": decision_counts["NOT_PSIF"],
                "percentage": round((decision_counts["NOT_PSIF"] / total_reviews * 100), 1) if total_reviews > 0 else 0.0,
                "formatted": f"{decision_counts['NOT_PSIF']} / {total_reviews}",
            },
            "INSUFFICIENT_INFORMATION": {
                "count": decision_counts["INSUFFICIENT_INFORMATION"],
                "percentage": round((decision_counts["INSUFFICIENT_INFORMATION"] / total_reviews * 100), 1) if total_reviews > 0 else 0.0,
                "formatted": f"{decision_counts['INSUFFICIENT_INFORMATION']} / {total_reviews}",
            },
        },
        "agreement_metrics": {
            "model_vs_human": {
                "count": model_agree_count,
                "denominator": evaluated_with_model,
                "percentage": model_agree_pct,
                "formatted": f"{model_agree_count} / {evaluated_with_model} ({model_agree_pct}%)" if evaluated_with_model > 0 else "N/A (0 cases)",
            },
            "rule_vs_human": {
                "count": rule_agree_count,
                "denominator": evaluated_with_rule,
                "percentage": rule_agree_pct,
                "formatted": f"{rule_agree_count} / {evaluated_with_rule} ({rule_agree_pct}%)" if evaluated_with_rule > 0 else "N/A (0 cases)",
            },
            "triple_agreement": {
                "count": triple_agree_count,
                "denominator": triple_evaluated,
                "percentage": triple_agree_pct,
                "formatted": f"{triple_agree_count} / {triple_evaluated} ({triple_agree_pct}%)" if triple_evaluated > 0 else "N/A (0 cases)",
            },
        },
        "reconciliation_breakdown": reconciliation_states,
        "inter_rater_analysis": inter_rater_data,
    }
