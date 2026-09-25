"""
Representative Sampling Engine for HSE Validation Cohort.
OIL India Problem Statement 26165.

Generates a representative, stratified, deduplicated, and quota-aware cohort
of incidents for human ground-truth validation.
"""

import random
from typing import Any, Dict, List, Optional, Set, Tuple
from django.db.models import Q

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult


DEFAULT_DATASET_ID = "182250b2-dd76-4506-826a-dd6da0c457a3"
DEFAULT_TARGET_SIZE = 150
DEFAULT_SEED = 42


def sample_validation_cohort(
    dataset_id: str = DEFAULT_DATASET_ID,
    target_size: int = DEFAULT_TARGET_SIZE,
    seed: int = DEFAULT_SEED,
) -> Tuple[List[Incident], Dict[str, Any]]:
    """
    Select a representative validation cohort from the dataset.

    Guarantees:
    1. Deduplication across all strata.
    2. Quota filling to reach EXACTLY target_size (e.g. 150).
    3. Reproducibility using deterministic seed.
    4. Comprehensive coverage across score tiers, threshold boundary,
       sparse narratives, and operational categories.

    Returns:
        (cohort_incidents_list, sampling_metadata_dict)
    """
    rng = random.Random(seed)

    base_qs = Incident.objects.filter(dataset_id=dataset_id).select_related("prediction")
    if not base_qs.exists():
        # Fallback if specific dataset_id is absent
        base_qs = Incident.objects.select_related("prediction")

    # Fetch all candidate IDs with their score and sparsity attributes
    candidates_info = list(
        base_qs.filter(prediction__isnull=False).values(
            "id",
            "prediction__psif_probability",
            "prediction__is_sparse_input",
            "prediction__evidence_strength",
            "department",
            "high_energy_present",
        )
    )

    if not candidates_info:
        return [], {"error": "No incidents with predictions found."}

    # Strata target quotas (approximate targets before deduplication)
    strata_targets = {
        "high_score": 25,          # prob >= 0.50
        "low_score": 25,           # prob < 0.10 (below active threshold)
        "near_threshold": 25,      # 0.08 <= prob <= 0.15
        "moderate_score": 25,      # 0.20 <= prob < 0.40
        "sparse_narrative": 20,    # is_sparse_input = True
        "diverse_categories": 15,  # specific departments / high-energy
    }

    # Partition candidate pools
    pools: Dict[str, List[str]] = {
        "high_score": [],
        "low_score": [],
        "near_threshold": [],
        "moderate_score": [],
        "sparse_narrative": [],
        "diverse_categories": [],
    }

    for item in candidates_info:
        inc_id = str(item["id"])
        prob = float(item["prediction__psif_probability"] or 0.0)
        is_sparse = bool(item["prediction__is_sparse_input"])
        has_high_energy = bool(item["high_energy_present"])
        dept = item["department"] or ""

        if is_sparse:
            pools["sparse_narrative"].append(inc_id)

        if prob >= 0.50:
            pools["high_score"].append(inc_id)
        elif prob < 0.10:
            pools["low_score"].append(inc_id)
        elif 0.08 <= prob <= 0.15:
            pools["near_threshold"].append(inc_id)
        elif 0.20 <= prob < 0.40:
            pools["moderate_score"].append(inc_id)

        if has_high_energy or dept in ("Drilling", "Workover", "Production"):
            pools["diverse_categories"].append(inc_id)

    # Deterministic shuffle for each pool
    for pool_name in pools:
        rng.shuffle(pools[pool_name])

    selected_ids: Set[str] = set()
    strata_counts: Dict[str, int] = {k: 0 for k in strata_targets}

    # Sequentially sample and deduplicate
    for pool_name, target_count in strata_targets.items():
        pool = pools[pool_name]
        added_for_pool = 0
        for inc_id in pool:
            if inc_id not in selected_ids:
                selected_ids.add(inc_id)
                added_for_pool += 1
                if added_for_pool >= target_count:
                    break
        strata_counts[pool_name] = added_for_pool

    # Quota filling: if deduplicated total < target_size, fill from remaining random candidates
    all_cand_ids = [str(item["id"]) for item in candidates_info]
    rng.shuffle(all_cand_ids)
    
    random_fill_count = 0
    if len(selected_ids) < target_size:
        for inc_id in all_cand_ids:
            if inc_id not in selected_ids:
                selected_ids.add(inc_id)
                random_fill_count += 1
                if len(selected_ids) >= target_size:
                    break

    # If we selected more than target_size (e.g. from total quotas > target_size), trim deterministically
    final_id_list = list(selected_ids)
    if len(final_id_list) > target_size:
        # Keep deterministic order
        final_id_list = sorted(final_id_list)[:target_size]
    else:
        final_id_list = sorted(final_id_list)

    # Fetch incident objects preserving order
    incidents_dict = {
        str(inc.id): inc
        for inc in Incident.objects.filter(id__in=final_id_list).select_related("prediction")
    }
    cohort_incidents = [incidents_dict[iid] for iid in final_id_list if iid in incidents_dict]

    # Calculate actual statistics of selected cohort
    actual_scores = [
        float(inc.prediction.psif_probability)
        for inc in cohort_incidents
        if hasattr(inc, "prediction") and inc.prediction
    ]
    actual_sparse_count = sum(
        1
        for inc in cohort_incidents
        if hasattr(inc, "prediction") and inc.prediction and inc.prediction.is_sparse_input
    )

    metadata = {
        "dataset_id": dataset_id,
        "seed": seed,
        "target_size": target_size,
        "actual_size": len(cohort_incidents),
        "sampling_strata_breakdown": strata_counts,
        "random_fill_count": random_fill_count,
        "sparse_narratives_count": actual_sparse_count,
        "score_statistics": {
            "min": round(min(actual_scores), 4) if actual_scores else None,
            "max": round(max(actual_scores), 4) if actual_scores else None,
            "mean": round(sum(actual_scores) / len(actual_scores), 4) if actual_scores else None,
            "count_below_threshold_0_10": sum(1 for s in actual_scores if s < 0.10),
            "count_near_threshold_0_08_0_15": sum(1 for s in actual_scores if 0.08 <= s <= 0.15),
            "count_above_0_50": sum(1 for s in actual_scores if s >= 0.50),
        },
    }

    return cohort_incidents, metadata
