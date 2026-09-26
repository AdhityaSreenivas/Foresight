import os
try:
    import requests
except ImportError:
    requests = None
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

def get_industrial_image(query='industrial safety worker', orientation='landscape'):
    """
    Fetch an image from Pexels API related to industrial safety.
    Fails gracefully by returning local static image if API key is not present or if the request fails.
    Caches the image URL to avoid hitting rate limits.
    """
    fallback_image = '/static/img/hero.jpg' if orientation == 'landscape' else '/static/img/auth_hero.jpg'
    
    if not PEXELS_API_KEY or requests is None:
        logger.info("PEXELS_API_KEY not found or requests unavailable. Returning local fallback imagery.")
        return fallback_image

    cache_key = f"pexels_img_{query}_{orientation}"
    cached_url = cache.get(cache_key)
    if cached_url:
        return cached_url

    try:
        headers = {
            'Authorization': PEXELS_API_KEY
        }
        params = {
            'query': query,
            'orientation': orientation,
            'per_page': 1
        }
        response = requests.get('https://api.pexels.com/v1/search', headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get('photos') and len(data['photos']) > 0:
            image_url = data['photos'][0]['src']['large2x']
            # Cache for 24 hours
            cache.set(cache_key, image_url, 60 * 60 * 24)
            return image_url
    except Exception as e:
        logger.error(f"Error fetching image from Pexels: {e}")
    
    return fallback_image
