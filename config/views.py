"""
PSIF Platform — System & Health Views
"""
import logging
from django.db import connection
from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    """
    Lightweight health check endpoint for container orchestrators and load balancers.
    Returns status: healthy, database: ok/error, cache: ok/error.
    Does not expose sensitive credentials, stack traces, or environment data.
    """
    status = {"status": "healthy", "database": "ok", "cache": "ok"}
    status_code = 200

    # 1. Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception as exc:
        logger.warning("Health check database failure: %s", exc)
        status["database"] = "error"
        status["status"] = "unhealthy"
        status_code = 503

    # 2. Cache check (graceful degradation reported)
    try:
        cache.set("_health_test", 1, 5)
        if cache.get("_health_test") != 1:
            status["cache"] = "degraded"
    except Exception as exc:
        logger.warning("Health check cache failure: %s", exc)
        status["cache"] = "unavailable"

    return JsonResponse(status, status=status_code)
