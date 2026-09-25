from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult

from django.conf import settings
from .services import (
    CANONICAL_METRIC_DEFINITION,
    CANONICAL_METRIC_DEFINITIONS,
    get_analytics_summary,
    get_analytics_trend,
    get_barrier_intelligence,
)


class AnalyticsSummaryAPIView(APIView):
    """GET /api/analytics/summary/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        force_refresh = (request.GET.get("refresh") == "true" or getattr(settings, "TESTING", False))
        data = get_analytics_summary(use_cache=not force_refresh, force_refresh=force_refresh)
        return Response(data, status=status.HTTP_200_OK)


class AnalyticsTrendAPIView(APIView):
    """GET /api/analytics/trend/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        force_refresh = (request.GET.get("refresh") == "true" or getattr(settings, "TESTING", False))
        data = get_analytics_trend(use_cache=not force_refresh, force_refresh=force_refresh)
        return Response(data, status=status.HTTP_200_OK)

import json
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from apps.dashboard.tasks import CACHE_KEY_RECURRING, CACHE_KEY_MULTI_SITE
from apps.dashboard.pattern_detection import detect_recurring_patterns, detect_multi_site_recurrence

class RecurringPatternsAPIView(APIView):
    """GET /api/analytics/recurring-patterns/"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        cached_data = cache.get(CACHE_KEY_RECURRING)
        if cached_data:
            patterns = json.loads(cached_data)
        else:
            # Synchronous fallback if cache is empty
            patterns = detect_recurring_patterns()
            cache.set(CACHE_KEY_RECURRING, json.dumps(patterns, cls=DjangoJSONEncoder), 3600)
            
        return Response({"patterns": patterns}, status=status.HTTP_200_OK)

class CrossSiteAlertsAPIView(APIView):
    """GET /api/analytics/cross-site-alerts/"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        cached_data = cache.get(CACHE_KEY_MULTI_SITE)
        if cached_data:
            patterns = json.loads(cached_data)
        else:
            # Synchronous fallback if cache is empty
            patterns = detect_multi_site_recurrence()
            cache.set(CACHE_KEY_MULTI_SITE, json.dumps(patterns, cls=DjangoJSONEncoder), 3600)
            
        return Response({"alerts": patterns}, status=status.HTTP_200_OK)


class BarrierIntelligenceAPIView(APIView):
    """GET /api/analytics/barriers/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        force_refresh = (request.GET.get("refresh") == "true" or getattr(settings, "TESTING", False))
        data = get_barrier_intelligence(use_cache=not force_refresh, force_refresh=force_refresh)
        return Response(data, status=status.HTTP_200_OK)


class BarrierDetailAPIView(APIView):
    """GET /api/analytics/barriers/<str:rule_slug>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, rule_slug, *args, **kwargs):
        from apps.incidents.services.barrier_service import BarrierIntelligenceService
        from apps.incidents.services.normalization import normalize_iogp_rule
        rule_norm = normalize_iogp_rule(rule_slug.replace("-", " "))
        page = int(request.GET.get("page", 1))
        page_size = int(request.GET.get("page_size", 10))

        try:
            data = BarrierIntelligenceService.get_barrier_detail(
                rule_name=rule_norm.canonical_value,
                page=page,
                page_size=page_size,
            )
            return Response(data, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error("Error in BarrierDetailAPIView: %s", e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

