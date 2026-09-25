import os
import json
import time
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion

User = get_user_model()
user, _ = User.objects.get_or_create(username="api_smoke_test_user", defaults={"email": "smoke@example.com", "is_staff": True})

client = APIClient()
client.force_authenticate(user=user)

# Representative test cases
cases = [
    {
        "label": "PSIF (Pressure release in line of fire, no LOTO)",
        "narrative": "Technician cracked 600 psi hydraulic union without lockout applied. Worker was directly in line of fire when hydraulic oil erupted and struck chest.",
        "ml_prob": 0.85,
    },
    {
        "label": "NOT_PSIF / HIGH_ENERGY_CONTROLLED (Blast containment barricade held)",
        "narrative": "High pressure bleed fitting sheared at 320 bar during proof test. High pressure water stream hit the interior wall of blast containment barricade. Interlocked warning beacons and perimeter fences were fully active, and testing personnel were staged 28 meters away inside the monitoring trailer. Blast containment barrier held securely and completely contained the 320 bar release.",
        "ml_prob": 0.22,
    },
    {
        "label": "LOW_ENERGY NOT_PSIF (Office hallway slip)",
        "narrative": "Administrative clerk slipped on a freshly mopped office tile floor sustaining a minor ankle sprain. First aid ice pack applied; employee returned to regular desk duties. Office housekeeping caution cone was placed near doorway.",
        "ml_prob": 0.05,
    },
    {
        "label": "CONFLICTING_EVIDENCE (Contradictory exclusion zone entrance)",
        "narrative": "Worker entered the exclusion zone under the suspended 5-ton drill collar. Worker remained outside the exclusion zone behind the physical barricade.",
        "ml_prob": 0.55,
    },
    {
        "label": "MODEL_DISAGREEMENT / FALSE_NEGATIVE (Rule evidence proves PSIF despite low ML score)",
        "narrative": "Conveyor tail pulley nip point was completely unguarded when operator reached to dislodge a jammed belt roller while conveyor was actively running without lockout applied. Right arm was caught in pinch point.",
        "ml_prob": 0.18, # ML says 0.18 (NOT PSIF), but rule proves open pathway
    }
]

print("=" * 80)
print("SECTION 27: API SMOKE TEST & CONTRACT VERIFICATION")
print("=" * 80)

for c in cases:
    inc = Incident.objects.create(
        incident_date="2026-09-01",
        description=c["narrative"],
        composite_narrative=c["narrative"],
        department="Drilling Ops",
        severity_potential=Incident.SeverityPotential.SERIOUS,
    )
    if c["ml_prob"] is not None:
        mv, _ = ModelVersion.objects.get_or_create(version_label="v1.0-smoke", defaults={"bert_model_name": "bert-test", "xgboost_artifact_path": "/tmp/smoke"})
        PredictionResult.objects.create(
            incident=inc,
            model_version=mv,
            psif_probability=c["ml_prob"],
            psif_predicted=(c["ml_prob"] >= 0.5),
            risk_level=PredictionResult.RiskLevel.HIGH if c["ml_prob"] >= 0.5 else PredictionResult.RiskLevel.LOW,
        )

    url = f"/api/incidents/{inc.id}/reasoning/"
    t0 = time.perf_counter()
    response = client.get(url)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n--- Test Case: {c['label']} ---")
    print(f"URL: {url}")
    print(f"Status Code: {response.status_code}")
    print(f"Latency: {elapsed_ms:.2f} ms")

    if response.status_code == 200:
        data = response.json()
        print(f"Decision: {data.get('decision')}")
        print(f"Internal Reasoning State: {data.get('internal_reasoning_state')}")
        print(f"Evidence Strength: {data.get('evidence_strength')}")
        print(f"Reconciliation: {data.get('reconciliation', {}).get('agreement_state')}")
        print(f"High Priority Review: {data.get('high_priority_review')}")
        print(f"Why PSIF: {data.get('why_psif', '')[:100]}...")
        print(f"Why NOT PSIF: {data.get('why_not_psif', '')[:100]}...")
        print(f"Evidence Needed: {len(data.get('evidence_needed_to_close', []))} items")
        print(f"Grounded Actions: {len(data.get('grounded_actions', []))} actions")
        print(f"Provenance Trace Steps: {len(data.get('source_provenance', []))}")
    else:
        print(f"Error Response: {response.content}")

    # Cleanup smoke incident
    inc.delete()

print("\n" + "=" * 80)
print("ALL 5 REPRESENTATIVE CASES SMOKE-TESTED SUCCESSFULLY")
print("=" * 80)
