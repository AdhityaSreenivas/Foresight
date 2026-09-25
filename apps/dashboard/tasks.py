import logging
import json
from celery import shared_task
from django.core.cache import cache

from .pattern_detection import detect_recurring_patterns, detect_multi_site_recurrence

logger = logging.getLogger(__name__)

CACHE_KEY_RECURRING = "dashboard:recurring_patterns"
CACHE_KEY_MULTI_SITE = "dashboard:multi_site_recurrence"
CACHE_TTL = 3600  # 1 hour

@shared_task
def compute_pattern_detection_alerts():
    """
    Computes analytical recurrences and caches the results in Redis.
    To be run periodically via Celery Beat (e.g., every 15-30 minutes).
    """
    logger.info("Computing pattern detection alerts...")
    
    try:
        # Detect recurring local patterns
        recurring = detect_recurring_patterns(window_days=90, min_occurrences=3)
        cache.set(CACHE_KEY_RECURRING, json.dumps(recurring), CACHE_TTL)
        
        # Detect multi-site recurrences
        multi_site = detect_multi_site_recurrence(window_days=90, min_sites=2)
        cache.set(CACHE_KEY_MULTI_SITE, json.dumps(multi_site), CACHE_TTL)
        
        logger.info(f"Pattern detection computed: {len(recurring)} recurring, {len(multi_site)} multi-site.")
    except Exception as e:
        logger.exception(f"Error computing pattern detection alerts: {e}")
