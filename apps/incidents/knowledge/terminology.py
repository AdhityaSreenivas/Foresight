"""
Structured Semantic Terminology & Synonym Clusters
apps/incidents/knowledge/terminology.py

Organizes domain vocabulary into coherent semantic clusters rather than flat keyword sets.
Maps natural field phrasing to normalized safety concepts.
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class SemanticConcept:
    concept_id: str
    canonical_name: str
    domain: str
    synonyms: List[str]
    effective_cues: List[str]
    compromised_cues: List[str]
    exposure_cues: List[str]


TERMINOLOGY_CLUSTERS: Dict[str, SemanticConcept] = {
    "energy_isolation": SemanticConcept(
        concept_id="energy_isolation",
        canonical_name="Positive Energy Isolation (LOTO)",
        domain="Pressure / Electrical / Mechanical",
        synonyms=["loto", "lockout/tagout", "lockout", "tagout", "positive isolation", "double block and bleed", "blinding", "blind flange", "spade", "de-energized", "zero energy", "depressurized", "isolated"],
        effective_cues=["isolation verified", "valves held absolute isolation", "verified zero pressure", "depressurized to zero", "verified zero voltage", "held throughout"],
        compromised_cues=["isolation failed", "valve passing", "omitted opening bleeder", "lockout not applied", "not verified", "wrong isolation point", "residual pressure released"],
        exposure_cues=["line breaking", "breaking flange", "unbolting live", "tightening under pressure", "in release path"],
    ),
    "working_at_height": SemanticConcept(
        concept_id="working_at_height",
        canonical_name="Fall Protection at Height",
        domain="Working at Height",
        synonyms=["scaffold", "scaffolding", "scaffolder", "ladder", "mewp", "manlift", "elevated platform", "pipe rack", "derrick mast", "fall arrest", "harness", "srl", "self-retracting lifeline", "lanyard", "anchor", "tie-off", "guardrail"],
        effective_cues=["fall arrest installed and verified", "100% tie-off maintained", "guardrail held", "harness arrested", "netting caught", "tied off"],
        compromised_cues=["lanyards unhitched", "lanyard unclipped", "detached harness", "guardrail missing", "not anchored", "frayed lanyard"],
        exposure_cues=["worked at height", "working at 8 metres", "worked at 7 meters elevation", "at unprotected edge", "fell from"],
    ),
    "lifting_rigging": SemanticConcept(
        concept_id="lifting_rigging",
        canonical_name="Mechanical Lifting & Rigging",
        domain="Lifting Operations",
        synonyms=["crane", "mobile crane", "hoist", "winch", "rigging", "sling", "synthetic sling", "wire rope", "shackle", "spreader bar", "tag line", "banksman", "rigger", "suspended load", "lift radius", "drop zone"],
        effective_cues=["remained outside exclusion zone", "behind designated safety barrier", "remote console operation", "slings held firm", "exclusion zone maintained"],
        compromised_cues=["stood beneath suspended load", "entered exclusion zone", "sling parted", "dropped assembly", "rigging failed", "crossed inside barrier"],
        exposure_cues=["underneath load", "under suspended load", "in crane radius", "beneath hoisted package"],
    ),
    "confined_space": SemanticConcept(
        concept_id="confined_space",
        canonical_name="Confined Space Atmospheric Safety",
        domain="Atmospheric & Confined Space",
        synonyms=["confined space", "tank entry", "vessel entry", "manhole", "sewer", "manway", "scrubber", "column", "nitrogen purge", "atmospheric testing", "gas monitoring", "oxygen deficiency", "h2s"],
        effective_cues=["continuous gas testing confirmed", "safe atmosphere verified", "alarm sounded and crew cleared", "positive mechanical blinds installed"],
        compromised_cues=["entered without continuous monitoring", "gas testing was bypassed", "entered without permit", "nitrogen pocket", "lost consciousness"],
        exposure_cues=["entered vessel", "inside tank", "inside confined space", "leaned through manway", "entrant"],
    ),
    "electrical_systems": SemanticConcept(
        concept_id="electrical_systems",
        canonical_name="High Voltage & Arc Flash Control",
        domain="Electrical",
        synonyms=["switchgear", "cubicle", "breaker", "racking", "busbar", "copper busbar", "11kv", "33kv", "440v", "transformer", "arc flash", "live wire", "conductor", "electrocution"],
        effective_cues=["verified zero hazardous voltage", "remained fully locked out", "dead-front interlock engaged", "tested safe before touch"],
        compromised_cues=["absence of voltage not maintained", "lockout verification degraded", "energized-panel not closed off", "worked live", "arc flash occurred"],
        exposure_cues=["direct contact trajectory", "contact with live", "opened energized switchgear", "inside flash boundary"],
    ),
    "vehicle_logistics": SemanticConcept(
        concept_id="vehicle_logistics",
        canonical_name="Vehicle & Pedestrian Segregation",
        domain="Logistics & Transport",
        synonyms=["forklift", "truck", "delivery truck", "heavy vehicle", "tractor-trailer", "loading bay", "pedestrian walkway", "segregation barrier", "bollard", "reverse alarm", "spotter"],
        effective_cues=["stayed outside reversing zone", "behind segregation walkway barriers", "reversing alarm held throughout", "bolted steel barrier prevented vehicle encroaching"],
        compromised_cues=["reverse alarm disabled", "backup alarm broken", "severed wiring harness", "entered vehicle path", "rolled over foot"],
        exposure_cues=["in vehicle path", "in front of moving", "behind reversing truck", "in travel path"],
    ),
    "hot_work": SemanticConcept(
        concept_id="hot_work",
        canonical_name="Hot Work Spark & Fire Containment",
        domain="Hot Work / Ignition",
        synonyms=["hot work", "welding", "torch cutting", "oxy-acetylene", "cutting torch", "grinding", "welding sparks", "hot slag", "fire blanket", "fire watch"],
        effective_cues=["dedicated fire watch immediately doused", "fire blanket completely sealed deck", "continuous gas test zero lel"],
        compromised_cues=["slag rolled past fire blanket", "hot work started without gas test", "sparks contacted combustible"],
        exposure_cues=["in hot slag path", "welding spatter trajectory", "flash fire enveloped"],
    ),
    "excavation_ground": SemanticConcept(
        concept_id="excavation_ground",
        canonical_name="Excavation Shoring & Ground Stability",
        domain="Excavation & Civil",
        synonyms=["excavation", "trench", "trenching", "shoring box", "trench shield", "vertical cut", "soil collapse", "cave-in", "bell hole", "spoil pile"],
        effective_cues=["certified steel shoring box deployed", "workers shielded inside trench box", "soil sloped at 45 degrees", "trench shield held firm"],
        compromised_cues=["entered un-shored trench", "bypassed trench shoring boxes", "wall collapsed engulfing worker"],
        exposure_cues=["inside trench bed", "below vertical soil face", "in excavation"],
    ),
    "dropped_objects": SemanticConcept(
        concept_id="dropped_objects",
        canonical_name="Overhead Drop Prevention & Netting",
        domain="Dropped Objects",
        synonyms=["dropped object", "falling object", "fallen tool", "dropped clamp", "dropped pipe", "tool lanyard", "drop netting", "toe board", "red zone"],
        effective_cues=["tool lanyard arrested dynamic fall", "drop netting caught clamp", "toe boards installed and held"],
        compromised_cues=["drop netting absent", "tool untethered and fell", "object fell through grating"],
        exposure_cues=["working below scaffold", "under elevated platform", "in drop zone"],
    ),
}


def get_semantic_concept(concept_id: str) -> Optional[SemanticConcept]:
    """Retrieves structured semantic concept by identifier."""
    return TERMINOLOGY_CLUSTERS.get(concept_id)


@dataclass
class TerminologyMatch:
    concept_id: str
    canonical_name: str
    domain: str
    matched_text: str
    match_category: str  # SYNONYM, EFFECTIVE_CUE, COMPROMISED_CUE, EXPOSURE_CUE


def find_terminology_matches(text: str) -> List[TerminologyMatch]:
    """Scans narrative for terminology clusters, distinguishing synonyms, cues, and exposures."""
    if not text:
        return []
    text_lower = text.lower()
    matches: List[TerminologyMatch] = []
    for concept_id, concept in TERMINOLOGY_CLUSTERS.items():
        # Check synonyms
        for syn in concept.synonyms:
            if syn in text_lower:
                matches.append(TerminologyMatch(
                    concept_id=concept.concept_id,
                    canonical_name=concept.canonical_name,
                    domain=concept.domain,
                    matched_text=syn,
                    match_category="SYNONYM",
                ))
                break
        # Check effective cues
        for cue in concept.effective_cues:
            if cue in text_lower:
                matches.append(TerminologyMatch(
                    concept_id=concept.concept_id,
                    canonical_name=concept.canonical_name,
                    domain=concept.domain,
                    matched_text=cue,
                    match_category="EFFECTIVE_CUE",
                ))
                break
        # Check compromised cues
        for cue in concept.compromised_cues:
            if cue in text_lower:
                matches.append(TerminologyMatch(
                    concept_id=concept.concept_id,
                    canonical_name=concept.canonical_name,
                    domain=concept.domain,
                    matched_text=cue,
                    match_category="COMPROMISED_CUE",
                ))
                break
        # Check exposure cues
        for cue in concept.exposure_cues:
            if cue in text_lower:
                matches.append(TerminologyMatch(
                    concept_id=concept.concept_id,
                    canonical_name=concept.canonical_name,
                    domain=concept.domain,
                    matched_text=cue,
                    match_category="EXPOSURE_CUE",
                ))
                break
    return matches


def get_concepts_for_text(text: str) -> List[str]:
    """Returns unique concept IDs matched in text."""
    matches = find_terminology_matches(text)
    return list({m.concept_id for m in matches})
