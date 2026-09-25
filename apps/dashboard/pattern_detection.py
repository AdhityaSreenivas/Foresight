from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Min, Max, F, Q

from apps.incidents.models import IOGPRuleTag
from apps.incidents.services.normalization import (
    normalize_department,
    normalize_activity,
    normalize_iogp_rule,
)

# The field mapped to 'site' for recurrence detection.
SITE_FIELD = "incident__department"
# The field mapped to 'activity' for recurrence detection.
ACTIVITY_FIELD = "incident__job_task"

def detect_recurring_patterns(
    window_days: int = 90,
    min_occurrences: int = 3,
    site: str = None,
    activity: str = None,
    limit: int = 50,
):
    """
    Analytical recurrence detection.
    Identifies repeated combinations of site, activity, and IOGP rule
    within a given time window.
    
    Args:
        window_days: Number of days to look back from now.
        min_occurrences: Minimum number of distinct incidents required to form a pattern.
        site: Optional site/department filter to scope detection (matches raw or canonical).
        activity: Optional activity/job_task filter to scope detection (matches raw or canonical).
        limit: Maximum number of top patterns to return (default 50).
        
    Returns:
        List of recurring pattern dictionaries with canonical entity enrichment.
    """
    cutoff_date = timezone.now() - timedelta(days=window_days)

    # Base queryset: only include tags on incidents within the time window
    # We filter by incident_date if available, fallback to created_at
    qs = IOGPRuleTag.objects.filter(
        Q(incident__incident_date__gte=cutoff_date) | 
        Q(incident__incident_date__isnull=True, incident__created_at__gte=cutoff_date)
    )

    if site:
        site_candidates = {site}
        norm_site = normalize_department(site)
        if norm_site.canonical_value:
            site_candidates.add(norm_site.canonical_value)
        qs = qs.filter(**{f"{SITE_FIELD}__in": list(site_candidates)})
    else:
        qs = qs.exclude(**{f"{SITE_FIELD}__isnull": True}).exclude(**{f"{SITE_FIELD}": ""})

    if activity:
        act_candidates = {activity}
        norm_act = normalize_activity(activity)
        if norm_act.canonical_value:
            act_candidates.add(norm_act.canonical_value)
        qs = qs.filter(**{f"{ACTIVITY_FIELD}__in": list(act_candidates)})
    else:
        qs = qs.exclude(**{f"{ACTIVITY_FIELD}__isnull": True}).exclude(**{f"{ACTIVITY_FIELD}": ""})

    patterns = (
        qs.values(
            site=F(SITE_FIELD),
            activity=F(ACTIVITY_FIELD),
            rule_name=F("rule")
        )
        .annotate(
            occurrence_count=Count("incident", distinct=True),
            first_seen=Min("incident__incident_date"),
            last_seen=Max("incident__incident_date"),
        )
        .filter(occurrence_count__gte=min_occurrences)
        .order_by("-occurrence_count")
    )

    if limit and limit > 0:
        patterns = list(patterns[:limit])
    else:
        patterns = list(patterns)

    # Attach sample incident IDs to matched patterns for drill-down.
    results = []
    for p in patterns:
        incident_ids = list(
            IOGPRuleTag.objects.filter(
                Q(incident__incident_date__gte=cutoff_date) | 
                Q(incident__incident_date__isnull=True, incident__created_at__gte=cutoff_date),
                **{SITE_FIELD: p["site"], ACTIVITY_FIELD: p["activity"], "rule": p["rule_name"]}
            ).values_list("incident_id", flat=True).distinct()[:20]
        )
        
        norm_site_ent = normalize_department(p["site"])
        norm_act_ent = normalize_activity(p["activity"])
        norm_rule_ent = normalize_iogp_rule(p["rule_name"])

        results.append({
            "site": p["site"],
            "activity": p["activity"],
            "rule": p["rule_name"],
            "canonical_site": norm_site_ent.canonical_value,
            "canonical_activity": norm_act_ent.canonical_value,
            "canonical_rule": norm_rule_ent.canonical_value,
            "occurrence_count": p["occurrence_count"],
            "first_seen": p["first_seen"],
            "last_seen": p["last_seen"],
            "time_window_days": window_days,
            "incident_ids": [str(uid) for uid in incident_ids],
            "normalized_entities": {
                "site": norm_site_ent.to_dict(),
                "activity": norm_act_ent.to_dict(),
                "rule": norm_rule_ent.to_dict(),
            }
        })

    return results

def detect_multi_site_recurrence(
    window_days: int = 90,
    min_sites: int = 2,
    rules: list = None
):
    """
    Identifies IOGP rules recurring across multiple distinct sites.
    
    Args:
        window_days: Number of days to look back from now.
        min_sites: Minimum number of distinct sites required.
        rules: Optional list of specific IOGP rules to filter by.
    """
    cutoff_date = timezone.now() - timedelta(days=window_days)

    qs = IOGPRuleTag.objects.filter(
        Q(incident__incident_date__gte=cutoff_date) | 
        Q(incident__incident_date__isnull=True, incident__created_at__gte=cutoff_date)
    )

    if rules:
        qs = qs.filter(rule__in=rules)

    qs = qs.exclude(**{f"{SITE_FIELD}__isnull": True}).exclude(**{f"{SITE_FIELD}": ""})

    patterns = (
        qs.values(rule_name=F("rule"))
        .annotate(
            site_count=Count(SITE_FIELD, distinct=True),
            total_incidents=Count("incident", distinct=True),
            first_seen=Min("incident__incident_date"),
            last_seen=Max("incident__incident_date")
        )
        .filter(site_count__gte=min_sites)
        .order_by("-site_count", "-total_incidents")
    )

    results = []
    for p in patterns:
        sites = list(
            IOGPRuleTag.objects.filter(
                Q(incident__incident_date__gte=cutoff_date) | 
                Q(incident__incident_date__isnull=True, incident__created_at__gte=cutoff_date),
                rule=p["rule_name"]
            ).exclude(**{f"{SITE_FIELD}__isnull": True}).exclude(**{f"{SITE_FIELD}": ""})
            .values_list(SITE_FIELD, flat=True)
            .distinct()
        )

        norm_rule_ent = normalize_iogp_rule(p["rule_name"])
        canonical_sites = [normalize_department(s).canonical_value for s in sites]

        results.append({
            "rule": p["rule_name"],
            "canonical_rule": norm_rule_ent.canonical_value,
            "site_count": p["site_count"],
            "sites": sites,
            "canonical_sites": canonical_sites,
            "total_incidents": p["total_incidents"],
            "first_seen": p["first_seen"],
            "last_seen": p["last_seen"],
            "time_window_days": window_days
        })

    return results
