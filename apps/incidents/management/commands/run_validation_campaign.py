"""
Management command to run the HSE validation campaign on the sampled cohort.
"""

from django.core.management.base import BaseCommand
import json

from apps.incidents.services.sampling import sample_validation_cohort
from apps.incidents.services.evaluation import (
    record_dual_review_campaign,
    compute_inter_rater_agreement,
    compute_model_vs_human_metrics,
    compute_score_distribution_by_human_class,
    compute_threshold_sweep,
    compute_synthetic_vs_human_agreement,
)


class Command(BaseCommand):
    help = "Run the dual-reviewer validation campaign, compute inter-rater agreement, model metrics, and threshold sweeps."

    def add_arguments(self, parser):
        parser.add_argument("--target-size", type=int, default=150, help="Cohort size (default: 150)")
        parser.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42)")

    def handle(self, *args, **options):
        target_size = options["target_size"]
        seed = options["seed"]

        self.stdout.write(f"Sampling cohort (N={target_size}, seed={seed})...")
        cohort, sample_meta = sample_validation_cohort(target_size=target_size, seed=seed)
        self.stdout.write(self.style.SUCCESS(f"Sampled {len(cohort)} incidents."))

        self.stdout.write("Recording dual-reviewer campaign with HSE 6-point rubric...")
        campaign_meta = record_dual_review_campaign(cohort)
        self.stdout.write(self.style.SUCCESS(f"Recorded {campaign_meta['total_reviews_created']} reviews."))

        self.stdout.write("Computing inter-rater agreement...")
        agreement = compute_inter_rater_agreement(cohort)

        self.stdout.write("Computing model vs human evaluation metrics (threshold=0.10)...")
        model_metrics = compute_model_vs_human_metrics(cohort, threshold=0.10)

        self.stdout.write("Computing score distributions by human decision...")
        distributions = compute_score_distribution_by_human_class(cohort)

        self.stdout.write("Executing threshold sensitivity sweep (0.05 to 0.80)...")
        sweep = compute_threshold_sweep(cohort)

        self.stdout.write("Comparing synthetic benchmark labels vs human ground truth...")
        synthetic_comp = compute_synthetic_vs_human_agreement(cohort)

        results = {
            "sampling_metadata": sample_meta,
            "campaign_metadata": campaign_meta,
            "inter_rater_agreement": agreement,
            "model_vs_human_active_threshold": model_metrics,
            "score_distributions": distributions,
            "threshold_sweep": sweep,
            "synthetic_vs_human": synthetic_comp,
        }

        self.stdout.write(self.style.SUCCESS("\n================ VALIDATION CAMPAIGN SUMMARY ================"))
        self.stdout.write(f"Total Reviewed Incidents: {len(cohort)}")
        self.stdout.write(f"Inter-Rater Raw Agreement: {agreement['raw_agreement_percentage']}% (Cohen's Kappa: {agreement['cohens_kappa']} - {agreement['kappa_interpretation']})")
        self.stdout.write(f"Model at 0.10: Precision={model_metrics['precision']:.4f}, Recall={model_metrics['recall']:.4f}, F1={model_metrics['f1_score']:.4f}, FN={model_metrics['false_negative_count']}")
        self.stdout.write(f"Synthetic vs Human Agreement: {synthetic_comp['agreement_percentage']}%")
        self.stdout.write(self.style.SUCCESS("============================================================\n"))

        return json.dumps(results, indent=2)
