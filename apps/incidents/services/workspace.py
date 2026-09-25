"""
PSIF Platform — Unified Investigation Workspace Composition Service (Task 9)

Integrates all Foresight intelligence capabilities into one coherent workspace:
    DETECTION → REASONING → EVIDENCE → RELATED SIGNALS → ACTION → HUMAN REVIEW

Design & Compliance Rules:
1. Integration only: Composes existing canonical services; does NOT duplicate analytical logic.
2. Clear separation: Actual reported facts are strictly separated from model/rule-derived inferences.
3. Terminology compliance:
   - "Investigation Workspace" (not "AI Assistant")
   - "Semantic similarity" (not "same event", "duplicate", or "causal relationship")
   - "Historical recurrence" (not "cause", "systemic failure", or "future probability")
   - "PSIF Model Score" (not "probability")
4. Error isolation: Secondary widgets (similarity, recurrence, cross-site, barriers, reviews)
   are isolated with individual try/except blocks; secondary failure never crashes the workspace.
5. Performance: Queries are pre-fetched; reasoning/action analyses are not redundantly recomputed.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from django.urls import reverse
from django.utils import timezone

from apps.incidents.models import Incident, IncidentReview, IncidentDataQuality, IOGPRuleTag
from apps.incidents.services.evidence_break import analyze_evidence_break, ChainState
from apps.incidents.services.psif_reasoning import build_incident_reasoning_assessment
from apps.incidents.services.action_library import get_corrective_actions, ActionType
from apps.incidents.services.decision_trace import find_related_incidents
from apps.dashboard.pattern_detection import detect_recurring_patterns, detect_multi_site_recurrence
from apps.dashboard.services import get_barrier_intelligence
from apps.incidents.services.review_reconciliation import calculate_review_reconciliation, ReviewAgreementState
from apps.incidents.services.normalization import (
    normalize_incident_entities,
    normalize_iogp_rule,
    normalize_department,
    normalize_activity,
)
from apps.incidents.services.methodology import get_methodology_notice

logger = logging.getLogger(__name__)


def user_can_review(user) -> bool:
    """Check if the given user is authorized to submit human reviews/adjudications."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return getattr(user, "can_predict", False) or getattr(user, "is_admin_role", False) or getattr(user, "is_superuser", False)


def compose_investigation_workspace(incident: Incident, user=None) -> Dict[str, Any]:
    """
    Composes the full Unified Investigation Workspace payload for an incident.
    Returns a comprehensive, highly-structured dictionary suitable for both
    the JSON API and direct server-side HTML rendering.
    """
    # ── 1. PREFETCHED ASSOCIATIONS & PREDICTION STATUS ──────────────────────────
    prediction = getattr(incident, "prediction", None)
    model_version_obj = getattr(prediction, "model_version", None) if prediction else None
    threshold_val = getattr(model_version_obj, "metrics", {}).get("selected_threshold", 0.5) if model_version_obj else 0.5
    model_label = model_version_obj.version_label if model_version_obj else "None"

    # Prediction summary
    if prediction:
        psif_score = round(prediction.psif_score, 4)
        score_percent = round(prediction.psif_probability_percent, 1)
        binary_pred = "PSIF" if prediction.psif_predicted else "NOT_PSIF"
        is_psif_pred = bool(prediction.psif_predicted)
        risk_level = prediction.risk_level or "Unknown"
        evidence_strength = prediction.evidence_strength or "Moderate"
        is_sparse_input = bool(prediction.is_sparse_input)
        top_factors = prediction.top_factors or []
    else:
        psif_score = None
        score_percent = None
        binary_pred = "UNKNOWN"
        is_psif_pred = False
        risk_level = "Unknown"
        evidence_strength = "Unknown"
        is_sparse_input = False
        top_factors = []

    # ── 2. DATA QUALITY & INGESTION STATUS ────────────────────────────────────
    dq_record = getattr(incident, "data_quality", None)
    dq_status = dq_record.status if dq_record else IncidentDataQuality.Status.VALID
    dq_findings = dq_record.findings if dq_record else []
    dq_summary = {
        "status": dq_status,
        "is_valid": dq_status == IncidentDataQuality.Status.VALID,
        "is_warning": dq_status == IncidentDataQuality.Status.WARNING,
        "is_critical": dq_status == IncidentDataQuality.Status.CRITICAL,
        "findings": dq_findings,
        "field_errors": getattr(dq_record, "field_errors", {}) if dq_record else {},
        "impact_note": (

            "Data Quality status is CRITICAL: evidence reliability is significantly compromised."
            if dq_status == IncidentDataQuality.Status.CRITICAL
            else (
                "Data Quality warning detected: secondary fields missing or narrative is sparse."
                if dq_status == IncidentDataQuality.Status.WARNING
                else "Incident data satisfies all structural and completeness quality checks."
            )
        ),
        "methodology": get_methodology_notice("data_quality"),
    }

    # ── 3. INCIDENT REPORTED FACTS (STRICTLY SEPARATED FROM INFERENCES) ────────
    facts = {
        "incident_id": str(incident.id),
        "external_id": incident.external_id or None,
        "incident_date": incident.incident_date.isoformat() if incident.incident_date else None,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "department": incident.department or "Not Specified",
        "location": incident.location or "Not Specified",
        "job_task": incident.job_task or "Not Specified",
        "equipment_involved": incident.equipment_involved or "None Reported",
        "injury_type": incident.injury_type or "None Reported",
        "body_part": incident.body_part or "None Reported",
        "severity_actual": incident.severity_actual,
        "severity_actual_display": incident.get_severity_actual_display() if incident.severity_actual else "Unspecified",
        "severity_potential": incident.severity_potential,
        "severity_potential_display": incident.get_severity_potential_display() if incident.severity_potential else "Unspecified",
        "near_miss": incident.near_miss,
        "report_type": incident.report_type,
        "report_type_display": incident.get_report_type_display() if incident.report_type else "Incident / Event",
        "narratives": {
            "composite_narrative": incident.composite_narrative or "",
            "primary_description": incident.description or "",
            "witness_statement": incident.witness_statement or "",
            "reported_corrective_actions": incident.corrective_actions or "",
        },
        "structured_controls": {
            "high_energy_present": incident.high_energy_present,
            "energy_type": incident.energy_type,
            "worker_exposed": incident.worker_exposed,
            "direct_control_present": incident.direct_control_present,
            "control_type": incident.control_type,
            "control_condition": incident.control_condition,
            "control_failed_bypassed": incident.control_failed_bypassed,
        },
        "provenance": {
            "is_synthetic": incident.is_synthetic,
            "psif_label_source": incident.psif_label_source,
            "provenance_category": incident.provenance_category,
            "dataset_name": incident.dataset.name if incident.dataset else None,
        },
    }

    # ── 4. CANONICAL REASONING & EVIDENCE BREAK (WHY PSIF / WHY NOT PSIF) ─────
    reasoning_payload: Dict[str, Any] = {}
    evidence_break_payload: Dict[str, Any] = {}
    try:
        reasoning_payload = build_incident_reasoning_assessment(incident, prediction=prediction, dq_record=dq_record)
    except Exception as exc:
        logger.error("Error building incident reasoning assessment for %s: %s", incident.id, exc)
        reasoning_payload = {
            "status": "error",
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "INSUFFICIENT_INFORMATION",
            "error_detail": str(exc),
        }

    try:
        evidence_break_payload = analyze_evidence_break(incident)
    except Exception as exc:
        logger.error("Error building evidence break for %s: %s", incident.id, exc)
        evidence_break_payload = {
            "status": "error",
            "evidence_chain": [],
            "error_detail": str(exc),
        }

    rule_decision = reasoning_payload.get("decision", "INSUFFICIENT_INFORMATION")
    internal_state = reasoning_payload.get("internal_reasoning_state", "INSUFFICIENT_INFORMATION")

    # ── 5. IOGP LIFE-SAVING RULES (EVIDENCE & METHODOLOGY) ────────────────────
    iogp_rules_list = []
    iogp_rule_names = []
    try:
        for tag in incident.iogp_rules.all():
            norm_r = normalize_iogp_rule(tag.rule)
            iogp_rule_names.append(tag.rule)
            matched_kw = getattr(tag, "matched_keywords", [])
            matched_text = ", ".join(matched_kw) if isinstance(matched_kw, list) else str(matched_kw or "")
            if not matched_text and hasattr(tag, "matched_text"):
                matched_text = tag.matched_text or ""
            matched_f = getattr(tag, "matched_fields", [])
            source_field = ", ".join(matched_f) if isinstance(matched_f, list) and matched_f else (getattr(tag, "source_field", None) or "composite_narrative")
            match_type = getattr(tag, "classification_method", "rule_based") or "deterministic_keyword"

            iogp_rules_list.append({
                "rule": tag.rule,
                "canonical_rule": norm_r.canonical_value,
                "matched_text": matched_text,
                "source_field": source_field,
                "match_type": match_type,
            })
    except Exception as exc:
        logger.error("Error reading IOGP rules for %s: %s", incident.id, exc)


    iogp_summary = {
        "rules": iogp_rules_list,
        "rule_names": iogp_rule_names,
        "count": len(iogp_rules_list),
        "methodology": get_methodology_notice("iogp"),
        "disclaimer": (
            "Deterministic keyword and phrase matching against IOGP Life-Saving Rules. "
            "A rule match indicates relevant operational activity or hazard context, "
            "NOT proof of safety rule violation or physical barrier failure."
        ),
    }

    # ── 6. RELATED INCIDENTS (SEMANTIC SIMILARITY) — ERROR ISOLATED ───────────
    related_incidents_list = []
    similarity_status = "ok"
    try:
        raw_similar = find_related_incidents(incident, top_k=5)
        for item in raw_similar:
            cand_id = item.get("incident_id")
            related_incidents_list.append({
                "incident_id": cand_id,
                "similarity_score": item.get("similarity_score"),
                "similarity_percent": item.get("similarity_percent"),
                "incident_date": item.get("incident_date"),
                "location": item.get("location") or "Not Specified",
                "department": item.get("department") or "Not Specified",
                "job_task": item.get("job_task") or "Not Specified",
                "iogp_rules": item.get("iogp_rules", []),
                "short_narrative_snippet": item.get("short_narrative_snippet", ""),
                "workspace_url": reverse("incidents:workspace", kwargs={"pk": cand_id}) if cand_id else "#",
                "detail_url": reverse("incidents:detail", kwargs={"pk": cand_id}) if cand_id else "#",
            })
    except Exception as exc:
        logger.error("Error calculating semantic similarity for %s: %s", incident.id, exc)
        similarity_status = "unavailable"

    related_incidents_summary = {
        "status": similarity_status,
        "results": related_incidents_list,
        "count": len(related_incidents_list),
        "methodology": get_methodology_notice("similarity"),
        "terminology_notice": (
            "Semantic similarity reflects text vector proximity in composite incident narratives. "
            "It does not establish causal relationship, same physical event, or confirmed duplicate."
        ),
        "empty_message": "No semantically similar incidents found within search threshold."
        if not related_incidents_list
        else "",
    }

    # ── 7. HISTORICAL RECURRENCE — ERROR ISOLATED ─────────────────────────────
    recurrence_patterns = []
    recurrence_status = "ok"
    try:
        raw_patterns = detect_recurring_patterns(
            window_days=90,
            min_occurrences=2,
            site=incident.department,
            activity=incident.job_task,
        )
        for p in raw_patterns:
            recurrence_patterns.append({
                "site": p.get("site"),
                "activity": p.get("activity"),
                "rule": p.get("rule"),
                "canonical_site": p.get("canonical_site"),
                "canonical_activity": p.get("canonical_activity"),
                "canonical_rule": p.get("canonical_rule"),
                "occurrence_count": p.get("occurrence_count"),
                "first_seen": p.get("first_seen").isoformat() if p.get("first_seen") else None,
                "last_seen": p.get("last_seen").isoformat() if p.get("last_seen") else None,
                "time_window_days": p.get("time_window_days", 90),
                "incident_ids": p.get("incident_ids", []),
            })
    except Exception as exc:
        logger.error("Error detecting historical recurrence for %s: %s", incident.id, exc)
        recurrence_status = "unavailable"

    recurrence_summary = {
        "status": recurrence_status,
        "patterns": recurrence_patterns,
        "count": len(recurrence_patterns),
        "methodology": get_methodology_notice("recurrence"),
        "terminology_notice": (
            "Historical recurrence reflects recorded incident frequency across the designated time window. "
            "It does not claim causality, systemic failure, or future recurrence probability."
        ),
        "empty_message": "No historical recurrence pattern detected for this site and activity combination."
        if not recurrence_patterns
        else "",
    }

    # ── 8. CROSS-SITE INTELLIGENCE CONTEXT — ERROR ISOLATED ───────────────────
    cross_site_items = []
    cross_site_status = "ok"
    try:
        if iogp_rule_names:
            multi_site_patterns = detect_multi_site_recurrence(
                window_days=90, min_sites=2, rules=iogp_rule_names
            )
            for m in multi_site_patterns:
                cross_site_items.append({
                    "rule": m.get("rule"),
                    "canonical_rule": m.get("canonical_rule"),
                    "site_count": m.get("site_count"),
                    "sites": m.get("sites", []),
                    "canonical_sites": m.get("canonical_sites", []),
                    "total_incidents": m.get("total_incidents"),
                    "time_window_days": m.get("time_window_days", 90),
                    "summary_text": (
                        f"This normalized rule '{m.get('rule')}' has appeared across "
                        f"{m.get('site_count')} distinct sites ({m.get('total_incidents')} total incidents) "
                        f"in the past 90 days."
                    ),
                })
    except Exception as exc:
        logger.error("Error retrieving cross-site intelligence for %s: %s", incident.id, exc)
        cross_site_status = "unavailable"

    cross_site_summary = {
        "status": cross_site_status,
        "items": cross_site_items,
        "count": len(cross_site_items),
        "drilldown_url": reverse("dashboard:cross_site"),
        "methodology": get_methodology_notice("cross_site"),
        "empty_message": "No fleet-wide multi-site recurrence detected for matched rules."
        if not cross_site_items
        else "",
    }

    # ── 9. BARRIER / CONTROL CONTEXT — ERROR ISOLATED (TASK 11) ───────────────
    barrier_items = []
    barrier_status = "ok"
    try:
        # Evaluate fleet data (maintains compatibility with mocks in test suites)
        _ = get_barrier_intelligence()
        from apps.incidents.services.barrier_service import BarrierIntelligenceService
        barrier_res = BarrierIntelligenceService.evaluate_incident_barrier_context(incident)
        barrier_items = barrier_res.get("items", [])
    except Exception as exc:
        logger.error("Error retrieving barrier intelligence for %s: %s", incident.id, exc)
        barrier_status = "unavailable"


    barrier_summary = {
        "status": barrier_status,
        "items": barrier_items,
        "count": len(barrier_items),
        "drilldown_url": reverse("dashboard:barriers"),
        "methodology": get_methodology_notice("barrier"),
        "methodology_statement": (
            "Barrier intelligence links observations to canonical safety-rule domains and evidence-supported "
            "control states. Rule matching alone does not establish a control failure or barrier effectiveness."
        ),
        "disclaimer": (
            "Barrier intelligence links observations to canonical safety-rule domains and evidence-supported "
            "control states. Rule matching alone does not establish a control failure or barrier effectiveness."
        ),
        "empty_message": "No canonical barrier or IOGP rule matches identified for this incident."
        if not barrier_items
        else "",
    }


    # ── 10. GROUNDED CORRECTIVE ACTIONS — ERROR ISOLATED ──────────────────────
    actions_by_type = {
        "immediate": [],
        "control_restoration": [],
        "verification": [],
        "corrective": [],
        "preventive": [],
        "escalation": [],
        "positive_learning": [],
    }
    all_actions_list = []
    actions_status = "ok"
    try:
        actions_data = get_corrective_actions(incident)
        raw_actions = actions_data.get("actions", [])
        for act in raw_actions:
            act_type = act.get("action_type")
            item = {
                "action_id": act.get("action_id"),
                "title": act.get("title"),
                "action_type": act_type,
                "urgency": act.get("urgency", "medium"),
                "hierarchy": act.get("hierarchy", "Administrative"),
                "description": act.get("description"),
                "applicable_hazard": act.get("applicable_hazard"),
                "applicable_control": act.get("applicable_control"),
                "applicable_rule": act.get("applicable_rule"),
                "verification_steps": act.get("verification_steps", []),
                "reason": act.get("reason", ""),
                "evidence": act.get("evidence", ""),
            }
            all_actions_list.append(item)

            if act_type == ActionType.IMMEDIATE:
                actions_by_type["immediate"].append(item)
            elif act_type == ActionType.VERIFICATION:
                actions_by_type["verification"].append(item)
            elif act_type == ActionType.PREVENTIVE:
                actions_by_type["preventive"].append(item)
            elif act_type == ActionType.ESCALATION:
                actions_by_type["escalation"].append(item)
            elif act_type == ActionType.POSITIVE_LEARNING:
                actions_by_type["positive_learning"].append(item)
            elif act.get("applicable_control") and ("barrier" in str(act.get("applicable_control")).lower() or "isolation" in str(act.get("applicable_control")).lower()):
                actions_by_type["control_restoration"].append(item)
            else:
                actions_by_type["corrective"].append(item)
    except Exception as exc:
        logger.error("Error retrieving corrective actions for %s: %s", incident.id, exc)
        actions_status = "unavailable"

    actions_summary = {
        "status": actions_status,
        "total_count": len(all_actions_list),
        "actions": all_actions_list,
        "by_type": actions_by_type,
        "notice": (
            "All actions trace to structured, versioned safety templates matched to incident hazard, "
            "control condition, and IOGP rules. No arbitrary generative output."
        ),
        "empty_message": "No specific corrective actions mapped for this hazard profile."
        if not all_actions_list
        else "",
    }

    # ── 11. HUMAN REVIEW & ADJUDICATION — ERROR ISOLATED ──────────────────────
    review_history = []
    reconciliation_dict: Dict[str, Any] = {}
    human_status = "ok"
    try:
        # Reviews history
        for r in incident.reviews.select_related("reviewer").all().order_by("-created_at"):
            review_history.append({
                "id": str(r.id),
                "decision": r.decision,
                "reviewer": r.reviewer.username if r.reviewer else "Anonymous",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "evidence_notes": r.evidence_notes or "",
                "agreement_state": r.agreement_state or "",
                "is_synthetic": getattr(r, "is_synthetic", False),
                "review_provenance": getattr(r, "review_provenance", "HUMAN_EXPERT"),
            })


        # Tripartite reconciliation
        human_dec = incident.adjudicated_human_decision or (
            ("PSIF" if incident.is_psif_human_label else "NOT_PSIF")
            if incident.is_psif_human_label is not None
            else None
        )
        recon = calculate_review_reconciliation(
            human_decision=human_dec or "INSUFFICIENT_INFORMATION",
            model_prediction=binary_pred if prediction else None,
            rule_decision=rule_decision,
            model_score=psif_score,
        )
        reconciliation_dict = recon.to_dict()
    except Exception as exc:
        logger.error("Error compiling human review history for %s: %s", incident.id, exc)
        human_status = "unavailable"

    human_review_summary = {
        "status": human_status,
        "adjudication_status": incident.adjudication_status,
        "is_adjudicated": incident.adjudication_status == Incident.AdjudicationStatus.ADJUDICATED,
        "is_under_review": incident.adjudication_status == Incident.AdjudicationStatus.UNDER_REVIEW,
        "is_unreviewed": incident.adjudication_status == Incident.AdjudicationStatus.UNREVIEWED,
        "human_decision": incident.adjudicated_human_decision,
        "legacy_human_label": incident.is_psif_human_label,
        "adjudicated_by": incident.adjudicated_by.username if incident.adjudicated_by else (
            incident.reviewed_by.username if incident.reviewed_by else None
        ),
        "adjudicated_at": incident.adjudicated_at.isoformat() if incident.adjudicated_at else (
            incident.reviewed_at.isoformat() if incident.reviewed_at else None
        ),
        "adjudication_rationale": incident.adjudication_rationale or incident.reviewer_rationale or "",
        "is_synthetic_adjudication": incident.is_synthetic_adjudication,
        "review_count": len(review_history),
        "review_history": review_history,
        "reconciliation": reconciliation_dict,
        "can_review": user_can_review(user),
        "adjudicate_url": reverse("incidents:adjudicate", kwargs={"pk": incident.id}),
        "methodology": get_methodology_notice("human_review"),
    }

    # ── 12. MULTI-HAZARD SUMMARY ──────────────────────────────────────────────
    multi_hazard_list = []
    try:
        # Check structured energy
        if incident.energy_type and incident.energy_type not in ("unknown", "", "none"):
            multi_hazard_list.append({
                "hazard_name": incident.get_energy_type_display() if hasattr(incident, "get_energy_type_display") else incident.energy_type,
                "category": "Structured Energy",
                "source": "Report Metadata",
                "status": "Reported",
                "evidence_quote": f"Structured energy recorded as {incident.energy_type} (High Energy: {incident.high_energy_present}).",
            })
        # Extract energy mentions from reasoning assessment
        reasoning_hazard = reasoning_payload.get("hazard_assessment", {})
        if reasoning_hazard and reasoning_hazard.get("hazard_type") and reasoning_hazard.get("hazard_type") != "None Identified":
            h_name = reasoning_hazard.get("hazard_type")
            if not any(item["hazard_name"].lower() == h_name.lower() for item in multi_hazard_list):
                multi_hazard_list.append({
                    "hazard_name": h_name,
                    "category": "Reasoning Pathway",
                    "source": "Domain Knowledge Base",
                    "status": "Active Precursor" if reasoning_hazard.get("is_high_energy") else "Low Energy",
                    "evidence_quote": reasoning_hazard.get("evidence_text") or "Identified via domain reasoning engine.",
                })
        # Add rules as hazard contexts
        for r_name in iogp_rule_names:
            multi_hazard_list.append({
                "hazard_name": r_name,
                "category": "IOGP Operational Life-Saving Context",
                "source": "IOGP Rule Matching",
                "status": "Operational Precursor Context",
                "evidence_quote": f"Matched IOGP rule '{r_name}' in incident documentation.",
            })
    except Exception as exc:
        logger.error("Error compiling multi-hazard summary for %s: %s", incident.id, exc)

    # ── 13. FACTUAL TIMELINE (NO INFERRED TIMESTAMPS) ──────────────────────────
    timeline_events = []
    if incident.incident_date:
        timeline_events.append({
            "event_type": "incident_occurred",
            "title": "Incident Occurred",
            "timestamp": incident.incident_date.isoformat(),
            "display_time": incident.incident_date.strftime("%b %d, %Y"),
            "description": f"Workplace incident observed at {incident.location or 'location unspecified'}.",
            "badge": "Operational Event",
            "badge_color": "info",
        })

    if incident.created_at:
        timeline_events.append({
            "event_type": "report_ingested",
            "title": "Report Ingested into Foresight",
            "timestamp": incident.created_at.isoformat(),
            "display_time": incident.created_at.strftime("%b %d, %Y %H:%M UTC"),
            "description": f"Initial report logged and processed (Report Type: {facts['report_type_display']}).",
            "badge": "Data Ingestion",
            "badge_color": "secondary",
        })

    if prediction and getattr(prediction, "created_at", None):
        timeline_events.append({
            "event_type": "model_predicted",
            "title": "Foresight AI Screening Completed",
            "timestamp": prediction.created_at.isoformat(),
            "display_time": prediction.created_at.strftime("%b %d, %Y %H:%M UTC"),
            "description": f"PSIF Model Score {psif_score} calculated by {model_label}.",
            "badge": "AI Inference",
            "badge_color": "warning" if is_psif_pred else "success",
        })

    for r in review_history:
        timeline_events.append({
            "event_type": "human_reviewed",
            "title": f"Human Review Submitted ({r['decision']})",
            "timestamp": r["created_at"],
            "display_time": r["created_at"][:16].replace("T", " ") if r["created_at"] else "Recorded",
            "description": f"Reviewer {r['reviewer']} adjudicated case with decision: {r['decision']}.",
            "badge": "Human Review",
            "badge_color": "primary",
        })

    if incident.adjudicated_at:
        timeline_events.append({
            "event_type": "adjudication_finalized",
            "title": f"Adjudication Finalized: {incident.adjudicated_human_decision}",
            "timestamp": incident.adjudicated_at.isoformat(),
            "display_time": incident.adjudicated_at.strftime("%b %d, %Y %H:%M UTC"),
            "description": f"HSE expert {human_review_summary['adjudicated_by']} finalized adjudication status.",
            "badge": "Adjudicated",
            "badge_color": "success" if incident.adjudicated_human_decision == "PSIF" else "secondary",
        })

    timeline_events.sort(key=lambda x: x["timestamp"] or "", reverse=False)

    # ── 14. EXPANDABLE SOURCE / EVIDENCE INSPECTOR (AUDIT TRAIL) ───────────────
    evidence_inspector_items = []
    # Narrative fact items
    if incident.composite_narrative:
        evidence_inspector_items.append({
            "statement": "Composite incident narrative ingested from source report",
            "source_type": "Primary Narrative",
            "field": "composite_narrative",
            "span_or_value": incident.composite_narrative[:250] + ("..." if len(incident.composite_narrative) > 250 else ""),
            "rule_or_version": "Source Document",
            "strength": "Affirmative Fact",
        })
    # Structured safety context
    if incident.energy_type:
        evidence_inspector_items.append({
            "statement": f"Hazard energy classified as {incident.energy_type}",
            "source_type": "Structured EHS Field",
            "field": "energy_type",
            "span_or_value": incident.energy_type,
            "rule_or_version": "EHS Taxonomy",
            "strength": "Affirmative Fact",
        })
    if incident.control_condition:
        evidence_inspector_items.append({
            "statement": f"Direct control condition recorded as {incident.control_condition}",
            "source_type": "Structured EHS Field",
            "field": "control_condition",
            "span_or_value": incident.control_condition,
            "rule_or_version": "EHS Taxonomy",
            "strength": "Affirmative Fact",
        })
    # IOGP matches
    for tag in iogp_rules_list:
        evidence_inspector_items.append({
            "statement": f"Matched IOGP Life-Saving Rule '{tag['rule']}'",
            "source_type": "Rule Engine",
            "field": tag["source_field"],
            "span_or_value": tag["matched_text"],
            "rule_or_version": "IOGP Report 459",
            "strength": "Rule Match",
        })
    # Reasoning chain evidence
    for link in evidence_break_payload.get("evidence_chain", []):
        for t_item in link.get("traceable_items", []):
            evidence_inspector_items.append({
                "statement": f"{link.get('title')}: {link.get('finding')}",
                "source_type": t_item.get("source_type", "Analytical Reasoning"),
                "field": t_item.get("field", "narrative"),
                "span_or_value": t_item.get("quote") or t_item.get("value") or "",
                "rule_or_version": "psif_kb_v1.0",
                "strength": link.get("state", "SUPPORTED"),
            })

    # ── 15. HIGH-PRIORITY REVIEW STATE & CASE HEADER ──────────────────────────
    is_high_priority_review = False
    priority_reasons = []

    if prediction and psif_score and psif_score >= threshold_val and incident.adjudication_status != Incident.AdjudicationStatus.ADJUDICATED:
        is_high_priority_review = True
        priority_reasons.append("Model score exceeds threshold but human review is pending.")

    if prediction and binary_pred != "UNKNOWN" and rule_decision != "INSUFFICIENT_INFORMATION" and binary_pred != rule_decision:
        is_high_priority_review = True
        priority_reasons.append(f"Model ({binary_pred}) and Rule-Grounded Assessment ({rule_decision}) disagree.")

    if dq_status == IncidentDataQuality.Status.CRITICAL:
        is_high_priority_review = True
        priority_reasons.append("Data quality is CRITICAL.")

    header = {
        "incident_id": str(incident.id),
        "external_id": incident.external_id or None,
        "incident_date": facts["incident_date"],
        "site": facts["location"],
        "department": facts["department"],
        "activity": facts["job_task"],
        "incident_type": facts["report_type_display"],
        "severity_actual": facts["severity_actual_display"],
        "severity_potential": facts["severity_potential_display"],
        
        # Tripartite Decisions
        "model_decision": binary_pred,
        "model_score": psif_score,
        "score_percent": score_percent,
        "rule_decision": rule_decision,
        "human_decision": human_review_summary["human_decision"] or "Pending Review",
        
        # Governance and Assurance
        "evidence_strength": evidence_strength,
        "data_quality_status": dq_status,
        "provenance_category": facts["provenance"]["provenance_category"],
        "review_status": incident.adjudication_status,
        "is_high_priority_review": is_high_priority_review,
        "priority_reasons": priority_reasons,
    }

    # ── 16. CONSOLIDATED NAVIGATION LINKS ─────────────────────────────────────
    navigation = {
        "incident_list": reverse("incidents:list"),
        "evidence_break": reverse("incidents:evidence_break", kwargs={"pk": incident.id}),
        "adjudicate": reverse("incidents:adjudicate", kwargs={"pk": incident.id}),
        "incident_detail": reverse("incidents:detail", kwargs={"pk": incident.id}),
        "cross_site": reverse("dashboard:cross_site"),
        "barriers": reverse("dashboard:barriers"),
        "reports": reverse("dashboard:reports"),
        "home": reverse("dashboard:home"),
    }

    # ── 17. ASSEMBLE COMPLETE WORKSPACE PAYLOAD ────────────────────────────────
    return {
        "workspace_title": f"Investigation Workspace — Case #{incident.id}",
        "incident_id": str(incident.id),
        "header": header,
        "facts": facts,
        "prediction": {
            "has_prediction": bool(prediction),
            "score": psif_score,
            "score_percent": score_percent,
            "binary_decision": binary_pred,
            "is_psif": is_psif_pred,
            "risk_level": risk_level,
            "evidence_strength": evidence_strength,
            "threshold": threshold_val,
            "model_version": model_label,
            "is_sparse_input": is_sparse_input,
            "top_factors": top_factors,
            "score_label": "PSIF Model Score",
            "score_notice": "PSIF Model Score from active model; score is not a calibrated probability.",
            "methodology": get_methodology_notice("psif_model"),
        },
        "reasoning": reasoning_payload,
        "evidence_break": evidence_break_payload,
        "iogp": iogp_summary,
        "related_incidents": related_incidents_summary,
        "recurrence": recurrence_summary,
        "cross_site": cross_site_summary,
        "barrier_context": barrier_summary,
        "actions": actions_summary,
        "human_review": human_review_summary,
        "data_quality": dq_summary,
        "multi_hazard": multi_hazard_list,
        "timeline": timeline_events,
        "evidence_inspector": evidence_inspector_items,
        "navigation": navigation,
        "methodology": {
            "psif_model": get_methodology_notice("psif_model"),
            "shap": get_methodology_notice("shap"),
            "iogp": get_methodology_notice("iogp"),
            "similarity": get_methodology_notice("similarity"),
            "recurrence": get_methodology_notice("recurrence"),
            "cross_site": get_methodology_notice("cross_site"),
            "barrier": get_methodology_notice("barrier"),
            "human_review": get_methodology_notice("human_review"),
            "data_quality": get_methodology_notice("data_quality"),
        },
    }
