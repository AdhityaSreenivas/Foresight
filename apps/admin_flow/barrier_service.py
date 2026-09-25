"""
PSIF Platform — Admin Flow Barrier Intelligence Service.
apps/admin_flow/barrier_service.py

Authoritative, single-source service for Admin Flow Barrier Intelligence:
- Computes canonical BarrierObservation records across the Admin Flow dataset.
- Evaluates barrier recurrence, effective safeguards, and control deficiencies.
- Aggregates multi-dimensional associations: Location, Activity, IOGP Rule, and PSIF linkage.
- Manages high-performance Admin Flow versioned caching.
"""
import logging
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set

from django.core.cache import cache
from django.db.models import Q, QuerySet

from apps.incidents.models import Incident
from apps.admin_flow.barrier_engine import (
    BarrierCategory,
    BarrierObservation,
    BarrierRole,
    BarrierState,
    BARRIER_LABELS,
    DEFICIENT_BARRIER_STATES,
    EFFECTIVE_BARRIER_STATES,
    extract_incident_barriers,
)

logger = logging.getLogger(__name__)

ADMIN_FLOW_WORKSPACE = "admin_flow"
ADMIN_FLOW_SITE_NAME = "Duliajan Operational Complex"

CACHE_PREFIX_BARRIER_PATTERNS = "admin_flow:barrier_patterns"
CACHE_VERSION_KEY_BARRIER = "admin_flow:barrier_patterns:version"
CACHE_TTL_BARRIER = 1800  # 30 minutes


# ── Cache Version Management ──────────────────────────────────────────────────

def get_admin_flow_barrier_cache_version() -> int:
    """Returns the current cache version number for Admin Flow barrier analytics."""
    version = cache.get(CACHE_VERSION_KEY_BARRIER)
    if version is None:
        version = 1
        cache.set(CACHE_VERSION_KEY_BARRIER, version, timeout=None)
    return version


def invalidate_admin_flow_barrier_cache() -> None:
    """
    Increments the barrier cache version, immediately invalidating all
    cached barrier analytics for Admin Flow.
    """
    try:
        cache.incr(CACHE_VERSION_KEY_BARRIER)
    except Exception:
        curr = get_admin_flow_barrier_cache_version()
        cache.set(CACHE_VERSION_KEY_BARRIER, curr + 1, timeout=None)
    logger.info("Admin Flow Barrier Intelligence cache invalidated (version bumped).")


# ── Canonical Barrier Pattern Service ─────────────────────────────────────────

class BarrierPatternService:
    """
    Canonical service for Barrier Intelligence analytics in Admin Flow.
    Single source of truth for:
    - Barrier Pattern Analysis page (/admin-flow/patterns/barrier/)
    - REST API (/admin-flow/api/patterns/barrier/)
    - Pattern Analysis Hub summary card
    - Multi-dimensional cross-dimension synthesis
    """

    @classmethod
    def get_barrier_pattern_view_data(
        cls,
        psif_filter: Optional[str] = None,
        state_filter: Optional[str] = None,
        location_filter: Optional[str] = None,
        query: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Builds complete, structured view data for the Barrier Intelligence workspace.
        Supports caching and granular filtering by PSIF status, control state, location, and query.
        """
        # Determine cache key
        version = get_admin_flow_barrier_cache_version()
        cache_key = (
            f"{CACHE_PREFIX_BARRIER_PATTERNS}:{version}:"
            f"psif={psif_filter or 'all'}:"
            f"state={state_filter or 'all'}:"
            f"loc={location_filter or 'all'}:"
            f"q={query or ''}"
        )

        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return cached_data

        data = cls._compute_barrier_analytics(
            psif_filter=psif_filter,
            state_filter=state_filter,
            location_filter=location_filter,
            query=query,
        )

        if use_cache:
            cache.set(cache_key, data, timeout=CACHE_TTL_BARRIER)

        return data

    @classmethod
    def _compute_barrier_analytics(
        cls,
        psif_filter: Optional[str] = None,
        state_filter: Optional[str] = None,
        location_filter: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Core analytical aggregation across Admin Flow incidents."""
        from apps.admin_flow.pattern_engine import (
            normalize_admin_flow_location,
            normalize_admin_flow_activity,
            CANONICAL_INTERNAL_LOCATIONS,
        )

        base_qs = Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE)
        total_workspace_incidents = base_qs.count()

        qs = (
            base_qs
            .select_related("prediction")
            .prefetch_related("iogp_rules")
            .order_by("-incident_date", "-created_at")
        )

        # 1. Apply Query Search
        if query and query.strip():
            q_clean = query.strip()
            qs = qs.filter(
                Q(job_task__icontains=q_clean) |
                Q(description__icontains=q_clean) |
                Q(location__icontains=q_clean) |
                Q(equipment_involved__icontains=q_clean)
            )

        # 2. Apply PSIF Filter
        if psif_filter == "psif":
            qs = qs.filter(prediction__psif_predicted=True, prediction__is_sparse_input=False)
        elif psif_filter == "not_psif":
            qs = qs.filter(prediction__psif_predicted=False, prediction__is_sparse_input=False)
        elif psif_filter == "insufficient":
            qs = qs.filter(prediction__is_sparse_input=True)

        # 3. Extract All Barrier Observations
        incident_list = list(qs)
        total_filtered_incidents = len(incident_list)

        # Track distinct incidents for top-level KPIs
        incidents_with_barrier: Set[str] = set()
        incidents_with_effective: Set[str] = set()
        incidents_with_deficient: Set[str] = set()

        # Group observations by barrier category
        barrier_groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "category": "",
            "name": "",
            "role": "",
            "associated_incidents": set(),
            "effective_incidents": set(),
            "deficient_incidents": set(),
            "psif_incidents": set(),
            "locations": Counter(),
            "activities": Counter(),
            "iogp_rules": Counter(),
            "states": Counter(),
            "evidence_examples": [],
        })

        # Dataset-wide state breakdown
        state_distribution: Counter = Counter()

        for inc in incident_list:
            inc_id = str(inc.id)
            loc_tuple = normalize_admin_flow_location(inc)
            loc_norm = loc_tuple[0] if isinstance(loc_tuple, (tuple, list)) else str(loc_tuple)
            act_tuple = normalize_admin_flow_activity(inc.job_task, inc.description)
            act_norm = act_tuple[0] if isinstance(act_tuple, (tuple, list)) else str(act_tuple)

            barriers = extract_incident_barriers(
                inc,
                default_activity=act_norm,
                default_location=loc_norm,
            )

            if barriers:
                incidents_with_barrier.add(inc_id)

            for b in barriers:
                # 4. Apply State Filter if specified
                if state_filter and state_filter.strip() and state_filter != "all":
                    sf = state_filter.strip().upper()
                    if sf == "EFFECTIVE" and not b.is_effective:
                        continue
                    elif sf in ["DEFICIENT", "DEFICIENCY"] and not b.is_deficient:
                        continue
                    elif sf not in ["EFFECTIVE", "DEFICIENT", "DEFICIENCY"] and b.barrier_state.upper() != sf:
                        continue

                # 5. Apply Location Filter if specified
                if location_filter and location_filter.strip() and location_filter != "all":
                    target_loc = location_filter.strip().lower()
                    if target_loc not in b.location.lower():
                        continue

                cat = b.barrier_category
                group = barrier_groups[cat]
                group["category"] = cat
                group["name"] = b.barrier_name
                group["role"] = b.barrier_role

                group["associated_incidents"].add(inc_id)
                if b.is_effective:
                    group["effective_incidents"].add(inc_id)
                    incidents_with_effective.add(inc_id)
                if b.is_deficient:
                    group["deficient_incidents"].add(inc_id)
                    incidents_with_deficient.add(inc_id)

                if b.psif_state == "PSIF":
                    group["psif_incidents"].add(inc_id)

                group["states"][b.barrier_state] += 1
                state_distribution[b.barrier_state] += 1

                if b.location and b.location != "UNKNOWN LOCATION":
                    group["locations"][b.location] += 1
                if b.activity and b.activity != "UNKNOWN ACTIVITY":
                    group["activities"][b.activity] += 1
                if b.iogp_rule and b.iogp_rule not in ["None Associated", "Unknown", "none"]:
                    group["iogp_rules"][b.iogp_rule] += 1

                # Save up to 4 evidence examples with state
                if len(group["evidence_examples"]) < 4:
                    group["evidence_examples"].append({
                        "incident_id": inc_id,
                        "state": b.barrier_state,
                        "is_effective": b.is_effective,
                        "is_deficient": b.is_deficient,
                        "evidence_span": b.evidence_span,
                        "location": b.location,
                        "activity": b.activity,
                        "iogp_rule": b.iogp_rule,
                    })

        # Assemble Ranked Portfolio Cards
        portfolio_cards: List[Dict[str, Any]] = []

        for cat, g in barrier_groups.items():
            total_assoc = len(g["associated_incidents"])
            if total_assoc == 0:
                continue

            eff_count = len(g["effective_incidents"])
            def_count = len(g["deficient_incidents"])
            psif_count = len(g["psif_incidents"])

            share_pct = round((total_assoc / total_filtered_incidents * 100), 1) if total_filtered_incidents > 0 else 0.0
            psif_rate = round((psif_count / total_assoc * 100), 1) if total_assoc > 0 else 0.0

            # Sorted locations & activities
            top_locs = [loc for loc, _ in g["locations"].most_common()]
            top_acts = [act for act, _ in g["activities"].most_common()]
            associated_rules = [rule for rule, _ in g["iogp_rules"].most_common(3)]

            # Dominant state
            dominant_state = g["states"].most_common(1)[0][0] if g["states"] else "UNKNOWN"

            portfolio_cards.append({
                "barrier_category": cat,
                "barrier_name": g["name"],
                "barrier_role": g["role"],
                "associated_incidents_count": total_assoc,
                "share_of_dataset": share_pct,
                "effective_count": eff_count,
                "deficient_count": def_count,
                "psif_linked_count": psif_count,
                "psif_rate": psif_rate,
                "dominant_state": dominant_state,
                "state_breakdown": dict(g["states"]),
                "affected_locations": top_locs,
                "affected_locations_count": len(top_locs),
                "top_activity": top_acts[0] if top_acts else "General Operations",
                "top_activities": top_acts[:3],
                "associated_iogp_rules": associated_rules,
                "is_recurring": total_assoc >= 2,
                "evidence_examples": g["evidence_examples"],
            })

        # Sort portfolio cards descending by total associated incident count
        portfolio_cards.sort(key=lambda x: (-x["associated_incidents_count"], -x["deficient_count"], x["barrier_name"]))

        # Assign ranks
        for idx, card in enumerate(portfolio_cards, start=1):
            card["rank"] = idx

        # Top Callout 1: Most Frequent Barrier Overall
        top_barrier_overall = portfolio_cards[0] if portfolio_cards else None

        # Top Callout 2: Most Frequent Effective Barrier (Top Protective Success)
        effective_sorted = sorted(portfolio_cards, key=lambda x: (-x["effective_count"], x["barrier_name"]))
        top_effective_barrier = effective_sorted[0] if (effective_sorted and effective_sorted[0]["effective_count"] > 0) else None

        # Top Callout 3: Most Frequent Deficient Barrier (Top Vulnerability Signal)
        deficient_sorted = sorted(portfolio_cards, key=lambda x: (-x["deficient_count"], x["barrier_name"]))
        top_deficient_barrier = deficient_sorted[0] if (deficient_sorted and deficient_sorted[0]["deficient_count"] > 0) else None

        # Chart.js Payload (Top 12 for clean visibility)
        top_chart_cards = portfolio_cards[:12]
        chart_labels = [c["barrier_name"] for c in top_chart_cards]
        chart_total_counts = [c["associated_incidents_count"] for c in top_chart_cards]
        chart_effective_counts = [c["effective_count"] for c in top_chart_cards]
        chart_deficient_counts = [c["deficient_count"] for c in top_chart_cards]
        chart_psif_counts = [c["psif_linked_count"] for c in top_chart_cards]

        # Dataset metrics
        barrier_identified_count = len(incidents_with_barrier)
        barrier_unestablished_count = total_filtered_incidents - barrier_identified_count
        barrier_identification_rate = (
            round((barrier_identified_count / total_filtered_incidents * 100), 1)
            if total_filtered_incidents > 0 else 0.0
        )

        has_active_filters = bool(
            (psif_filter and psif_filter != "all") or
            (state_filter and state_filter != "all") or
            (location_filter and location_filter != "all") or
            (query and query.strip())
        )

        return {
            "workspace_id": ADMIN_FLOW_WORKSPACE,
            "site_context": ADMIN_FLOW_SITE_NAME,
            "total_workspace_incidents": total_workspace_incidents,
            "total_filtered_incidents": total_filtered_incidents,
            "barrier_identified_count": barrier_identified_count,
            "barrier_unestablished_count": barrier_unestablished_count,
            "barrier_identification_rate": barrier_identification_rate,
            "unique_barrier_types_count": len(portfolio_cards),
            "total_patterns": len(portfolio_cards),
            "distinct_barriers_count": len(portfolio_cards),
            "recurring_barriers_count": len([c for c in portfolio_cards if c["is_recurring"]]),
            "total_deficiency_associated": sum(c["deficient_count"] for c in portfolio_cards),
            "total_psif_linked": sum(c["psif_linked_count"] for c in portfolio_cards),
            "effective_barrier_signals": len(incidents_with_effective),
            "deficient_barrier_signals": len(incidents_with_deficient),
            "effective_rate": round(len(incidents_with_effective) / total_filtered_incidents * 100, 1) if total_filtered_incidents > 0 else 0.0,
            "deficient_rate": round(len(incidents_with_deficient) / total_filtered_incidents * 100, 1) if total_filtered_incidents > 0 else 0.0,
            "top_barrier_overall": top_barrier_overall,
            "top_effective_barrier": top_effective_barrier,
            "top_deficient_barrier": top_deficient_barrier,
            "state_distribution": dict(state_distribution),
            "portfolio_cards": portfolio_cards,
            "barriers": portfolio_cards,  # Alias for backward compatibility
            "chart_labels": chart_labels,
            "chart_total_counts": chart_total_counts,
            "chart_effective_counts": chart_effective_counts,
            "chart_deficient_counts": chart_deficient_counts,
            "chart_deficiency_counts": chart_deficient_counts,  # Alias for backward compatibility
            "chart_psif_counts": chart_psif_counts,
            "has_data": len(portfolio_cards) > 0,
            "has_active_filters": has_active_filters,
            "canonical_locations": CANONICAL_INTERNAL_LOCATIONS,
            "supported_states": [
                BarrierState.EFFECTIVE,
                BarrierState.FAILED,
                BarrierState.NOT_VERIFIED,
                BarrierState.ABSENT,
                BarrierState.BYPASSED,
                BarrierState.PARTIALLY_EFFECTIVE,
            ],
            "filters": {
                "psif_filter": psif_filter or "all",
                "state_filter": state_filter or "all",
                "location_filter": location_filter or "all",
                "query": query or "",
            },
            "methodology_note": (
                "Barriers represent physical and operational protective safeguards described in incident reports. "
                "Effective safeguards are recognized as protective successes and are not classified as failures. "
                "Associated IOGP rules provide domain context and are tracked independently."
            ),
        }
