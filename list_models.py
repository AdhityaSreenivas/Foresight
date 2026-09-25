import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from apps.predictions.models import ModelVersion

for m in ModelVersion.objects.all().order_by('-trained_at'):
    print(f"ID: {m.id}, Label: {m.version_label}, Active: {m.is_active}, Path: {m.xgboost_artifact_path}")

