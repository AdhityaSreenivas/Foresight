import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.services import ADMIN_FLOW_WORKSPACE, get_admin_flow_barrier_portfolio_data

mv = ModelVersion.objects.filter(is_active=True).first()
if not mv:
    mv = ModelVersion.objects.create(version_label="v_demo_active", is_active=True)

# 1. Energy Isolation Incident
inc_ei, _ = Incident.objects.get_or_create(
    workspace_id=ADMIN_FLOW_WORKSPACE,
    description="High pressure nitrogen header depressurization without positive mechanical isolation (LOTO).",
    defaults={
        "location": "Compressor Station B",
        "job_task": "Pipeline De-inventorying",
        "control_condition": "bypassed",
    }
)
PredictionResult.objects.get_or_create(
    incident=inc_ei,
    defaults={
        "model_version": mv,
        "psif_probability": 0.84,
        "psif_predicted": True,
        "risk_level": "critical",
        "is_sparse_input": False,
    }
)
IOGPRuleTag.objects.get_or_create(incident=inc_ei, rule="Energy Isolation")

# 2. Working at Height Incident
inc_wah, _ = Incident.objects.get_or_create(
    workspace_id=ADMIN_FLOW_WORKSPACE,
    description="Rig floor monkey board latch failed at 25m height during casing run.",
    defaults={
        "location": "Drill Floor Deck",
        "job_task": "Casing Operations",
        "control_condition": "failed",
    }
)
PredictionResult.objects.get_or_create(
    incident=inc_wah,
    defaults={
        "model_version": mv,
        "psif_probability": 0.91,
        "psif_predicted": True,
        "risk_level": "critical",
        "is_sparse_input": False,
    }
)
IOGPRuleTag.objects.get_or_create(incident=inc_wah, rule="Working at Height")

# Invalidate cache
data = get_admin_flow_barrier_portfolio_data(use_cache=False)
print("Populated demo records. Total analyzed:", data["total_analyzed_incidents"])
print("Rules summary:")
for r in data["rules"]:
    if r["matched_observations"] > 0:
        print(f" - {r['rule']}: {r['matched_observations']} matched, {r['psif_linked_observations']} PSIF, location: {r['top_location']}")
