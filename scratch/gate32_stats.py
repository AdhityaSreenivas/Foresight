import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.incidents.models import Incident, IOGPRuleTag
from django.db.models import Count

total_incidents = Incident.objects.count()
total_tags = IOGPRuleTag.objects.count()
distinct_incidents_tagged = IOGPRuleTag.objects.values('incident').distinct().count()

print(f"Total Incidents: {total_incidents}")
print(f"Total IOGPRuleTags: {total_tags}")
print(f"Distinct Incidents with at least one IOGP Tag: {distinct_incidents_tagged}")
