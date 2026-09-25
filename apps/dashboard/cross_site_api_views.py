"""
PSIF Platform — Normalized Cross-Site Intelligence REST API Views
apps/dashboard/cross_site_api_views.py

Provides authenticated REST API endpoints for cross-site safety signal analysis.
All endpoints return explicit metadata:
- normalization_version
- data_scope
- denominator definitions
- methodology disclosures and limitations
- generated_at timestamp
"""

from typing import List
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.incidents.services.normalization import (
    NORMALIZATION_VERSION,
    normalize_operational_site,
)
from apps.dashboard.cross_site_service import (
    METHODOLOGY_DISCLOSURE,
    PLATFORM_LIMITATIONS,
    get_cross_site_overview,
    get_site_comparison_table,
    get_site_detail,
    get_site_iogp_matrix,
    get_site_hazard_matrix,
    get_normalized_activities_cross_site,
    get_normalized_hazards_cross_site,
    get_normalized_iogp_cross_site,
    compare_sites,
    get_cross_site_recurrence_signals,
)


def _base_metadata(extra_denominators: dict = None) -> dict:
    denominators = {
        "psif_rate": "Prediction-eligible observations with composite narrative (n = eligible observations)",
        "site_volumes": "Total recorded observations mapped to canonical operational facility",
    }
    if extra_denominators:
        denominators.update(extra_denominators)

    return {
        "normalization_version": NORMALIZATION_VERSION,
        "data_scope": "Historical incident records across operational sites and facilities",
        "generated_at": timezone.now().isoformat(),
        "methodology_notice": METHODOLOGY_DISCLOSURE,
        "limitations": PLATFORM_LIMITATIONS,
        "denominators": denominators,
    }


class CrossSiteOverviewAPIView(APIView):
    """
    GET /api/cross-site/overview/
    Returns high-level system safety signal KPIs across all operational facilities.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        force_refresh = request.query_params.get("refresh", "").lower() in ("true", "1")
        data = get_cross_site_overview(force_refresh=force_refresh)
        return Response(data, status=status.HTTP_200_OK)


class CrossSiteSitesAPIView(APIView):
    """
    GET /api/cross-site/sites/
    Returns site-by-site comparative summary across all canonical operational sites.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        force_refresh = request.query_params.get("refresh", "").lower() in ("true", "1")
        sites = get_site_comparison_table(force_refresh=force_refresh)
        return Response({
            "count": len(sites),
            "sites": sites,
            "metadata": _base_metadata({
                "comparison_metric": "Observed safety-signal volume per canonical site",
            }),
        }, status=status.HTTP_200_OK)


class CrossSiteSiteDetailAPIView(APIView):
    """
    GET /api/cross-site/sites/<str:site_id>/
    Returns detailed operational safety context for a single canonical site.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, site_id: str):
        force_refresh = request.query_params.get("refresh", "").lower() in ("true", "1")
        detail = get_site_detail(site_id, force_refresh=force_refresh)
        if not detail:
            return Response({
                "error": f"Site '{site_id}' not found or has no recorded observations.",
                "normalized_attempt": normalize_operational_site(site_id).to_dict(),
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "site": detail,
            "metadata": _base_metadata({
                "site_detail": f"All historical records attributed to {detail['canonical_site']}",
            }),
        }, status=status.HTTP_200_OK)


class CrossSiteActivitiesAPIView(APIView):
    """
    GET /api/cross-site/activities/
    Returns safety observations aggregated across sites by normalized canonical activity.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        force_refresh = request.query_params.get("refresh", "").lower() in ("true", "1")
        activities = get_normalized_activities_cross_site(force_refresh=force_refresh)
        return Response({
            "count": len(activities),
            "activities": activities,
            "metadata": _base_metadata({
                "activity_denominators": "Total observations grouped by normalized canonical activity",
            }),
        }, status=status.HTTP_200_OK)


class CrossSiteHazardsAPIView(APIView):
    """
    GET /api/cross-site/hazards/
    Returns safety observations aggregated across sites by the 15 canonical hazard families.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        force_refresh = request.query_params.get("refresh", "").lower() in ("true", "1")
        hazards = get_normalized_hazards_cross_site(force_refresh=force_refresh)
        return Response({
            "count": len(hazards),
            "hazards": hazards,
            "metadata": _base_metadata({
                "hazard_denominators": "Observations classified into 15 canonical high-energy hazard families",
            }),
        }, status=status.HTTP_200_OK)


class CrossSiteIOGPAPIView(APIView):
    """
    GET /api/cross-site/iogp/
    Returns observation counts for the 9 canonical IOGP Life-Saving Rules across sites.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        force_refresh = request.query_params.get("refresh", "").lower() in ("true", "1")
        rules = get_normalized_iogp_cross_site(force_refresh=force_refresh)
        matrix = get_site_iogp_matrix(force_refresh=force_refresh)
        return Response({
            "count": len(rules),
            "rules": rules,
            "site_matrix": matrix,
            "metadata": _base_metadata({
                "rule_status": "All rule occurrences are RULE-DERIVED CANDIDATES (not confirmed violations)",
            }),
        }, status=status.HTTP_200_OK)


class CrossSiteCompareAPIView(APIView):
    """
    GET /api/cross-site/compare/?sites=Duliajan,Numaligarh
    Compares 2 or more canonical sites head-to-head.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sites_param = request.query_params.get("sites", "")
        site_list: List[str] = [s.strip() for s in sites_param.split(",") if s.strip()]
        if not site_list:
            # Default to top 2 operational sites
            site_list = ["DULIAJAN", "NUMALIGARH"]

        comparison = compare_sites(site_list)
        return Response({
            "comparison": comparison,
            "metadata": _base_metadata({
                "compared_entities": f"Selected operational sites: {', '.join(site_list)}",
            }),
        }, status=status.HTTP_200_OK)


class CrossSiteRecurrenceAPIView(APIView):
    """
    GET /api/cross-site/recurrence/
    Returns historical recurring safety signals detected across 2 or more distinct sites.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            window_days = int(request.query_params.get("window_days", 180))
        except (TypeError, ValueError):
            window_days = 180

        try:
            min_sites = int(request.query_params.get("min_sites", 2))
        except (TypeError, ValueError):
            min_sites = 2

        recurrence = get_cross_site_recurrence_signals(window_days=window_days, min_sites=min_sites)
        return Response({
            "count": len(recurrence),
            "recurrence_signals": recurrence,
            "time_window_days": window_days,
            "min_sites_threshold": min_sites,
            "guidance_statement": "Similar observations have been recorded across multiple sites.",
            "metadata": _base_metadata({
                "recurrence_scope": f"Historical signals across ≥ {min_sites} sites in {window_days}-day window",
            }),
        }, status=status.HTTP_200_OK)
