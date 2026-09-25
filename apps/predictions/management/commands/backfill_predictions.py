import logging
import time
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.incidents.models import Incident, incident_to_prediction_record
from apps.predictions.models import ModelVersion, PredictionResult
from ml_engine.model_inference import get_active_predictor

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfills/re-scores predictions for incidents using canonical Incident fields and the active ML model."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dataset-id",
            type=str,
            default=None,
            help="UUID of the specific Dataset to re-score. If omitted, all dataset incidents are processed.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of incidents to process in each inference and DB batch (default: 500).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Re-score incidents even if they already have an active-model prediction.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional maximum number of incidents to process.",
        )

    def handle(self, *args, **options):
        dataset_id = options.get("dataset_id")
        batch_size = options.get("batch_size") or 500
        force = options.get("force")
        limit = options.get("limit")

        # 1. Verify active model
        active_version = ModelVersion.objects.filter(is_active=True).first()
        if not active_version:
            self.stdout.write(self.style.ERROR("No active ModelVersion found. Aborting."))
            return

        predictor = get_active_predictor()
        if not predictor:
            self.stdout.write(self.style.ERROR("Failed to load active predictor. Aborting."))
            return

        self.stdout.write(
            self.style.NOTICE(
                f"Active Model: {active_version.version_label} | "
                f"Threshold: {predictor.psif_threshold:.4f} | "
                f"Batch Size: {batch_size}"
            )
        )

        # 2. Build target queryset
        qs = Incident.objects.filter(dataset__isnull=False)
        if dataset_id:
            qs = qs.filter(dataset_id=dataset_id)

        if not force:
            # Filter to incidents that do NOT have a prediction with the active model version
            qs = qs.exclude(prediction__model_version=active_version)

        # Order consistently
        qs = qs.order_by("created_at", "id")

        if limit:
            qs = qs[:limit]

        total_to_process = qs.count()
        self.stdout.write(f"Incidents eligible for re-scoring: {total_to_process}")

        if total_to_process == 0:
            self.stdout.write(self.style.SUCCESS("No incidents require backfill."))
            return

        start_time = time.time()
        processed_count = 0
        success_count = 0
        sparse_count = 0
        psif_count = 0
        not_psif_count = 0

        # We paginate through the queryset in chunks using IDs or iterator
        # To avoid offset issues with iterator on large tables, we iterate in ID chunks
        chunk_incidents = []

        for incident in qs.iterator(chunk_size=batch_size):
            chunk_incidents.append(incident)
            if len(chunk_incidents) >= batch_size:
                s_count, sp_count, p_count, np_count = self._process_batch(
                    chunk_incidents, predictor, active_version
                )
                success_count += s_count
                sparse_count += sp_count
                psif_count += p_count
                not_psif_count += np_count
                processed_count += len(chunk_incidents)
                chunk_incidents = []

                elapsed = time.time() - start_time
                rate = processed_count / elapsed if elapsed > 0 else 0
                self.stdout.write(
                    f"Progress: {processed_count}/{total_to_process} ({processed_count/total_to_process*100:.1f}%) | "
                    f"Rate: {rate:.1f} rec/s | PSIF: {psif_count} | Non-PSIF: {not_psif_count} | Sparse: {sparse_count}"
                )

        # Process any remaining records
        if chunk_incidents:
            s_count, sp_count, p_count, np_count = self._process_batch(
                chunk_incidents, predictor, active_version
            )
            success_count += s_count
            sparse_count += sp_count
            psif_count += p_count
            not_psif_count += np_count
            processed_count += len(chunk_incidents)

        total_elapsed = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"\nRe-scoring Complete in {total_elapsed:.1f}s!\n"
                f"Total Processed: {processed_count}\n"
                f"Predictions Created/Updated: {success_count}\n"
                f"PSIF Candidates: {psif_count}\n"
                f"NOT PSIF: {not_psif_count}\n"
                f"Sparse (Insufficient Evidence): {sparse_count}\n"
            )
        )

    def _process_batch(self, incidents, predictor, active_version):
        """
        Process a batch of incidents:
        1. Construct canonical records.
        2. Run batched inference.
        3. Idempotently update or create PredictionResults.
        """
        # Build canonical records - strictly legitimate predictive features
        records = [incident_to_prediction_record(inc) for inc in incidents]

        # Run batched inference
        batch_outputs = predictor.predict_batch(records)

        # Fetch existing PredictionResults for this chunk
        incident_map = {inc.id: inc for inc in incidents}
        existing_preds = {
            p.incident_id: p
            for p in PredictionResult.objects.filter(incident__in=incidents)
        }

        to_update = []
        to_create = []
        sparse_count = 0
        psif_count = 0
        not_psif_count = 0

        for inc, pred in zip(incidents, batch_outputs):
            if pred.is_sparse_input:
                sparse_count += 1
            if pred.psif_predicted:
                psif_count += 1
            else:
                not_psif_count += 1

            if inc.id in existing_preds:
                pr = existing_preds[inc.id]
                pr.model_version = active_version
                pr.psif_probability = pred.psif_probability
                pr.psif_predicted = pred.psif_predicted
                pr.risk_level = pred.risk_level
                pr.is_sparse_input = pred.is_sparse_input
                pr.evidence_strength = pred.evidence_strength
                pr.explanation_detail = pred.explanation
                pr.top_factors = pred.top_factors
                to_update.append(pr)
            else:
                to_create.append(
                    PredictionResult(
                        incident=inc,
                        model_version=active_version,
                        psif_probability=pred.psif_probability,
                        psif_predicted=pred.psif_predicted,
                        risk_level=pred.risk_level,
                        is_sparse_input=pred.is_sparse_input,
                        evidence_strength=pred.evidence_strength,
                        explanation_detail=pred.explanation,
                        top_factors=pred.top_factors,
                    )
                )

            # Keep raw_row audit metadata synchronized without mutating any source keys
            if isinstance(inc.raw_row, dict):
                inc.raw_row["_model_version"] = active_version.version_label
                inc.raw_row["_psif_probability"] = pred.psif_probability
                inc.raw_row["_psif_predicted"] = pred.psif_predicted
                inc.raw_row["_risk_level"] = pred.risk_level
                inc.raw_row["_is_sparse_input"] = pred.is_sparse_input

        with transaction.atomic():
            if to_update:
                PredictionResult.objects.bulk_update(
                    to_update,
                    fields=[
                        "model_version",
                        "psif_probability",
                        "psif_predicted",
                        "risk_level",
                        "is_sparse_input",
                        "evidence_strength",
                        "explanation_detail",
                        "top_factors",
                    ],
                    batch_size=500,
                )
            if to_create:
                PredictionResult.objects.bulk_create(to_create, batch_size=500)

            Incident.objects.bulk_update(incidents, fields=["raw_row"], batch_size=500)

        return len(incidents), sparse_count, psif_count, not_psif_count
