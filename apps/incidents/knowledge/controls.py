"""
Control Hierarchy, Barrier Classifications, and Full Control States
apps/incidents/knowledge/controls.py
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


class ControlHierarchyType:
    """Standard industrial Hierarchy of Controls tiers."""
    ELIMINATION = "ELIMINATION"
    SUBSTITUTION = "SUBSTITUTION"
    DIRECT_ENGINEERED_CONTROL = "DIRECT_ENGINEERED_CONTROL"
    PROCEDURAL_CONTROL = "PROCEDURAL_CONTROL"
    ADMINISTRATIVE_CONTROL = "ADMINISTRATIVE_CONTROL"
    PPE = "PPE"


class ControlState:
    """
    12 Full operational states modeling physical barrier performance.
    Distinguishes effective, compromised, temporal restoration, and non-barrier mentions.
    """
    EFFECTIVE = "EFFECTIVE"
    PARTIALLY_EFFECTIVE = "PARTIALLY_EFFECTIVE"
    ABSENT = "ABSENT"
    FAILED = "FAILED"
    BYPASSED = "BYPASSED"
    NOT_VERIFIED = "NOT_VERIFIED"
    INCORRECTLY_ASSUMED = "INCORRECTLY_ASSUMED"
    RESTORED_BEFORE_EXPOSURE = "RESTORED_BEFORE_EXPOSURE"
    RESTORED_AFTER_EXPOSURE = "RESTORED_AFTER_EXPOSURE"
    PLANNED_ONLY = "PLANNED_ONLY"
    RECOMMENDATION_ONLY = "RECOMMENDATION_ONLY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ExtractedControl:
    """Structured extraction output representing safety control/barrier evidence."""
    control_type: Optional[str]
    state: str
    is_direct_control: bool
    is_compromised: bool
    hierarchy_type: str = ControlHierarchyType.DIRECT_ENGINEERED_CONTROL
    evidence_text: Optional[str] = None
    source_field: str = "control_condition"
