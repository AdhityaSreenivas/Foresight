"""
PSIF Platform — train_model management command

Orchestrates the complete ML training pipeline:
    1. Load eligible labeled incidents
    2. Audit label distribution
    3. Split data 85/15 (stratified)
    4. Generate BERT embeddings
    5. Fit structured preprocessing on training data
    6. Fuse features
    7. Train/tune XGBoost (5-fold stratified CV)
    8. Select F2-oriented threshold on OOF predictions
    9. Train baselines (structured-only, text-only)
    10. Evaluate all models on held-out test set
    11. Save artifacts
    12. Reload + verify prediction
    13. Create ModelVersion
    14. Print training summary

Usage:
    python manage.py train_model
    python manage.py train_model --seed 123
    python manage.py train_model --bert-batch-size 16
"""
import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Train the PSIF prediction model (BERT + XGBoost pipeline)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed", type=int, default=42,
            help="Random seed for reproducibility (default: 42).",
        )
        parser.add_argument(
            "--bert-batch-size", type=int, default=32,
            help="Batch size for BERT encoding (default: 32).",
        )
        parser.add_argument(
            "--max-search", type=int, default=81,
            help="Max hyperparameter search combinations (default: 81).",
        )

    def handle(self, *args, **options):
        from ml_engine.training.trainer import run_training_pipeline

        seed = options["seed"]
        bert_batch_size = options["bert_batch_size"]
        max_search = options["max_search"]

        self.stdout.write(self.style.NOTICE(
            "\n" + "=" * 60 + "\n"
            "PSIF MODEL TRAINING\n"
            "=" * 60
        ))

        try:
            summary = run_training_pipeline(
                seed=seed,
                max_search_combinations=max_search,
                bert_batch_size=bert_batch_size,
            )
        except (ValueError, RuntimeError) as exc:
            self.stderr.write(self.style.ERROR(f"\nTraining FAILED: {exc}"))
            raise

        # ── Print training summary ────────────────────────────────────────────
        audit = summary["label_audit"]
        m_struct = summary["metrics_baseline_structured"]
        m_text = summary["metrics_baseline_text"]
        m_fused = summary["metrics_fused_test"]
        m_oof = summary["metrics_oof"]
        reload = summary["reload_verification"]

        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*60}\n"
            f"PSIF MODEL TRAINING SUMMARY\n"
            f"{'='*60}\n"
            f"\n"
            f"Model version:           {summary['version_label']}\n"
            f"BERT model:              {summary['bert_model_name']}\n"
            f"BERT dimension:          {summary['bert_dim']}\n"
            f"\n"
            f"Total eligible rows:     {audit['training_eligible']}\n"
            f"  Human-approved synth:  {audit.get('human_approved_synthetic_labeled', audit.get('human_labeled', 0))}\n"
            f"  Synthetic-labeled:     {audit.get('synthetic_labeled', audit.get('heuristic_labeled', 0))}\n"
            f"  Positive:              {audit['positive']}\n"
            f"  Negative:              {audit['negative']}\n"
            f"  Positive %:            {audit['positive_pct']}%\n"
            f"\n"
            f"Train rows:              {summary['train_rows']}\n"
            f"Test rows:               {summary['test_rows']}\n"
            f"\n"
            f"Structured features:     {summary['structured_feature_count']}\n"
            f"Fused dimension:         {summary['fused_dimension']}\n"
            f"\n"
            f"scale_pos_weight:        {summary['scale_pos_weight']}\n"
            f"Selected threshold:      {summary['selected_threshold']}\n"
            f"Best XGBoost params:     {summary['best_params']}\n"
            f"\n"
            f"--- OOF Metrics (Training CV) ---\n"
            f"  Precision:             {m_oof['precision']}\n"
            f"  Recall:                {m_oof['recall']}\n"
            f"  F2:                    {m_oof['f2']}\n"
            f"  ROC-AUC:               {m_oof['roc_auc']}\n"
            f"\n"
            f"--- Baseline A: Structured-only (TEST) ---\n"
            f"  Precision:             {m_struct['precision']}\n"
            f"  Recall:                {m_struct['recall']}\n"
            f"  F2:                    {m_struct['f2']}\n"
            f"  ROC-AUC:               {m_struct['roc_auc']}\n"
            f"\n"
            f"--- Baseline B: Text-only (TEST) ---\n"
            f"  Precision:             {m_text['precision']}\n"
            f"  Recall:                {m_text['recall']}\n"
            f"  F2:                    {m_text['f2']}\n"
            f"  ROC-AUC:               {m_text['roc_auc']}\n"
            f"\n"
            f"--- Final Model: BERT + Structured (TEST) ---\n"
            f"  Precision:             {m_fused['precision']}\n"
            f"  Recall:                {m_fused['recall']}\n"
            f"  F2:                    {m_fused['f2']}\n"
            f"  F1:                    {m_fused['f1']}\n"
            f"  ROC-AUC:               {m_fused['roc_auc']}\n"
            f"  PR-AUC:                {m_fused['pr_auc']}\n"
            f"\n"
            f"Confusion matrix (TEST): {m_fused['confusion_matrix']}\n"
            f"  [[TN, FP], [FN, TP]]\n"
            f"\n"
            f"Artifact directory:      {summary['artifact_dir']}\n"
            f"ModelVersion ID:         {summary['model_version_id']}\n"
            f"Active model count:      {summary['active_model_count']}\n"
            f"\n"
            f"Reload verification:     {reload['status']}\n"
            f"  Single prediction:     prob={reload['single_prediction']['probability']:.4f} "
            f"risk={reload['single_prediction']['risk_level']}\n"
            f"  Batch prediction:      {reload['batch_prediction_count']} results\n"
            f"\n"
            f"Training duration:       {summary['training_duration_seconds']}s\n"
            f"\n"
            f"{'='*60}\n"
            f"SCIENTIFIC CAVEATS & PROVENANCE DISCLAIMER\n"
            f"{'='*60}\n"
            f"• All training data is SYNTHETIC — not real OIL data.\n"
            f"• Human approval of synthetic incidents indicates human review of\n"
            f"  generated examples; it is not equivalent to validation against\n"
            f"  real-world OIL HSE records.\n"
            f"• severity_actual and severity_potential are collected as incident\n"
            f"  context/documentation fields but are EXCLUDED from the\n"
            f"  predictive feature space to prevent data leakage.\n"
            f"• Genuine real-world HSE validation is required before operational use.\n"
            f"{'='*60}\n"
        ))
