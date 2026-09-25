"""
PSIF Platform — Production Settings
Extends base.py with production-specific overrides.
Set DJANGO_SETTINGS_MODULE=config.settings.prod in your production environment.
"""
from .base import *  # noqa: F401, F403

DEBUG = False

# In production, ALLOWED_HOSTS must be set explicitly via .env
# ALLOWED_HOSTS = env("ALLOWED_HOSTS")  # already loaded by base.py

# Security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Use SMTP in production — configure via env vars
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
