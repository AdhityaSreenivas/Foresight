import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult

print("Total incidents:", Incident.objects.count())
print("Total predictions:", PredictionResult.objects.count())

for i, p in enumerate(PredictionResult.objects.all()[:20]):
    print(f"[{i}] Incident: {p.incident.description[:30]}...")
    print(f"    psif_probability: {p.psif_probability}")
    print(f"    risk_level: {p.risk_level}")
    print(f"    psif_predicted: {p.psif_predicted}")

