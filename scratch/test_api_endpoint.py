import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(role="admin").first()
client = Client()
client.force_login(user)

payload1 = {
    "description": "Slip and fall",
    "severity_actual": "first_aid",
    "severity_potential": "low",
    "department": "Maintenance"
}

payload2 = {
    "description": "Explosion with fatality",
    "severity_actual": "fatality",
    "severity_potential": "fatality",
    "department": "Operations"
}

r1 = client.post("/api/predict/", data=payload1, content_type="application/json")
print("R1:", r1.json())

r2 = client.post("/api/predict/", data=payload2, content_type="application/json")
print("R2:", r2.json())
