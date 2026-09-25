"""
Comparison of 72 Forensic Sample Incidents: Pre-Deepening (Task 3) vs Post-Deepening (Task 4)
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

def rerun_comparison():
    # 1. Load baseline
    baseline_file = "scripts/deep_dive_results.json"
    with open(baseline_file, "r") as f:
        baseline_data = json.load(f)

    baseline_state_counts = baseline_data["state_counts"]
    baseline_cases = {c["incident_id"]: c for c in baseline_data.get("deep_dive_cases", [])}

    # 2. Sample same 72 incidents
    sampled = sample_diverse_incidents(72)
    print(f"Loaded {len(sampled)} incidents for post-deepening evaluation.")

    post_state_counts = {}
    post_decisions = {}
    transitions = []
    semantic_extraction_stats = {
        "provenance_steps_total": 0,
        "anti_inferences_evaluated_total": 0,
        "temporal_expressions_total": 0,
        "terminology_matches_total": 0,
        "multi_hazard_cases": 0,
    }

    ml_disagreements_pre = 0
    ml_disagreements_post = 0

    detailed_comparisons = []

    for idx, inc in enumerate(sampled, 1):
        assessment = build_incident_reasoning_assessment(inc)
        state = assessment["internal_reasoning_state"]
        dec = assessment["decision"]
        post_state_counts[state] = post_state_counts.get(state, 0) + 1
        post_decisions[str(inc.id)] = {"state": state, "decision": dec}

        # Track semantic extras
        prov = assessment.get("provenance_graph", [])
        semantic_extraction_stats["provenance_steps_total"] += len(prov)

        anti = assessment.get("anti_inferences", [])
        semantic_extraction_stats["anti_inferences_evaluated_total"] += len(anti)

        temp = assessment.get("temporal_expressions", [])
        semantic_extraction_stats["temporal_expressions_total"] += len(temp)

        terms = assessment.get("terminology_matches", [])
        semantic_extraction_stats["terminology_matches_total"] += len(terms)

        multi = assessment.get("multi_hazard", {})
        if multi.get("is_multi_hazard"):
            semantic_extraction_stats["multi_hazard_cases"] += 1

        ml_pred = assessment.get("model_prediction", {}).get("predicted_label")
        if ml_pred is not None:
            if (dec == "PSIF" and ml_pred != 1) or (dec == "NOT_PSIF" and ml_pred != 0):
                ml_disagreements_post += 1

        # Check if in deep dive baseline
        b_case = baseline_cases.get(str(inc.id))
        if b_case:
            b_state = b_case.get("rule_decision") # Note: baseline stored decision or state
            b_ml = b_case.get("ml_prediction")
            if b_ml is not None:
                if (b_case["rule_decision"] == "PSIF" and b_ml != 1) or (b_case["rule_decision"] == "NOT_PSIF" and b_ml != 0):
                    ml_disagreements_pre += 1

            if b_case["rule_decision"] != dec:
                transitions.append({
                    "incident_id": str(inc.id),
                    "desc": inc.description[:80],
                    "before": b_case["rule_decision"],
                    "after": dec,
                    "before_state": b_case.get("hazard_extraction", {}).get("hazard_type"),
                    "after_state": state,
                })

    print("\n--- BASELINE (TASK 3) STATE COUNTS ---")
    print(json.dumps(baseline_state_counts, indent=2))

    print("\n--- POST-DEEPENING (TASK 4) STATE COUNTS ---")
    print(json.dumps(post_state_counts, indent=2))

    print("\n--- STATE COMPARISON ---")
    for st in ["PSIF_PATHWAY_OPEN", "HIGH_ENERGY_CONTROLLED", "INSUFFICIENT_INFORMATION", "LOW_ENERGY", "CONFLICTING_EVIDENCE"]:
        b_cnt = baseline_state_counts.get(st, 0)
        p_cnt = post_state_counts.get(st, 0)
        diff = p_cnt - b_cnt
        diff_str = f"+{diff}" if diff > 0 else f"{diff}"
        print(f"  {st:25s}: Baseline={b_cnt:2d} ({b_cnt/72*100:4.1f}%) -> Post={p_cnt:2d} ({p_cnt/72*100:4.1f}%) [Change: {diff_str}]")

    print("\n--- SEMANTIC REASONING UPGRADES ---")
    for k, v in semantic_extraction_stats.items():
        print(f"  {k:35s}: {v}")

    print(f"\n--- TRANSITIONS IN 28 DEEP-DIVE AUDITED CASES ({len(transitions)}) ---")
    for t in transitions:
        print(f"  Incident {t['incident_id']}: {t['before']} -> {t['after']} ({t['desc']})")

    report_payload = {
        "baseline_state_counts": baseline_state_counts,
        "post_state_counts": post_state_counts,
        "semantic_extraction_stats": semantic_extraction_stats,
        "transitions_count": len(transitions),
        "transitions": transitions,
    }

    with open("scripts/forensic_comparison_task4.json", "w") as f:
        json.dump(report_payload, f, indent=2)
    print("\nComparison report written to scripts/forensic_comparison_task4.json")

if __name__ == "__main__":
    rerun_comparison()
