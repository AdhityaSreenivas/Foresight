import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()
from apps.predictions.models import ModelVersion
from ml_engine.model_inference import get_active_predictor

predictor = get_active_predictor()
if predictor:
    rec1 = dict(description="Slip and fall", severity_actual="first_aid", near_miss=False)
    rec2 = dict(description="Explosion with fatal outcome", severity_actual="fatality", near_miss=True)
    p1 = predictor.predict(rec1)
    p2 = predictor.predict(rec2)
    print(f"P1: {p1.psif_probability}, P2: {p2.psif_probability}")
else:
    print("No predictor active")
