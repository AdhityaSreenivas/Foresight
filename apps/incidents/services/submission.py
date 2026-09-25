"""
PSIF Platform — Incident submission service

Handles end-to-end processing of newly submitted incident reports:
1. Composite narrative generation
2. Data quality checks (preserves audit trail without altering source data)
3. Provenance assignment
4. ML inference (if active model is available)
5. Embedding generation
6. IOGP Life-Saving Rules classification
"""
import logging
from apps.incidents.models import Incident, IOGPRuleTag
from apps.incidents.services.data_quality import validate_incident_quality
from apps.incidents.services.embedding import generate_and_persist_embeddings
from apps.datasets.ingestion import build_composite_narrative

logger = logging.getLogger(__name__)


def process_new_incident_submission(incident: Incident) -> Incident:
    """
    Runs automated post-submission processing for a new incident report.
    Never assigns human ground-truth labels.
    """
    # 1. Ensure composite narrative is built
    if not incident.composite_narrative:
        composite = build_composite_narrative(
            description=incident.description,
            corrective_actions=incident.corrective_actions,
            witness_statement=incident.witness_statement,
        )
        incident.composite_narrative = composite or incident.description or ""
        incident.save(update_fields=["composite_narrative"])

    # 2. Run Data Quality validation
    dq_record = None
    try:
        from apps.incidents.models import IncidentDataQuality
        dq_record = validate_incident_quality(incident)
        if dq_record.status == IncidentDataQuality.Status.CRITICAL:
            logger.warning(
                "Incident %s rejected by data quality gate (status=CRITICAL). "
                "Skipping ML inference, embeddings, weak labeling, and IOGP tagging.",
                incident.id,
            )
            return incident
    except Exception as exc:
        logger.exception("Data quality check failed for incident %s: %s", incident.id, exc)

    # 3. Ensure provenance is recorded (unreviewed incident)
    if not incident.psif_label_source or incident.psif_label_source == Incident.PsifLabelSource.NONE:
        incident.psif_label_source = Incident.PsifLabelSource.NONE
        incident.is_synthetic = True
        incident.save(update_fields=["is_synthetic", "psif_label_source"])

    # 4. Run ML model inference if active model exists
    try:
        from ml_engine.model_inference import get_active_predictor
        from apps.predictions.models import ModelVersion, PredictionResult

        predictor = get_active_predictor()
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

        if active_version and predictor:
            record = {
                "description": incident.description,
                "corrective_actions": incident.corrective_actions,
                "witness_statement": incident.witness_statement,
                "department": incident.department,
                "location": incident.location,
                "job_task": incident.job_task,
                "equipment_involved": incident.equipment_involved,
                "injury_type": incident.injury_type,
                "body_part": incident.body_part,
                "immediate_cause": incident.immediate_cause,
                "root_cause_category": incident.root_cause_category,
                "severity_actual": incident.severity_actual,
                "severity_potential": incident.severity_potential,
                "near_miss": incident.near_miss,
            }
            pred_output = predictor.predict(record)
            PredictionResult.objects.update_or_create(
                incident=incident,
                defaults={
                    "model_version": active_version,
                    "psif_probability": pred_output.psif_probability,
                    "psif_predicted": pred_output.psif_predicted,
                    "risk_level": pred_output.risk_level,
                    "top_factors": pred_output.top_factors,
                    "is_sparse_input": getattr(pred_output, "is_sparse_input", False),
                    "evidence_strength": getattr(pred_output, "evidence_strength", "MODERATE"),
                    "explanation_detail": getattr(pred_output, "explanation", {}),
                }
            )
    except Exception as exc:
        logger.exception("ML inference failed for incident %s: %s", incident.id, exc)

    # 5. Generate and persist embeddings
    try:
        generate_and_persist_embeddings([incident])
    except Exception as exc:
        logger.exception("Embedding generation failed for incident %s: %s", incident.id, exc)

    # 6. IOGP Life-Saving Rules tagging
    try:
        from apps.predictions.iogp_classifier import classify_iogp_rules

        fields_to_check = {
            "description": incident.description,
            "job_task": incident.job_task,
            "equipment_involved": incident.equipment_involved,
            "immediate_cause": incident.immediate_cause,
            "corrective_actions": incident.corrective_actions,
            "location": incident.location,
            "composite_narrative": incident.composite_narrative,
        }
        iogp_results = classify_iogp_rules(fields_to_check)
        for res in iogp_results:
            IOGPRuleTag.objects.update_or_create(
                incident=incident,
                rule=res["rule"],
                classifier_version=res["classifier_version"],
                defaults={
                    "matched_keywords": res["matched_keywords"],
                    "matched_fields": res["matched_fields"],
                    "classification_method": res["classification_method"],
                    "confidence": res["confidence"],
                }
            )
    except Exception as exc:
        logger.exception("IOGP classification failed for incident %s: %s", incident.id, exc)

    return incident
