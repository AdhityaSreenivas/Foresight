"""
PSIF Platform — Standardized Analytical Evidence Structures

Provides a unified representation for analytical evidence across:
- Predictive model SHAP attributions
- Incident structured fields & narrative spans
- IOGP rule classifications
- Semantic incident similarity
- Historical recurrence clusters
- Barrier integrity & critical-control conditions
- Human expert adjudications
- Data-quality checks

Design:
- Strongly-typed dataclass AnalyticalEvidence with serialization
- Preserves source, evidence_type, label, value, strength, supporting_text, caveat, provenance
- Helper builder functions for seamless conversion from existing models and dicts
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


class EvidenceSource:
    MODEL_PREDICTION = "model_prediction"
    INCIDENT_RECORD = "incident_record"
    IOGP_CLASSIFICATION = "iogp_classification"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    RECURRENCE_PATTERN = "recurrence_pattern"
    HUMAN_REVIEW = "human_review"
    DATA_QUALITY = "data_quality"
    BARRIER_INTELLIGENCE = "barrier_intelligence"
    CROSS_SITE = "cross_site"


class EvidenceType:
    SHAP_FACTOR = "shap_factor"
    STRUCTURED_FIELD = "structured_field"
    NARRATIVE_SPAN = "narrative_span"
    RULE_MATCH = "rule_match"
    SIMILAR_INCIDENT = "similar_incident"
    RECURRENCE_CLUSTER = "recurrence_cluster"
    DQ_FINDING = "dq_finding"
    CONTROL_STATUS = "control_status"
    EXPERT_ADJUDICATION = "expert_adjudication"
    CROSS_SITE_MATCH = "cross_site_match"


class EvidenceStrength:
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INFO = "info"


@dataclass
class AnalyticalEvidence:
    """
    Standardized atomic analytical evidence object.
    Carries provenance and concise methodological caveats alongside the signal value.
    """
    source: str                                # Member of EvidenceSource
    evidence_type: str                         # Member of EvidenceType
    label: str                                 # Human-readable title/label
    value: Any                                 # Metric, status, string, or numeric score
    strength: str = EvidenceStrength.INFO      # Member of EvidenceStrength
    supporting_text: Optional[str] = None      # Verbatim text excerpt or keyword phrase
    field_name: Optional[str] = None           # Source field in database if applicable
    caveat: Optional[str] = None               # Standardized methodological disclosure
    provenance: str = "analytical_evidence_v1" # Algorithm / ruleset / pipeline version
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def incident_field(self) -> Optional[str]:
        return self.field_name or self.metadata.get("incident_field")

    @property
    def narrative_span(self) -> Optional[str]:
        if self.evidence_type == EvidenceType.NARRATIVE_SPAN:
            return self.supporting_text
        return self.metadata.get("narrative_span")

    @property
    def analytical_component(self) -> str:
        return self.metadata.get("analytical_component") or self.source

    @property
    def model_version(self) -> Optional[str]:
        return self.metadata.get("model_version") or (
            self.provenance if self.source == EvidenceSource.MODEL_PREDICTION else None
        )

    @property
    def ruleset_version(self) -> Optional[str]:
        return self.metadata.get("ruleset_version") or (
            self.provenance if self.source in (
                EvidenceSource.IOGP_CLASSIFICATION,
                EvidenceSource.BARRIER_INTELLIGENCE,
                EvidenceSource.DATA_QUALITY,
            ) else None
        )

    @property
    def source_document(self) -> Optional[str]:
        return (
            self.metadata.get("source_document")
            or self.metadata.get("rule")
            or (str(self.value) if self.evidence_type == EvidenceType.RULE_MATCH else None)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary with deterministic sorted keys and backlinks."""
        d = asdict(self)
        d["incident_field"] = self.incident_field
        d["narrative_span"] = self.narrative_span
        d["analytical_component"] = self.analytical_component
        d["model_version"] = self.model_version
        d["ruleset_version"] = self.ruleset_version
        d["source_document"] = self.source_document
        return {k: d[k] for k in sorted(d.keys())}


# ── Builder Helpers ───────────────────────────────────────────────────────────

def evidence_from_shap(factor: Dict[str, Any]) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from a SHAP feature attribution dict."""
    if not isinstance(factor, dict):
        factor = {}
    feat_name = str(factor.get("feature") or "unknown_feature")
    raw_contrib = factor.get("contribution", 0.0)
    try:
        contrib = float(raw_contrib)
    except (ValueError, TypeError):
        contrib = 0.0
    abs_contrib = abs(contrib)
    
    if abs_contrib >= 0.10:
        strength = EvidenceStrength.STRONG
    elif abs_contrib >= 0.03:
        strength = EvidenceStrength.MODERATE
    else:
        strength = EvidenceStrength.WEAK

    direction = "increased_score" if contrib > 0 else "decreased_score"


    return AnalyticalEvidence(
        source=EvidenceSource.MODEL_PREDICTION,
        evidence_type=EvidenceType.SHAP_FACTOR,
        label=f"Feature Impact: {feat_name}",
        value=round(contrib, 4),
        strength=strength,
        field_name=feat_name,
        caveat="SHAP values show mathematical model contribution, not causality.",
        provenance="tree_shap_explainer_v1",
        metadata={
            "direction": direction,
            "interpretation": f"{'Increases' if contrib > 0 else 'Decreases'} PSIF model score by {abs_contrib:.3f}",
        }
    )


def evidence_from_incident_field(
    field_name: str,
    value: Any,
    label: Optional[str] = None,
    strength: str = EvidenceStrength.INFO,
) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from a raw or canonical incident field."""
    display_label = label or field_name.replace("_", " ").title()
    return AnalyticalEvidence(
        source=EvidenceSource.INCIDENT_RECORD,
        evidence_type=EvidenceType.STRUCTURED_FIELD,
        label=display_label,
        value=value,
        strength=strength,
        field_name=field_name,
        caveat="Direct fact from incident record.",
        provenance="incident_source_record",
    )


def evidence_from_iogp_tag(tag_or_dict: Any) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from an IOGPRuleTag instance or dict."""
    if hasattr(tag_or_dict, "rule"):
        rule_name = tag_or_dict.rule
        confidence = getattr(tag_or_dict, "confidence", 1.0)
        keywords = getattr(tag_or_dict, "matched_keywords", [])
        fields_matched = getattr(tag_or_dict, "matched_fields", [])
        prov = getattr(tag_or_dict, "classifier_version", "deterministic_iogp_ruleset_v1")
    else:
        rule_name = tag_or_dict.get("rule", "")
        confidence = tag_or_dict.get("match_strength", tag_or_dict.get("confidence", 1.0))
        keywords = tag_or_dict.get("matched_phrases", tag_or_dict.get("matched_keywords", []))
        fields_matched = tag_or_dict.get("matched_fields", [])
        prov = tag_or_dict.get("classifier_version", "deterministic_iogp_ruleset_v1")

    strength = EvidenceStrength.STRONG if confidence >= 0.9 else EvidenceStrength.MODERATE
    supporting_text = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)

    return AnalyticalEvidence(
        source=EvidenceSource.IOGP_CLASSIFICATION,
        evidence_type=EvidenceType.RULE_MATCH,
        label=f"IOGP Rule: {rule_name}",
        value=rule_name,
        strength=strength,
        supporting_text=supporting_text or None,
        field_name=",".join(fields_matched) if fields_matched else None,
        caveat="Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure.",
        provenance=prov,
        metadata={
            "match_strength": confidence,
            "matched_keywords": keywords,
            "matched_fields": fields_matched,
        }
    )


def evidence_from_narrative_span(
    span: str,
    category: str = "Narrative Observation",
    strength: str = EvidenceStrength.MODERATE,
) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from an extracted narrative text span."""
    return AnalyticalEvidence(
        source=EvidenceSource.INCIDENT_RECORD,
        evidence_type=EvidenceType.NARRATIVE_SPAN,
        label=category,
        value=span,
        strength=strength,
        supporting_text=span,
        caveat="Verbatim quote from composite incident narrative.",
        provenance="narrative_span_extractor_v1",
    )


def evidence_from_similar_incident(item: Dict[str, Any]) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from a related incident similarity result."""
    inc_id = item.get("incident_id", "")
    score = float(item.get("similarity_score", 0.0))
    strength = EvidenceStrength.STRONG if score >= 0.85 else EvidenceStrength.MODERATE

    return AnalyticalEvidence(
        source=EvidenceSource.SEMANTIC_SIMILARITY,
        evidence_type=EvidenceType.SIMILAR_INCIDENT,
        label=f"Similar Incident #{str(inc_id)[:8]}",
        value=round(score, 3),
        strength=strength,
        supporting_text=item.get("narrative_excerpt") or item.get("composite_narrative"),
        caveat="Semantic similarity between incident narratives; not causal evidence or duplicate identity.",
        provenance=item.get("embedding_model", "distilbert_embedding_v1"),
        metadata={
            "target_incident_id": str(inc_id),
            "department": item.get("department"),
            "severity_actual": item.get("severity_actual"),
        }
    )


def evidence_from_recurrence_pattern(pattern: Dict[str, Any]) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from a recurring pattern detection result."""
    rule = pattern.get("rule", "Unknown Rule")
    site = pattern.get("site", "Site")
    count = int(pattern.get("occurrence_count", 0))
    strength = EvidenceStrength.STRONG if count >= 5 else EvidenceStrength.MODERATE

    return AnalyticalEvidence(
        source=EvidenceSource.RECURRENCE_PATTERN,
        evidence_type=EvidenceType.RECURRENCE_CLUSTER,
        label=f"Recurrence: {rule} at {site}",
        value=count,
        strength=strength,
        caveat="Historical recurrence based on normalized entities and time-window matching; not causal/systemic prediction.",
        provenance="temporal_recurrence_clustering_v1",
        metadata={
            "site": site,
            "activity": pattern.get("activity"),
            "rule": rule,
            "window_days": pattern.get("time_window_days", 90),
            "incident_count": count,
        }
    )


def evidence_from_control_status(
    control_type: Optional[str],
    control_condition: Optional[str],
    failed_or_bypassed: Optional[bool] = None,
) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from control type and condition assessment."""
    condition_str = control_condition or "unknown"
    is_compromised = (
        failed_or_bypassed is True
        or condition_str.lower() in ("failed", "bypassed", "absent")
    )
    strength = EvidenceStrength.STRONG if is_compromised else EvidenceStrength.MODERATE

    return AnalyticalEvidence(
        source=EvidenceSource.BARRIER_INTELLIGENCE,
        evidence_type=EvidenceType.CONTROL_STATUS,
        label=f"Control Integrity: {control_type or 'General Control'}",
        value=condition_str,
        strength=strength,
        field_name="control_condition",
        caveat="Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure.",
        provenance="control_evaluator_v1",
        metadata={
            "control_type": control_type,
            "condition": condition_str,
            "is_compromised": is_compromised,
        }
    )


def evidence_from_data_quality(finding: Any) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from a data quality check finding."""
    if isinstance(finding, dict):
        code = finding.get("code", "DQ_FINDING")
        msg = finding.get("message", str(finding))
        severity = finding.get("severity", "WARNING")
    else:
        code = "DQ_FINDING"
        msg = str(finding)
        severity = "WARNING"

    strength = EvidenceStrength.STRONG if severity.upper() == "CRITICAL" else EvidenceStrength.MODERATE

    return AnalyticalEvidence(
        source=EvidenceSource.DATA_QUALITY,
        evidence_type=EvidenceType.DQ_FINDING,
        label=f"Data Quality: {code}",
        value=msg,
        strength=strength,
        caveat="Data-quality rules indicate analytical suitability; they do not establish PSIF status.",
        provenance="incident_data_quality_v1",
        metadata={"finding_code": code, "severity": severity}
    )


def evidence_from_cross_site(finding: Dict[str, Any]) -> AnalyticalEvidence:
    """Creates AnalyticalEvidence from a cross-site recurrence pattern finding."""
    rule = finding.get("rule", "Life-Saving Rule")
    site = finding.get("site", "Other Site")
    count = int(finding.get("occurrence_count", 0))
    strength = EvidenceStrength.STRONG if count >= 3 else EvidenceStrength.MODERATE

    return AnalyticalEvidence(
        source=EvidenceSource.CROSS_SITE,
        evidence_type=EvidenceType.CROSS_SITE_MATCH,
        label=f"Cross-Site Pattern: {rule} ({site})",
        value=count,
        strength=strength,
        supporting_text=finding.get("summary_text"),
        caveat="Cross-site findings use normalized safety entities and historical occurrence data. They indicate recurrence patterns, not causal relationships or future-risk predictions.",
        provenance="cross_site_normalization_v1",
        metadata={
            "matched_site": site,
            "matched_rule": rule,
            "activity": finding.get("activity"),
            "occurrence_count": count,
            "source_document": finding.get("source_document"),
        }
    )
