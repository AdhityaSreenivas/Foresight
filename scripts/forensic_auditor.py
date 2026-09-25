"""
Forensic Validation Script for PSIF Domain Knowledge & Reasoning Engine
Task 3 — Forensic Validation
"""
import os
import sys
import json
import re
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()


from django.db.models import Q
from apps.incidents.models import Incident
from apps.incidents.services.psif_knowledge_base import (
    EnergyHazardType,
    ExposureState,
    ControlState,
    ControlHierarchyType,
    UserFacingDecision,
    InternalReasoningState,
    SOURCE_REGISTRY,
    PSIF_RULES_CATALOG,
)
from apps.incidents.services.psif_reasoning import (
    build_incident_reasoning_assessment,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
    reconcile_prediction_and_rules,
)

def sample_diverse_incidents(target_count=72) -> List[Incident]:
    """
    Selects at least 68 (here 72) prediction-eligible incidents from the DB
    with maximum diversity across domains, hazard families, report types,
    and narrative styles without modifying source records.
    """
    criteria = [
        # Domain categories
        ("drilling", Q(department__icontains="drilling") | Q(job_task__icontains="drilling")),
        ("production", Q(department__icontains="production") | Q(job_task__icontains="production")),
        ("maintenance", Q(department__icontains="maintenance") | Q(job_task__icontains="maintenance")),
        ("lifting", Q(job_task__icontains="lifting") | Q(job_task__icontains="crane") | Q(description__icontains="crane")),
        ("transportation", Q(job_task__icontains="transport") | Q(job_task__icontains="vehicle") | Q(description__icontains="vehicle")),
        ("electrical", Q(job_task__icontains="electrical") | Q(description__icontains="electrical")),
        ("mechanical", Q(job_task__icontains="mechanical") | Q(description__icontains="mechanical")),
        ("pipeline", Q(department__icontains="pipeline") | Q(description__icontains="pipeline")),
        ("confined_space", Q(job_task__icontains="confined") | Q(description__icontains="confined space")),
        ("work_at_height", Q(job_task__icontains="height") | Q(description__icontains="scaffold") | Q(description__icontains="ladder")),
        ("hot_work", Q(job_task__icontains="hot work") | Q(job_task__icontains="welding") | Q(description__icontains="welding")),
        ("pressure", Q(description__icontains="pressure") | Q(description__icontains="flange") | Q(description__icontains="valve")),
        ("isolation", Q(description__icontains="isolation") | Q(description__icontains="lockout") | Q(description__icontains="loto")),
        ("contractor", Q(description__icontains="contractor")),
        ("near_miss", Q(near_miss=True) | Q(description__icontains="near miss")),
        ("unsafe_act", Q(description__icontains="unsafe act")),
        ("unsafe_condition", Q(description__icontains="unsafe condition")),
        # Narrative styles
        ("sparse_narrative", Q(description__regex=r"^.{15,60}$")),
        ("rich_narrative", Q(description__regex=r"^.{250,}$")),
        ("temporal_language", Q(description__icontains="before") | Q(description__icontains="after") | Q(description__icontains="prior to")),
        ("verification_language", Q(description__icontains="verified") | Q(description__icontains="tested") | Q(description__icontains="inspected")),
        ("negative_statements", Q(description__icontains="without") | Q(description__icontains="not") | Q(description__icontains="failed")),
    ]

    selected_ids = set()
    sampled_incidents = []

    for name, q in criteria:
        qs = Incident.objects.filter(q).exclude(id__in=selected_ids).order_by("id")
        count_to_take = 4 if "narrative" in name or "language" in name or "statements" in name else 3
        items = list(qs[:count_to_take])
        for inc in items:
            if inc.id not in selected_ids:
                selected_ids.add(inc.id)
                sampled_incidents.append(inc)

    # Fill up to target_count if needed
    if len(sampled_incidents) < target_count:
        remainder = Incident.objects.exclude(id__in=selected_ids).order_by("id")[:(target_count - len(sampled_incidents))]
        for inc in remainder:
            selected_ids.add(inc.id)
            sampled_incidents.append(inc)

    return sampled_incidents[:target_count]

if __name__ == "__main__":
    sampled = sample_diverse_incidents(72)
    print(f"Sampled {len(sampled)} incidents successfully.")
    for idx, inc in enumerate(sampled[:10], 1):
        print(f"[{idx}] {inc.id} | Dept: {inc.department} | Task: {inc.job_task} | Text: {inc.description[:60]}...")
