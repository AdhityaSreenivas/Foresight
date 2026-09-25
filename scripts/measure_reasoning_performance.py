import time
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.incidents.models import Incident
from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment

incidents = list(Incident.objects.select_related("prediction", "prediction__model_version", "data_quality").prefetch_related("iogp_rules", "reviews")[:10])

print(f"Loaded {len(incidents)} incidents for performance measurement.")

durations = []
query_counts = []

for inc in incidents:
    pred = getattr(inc, "prediction", None)
    dq = getattr(inc, "data_quality", None)
    with CaptureQueriesContext(connection) as ctx:
        t0 = time.perf_counter()
        res = build_incident_reasoning_assessment(inc, prediction=pred, dq_record=dq)
        dur = (time.perf_counter() - t0) * 1000.0
        durations.append(dur)
        query_counts.append(len(ctx.captured_queries))

avg_dur = sum(durations) / len(durations) if durations else 0
max_dur = max(durations) if durations else 0
min_dur = min(durations) if durations else 0
avg_q = sum(query_counts) / len(query_counts) if query_counts else 0

print(f"Performance Stats over {len(incidents)} incidents:")
print(f"  Average execution time: {avg_dur:.2f} ms (Min: {min_dur:.2f} ms, Max: {max_dur:.2f} ms)")
print(f"  Queries executed per incident: {avg_q} queries")
for i, inc in enumerate(incidents[:5]):
    print(f"  Incident {i+1} ({inc.id}): {durations[i]:.2f} ms, {query_counts[i]} DB queries")
