"""
PSIF Platform — seed_model_versions management command

Registers the canonical repository model versions into the ModelVersion table:
- v_20260906_202052: Active benchmark model (F2-optimal threshold 0.20, 856-dim fused representation, trained on 150,582 records)
- v_20260902_122321: Historical audit baseline model (threshold 0.10)

Idempotent: updates existing versions if already present, ensuring exactly ONE model is active.
"""
import json
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.predictions.models import ModelVersion

logger = logging.getLogger(__name__)

CANONICAL_VERSIONS = [
    {
        "version_label": "v_20260906_202052",
        "bert_model_name": "distilbert-base-uncased",
        "relative_artifact_dir": "ml_engine/artifacts/v_20260906_202052",
        "is_active": True,
        "status": ModelVersion.Status.ACTIVE,
        "default_threshold": 0.20,
    },
    {
        "version_label": "v_20260902_122321",
        "bert_model_name": "distilbert-base-uncased",
        "relative_artifact_dir": "ml_engine/artifacts/v_20260902_122321",
        "is_active": False,
        "status": ModelVersion.Status.READY,
        "default_threshold": 0.10,
    },
]


class Command(BaseCommand):
    help = "Seed or update canonical model versions in the PostgreSQL database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the registration without committing to the database.",
        )
        parser.add_argument(
            "--active-version",
            type=str,
            default="v_20260906_202052",
            help="The version label to designate as active (default: v_20260906_202052).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        target_active = options["active_version"]

        self.stdout.write(self.style.NOTICE(
            "\n=================================================================\n"
            "PSIF PLATFORM — MODEL REGISTRY SEEDING\n"
            "================================================================="
        ))

        base_dir = settings.BASE_DIR

        with transaction.atomic():
            for v_info in CANONICAL_VERSIONS:
                v_label = v_info["version_label"]
                rel_dir = v_info["relative_artifact_dir"]
                art_dir = base_dir / rel_dir

                model_file = rel_dir + "/model.json"
                encoder_file = rel_dir + "/encoder.joblib"
                snapshot_file = rel_dir + "/training_snapshot.json"
                metadata_path = art_dir / "metadata.json"

                # Check on-disk artifact existence
                disk_model = art_dir / "model.json"
                disk_encoder = art_dir / "encoder.joblib"
                has_artifacts = disk_model.exists() and disk_encoder.exists()

                if not has_artifacts:
                    self.stdout.write(self.style.WARNING(
                        f"[-] Warning: Artifact files for {v_label} not found at {art_dir}. "
                        "Paths will be recorded for container worker deployment."
                    ))

                # Load metadata
                metadata = {}
                if metadata_path.exists():
                    try:
                        with open(metadata_path, "r") as f:
                            metadata = json.load(f)
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"[-] Could not read {metadata_path}: {e}"))

                # Ensure key metrics are populated
                if "selected_threshold" not in metadata:
                    metadata["selected_threshold"] = v_info["default_threshold"]
                if "bert_hidden_dimension" not in metadata:
                    metadata["bert_hidden_dimension"] = 768

                should_be_active = (v_label == target_active)
                target_status = ModelVersion.Status.ACTIVE if should_be_active else ModelVersion.Status.READY

                self.stdout.write(
                    f"[*] Processing {v_label}: active={should_be_active}, status={target_status}, "
                    f"threshold={metadata.get('selected_threshold')}"
                )

                if dry_run:
                    self.stdout.write(self.style.SUCCESS(f"    [DRY RUN] Would update/create ModelVersion {v_label}"))
                    continue

                # If this model will be active, deactivate all existing active models first
                if should_be_active:
                    ModelVersion.objects.filter(is_active=True).exclude(version_label=v_label).update(
                        is_active=False,
                        status=ModelVersion.Status.READY
                    )

                mv, created = ModelVersion.objects.update_or_create(
                    version_label=v_label,
                    defaults={
                        "bert_model_name": v_info["bert_model_name"],
                        "xgboost_artifact_path": model_file,
                        "encoder_artifact_path": encoder_file,
                        "training_snapshot_path": snapshot_file if (art_dir / "training_snapshot.json").exists() else "",
                        "metrics": metadata,
                        "status": target_status,
                        "is_active": should_be_active,
                    },
                )

                action_str = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(f"    [✓] {action_str} ModelVersion {v_label} (ID: {mv.id})"))

            if dry_run:
                self.stdout.write(self.style.NOTICE("\n[DRY RUN COMPLETE] No database modifications committed.\n"))
            else:
                active_count = ModelVersion.objects.filter(is_active=True).count()
                total_count = ModelVersion.objects.count()
                self.stdout.write(self.style.SUCCESS(
                    f"\n[✓] Model seeding complete! Total versions: {total_count} | Active versions: {active_count}\n"
                ))
