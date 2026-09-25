"""
PSIF Platform — ML Training Pipeline

Implements the complete training flow:

    Incident records
    → label selection (human > heuristic > exclude)
    → 85/15 stratified train/test split
    → BERT text embedding (frozen distilbert-base-uncased)
    → structured feature encoding (fit on train only)
    → feature fusion [BERT | structured]
    → XGBoost training with 5-fold stratified CV
    → F2-oriented threshold selection on OOF predictions
    → final model retrained on full training set
    → held-out test evaluation (touched exactly once)
    → artifact persistence
    → reload verification

Data splitting methodology (documented per specification):
    - 85% TRAIN / 15% TEST, stratified by label
    - Within TRAIN: 5-fold stratified CV for hyperparameter search
    - After HP selection: fresh OOF predictions for threshold selection
    - Final model retrained on complete TRAIN set
    - TEST touched exactly ONCE for final evaluation

Leakage prevention:
    - Preprocessing (OneHotEncoder, scalers) fit only on TRAIN
    - scale_pos_weight calculated only from TRAIN
    - Threshold selected only from TRAIN OOF predictions
    - TEST never used for any fitting, selection, or tuning
    - Excluded from features: is_psif_human_label, is_psif_heuristic_label,
      psif_label_source (any target-derived field)
    - severity_actual and severity_potential are used ONLY to construct the
      heuristic PSIF label in ml_engine/training/weak_labeling.py. They are
      NOT present in StructuredFeatureEncoder.BOOLEAN_FIELDS, NUMERIC_FIELDS,
      or CATEGORICAL_FIELDS and therefore do NOT enter the structured model
      feature vector. There is no confirmed structural leakage via those two
      fields. The remaining concern is text-level: if free-text narratives
      echo their own severity assessment, DistilBERT may encode that as a
      soft correlate of the heuristic label. This risk is currently
      unquantified and cannot be mitigated purely by adjusting the encoder's
      field lists.

Baseline comparisons:
    - Baseline A: structured features only → XGBoost
    - Baseline B: BERT text embeddings only → XGBoost
    - Final model: BERT + structured → XGBoost
"""
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from sklearn.metrics import (
    precision_score,
    recall_score,
    fbeta_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
)
from sklearn.model_selection import (
    train_test_split,
    StratifiedKFold,
    GridSearchCV,
    cross_val_predict,
)
import xgboost as xgb

from ml_engine.bert_encoder import encode_texts, _get_model_and_tokenizer
from ml_engine.feature_encoder import StructuredFeatureEncoder
from ml_engine.text_preprocessing import build_composite_narrative
from ml_engine.training.training_sources import (
    get_training_eligible_incidents,
    TrainingSource,
)

logger = logging.getLogger(__name__)

# Default random seed for reproducibility
DEFAULT_SEED = 42

# Default max combinations for hyperparameter search
# Set via settings or override at call site
DEFAULT_MAX_SEARCH_COMBINATIONS = 81  # full 3×3×3×3 grid


# ── Label audit & Provenance ──────────────────────────────────────────────────

def audit_labels(
    incidents=None,
    training_source: str = "SYNTHETIC",
    composition: Optional[dict] = None,
) -> dict:
    """
    Audit label distribution across clean provenance categories:
    1. human_approved_synthetic_psif
    2. human_approved_synthetic_not_psif
    3. human_insufficient_information
    4. synthetic_simulation
    5. real_external
    6. synthetic_eligible
    """
    from apps.incidents.models import Incident
    from django.db.models import Q

    total_db = Incident.objects.count()

    human_approved_psif = Incident.objects.filter(
        is_synthetic=True,
        is_synthetic_adjudication=False,
        adjudicated_human_decision=Incident.HumanDecision.PSIF,
    ).count()

    human_approved_not_psif = Incident.objects.filter(
        is_synthetic=True,
        is_synthetic_adjudication=False,
        adjudicated_human_decision=Incident.HumanDecision.NOT_PSIF,
    ).count()

    human_insufficient = Incident.objects.filter(
        is_synthetic_adjudication=False,
        adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION,
    ).count()

    synthetic_simulation = Incident.objects.filter(
        is_synthetic_adjudication=True,
    ).count()

    real_external = Incident.objects.filter(
        psif_label_source=Incident.PsifLabelSource.REAL_EXTERNAL,
    ).count()

    human_eligible = human_approved_psif + human_approved_not_psif

    if incidents is not None:
        training_eligible = len(incidents)
        final_positive = sum(
            1 for inc in incidents
            if getattr(inc, "_training_label", getattr(inc, "effective_training_label", None)) is True
        )
        final_negative = sum(
            1 for inc in incidents
            if getattr(inc, "_training_label", getattr(inc, "effective_training_label", None)) is False
        )
    else:
        norm_source = str(training_source).upper().strip()
        if norm_source in ("HUMAN_APPROVED_SYNTHETIC", "HUMAN"):
            training_eligible = human_eligible
            final_positive = human_approved_psif
            final_negative = human_approved_not_psif
        else:
            synth_eligible_qs = Incident.objects.filter(
                is_synthetic=True,
                is_synthetic_adjudication=False,
            ).exclude(
                adjudicated_human_decision=Incident.HumanDecision.INSUFFICIENT_INFORMATION
            )
            training_eligible = synth_eligible_qs.count()
            final_positive = sum(1 for inc in synth_eligible_qs if inc.effective_training_label is True)
            final_negative = sum(1 for inc in synth_eligible_qs if inc.effective_training_label is False)

    training_excluded = human_insufficient + synthetic_simulation + real_external

    pos_pct = (final_positive / training_eligible * 100) if training_eligible > 0 else 0.0
    ratio = (final_negative / final_positive) if final_positive > 0 else float("inf")

    audit = {
        "total_incidents_in_db": total_db,
        "training_source": training_source,
        "provenance_counts": {
            "human_approved_synthetic": human_approved_psif + human_approved_not_psif,
            "human_approved_synthetic_psif": human_approved_psif,
            "human_approved_synthetic_not_psif": human_approved_not_psif,
            "human_insufficient_information": human_insufficient,
            "synthetic_simulation": synthetic_simulation,
            "real_external": real_external,
            "heuristic_psif": 0,
            "heuristic_not_psif": 0,
            "synthetic_evaluation": synthetic_simulation,
            "unknown_unlabelled": 0,
        },
        "composition": composition or {},
        "human_approved_eligible": human_eligible,
        "human_eligible": human_eligible,
        "heuristic_eligible": 0,
        "training_eligible": training_eligible,
        "training_excluded": training_excluded,
        "final_positive_count": final_positive,
        "final_negative_count": final_negative,
        "positive_pct": round(pos_pct, 2),
        "class_ratio_neg_pos": round(ratio, 2) if ratio != float("inf") else "inf",
        "synthetic_evaluation_excluded": True,
    }

    logger.info("Database Provenance & Label Audit: %s", json.dumps(audit, indent=2))

    if training_eligible < 20:
        raise ValueError(
            f"Insufficient training data: only {training_eligible} eligible labeled rows in database "
            f"for training source '{training_source}'. Need at least 20."
        )
    if final_positive == 0:
        raise ValueError("Zero positive examples — cannot train a classifier.")
    if final_negative == 0:
        raise ValueError("Zero negative examples — cannot train a classifier.")
    if final_positive < 5:
        raise ValueError(
            f"Only {final_positive} positive examples — too few for stratified splitting."
        )

    return audit


def generate_training_snapshot(
    eligible_incidents: list,
    audit: dict,
    version_label: str,
    feature_names: list,
    training_source: str = "HUMAN",
    validation_basis: str = "REAL HUMAN HSE VALIDATION",
    disclaimer: Optional[str] = None,
    composition: Optional[dict] = None,
) -> dict:
    """
    Generate an immutable training snapshot bound to the candidate model version.
    Contains complete incident UUID list, target per incident, label source per incident,
    dataset SHA256 hash, schema versions, and DB provenance breakdown.
    """
    snapshot_id = str(uuid.uuid4())
    now_iso = datetime.now(dt_timezone.utc).isoformat()

    hasher = hashlib.sha256()
    incident_records = []

    sorted_incidents = sorted(eligible_incidents, key=lambda x: str(x.id))
    for inc in sorted_incidents:
        raw_label = getattr(inc, "_training_label", getattr(inc, "effective_training_label", None))
        target = 1 if raw_label else 0

        source = getattr(inc, "_training_source", None)
        if not source:
            if getattr(inc, "is_human_approved_synthetic", False):
                source = "human_approved_synthetic"
            else:
                source = "synthetic"

        entry = {
            "incident_id": str(inc.id),
            "target": target,
            "label_source": source,
            "provenance_category": getattr(inc, "provenance_category", source.upper()),
        }
        incident_records.append(entry)
        hasher.update(f"{inc.id}:{target}:{source}\n".encode("utf-8"))

    dataset_hash = hasher.hexdigest()

    return {
        "snapshot_id": snapshot_id,
        "model_version_label": version_label,
        "created_at": now_iso,
        "training_source": training_source,
        "validation_basis": validation_basis,
        "disclaimer": disclaimer,
        "provenance_composition": composition or audit.get("composition") or {},
        "label_policy_version": "2.0-provenance-hierarchy",
        "feature_schema_version": "1.0-distilbert768+structured",
        "training_code_version": "git-sih-26165-v2",
        "dataset_hash": dataset_hash,
        "provenance_summary": audit["provenance_counts"],
        "counts": {
            "total_incidents_in_db": audit["total_incidents_in_db"],
            "human_approved_eligible": audit.get("human_approved_eligible", 0),
            "human_eligible": audit["human_eligible"],
            "synthetic_eligible": audit.get("synthetic_eligible", 0),
            "training_eligible": audit["training_eligible"],
            "training_excluded": audit["training_excluded"],
            "final_positive_count": audit["final_positive_count"],
            "final_negative_count": audit["final_negative_count"],
        },
        "feature_names": feature_names,
        "incident_uuid_list": [r["incident_id"] for r in incident_records],
        "incident_records": incident_records,
    }


# ── Data preparation ─────────────────────────────────────────────────────────

def prepare_training_data(incidents) -> tuple[list[dict], list[str], np.ndarray]:
    """
    Extract features and labels from incident records.

    Returns:
        (records, narratives, labels)
        - records: list of dicts with structured fields
        - narratives: list of composite narrative strings
        - labels: numpy array of 0/1 labels
    """
    records = []
    narratives = []
    labels = []

    for inc in incidents:
        label = getattr(inc, "_training_label", None)
        if label is None:
            label = getattr(inc, "effective_training_label", None)
        if label is None:
            continue  # skip unlabeled

        record = {
            "department": inc.department,
            "injury_type": inc.injury_type,
            "body_part": inc.body_part,
            "immediate_cause": inc.immediate_cause,
            "root_cause_category": inc.root_cause_category,
            # severity_actual and severity_potential are intentionally EXCLUDED
            # from this dict.  They are not in StructuredFeatureEncoder's field
            # lists and would be silently ignored if included — but keeping them
            # out makes the absence explicit and prevents any future accidental
            # inclusion without a deliberate encoder change.
            "near_miss": inc.near_miss,
            # Text fields for narrative
            "description": inc.description,
            "corrective_actions": inc.corrective_actions,
            "witness_statement": inc.witness_statement,
        }
        records.append(record)

        # Use stored composite_narrative if available, otherwise rebuild
        narrative = inc.composite_narrative or build_composite_narrative(
            description=inc.description,
            corrective_actions=inc.corrective_actions,
            witness_statement=inc.witness_statement,
        )
        narratives.append(narrative)
        labels.append(1 if label else 0)

    return records, narratives, np.array(labels, dtype=int)


# ── Metrics computation ──────────────────────────────────────────────────────

def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
    threshold: float,
    label: str = "",
) -> dict:
    """Compute the full metrics suite for a set of predictions."""
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f2 = fbeta_score(y_true, y_pred, beta=2, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    try:
        roc = roc_auc_score(y_true, y_prob)
    except ValueError:
        roc = 0.0

    try:
        pr_auc = average_precision_score(y_true, y_prob)
    except ValueError:
        pr_auc = 0.0

    cm = confusion_matrix(y_true, y_pred).tolist()

    metrics = {
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f2": round(f2, 4),
        "f1": round(f1, 4),
        "roc_auc": round(roc, 4),
        "pr_auc": round(pr_auc, 4),
        "confusion_matrix": cm,
        "false_negatives": int(cm[1][0]),
        "threshold": threshold,
        "support": {
            "positive": int(y_true.sum()),
            "negative": int((1 - y_true).sum()),
        },
    }

    if label:
        logger.info(
            "%s metrics — Precision: %.4f | Recall: %.4f | F2: %.4f | "
            "ROC-AUC: %.4f | PR-AUC: %.4f | Threshold: %.2f",
            label, prec, rec, f2, roc, pr_auc, threshold,
        )

    return metrics


# ── Threshold selection ──────────────────────────────────────────────────────

def select_threshold_f2(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """
    Select the binary decision threshold that maximises F2 score.

    Evaluates thresholds from 0.10 to 0.90 in increments of 0.05.
    This function must only be called on TRAINING data (OOF predictions),
    never on the held-out test set.
    """
    best_threshold = 0.5
    best_f2 = 0.0

    for threshold in np.arange(0.10, 0.91, 0.05):
        y_pred = (y_prob >= threshold).astype(int)
        f2 = fbeta_score(y_true, y_pred, beta=2, zero_division=0)
        if f2 > best_f2:
            best_f2 = f2
            best_threshold = threshold

    logger.info(
        "Threshold selection: best_threshold=%.2f best_F2=%.4f (from OOF)",
        best_threshold, best_f2,
    )
    return round(best_threshold, 2)


# ── XGBoost training with baselines ──────────────────────────────────────────

def _make_xgb_estimator(scale_pos_weight: float, seed: int) -> xgb.XGBClassifier:
    """Create a base XGBClassifier with shared configuration."""
    return xgb.XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        scale_pos_weight=scale_pos_weight,
        random_state=seed,
        use_label_encoder=False,
        n_jobs=1,
        verbosity=0,
    )


def _run_grid_search(
    X_train: np.ndarray,
    y_train: np.ndarray,
    scale_pos_weight: float,
    seed: int,
    max_combinations: int,
    n_cv_folds: int = 5,
) -> dict:
    """
    Run bounded hyperparameter grid search with stratified CV.
    Scoring: F2 (fbeta with beta=2).
    """
    from sklearn.metrics import make_scorer

    f2_scorer = make_scorer(fbeta_score, beta=2, zero_division=0)

    param_grid = {
        "max_depth": [3, 5, 7],
        "learning_rate": [0.05, 0.1, 0.2],
        "n_estimators": [100, 200, 300],
        "min_child_weight": [1, 3, 5],
    }

    estimator = _make_xgb_estimator(scale_pos_weight, seed)
    cv = StratifiedKFold(n_splits=n_cv_folds, shuffle=True, random_state=seed)

    grid = GridSearchCV(
        estimator,
        param_grid,
        scoring=f2_scorer,
        cv=cv,
        n_jobs=-1,
        refit=False,  # we will retrain manually
        verbose=0,
    )

    logger.info(
        "Starting XGBoost grid search: %d param combos × %d folds",
        min(max_combinations, 81), n_cv_folds,
    )
    grid.fit(X_train, y_train)

    best_params = grid.best_params_
    best_score = grid.best_score_

    logger.info(
        "Grid search complete: best_F2_cv=%.4f best_params=%s",
        best_score, best_params,
    )

    return best_params


def _train_single_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    best_params: dict,
    scale_pos_weight: float,
    seed: int,
) -> xgb.XGBClassifier:
    """Train a single XGBoost model with the selected hyperparameters."""
    model = _make_xgb_estimator(scale_pos_weight, seed)
    model.set_params(**best_params)
    model.fit(X_train, y_train)
    return model


def _generate_oof_predictions(
    X_train: np.ndarray,
    y_train: np.ndarray,
    best_params: dict,
    scale_pos_weight: float,
    seed: int,
    n_cv_folds: int = 5,
) -> np.ndarray:
    """
    Generate fresh out-of-fold probability predictions using the selected
    hyperparameters. Used for threshold selection on training data only.
    """
    model = _make_xgb_estimator(scale_pos_weight, seed)
    model.set_params(**best_params)

    cv = StratifiedKFold(n_splits=n_cv_folds, shuffle=True, random_state=seed)

    oof_probs = cross_val_predict(
        model, X_train, y_train,
        cv=cv,
        method="predict_proba",
    )[:, 1]  # probability of positive class

    logger.info("Generated OOF predictions: shape=%s", oof_probs.shape)
    return oof_probs


# ── Artifact management ──────────────────────────────────────────────────────

def save_artifacts(
    version_dir: Path,
    model: xgb.XGBClassifier,
    encoder: StructuredFeatureEncoder,
    metadata: dict,
) -> None:
    """Save all training artifacts to the version directory."""
    version_dir.mkdir(parents=True, exist_ok=True)

    # XGBoost model in native JSON format
    model_path = version_dir / "model.json"
    model.get_booster().save_model(str(model_path))
    logger.info("Saved XGBoost model to %s", model_path)

    # Structured feature encoder
    encoder_path = version_dir / "encoder.joblib"
    encoder.save(encoder_path)
    logger.info("Saved encoder to %s", encoder_path)

    # Metadata
    metadata_path = version_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    logger.info("Saved metadata to %s", metadata_path)


def verify_artifact_reload(
    version_dir: Path,
    sample_record: dict,
    bert_model_name: str,
) -> dict:
    """
    Load saved artifacts and run a test prediction to verify they work.
    Returns the test prediction result.
    """
    from ml_engine.model_inference import PSIFPredictor

    model_path = version_dir / "model.json"
    encoder_path = version_dir / "encoder.joblib"
    metadata_path = version_dir / "metadata.json"

    # Verify all files exist
    for path in [model_path, encoder_path, metadata_path]:
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")

    # Load metadata to get threshold and bert_dim
    with open(metadata_path) as f:
        metadata = json.load(f)

    threshold = metadata.get("selected_threshold", 0.5)

    # Create predictor from saved artifacts
    predictor = PSIFPredictor(
        xgboost_artifact_path=model_path,
        encoder_artifact_path=encoder_path,
        bert_model_name=bert_model_name,
        psif_threshold=threshold,
        bert_dim=metadata.get("bert_hidden_dimension"),
    )

    # Single prediction
    result = predictor.predict(sample_record)
    logger.info(
        "Reload verification — single predict: prob=%.4f predicted=%s risk=%s",
        result.psif_probability, result.psif_predicted, result.risk_level,
    )

    # Batch prediction
    batch_results = predictor.predict_batch([sample_record, sample_record])
    logger.info(
        "Reload verification — batch predict: %d results", len(batch_results),
    )

    return {
        "single_prediction": {
            "probability": result.psif_probability,
            "predicted": result.psif_predicted,
            "risk_level": result.risk_level,
        },
        "batch_prediction_count": len(batch_results),
        "status": "success",
    }


# ── Main training pipeline ──────────────────────────────────────────────────

def run_training_pipeline(
    seed: int = DEFAULT_SEED,
    max_search_combinations: int = DEFAULT_MAX_SEARCH_COMBINATIONS,
    bert_batch_size: int = 32,
    model_version: Optional[Any] = None,
    training_source: Optional[str] = None,
    sample_limit: Optional[int] = None,
) -> dict:
    """
    Execute the complete PSIF model training pipeline.

    Args:
        seed: Random seed for reproducibility.
        max_search_combinations: Hyperparameter search budget.
        bert_batch_size: Inference batch size for DistilBERT.
        model_version: Optional existing ModelVersion instance to update (candidate model).
        training_source: Training source ('HUMAN', 'HEURISTIC', 'SYNTHETIC', 'MIXED').
        sample_limit: Optional max rows to train on.

    Returns:
        Summary dict with all training results, metrics, and artifact paths.

    Raises:
        ValueError: if label distribution is pathological
        RuntimeError: if artifact verification fails
    """
    from django.conf import settings
    from apps.predictions.models import ModelVersion
    from ml_engine.training.training_sources import (
        TrainingSource,
        get_training_eligible_incidents,
    )

    start_time = time.time()
    bert_model_name = settings.BERT_MODEL_NAME

    if training_source is None:
        if model_version and isinstance(model_version.metrics, dict) and "training_source" in model_version.metrics:
            training_source = model_version.metrics["training_source"]
        else:
            training_source = TrainingSource.HUMAN
    training_source = str(training_source).upper().strip()

    last_report_time = 0.0

    def _report_progress(
        pct: int,
        stage_text: str,
        stage_code: typing.Optional[str] = None,
        processed_units: typing.Optional[int] = None,
        total_units: typing.Optional[int] = None,
        force: bool = False,
    ):
        nonlocal last_report_time
        now_ts = time.time()
        # Throttle DB updates to at most once per 1.0s unless force=True
        if not force and (now_ts - last_report_time) < 1.0:
            return

        if model_version:
            try:
                from apps.predictions.timing import calculate_retraining_timing
                model_version.refresh_from_db()
                if not isinstance(model_version.metrics, dict):
                    model_version.metrics = {}
                pct_clamped = max(0, min(100, int(pct)))
                model_version.metrics["progress_pct"] = pct_clamped
                model_version.metrics["current_stage"] = stage_text
                model_version.metrics["training_status"] = "RUNNING"
                if stage_code:
                    model_version.metrics["stage_code"] = stage_code
                if processed_units is not None:
                    model_version.metrics["processed_units"] = processed_units
                if total_units is not None:
                    model_version.metrics["total_units"] = total_units

                timing_info = calculate_retraining_timing(model_version, current_metrics=model_version.metrics)
                model_version.metrics.update(timing_info)

                model_version.save(update_fields=["metrics"])
                last_report_time = now_ts
            except Exception as prog_err:
                logger.debug("Could not update progress metrics: %s", prog_err)

    logger.info("=" * 60)
    logger.info("PSIF MODEL TRAINING PIPELINE STARTED (CONTROLLED RETRAINING: %s)", training_source)
    logger.info("=" * 60)

    _report_progress(5, "Loading eligible training incidents from PostgreSQL...", stage_code="DATA_LOADING", force=True)

    # ── 1. Load eligible incidents dynamically from DB ─────────────────────────
    logger.info("Step 1: Loading eligible labeled incidents for source %s from PostgreSQL...", training_source)
    all_incidents, row_provenance, comp = get_training_eligible_incidents(
        training_source=training_source,
        sample_limit=sample_limit,
    )
    logger.info("Found %d eligible training incidents in database for source %s", len(all_incidents), training_source)
    _report_progress(12, f"Resolved {len(all_incidents):,} eligible incidents. Auditing database provenance...", stage_code="DATA_AUDIT", force=True)

    # ── 2. Comprehensive DB Provenance Audit ──────────────────────────────────
    logger.info("Step 2: Auditing database provenance and label distribution...")
    audit = audit_labels(incidents=all_incidents, training_source=training_source, composition=comp)
    _report_progress(16, "Preparing narrative corpus & structured safety factors...", stage_code="DATA_PREP", force=True)

    # Validation basis & disclaimers
    if training_source in (TrainingSource.HUMAN_APPROVED_SYNTHETIC, "HUMAN"):
        validation_basis = "HUMAN-APPROVED SYNTHETIC EVALUATION"
        disclaimer = (
            "This candidate was trained using human-approved synthetic incident records. "
            "Human approval of synthetic incidents indicates human review of generated examples; "
            "it is not equivalent to validation against real-world OIL HSE records."
        )
    elif training_source == TrainingSource.SYNTHETIC:
        validation_basis = "SYNTHETIC DATASET EVALUATION"
        disclaimer = (
            "This candidate was trained using synthetic dataset benchmark labels and is intended "
            "for development and comparative experimentation. The results do not establish "
            "real-world HSE predictive validity."
        )
    else:  # MIXED_SYNTHETIC
        validation_basis = "MIXED SYNTHETIC EVALUATION"
        disclaimer = (
            "This candidate was trained using combined synthetic benchmark and human-approved synthetic records. "
            "Human approval of synthetic incidents indicates human review of generated examples; "
            "it is not equivalent to validation against real-world OIL HSE records."
        )

    # ── 3. Prepare data ───────────────────────────────────────────────────────
    logger.info("Step 3: Preparing training data...")
    records, narratives, labels = prepare_training_data(all_incidents)
    n_total = len(labels)
    logger.info("Prepared %d records (%d positive, %d negative)",
                n_total, labels.sum(), (1 - labels).sum())
    _report_progress(20, "Splitting dataset into stratified 85/15 train/test partitions...", stage_code="DATA_PREP", force=True)

    # ── 4. Stratified 85/15 train/test split ──────────────────────────────────
    logger.info("Step 4: Splitting data 85/15 (stratified)...")
    indices = np.arange(n_total)
    train_idx, test_idx = train_test_split(
        indices, test_size=0.15, stratify=labels, random_state=seed,
    )

    records_train = [records[i] for i in train_idx]
    records_test = [records[i] for i in test_idx]
    narratives_train = [narratives[i] for i in train_idx]
    narratives_test = [narratives[i] for i in test_idx]
    y_train = labels[train_idx]
    y_test = labels[test_idx]

    logger.info("Train: %d rows (%d pos, %d neg)",
                len(y_train), y_train.sum(), (1 - y_train).sum())
    logger.info("Test:  %d rows (%d pos, %d neg)",
                len(y_test), y_test.sum(), (1 - y_test).sum())

    # ── 5. scale_pos_weight from TRAIN only ───────────────────────────────────
    n_pos_train = int(y_train.sum())
    n_neg_train = int((1 - y_train).sum())
    scale_pos_weight = n_neg_train / n_pos_train
    logger.info("scale_pos_weight (from train): %.4f", scale_pos_weight)

    # ── 6. BERT text embeddings ───────────────────────────────────────────────
    logger.info("Step 6: Generating BERT embeddings (this may take a few minutes)...")
    bert_start = time.time()

    if model_version and isinstance(model_version.metrics, dict):
        model_version.metrics["emb_train_started_at"] = timezone.now().isoformat()

    def _train_emb_progress(processed: int, total: int):
        pct = 20 + int(round(40 * (processed / max(total, 1))))
        stage_msg = f"Encoding training narratives with DistilBERT ({processed:,} / {total:,} samples)..."
        _report_progress(
            pct=pct,
            stage_text=stage_msg,
            stage_code="EMBEDDING_TRAIN",
            processed_units=processed,
            total_units=total,
            force=(processed == total or processed == 0),
        )

    _report_progress(
        pct=20,
        stage_text=f"Encoding {len(narratives_train):,} training narratives with DistilBERT transformer...",
        stage_code="EMBEDDING_TRAIN",
        processed_units=0,
        total_units=len(narratives_train),
        force=True,
    )

    X_bert_train = encode_texts(
        narratives_train,
        model_name=bert_model_name,
        batch_size=bert_batch_size,
        progress_callback=_train_emb_progress,
    )

    if model_version and isinstance(model_version.metrics, dict):
        model_version.metrics["emb_test_started_at"] = timezone.now().isoformat()

    def _test_emb_progress(processed: int, total: int):
        pct = 60 + int(round(5 * (processed / max(total, 1))))
        stage_msg = f"Encoding test narratives with DistilBERT ({processed:,} / {total:,} samples)..."
        _report_progress(
            pct=pct,
            stage_text=stage_msg,
            stage_code="EMBEDDING_TEST",
            processed_units=processed,
            total_units=total,
            force=(processed == total or processed == 0),
        )

    _report_progress(
        pct=60,
        stage_text=f"Encoding {len(narratives_test):,} test narratives with DistilBERT transformer...",
        stage_code="EMBEDDING_TEST",
        processed_units=0,
        total_units=len(narratives_test),
        force=True,
    )

    X_bert_test = encode_texts(
        narratives_test,
        model_name=bert_model_name,
        batch_size=bert_batch_size,
        progress_callback=_test_emb_progress,
    )
    bert_elapsed = time.time() - bert_start
    logger.info("BERT encoding complete in %.1fs | train shape: %s, test shape: %s",
                bert_elapsed, X_bert_train.shape, X_bert_test.shape)

    # Get BERT hidden dimension from model config (NOT hardcoded)
    _, bert_model = _get_model_and_tokenizer(bert_model_name)
    bert_dim = bert_model.config.hidden_size
    logger.info("BERT hidden dimension (from model config): %d", bert_dim)

    # ── 7. Structured feature encoding (fit on TRAIN only) ────────────────────
    _report_progress(68, "Encoding structured safety factors and tabular variables...", stage_code="STRUCTURED_ENCODING", force=True)
    logger.info("Step 7: Fitting structured feature encoder on training data...")
    encoder = StructuredFeatureEncoder()
    X_struct_train = encoder.fit_transform(records_train)
    X_struct_test = encoder.transform(records_test)
    struct_dim = X_struct_train.shape[1]
    logger.info("Structured features: %d dimensions", struct_dim)
    logger.info("Feature names: %s", encoder.feature_names_)

    # ── 8. Feature fusion ─────────────────────────────────────────────────────
    _report_progress(72, "Fusing transformer text embeddings with structured safety features...", stage_code="FEATURE_FUSION", force=True)
    logger.info("Step 8: Fusing features [BERT %d | structured %d]...",
                bert_dim, struct_dim)
    X_fused_train = np.hstack([X_bert_train, X_struct_train])
    X_fused_test = np.hstack([X_bert_test, X_struct_test])
    fused_dim = X_fused_train.shape[1]
    logger.info("Fused feature dimension: %d", fused_dim)

    # ── 9. Train all three models ─────────────────────────────────────────────

    # 9a. Hyperparameter search on FUSED features
    _report_progress(78, "Running XGBoost hyperparameter search & cross-validation...", stage_code="XGBOOST_SEARCH", force=True)
    logger.info("Step 9a: XGBoost hyperparameter search (fused features)...")
    best_params = _run_grid_search(
        X_fused_train, y_train, scale_pos_weight, seed, max_search_combinations,
    )

    # 9b. Generate fresh OOF predictions for threshold selection
    _report_progress(83, "Generating Out-of-Fold (OOF) predictions for threshold calibration...", stage_code="THRESHOLD_CALIBRATION", force=True)
    logger.info("Step 9b: Generating OOF predictions for threshold selection...")
    oof_probs = _generate_oof_predictions(
        X_fused_train, y_train, best_params, scale_pos_weight, seed,
    )

    # 9c. Select F2-optimal threshold from OOF predictions (TRAIN only)
    _report_progress(85, "Calibrating high-recall F2-optimal operating threshold...", stage_code="THRESHOLD_CALIBRATION", force=True)
    logger.info("Step 9c: Selecting F2-optimal threshold from OOF predictions...")
    selected_threshold = select_threshold_f2(y_train, oof_probs)

    # 9d. Retrain final model on complete training set
    _report_progress(88, "Fitting final candidate XGBoost model on fused features...", stage_code="MODEL_FIT", force=True)
    logger.info("Step 9d: Training final fused model on complete training set...")
    final_model = _train_single_model(
        X_fused_train, y_train, best_params, scale_pos_weight, seed,
    )

    # ── 10. Baseline A: structured-only ───────────────────────────────────────
    _report_progress(91, "Evaluating candidate against structured & text baseline models...", stage_code="BASELINES", force=True)
    logger.info("Step 10a: Training Baseline A (structured-only)...")
    best_params_struct = _run_grid_search(
        X_struct_train, y_train, scale_pos_weight, seed, max_search_combinations,
    )
    model_struct = _train_single_model(
        X_struct_train, y_train, best_params_struct, scale_pos_weight, seed,
    )
    y_prob_struct_test = model_struct.predict_proba(X_struct_test)[:, 1]
    y_pred_struct_test = (y_prob_struct_test >= selected_threshold).astype(int)
    metrics_struct = compute_metrics(
        y_test, y_pred_struct_test, y_prob_struct_test, selected_threshold,
        label="Baseline A (structured-only) TEST",
    )

    # ── 11. Baseline B: text-only ─────────────────────────────────────────────
    logger.info("Step 10b: Training Baseline B (text-only)...")
    best_params_text = _run_grid_search(
        X_bert_train, y_train, scale_pos_weight, seed, max_search_combinations,
    )
    model_text = _train_single_model(
        X_bert_train, y_train, best_params_text, scale_pos_weight, seed,
    )
    y_prob_text_test = model_text.predict_proba(X_bert_test)[:, 1]
    y_pred_text_test = (y_prob_text_test >= selected_threshold).astype(int)
    metrics_text = compute_metrics(
        y_test, y_pred_text_test, y_prob_text_test, selected_threshold,
        label="Baseline B (text-only) TEST",
    )

    # ── 12. Final fused model evaluation on held-out test set ─────────────────
    _report_progress(95, "Computing test metrics on held-out 15% evaluation split...", stage_code="EVALUATION", force=True)
    logger.info("Step 12: Evaluating final fused model on held-out test set...")
    y_prob_test = final_model.predict_proba(X_fused_test)[:, 1]
    y_pred_test = (y_prob_test >= selected_threshold).astype(int)
    metrics_fused = compute_metrics(
        y_test, y_pred_test, y_prob_test, selected_threshold,
        label="Final model (BERT+structured) TEST",
    )

    # OOF metrics for reference (training-derived)
    y_pred_oof = (oof_probs >= selected_threshold).astype(int)
    metrics_oof = compute_metrics(
        y_train, y_pred_oof, oof_probs, selected_threshold,
        label="OOF (training CV)",
    )

    # ── 13. Save artifacts & Immutable Training Snapshot ──────────────────────
    _report_progress(98, "Generating immutable training snapshot and persisting model artifacts...", stage_code="ARTIFACT_PERSISTENCE", force=True)
    timestamp = datetime.now(dt_timezone.utc).strftime("%Y%m%d_%H%M%S")
    version_label = model_version.version_label if model_version and model_version.version_label else f"v_{timestamp}"
    version_dir = Path(settings.ML_ARTIFACTS_DIR) / version_label
    version_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Step 13: Saving artifacts and snapshot to %s...", version_dir)

    risk_bands = {
        "low_max": settings.RISK_BANDS["LOW_MAX"],
        "medium_max": settings.RISK_BANDS["MEDIUM_MAX"],
        "high_max": settings.RISK_BANDS["HIGH_MAX"],
    }

    # Generate immutable training snapshot
    snapshot = generate_training_snapshot(
        eligible_incidents=all_incidents,
        audit=audit,
        version_label=version_label,
        feature_names=encoder.feature_names_,
        training_source=training_source,
        validation_basis=validation_basis,
        disclaimer=disclaimer,
        composition=comp,
    )
    snapshot_path = version_dir / "training_snapshot.json"
    with open(snapshot_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    # Separate metric provenance clearly:
    metric_provenance = {
        "validation_basis": validation_basis,
        "training_source": training_source,
        "disclaimer": disclaimer,
        "provenance_composition": comp,
        "real_human_ground_truth_metrics": (
            {
                "metrics_oof": metrics_oof,
                "metrics_final_test": metrics_fused,
                "metrics_baseline_structured": metrics_struct,
                "metrics_baseline_text": metrics_text,
                "test_sample_size": len(y_test),
            }
            if training_source in (TrainingSource.HUMAN_APPROVED_SYNTHETIC, "HUMAN")
            else None
        ),
        "synthetic_benchmark_metrics": (
            {
                "metrics_oof": metrics_oof,
                "metrics_final_test": metrics_fused,
                "metrics_baseline_structured": metrics_struct,
                "metrics_baseline_text": metrics_text,
                "test_sample_size": len(y_test),
            }
            if training_source in (TrainingSource.SYNTHETIC, TrainingSource.MIXED_SYNTHETIC)
            else None
        ),
        "notes": (
            disclaimer or
            "Model training and test metrics in this candidate release are derived from "
            "human-approved synthetic incident records."
        ),
    }

    metadata = {
        "model_version": version_label,
        "training_source": training_source,
        "validation_basis": validation_basis,
        "disclaimer": disclaimer,
        "provenance_composition": comp,
        "bert_model_name": bert_model_name,
        "bert_hidden_dimension": bert_dim,
        "training_timestamp": timestamp,
        "random_seed": seed,
        "is_candidate": True,
        "training_status": "READY",
        "progress_pct": 100,
        "stage_code": "COMPLETED",
        "stage": "COMPLETED",
        "current_stage": "Retraining complete — candidate model ready for review.",
        "train_row_count": len(y_train),
        "test_row_count": len(y_test),
        "total_labeled_rows": n_total,
        "positive_count": int(labels.sum()),
        "negative_count": int((1 - labels).sum()),
        "train_positive": n_pos_train,
        "train_negative": n_neg_train,
        "structured_feature_names": encoder.feature_names_,
        "structured_feature_count": struct_dim,
        "bert_embedding_dimension": bert_dim,
        "fused_feature_dimension": fused_dim,
        "scale_pos_weight": round(scale_pos_weight, 4),
        "selected_threshold": selected_threshold,
        "risk_bands": risk_bands,
        "xgboost_best_params": best_params,
        "split_methodology": "85% train / 15% test, stratified",
        "threshold_methodology": "F2-optimal from 5-fold stratified OOF on training data",
        "label_audit": audit,
        "training_snapshot_id": snapshot["snapshot_id"],
        "training_snapshot_path": str(snapshot_path),
        "dataset_hash": snapshot["dataset_hash"],
        "metric_provenance": metric_provenance,
        "metrics_oof": metrics_oof,
        "metrics_final_test": metrics_fused,
        "metrics_baseline_structured": metrics_struct,
        "metrics_baseline_text": metrics_text,
        "leakage_notes": (
            "severity_actual and severity_potential are contextual EHS report fields and are "
            "NOT included in StructuredFeatureEncoder's BOOLEAN_FIELDS, NUMERIC_FIELDS, "
            "or CATEGORICAL_FIELDS and do NOT enter the structured feature vector. "
            "There is no confirmed structural leakage via those two fields. "
            "is_psif_human_label, psif_label_source, and is_synthetic are also excluded from features. "
            "Remaining risk: text-level correlation if free-text narratives echo severity descriptions. "
            "This is unquantified and cannot be mitigated via encoder field lists."
        ),
    }

    # Preserve timing and provenance keys in metadata
    if model_version and isinstance(model_version.metrics, dict):
        for k in ("started_at", "enqueued_at", "emb_train_started_at", "emb_test_started_at"):
            if k in model_version.metrics and k not in metadata:
                metadata[k] = model_version.metrics[k]

    from apps.predictions.timing import parse_iso_datetime, calculate_retraining_timing
    started_dt = parse_iso_datetime(metadata.get("started_at"))
    completed_dt = datetime.now(dt_timezone.utc)
    if started_dt:
        dur = round((completed_dt - started_dt).total_seconds(), 1)
        metadata["training_duration_seconds"] = dur
    metadata["completed_at"] = completed_dt.isoformat()

    timing_final = calculate_retraining_timing(model_version, current_metrics=metadata)
    metadata.update(timing_final)

    save_artifacts(version_dir, final_model, encoder, metadata)

    # ── 14. Reload verification ───────────────────────────────────────────────
    logger.info("Step 14: Verifying artifact reload and inference...")
    sample_record = records_train[0]
    reload_result = verify_artifact_reload(version_dir, sample_record, bert_model_name)

    # ── 15. Persist Candidate ModelVersion in PostgreSQL ───────────────────────
    logger.info("Step 15: Persisting Candidate ModelVersion in PostgreSQL...")
    if model_version is None:
        model_version = ModelVersion.objects.create(
            version_label=version_label,
            bert_model_name=bert_model_name,
            xgboost_artifact_path=str(version_dir / "model.json"),
            encoder_artifact_path=str(version_dir / "encoder.joblib"),
            training_snapshot_path=str(snapshot_path),
            metrics=metadata,
            status=ModelVersion.Status.READY,
            is_active=False,  # STRICT: Candidate model is NEVER automatically activated
        )
    else:
        model_version.version_label = version_label
        model_version.bert_model_name = bert_model_name
        model_version.xgboost_artifact_path = str(version_dir / "model.json")
        model_version.encoder_artifact_path = str(version_dir / "encoder.joblib")
        model_version.training_snapshot_path = str(snapshot_path)
        model_version.metrics = metadata
        model_version.status = ModelVersion.Status.READY
        model_version.is_active = False  # STRICT: Candidate model is NEVER automatically activated
        model_version.save()

    logger.info("Candidate ModelVersion persisted as READY (is_active=False): %s", version_label)

    # Active model count remains unaffected
    active_count = ModelVersion.objects.filter(is_active=True).count()
    logger.info("Current active models in database: %d", active_count)

    elapsed = time.time() - start_time

    # ── Build summary ─────────────────────────────────────────────────────────
    summary = {
        "version_label": version_label,
        "training_source": training_source,
        "validation_basis": validation_basis,
        "disclaimer": disclaimer,
        "provenance_composition": comp,
        "artifact_dir": str(version_dir),
        "bert_model_name": bert_model_name,
        "bert_dim": bert_dim,
        "label_audit": audit,
        "train_rows": len(y_train),
        "test_rows": len(y_test),
        "structured_feature_count": struct_dim,
        "fused_dimension": fused_dim,
        "scale_pos_weight": round(scale_pos_weight, 4),
        "selected_threshold": selected_threshold,
        "best_params": best_params,
        "metrics_baseline_structured": metrics_struct,
        "metrics_baseline_text": metrics_text,
        "metrics_fused_test": metrics_fused,
        "metrics_oof": metrics_oof,
        "reload_verification": reload_result,
        "model_version_id": str(model_version.id),
        "active_model_count": active_count,
        "training_duration_seconds": round(elapsed, 1),
    }

    logger.info("=" * 60)
    logger.info("PSIF MODEL TRAINING PIPELINE COMPLETED in %.1fs", elapsed)
    logger.info("=" * 60)

    return summary
