"""
Exposure Mechanisms, Worker Positioning, and Exposure States
apps/incidents/knowledge/exposures.py
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


class ExposureState:
    """Canonical exposure states defining the physical relationship between worker and energy."""
    DIRECT_EXPOSURE = "DIRECT_EXPOSURE"
    IN_RELEASE_PATH = "IN_RELEASE_PATH"
    INSIDE_EXCLUSION_ZONE = "INSIDE_EXCLUSION_ZONE"
    NEARBY_BUT_PROTECTED = "NEARBY_BUT_PROTECTED"
    NO_WORKER_EXPOSURE = "NO_WORKER_EXPOSURE"
    EXPOSURE_INTERRUPTED = "EXPOSURE_INTERRUPTED"
    POTENTIAL_EXPOSURE = "POTENTIAL_EXPOSURE"
    UNKNOWN = "UNKNOWN"


class WorkerPositionState:
    """Granular worker positioning vectors relative to the hazard release zone."""
    INSIDE_LINE_OF_FIRE = "INSIDE_LINE_OF_FIRE"
    UNDER_SUSPENDED_LOAD = "UNDER_SUSPENDED_LOAD"
    AT_UNPROTECTED_EDGE = "AT_UNPROTECTED_EDGE"
    INSIDE_CONFINED_SPACE = "INSIDE_CONFINED_SPACE"
    INSIDE_VEHICLE_TRAJECTORY = "INSIDE_VEHICLE_TRAJECTORY"
    IN_ELECTRICAL_FLASH_BOUNDARY = "IN_ELECTRICAL_FLASH_BOUNDARY"
    OUTSIDE_EXCLUSION_ZONE = "OUTSIDE_EXCLUSION_ZONE"
    BEHIND_PHYSICAL_BARRIER = "BEHIND_PHYSICAL_BARRIER"
    REMOTE_CONTROL_STATION = "REMOTE_CONTROL_STATION"
    UNKNOWN = "UNKNOWN"


@dataclass
class ExtractedExposure:
    """Structured extraction output representing personnel exposure evidence."""
    state: str
    worker_present: bool
    evidence_text: Optional[str] = None
    source_field: str = "composite_narrative"
    worker_positioning: Optional[str] = None
