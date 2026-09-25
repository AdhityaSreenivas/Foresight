"""
PSIF Platform — Development Settings
Extends base.py with development-specific overrides.
"""
from .base import *  # noqa: F401, F403

DEBUG = True

# Allow all hosts locally
ALLOWED_HOSTS = ["*"]

# Explicitly trust local development origins for CSRF
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://0.0.0.0:8000",
]

# More verbose SQL logging in dev (uncomment to see all queries)
# LOGGING["loggers"]["django.db.backends"] = {
#     "handlers": ["console"],
#     "level": "DEBUG",
#     "propagate": False,
# }

# Use console email backend in dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
