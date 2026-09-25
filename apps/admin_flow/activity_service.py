"""
PSIF Platform — Admin Flow Activity Pattern Service.
apps/admin_flow/activity_service.py

Responsibilities:
1. Surfaces recurring operational work activities across the Admin Flow dataset.
2. Strictly decouples ACTIVITY from LOCATION, BARRIER, IOGP RULE, and PSIF RESULT.
3. Computes:
   - Ranked horizontal bar distribution (Incident Volume & PSIF-Linked Volume).
   - Top activity KPI callout (Most frequently observed activity).
   - Data coverage (Known activities vs legitimate Unknown).
   - Activity × Location heatmap matrix.
   - Activity × IOGP observed association matrix.
   - Activity × Barrier observed association matrix.
   - Incident drilldowns for interactive inspection.
4. Version-controlled cache with invalidation hooks.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from django.core.cache import cache
from django.db.models import Q, QuerySet

from apps.incidents.models import Incident
from apps.admin_flow.activity_engine import (
    normalize_admin_flow_activity,
    ActivityCategory,
    ACTIVITY_DISPLAY_NAMES,
)

logger = logging.getLogger(__name__)

ADMIN_FLOW_WORKSPACE = "admin_flow"
ACTIVITY_CACHE_PREFIX = "admin_flow:activity_patterns"
ACTIVITY_CACHE_VERSION_KEY = "admin_flow:activity_patterns:version"
ACTIVITY_CACHE_TTL = 1800  # 30 minutes


def get_activity_cache_version() -> int:
    """Returns the current cache version for Admin Flow activity patterns."""
    version = cache.get(ACTIVITY_CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(ACTIVITY_CACHE_VERSION_KEY, version, timeout=None)
    return int(version)


def invalidate_admin_flow_activity_cache() -> None:
    """Increments the cache version, invalidating all cached activity pattern views."""
    try:
        cache.incr(ACTIVITY_CACHE_VERSION_KEY)
    except Exception:
        curr = get_activity_cache_version()
        cache.set(ACTIVITY_CACHE_VERSION_KEY, curr + 1, timeout=None)
    logger.info("Admin Flow activity pattern cache invalidated.")


class ActivityPatternService:
    """
    Dedicated analytical service for Admin Flow Activity Pattern Recognition.
    """

    @classmethod
    def get_activity_pattern_view_data(
        cls,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        psif_filter: Optional[str] = None,
        query: Optional[str] = None,
        workspace_id: str = ADMIN_FLOW_WORKSPACE,
    ) -> Dict[str, Any]:
        """
        Builds the comprehensive Activity Pattern Analysis payload.
        """
        version = get_activity_cache_version()
        cache_params = f"{date_from}_{date_to}_{psif_filter}_{query}_{workspace_id}"
        param_hash = hashlib.md5(cache_params.encode("utf-8")).hexdigest()
        cache_key = f"{ACTIVITY_CACHE_PREFIX}:{version}:{param_hash}"

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # ── Step 1: Base Workspace Incidents Query ──
        base_qs = Incident.objects.filter(workspace_id=workspace_id)
        total_workspace_incidents = base_qs.count()

        # Apply filtering
        filtered_qs = base_qs.select_related("prediction").prefetch_related("iogp_rules")

        if date_from:
            filtered_qs = filtered_qs.filter(incident_date__gte=date_from)
        if date_to:
            filtered_qs = filtered_qs.filter(incident_date__lte=date_to)

        if psif_filter and psif_filter.lower() != "all":
            if psif_filter.lower() == "psif":
                filtered_qs = filtered_qs.filter(
                    prediction__psif_predicted=True,
                    prediction__is_sparse_input=False,
                )
            elif psif_filter.lower() == "not_psif":
                filtered_qs = filtered_qs.filter(
                    prediction__psif_predicted=False,
                    prediction__is_sparse_input=False,
                )

        if query and str(query).strip():
            q_clean = str(query).strip()
            filtered_qs = filtered_qs.filter(
                Q(description__icontains=q_clean) |
                Q(job_task__icontains=q_clean) |
                Q(location__icontains=q_clean)
            )

        incidents_list = list(filtered_qs)
        total_filtered = len(incidents_list)

        # ── Empty State Handling ──
        if total_filtered == 0:
            empty_payload = {
                "has_data": False,
                "workspace_id": workspace_id,
                "site_context": "Duliajan Operational Complex",
                "total_workspace_incidents": total_workspace_incidents,
                "total_filtered_incidents": 0,
                "total_incidents": total_filtered,
                "total_patterns": 0,
                "recurring_count": 0,
                "distinct_activities_count": 0,
                "recurring_activities_count": 0,
                "total_psif_linked": 0,
                "known_activity_incidents": 0,
                "unknown_activity_incidents": 0,
                "activity_coverage_rate": 0.0,
                "recurring_pattern_count": 0,
                "activities": [],
                "chart_labels": [],
                "chart_incident_counts": [],
                "chart_psif_counts": [],
                "top_activity": {
                    "has_data": False,
                    "activity": "No Data",
                    "category": "No Data",
                    "display_name": "No Data",
                    "incident_count": 0,
                    "psif_linked_count": 0,
                    "psif_linkage_rate": 0.0,
                    "dataset_share": 0.0,
                    "share_label": "0.0% (0/0)",
                    "callout_caption": "No activity patterns recorded for this selection.",
                },
                "location_matrix": {"rows": [], "columns": []},
                "iogp_matrix": {"rows": [], "columns": []},
                "summary": {
                    "total_incidents": 0,
                    "known_activity_incidents": 0,
                    "unknown_activity_incidents": 0,
                    "activity_coverage_rate": 0.0,
                    "recurring_pattern_count": 0,
                }
            }
            cache.set(cache_key, empty_payload, timeout=ACTIVITY_CACHE_TTL)
            return empty_payload

        # ── Step 2: Evaluation & Extraction ──
        from apps.admin_flow.pattern_engine import normalize_admin_flow_location
        from apps.admin_flow.barrier_engine import extract_incident_barriers

        activity_buckets = defaultdict(list)
        activity_psif_counts = Counter()
        activity_location_counts = defaultdict(Counter)
        activity_barrier_counts = defaultdict(Counter)
        activity_iogp_counts = defaultdict(Counter)

        known_count = 0
        unknown_count = 0

        for inc in incidents_list:
            pred = getattr(inc, "prediction", None)
            is_psif = bool(pred and pred.psif_predicted and not getattr(pred, "is_sparse_input", False))

            narrative = inc.composite_narrative or inc.description or ""
            act_name, act_cat, method = normalize_admin_flow_activity(inc.job_task, narrative)

            if act_cat == ActivityCategory.UNKNOWN_ACTIVITY:
                unknown_count += 1
            else:
                known_count += 1

            # Location extraction
            norm_loc, _, _ = normalize_admin_flow_location(inc)

            # Barriers extraction
            barriers = extract_incident_barriers(inc)
            top_barrier_name = barriers[0].barrier_name if barriers else None
            top_barrier_state = barriers[0].barrier_state if barriers else None

            # IOGP rules extraction
            iogp_tags = list(inc.iogp_rules.all())
            iogp_rule_names = [t.rule for t in iogp_tags] if iogp_tags else []

            # Populate buckets
            activity_buckets[act_name].append({
                "incident_id": str(inc.id),
                "incident_date": inc.incident_date.strftime("%b %d, %Y") if inc.incident_date else "Recent",
                "location": norm_loc,
                "barrier": top_barrier_name or "No Established Protective Barrier",
                "barrier_state": top_barrier_state or "UNKNOWN",
                "iogp_rule": iogp_rule_names[0] if iogp_rule_names else "No Rule Matched",
                "is_psif": is_psif,
                "narrative_snippet": (inc.description[:150] + "...") if inc.description and len(inc.description) > 150 else (inc.description or ""),
            })

            if is_psif:
                activity_psif_counts[act_name] += 1

            activity_location_counts[act_name][norm_loc] += 1

            if top_barrier_name:
                activity_barrier_counts[act_name][top_barrier_name] += 1

            for r_name in iogp_rule_names:
                activity_iogp_counts[act_name][r_name] += 1

        # ── Step 3: Build Ranked Activity List ──
        sorted_activities = sorted(
            activity_buckets.keys(),
            key=lambda k: len(activity_buckets[k]),
            reverse=True,
        )

        activities_data = []
        chart_labels = []
        chart_incident_counts = []
        chart_psif_counts = []
        recurring_pattern_count = 0

        for rank, act_name in enumerate(sorted_activities, start=1):
            incidents_in_act = activity_buckets[act_name]
            inc_cnt = len(incidents_in_act)
            psif_cnt = activity_psif_counts[act_name]

            # Explicit denominators
            dataset_share = round((inc_cnt / total_filtered) * 100, 1)
            share_label = f"{dataset_share}% ({inc_cnt}/{total_filtered})"
            psif_linkage_rate = round((psif_cnt / inc_cnt) * 100, 1) if inc_cnt > 0 else 0.0
            is_recurring = inc_cnt >= 2

            if is_recurring:
                recurring_pattern_count += 1

            # Multi-dimensional associations (observed historical correlations)
            loc_counts = activity_location_counts[act_name]
            top_locs = [
                {"name": loc, "count": cnt}
                for loc, cnt in loc_counts.most_common(4)
            ]
            top_location_name = top_locs[0]["name"] if top_locs else "Site Area"

            barr_counts = activity_barrier_counts[act_name]
            top_barrs = [
                {"name": b, "count": cnt}
                for b, cnt in barr_counts.most_common(4)
            ]
            top_barrier_name = top_barrs[0]["name"] if top_barrs else "None recorded"

            iogp_counts = activity_iogp_counts[act_name]
            top_iogps = [
                {"name": r, "count": cnt}
                for r, cnt in iogp_counts.most_common(4)
            ]
            top_iogp_name = top_iogps[0]["name"] if top_iogps else "No rule association"

            act_dict = {
                "activity": act_name,
                "category": act_name,  # Backwards compatibility alias for existing tests
                "display_name": act_name,  # Friendly display name
                "rank": rank,
                "incident_count": inc_cnt,
                "psif_linked_count": psif_cnt,
                "dataset_share": dataset_share,
                "share_of_total": dataset_share,  # Backwards compatibility alias
                "share_label": share_label,
                "psif_linkage_rate": psif_linkage_rate,
                "is_recurring": is_recurring,
                "top_location": top_location_name,
                "top_barrier": top_barrier_name,
                "top_iogp_rule": top_iogp_name,
                "top_locations": top_locs,
                "top_barriers": top_barrs,
                "associated_iogp": top_iogps,
                "sample_incidents": incidents_in_act[:5],
            }
            activities_data.append(act_dict)

            chart_labels.append(act_name)
            chart_incident_counts.append(inc_cnt)
            chart_psif_counts.append(psif_cnt)

        # ── Step 4: Top Activity Callout ──
        if activities_data:
            top_act = activities_data[0]
            top_activity = {
                "has_data": True,
                "activity": top_act["activity"],
                "category": top_act["activity"],  # Backwards compatibility alias
                "display_name": top_act["activity"],
                "incident_count": top_act["incident_count"],
                "psif_linked_count": top_act["psif_linked_count"],
                "psif_linkage_rate": top_act["psif_linkage_rate"],
                "dataset_share": top_act["dataset_share"],
                "share_of_total": top_act["dataset_share"],
                "share_label": top_act["share_label"],
                "callout_caption": "Most frequently observed activity in the current Admin Flow dataset.",
                "top_location": top_act["top_location"],
                "top_barrier": top_act["top_barrier"],
                "top_iogp_rule": top_act["top_iogp_rule"],
            }
        else:
            top_activity = {
                "has_data": False,
                "activity": "None",
                "category": "None",
                "incident_count": 0,
                "psif_linked_count": 0,
                "psif_linkage_rate": 0.0,
                "dataset_share": 0.0,
                "share_label": "0.0% (0/0)",
                "callout_caption": "No activity patterns recorded.",
            }

        # ── Step 5: Activity × Location Heatmap Matrix ──
        # Top 6-8 canonical internal locations for matrix columns
        ALL_INTERNAL_LOCATIONS = [
            "Process Area / Refining Unit",
            "Workshop / Maintenance Bay",
            "Tank Farm",
            "Compressor Area",
            "Pipe Rack / Manifold",
            "Drilling Area / Rig Floor",
        ]
        # Include any additional locations that have >= 5 incidents
        seen_locs = Counter()
        for act in activities_data:
            for l_item in act["top_locations"]:
                seen_locs[l_item["name"]] += l_item["count"]

        matrix_locations = list(ALL_INTERNAL_LOCATIONS)
        for loc_name, cnt in seen_locs.most_common():
            if loc_name not in matrix_locations and cnt >= 5 and len(matrix_locations) < 8:
                matrix_locations.append(loc_name)

        # Build matrix rows for top 8 activities
        matrix_rows = []
        max_matrix_val = 1
        for act in activities_data[:8]:
            row_cells = []
            for loc in matrix_locations:
                val = activity_location_counts[act["activity"]][loc]
                if val > max_matrix_val:
                    max_matrix_val = val
                row_cells.append({"location": loc, "count": val})
            matrix_rows.append({
                "activity": act["activity"],
                "cells": row_cells,
            })

        # Assign intensity (0 to 4) based on relative maximum
        for r in matrix_rows:
            for c in r["cells"]:
                val = c["count"]
                if val == 0:
                    c["intensity"] = 0
                elif val < (max_matrix_val * 0.25):
                    c["intensity"] = 1
                elif val < (max_matrix_val * 0.50):
                    c["intensity"] = 2
                elif val < (max_matrix_val * 0.75):
                    c["intensity"] = 3
                else:
                    c["intensity"] = 4

        location_matrix = {
            "columns": matrix_locations,
            "rows": matrix_rows,
        }

        # ── Step 6: Activity × IOGP Association Matrix ──
        CANONICAL_IOGP_9 = [
            "Safe Mechanical Lifting",
            "Energy Isolation",
            "Driving",
            "Working at Height",
            "Hot Work",
            "Confined Space",
            "Line of Fire",
            "Work Authorization",
            "Bypassing Safety Controls",
        ]
        iogp_matrix_rows = []
        max_iogp_val = 1
        for act in activities_data[:8]:
            row_cells = []
            for rule in CANONICAL_IOGP_9:
                val = activity_iogp_counts[act["activity"]][rule]
                if val > max_iogp_val:
                    max_iogp_val = val
                row_cells.append({"rule": rule, "count": val})
            iogp_matrix_rows.append({
                "activity": act["activity"],
                "cells": row_cells,
            })

        for r in iogp_matrix_rows:
            for c in r["cells"]:
                val = c["count"]
                if val == 0:
                    c["intensity"] = 0
                elif val < (max_iogp_val * 0.25):
                    c["intensity"] = 1
                elif val < (max_iogp_val * 0.50):
                    c["intensity"] = 2
                elif val < (max_iogp_val * 0.75):
                    c["intensity"] = 3
                else:
                    c["intensity"] = 4

        iogp_matrix = {
            "columns": CANONICAL_IOGP_9,
            "rows": iogp_matrix_rows,
        }

        # Coverage rate
        coverage_rate = round((known_count / total_filtered) * 100, 1) if total_filtered > 0 else 0.0

        summary = {
            "total_incidents": total_filtered,
            "known_activity_incidents": known_count,
            "unknown_activity_incidents": unknown_count,
            "activity_coverage_rate": coverage_rate,
            "recurring_pattern_count": recurring_pattern_count,
            "unique_activities_count": len(activities_data),
        }

        site_name = "Duliajan Operational Complex"
        total_psif = sum(a["psif_linked_count"] for a in activities_data)

        view_data = {
            "has_data": total_filtered > 0,
            "workspace_id": workspace_id,
            "site_context": site_name,
            "total_workspace_incidents": total_workspace_incidents,
            "total_filtered_incidents": total_filtered,
            "total_incidents": total_filtered,
            "total_patterns": len(activities_data),
            "recurring_count": recurring_pattern_count,
            "distinct_activities_count": len(activities_data),
            "recurring_activities_count": recurring_pattern_count,
            "total_psif_linked": total_psif,
            "known_activity_incidents": known_count,
            "unknown_activity_incidents": unknown_count,
            "activity_coverage_rate": coverage_rate,
            "recurring_pattern_count": recurring_pattern_count,
            "activities": activities_data,
            "chart_labels": chart_labels,
            "chart_incident_counts": chart_incident_counts,
            "chart_psif_counts": chart_psif_counts,
            "top_activity": top_activity,
            "location_matrix": location_matrix,
            "iogp_matrix": iogp_matrix,
            "summary": summary,
        }

        cache.set(cache_key, view_data, timeout=ACTIVITY_CACHE_TTL)
        return view_data
