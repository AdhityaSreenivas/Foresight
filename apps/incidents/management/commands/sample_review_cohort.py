"""
Management command to sample a representative HSE validation cohort.
"""

from django.core.management.base import BaseCommand
import json

from apps.incidents.services.sampling import (
    DEFAULT_DATASET_ID,
    DEFAULT_TARGET_SIZE,
    DEFAULT_SEED,
    sample_validation_cohort,
)


class Command(BaseCommand):
    help = "Sample a representative, deduplicated, quota-filled validation cohort from the dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset-id",
            type=str,
            default=DEFAULT_DATASET_ID,
            help="Dataset UUID to sample from",
        )
        parser.add_argument(
            "--target-size",
            type=int,
            default=DEFAULT_TARGET_SIZE,
            help="Exact target size for validation cohort (default: 150)",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=DEFAULT_SEED,
            help="Deterministic RNG seed (default: 42)",
        )

    def handle(self, *args, **options):
        dataset_id = options["dataset_id"]
        target_size = options["target_size"]
        seed = options["seed"]

        self.stdout.write(f"Sampling validation cohort: dataset={dataset_id}, target={target_size}, seed={seed}")

        cohort, metadata = sample_validation_cohort(
            dataset_id=dataset_id,
            target_size=target_size,
            seed=seed,
        )

        self.stdout.write(self.style.SUCCESS(f"Selected exactly {len(cohort)} incidents."))
        self.stdout.write(json.dumps(metadata, indent=2))
