"""
PSIF Platform — Admin Flow Canonical Data Access Contract & Isolation Services.

This module provides the single source of truth for:
1. Identifying Admin Flow users and workspace scopes.
2. Filtering incidents, predictions, and datasets to the isolated Admin Flow workspace.
3. Filtering global/existing datasets to exclude Admin Flow demonstration records.
4. Computing dynamically isolated dashboard metrics for Admin Flow.
"""
import logging
from typing import Any, Dict, List, Optional
from django.db import transaction
from django.db.models import Count, Q, QuerySet, Avg
from django.core.cache import cache
from django.utils import timezone
from apps.incidents.models import Incident, IncidentReview, IOGPRuleTag
from apps.predictions.models import PredictionResult
from apps.datasets.models import Dataset

logger = logging.getLogger(__name__)

# Canonical workspace identifier
ADMIN_FLOW_WORKSPACE = "admin_flow"
ADMIN_FLOW_RESET_LOCK_KEY = "admin_flow:reset_lock"
ADMIN_FLOW_GENERATION_KEY = "admin_flow:generation"
ADMIN_FLOW_AUDIT_LOG_KEY = "admin_flow:audit_log"


def is_admin_flow_user(user) -> bool:
    """
    Check if a user has the ADMIN_FLOW role or is designated as an Admin Flow user.
    """
    if not user or not user.is_authenticated:
        return False
    return getattr(user, "is_admin_flow", False) or getattr(user, "role", None) == "admin_flow"


def get_admin_flow_workspace(request_or_user=None) -> str:
    """
    Returns the canonical workspace identifier for Admin Flow.
    """
    return ADMIN_FLOW_WORKSPACE


def get_admin_flow_incidents(queryset: Optional[QuerySet] = None) -> QuerySet[Incident]:
    """
    Return all incidents belonging strictly to the Admin Flow workspace.
    """
    if queryset is None:
        queryset = Incident.objects.all()
    return queryset.filter(workspace_id=ADMIN_FLOW_WORKSPACE)


def get_global_incidents(queryset: Optional[QuerySet] = None) -> QuerySet[Incident]:
    """
    Return all incidents belonging to the existing global system (excluding Admin Flow records).
    """
    if queryset is None:
        queryset = Incident.objects.all()
    return queryset.filter(workspace_id__isnull=True)


def get_admin_flow_datasets(queryset: Optional[QuerySet] = None) -> QuerySet[Dataset]:
    """
    Return all datasets uploaded strictly within the Admin Flow workspace.
    """
    if queryset is None:
        queryset = Dataset.objects.all()
    return queryset.filter(workspace_id=ADMIN_FLOW_WORKSPACE)


def get_global_datasets(queryset: Optional[QuerySet] = None) -> QuerySet[Dataset]:
    """
    Return all datasets belonging to the existing global system (excluding Admin Flow records).
    """
    if queryset is None:
        queryset = Dataset.objects.all()
    return queryset.filter(workspace_id__isnull=True)


def get_admin_flow_predictions(queryset: Optional[QuerySet] = None) -> QuerySet[PredictionResult]:
    """
    Return predictions associated strictly with Admin Flow incidents.
    """
    if queryset is None:
        queryset = PredictionResult.objects.all()
    return queryset.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE)


def get_admin_flow_analytics_summary() -> Dict[str, Any]:
    """
    Computes dynamically isolated analytics metrics strictly for Admin Flow.
    Starts genuinely at zero when no records exist.
    """
    # 1. Prediction aggregations scoped to Admin Flow
    pred_stats = PredictionResult.objects.filter(
        incident__workspace_id=ADMIN_FLOW_WORKSPACE
    ).aggregate(
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

    inc_stats = Incident.objects.filter(
        workspace_id=ADMIN_FLOW_WORKSPACE
    ).aggregate(
        total=Count("id", distinct=True),
        adjudicated=Count("id", filter=Q(adjudication_status=Incident.AdjudicationStatus.ADJUDICATED), distinct=True),
        human_reviewed=Count(
            "id",
            filter=Q(adjudication_status=Incident.AdjudicationStatus.ADJUDICATED) |
            Q(is_psif_human_label__isnull=False) |
            Q(reviews__isnull=False),
            distinct=True
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

    # Rates
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

    return {
        # Raw integer values
        "total_incidents": total_incidents,
        "total_predictions": total_predictions,
        "prediction_eligible_count": prediction_eligible_count,
        "psif_count": psif_count,
        "not_psif_count": not_psif_count,
        "insufficient_evidence_count": sparse_count,
        "human_reviewed_count": human_reviewed_count,
        "human_psif_count": human_psif_count,
        "human_not_psif_count": human_not_psif_count,
        "human_insufficient_count": human_insufficient_count,
        "high_risk": high_risk,
        "psif_prediction_rate": psif_prediction_rate,
        "psif_percentage": psif_percentage,
        "prediction_coverage_rate": prediction_coverage_rate,
        "human_reviewed_rate": human_reviewed_rate,
        # Formatted string values for UI KPI cards
        "formatted_total_incidents": f"{total_incidents:,}",
        "formatted_prediction_eligible_count": f"{prediction_eligible_count:,}",
        "formatted_psif_count": f"{psif_count:,}",
        "formatted_not_psif_count": f"{not_psif_count:,}",
        "formatted_insufficient_evidence_count": f"{sparse_count:,}",
        "formatted_human_reviewed_count": f"{human_reviewed_count:,}",
        "is_admin_flow": True,
        "workspace_id": ADMIN_FLOW_WORKSPACE,
    }


def get_admin_flow_psif_metrics() -> Dict[str, Any]:
    """
    Computes visual summary metrics for the Admin Flow PSIF Classification page.
    Strictly isolated to workspace_id='admin_flow'.
    """
    pred_stats = PredictionResult.objects.filter(
        incident__workspace_id=ADMIN_FLOW_WORKSPACE
    ).aggregate(
        total=Count("id"),
        sparse=Count("id", filter=Q(is_sparse_input=True)),
        eligible=Count("id", filter=Q(is_sparse_input=False)),
        psif=Count("id", filter=Q(is_sparse_input=False, psif_predicted=True)),
        not_psif=Count("id", filter=Q(is_sparse_input=False, psif_predicted=False)),
        score_low=Count("id", filter=Q(is_sparse_input=False, psif_probability__lt=0.20)),
        score_medium=Count("id", filter=Q(is_sparse_input=False, psif_probability__gte=0.20, psif_probability__lt=0.50)),
        score_high=Count("id", filter=Q(is_sparse_input=False, psif_probability__gte=0.50, psif_probability__lt=0.75)),
        score_critical=Count("id", filter=Q(is_sparse_input=False, psif_probability__gte=0.75)),
        avg_score=Avg("psif_probability", filter=Q(is_sparse_input=False)),
    )

    total_predictions = pred_stats["total"] or 0
    sparse_count = pred_stats["sparse"] or 0
    prediction_eligible_count = pred_stats["eligible"] or 0
    psif_count = pred_stats["psif"] or 0
    not_psif_count = pred_stats["not_psif"] or 0

    inc_stats = Incident.objects.filter(
        workspace_id=ADMIN_FLOW_WORKSPACE
    ).aggregate(
        total=Count("id", distinct=True),
        reviewed=Count(
            "id",
            filter=Q(adjudication_status=Incident.AdjudicationStatus.ADJUDICATED) |
            Q(is_psif_human_label__isnull=False) |
            Q(reviews__isnull=False),
            distinct=True
        ),
    )
    total_incidents = inc_stats["total"] or 0
    reviewed_count = inc_stats["reviewed"] or 0
    unreviewed_count = max(0, total_incidents - reviewed_count)

    # PSIF Rate among eligible records: explicitly defined denominator
    if prediction_eligible_count > 0:
        psif_rate = round((psif_count / prediction_eligible_count) * 100, 1)
        psif_rate_display = f"{psif_rate}%"
    else:
        psif_rate = None
        psif_rate_display = "—"

    recent_incidents = (
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE)
        .select_related("prediction")
        .prefetch_related("iogp_rules")
        .order_by("-incident_date", "-created_at")[:20]
    )

    return {
        "total_incidents": total_incidents,
        "total_predictions": total_predictions,
        "prediction_eligible_count": prediction_eligible_count,
        "psif_count": psif_count,
        "not_psif_count": not_psif_count,
        "insufficient_evidence_count": sparse_count,
        "has_eligible": prediction_eligible_count > 0,
        "has_data": total_incidents > 0,
        "psif_rate": psif_rate,
        "psif_rate_display": psif_rate_display,
        "denominator_definition": "Prediction-eligible non-sparse observations (excludes insufficient evidence)",
        "binary_distribution": {
            "PSIF": psif_count,
            "NOT_PSIF": not_psif_count,
        },
        "evidence_distribution": {
            "eligible": prediction_eligible_count,
            "insufficient": sparse_count,
        },
        "score_distribution": {
            "low": pred_stats["score_low"] or 0,
            "medium": pred_stats["score_medium"] or 0,
            "high": pred_stats["score_high"] or 0,
            "critical": pred_stats["score_critical"] or 0,
        },
        "review_distribution": {
            "reviewed": reviewed_count,
            "unreviewed": unreviewed_count,
        },
        "average_psif_score": round(pred_stats["avg_score"], 3) if pred_stats["avg_score"] is not None else None,
        "formatted_average_psif_score": f"{pred_stats['avg_score']:.3f}" if pred_stats["avg_score"] is not None else "—",
        "recent_incidents": recent_incidents,
        "workspace_id": ADMIN_FLOW_WORKSPACE,
        "methodology_note": "The PSIF Model Score is a model output and is not presented as a calibrated probability.",
        "semantic_note": "NOT PSIF ≠ INSUFFICIENT INFORMATION: NOT PSIF indicates evaluated observations with low precursor risk. INSUFFICIENT INFORMATION indicates sparse narrative text (< 10 words) where evidence is lacking.",
    }


def get_admin_flow_iogp_metrics() -> Dict[str, Any]:
    """
    Computes visual metrics for the Admin Flow IOGP Classification page.
    Covers the 9 canonical IOGP Life-Saving Rules sorted descending by incident count,
    plus an explicit category for legitimate unmatched incidents.
    Strictly isolated to workspace_id='admin_flow'.
    """
    from apps.incidents.services.normalization import CANONICAL_IOGP_RULES

    # Total incident counts in Admin Flow
    total_analyzed_incidents = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).count()
    matched_incidents_count = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE, iogp_rules__isnull=False).distinct().count()
    unmatched_incidents_count = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE, iogp_rules__isnull=True).distinct().count()

    unmatched_psif_linked = Incident.objects.filter(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        iogp_rules__isnull=True,
        prediction__psif_predicted=True,
        prediction__is_sparse_input=False,
    ).distinct().count()

    unmatched_sites = Incident.objects.filter(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        iogp_rules__isnull=True,
    ).exclude(location__in=[None, ""]).values("location").distinct().count()

    unmatched_linkage_rate = (
        round((unmatched_psif_linked / unmatched_incidents_count * 100), 1)
        if unmatched_incidents_count > 0
        else 0.0
    )

    qs = (
        IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE)
        .values("rule")
        .annotate(
            matched_observations=Count("incident", distinct=True),
            psif_linked_observations=Count(
                "incident",
                filter=Q(
                    incident__prediction__psif_predicted=True,
                    incident__prediction__is_sparse_input=False,
                ),
                distinct=True,
            ),
            affected_sites=Count(
                "incident__location",
                filter=~Q(incident__location__in=[None, ""]),
                distinct=True,
            ),
        )
    )

    db_map = {}
    for item in qs:
        r_name = item["rule"]
        db_map[r_name] = {
            "matched": item["matched_observations"] or 0,
            "psif_linked": item["psif_linked_observations"] or 0,
            "affected_sites": item["affected_sites"] or 0,
        }

    barriers = []
    for rule_name in CANONICAL_IOGP_RULES:
        r_data = db_map.get(rule_name, {"matched": 0, "psif_linked": 0, "affected_sites": 0})
        matched = r_data["matched"]
        psif_linked = r_data["psif_linked"]
        sites = r_data["affected_sites"]
        linkage_rate = round((psif_linked / matched * 100), 1) if matched > 0 else 0.0

        barriers.append({
            "rule": rule_name,
            "slug": rule_name.lower().replace(" ", "-"),
            "matched_observations": matched,
            "formatted_matched": f"{matched:,}",
            "psif_linked_observations": psif_linked,
            "formatted_psif_linked": f"{psif_linked:,}",
            "affected_sites": sites,
            "formatted_affected_sites": f"{sites:,}",
            "psif_linkage_rate": linkage_rate,
            "has_matches": matched > 0,
            "is_unmatched_category": False,
        })

    # Sort canonical rules from highest to lowest incident count, then alphabetically
    barriers.sort(key=lambda x: (-x["matched_observations"], x["rule"]))

    # Explicit category for legitimate non-matching incidents
    unmatched_category = {
        "rule": "No IOGP Rule Matched",
        "slug": "none",
        "matched_observations": unmatched_incidents_count,
        "formatted_matched": f"{unmatched_incidents_count:,}",
        "psif_linked_observations": unmatched_psif_linked,
        "formatted_psif_linked": f"{unmatched_psif_linked:,}",
        "affected_sites": unmatched_sites,
        "formatted_affected_sites": f"{unmatched_sites:,}",
        "psif_linkage_rate": unmatched_linkage_rate,
        "has_matches": unmatched_incidents_count > 0,
        "is_unmatched_category": True,
        "description": "Legitimate non-rule observations evaluated by the canonical classifier with no Life-Saving Rule keyword match.",
    }

    chart_labels = [b["rule"] for b in barriers]
    chart_matched = [b["matched_observations"] for b in barriers]
    chart_psif = [b["psif_linked_observations"] for b in barriers]
    total_rule_matches = sum(chart_matched)
    # Count distinct PSIF-predicted incidents matched to at least one rule (not a per-rule sum,
    # which overcounts incidents matched to multiple rules).
    total_psif_linked = Incident.objects.filter(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        iogp_rules__isnull=False,
        prediction__psif_predicted=True,
        prediction__is_sparse_input=False,
    ).distinct().count()

    recent_rule_tags = (
        IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE)
        .select_related("incident", "incident__prediction")
        .order_by("-created_at")[:20]
    )

    return {
        "rules": barriers,
        "unmatched_category": unmatched_category,
        "total_analyzed_incidents": total_analyzed_incidents,
        "matched_incidents_count": matched_incidents_count,
        "unmatched_incidents_count": unmatched_incidents_count,
        "unmatched_psif_linked": unmatched_psif_linked,
        "total_rule_matches": total_rule_matches,
        "total_psif_linked": total_psif_linked,
        "chart_labels": chart_labels,
        "chart_matched": chart_matched,
        "chart_psif": chart_psif,
        "has_data": total_analyzed_incidents > 0,
        "recent_rule_tags": recent_rule_tags,
        "workspace_id": ADMIN_FLOW_WORKSPACE,
        "semantic_disclaimer": (
            "Rule-matched / Rule-derived candidate: An IOGP rule match does NOT automatically mean a confirmed violation, "
            "a failed barrier, or a PSIF precursor. Observations with no rule match reflect legitimate non-rule events."
        ),
    }


def get_admin_flow_barrier_portfolio_data(use_cache: bool = True) -> Dict[str, Any]:
    """
    Authoritative Barrier Intelligence Portfolio for Admin Flow (Task: Barrier Intelligence Portfolio).
    Computes visual and interactive card data for the canonical 9 IOGP Life-Saving Rules.

    Guarantees:
    1. Exactly 9 canonical rules in official canonical order (1 to 9).
    2. Single bulk-aggregated execution (0 N+1 queries).
    3. Metrics:
       - Matched Observations (distinct Admin Flow incidents matched)
       - PSIF-Linked Observations (matched incidents with canonical PSIF prediction)
       - Affected Internal Locations (distinct locations count & top locations list)
       - Most frequently associated activity (top activity)
       - Highest observation concentration (top internal location)
       - Dominant observed control state (evidence-based, without treating UNKNOWN as failure)
       - Representative matched sample incidents for drilldown inspection
    4. Canonical IOGP definitions, citations (IOGP Report 459), and Start-Work Checks.
    5. Clean empty states (all 9 cards persist with 0s after reset or empty workspace).
    6. Non-causal terminology contract throughout.
    """
    from apps.incidents.knowledge.iogp import IOGPRuleCode, IOGP_RULE_DEFINITIONS
    from apps.incidents.services.normalization import CANONICAL_IOGP_RULES

    gen = get_admin_flow_generation()
    cache_key = f"admin_flow:barrier_portfolio:{gen}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    # 1. Base counts in Admin Flow
    total_analyzed = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).count()
    matched_incidents_count = (
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE, iogp_rules__isnull=False)
        .distinct()
        .count()
    )
    unmatched_incidents_count = (
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE, iogp_rules__isnull=True)
        .distinct()
        .count()
    )
    unmatched_psif = (
        Incident.objects.filter(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            iogp_rules__isnull=True,
            prediction__psif_predicted=True,
            prediction__is_sparse_input=False,
        )
        .distinct()
        .count()
    )
    unmatched_sites = (
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE, iogp_rules__isnull=True)
        .exclude(location__in=[None, ""])
        .values("location")
        .distinct()
        .count()
    )

    # 2. Bulk Query 1: Matched, PSIF, and Location counts per rule
    stats_qs = (
        IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE)
        .values("rule")
        .annotate(
            matched_count=Count("incident", distinct=True),
            psif_count=Count(
                "incident",
                filter=Q(
                    incident__prediction__psif_predicted=True,
                    incident__prediction__is_sparse_input=False,
                ),
                distinct=True,
            ),
            affected_locations_count=Count(
                "incident__location",
                filter=~Q(incident__location__in=[None, ""]),
                distinct=True,
            ),
        )
    )
    stats_map = {
        item["rule"]: {
            "matched": item["matched_count"] or 0,
            "psif": item["psif_count"] or 0,
            "locations": item["affected_locations_count"] or 0,
        }
        for item in stats_qs
    }

    # 3. Bulk Query 2: Top associated activities per rule
    activity_qs = (
        IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE)
        .exclude(incident__job_task__in=[None, ""])
        .values("rule", "incident__job_task")
        .annotate(cnt=Count("incident", distinct=True))
        .order_by("rule", "-cnt")
    )
    top_activities_map = {}
    for row in activity_qs:
        r = row["rule"]
        if r not in top_activities_map:
            top_activities_map[r] = {"name": row["incident__job_task"], "count": row["cnt"]}

    # 4. Bulk Query 3: Top locations per rule
    location_qs = (
        IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE)
        .exclude(incident__location__in=[None, ""])
        .values("rule", "incident__location")
        .annotate(cnt=Count("incident", distinct=True))
        .order_by("rule", "-cnt")
    )
    top_locations_map = {}
    all_locations_by_rule = {}
    for row in location_qs:
        r = row["rule"]
        loc_name = row["incident__location"]
        if r not in top_locations_map:
            top_locations_map[r] = {"name": loc_name, "count": row["cnt"]}
        if r not in all_locations_by_rule:
            all_locations_by_rule[r] = []
        if len(all_locations_by_rule[r]) < 6:
            all_locations_by_rule[r].append(f"{loc_name} ({row['cnt']})")

    # 5. Bulk Query 4: Dominant observed control state per rule
    control_qs = (
        IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE)
        .exclude(incident__control_condition__in=[None, "", "unknown"])
        .values("rule", "incident__control_condition")
        .annotate(cnt=Count("incident", distinct=True))
        .order_by("rule", "-cnt")
    )
    control_map = {}
    for row in control_qs:
        r = row["rule"]
        if r not in control_map:
            cond_raw = row["incident__control_condition"]
            cond_label = {
                "effective": "Effective / Maintained",
                "failed": "Failed / Compromised",
                "absent": "Absent / Not Implemented",
                "bypassed": "Bypassed / Defeated",
            }.get(cond_raw, cond_raw.title())
            control_map[r] = {
                "condition": cond_label,
                "count": row["cnt"],
                "raw": cond_raw,
            }

    # 6. Bulk Query 5: Representative matched sample incidents (up to 4 per rule)
    recent_tags = (
        IOGPRuleTag.objects.filter(incident__workspace_id=ADMIN_FLOW_WORKSPACE)
        .select_related("incident", "incident__prediction")
        .order_by("-incident__incident_date", "-incident__created_at")[:120]
    )
    sample_incidents_by_rule = {}
    for tag in recent_tags:
        r = tag.rule
        if r not in sample_incidents_by_rule:
            sample_incidents_by_rule[r] = []
        if len(sample_incidents_by_rule[r]) < 4:
            inc = tag.incident
            pred = getattr(inc, "prediction", None)
            is_psif = bool(pred and pred.psif_predicted and not pred.is_sparse_input)
            sample_incidents_by_rule[r].append({
                "id": str(inc.id),
                "incident_date": inc.incident_date.strftime("%b %d, %Y") if inc.incident_date else "Recent",
                "job_task": inc.job_task or "General Operations",
                "location": inc.location or "Site Area",
                "description_snippet": (inc.description[:140] + "...") if inc.description and len(inc.description) > 140 else (inc.description or "No description recorded"),
                "psif_predicted": is_psif,
                "psif_probability": round(pred.psif_probability * 100, 1) if pred and pred.psif_probability is not None else None,
                "risk_level": getattr(pred, "risk_level", "LOW") or "LOW",
                "control_condition": inc.control_condition or "Unknown",
            })

    # Rule SVGs (Clean, authoritative iconography matching Foresight design language)
    RULE_SVG_ICONS = {
        "Bypassing Safety Controls": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>'
            '<line x1="12" y1="8" x2="12" y2="12"></line>'
            '<line x1="12" y1="16" x2="12.01" y2="16"></line>'
            '</svg>'
        ),
        "Confined Space": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>'
            '<polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>'
            '<line x1="12" y1="22.08" x2="12" y2="12"></line>'
            '</svg>'
        ),
        "Driving": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="1" y="3" width="15" height="13"></rect>'
            '<polygon points="16 8 20 8 23 11 23 16 16 16 16 8"></polygon>'
            '<circle cx="5.5" cy="18.5" r="2.5"></circle>'
            '<circle cx="18.5" cy="18.5" r="2.5"></circle>'
            '</svg>'
        ),
        "Energy Isolation": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>'
            '</svg>'
        ),
        "Hot Work": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path>'
            '</svg>'
        ),
        "Line of Fire": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="12" cy="12" r="10"></circle>'
            '<line x1="22" y1="12" x2="18" y2="12"></line>'
            '<line x1="6" y1="12" x2="2" y2="12"></line>'
            '<line x1="12" y1="6" x2="12" y2="2"></line>'
            '<line x1="12" y1="22" x2="12" y2="18"></line>'
            '</svg>'
        ),
        "Safe Mechanical Lifting": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>'
            '<rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>'
            '</svg>'
        ),
        "Work Authorization": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>'
            '<polyline points="14 2 14 8 20 8"></polyline>'
            '<polyline points="9 15 11 17 15 13"></polyline>'
            '</svg>'
        ),
        "Working at Height": (
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '<line x1="6" y1="3" x2="6" y2="21"></line>'
            '<line x1="18" y1="3" x2="18" y2="21"></line>'
            '<line x1="6" y1="7" x2="18" y2="7"></line>'
            '<line x1="6" y1="12" x2="18" y2="12"></line>'
            '<line x1="6" y1="17" x2="18" y2="17"></line>'
            '</svg>'
        ),
    }

    # 7. Build Portfolio Cards in Canonical IOGP Order (1 to 9)
    portfolio_cards = []
    total_rule_matches = 0

    for idx, rule_name in enumerate(CANONICAL_IOGP_RULES, start=1):
        rule_def = IOGP_RULE_DEFINITIONS.get(rule_name, {})
        stats = stats_map.get(rule_name, {"matched": 0, "psif": 0, "locations": 0})
        matched = stats["matched"]
        psif_linked = stats["psif"]
        locations_cnt = stats["locations"]
        total_rule_matches += matched

        linkage_rate = round((psif_linked / matched * 100), 1) if matched > 0 else 0.0

        top_act_data = top_activities_map.get(rule_name)
        top_activity_name = top_act_data["name"] if top_act_data else "None yet recorded"
        top_activity_count = top_act_data["count"] if top_act_data else 0

        top_loc_data = top_locations_map.get(rule_name)
        top_location_name = top_loc_data["name"] if top_loc_data else "None yet recorded"
        top_location_count = top_loc_data["count"] if top_loc_data else 0

        control_data = control_map.get(rule_name)
        if control_data:
            dominant_control_state = f"{control_data['condition']} ({control_data['count']} observation{'s' if control_data['count'] != 1 else ''})"
            control_signal = f"Reported evidence indicates dominant state: {control_data['condition']}"
        else:
            dominant_control_state = "Not Specified in Report Evidence"
            control_signal = "No non-routine control deficiency specified in matching narrative"

        portfolio_cards.append({
            "order": idx,
            "rule": rule_name,
            "slug": rule_name.lower().replace(" ", "-"),
            "modal_id": f"modal-rule-{idx}",
            "description": rule_def.get("description", "Follow applicable life-saving controls for this domain."),
            "source_reference": rule_def.get("source_section", f"IOGP Report 459 (2018) {rule_name}"),
            "start_work_checks": rule_def.get("start_work_checks", []),
            "svg_icon": RULE_SVG_ICONS.get(rule_name, ""),
            "matched_observations": matched,
            "formatted_matched": f"{matched:,}",
            "psif_linked_observations": psif_linked,
            "formatted_psif_linked": f"{psif_linked:,}",
            "psif_linkage_rate": linkage_rate,
            "affected_locations": locations_cnt,
            "formatted_affected_locations": f"{locations_cnt:,}",
            "top_locations_list": all_locations_by_rule.get(rule_name, []),
            "top_activity": top_activity_name,
            "top_activity_count": top_activity_count,
            "top_location": top_location_name,
            "top_location_count": top_location_count,
            "dominant_control_state": dominant_control_state,
            "control_signal": control_signal,
            "has_matches": matched > 0,
            "recent_incidents": sample_incidents_by_rule.get(rule_name, []),
        })

    result = {
        "status": "success",
        "has_data": total_analyzed > 0,
        "total_analyzed_incidents": total_analyzed,
        "total_rule_matches": total_rule_matches,
        "matched_incidents_count": matched_incidents_count,
        "unmatched_incidents_count": unmatched_incidents_count,
        # Distinct PSIF-predicted incidents matched to ≥1 rule — avoids double-counting
        # incidents that match multiple rules (same bug as summing chart_psif per-rule).
        "total_psif_linked": Incident.objects.filter(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            iogp_rules__isnull=False,
            prediction__psif_predicted=True,
            prediction__is_sparse_input=False,
        ).distinct().count(),
        "rules": portfolio_cards,
        "unmatched_summary": {
            "rule": "No IOGP Rule Matched",
            "matched_observations": unmatched_incidents_count,
            "formatted_matched": f"{unmatched_incidents_count:,}",
            "psif_linked_observations": unmatched_psif,
            "formatted_psif_linked": f"{unmatched_psif:,}",
            "affected_locations": unmatched_sites,
            "formatted_affected_locations": f"{unmatched_sites:,}",
            "has_matches": unmatched_incidents_count > 0,
        },
        "methodology_note": (
            "IOGP categories are derived from the canonical rule-matching system. "
            "A rule match does not by itself establish a confirmed violation or control failure."
        ),
        "workspace_id": ADMIN_FLOW_WORKSPACE,
        "generation": gen,
    }

    try:
        cache.set(cache_key, result, timeout=1800)
    except Exception:
        pass

    return result


def get_admin_flow_generation() -> int:
    """
    Returns the current generation token/version for the Admin Flow workspace.
    Incremented on each reset to ensure concurrent tasks and caches recognize the clean sheet.
    """
    try:
        gen = cache.get(ADMIN_FLOW_GENERATION_KEY)
        if gen is None:
            gen = 1
            cache.set(ADMIN_FLOW_GENERATION_KEY, gen, timeout=None)
        return int(gen)
    except Exception:
        return 1


def invalidate_admin_flow_barrier_portfolio_cache() -> None:
    """
    Explicitly deletes the Admin Flow barrier portfolio cache entry for the current
    generation. Must be called whenever Admin Flow incidents or IOGPRuleTags change
    (dataset upload, incident submission, re-processing) so the 9 canonical rule
    cards on /admin-flow/iogp/ reflect live data on the next page load.
    """
    try:
        gen = get_admin_flow_generation()
        cache.delete(f"admin_flow:barrier_portfolio:{gen}")
        logger.info(
            "Admin Flow barrier portfolio cache invalidated (gen=%s).", gen
        )
    except Exception as exc:
        logger.warning(
            "Failed to invalidate Admin Flow barrier portfolio cache: %s", exc
        )


def is_admin_flow_reset_in_progress() -> bool:
    """
    Check if an Admin Flow reset operation is currently running.
    """
    try:
        return bool(cache.get(ADMIN_FLOW_RESET_LOCK_KEY))
    except Exception:
        return False


def get_admin_flow_reset_audit_log() -> List[Dict[str, Any]]:
    """
    Returns the recent audit events for Admin Flow reset actions.
    """
    try:
        return cache.get(ADMIN_FLOW_AUDIT_LOG_KEY, [])
    except Exception:
        return []


def reset_admin_flow_workspace(user=None) -> Dict[str, Any]:
    """
    Complete Clean-Sheet Demonstration Reset for the Admin Flow workspace.

    Safety & Scoping Guarantees:
    1. Scope is 100% server-enforced: targets strictly workspace_id='admin_flow'.
       NEVER deletes or modifies global records (workspace_id__isnull=True).
    2. Cooperative async cancellation: Signals in-flight Admin Flow Dataset tasks
       via cancel_requested and Redis keys so Celery chunk workers abort cleanly.
    3. Concurrency locking: Sets a temporary reset lock to block concurrent uploads.
    4. Transactional atomicity: Deletes all Admin Flow Incidents (cascading to
       PredictionResults, IOGPRuleTags, IncidentReviews, IncidentEmbeddings,
       IncidentDataQuality checks) and Datasets in a single atomic transaction.
    5. Cache invalidation: Bumps the pattern-analysis cache version and workspace generation token.
    6. Audit logging: Logs a structured ADMIN_FLOW_RESET event with user, timestamp,
       and deleted record tallies.
    7. Naturally recalculating: All downstream services naturally return 0 counts.
    """
    from .pattern_engine import invalidate_admin_flow_pattern_cache

    # 1. Acquire reset lock (30s timeout) to prevent upload race conditions
    try:
        cache.set(ADMIN_FLOW_RESET_LOCK_KEY, "1", timeout=30)
    except Exception as lock_err:
        logger.warning("Could not set reset lock in cache: %s", lock_err)

    try:
        # 2. Cooperatively cancel any in-flight Admin Flow dataset processing tasks
        active_datasets = list(Dataset.objects.filter(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            status__in=[
                Dataset.Status.PROCESSING,
                Dataset.Status.RETRYING,
                Dataset.Status.UPLOADED,
                Dataset.Status.CANCEL_REQUESTED,
            ]
        ))
        for ds in active_datasets:
            ds.cancel_requested = True
            ds.status = Dataset.Status.CANCELED
            try:
                ds.save(update_fields=["cancel_requested", "status"])
            except Exception:
                pass
            # Signal Redis cancellation key for sub-millisecond task abort
            try:
                import redis
                from django.conf import settings
                broker_url = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
                r = redis.from_url(broker_url)
                r.set(f"dataset:cancel:{ds.id}", "1", ex=300)
            except Exception:
                pass

        # 3. Transactional atomic database deletion strictly scoped to Admin Flow
        with transaction.atomic():
            af_incidents = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE)
            deleted_incidents_count = af_incidents.count()
            deleted_predictions_count = PredictionResult.objects.filter(
                incident__workspace_id=ADMIN_FLOW_WORKSPACE
            ).count()
            deleted_iogp_count = IOGPRuleTag.objects.filter(
                incident__workspace_id=ADMIN_FLOW_WORKSPACE
            ).count()
            deleted_reviews_count = IncidentReview.objects.filter(
                incident__workspace_id=ADMIN_FLOW_WORKSPACE
            ).count()

            # Fast cascading delete of all Admin Flow incidents and related entities
            af_incidents.delete()

            af_datasets = Dataset.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE)
            deleted_datasets_count = af_datasets.count()
            for ds in af_datasets:
                if ds.original_file:
                    try:
                        ds.original_file.delete(save=False)
                    except Exception:
                        pass
            af_datasets.delete()

        # 4. Cache invalidation & generation version bump
        invalidate_admin_flow_pattern_cache()
        try:
            curr_gen = cache.get(ADMIN_FLOW_GENERATION_KEY, 1) or 1
            new_gen = int(curr_gen) + 1
            cache.set(ADMIN_FLOW_GENERATION_KEY, new_gen, timeout=None)
            cache.delete(f"admin_flow:barrier_portfolio:{curr_gen}")
            cache.delete(f"admin_flow:barrier_portfolio:{new_gen}")
        except Exception:
            new_gen = 2

        # 5. Audit Logging
        now = timezone.now()
        timestamp = now.isoformat()
        username = getattr(user, "username", "admin_flow_user") if user else "system"
        audit_entry = {
            "event": "ADMIN_FLOW_RESET",
            "user": username,
            "timestamp": timestamp,
            "generation": new_gen,
            "deleted_counts": {
                "incidents": deleted_incidents_count,
                "datasets": deleted_datasets_count,
                "predictions": deleted_predictions_count,
                "iogp_rules": deleted_iogp_count,
                "human_reviews": deleted_reviews_count,
            },
            "remaining_counts": {
                "incidents": 0,
                "datasets": 0,
                "predictions": 0,
                "iogp_rules": 0,
                "human_reviews": 0,
            },
            "result": "SUCCESS",
        }
        logger.info(
            "AUDIT: ADMIN_FLOW_RESET executed by user=%s at %s. Removed %d incidents, %d datasets, %d predictions. Generation=%d.",
            username, timestamp, deleted_incidents_count, deleted_datasets_count, deleted_predictions_count, new_gen
        )

        try:
            history = cache.get(ADMIN_FLOW_AUDIT_LOG_KEY, [])
            if not isinstance(history, list):
                history = []
            history.insert(0, audit_entry)
            cache.set(ADMIN_FLOW_AUDIT_LOG_KEY, history[:25], timeout=None)
        except Exception:
            pass

        return {
            "status": "success",
            "message": "Demonstration workspace successfully reset to a clean starting state.",
            "workspace_id": ADMIN_FLOW_WORKSPACE,
            "user": username,
            "timestamp": timestamp,
            "generation": new_gen,
            "deleted_incidents": deleted_incidents_count,
            "deleted_datasets": deleted_datasets_count,
            "deleted_predictions": deleted_predictions_count,
            "remaining_incidents": 0,
            "deleted": audit_entry["deleted_counts"],
            "remaining": audit_entry["remaining_counts"],
            "audit_entry": audit_entry,
        }
    finally:
        # Release reset lock
        try:
            cache.delete(ADMIN_FLOW_RESET_LOCK_KEY)
        except Exception:
            pass
