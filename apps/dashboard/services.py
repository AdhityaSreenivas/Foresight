"""
Analytics Services for Dashboard and Reports.
OIL India Problem Statement 26165.

Provides high-performance single-pass database aggregations and Redis caching
for dashboard KPI summary metrics and trend series.
"""

import logging
from typing import Any, Dict, List, Optional
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

from apps.incidents.models import Incident, IncidentReview, IOGPRuleTag
from apps.predictions.models import PredictionResult

logger = logging.getLogger(__name__)

CACHE_KEY_ANALYTICS_SUMMARY = "dashboard:analytics_summary:v3"
CACHE_KEY_ANALYTICS_TREND = "dashboard:analytics_trend:v2"
CACHE_KEY_BARRIER_INTELLIGENCE = "dashboard:barrier_intelligence:v1"
CACHE_TTL_ANALYTICS = 3600  # 1 hour

CANONICAL_METRIC_DEFINITION = {
    "metric_name": "psif_prediction_rate",
    "numerator": "prediction-eligible incidents with psif_predicted=True and is_sparse_input=False",
    "denominator": "prediction-eligible incidents (has PredictionResult and is_sparse_input=False)",
    "sparse_input": "excluded from rate calculation (insufficient narrative yields uninformative prediction)",
    "time_window": "all_time",
    "reconciliation_note": (
        "Reconciles legacy dashboard (~18.8% reported when 174 predicted PSIF was divided by 926 total incidents) "
        "with forensic audit (~92.4% reported when evaluated across prediction results only). "
        "Canonical rate requires compatible populations: prediction-eligible non-sparse predictions only."
    ),
}

CANONICAL_METRIC_DEFINITIONS = {
    "psif_percentage": {
        "formula": "psif_count / prediction_eligible_count * 100",
        "numerator": "prediction-eligible incidents with psif_predicted=True",
        "denominator": "prediction-eligible incidents (has non-sparse PredictionResult)",
        "description": "Percentage of prediction-eligible reports classified as PSIF candidates by the model."
    },
    "prediction_coverage_rate": {
        "formula": "total_predictions / total_incidents",
        "numerator": "incidents with a PredictionResult",
        "denominator": "total incidents ingested",
        "description": "Fraction of all incident reports that have undergone model evaluation."
    },
    "insufficient_evidence_rate": {
        "formula": "insufficient_evidence_count / total_predictions",
        "numerator": "predictions flagged with is_sparse_input=True (< 10 words)",
        "denominator": "total incidents with PredictionResult",
        "description": "Proportion of reports where narrative was too sparse for reliable analysis."
    },
    "human_reviewed_rate": {
        "formula": "human_reviewed_count / total_incidents",
        "numerator": "incidents with an explicit human HSE review label (True or False)",
        "denominator": "total incidents ingested",
        "description": "Proportion of reports that have been validated by human HSE experts."
    },
    "human_model_agreement_rate": {
        "formula": "count(model_prediction == human_label) / count(has both non-sparse prediction and human label)",
        "numerator": "incidents where psif_predicted matches is_psif_human_label",
        "denominator": "incidents with BOTH an eligible non-sparse prediction and a human review label",
        "description": "Concordance between model candidate classification and human expert ground truth."
    }
}


def get_analytics_summary(use_cache: bool = True, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Computes high-performance canonical analytics summary with single-pass database aggregations.
    Results are cached in Redis under CACHE_KEY_ANALYTICS_SUMMARY.
    """
    if use_cache and not force_refresh:
        cached = cache.get(CACHE_KEY_ANALYTICS_SUMMARY)
        if cached is not None:
            return cached

    # 1. Single-pass aggregation on PredictionResult (scoped to global workspace)
    pred_stats = PredictionResult.objects.filter(incident__workspace_id__isnull=True).aggregate(
        total=Count("id"),
        sparse=Count("id", filter=Q(is_sparse_input=True)),
        eligible=Count("id", filter=Q(is_sparse_input=False)),
        psif=Count("id", filter=Q(is_sparse_input=False, psif_predicted=True)),
        not_psif=Count("id", filter=Q(is_sparse_input=False, psif_predicted=False)),
        high_risk=Count("id", filter=Q(is_sparse_input=False, risk_level__in=["high", "critical"])),
    )
    total_predictions = pred_stats["total"] or 0
    sparse_count = pred_stats["sparse"] or 0
    prediction_eligible_count = pred_stats["eligible"] or 0
    psif_count = pred_stats["psif"] or 0
    not_psif_count = pred_stats["not_psif"] or 0
    high_risk = pred_stats["high_risk"] or 0

    # 2. Single-pass aggregation on Incident (scoped to global workspace)
    inc_stats = Incident.objects.filter(workspace_id__isnull=True).aggregate(
        total=Count("id"),
        adjudicated=Count("id", filter=Q(adjudication_status=Incident.AdjudicationStatus.ADJUDICATED)),
        human_reviewed=Count(
            "id",
            filter=Q(adjudication_status=Incident.AdjudicationStatus.ADJUDICATED) |
            Q(is_psif_human_label__isnull=False)
        ),
        human_psif=Count(
            "id",
            filter=Q(adjudicated_human_decision=Incident.HumanDecision.PSIF) |
            Q(adjudicated_human_decision__isnull=True, is_psif_human_label=True)
        ),
        human_not_psif=Count(
            "id",
            filter=Q(adjudicated_human_decision=Incident.HumanDecision.NOT_PSIF) |
            Q(adjudicated_human_decision__isnull=True, is_psif_human_label=False)
        ),
        human_insufficient=Count(
            "id",
            filter=Q(adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION)
        ),
    )
    total_incidents = inc_stats["total"] or 0
    adjudicated_count = inc_stats["adjudicated"] or 0
    human_reviewed_count = inc_stats["human_reviewed"] or 0
    human_psif_count = inc_stats["human_psif"] or 0
    human_not_psif_count = inc_stats["human_not_psif"] or 0
    human_insufficient_count = inc_stats["human_insufficient"] or 0

    # Rates with strictly defined canonical denominators
    psif_prediction_rate = (
        round(psif_count / prediction_eligible_count, 4)
        if prediction_eligible_count > 0
        else 0.0
    )
    psif_percentage = round(psif_prediction_rate * 100, 2)

    prediction_coverage_rate = (
        round(total_predictions / total_incidents, 4)
        if total_incidents > 0
        else 0.0
    )

    human_reviewed_rate = (
        round(human_reviewed_count / total_incidents, 4)
        if total_incidents > 0
        else 0.0
    )

    total_human_reviews = IncidentReview.objects.filter(incident__workspace_id__isnull=True).count()

    # 3. Single-pass aggregation on Validation Performance Cohort
    val_eval_qs = Incident.objects.filter(
        workspace_id__isnull=True,
        prediction__isnull=False,
        prediction__is_sparse_input=False
    ).filter(
        Q(adjudicated_human_decision__in=[Incident.HumanDecision.PSIF, Incident.HumanDecision.NOT_PSIF]) |
        Q(adjudicated_human_decision__isnull=True, is_psif_human_label__isnull=False)
    )

    human_psif_filter = (
        Q(adjudicated_human_decision=Incident.HumanDecision.PSIF) |
        Q(adjudicated_human_decision__isnull=True, is_psif_human_label=True)
    )
    human_not_psif_filter = (
        Q(adjudicated_human_decision=Incident.HumanDecision.NOT_PSIF) |
        Q(adjudicated_human_decision__isnull=True, is_psif_human_label=False)
    )

    val_stats = val_eval_qs.aggregate(
        tp=Count("id", filter=Q(prediction__psif_predicted=True) & human_psif_filter),
        fp=Count("id", filter=Q(prediction__psif_predicted=True) & human_not_psif_filter),
        tn=Count("id", filter=Q(prediction__psif_predicted=False) & human_not_psif_filter),
        fn=Count("id", filter=Q(prediction__psif_predicted=False) & human_psif_filter),
    )
    tp = val_stats["tp"] or 0
    fp = val_stats["fp"] or 0
    tn = val_stats["tn"] or 0
    fn = val_stats["fn"] or 0
    sample_size = tp + fp + tn + fn

    if sample_size > 0:
        precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
        recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
        f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0
        human_model_agreement_rate = round((tp + tn) / sample_size, 4)
        validation_metrics = {
            "sample_size": sample_size,
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "agreement_rate": human_model_agreement_rate,
            "active_threshold": 0.10,
        }
    else:
        human_model_agreement_rate = None
        validation_metrics = None

    # 4. Inter-rater agreement (bulk-optimized)
    inter_rater_stats = None
    if total_human_reviews >= 2:
        try:
            from apps.incidents.services.evaluation import compute_inter_rater_agreement
            multi_reviewed = list(Incident.objects.filter(
                reviews__reviewer__username="hse_lead_auditor"
            ).filter(
                reviews__reviewer__username="hse_field_specialist"
            ).distinct())
            if multi_reviewed:
                res = compute_inter_rater_agreement(multi_reviewed)
                inter_rater_stats = {
                    "total_pairs": res["total_pairs"],
                    "agreement_percentage": res["raw_agreement_percentage"],
                    "cohen_kappa": res["cohens_kappa"],
                    "interpretation": res["kappa_interpretation"],
                }
        except Exception as e:
            logger.warning("Inter-rater computation omitted: %s", e)
            inter_rater_stats = None

    # 5. Breakdown queries (scoped to global workspace)
    depts = list(Incident.objects.filter(workspace_id__isnull=True).values("department").annotate(count=Count("id")).order_by("-count")[:5])

    binary_distribution = {
        "PSIF": psif_count,
        "NOT_PSIF": not_psif_count,
    }

    risk_counts = (
        PredictionResult.objects.filter(incident__workspace_id__isnull=True, is_sparse_input=False)
        .values("risk_level")
        .annotate(count=Count("id"))
    )
    risk_distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for r in risk_counts:
        lvl = r["risk_level"]
        if lvl in risk_distribution:
            risk_distribution[lvl] = r["count"]

    iogp_counts = list(IOGPRuleTag.objects.filter(incident__workspace_id__isnull=True).values("rule").annotate(count=Count("id")).order_by("-count"))
    iogp_distribution = [{"rule": r["rule"], "count": r["count"]} for r in iogp_counts]

    data = {
        # Core counts (numeric integers)
        "total_incidents": total_incidents,
        "prediction_eligible_incidents": prediction_eligible_count,
        "prediction_eligible_count": prediction_eligible_count,
        "psif_incidents": psif_count,
        "psif_count": psif_count,
        "not_psif_count": not_psif_count,
        "psif_prediction_rate": psif_prediction_rate,
        "psif_percentage": psif_percentage,
        "sparse_predictions_count": sparse_count,
        "insufficient_evidence_count": sparse_count,
        "total_predictions": total_predictions,
        "prediction_coverage_rate": prediction_coverage_rate,
        "human_reviewed_count": human_reviewed_count,
        "human_reviewed_rate": human_reviewed_rate,
        "adjudicated_count": adjudicated_count,
        "total_human_reviews": total_human_reviews,
        "human_psif_count": human_psif_count,
        "human_not_psif_count": human_not_psif_count,
        "human_insufficient_count": human_insufficient_count,
        "human_confirmed_psif_count": human_psif_count,
        "human_confirmed_not_psif_count": human_not_psif_count,
        "human_model_agreement_rate": human_model_agreement_rate,
        "validation_metrics": validation_metrics,
        "inter_rater_stats": inter_rater_stats,
        "binary_distribution": binary_distribution,
        "high_risk_predictions": high_risk,
        "department_breakdown": depts,
        "risk_distribution": risk_distribution,
        "iogp_distribution": iogp_distribution,
        "metric_definition": CANONICAL_METRIC_DEFINITION,
        "metric_definitions": CANONICAL_METRIC_DEFINITIONS,
        "canonical_metric_definitions": CANONICAL_METRIC_DEFINITIONS,

        # Formatted strings for direct server-side HTML rendering
        "formatted_total_incidents": f"{total_incidents:,}",
        "formatted_prediction_eligible_count": f"{prediction_eligible_count:,}",
        "formatted_psif_count": f"{psif_count:,}",
        "formatted_not_psif_count": f"{not_psif_count:,}",
        "formatted_insufficient_evidence_count": f"{sparse_count:,}",
        "formatted_human_reviewed_count": f"{(adjudicated_count if adjudicated_count else human_reviewed_count):,}",
    }

    if use_cache:
        cache.set(CACHE_KEY_ANALYTICS_SUMMARY, data, CACHE_TTL_ANALYTICS)

    return data


def get_analytics_trend(use_cache: bool = True, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Computes 12-month monthly incident volume and predicted PSIF trend series.
    Cached in Redis under CACHE_KEY_ANALYTICS_TREND.
    """
    if use_cache and not force_refresh:
        cached = cache.get(CACHE_KEY_ANALYTICS_TREND)
        if cached is not None:
            return cached

    trend = Incident.objects.filter(workspace_id__isnull=True).annotate(
        month=TruncMonth("incident_date")
    ).values("month").annotate(
        total=Count("id"),
        eligible=Count("id", filter=Q(prediction__isnull=False, prediction__is_sparse_input=False)),
        psif=Count("id", filter=Q(prediction__psif_predicted=True, prediction__is_sparse_input=False))
    ).order_by("month")

    trends_formatted = []
    for t in trend:
        if t["month"]:
            month_str = t["month"].strftime("%Y-%m")
            trends_formatted.append({
                "month": month_str,
                "total": t["total"],
                "eligible": t["eligible"],
                "psif": t["psif"]
            })

    data = {"trends": trends_formatted}

    if use_cache:
        cache.set(CACHE_KEY_ANALYTICS_TREND, data, CACHE_TTL_ANALYTICS)

    return data


def get_barrier_intelligence(use_cache: bool = True, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Computes defensible Barrier & Critical-Control Intelligence metrics across the 9 IOGP Life-Saving Rules.
    Delegates to the authoritative BarrierIntelligenceService (Task 11).
    """
    from apps.incidents.services.barrier_service import BarrierIntelligenceService
    return BarrierIntelligenceService.get_barrier_portfolio(use_cache=use_cache, force_refresh=force_refresh)


def invalidate_analytics_cache():
    """Invalidates cached analytics summary, trend series, and barrier intelligence."""
    cache.delete(CACHE_KEY_ANALYTICS_SUMMARY)
    cache.delete(CACHE_KEY_ANALYTICS_TREND)
    from apps.incidents.services.barrier_service import BarrierIntelligenceService
    BarrierIntelligenceService.invalidate_barrier_cache()
    logger.info("Analytics cache invalidated.")

