"""
PSIF Platform — Model Inference

The single, authoritative entry point for running BERT + XGBoost PSIF predictions.
Both the synchronous single-prediction API view and the Celery batch-processing
task import from this module — there is exactly ONE code path for inference.

Prediction flow (from specification §6, Step 6):
  record dict
    → composite_narrative (from text_preprocessing)
    → BERT embedding (from bert_encoder)      [768-dim vector]
    → structured features (from feature_encoder) [N-dim vector]
    → concatenation: [bert_embedding | structured_features]
    → XGBoost predict_proba
    → probability → risk_level (via probability_to_risk_level)
    → SHAP top_factors (via shap.TreeExplainer)
    → PredictionOutput dataclass

Feature vector order is FIXED and documented here:
    [bert_embedding (768) | structured_features (N)]
This order must remain identical between training and inference.

SHAP explainability:
    The XGBoost model receives the full concatenated feature vector.
    SHAP values are computed over all features.
    - Structured feature dimensions have human-readable names.
    - BERT embedding dimensions (0..767) are NOT individually meaningful.
      Their SHAP contributions are summed into a single "narrative_content"
      factor for human display.
    - Top 5 factors (by |contribution|) are stored in PredictionResult.top_factors.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    xgb = None
    HAS_XGBOOST = False

from .bert_encoder import encode_texts
from .feature_encoder import StructuredFeatureEncoder
from .text_preprocessing import build_composite_narrative, is_sparse_narrative

from .explanation_engine import generate_explanation

logger = logging.getLogger(__name__)


@dataclass
class PredictionOutput:
    """Output of the PSIF prediction pipeline for a single incident."""
    psif_probability: float
    psif_predicted: bool
    risk_level: str
    top_factors: list[dict] = field(default_factory=list)
    is_sparse_input: bool = False
    evidence_strength: str = "Moderate"
    explanation: dict = field(default_factory=dict)
    positive_factors: list[dict] = field(default_factory=list)
    negative_factors: list[dict] = field(default_factory=list)
    analytical_status: str = "AVAILABLE"
    threshold: float = 0.5

    @property
    def psif_score(self) -> float:
        """Alias for model score."""
        return self.psif_probability

    @property
    def binary_classification(self) -> str:
        """Returns PSIF or NOT PSIF."""
        return "PSIF" if self.psif_predicted else "NOT PSIF"


def _load_xgboost_model(artifact_path: str | Path) -> Optional[xgb.Booster]:
    """Load an XGBoost model from its native .json format."""
    if not HAS_XGBOOST or xgb is None:
        return None
    booster = xgb.Booster()
    booster.load_model(str(artifact_path))
    return booster


def _format_feature_name(raw_name: str) -> str:
    """Format a machine feature name into a human-readable display name."""
    if raw_name == "near_miss":
        return "Near miss"
    
    if "=" in raw_name:
        field, value = raw_name.split("=", 1)
        # Format the value
        clean_value = value.replace("_", " ").capitalize()
        if value == "first_aid":
            clean_value = "First-aid"
        
        if field == "severity_potential":
            return f"{clean_value} potential severity"
        elif field == "severity_actual":
            return f"{clean_value} actual severity"
        elif field == "department":
            return f"{clean_value} department"
        elif field == "injury_type":
            return f"{clean_value} injury"
        elif field == "body_part":
            return f"{clean_value} (body part)"
        elif field == "immediate_cause":
            return f"{clean_value} (immediate cause)"
        elif field == "root_cause_category":
            return f"{clean_value} (root cause)"
    
    return raw_name.replace("_", " ").capitalize()


def _parse_shap_1d(
    shap_1d: np.ndarray,
    fused_vector: np.ndarray,
    feature_names: list[str],
    bert_dim: int = 768,
    top_n: int = 5,
    min_abs_contribution: float = 0.001,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Parse 1D SHAP values into top_factors, positive_factors, negative_factors."""
    bert_contribution = float(np.sum(shap_1d[:bert_dim]))
    structured_shap = shap_1d[bert_dim:]
    structured_names = feature_names[bert_dim:]

    field_contributions = {}
    field_active_values = {}

    for name, contrib, val in zip(structured_names, structured_shap, fused_vector[bert_dim:]):
        if "=" in name:
            field, category = name.split("=", 1)
            field_contributions[field] = field_contributions.get(field, 0.0) + float(contrib)
            if val == 1.0:
                field_active_values[field] = category
        else:
            field_contributions[name] = float(contrib)
            field_active_values[name] = val

    factors = []
    if abs(bert_contribution) >= min_abs_contribution:
        factors.append({"feature": "Narrative content", "contribution": bert_contribution})

    for field, total_contrib in field_contributions.items():
        active_cat = field_active_values.get(field, "None")
        if active_cat == "None" or active_cat == "_MISSING_":
            continue

        if isinstance(active_cat, str):
            formatted_name = _format_feature_name(f"{field}={active_cat}")
        else:
            if isinstance(active_cat, (int, float)) and active_cat == 0.0:
                continue
            formatted_name = _format_feature_name(field)

        if abs(total_contrib) >= min_abs_contribution:
            factors.append({
                "feature": formatted_name,
                "contribution": float(total_contrib)
            })

    # Separate positive and negative contributors
    positive_factors = [
        {"feature": f["feature"], "contribution": round(f["contribution"], 4)}
        for f in factors if f["contribution"] > 0
    ]
    negative_factors = [
        {"feature": f["feature"], "contribution": round(f["contribution"], 4)}
        for f in factors if f["contribution"] < 0
    ]
    positive_factors.sort(key=lambda x: x["contribution"], reverse=True)
    negative_factors.sort(key=lambda x: x["contribution"])

    # Top factors ordered by magnitude
    all_sorted = sorted(factors, key=lambda x: abs(x["contribution"]), reverse=True)
    top_factors = all_sorted[:top_n]

    return top_factors, positive_factors, negative_factors


def _compute_shap_factors(
    booster: xgb.Booster,
    fused_vector: np.ndarray,
    feature_names: list[str],
    psif_predicted: bool,
    bert_dim: int = 768,
    top_n: int = 5,
    min_abs_contribution: float = 0.001,
    explainer: Optional[Any] = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Compute SHAP values for one prediction and return:
      (top_factors, positive_factors, negative_factors)

    Features that push toward PSIF (positive contribution) and features that pull
    toward NOT PSIF (negative contribution) are explicitly separated.
    BERT embedding dimensions are aggregated into a single "Narrative content" factor.
    """
    try:
        import shap

        if explainer is None:
            explainer = shap.TreeExplainer(booster)

        shap_values = explainer.shap_values(fused_vector.reshape(1, -1))
        if isinstance(shap_values, list):
            shap_values = shap_values[1]  # class 1 (PSIF positive)
        shap_1d = shap_values.flatten()

        return _parse_shap_1d(
            shap_1d=shap_1d,
            fused_vector=fused_vector,
            feature_names=feature_names,
            bert_dim=bert_dim,
            top_n=top_n,
            min_abs_contribution=min_abs_contribution,
        )

    except Exception as exc:
        logger.warning("SHAP computation failed: %s — returning empty factors", exc)
        return [], [], []


def _compute_shap_top_factors(
    booster: xgb.Booster,
    fused_vector: np.ndarray,
    feature_names: list[str],
    psif_predicted: bool,
    bert_dim: int = 768,
    top_n: int = 5,
    min_abs_contribution: float = 0.001,
) -> list[dict]:
    """Compatibility wrapper returning top factors list."""
    top_factors, _, _ = _compute_shap_factors(
        booster, fused_vector, feature_names, psif_predicted, bert_dim, top_n, min_abs_contribution
    )
    return top_factors


class PSIFPredictor:
    """
    Stateful predictor that holds loaded model artifacts.
    Instantiated once at startup (or on first use) and reused.

    Thread safety: read-only after __init__, safe for concurrent use
    in a single-process web server.
    """

    def __init__(
        self,
        xgboost_artifact_path: str | Path,
        encoder_artifact_path: str | Path,
        bert_model_name: str,
        psif_threshold: float = 0.5,
        bert_dim: int | None = None,
    ) -> None:
        from apps.predictions.models import probability_to_risk_level  # avoid circular import
        self._risk_fn = probability_to_risk_level

        self.bert_model_name = bert_model_name
        self.psif_threshold = psif_threshold

        logger.info("Loading XGBoost model from %s", xgboost_artifact_path)
        self.booster = _load_xgboost_model(xgboost_artifact_path)

        logger.info("Loading structured feature encoder from %s", encoder_artifact_path)
        self.encoder = StructuredFeatureEncoder.load(encoder_artifact_path)

        # Determine BERT hidden dimension from model config, not hardcoded
        if bert_dim is not None:
            self.bert_dim = bert_dim
        else:
            try:
                _, model = _get_model_and_tokenizer(bert_model_name)
                self.bert_dim = model.config.hidden_size
            except Exception:
                self.bert_dim = 768  # safe fallback
                logger.warning("Could not determine BERT hidden size from model config; using default 768")

        self.feature_names: list[str] = (
            [f"bert_{i}" for i in range(self.bert_dim)]
            + self.encoder.feature_names_
        )

        try:
            import shap
            self.explainer = shap.TreeExplainer(self.booster)
        except Exception as e:
            logger.warning("Could not initialize TreeExplainer: %s", e)
            self.explainer = None

        logger.info("PSIFPredictor ready | threshold=%.2f | bert_dim=%d", psif_threshold, self.bert_dim)

    def predict(self, record: dict) -> PredictionOutput:
        """
        Run the full pipeline for a single incident record.
        Returns in a few seconds on CPU (one BERT forward pass).
        """
        narrative = build_composite_narrative(
            description=record.get("description"),
            corrective_actions=record.get("corrective_actions"),
            witness_statement=record.get("witness_statement"),
        )

        bert_vec = encode_texts([narrative], model_name=self.bert_model_name, batch_size=1)[0]
        struct_vec = self.encoder.transform_single(record)
        fused = np.concatenate([bert_vec, struct_vec])

        dmat = xgb.DMatrix(fused.reshape(1, -1), feature_names=self.feature_names)
        prob = float(self.booster.predict(dmat)[0])
        


        predicted = prob >= self.psif_threshold
        risk_level = self._risk_fn(prob)

        top_factors, pos_factors, neg_factors = _compute_shap_factors(
            self.booster, fused, self.feature_names, predicted, bert_dim=self.bert_dim, explainer=self.explainer
        )

        is_sparse = is_sparse_narrative(narrative)

        explanation = generate_explanation(
            record=record,
            narrative=narrative,
            psif_score=prob,
            psif_predicted=predicted,
            threshold=self.psif_threshold,
            shap_factors=pos_factors + neg_factors,
            dq_findings=None,
        )

        return PredictionOutput(
            psif_probability=prob,
            psif_predicted=predicted,
            risk_level=risk_level,
            top_factors=top_factors,
            is_sparse_input=is_sparse,
            evidence_strength=explanation.get("evidence_strength", "Moderate"),
            explanation=explanation,
            positive_factors=pos_factors,
            negative_factors=neg_factors,
            analytical_status=explanation.get("analytical_status", "AVAILABLE"),
        )

    def predict_batch(self, records: list[dict]) -> list[PredictionOutput]:
        """
        Batch predict for efficiency (batched BERT forward pass).
        Used by the Celery dataset-processing task.

        Returns list of PredictionOutput in the same order as records.
        """
        if not records:
            return []

        from django.conf import settings
        batch_size = settings.BERT_BATCH_SIZE

        narratives = [
            build_composite_narrative(
                description=r.get("description"),
                corrective_actions=r.get("corrective_actions"),
                witness_statement=r.get("witness_statement"),
            )
            for r in records
        ]

        logger.info("BERT batch encoding %d records", len(records))
        bert_matrix = encode_texts(narratives, model_name=self.bert_model_name, batch_size=batch_size)

        logger.info("Encoding structured features for %d records", len(records))
        struct_matrix = self.encoder.transform(records)

        fused_matrix = np.hstack([bert_matrix, struct_matrix])

        dmat = xgb.DMatrix(fused_matrix, feature_names=self.feature_names)
        probs = self.booster.predict(dmat)

        # Vectorized batch SHAP computation across entire chunk
        shap_matrix = None
        if self.explainer is not None:
            try:
                shap_matrix = self.explainer.shap_values(fused_matrix)
                if isinstance(shap_matrix, list):
                    shap_matrix = shap_matrix[1]
            except Exception as e:
                logger.warning("Batch SHAP computation failed (%s) — using fallback", e)
                shap_matrix = None

        results = []
        for i, (prob, record) in enumerate(zip(probs, records)):
            prob_f = float(prob)
            predicted = prob_f >= self.psif_threshold
            risk_level = self._risk_fn(prob_f)

            # SHAP factors from vectorized matrix or fallback
            if shap_matrix is not None:
                top_factors, pos_factors, neg_factors = _parse_shap_1d(
                    shap_matrix[i], fused_matrix[i], self.feature_names, bert_dim=self.bert_dim
                )
            else:
                top_factors, pos_factors, neg_factors = _compute_shap_factors(
                    self.booster, fused_matrix[i], self.feature_names, predicted,
                    bert_dim=self.bert_dim, explainer=self.explainer
                )

            is_sparse = is_sparse_narrative(narratives[i])

            explanation = generate_explanation(
                record=record,
                narrative=narratives[i],
                psif_score=prob_f,
                psif_predicted=predicted,
                threshold=self.psif_threshold,
                shap_factors=pos_factors + neg_factors,
                dq_findings=None,
            )

            results.append(PredictionOutput(
                psif_probability=prob_f,
                psif_predicted=predicted,
                risk_level=risk_level,
                top_factors=top_factors,
                is_sparse_input=is_sparse,
                evidence_strength=explanation.get("evidence_strength", "Moderate"),
                explanation=explanation,
                positive_factors=pos_factors,
                negative_factors=neg_factors,
                analytical_status=explanation.get("analytical_status", "AVAILABLE"),
            ))

        return results


# ── Module-level singleton ─────────────────────────────────────────────────────
# The active predictor is loaded lazily on first use and cached here.
_active_predictor: Optional[PSIFPredictor] = None
_active_model_id: Optional[str] = None


def reset_active_predictor() -> None:
    """Reset cached active predictor singleton to force reload on next prediction."""
    global _active_predictor, _active_model_id
    _active_predictor = None
    _active_model_id = None
    logger.info("Active predictor singleton reset successfully.")


def get_active_predictor(force_reload: bool = False) -> Optional[PSIFPredictor]:
    """
    Return the module-level PSIFPredictor loaded from the active ModelVersion.
    Returns None if no active model version exists yet or if running in a serverless
    environment without XGBoost installed.
    Reloads if the active model version has changed or force_reload is True.
    """
    global _active_predictor, _active_model_id

    if not HAS_XGBOOST:
        logger.info("XGBoost not installed in serverless environment — predictions served by external worker")
        return None

    from django.conf import settings
    from apps.predictions.models import ModelVersion  # avoid circular import at module load

    try:
        active_version = (
            ModelVersion.objects.filter(is_active=True, status=ModelVersion.Status.ACTIVE)
            .exclude(xgboost_artifact_path="")
            .first()
        )
        if not active_version:
            active_version = (
                ModelVersion.objects.filter(is_active=True)
                .exclude(xgboost_artifact_path="")
                .first()
            )
        if not active_version:
            active_version = ModelVersion.objects.filter(is_active=True).first()
    except Exception:
        # DB may not be ready (e.g., during migrations)
        return None

    if active_version is None:
        logger.warning("No active ModelVersion found — predictions unavailable")
        _active_predictor = None
        _active_model_id = None
        return None

    # Verify that the artifact exists on disk; if not, check for a valid ready model with existing artifacts
    xgb_path = Path(active_version.xgboost_artifact_path) if active_version.xgboost_artifact_path else None
    if not xgb_path or not xgb_path.exists():
        valid_fallback = None
        for mv in ModelVersion.objects.exclude(xgboost_artifact_path="").order_by("-is_active", "-trained_at"):
            if mv.xgboost_artifact_path and Path(mv.xgboost_artifact_path).exists():
                valid_fallback = mv
                break
        if valid_fallback:
            logger.info("Falling back to valid model version %s with existing disk artifacts", valid_fallback.version_label)
            active_version = valid_fallback
        else:
            logger.warning("Active model version %s has missing artifact file: %s", getattr(active_version, "version_label", "?"), getattr(active_version, "xgboost_artifact_path", ""))
            return None

    # Reload if the predictor doesn't exist or the active version changed
    if _active_predictor is None or _active_model_id != str(active_version.id) or force_reload:
        # Try to load threshold and bert_dim from model metadata
        threshold = settings.PSIF_THRESHOLD
        bert_dim = None
        try:
            metadata = active_version.metrics or {}
            if "selected_threshold" in metadata:
                threshold = metadata["selected_threshold"]
            if "bert_hidden_dimension" in metadata:
                bert_dim = metadata["bert_hidden_dimension"]
        except Exception:
            pass  # fall back to settings defaults

        _active_predictor = PSIFPredictor(
            xgboost_artifact_path=active_version.xgboost_artifact_path,
            encoder_artifact_path=active_version.encoder_artifact_path,
            bert_model_name=active_version.bert_model_name,
            psif_threshold=threshold,
            bert_dim=bert_dim,
        )
        _active_model_id = str(active_version.id)
        logger.info("Loaded active predictor for model version %s (ID: %s)", active_version.version_label, active_version.id)

    return _active_predictor


def predict(record: dict) -> Optional[PredictionOutput]:
    """
    Module-level convenience function for single-record prediction.
    Used by the synchronous /api/predict/ view.
    """
    predictor = get_active_predictor()
    if predictor is None:
        return None
    return predictor.predict(record)


def predict_batch(records: list[dict]) -> list[Optional[PredictionOutput]]:
    """
    Module-level convenience function for batch prediction.
    Used by the Celery dataset-processing task.
    """
    predictor = get_active_predictor()
    if predictor is None:
        return [None] * len(records)
    return predictor.predict_batch(records)
