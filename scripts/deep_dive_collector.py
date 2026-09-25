"""
Collector script for 17-point deep dive on sampled incident cases.
Generates comprehensive structured results for PSIF_REASONING_FORENSIC_VALIDATION_V2.md.
"""
import os
import sys
import json
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.incidents.models import Incident
from apps.incidents.services.psif_knowledge_base import (
    EnergyHazardType,
    ExposureState,
    ControlState,
    ControlHierarchyType,
    UserFacingDecision,
    InternalReasoningState,
)
from apps.incidents.services.psif_reasoning import (
    build_incident_reasoning_assessment,
    extract_incident_safety_evidence,
    evaluate_psif_rules,
)
from apps.incidents.services.normalization import normalize_incident_entities
from scripts.forensic_auditor import sample_diverse_incidents

def run_deep_dive_audit():
    sampled = sample_diverse_incidents(72)
    print(f"Total sampled incidents: {len(sampled)}")

    results = []
    category_counts = {}
    state_counts = {}

    for idx, inc in enumerate(sampled, 1):
        assessment = build_incident_reasoning_assessment(inc)
        evidence = extract_incident_safety_evidence(inc)
        norm_entities = normalize_incident_entities(inc)

        state = assessment["internal_reasoning_state"]
        dec = assessment["decision"]
        state_counts[state] = state_counts.get(state, 0) + 1

        dept = inc.department or "Unspecified"
        category_counts[dept] = category_counts.get(dept, 0) + 1

        # Deep dive on first 28 cases
        if idx <= 28:
            results.append({
                "case_num": idx,
                "incident_id": str(inc.id),
                "raw_narrative": inc.description,
                "structured_fields": {
                    "department": inc.department,
                    "job_task": inc.job_task,
                    "energy_type": inc.energy_type,
                    "control_condition": inc.control_condition,
                    "injury_type": inc.injury_type,
                    "body_part": inc.body_part,
                    "near_miss": inc.near_miss,
                },
                "normalized_concepts": {
                    "energy": norm_entities.get("energy_source").canonical_value if norm_entities.get("energy_source") else None,
                    "control": norm_entities.get("control_type").canonical_value if norm_entities.get("control_type") else None,
                    "control_condition": norm_entities.get("control_condition").canonical_value if norm_entities.get("control_condition") else None,
                },
                "hazard_extraction": {
                    "hazard_type": evidence["hazard"].hazard_type,
                    "energy_present": evidence["hazard"].energy_present,
                    "evidence_text": evidence["hazard"].evidence_text,
                    "source": evidence["hazard"].source_field,
                },
                "exposure_extraction": {
                    "state": evidence["exposure"].state,
                    "evidence_text": evidence["exposure"].evidence_text,
                    "worker_present": evidence["exposure"].worker_present,
                },
                "control_extraction": {
                    "type": evidence["control"].control_type,
                    "hierarchy": evidence["control"].hierarchy_type,
                    "is_direct": evidence["control"].is_direct_control,
                    "is_compromised": evidence["control"].is_compromised,
                    "evidence_text": evidence["control"].evidence_text,
                },
                "control_state": evidence["control"].state,
                "consequence_pathway": {
                    "state": evidence["consequence"].pathway_state,
                    "mechanism": evidence["consequence"].mechanism,
                    "physical_mechanism": evidence["consequence"].physical_mechanism,
                },
                "iogp_matches": evidence["matched_iogp_rules"],
                "reasoning_matrix": assessment["evidence_matrix"],
                "rule_decision": assessment["decision"],
                "ml_prediction": assessment.get("model_prediction", {}).get("predicted_label"),
                "ml_score": assessment.get("model_prediction", {}).get("probability"),
                "reconciliation": assessment.get("reconciliation", {}),
                "policy_decision": assessment["decision"],
                "explanation": assessment["what_is_known"],
                "actions": assessment["action_interface"],
            })

    output_path = "/Users/sas/Developer/prototype_165/scripts/deep_dive_results.json"
    with open(output_path, "w") as f:
        json.dump({
            "total_sampled": len(sampled),
            "state_counts": state_counts,
            "category_counts": category_counts,
            "deep_dive_cases": results,
        }, f, indent=2)

    print(f"Deep dive results written to {output_path}")
    print(f"State breakdown across 72 sampled: {state_counts}")

if __name__ == "__main__":
    run_deep_dive_audit()
