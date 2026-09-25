import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()
from apps.predictions.models import ModelVersion

active = ModelVersion.objects.filter(is_active=True).first()
if active:
    print("Active:", active.version_label, active.artifact_path)
else:
    print("No active model")
