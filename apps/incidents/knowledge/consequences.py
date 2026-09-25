"""
18 Physical Consequence Mechanisms & SIF Pathway States
apps/incidents/knowledge/consequences.py
"""
from dataclasses import dataclass
from typing import Optional


class ConsequenceMechanism:
    """18 Canonical physical consequence mechanisms causing serious harm or fatality."""
    FALL = "FALL"
    STRUCK_BY = "STRUCK_BY"
    CAUGHT_BETWEEN = "CAUGHT_BETWEEN"
    ENTANGLEMENT = "ENTANGLEMENT"
    CRUSHING = "CRUSHING"
    AMPUTATION = "AMPUTATION"
    ELECTRICAL_CONTACT = "ELECTRICAL_CONTACT"
    ARC_FLASH = "ARC_FLASH"
    PRESSURE_RELEASE = "PRESSURE_RELEASE"
    FLUID_INJECTION = "FLUID_INJECTION"
    PROJECTILE = "PROJECTILE"
    FIRE = "FIRE"
    FLASH_FIRE = "FLASH_FIRE"
    EXPLOSION = "EXPLOSION"
    TOXIC_EXPOSURE = "TOXIC_EXPOSURE"
    ASPHYXIATION = "ASPHYXIATION"
    ENGULFMENT = "ENGULFMENT"
    DROPPED_OBJECT = "DROPPED_OBJECT"


class ConsequencePathwayState:
    """Physical state of the serious injury / fatality consequence pathway."""
    SUPPORTED = "SUPPORTED"
    INTERRUPTED = "INTERRUPTED"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class ExtractedConsequence:
    """Structured extraction output representing the evaluated consequence pathway."""
    pathway_state: str
    mechanism: Optional[str] = None
    physical_mechanism: Optional[str] = None
    credible_sif_potential: bool = False
    evidence_text: Optional[str] = None
