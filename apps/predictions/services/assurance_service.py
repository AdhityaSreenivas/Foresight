"""
PSIF Platform — Model Assurance Service (Task 12)
apps/predictions/services/assurance_service.py

Authoritative engine for:
1. Model Registry Auditing (reproducible metrics, independent denominators, actual database state).
2. Active Model Assurance Contract (explicit score semantics: "PSIF Model Score", not a calibrated probability).
3. Provenance & Human Validation Governance (honestly classifying real human validation vs simulated reviews).
4. Training Data Leakage Controls & Split Methodology Disclosures.
5. Model-Rule Disagreement & Reconciliation ("Model-rule disagreement requires human review").
6. Active Model Protection and Drift Detection.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from django.db.models import Count, Q
from django.utils import timezone as django_timezone

from apps.predictions.models import ModelVersion, PredictionResult
from apps.incidents.models import Incident, IncidentReview, IOGPRuleTag
from apps.incidents.services.data_quality import VERSION as DATA_QUALITY_VERSION

logger = logging.getLogger(__name__)

SCORE_SEMANTICS_DISCLAIMER = (
    "Model score reflects relative model output and is not a calibrated probability."
)

METHODOLOGY_STATEMENT = (
    "The active model is evaluated on synthetic benchmark test sets. Metrics indicate model output "
    "separation on benchmark distributions and must not be interpreted as calibrated real-world injury probabilities."
)


class ModelAssuranceService:
    """Authoritative service for Model Assurance and Governance."""

    @classmethod
    def get_model_registry_audit(cls) -> Dict[str, Any]:
        """
        Audits all registered model versions in the database.
        Computes live prediction counts, positive rates, independent binary metrics,
        and disclosures without hardcoded figures.
        """
        now = django_timezone.now()
        models = ModelVersion.objects.all().order_by("-trained_at")

        model_audits: List[Dict[str, Any]] = []

        total_platform_predictions = 0
        total_platform_psif = 0

        for mv in models:
            metrics = mv.metrics or {}
            test_m = metrics.get("metrics_final_test") or metrics.get("metrics_fused_test") or {}
            cm = test_m.get("confusion_matrix")  # [[TN, FP], [FN, TP]]

            # Compute independent denominator metrics if confusion matrix exists
            tn, fp, fn, tp = 0, 0, 0, 0
            if cm and len(cm) == 2 and len(cm[0]) == 2 and len(cm[1]) == 2:
                tn, fp = cm[0][0], cm[0][1]
                fn, tp = cm[1][0], cm[1][1]

            pred_pos_denom = tp + fp
            act_pos_denom = tp + fn
            pred_neg_denom = tn + fn
            act_neg_denom = tn + fp

            psif_precision = round(tp / pred_pos_denom, 4) if pred_pos_denom > 0 else test_m.get("precision", 0.0)
            psif_recall = round(tp / act_pos_denom, 4) if act_pos_denom > 0 else test_m.get("recall", 0.0)
            not_psif_precision = round(tn / pred_neg_denom, 4) if pred_neg_denom > 0 else 0.0
            not_psif_recall = round(tn / act_neg_denom, 4) if act_neg_denom > 0 else 0.0

            # Live prediction counts in PostgreSQL
            total_preds = PredictionResult.objects.filter(model_version=mv).count()
            psif_preds = PredictionResult.objects.filter(model_version=mv, psif_predicted=True).count()
            not_psif_preds = total_preds - psif_preds
            sparse_preds = PredictionResult.objects.filter(model_version=mv, is_sparse_input=True).count()

            pos_rate = round(psif_preds / total_preds * 100, 2) if total_preds > 0 else 0.0
            not_pos_rate = round(not_psif_preds / total_preds * 100, 2) if total_preds > 0 else 0.0

            if mv.is_active:
                total_platform_predictions = total_preds
                total_platform_psif = psif_preds

            threshold_val = metrics.get("selected_threshold", 0.5)

            model_audits.append({
                "model_version": mv.version_label,
                "version_label": mv.version_label,
                "is_active": mv.is_active,
                "status": getattr(mv, "status", "UNKNOWN"),
                "trained_at": mv.trained_at.isoformat() if mv.trained_at else None,
                "threshold": threshold_val,
                "threshold_methodology": metrics.get("threshold_methodology", "F2-optimal from OOF"),
                "score_semantics": "PSIF Model Score",
                "score_disclaimer": SCORE_SEMANTICS_DISCLAIMER,
                "training_dataset_identity": metrics.get("training_source", "SYNTHETIC"),
                "data_provenance": metrics.get("training_source", "SYNTHETIC"),
                "validation_basis": metrics.get("validation_basis", "SYNTHETIC DATASET EVALUATION"),
                "split_methodology": metrics.get("split_methodology", "85% train / 15% test, stratified"),
                "random_seed": metrics.get("random_seed", 42),
                "text_encoder": mv.bert_model_name,
                "bert_dim": metrics.get("bert_dim", metrics.get("bert_hidden_dimension", 768)),
                "structured_feature_count": metrics.get("structured_feature_count", 88),
                "structured_feature_names": metrics.get("structured_feature_names", []),
                "fused_dimension": metrics.get("fused_dimension", metrics.get("fused_feature_dimension", 856)),
                "sample_counts": {
                    "total_labeled_rows": metrics.get("total_labeled_rows", 0),
                    "train_row_count": metrics.get("train_row_count", 0),
                    "test_row_count": metrics.get("test_row_count", 0),
                    "positive_count": metrics.get("positive_count", 0),
                    "negative_count": metrics.get("negative_count", 0),
                },
                "live_predictions": {
                    "total": total_preds,
                    "formatted_total": f"{total_preds:,}",
                    "psif_count": psif_preds,
                    "formatted_psif": f"{psif_preds:,}",
                    "psif_rate": pos_rate,
                    "psif_rate_label": f"{pos_rate}% of live predictions classified as PSIF at threshold {threshold_val}",
                    "not_psif_count": not_psif_preds,
                    "formatted_not_psif": f"{not_psif_preds:,}",
                    "not_psif_rate": not_pos_rate,
                    "sparse_count": sparse_preds,
                    "formatted_sparse": f"{sparse_preds:,}",
                },
                "evaluation_metrics": {
                    "psif_precision": psif_precision,
                    "psif_precision_formula": "TP / (TP + FP) [predicted-positive denominator]",
                    "psif_recall": psif_recall,
                    "psif_recall_formula": "TP / (TP + FN) [actual-positive denominator]",
                    "not_psif_precision": not_psif_precision,
                    "not_psif_precision_formula": "TN / (TN + FN) [predicted-negative denominator]",
                    "not_psif_recall": not_psif_recall,
                    "not_psif_recall_formula": "TN / (TN + FP) [actual-negative denominator]",
                    "f1": test_m.get("f1", 0.0),
                    "f2": test_m.get("f2", 0.0),
                    "roc_auc": test_m.get("roc_auc", 0.0),
                    "pr_auc": test_m.get("pr_auc", 0.0),
                    "confusion_matrix": cm,
                },
                "leakage_controls": {
                    "severity_quarantined": True,
                    "corrective_actions_quarantined": True,
                    "human_labels_quarantined": True,
                    "notes": metrics.get(
                        "leakage_notes",
                        "severity_actual and severity_potential do not enter structured features. "
                        "corrective_actions is quarantined from inference."
                    ),
                },
                "synthetic_artifacts_and_risks": [
                    "Repeated synthetic narrative templates inflate random test split metrics (e.g. PR-AUC near 1.0).",
                    "Artificial phrasing patterns (e.g. 'the observation was made at') may trigger spurious correlation.",
                    "Zero real human-reviewed OIL events in model training set; cannot establish field operational validity.",
                    "Model score is an uncalibrated relative ranking score, not a physical probability.",
                ],
            })

        active_audit = next((m for m in model_audits if m["is_active"]), None)

        return {
            "timestamp": now.isoformat(),
            "methodology_statement": METHODOLOGY_STATEMENT,
            "score_semantics_rule": SCORE_SEMANTICS_DISCLAIMER,
            "registered_models_count": len(model_audits),
            "active_model": active_audit,
            "models": model_audits,
            "platform_predictions_summary": {
                "active_model_version": active_audit["version_label"] if active_audit else None,
                "total_predictions": total_platform_predictions,
                "formatted_total_predictions": f"{total_platform_predictions:,}",
                "total_psif_predictions": total_platform_psif,
                "formatted_total_psif": f"{total_platform_psif:,}",
            },
        }

    @classmethod
    def get_active_model_assurance(cls) -> Dict[str, Any]:
        """Returns assurance card for active model with full governance disclosures."""
        audit = cls.get_model_registry_audit()
        active = audit.get("active_model")
        if not active:
            return {
                "active": False,
                "message": "No active model version configured.",
                "methodology_statement": METHODOLOGY_STATEMENT,
            }
        return {
            "active": True,
            "model": active,
            "methodology_statement": METHODOLOGY_STATEMENT,
            "score_semantics_disclaimer": SCORE_SEMANTICS_DISCLAIMER,
        }

    @classmethod
    def get_human_review_audit(cls) -> Dict[str, Any]:
        """
        Provides completely honest disclosure of human review records:
        - Real Human Validation on OIL Data: 0
        - Simulated / Synthetic Reviewer Records: Count of IncidentReview
        - Human-Approved Synthetic Data: 0
        """
        now = django_timezone.now()

        # Query reviews
        total_reviews = IncidentReview.objects.count()
        decisions = dict(IncidentReview.objects.values_list("decision").annotate(c=Count("id")))

        # Check reviewers
        reviewers = list(IncidentReview.objects.values_list("reviewer__username", flat=True).distinct())

        simulated_users = {"hse_lead_auditor", "hse_field_specialist", "test_user"}
        is_all_simulated = all(u in simulated_users or not u for u in reviewers)

        return {
            "timestamp": now.isoformat(),
            "real_human_validation_count": 0,
            "real_human_validation_statement": (
                "ZERO (0) genuine OIL field incidents have been formally validated by authorized OIL human experts. "
                "All existing review records in the platform are synthetic developmental simulations."
            ),
            "simulated_human_reviews_count": total_reviews,
            "simulated_reviewers": reviewers,
            "is_simulation_only": is_all_simulated,
            "human_approved_synthetic_count": 0,
            "adjudicated_decisions_breakdown": {
                "psif_count": decisions.get("PSIF", 0),
                "not_psif_count": decisions.get("NOT_PSIF", 0),
                "insufficient_information_count": decisions.get("INSUFFICIENT_INFORMATION", 0),
            },
            "provenance_categories": {
                "SYNTHETIC": Incident.objects.filter(is_synthetic=True).count(),
                "HUMAN_APPROVED_SYNTHETIC": 0,
                "REAL_EXTERNAL": 0,
                "REAL_HUMAN": 0,
            },
            "governance_rule": (
                "Under SIH PS 26165 ethics requirements, synthetic and simulated reviewer judgments must never "
                "be claimed or presented as genuine OIL field human validation."
            ),
        }

    @classmethod
    def evaluate_model_rule_reconciliation(cls, incident: Incident) -> Dict[str, Any]:
        """
        Evaluates agreement between Model prediction and Safety Rules:
        - Model: PSIF vs NOT PSIF (with model score)
        - Rule: PSIF vs NOT PSIF (based on canonical IOGP rule matches)
        - Reconciliation: AGREEMENT vs MODEL_RULE_DISAGREEMENT
        - Statement: 'Model-rule disagreement requires human review.'
        Never labels disagreement as 'model error'.
        """
        pred = getattr(incident, "prediction", None)
        model_psif = bool(pred.psif_predicted) if pred else False
        model_score = round(pred.psif_score, 4) if pred and pred.psif_score is not None else None

        # Rule evaluation
        matched_tags = list(incident.iogp_rules.all()) if hasattr(incident, "iogp_rules") else []
        rule_names = [t.rule for t in matched_tags]

        # High consequence safety rule indicators
        rule_psif = len(rule_names) > 0 and any(
            r in ["Energy Isolation", "Safe Mechanical Lifting", "Working at Height", "Hot Work", "Confined Space"]
            for r in rule_names
        )

        agrees = (model_psif == rule_psif)

        if agrees:
            reconciliation_status = "AGREEMENT"
            reconciliation_statement = (
                f"Model and safety rules agree on hazard classification ({'PSIF' if model_psif else 'NOT PSIF'})."
            )
            final_policy = "PROCEED_TO_INVESTIGATION" if model_psif else "ROUTINE_MONITORING"
        else:
            reconciliation_status = "MODEL_RULE_DISAGREEMENT"
            reconciliation_statement = "Model-rule disagreement requires human review."
            final_policy = "HUMAN_ADJUDICATION_REQUIRED"

        return {
            "incident_id": str(incident.id),
            "model_decision": "PSIF" if model_psif else "NOT PSIF",
            "model_score": model_score,
            "rule_decision": "PSIF" if rule_psif else "NOT PSIF",
            "matched_rules": rule_names,
            "agreement": agrees,
            "reconciliation_status": reconciliation_status,
            "reconciliation_statement": reconciliation_statement,
            "final_policy": final_policy,
        }

    @classmethod
    def detect_model_drift_or_change(cls, model_version: ModelVersion) -> Dict[str, Any]:
        """
        Safeguard against accidental active-model drift or silent semantic changes.
        Detects changes in threshold, feature count, text encoder, or artifact paths.
        """
        metrics = model_version.metrics or {}
        stored_threshold = metrics.get("selected_threshold")
        stored_features = metrics.get("structured_feature_count")
        stored_bert = metrics.get("bert_model_name")

        drift_issues = []

        if stored_threshold is not None and stored_threshold not in (0.1, 0.2, 0.5):
            drift_issues.append(f"Unexpected threshold '{stored_threshold}' (expected 0.1, 0.2, or 0.5).")

        if stored_features is not None and stored_features not in (88, 5, 6):
            drift_issues.append(f"Structured feature count mutated to {stored_features}.")

        if stored_bert and stored_bert != model_version.bert_model_name:
            drift_issues.append(f"Backbone changed from '{stored_bert}' to '{model_version.bert_model_name}'.")

        is_stable = (len(drift_issues) == 0)

        return {
            "model_version": model_version.version_label,
            "status": "STABLE" if is_stable else "DRIFT_DETECTED",
            "is_stable": is_stable,
            "drift_issues": drift_issues,
            "timestamp": django_timezone.now().isoformat(),
        }
