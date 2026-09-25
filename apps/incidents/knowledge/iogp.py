"""
IOGP Life-Saving Rules & Independence Contracts
apps/incidents/knowledge/iogp.py
"""
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


class IOGPRuleCode:
    """Official 9 IOGP Life-Saving Rules (Report 459)."""
    BYPASSING_SAFETY_CONTROLS = "Bypassing Safety Controls"
    CONFINED_SPACE = "Confined Space"
    DRIVING = "Driving"
    ENERGY_ISOLATION = "Energy Isolation"
    HOT_WORK = "Hot Work"
    LINE_OF_FIRE = "Line of Fire"
    SAFE_MECHANICAL_LIFTING = "Safe Mechanical Lifting"
    WORK_AUTHORIZATION = "Work Authorization"
    WORKING_AT_HEIGHT = "Working at Height"


IOGP_RULE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    IOGPRuleCode.BYPASSING_SAFETY_CONTROLS: {
        "rule": IOGPRuleCode.BYPASSING_SAFETY_CONTROLS,
        "icon": "shield-exclamation",
        "description": "Obtain authorization before overriding or disabling safety controls.",
        "source_section": "IOGP Report 459 (2018) Section 2.1 Bypassing Safety Controls",
        "start_work_checks": [
            "I understand and use safety-critical equipment and procedures which apply to my task.",
            "I obtain authorization before: disabling or overriding safety equipment, deviating from procedures, or crossing a barrier.",
            "I confirm that compensatory measures are implemented before overriding any safety device.",
        ],
    },
    IOGPRuleCode.CONFINED_SPACE: {
        "rule": IOGPRuleCode.CONFINED_SPACE,
        "icon": "box-arrow-in-down",
        "description": "Obtain authorization before entering a confined space.",
        "source_section": "IOGP Report 459 (2018) Section 2.2 Confined Space",
        "start_work_checks": [
            "I confirm energy sources are isolated.",
            "I confirm the atmosphere has been tested and is monitored.",
            "I check and use my breathing apparatus when required.",
            "I confirm there is an attendant on duty.",
            "I confirm a rescue plan is in place.",
        ],
    },
    IOGPRuleCode.DRIVING: {
        "rule": IOGPRuleCode.DRIVING,
        "icon": "truck",
        "description": "Follow safe driving rules.",
        "source_section": "IOGP Report 459 (2018) Section 2.3 Driving",
        "start_work_checks": [
            "I always wear a seatbelt.",
            "I do not exceed the speed limit, and reduce speed for road conditions.",
            "I do not use only a mobile phone while driving.",
            "I am fit, rested and fully alert while driving.",
        ],
    },
    IOGPRuleCode.ENERGY_ISOLATION: {
        "rule": IOGPRuleCode.ENERGY_ISOLATION,
        "icon": "lightning-charge",
        "description": "Verify isolation and zero energy before work begins.",
        "source_section": "IOGP Report 459 (2018) Section 2.4 Energy Isolation",
        "start_work_checks": [
            "I have identified all energy sources.",
            "I confirm that hazardous energy sources have been isolated, locked, and tagged.",
            "I have checked that zero energy has been verified.",
            "I remain aware of any residual energy.",
        ],
    },
    IOGPRuleCode.HOT_WORK: {
        "rule": IOGPRuleCode.HOT_WORK,
        "icon": "fire",
        "description": "Control flammables and ignition sources.",
        "source_section": "IOGP Report 459 (2018) Section 2.5 Hot Work",
        "start_work_checks": [
            "I have identified and controlled all potential ignition sources.",
            "Before starting any hot work, I confirm the atmosphere has been tested.",
            "I verify that there is no combustible material in the work area.",
            "I confirm that a designated fire watch is present.",
        ],
    },
    IOGPRuleCode.LINE_OF_FIRE: {
        "rule": IOGPRuleCode.LINE_OF_FIRE,
        "icon": "bullseye",
        "description": "Keep yourself and others out of the line of fire.",
        "source_section": "IOGP Report 459 (2018) Section 2.6 Line of Fire",
        "start_work_checks": [
            "I position myself to avoid: moving objects, vehicles, pressure releases, and dropped objects.",
            "I establish and obey red zones, exclusion zones, and barriers.",
            "I take action to secure loose objects and report potential dropped objects.",
        ],
    },
    IOGPRuleCode.SAFE_MECHANICAL_LIFTING: {
        "rule": IOGPRuleCode.SAFE_MECHANICAL_LIFTING,
        "icon": "gear-wide-connected",
        "description": "Plan lifting operations and control the area.",
        "source_section": "IOGP Report 459 (2018) Section 2.7 Safe Mechanical Lifting",
        "start_work_checks": [
            "I confirm that the equipment and load have been inspected and are fit for purpose.",
            "I only operate equipment that I am qualified to use.",
            "I establish and obey the exclusion zone.",
            "I never walk or stand under a suspended load.",
        ],
    },
    IOGPRuleCode.WORK_AUTHORIZATION: {
        "rule": IOGPRuleCode.WORK_AUTHORIZATION,
        "icon": "file-earmark-check",
        "description": "Work with a valid permit when required.",
        "source_section": "IOGP Report 459 (2018) Section 2.8 Work Authorization",
        "start_work_checks": [
            "I have confirmed whether a permit is required.",
            "I am authorized to perform the work.",
            "I understand the permit requirements and have confirmed that hazards are controlled.",
            "I stop and re-assess if conditions change.",
        ],
    },
    IOGPRuleCode.WORKING_AT_HEIGHT: {
        "rule": IOGPRuleCode.WORKING_AT_HEIGHT,
        "icon": "person-bounding-box",
        "description": "Protect yourself against a fall when working at height.",
        "source_section": "IOGP Report 459 (2018) Section 2.9 Working at Height",
        "start_work_checks": [
            "I have inspected my fall protection equipment before use.",
            "I secure tools and work materials to prevent dropped objects.",
            "I tie off 100% to an approved anchor point while outside a protected area.",
        ],
    },
}


@dataclass
class IOGPSeparationResult:
    """
    Demonstrates the structural separation principle:
    IOGP_MATCH != IOGP_VIOLATION != PSIF
    """
    iogp_rule_matched: bool
    iogp_applicability: List[str]
    rule_adherence: str  # COMPLIANT, VIOLATED, UNKNOWN
    worker_exposure: str
    control_state: str
    sif_pathway: str
    psif_decision: str
    separation_rationale: str


def get_iogp_rule_definition(rule_code: str) -> Optional[Dict[str, Any]]:
    """Retrieves authoritative IOGP Life-Saving Rule definition."""
    return IOGP_RULE_DEFINITIONS.get(rule_code)
