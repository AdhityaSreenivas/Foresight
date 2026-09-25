"""
Barrier & Critical-Control Intelligence Service (Task 11)
apps/incidents/services/barrier_service.py

OIL India Problem Statement 26165.

Provides evidence-grounded Barrier and Critical-Control Intelligence across the
9 canonical IOGP Life-Saving Rules:
    1. Bypassing Safety Controls
    2. Confined Space
    3. Driving
    4. Energy Isolation
    5. Hot Work
    6. Line of Fire
    7. Safe Mechanical Lifting
    8. Work Authorization
    9. Working at Height

CRITICAL METHODOLOGY & SAFETY GOVERNANCE:
1. Grounded Reality: Structured control condition fields across the bulk dataset
   are unpopulated/unknown. V1 metrics MUST remain defensible.
2. The ONLY authoritative aggregate V1 metrics permitted are:
   - Matched Observations: Distinct incidents linked to a canonical IOGP rule through deterministic matching.
   - PSIF-Linked Observations: Matched incidents where psif_predicted=True and is_sparse_input=False.
   - Affected Sites: Distinct nonblank normalized sites among matched observations.
3. PSIF-Linkage Rate:
   PSIF-linkage rate = PSIF-linked matched observations / matched observations.
   Explicitly labeled as e.g. "60.8% of matched observations were PSIF-linked by the active model".
   NEVER labeled as "probability of barrier failure" or "control failure rate".
4. Control States (Explicit internal semantics):
   - CONTROLLED (evidence demonstrates control held / functioned as intended)
   - COMPROMISED (explicit evidence demonstrates bypass, failure, or absence)
   - UNKNOWN (no explicit control evidence; missing data NEVER defaults to COMPROMISED)
   - NOT_APPLICABLE (activity/hazard does not require this control)
   - PARTIALLY_EFFECTIVE (evidence genuinely supports partial containment)
5. Barrier Linkage:
   incident -> hazard/energy -> exposure -> critical control -> control state -> IOGP rule -> PSIF pathway.
6. Caching:
   Cache key: "dashboard:barrier_intelligence:v1", TTL: 3600 seconds.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from django.core.cache import cache
from django.db.models import Count, Q

from apps.incidents.models import Incident, IOGPRuleTag
from apps.incidents.services.normalization import (
    CANONICAL_IOGP_RULES,
    normalize_iogp_rule,
    normalize_site,
)

logger = logging.getLogger(__name__)

CACHE_KEY_BARRIER_INTELLIGENCE = "dashboard:barrier_intelligence:v1"
CACHE_TTL_BARRIER = 3600  # 1 hour

METHODOLOGY_STATEMENT = (
    "Barrier intelligence links observations to canonical safety-rule domains and evidence-supported "
    "control states. Rule matching alone does not establish a control failure or barrier effectiveness."
)

RATE_DEFINITION = (
    "PSIF-linkage rate = PSIF-linked matched observations / matched observations."
)

UNKNOWN_CONTROL_EVIDENCE_TEXT = (
    "Control effectiveness could not be established from available source data."
)


class ControlSemantics:
    """Explicit internal semantics for safety controls and barriers."""
    CONTROLLED = "CONTROLLED"
    COMPROMISED = "COMPROMISED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PARTIALLY_EFFECTIVE = "PARTIALLY_EFFECTIVE"

    ALL_STATES = [CONTROLLED, COMPROMISED, UNKNOWN, NOT_APPLICABLE, PARTIALLY_EFFECTIVE]


@dataclass
class BarrierLinkage:
    """
    Evidence-grounded 7-stage safety linkage:
    incident -> hazard/energy -> exposure -> relevant critical control -> control state -> IOGP rule -> PSIF pathway.
    """
    incident_id: str
    hazard_energy: Dict[str, Any]
    exposure: Dict[str, Any]
    critical_control: Dict[str, Any]
    control_state: str
    control_evidence: str
    iogp_rule: str
    psif_pathway: Dict[str, Any]
    reason_method: str = "deterministic_rule_grounded"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BarrierIntelligenceService:
    """
    Authoritative service for Barrier and Critical-Control Intelligence.
    Consumes canonical database tags, model predictions, and domain reasoning.
    """

    @classmethod
    def get_barrier_portfolio(
        cls, use_cache: bool = True, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Computes the fleet-wide portfolio across all 9 canonical IOGP rules.
        Uses single-pass database GROUP BY with distinct counts for performance.
        Results are cached in Redis under CACHE_KEY_BARRIER_INTELLIGENCE.
        """
        if use_cache and not force_refresh:
            cached = cache.get(CACHE_KEY_BARRIER_INTELLIGENCE)
            if cached is not None:
                return cached

        # Single-pass database aggregation across all IOGPRuleTag records
        qs = IOGPRuleTag.objects.values("rule").annotate(
            matched_observations=Count("incident", distinct=True),
            psif_linked_observations=Count(
                "incident",
                filter=Q(
                    incident__prediction__psif_predicted=True,
                    incident__prediction__is_sparse_input=False,
                ),
                distinct=True,
            ),
            affected_sites=Count(
                "incident__location",
                filter=~Q(incident__location__in=[None, ""]),
                distinct=True,
            ),
        ).order_by("-matched_observations")

        # Map aggregation results by canonical rule name
        db_map: Dict[str, Dict[str, int]] = {}
        for item in qs:
            r_name = item["rule"]
            db_map[r_name] = {
                "matched": item["matched_observations"] or 0,
                "psif_linked": item["psif_linked_observations"] or 0,
                "affected_sites": item["affected_sites"] or 0,
            }

        # Build comprehensive portfolio ensuring all 9 canonical rules are represented
        barriers: List[Dict[str, Any]] = []
        for rule_name in CANONICAL_IOGP_RULES:
            rule_data = db_map.get(rule_name, {"matched": 0, "psif_linked": 0, "affected_sites": 0})
            matched = rule_data["matched"]
            psif_linked = rule_data["psif_linked"]
            sites = rule_data["affected_sites"]
            linkage_rate = round((psif_linked / matched * 100), 1) if matched > 0 else 0.0

            rate_label = f"{linkage_rate}% of matched observations were PSIF-linked by the active model"

            rule_slug = rule_name.lower().replace(" ", "-")

            barriers.append({
                "rule": rule_name,
                "canonical_rule": rule_name,
                "slug": rule_slug,
                "matched_observations": matched,
                "formatted_matched": f"{matched:,}",
                "psif_linked_observations": psif_linked,
                "formatted_psif_linked": f"{psif_linked:,}",
                "psif_linkage_rate": linkage_rate,
                "psif_linkage_rate_label": rate_label,
                "affected_sites": sites,
                "formatted_affected_sites": f"{sites:,}",
                "evidence_methodology": (
                    "Deterministic keyword and phrase matching against canonical IOGP Life-Saving Rules "
                    "(Report 459). Rule match identifies relevant operational hazard context."
                ),
                "limitations": (
                    "Rule match does NOT prove barrier failure or rule non-compliance. "
                    "Structured control fields across the dataset are largely unknown/None."
                ),
            })

        # Sort barriers descending by matched observations for presentation
        barriers.sort(key=lambda b: b["matched_observations"], reverse=True)

        # Distinct fleet totals (proper set union across distinct incidents and sites)
        total_matched_distinct = IOGPRuleTag.objects.values("incident").distinct().count()
        total_psif_linked_distinct = IOGPRuleTag.objects.filter(
            incident__prediction__psif_predicted=True,
            incident__prediction__is_sparse_input=False,
        ).values("incident").distinct().count()
        total_sites = Incident.objects.filter(
            iogp_rules__isnull=False
        ).exclude(location__in=[None, ""]).values("location").distinct().count()

        overall_linkage_rate = (
            round((total_psif_linked_distinct / total_matched_distinct * 100), 1)
            if total_matched_distinct > 0
            else 0.0
        )
        overall_rate_label = (
            f"{overall_linkage_rate}% of matched observations were PSIF-linked by the active model"
        )

        from apps.incidents.services.methodology import get_methodology_notice

        payload = {
            "barriers": barriers,
            "total_monitored_barriers": len(barriers),
            "canonical_rule_count": 9,
            "total_matched_distinct": total_matched_distinct,
            "formatted_total_matched": f"{total_matched_distinct:,}",
            "total_psif_linked_distinct": total_psif_linked_distinct,
            "formatted_total_psif_linked": f"{total_psif_linked_distinct:,}",
            "overall_linkage_rate": overall_linkage_rate,
            "overall_linkage_rate_label": overall_rate_label,
            "total_affected_sites": total_sites,
            "formatted_total_affected_sites": f"{total_sites:,}",
            "table_columns": [
                "Rule",
                "Matched Observations",
                "PSIF-Linked Observations",
                "Affected Sites",
                "PSIF-Linkage Rate",
            ],
            "methodology_statement": METHODOLOGY_STATEMENT,
            "rate_definition": RATE_DEFINITION,
            "methodology_disclaimer": (
                "Barrier associations are derived from deterministic IOGP Life-Saving Rules keyword and phrase "
                "matching across incident narratives. PSIF linkages reflect authoritative model predictions on non-sparse "
                "reports. These metrics indicate operational observation frequency and risk correlation, not calibrated "
                "physical barrier integrity."
            ),
            "methodology_notice": get_methodology_notice("barrier"),
            "omitted_metrics": {
                "concern_pattern_matches": (
                    "Omitted. Structured control condition fields are unpopulated (100% unknown) across bulk records. "
                    "Keyword matches are not converted into confirmed control effectiveness."
                ),
                "barrier_health_score": (
                    "Omitted. No calibrated physical barrier reliability model exists in the platform. "
                    "Inventing barrier-health percentages is strictly prohibited."
                ),
                "barrier_failure_count": (
                    "Omitted. Rule match indicates hazard family context, NOT control failure."
                ),
            },
        }

        if use_cache:
            cache.set(CACHE_KEY_BARRIER_INTELLIGENCE, payload, CACHE_TTL_BARRIER)

        return payload

    @classmethod
    def get_barrier_detail(
        cls, rule_name: str, page: int = 1, page_size: int = 10
    ) -> Dict[str, Any]:
        """
        Retrieves detailed intelligence for a specific IOGP Life-Saving Rule.
        Includes authoritative V1 metrics, methodology statements, limitations,
        and representative incidents with evaluated control states.
        """
        norm_result = normalize_iogp_rule(rule_name)
        canonical_rule = norm_result.canonical_value

        if canonical_rule not in CANONICAL_IOGP_RULES:
            raise ValueError(f"Rule '{rule_name}' is not one of the 9 canonical IOGP Life-Saving Rules.")

        portfolio = cls.get_barrier_portfolio()
        rule_metric = next((b for b in portfolio["barriers"] if b["canonical_rule"] == canonical_rule), None)

        if not rule_metric:
            rule_metric = {
                "rule": canonical_rule,
                "canonical_rule": canonical_rule,
                "slug": canonical_rule.lower().replace(" ", "-"),
                "matched_observations": 0,
                "formatted_matched": "0",
                "psif_linked_observations": 0,
                "formatted_psif_linked": "0",
                "psif_linkage_rate": 0.0,
                "psif_linkage_rate_label": "0.0% of matched observations were PSIF-linked by the active model",
                "affected_sites": 0,
                "formatted_affected_sites": "0",
            }

        # Query representative incidents matching this rule
        incidents_qs = (
            Incident.objects.filter(iogp_rules__rule=canonical_rule)
            .select_related("prediction", "dataset")
            .prefetch_related("iogp_rules")
            .order_by("-id")
        )

        total_matching_incidents = incidents_qs.count()

        # Pagination slice
        offset = (page - 1) * page_size
        paged_incidents = list(incidents_qs[offset : offset + page_size])

        representative_incidents = []
        for inc in paged_incidents:
            linkage = cls.evaluate_incident_control_linkage(inc)
            pred = getattr(inc, "prediction", None)
            is_psif = bool(pred.psif_predicted) if pred else False
            score = round(pred.psif_score, 4) if pred and pred.psif_score is not None else None

            narrative = inc.composite_narrative or inc.description or ""
            snippet = narrative[:220] + "..." if len(narrative) > 220 else narrative

            representative_incidents.append({
                "incident_id": str(inc.id),
                "incident_date": inc.incident_date.isoformat() if inc.incident_date else None,
                "location": inc.location or "Not Specified",
                "department": inc.department or "Not Specified",
                "narrative_snippet": snippet,
                "model_psif_predicted": is_psif,
                "model_score": score,
                "control_state": linkage.control_state,
                "control_evidence": linkage.control_evidence,
                "psif_pathway_role": linkage.psif_pathway.get("pathway_role", "Operational Context"),
                "evidence_strength": linkage.critical_control.get("evidence_strength", "MODERATE"),
            })

        return {
            "rule": canonical_rule,
            "canonical_rule": canonical_rule,
            "slug": canonical_rule.lower().replace(" ", "-"),
            "matched_observations": rule_metric["matched_observations"],
            "formatted_matched": rule_metric["formatted_matched"],
            "psif_linked_observations": rule_metric["psif_linked_observations"],
            "formatted_psif_linked": rule_metric["formatted_psif_linked"],
            "affected_sites": rule_metric["affected_sites"],
            "formatted_affected_sites": rule_metric["formatted_affected_sites"],
            "psif_linkage_rate": rule_metric["psif_linkage_rate"],
            "psif_linkage_rate_label": rule_metric["psif_linkage_rate_label"],
            "evidence_methodology": (
                "Deterministic keyword and phrase matching against canonical IOGP Life-Saving Rules "
                "(Report 459). Rule match indicates relevant operational hazard domain."
            ),
            "methodology_limitations": (
                "The current structured control fields across the dataset are largely unknown/None. "
                "Rule matching alone does not establish a control failure or barrier effectiveness. "
                "Observations reflect operational frequency, not physical barrier degradation."
            ),
            "sampling_notice": (
                "Representative incidents are illustrative examples matching this rule and are not "
                "statistically sampled across the population."
            ),
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_matching_incidents,
                "total_pages": (total_matching_incidents + page_size - 1) // page_size if page_size > 0 else 1,
            },
            "representative_incidents": representative_incidents,
            "methodology_statement": METHODOLOGY_STATEMENT,
            "rate_definition": RATE_DEFINITION,
        }

    @classmethod
    def evaluate_incident_control_linkage(cls, incident: Incident) -> BarrierLinkage:
        """
        Builds evidence-grounded 7-stage linkage for an incident:
        incident -> hazard/energy -> exposure -> critical control -> control state -> IOGP rule -> PSIF pathway.

        Evaluates explicit evidence:
        - When explicit evidence indicates control compromised -> COMPROMISED
        - When explicit evidence indicates control effective/held -> CONTROLLED
        - When explicit evidence indicates partial effectiveness -> PARTIALLY_EFFECTIVE
        - When NO explicit evidence exists -> UNKNOWN
          with evidence "Control effectiveness could not be established from available source data."
        """
        from apps.incidents.services.psif_reasoning import (
            CONTROL_EFFECTIVE_PATTERNS,
            CONTROL_COMPROMISED_PATTERNS,
            PPE_PATTERNS,
            _extract_first_match_span,
        )

        narrative = incident.composite_narrative or incident.description or ""
        raw_failed_bypassed = getattr(incident, "control_failed_bypassed", None)
        raw_control_cond = getattr(incident, "control_condition", None)
        raw_control_type = getattr(incident, "control_type", None)
        raw_energy_type = getattr(incident, "energy_type", None)

        # 1. Evaluate Control State & Evidence
        control_state = ControlSemantics.UNKNOWN
        control_evidence = UNKNOWN_CONTROL_EVIDENCE_TEXT
        source_field = "control_condition"

        # Check structured field first
        raw_cond_lower = str(raw_control_cond).strip().lower() if raw_control_cond else ""
        if raw_failed_bypassed is True or raw_cond_lower in ["failed", "bypassed", "absent"]:
            control_state = ControlSemantics.COMPROMISED
            cond_str = str(raw_control_cond).strip() if raw_control_cond else "bypassed"
            control_evidence = f"Structured control condition explicitly recorded as '{cond_str}'"
            source_field = "control_condition"
        elif raw_cond_lower in ["effective", "held"] or "effective" in raw_cond_lower:
            control_state = ControlSemantics.CONTROLLED
            control_evidence = "Structured control condition explicitly recorded as 'Effective / Held'"
            source_field = "control_condition"
        else:
            # Check narrative for explicit control cues
            effective_span = _extract_first_match_span(narrative, CONTROL_EFFECTIVE_PATTERNS)
            compromise_span = _extract_first_match_span(narrative, CONTROL_COMPROMISED_PATTERNS)

            if compromise_span and not effective_span:
                control_state = ControlSemantics.COMPROMISED
                control_evidence = compromise_span
                source_field = "composite_narrative"
            elif effective_span and not compromise_span:
                control_state = ControlSemantics.CONTROLLED
                control_evidence = effective_span
                source_field = "composite_narrative"
            elif effective_span and compromise_span:
                control_state = ControlSemantics.PARTIALLY_EFFECTIVE
                control_evidence = f"{compromise_span} (effective control also cited: {effective_span})"
                source_field = "composite_narrative"
            else:
                # No explicit evidence: UNKNOWN
                control_state = ControlSemantics.UNKNOWN
                control_evidence = UNKNOWN_CONTROL_EVIDENCE_TEXT
                source_field = "none"

        # 2. Extract matched IOGP Rule
        iogp_tags = list(incident.iogp_rules.all()) if hasattr(incident, "iogp_rules") else []
        matched_rule_names = [t.rule for t in iogp_tags]
        primary_rule = matched_rule_names[0] if matched_rule_names else "General Life-Saving Rule"

        # 3. Hazard & Energy Context
        hazard_concept = raw_energy_type or "Operational Hazard"
        hazard_energy = {
            "source_field": "energy_type" if raw_energy_type else "composite_narrative",
            "normalized_concept": hazard_concept,
            "high_energy_present": bool(incident.high_energy_present),
            "evidence_text": f"Energy type: {hazard_concept}",
        }

        # 4. Exposure Context
        exposure = {
            "source_field": "worker_exposed" if incident.worker_exposed is not None else "composite_narrative",
            "state": "EXPOSED" if incident.worker_exposed else "UNKNOWN",
            "evidence_text": "Worker in hazardous zone" if incident.worker_exposed else "Exposure unconfirmed in report metadata",
        }

        # 5. Critical Control Context
        ctrl_name = raw_control_type or (primary_rule + " Control")
        critical_control = {
            "control_type": ctrl_name,
            "hierarchy": "Direct Engineered Control",
            "source_field": source_field,
            "evidence_text": control_evidence,
            "evidence_strength": "STRONG" if control_state != ControlSemantics.UNKNOWN else "WEAK",
        }

        # 6. PSIF Pathway Role
        pred = getattr(incident, "prediction", None)
        is_psif = bool(pred.psif_predicted) if pred else False
        if is_psif:
            pathway_role = "Primary Barrier Precursor" if control_state == ControlSemantics.COMPROMISED else "Operational Hazard Context"
        else:
            pathway_role = "Capacity / Controlled Energy" if control_state == ControlSemantics.CONTROLLED else "Defended / Low Risk"

        psif_pathway = {
            "pathway_role": pathway_role,
            "psif_predicted": is_psif,
            "pathway_state": "OPEN" if is_psif else "INTERRUPTED",
        }

        return BarrierLinkage(
            incident_id=str(incident.id),
            hazard_energy=hazard_energy,
            exposure=exposure,
            critical_control=critical_control,
            control_state=control_state,
            control_evidence=control_evidence,
            iogp_rule=primary_rule,
            psif_pathway=psif_pathway,
            reason_method="deterministic_evidence_grounded",
        )

    @classmethod
    def evaluate_incident_barrier_context(cls, incident: Incident) -> Dict[str, Any]:
        """
        Integrates barrier intelligence into Task 9 Unified Investigation Workspace.
        Provides canonical reasoning result for each matched rule:
        - Relevant barrier/rule
        - Control state (CONTROLLED, COMPROMISED, UNKNOWN, NOT_APPLICABLE)
        - Evidence
        - Evidence strength
        - PSIF pathway role
        - IOGP rule match
        - Corrective action linkage
        """
        linkage = cls.evaluate_incident_control_linkage(incident)
        portfolio = cls.get_barrier_portfolio()
        fleet_map = {b["canonical_rule"]: b for b in portfolio.get("barriers", [])}

        iogp_tags = list(incident.iogp_rules.all()) if hasattr(incident, "iogp_rules") else []
        iogp_rule_names = [t.rule for t in iogp_tags]

        barrier_items = []
        for tag in iogp_tags:
            r_name = tag.rule
            canonical_r = normalize_iogp_rule(r_name).canonical_value
            fleet_info = fleet_map.get(canonical_r, {})

            # Rule match details
            matched_kw = getattr(tag, "matched_keywords", [])
            matched_text = ", ".join(matched_kw) if isinstance(matched_kw, list) else str(matched_kw or "")
            matched_f = getattr(tag, "matched_fields", [])
            source_field = ", ".join(matched_f) if isinstance(matched_f, list) and matched_f else "composite_narrative"

            # Derive grounded action linkage
            if canonical_r == "Energy Isolation":
                if linkage.control_state == ControlSemantics.COMPROMISED:
                    action_link = "Verify isolation/bypass-control compliance at the identified work activity."
                else:
                    action_link = "Verify isolation status and evidence of effective energy isolation."
            elif linkage.control_state == ControlSemantics.COMPROMISED:
                action_link = f"Verify {canonical_r} critical control integrity and restore barrier safeguards."
            else:
                action_link = f"Verify operational adherence and Start Work Checks for {canonical_r}."

            barrier_items.append({
                "rule": r_name,
                "canonical_rule": canonical_r,
                "control_state": linkage.control_state,
                "control_state_badge": (
                    "badge-success" if linkage.control_state == ControlSemantics.CONTROLLED
                    else ("badge-danger" if linkage.control_state == ControlSemantics.COMPROMISED else "badge-neutral")
                ),
                "evidence": linkage.control_evidence,
                "evidence_strength": linkage.critical_control.get("evidence_strength", "MODERATE"),
                "psif_pathway_role": linkage.psif_pathway.get("pathway_role", "Operational Context"),
                "iogp_rule_match": {
                    "matched_keywords": matched_text,
                    "source_field": source_field,
                    "method": getattr(tag, "classification_method", "rule_based"),
                },
                "action_linkage": action_link,
                "matched_observations": fleet_info.get("matched_observations", 0),
                "formatted_matched": fleet_info.get("formatted_matched", "0"),
                "psif_linked_observations": fleet_info.get("psif_linked_observations", 0),
                "formatted_psif_linked": fleet_info.get("formatted_psif_linked", "0"),
                "psif_linkage_rate": fleet_info.get("psif_linkage_rate", 0.0),
                "affected_sites": fleet_info.get("affected_sites", 0),
                "formatted_affected_sites": fleet_info.get("formatted_affected_sites", "0"),
            })

        return {
            "items": barrier_items,
            "count": len(barrier_items),
            "methodology_statement": METHODOLOGY_STATEMENT,
            "disclaimer": (
                "Barrier intelligence links observations to canonical safety-rule domains and evidence-supported "
                "control states. Rule matching alone does not establish a control failure or barrier effectiveness."
            ),
            "empty_message": "No canonical barrier or IOGP rule matches identified for this incident.",
        }

    @classmethod
    def invalidate_barrier_cache(cls) -> None:
        """Invalidates cached barrier intelligence portfolio."""
        cache.delete(CACHE_KEY_BARRIER_INTELLIGENCE)
        logger.info("Barrier intelligence cache invalidated: %s", CACHE_KEY_BARRIER_INTELLIGENCE)
