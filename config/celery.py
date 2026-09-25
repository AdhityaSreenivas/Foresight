"""
PSIF Platform — Celery Application Configuration

Run the worker with:
    celery -A config worker -l info

Run beat scheduler (if periodic tasks needed):
    celery -A config beat -l info
"""
import os
import sys
from celery import Celery

# macOS safety for native ML libraries (PyTorch, XGBoost, OpenMP)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
if sys.platform == "darwin":
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

# Tell Celery which Django settings module to use
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("psif_platform")

# Load all Celery config from Django settings, using CELERY_ prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Health-check task — useful for testing the Celery worker is running."""
    print(f"Request: {self.request!r}")
