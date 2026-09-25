"""
Script to construct and validate the comprehensive 30 golden reasoning fixtures for Task 5.
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult
from apps.incidents.services.psif_reasoning import (
    build_incident_reasoning_assessment,
    InternalReasoningState,
    UserFacingDecision,
)

FIXTURES = [
    # 1. Clear Pressure PSIF
    {
        "id": "GOLDEN-01-CLEAR-PSIF",
        "name": "Clear PSIF: Pressurized Manifold Strike Under Live Load",
        "description": "Technician attempted to tighten union under live pressure on a 250 bar manifold without positive isolation. Threads stripped off, striking worker directly.",
        "incident": {
            "description": "Technician attempted to tighten the union under active hydraulic load on a 250 bar manifold without obtaining a permit or proving zero energy. The threads stripped off, and the pressurized line whipped, striking the worker directly in the chest causing severe internal injuries.",
            "composite_narrative": "Technician attempted to tighten the union under active hydraulic load on a 250 bar manifold without obtaining a permit or proving zero energy. The threads stripped off, and the pressurized line whipped, striking the worker directly in the chest causing severe internal injuries. [SEP] Investigation confirmed threads stripped under 250 bar pressure with technician positioned directly in the line of fire.",
            "injury_type": "severe_internal",
            "body_part": "chest"
        },
        "prediction": {
            "psif_score": 0.942,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "primary_hazard": "pressure_stored",
            "control_state": "FAILED",
            "exposure_state": "DIRECT_EXPOSURE",
            "credible_sif_potential": True,
            "evidence_strength": "STRONG",
            "agreement_state": "MODEL_AND_RULE_AGREE",
            "disagreement_type": None,
            "is_conflicting": False
        }
    },
    # 2. Pressure Controlled (Capacity)
    {
        "id": "GOLDEN-02-CAPACITY-NOT-PSIF",
        "name": "Clear Controlled High-Energy: Hydrotest Blast Containment Barricade (Capacity)",
        "description": "High pressure bleed fitting sheared at 320 bar during hydrostatic test. High pressure water stream hit interior wall of certified blast containment barricade with crew protected in monitoring trailer.",
        "incident": {
            "description": "High pressure bleed fitting sheared at 320 bar during proof test. High pressure water stream hit the interior wall of blast containment barricade. Interlocked warning beacons and perimeter fences were fully active, and testing personnel were staged 28 meters away inside the monitoring trailer.",
            "composite_narrative": "High pressure bleed fitting sheared at 320 bar during proof test. High pressure water stream hit the interior wall of blast containment barricade. Interlocked warning beacons and perimeter fences were fully active, and testing personnel were staged 28 meters away inside the monitoring trailer. [SEP] Blast containment barrier held securely and completely contained the 320 bar release.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.22,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "primary_hazard": "pressure_stored",
            "control_state": "EFFECTIVE",
            "exposure_state": "NEARBY_BUT_PROTECTED",
            "credible_sif_potential": False,
            "evidence_strength": "STRONG",
            "agreement_state": "MODEL_AND_RULE_AGREE",
            "disagreement_type": None,
            "is_conflicting": False
        }
    },
    # 3. Low-Energy NOT PSIF
    {
        "id": "GOLDEN-03-LOW-ENERGY-NOT-PSIF",
        "name": "Low-Energy NOT PSIF: Office Hallway Slip",
        "description": "Administrative clerk slipped on freshly cleaned office floor sustaining a minor ankle twist.",
        "incident": {
            "description": "Administrative clerk slipped on a freshly mopped office tile floor sustaining a minor ankle sprain. First aid ice pack applied; employee returned to regular desk duties.",
            "composite_narrative": "Administrative clerk slipped on a freshly mopped office tile floor sustaining a minor ankle sprain. First aid ice pack applied; employee returned to regular desk duties. [SEP] Office housekeeping caution cone was placed near doorway.",
            "injury_type": "sprain",
            "body_part": "ankle"
        },
        "prediction": {
            "psif_score": 0.012,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "LOW_ENERGY",
            "primary_hazard": "low_energy_general",
            "credible_sif_potential": False,
            "agreement_state": "MODEL_AND_RULE_AGREE",
            "disagreement_type": None,
            "is_conflicting": False
        }
    },
    # 4. Electrical Insufficient Information
    {
        "id": "GOLDEN-04-INSUFFICIENT-INFORMATION",
        "name": "Insufficient Information: Missing Substation Isolation Verification",
        "description": "Technician entered 11kV electrical substation yard to inspect control cabling with no recorded information on feeder isolation status.",
        "incident": {
            "description": "Technician entered 11kV electrical switchyard to inspect terminal cabinet cabling. Unclear whether the primary feeder was de-energized or if isolation had been verified prior to entry.",
            "composite_narrative": "Technician entered 11kV electrical switchyard to inspect terminal cabinet cabling. Unclear whether the primary feeder was de-energized or if isolation had been verified prior to entry. [SEP] Report submitted as preliminary notification pending full supervisor investigation.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.45,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "INSUFFICIENT_INFORMATION",
            "primary_hazard": "electrical",
            "control_state": "UNKNOWN",
            "agreement_state": "INSUFFICIENT_EVIDENCE",
            "high_priority_review": True,
            "is_conflicting": False
        }
    },
    # 5. Model/Rule Disagreement: False Negative
    {
        "id": "GOLDEN-05-DISAGREEMENT-FALSE-NEGATIVE",
        "name": "Model/Rule Disagreement: Potential False Negative (Unguarded Motor Shaft)",
        "description": "Mechanic inspected water injection pump motor rotating at 1,780 RPM where coupling guard was removed. Model scored low (0.046) due to neutral language, but rule catches critical hazard.",
        "incident": {
            "description": "Mechanic inspected motor running at 1,780 RPM. The protective mesh coupling guard was removed during rotation check while worker was troubleshooting nearby.",
            "composite_narrative": "Mechanic inspected motor running at 1,780 RPM. The protective mesh coupling guard was removed during rotation check while worker was troubleshooting nearby. [SEP] Rotating shaft was fully exposed within 30 centimeters of operator hands.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.046,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "primary_hazard": "mechanical_motion",
            "control_state": "FAILED",
            "agreement_state": "RULE_EVIDENCE_STRONGER_THAN_MODEL",
            "disagreement_type": "POTENTIAL_FALSE_NEGATIVE",
            "high_priority_review": True,
            "is_conflicting": False
        }
    },
    # 6. Model/Rule Disagreement: False Positive
    {
        "id": "GOLDEN-06-DISAGREEMENT-FALSE-POSITIVE",
        "name": "Model/Rule Disagreement: Potential False Positive (Protected Heavy Crane Lift)",
        "description": "12-ton compressor lifted by crane; words trigger statistical model (score 0.77), but exclusion zone was verified with rigid barricades and all personnel staged outside.",
        "incident": {
            "description": "Mobile crane performed an 8-ton vessel lift. The cordoned drop zone was established and rigid timber barricades prevented any pedestrian entry. All personnel remained safely behind segregation walkway barriers.",
            "composite_narrative": "Mobile crane performed an 8-ton vessel lift. The cordoned drop zone was established and rigid timber barricades prevented any pedestrian entry. All personnel remained safely behind segregation walkway barriers. [SEP] Rigging team confirmed zero unauthorized personnel were inside the swing radius.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.77,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "primary_hazard": "suspended_load",
            "control_state": "EFFECTIVE",
            "exposure_state": "NO_WORKER_EXPOSURE",
            "agreement_state": "MODEL_STRONGER_THAN_RULE_EVIDENCE",
            "disagreement_type": "POTENTIAL_FALSE_POSITIVE",
            "high_priority_review": True,
            "is_conflicting": False
        }
    },
    # 7. Multi-Hazard
    {
        "id": "GOLDEN-07-MULTI-HAZARD",
        "name": "Multi-Hazard: Hydrocarbon Gas Leakage with Adjacent Welding Hot Work",
        "description": "High pressure gas release at 45 bar occurred adjacent to welding habitat with hot work sparks in the immediate vicinity.",
        "incident": {
            "description": "During maintenance on a 45 bar natural gas separator line, pressurized hydrocarbon gas escaped near an ongoing structural welding habitat where positive isolation blinds were absent and continuous gas testing had not been performed. Welding sparks ignited a flash fire while technicians were standing inside the release path.",
            "composite_narrative": "During maintenance on a 45 bar natural gas separator line, pressurized hydrocarbon gas escaped near an ongoing structural welding habitat where positive isolation blinds were absent and continuous gas testing had not been performed. Welding sparks ignited a flash fire while technicians were standing inside the release path. [SEP] Emergency shut-down was manually tripped by fire watch.",
            "injury_type": "burns",
            "body_part": "face"
        },
        "prediction": {
            "psif_score": 0.88,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "min_detected_hazards": 2,
            "required_hazards": ["pressure_stored", "chemical_flammable"],
            "is_conflicting": False
        }
    },
    # 8. Contradictory Evidence
    {
        "id": "GOLDEN-08-CONTRADICTORY-EVIDENCE",
        "name": "Material Contradiction: Isolation Verified Claim vs Passing Valve Evidence",
        "description": "Narrative asserts zero energy isolation verified, but subsequently states isolation valve was passing pressurized steam into work area.",
        "incident": {
            "description": "Operator confirmed zero energy isolation verified and signed off on permit before opening line. However, during line break, the isolation valve was found passing steam at 18 bar directly into the breathing zone.",
            "composite_narrative": "Operator confirmed zero energy isolation verified and signed off on permit before opening line. However, during line break, the isolation valve was found passing steam at 18 bar directly into the breathing zone. [SEP] Supervisor questioned whether bleeder had been checked prior to permit authorization.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.62,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "CONFLICTING_EVIDENCE",
            "is_conflicting": True,
            "high_priority_review": True
        }
    },
    # 9. Pressure Insufficient
    {
        "id": "GOLDEN-09-PRESSURE-INSUFFICIENT",
        "name": "Pressure Insufficient: High Pressure Manifold Inspection Unclear Facts",
        "description": "Technician inspected 40 bar manifold valve. Report omits whether line was vented and drained.",
        "incident": {
            "description": "Technician approached 40 bar manifold to inspect valve. Unknown whether line was depressurized or isolated.",
            "composite_narrative": "Technician approached 40 bar manifold to inspect valve. Unknown whether line was depressurized or isolated. [SEP] Inspection log lacked barrier verification details.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.35,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "INSUFFICIENT_INFORMATION",
            "is_conflicting": False
        }
    },
    # 10. Working at Height PSIF
    {
        "id": "GOLDEN-10-HEIGHT-PSIF",
        "name": "Working at Height PSIF: Unguarded Edge with Detached Lanyard",
        "description": "Scaffolder on elevated scaffold at 8 meters where guardrail was missing slipped and fell from height.",
        "incident": {
            "description": "Scaffolder walked on elevated scaffold deck at 8 meters where guardrail was missing. Lanyard was unclipped and worker fell from height.",
            "composite_narrative": "Scaffolder walked on elevated scaffold deck at 8 meters where guardrail was missing. Lanyard was unclipped and worker fell from height. [SEP] Scaffolder sustained severe leg fractures upon ground impact.",
            "injury_type": "fracture",
            "body_part": "leg"
        },
        "prediction": {
            "psif_score": 0.91,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "is_conflicting": False
        }
    },
    # 11. Working at Height Controlled
    {
        "id": "GOLDEN-11-HEIGHT-CONTROLLED",
        "name": "Working at Height Controlled: Certified Anchor and Intact Guardrail",
        "description": "Scaffolder worked at 8 meters elevation with 100% tie-off and verified guardrails.",
        "incident": {
            "description": "Scaffolder worked at 8 meters elevation. Fall arrest was installed and verified with 100% tie-off. Guardrail held and worker remained behind segregation.",
            "composite_narrative": "Scaffolder worked at 8 meters elevation. Fall arrest was installed and verified with 100% tie-off. Guardrail held and worker remained behind segregation. [SEP] Task was completed safely without incident.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.15,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    },
    # 12. Working at Height Insufficient
    {
        "id": "GOLDEN-12-HEIGHT-INSUFFICIENT",
        "name": "Working at Height Insufficient: Omitted Tie-off Documentation",
        "description": "Worker stood on elevated structure at height with no record of tie-off or edge barriers.",
        "incident": {
            "description": "Worker was on scaffold structure at height. Unclear whether safety harness was used or if edge guardrails were present.",
            "composite_narrative": "Worker was on scaffold structure at height. Unclear whether safety harness was used or if edge guardrails were present. [SEP] Observer noted work at height without further barrier details.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.40,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "INSUFFICIENT_INFORMATION",
            "is_conflicting": False
        }
    },
    # 13. Suspended Load PSIF
    {
        "id": "GOLDEN-13-LIFT-PSIF",
        "name": "Suspended Load PSIF: Worker Under Load with Failed Rigging",
        "description": "Worker walked underneath 5-ton suspended steel bundle when rigging sling unseated.",
        "incident": {
            "description": "Mobile crane lifted a 5-ton steel bundle. Worker walked underneath suspended load to adjust timber dunnage. Sling unseated and worker was struck by load.",
            "composite_narrative": "Mobile crane lifted a 5-ton steel bundle. Worker walked underneath suspended load to adjust timber dunnage. Sling unseated and worker was struck by load. [SEP] Emergency medical team responded to severe crush injuries.",
            "injury_type": "crush",
            "body_part": "chest"
        },
        "prediction": {
            "psif_score": 0.95,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "is_conflicting": False
        }
    },
    # 14. Suspended Load Controlled
    {
        "id": "GOLDEN-14-LIFT-CONTROLLED",
        "name": "Suspended Load Controlled: Barricaded Drop Zone and Staged Personnel",
        "description": "Crane lifted structural beams with cordoned drop zone and spotters keeping all personnel clear.",
        "incident": {
            "description": "Mobile crane performed lift of heavy tubulars. The cordoned drop zone was established and rigid timber barricades prevented any pedestrian entry. All personnel remained safely behind segregation walkway barriers.",
            "composite_narrative": "Mobile crane performed lift of heavy tubulars. The cordoned drop zone was established and rigid timber barricades prevented any pedestrian entry. All personnel remained safely behind segregation walkway barriers. [SEP] Banksman confirmed all riggers were positioned outside lift radius.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.20,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    },
    # 15. Suspended Load Insufficient
    {
        "id": "GOLDEN-15-LIFT-INSUFFICIENT",
        "name": "Suspended Load Insufficient: Omitted Barricade Details",
        "description": "Crane lifted pipe bundle in yard with missing positioning information.",
        "incident": {
            "description": "Mobile crane lifted a pipe bundle in yard. Personnel were in area but report omits worker position and whether drop zone barricade was established.",
            "composite_narrative": "Mobile crane lifted a pipe bundle in yard. Personnel were in area but report omits worker position and whether drop zone barricade was established. [SEP] Preliminary summary submitted without rigger statements.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.42,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "INSUFFICIENT_INFORMATION",
            "is_conflicting": False
        }
    },
    # 16. Electrical PSIF
    {
        "id": "GOLDEN-16-ELECTRICAL-PSIF",
        "name": "Electrical PSIF: Live 415V Busbar Contact Without LOTO",
        "description": "Electrician reached hand into energized 415V switchgear without lockout applied.",
        "incident": {
            "description": "Electrician performed maintenance on 415V switchgear with live exposed busbars where lockout was not applied. Worker made contact with energized parts and suffered arc flash.",
            "composite_narrative": "Electrician performed maintenance on 415V switchgear with live exposed busbars where lockout was not applied. Worker made contact with energized parts and suffered arc flash. [SEP] High energy flash caused second degree burns to face and hands.",
            "injury_type": "burn",
            "body_part": "face"
        },
        "prediction": {
            "psif_score": 0.89,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "is_conflicting": False
        }
    },
    # 17. Electrical Controlled
    {
        "id": "GOLDEN-17-ELECTRICAL-CONTROLLED",
        "name": "Electrical Controlled: Breaker Racked Out and Zero Energy Verified",
        "description": "Electrician performed switchgear maintenance after zero energy verification and LOTO.",
        "incident": {
            "description": "Electrician performed maintenance on 415V switchgear after breaker was racked out. Zero energy verified and valves held absolute isolation with LOTO verified.",
            "composite_narrative": "Electrician performed maintenance on 415V switchgear after breaker was racked out. Zero energy verified and valves held absolute isolation with LOTO verified. [SEP] Two-pole voltage test confirmed zero volts across all phases.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.18,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    },
    # 18. Vehicle PSIF
    {
        "id": "GOLDEN-18-VEHICLE-PSIF",
        "name": "Vehicle PSIF: Reversing Forklift With Broken Alarm Strikes Pedestrian",
        "description": "Forklift reversing in warehouse with broken backup alarm struck pedestrian in vehicle path.",
        "incident": {
            "description": "Forklift was reversing in warehouse with broken backup alarm. Worker was struck by moving vehicle path in blind spot.",
            "composite_narrative": "Forklift was reversing in warehouse with broken backup alarm. Worker was struck by moving vehicle path in blind spot. [SEP] Heavy impact knocked pedestrian down with fractured pelvis.",
            "injury_type": "fracture",
            "body_part": "hip"
        },
        "prediction": {
            "psif_score": 0.86,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "is_conflicting": False
        }
    },
    # 19. Vehicle Controlled
    {
        "id": "GOLDEN-19-VEHICLE-CONTROLLED",
        "name": "Vehicle Controlled: Bolted Steel Barriers and Segregated Walkway",
        "description": "Forklift moved materials in yard while pedestrian remained behind segregation.",
        "incident": {
            "description": "Forklift moved materials in yard. Dedicated pedestrian walkway remained behind segregation and bolted steel barriers prevented entry.",
            "composite_narrative": "Forklift moved materials in yard. Dedicated pedestrian walkway remained behind segregation and bolted steel barriers prevented entry. [SEP] Crash bollards and interlocked gates prevented any vehicle intrusion.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.12,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    },
    # 20. Vehicle Insufficient
    {
        "id": "GOLDEN-20-VEHICLE-INSUFFICIENT",
        "name": "Vehicle Insufficient: Omitted Pedestrian Presence Information",
        "description": "Forklift moved in warehouse with unrecorded pedestrian positioning.",
        "incident": {
            "description": "Forklift was operating in warehouse. Narrative does not state if pedestrian workers were present or if barriers were established.",
            "composite_narrative": "Forklift was operating in warehouse. Narrative does not state if pedestrian workers were present or if barriers were established. [SEP] Shift turnover report noted forklift logistics.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.38,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "INSUFFICIENT_INFORMATION",
            "is_conflicting": False
        }
    },
    # 21. Hot Work PSIF
    {
        "id": "GOLDEN-21-HOTWORK-PSIF",
        "name": "Hot Work PSIF: Torch Cutting Near Open Sump With Flammable Gas",
        "description": "Welder ignited cutting torch near open drain where gas testing was absent causing flash fire.",
        "incident": {
            "description": "Welder ignited cutting torch near open drain where continuous atmospheric monitoring was absent. Flammable gas ignited flash fire and worker was burned.",
            "composite_narrative": "Welder ignited cutting torch near open drain where continuous atmospheric monitoring was absent. Flammable gas ignited flash fire and worker was burned. [SEP] Flash fire engulfed work station before operator could retreat.",
            "injury_type": "burn",
            "body_part": "arm"
        },
        "prediction": {
            "psif_score": 0.92,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "is_conflicting": False
        }
    },
    # 22. Hot Work Controlled
    {
        "id": "GOLDEN-22-HOTWORK-CONTROLLED",
        "name": "Hot Work Controlled: Positive Habitat and Fire Watch Extinguisher",
        "description": "Structural welding performed inside habitat with continuous gas testing confirming zero LEL.",
        "incident": {
            "description": "Structural welding performed inside habitat. Continuous gas testing confirmed zero LEL and fire watch with extinguisher safely contained all sparks.",
            "composite_narrative": "Structural welding performed inside habitat. Continuous gas testing confirmed zero LEL and fire watch with extinguisher safely contained all sparks. [SEP] Certified fire blankets completely shielded adjacent piping.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.16,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    },
    # 23. Hot Work Insufficient
    {
        "id": "GOLDEN-23-HOTWORK-INSUFFICIENT",
        "name": "Hot Work Insufficient: Omitted Gas Monitoring Documentation",
        "description": "Hot work welding performed on pipe support without recorded gas test.",
        "incident": {
            "description": "Hot work welding performed on pipe support. Narrative omits gas testing and barrier status.",
            "composite_narrative": "Hot work welding performed on pipe support. Narrative omits gas testing and barrier status. [SEP] Daily work log noted maintenance welding.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.44,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "INSUFFICIENT_INFORMATION",
            "is_conflicting": False
        }
    },
    # 24. Confined Space PSIF
    {
        "id": "GOLDEN-24-CONFINED-PSIF",
        "name": "Confined Space PSIF: Tank Entry Without Atmospheric Monitoring",
        "description": "Contractor entered storage tank without permit or atmospheric monitoring and collapsed.",
        "incident": {
            "description": "Contractor entered storage tank without obtaining permit and without atmospheric monitoring. Entrant collapsed from toxic gas inside vessel.",
            "composite_narrative": "Contractor entered storage tank without obtaining permit and without atmospheric monitoring. Entrant collapsed from toxic gas inside vessel. [SEP] Emergency extraction team deployed with breathing apparatus.",
            "injury_type": "asphyxiation",
            "body_part": "respiratory"
        },
        "prediction": {
            "psif_score": 0.96,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "is_conflicting": False
        }
    },
    # 25. Confined Space Controlled
    {
        "id": "GOLDEN-25-CONFINED-CONTROLLED",
        "name": "Confined Space Controlled: Blinds Installed and Continuous Gas Test",
        "description": "Technician entered confined space vessel after mechanical blinds and verified gas test.",
        "incident": {
            "description": "Technician entered confined space vessel after positive mechanical blinds installed. Continuous gas testing confirmed normal oxygen and isolation held.",
            "composite_narrative": "Technician entered confined space vessel after positive mechanical blinds installed. Continuous gas testing confirmed normal oxygen and isolation held. [SEP] Trained hole watch remained stationed at manway with retrieval winch.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.25,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    },
    # 26. Confined Space Insufficient
    {
        "id": "GOLDEN-26-CONFINED-INSUFFICIENT",
        "name": "Confined Space Insufficient: Unclear Bodily Entry",
        "description": "Worker was near tank manway opening without clear record of entry or gas test.",
        "incident": {
            "description": "Worker was near tank manway opening. Unclear whether entry occurred or if atmospheric test was completed.",
            "composite_narrative": "Worker was near tank manway opening. Unclear whether entry occurred or if atmospheric test was completed. [SEP] Field supervisor requested formal investigation.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.48,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "INSUFFICIENT_INFORMATION",
            "internal_reasoning_state": "INSUFFICIENT_INFORMATION",
            "is_conflicting": False
        }
    },
    # 27. IOGP Mention Without Violation
    {
        "id": "GOLDEN-27-IOGP-NO-VIOLATION",
        "name": "IOGP Mention Without Violation: LSR Discussed and Fully Followed",
        "description": "IOGP life saving rule referenced in permit with all controls effectively verified.",
        "incident": {
            "description": "Work at height permit reviewed per IOGP Life-Saving Rules. Scaffolder wore full body harness and was 100% tied off. Guardrail held and worker remained behind segregation.",
            "composite_narrative": "Work at height permit reviewed per IOGP Life-Saving Rules. Scaffolder wore full body harness and was 100% tied off. Guardrail held and worker remained behind segregation. [SEP] Safety audit confirmed full procedural adherence.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.10,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    },
    # 28. Corrective Action Leakage Quarantine
    {
        "id": "GOLDEN-28-ACTION-LEAKAGE",
        "name": "Corrective Action Leakage: Post-Incident Recommendation Quarantined",
        "description": "Coupling guard was bolted during run; corrective action recommendation does not taint event.",
        "incident": {
            "description": "Mechanic stood behind designated safety barrier while coupling guard was securely bolted and held during pump operation. [SEP] Corrective action: Recommend replacing guard during next shutdown.",
            "composite_narrative": "Mechanic stood behind designated safety barrier while coupling guard was securely bolted and held during pump operation. [SEP] Corrective action: Recommend replacing guard during next shutdown.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.15,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    },
    # 29. Planned Action Quarantine
    {
        "id": "GOLDEN-29-PLANNED-ACTION",
        "name": "Planned Action Quarantine: Future Promise Does Not Mask Present Failure",
        "description": "Drive belt was running unguarded while technician was exposed; future plan does not mask failure.",
        "incident": {
            "description": "Machine drive belt was running unguarded while technician reached into nip point. Maintenance team plans to install an interlocked guard next week.",
            "composite_narrative": "Machine drive belt was running unguarded while technician reached into nip point. Maintenance team plans to install an interlocked guard next week. [SEP] Worker sustained laceration to right hand.",
            "injury_type": "laceration",
            "body_part": "hand"
        },
        "prediction": {
            "psif_score": 0.87,
            "psif_predicted": True,
            "binary_classification": "PSIF"
        },
        "expected": {
            "decision": "PSIF",
            "internal_reasoning_state": "PSIF_PATHWAY_OPEN",
            "is_conflicting": False
        }
    },
    # 30. Temporal Restoration Before Exposure
    {
        "id": "GOLDEN-30-TEMPORAL-RESTORATION",
        "name": "Temporal Restoration: Barrier Restored Prior to Exposure",
        "description": "Work halted when barrier was noticed defective, and restored before worker entered area.",
        "incident": {
            "description": "Scaffolding work at height was halted when lanyard defect was noticed. Lanyard was restored before exposure and worker remained behind segregation.",
            "composite_narrative": "Scaffolding work at height was halted when lanyard defect was noticed. Lanyard was restored before exposure and worker remained behind segregation. [SEP] Defective lanyard was tagged out of service.",
            "injury_type": "none",
            "body_part": "none"
        },
        "prediction": {
            "psif_score": 0.19,
            "psif_predicted": False,
            "binary_classification": "NOT PSIF"
        },
        "expected": {
            "decision": "NOT_PSIF",
            "internal_reasoning_state": "HIGH_ENERGY_CONTROLLED",
            "is_conflicting": False
        }
    }
]

def validate_and_save():
    print(f"Validating {len(FIXTURES)} golden reasoning fixtures...")
    failures = []
    
    for fix in FIXTURES:
        fix_id = fix["id"]
        inc_data = fix["incident"]
        pred_data = fix.get("prediction")
        expected = fix["expected"]

        incident = Incident(
            description=inc_data["description"],
            composite_narrative=inc_data.get("composite_narrative", inc_data["description"]),
            injury_type=inc_data.get("injury_type", "none"),
            body_part=inc_data.get("body_part", "none"),
        )

        prediction = None
        if pred_data:
            prediction = PredictionResult(
                psif_probability=pred_data["psif_score"],
                psif_predicted=pred_data["psif_predicted"],
            )

        assessment = build_incident_reasoning_assessment(incident, prediction=prediction)

        # Check decision
        if assessment["decision"] != expected["decision"]:
            failures.append(f"[{fix_id}] Decision mismatch: got {assessment['decision']}, exp {expected['decision']}")
            continue

        # Check internal state
        if "internal_reasoning_state" in expected:
            if assessment["internal_reasoning_state"] != expected["internal_reasoning_state"]:
                failures.append(f"[{fix_id}] State mismatch: got {assessment['internal_reasoning_state']}, exp {expected['internal_reasoning_state']}")
                continue

        # Check is_conflicting
        if "is_conflicting" in expected:
            is_conf = (assessment["internal_reasoning_state"] == InternalReasoningState.CONFLICTING_EVIDENCE)
            if is_conf != expected["is_conflicting"]:
                failures.append(f"[{fix_id}] is_conflicting mismatch: got {is_conf}, exp {expected['is_conflicting']}")
                continue

        print(f"  ✓ {fix_id:36s} -> {assessment['internal_reasoning_state']:25s} | {assessment['decision']}")

    if failures:
        print("\nERRORS DETECTED:")
        for f in failures:
            print("  ✕", f)
        sys.exit(1)

    print(f"\nAll {len(FIXTURES)} fixtures validated successfully!")
    out_file = Path("tests/fixtures/golden_reasoning_traces.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "version": "2.0",
            "description": "Comprehensive Deterministic Golden Reasoning Traces for PSIF Assurance (Task 5 Frozen)",
            "total_fixtures": len(FIXTURES),
            "fixtures": FIXTURES,
        }, f, indent=2)
    print(f"Written to {out_file}")

if __name__ == "__main__":
    validate_and_save()
