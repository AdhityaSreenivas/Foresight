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

payload = {
    "description": "Test",
    "severity_actual": "",
    "severity_potential": "",
    "department": ""
}

r1 = client.post("/api/predict/", data=payload, content_type="application/json")
print("R1:", r1.json())
