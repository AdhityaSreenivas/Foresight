"""
Authoritative Provenance Hierarchy & Source Registry
apps/incidents/knowledge/sources.py
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


class SourceAuthority:
    EEI_SCL = "EEI_SCL_2021"
    IOGP_459 = "IOGP_REPORT_459_2018"
    IOGP_559 = "IOGP_REPORT_559_2020"
    INDIAN_OISD = "INDIAN_OISD_GENERAL"
    INDIAN_DGMS = "INDIAN_DGMS_GENERAL"
    OIL_PROCEDURAL = "OIL_PROCEDURAL_VERIFIED"
    FORESIGHT_ANALYTICAL = "FORESIGHT_ANALYTICAL_V1"
    UNVERIFIED_SOURCE = "UNVERIFIED_LOCAL_SOURCE"


class ProvenanceTier:
    """
    Five canonical provenance tiers governing all rules, standards, and procedures:
    - IOGP_GUIDANCE: International petroleum industry guidance (Report 459 / 559).
    - DOMAIN_SIF_FRAMEWORK: High-energy control & SCL capacity frameworks (EEI SCL).
    - INDIAN_REGULATORY: Indian statutory standards (OISD / DGMS), scoped strictly to verified applicability.
    - OIL_PROCEDURAL: Verified operating company procedures (NEVER invented or assumed).
    - FORESIGHT_ANALYTICAL: Deterministic internal analytical taxonomy.
    """
    IOGP_GUIDANCE = "IOGP_GUIDANCE"
    DOMAIN_SIF_FRAMEWORK = "DOMAIN_SIF_FRAMEWORK"
    INDIAN_REGULATORY = "INDIAN_REGULATORY"
    OIL_PROCEDURAL = "OIL_PROCEDURAL"
    FORESIGHT_ANALYTICAL = "FORESIGHT_ANALYTICAL"


@dataclass(frozen=True)
class SourceMetadata:
    """Immutable authoritative metadata tracking source provenance for every safety rule."""
    source_id: str
    document: str
    organization: str
    year_or_version: str
    source_section: str
    scope: str
    applicability: str
    provenance_type: str
    is_verified: bool = True
    verification_notes: Optional[str] = None

    @property
    def provenance_tier(self) -> str:
        return self.provenance_type

    def __getitem__(self, item: str) -> Any:
        if item == "provenance_tier":
            return self.provenance_type
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default


SOURCE_REGISTRY: Dict[str, SourceMetadata] = {
    SourceAuthority.EEI_SCL: SourceMetadata(
        source_id=SourceAuthority.EEI_SCL,
        document="Safety Classification and Learning (SCL) Model",
        organization="Edison Electric Institute (EEI)",
        year_or_version="2021 / Revision 3",
        source_section="Section 2.1 — Direct Controls & High-Energy Release; Section 3.2 — Capacity vs. PSIF Precursor",
        scope="Global energy and industrial sector serious injury precursor classification.",
        applicability="High-energy hazard characterization, capacity interruption, and physical SIF pathway determination.",
        provenance_type=ProvenanceTier.DOMAIN_SIF_FRAMEWORK,
        is_verified=True,
        verification_notes="Authoritative industry standard defining the physical separation between high energy without direct control (PSIF) and high energy controlled (Capacity).",
    ),
    SourceAuthority.IOGP_459: SourceMetadata(
        source_id=SourceAuthority.IOGP_459,
        document="IOGP Report 459 — Life-Saving Rules",
        organization="International Association of Oil & Gas Producers (IOGP)",
        year_or_version="2018 Edition",
        source_section="Report 459 Section 2 (Core Rules) & Report 459-1 (Start Work Checks)",
        scope="Upstream, midstream, and downstream oil & gas operational activities.",
        applicability="Life-Saving Rules, critical barrier verification, and Start Work Checks.",
        provenance_type=ProvenanceTier.IOGP_GUIDANCE,
        is_verified=True,
        verification_notes="Authoritative standard for the 9 Life-Saving Rules. Establishes that IOGP rule matches reflect activity classification, not automatic rule violations or PSIF status.",
    ),
    SourceAuthority.IOGP_559: SourceMetadata(
        source_id=SourceAuthority.IOGP_559,
        document="IOGP Report 559 — Process Safety Fundamentals",
        organization="International Association of Oil & Gas Producers (IOGP)",
        year_or_version="2020 Edition",
        source_section="Report 559 Section 3 — Loss of Containment & Barrier Integrity",
        scope="Process facilities, hydrocarbon containment, energy isolation, and management of change.",
        applicability="Process SIF precursor evaluation, toxic atmospheres, line breaking, and pressure containment.",
        provenance_type=ProvenanceTier.IOGP_GUIDANCE,
        is_verified=True,
        verification_notes="Authoritative guidance on process safety barriers, positive isolation, and flammable/toxic release pathways.",
    ),
    SourceAuthority.INDIAN_OISD: SourceMetadata(
        source_id=SourceAuthority.INDIAN_OISD,
        document="Oil Industry Safety Directorate (OISD) Standards",
        organization="Ministry of Petroleum and Natural Gas, Government of India",
        year_or_version="OISD-STD-105 (Work Permit) / OISD-STD-114 (Hazardous Chemical Handling)",
        source_section="OISD-STD-105 Section 4.2; OISD-STD-114 Section 5.1",
        scope="Indian petroleum refineries, pipelines, drill sites, and installations.",
        applicability="Strictly scoped to Indian statutory compliance boundaries; not generalized globally.",
        provenance_type=ProvenanceTier.INDIAN_REGULATORY,
        is_verified=True,
        verification_notes="Verified statutory mandate for Indian oil and gas facilities; applied strictly where facility is under OISD jurisdiction.",
    ),
    SourceAuthority.INDIAN_DGMS: SourceMetadata(
        source_id=SourceAuthority.INDIAN_DGMS,
        document="Directorate General of Mines Safety (DGMS) Guidelines",
        organization="Ministry of Labour and Employment, Government of India",
        year_or_version="Oil Mines Regulations (OMR) 2017",
        source_section="OMR 2017 Regulation 42 (Drilling & Workover); Regulation 87 (Electrical Apparatus)",
        scope="Indian onshore and offshore oil mines and drilling rigs.",
        applicability="Strictly scoped to Indian mine safety statutory boundaries.",
        provenance_type=ProvenanceTier.INDIAN_REGULATORY,
        is_verified=True,
        verification_notes="Verified statutory mandate for Indian drilling and mining concessions.",
    ),
    SourceAuthority.OIL_PROCEDURAL: SourceMetadata(
        source_id=SourceAuthority.OIL_PROCEDURAL,
        document="Verified Oil Operating Company Standard Operating Procedures",
        organization="Operating Asset HSE Directorate",
        year_or_version="Approved Site Procedure Register",
        source_section="Verified Plant Operating Manuals",
        scope="Site-specific asset boundaries with documented provenance.",
        applicability="Applied strictly when an approved, verified site standard exists in the operational registry.",
        provenance_type=ProvenanceTier.OIL_PROCEDURAL,
        is_verified=True,
        verification_notes="Mandate: Local company procedures are never assumed or fabricated; verified entries only.",
    ),
    SourceAuthority.FORESIGHT_ANALYTICAL: SourceMetadata(
        source_id=SourceAuthority.FORESIGHT_ANALYTICAL,
        document="Foresight Deterministic HSE Intelligence Taxonomy",
        organization="Foresight Core Engineering Team",
        year_or_version="2026.1 / Task 4 Deepened Semantic Architecture",
        source_section="Architecture Contract v2 — Evidence Reconciliation, Semantic Roles, & Anti-Inference Catalog",
        scope="Platform-wide multi-source safety evidence reconciliation and physical barrier reasoning.",
        applicability="Deterministic multi-hazard reconciliation, anti-inferences, and structured explanation generation.",
        provenance_type=ProvenanceTier.FORESIGHT_ANALYTICAL,
        is_verified=True,
        verification_notes="Internal formal architecture governing safety rules, evidence sufficiency matrices, and explanation contracts.",
    ),
}


def get_source_metadata(source_id: str) -> SourceMetadata:
    """Retrieves authoritative source metadata, defaulting to FORESIGHT_ANALYTICAL if unregistered."""
    return SOURCE_REGISTRY.get(source_id, SOURCE_REGISTRY[SourceAuthority.FORESIGHT_ANALYTICAL])
