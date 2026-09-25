"""
Semantic Roles & Temporal Ordering Knowledge
apps/incidents/knowledge/temporal.py
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


class SemanticRole:
    """
    Semantic role of an extracted statement or observation.
    Prevents confusing post-incident desires with contemporaneous physical states.
    """
    EVENT = "EVENT"                                       # Actual physical occurrence during incident
    OBSERVED_STATE = "OBSERVED_STATE"                     # Baseline condition observed at scene
    VERIFIED_STATE = "VERIFIED_STATE"                     # Explicitly checked and confirmed barrier state
    HISTORICAL_STATE = "HISTORICAL_STATE"                 # Past operational condition prior to current shift
    RECOMMENDED = "RECOMMENDED"                           # Post-incident remedial recommendation
    PLANNED = "PLANNED"                                   # Scheduled or intended future action
    FUTURE = "FUTURE"                                     # Prospective statement (will occur)
    DISCOVERED_SUBSEQUENTLY = "DISCOVERED_SUBSEQUENTLY"   # Latent defect discovered during investigation
    RESTORED_BEFORE_EXPOSURE = "RESTORED_BEFORE_EXPOSURE"# Barrier restored prior to personnel exposure
    RESTORED_AFTER_EXPOSURE = "RESTORED_AFTER_EXPOSURE"   # Barrier repaired after incident occurred


class TemporalPhase:
    """Causal operational phases governing incident progression."""
    BEFORE_WORK = "BEFORE_WORK"           # Planning, toolbox talk, pre-job permit stage
    DURING_WORK = "DURING_WORK"           # Normal active operational execution
    BEFORE_EXPOSURE = "BEFORE_EXPOSURE"   # Hazard manifested or detected prior to worker entry
    DURING_EXPOSURE = "DURING_EXPOSURE"   # Worker actively inside energy release envelope
    AFTER_EXPOSURE = "AFTER_EXPOSURE"     # Consequence realization or immediate aftermath
    AFTER_WORK = "AFTER_WORK"             # Shift handover or post-task securing
    POST_INCIDENT = "POST_INCIDENT"       # Investigation, remedial recommendation, PM schedule


@dataclass
class TemporalExpression:
    """Structured temporal expression extracted from incident reporting."""
    raw_text: str
    phase: str
    semantic_role: str
    is_contemporaneous: bool = True
    event_relevance: str = "DIRECT"


def extract_temporal_expressions(text: str) -> List[TemporalExpression]:
    """
    Extracts structured temporal expressions and semantic roles from incident narrative.
    Distinguishes contemporaneous barrier conditions from recommendations and future plans.
    """
    if not text:
        return []

    expressions: List[TemporalExpression] = []
    text_lower = text.lower()

    # Pattern mappings for temporal extraction:
    patterns = [
        (["restored before", "fixed prior to", "replaced before starting", "installed prior to entry", "isolated before entry"],
         TemporalPhase.BEFORE_EXPOSURE, SemanticRole.RESTORED_BEFORE_EXPOSURE, True),
        (["restored after", "repaired subsequently", "fixed following", "reinstalled after incident", "replaced post-incident"],
         TemporalPhase.AFTER_EXPOSURE, SemanticRole.RESTORED_AFTER_EXPOSURE, False),
        (["should be", "recommended to", "advise that", "suggest that", "action recommended"],
         TemporalPhase.POST_INCIDENT, SemanticRole.RECOMMENDED, False),
        (["will be", "planned to", "to be replaced", "scheduled for next", "to be rectified", "target completion"],
         TemporalPhase.POST_INCIDENT, SemanticRole.PLANNED, False),
        (["verified zero", "tested before touch", "confirmed isolated", "measured 0v", "zero pressure confirmed", "lock applied and verified"],
         TemporalPhase.BEFORE_WORK, SemanticRole.VERIFIED_STATE, True),
        (["previously observed", "past history", "prior shift report", "historically known"],
         TemporalPhase.BEFORE_WORK, SemanticRole.HISTORICAL_STATE, False),
        (["investigation revealed", "later found", "subsequently discovered", "post-incident audit noted"],
         TemporalPhase.POST_INCIDENT, SemanticRole.DISCOVERED_SUBSEQUENTLY, False),
    ]

    for keywords, phase, role, contemporaneous in patterns:
        for kw in keywords:
            if kw in text_lower:
                expressions.append(TemporalExpression(
                    raw_text=kw,
                    phase=phase,
                    semantic_role=role,
                    is_contemporaneous=contemporaneous,
                    event_relevance="DIRECT",
                ))

    return expressions
