#!/usr/bin/env python
"""
Verification script for 50,000 dataset remediation.
Computes all post-fix PostgreSQL metrics, score distributions, percentiles,
and cross-tabulations.
"""
import os
import sys
import django
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult

DATASET_ID = "182250b2-dd76-4506-826a-dd6da0c457a3"

def main():
    print("==================================================")
    print("50,000 DATASET REMEDIATION VERIFICATION")
    print("==================================================")

    # 1. Overall Incident Counts
    total_all_incidents = Incident.objects.count()
    dataset_incidents_qs = Incident.objects.filter(dataset_id=DATASET_ID)
    total_dataset_incidents = dataset_incidents_qs.count()

    print(f"Total Incidents (all datasets): {total_all_incidents}")
    print(f"Dataset Incidents ({DATASET_ID}): {total_dataset_incidents}")

    # 2. Human Review Fields Guard
    human_labeled_count = dataset_incidents_qs.filter(is_psif_human_label__isnull=False).count()
    human_rationale_count = dataset_incidents_qs.filter(reviewer_rationale__isnull=False).exclude(reviewer_rationale="").count()
    human_reviewed_by_count = dataset_incidents_qs.filter(reviewed_by__isnull=False).count()
    human_reviewed_at_count = dataset_incidents_qs.filter(reviewed_at__isnull=False).count()

    print(f"\n--- Human Review Ground Truth Integrity ---")
    print(f"Incidents with is_psif_human_label != NULL: {human_labeled_count}")
    print(f"Incidents with reviewer_rationale != NULL/empty: {human_rationale_count}")
    print(f"Incidents with reviewed_by != NULL: {human_reviewed_by_count}")
    print(f"Incidents with reviewed_at != NULL: {human_reviewed_at_count}")

    # 3. Prediction Results for Dataset
    preds_qs = PredictionResult.objects.filter(incident__dataset_id=DATASET_ID)
    total_preds = preds_qs.count()

    sparse_preds = preds_qs.filter(is_sparse_input=True)
    sparse_count = sparse_preds.count()

    eligible_preds = preds_qs.filter(is_sparse_input=False)
    eligible_count = eligible_preds.count()

    psif_count = eligible_preds.filter(psif_predicted=True).count()
    not_psif_count = eligible_preds.filter(psif_predicted=False).count()

    print(f"\n--- Prediction Results (Dataset {DATASET_ID}) ---")
    print(f"Total Predictions: {total_preds}")
    print(f"Prediction Eligible (Non-Sparse): {eligible_count} ({eligible_count/total_preds*100:.2f}%)")
    print(f"Insufficient Evidence (Sparse < 10 words): {sparse_count} ({sparse_count/total_preds*100:.2f}%)")
    print(f"PSIF Candidates (threshold=0.10): {psif_count} ({psif_count/eligible_count*100:.2f}% of eligible)")
    print(f"NOT PSIF (threshold=0.10): {not_psif_count} ({not_psif_count/eligible_count*100:.2f}% of eligible)")

    # 4. Score Distribution on Eligible Predictions
    print(f"\n--- Score Distribution on Eligible Predictions (N={eligible_count}) ---")
    probs = np.array(list(eligible_preds.values_list('psif_probability', flat=True)), dtype=float)

    if len(probs) > 0:
        percentiles = [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]
        pct_values = np.percentile(probs, percentiles)
        print("Percentile Distribution:")
        for p, val in zip(percentiles, pct_values):
            label = "Min" if p == 0 else ("Max" if p == 100 else f"p{p:02d}")
            print(f"  {label:5s}: {val:.4f}")

        print(f"\nMean: {np.mean(probs):.4f} | Std: {np.std(probs):.4f}")

        # Threshold sensitivity table
        thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60, 0.70, 0.80, 0.90]
        print("\nThreshold Sensitivity Analysis:")
        print(f"  {'Threshold':>10s} | {'Count >= Thresh':>15s} | {'% of Eligible':>14s}")
        print("  " + "-" * 45)
        for t in thresholds:
            cnt = np.sum(probs >= t)
            pct = cnt / len(probs) * 100
            print(f"  {t:10.2f} | {cnt:15d} | {pct:13.2f}%")

    # 5. Model Versions in Use
    versions = list(preds_qs.values('model_version').annotate(c=django.db.models.Count('id')))
    print(f"\n--- Active Model Versions ---")
    for v in versions:
        print(f"  Version: {v['model_version']} | Count: {v['c']}")

    print("\n==================================================")
    print("VERIFICATION COMPLETE")
    print("==================================================")

if __name__ == "__main__":
    main()
