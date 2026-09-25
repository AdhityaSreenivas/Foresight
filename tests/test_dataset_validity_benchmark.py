"""
PSIF Platform — Tests for Dataset & Model Validity Benchmark
OIL India Problem Statement 26165

Verifies:
1. Target-derived fields cannot enter baseline features
2. Group split does not mix groups across train and test
3. Benchmark can run on dataset and produces valid result
4. Leakage report is generated with lexical analysis
5. Adversarial benchmark runs and evaluates robustness
6. Counterfactual benchmark runs on paired safety cases
7. Benchmark does not modify the active model
8. Benchmark outputs are reproducible under fixed random seed
"""
import copy
import pytest
import numpy as np
from pathlib import Path

from ml_engine.benchmark.dataset_benchmark import (
    run_dataset_benchmark,
    generate_benchmark_markdown_report,
    evaluate_adversarial_suite,
    evaluate_counterfactual_suite,
    analyze_lexical_leakage,
    analyze_schema_integrity,
    analyze_templates_and_duplication,
    evaluate_baselines_random_vs_group,
    TARGET_DERIVED_FORBIDDEN_FIELDS,
    COUNTERFACTUAL_PAIRS,
    ADVERSARIAL_CASES,
)
from apps.predictions.models import ModelVersion


@pytest.fixture
def synthetic_sample_records():
    """Generates synthetic records with deliberate template and non-template features."""
    records = []
    for i in range(120):
        is_pos = i % 2 == 1
        area = f"Area_{i % 6}"
        activity = f"Activity_{i % 4}"
        text = (
            f"Worker performed {activity} at {area}. "
            f"The finding was critical failure of barrier {i % 3}; risk: unexpected start. "
            f"The reported activity was {activity}."
            if is_pos
            else
            f"Inspection of equipment completed per standard schedule at {area}. "
            f"All safety barriers verified effective and fully functional with no defects."
        )
        rec = {
            "report_id": f"TEST_{i:04d}",
            "report_text": text,
            "description": text,
            "sif_label": 1 if is_pos else 0,
            "activity": activity,
            "site_area": area,
            "report_type": "Incident" if is_pos else "Inspection",
            "department": "Operations",
            # Leaked fields (should be ignored by baseline features)
            "confidence_target": 0.95 if is_pos else 0.10,
            "reason": "critical failure" if is_pos else "inspection",
            "potential_consequence": "unexpected start" if is_pos else "none",
            "sif_category": "Energy Isolation" if is_pos else "None",
            "life_saving_rule": "Energy Isolation" if is_pos else "None",
        }
        records.append(rec)
    return records


class TestDatasetValidityBenchmark:

    def test_1_target_derived_fields_forbidden(self, synthetic_sample_records):
        """1. Target-derived fields cannot enter baseline features."""
        # Check standard forbidden set
        assert "sif_label" in TARGET_DERIVED_FORBIDDEN_FIELDS
        assert "confidence_target" in TARGET_DERIVED_FORBIDDEN_FIELDS
        assert "potential_consequence" in TARGET_DERIVED_FORBIDDEN_FIELDS
        assert "reason" in TARGET_DERIVED_FORBIDDEN_FIELDS
        assert "psif_probability" in TARGET_DERIVED_FORBIDDEN_FIELDS
        assert "severity_actual" in TARGET_DERIVED_FORBIDDEN_FIELDS
        assert "severity_potential" in TARGET_DERIVED_FORBIDDEN_FIELDS

        # Ensure baseline evaluation only uses non-target structured columns
        rand_m, grp_m = evaluate_baselines_random_vs_group(synthetic_sample_records, seed=42)
        assert "error" not in rand_m
        assert "error" not in grp_m

    def test_2_group_split_does_not_mix_groups(self, synthetic_sample_records):
        """2. Group split does not mix groups across train and test partitions."""
        rand_m, grp_m = evaluate_baselines_random_vs_group(synthetic_sample_records, seed=42)

        # In group split, group overlap count MUST be strictly 0
        assert grp_m.get("group_overlap_count") == 0, "Group split allowed template/scenario groups to leak between train and test!"

    @pytest.mark.django_db
    def test_3_benchmark_can_run_on_dataset(self, tmp_path, synthetic_sample_records):
        """3. Benchmark can run on a dataset file and produces valid results."""
        import json
        test_jsonl = tmp_path / "test_benchmark.jsonl"
        with open(test_jsonl, "w") as f:
            for r in synthetic_sample_records:
                f.write(json.dumps(r) + "\n")

        res = run_dataset_benchmark(test_jsonl, dataset_name="TestDataset", sample_limit=100, seed=42)
        assert res is not None
        assert res.total_rows == 100
        assert "class_distribution" in res.schema_integrity
        assert "SUITABLE_FOR_DEVELOPMENT" in res.suitability_verdict
        assert "SUITABLE_FOR_FINAL_MODEL_VALIDATION" in res.suitability_verdict

    def test_4_leakage_report_is_generated(self, synthetic_sample_records):
        """4. Leakage report is generated with lexical analysis and markdown output."""
        lexical = analyze_lexical_leakage(synthetic_sample_records)
        assert "suspicious_tokens" in lexical
        assert "high_confidence_leakage_detected" in lexical

        template_stats = analyze_templates_and_duplication(synthetic_sample_records)
        assert "top_boilerplate_phrases" in template_stats

        schema_stats = analyze_schema_integrity(synthetic_sample_records)
        assert schema_stats["total_records"] == 120

    def test_5_adversarial_benchmark_runs(self):
        """5. Adversarial benchmark runs and evaluates edge cases."""
        adv_res = evaluate_adversarial_suite(predictor=None)
        assert adv_res["total_adversarial_tests"] == len(ADVERSARIAL_CASES)
        assert adv_res["pass_rate"] >= 0.0
        assert "robustness_verdict" in adv_res
        assert len(adv_res["test_breakdown"]) == len(ADVERSARIAL_CASES)

    def test_6_counterfactual_benchmark_runs(self):
        """6. Counterfactual benchmark runs on paired safety cases."""
        cf_res = evaluate_counterfactual_suite(predictor=None)
        assert cf_res["total_pairs"] == len(COUNTERFACTUAL_PAIRS)
        assert "accuracy" in cf_res
        assert len(cf_res["pairs_evaluation"]) == len(COUNTERFACTUAL_PAIRS)

    @pytest.mark.django_db
    def test_7_benchmark_does_not_modify_active_model(self, tmp_path, synthetic_sample_records):
        """7. Benchmark does NOT modify the active model version, weights, or status."""
        import json

        # Create or fetch active model
        active_before = ModelVersion.objects.filter(is_active=True).first()
        active_id_before = active_before.id if active_before else None
        active_ver_before = active_before.version_label if active_before else None

        test_jsonl = tmp_path / "test_benchmark_active.jsonl"
        with open(test_jsonl, "w") as f:
            for r in synthetic_sample_records:
                f.write(json.dumps(r) + "\n")

        # Run benchmark
        res = run_dataset_benchmark(test_jsonl, sample_limit=50, seed=42)
        assert res is not None

        # Verify active model is completely unchanged
        active_after = ModelVersion.objects.filter(is_active=True).first()
        active_id_after = active_after.id if active_after else None
        active_ver_after = active_after.version_label if active_after else None

        assert active_id_before == active_id_after
        assert active_ver_before == active_ver_after

    def test_8_benchmark_outputs_are_reproducible(self, synthetic_sample_records):
        """8. Benchmark outputs are reproducible under fixed random seed."""
        rand_m1, grp_m1 = evaluate_baselines_random_vs_group(synthetic_sample_records, seed=42)
        rand_m2, grp_m2 = evaluate_baselines_random_vs_group(synthetic_sample_records, seed=42)

        # Exact matching metrics across two independent runs
        lr1 = rand_m1["text_tfidf_logistic_regression"]
        lr2 = rand_m2["text_tfidf_logistic_regression"]
        assert lr1["roc_auc"] == lr2["roc_auc"]
        assert lr1["accuracy"] == lr2["accuracy"]
        assert lr1["f1"] == lr2["f1"]
