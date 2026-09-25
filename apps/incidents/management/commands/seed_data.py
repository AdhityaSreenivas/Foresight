"""
PSIF Platform — seed_data management command

Generates ~750 synthetic workplace incident records for training the PSIF
prediction model.  This data is SYNTHETIC DEMONSTRATION DATA — it is NOT
real OIL (Occupational Injury/Loss) data and must not be treated as such.

Target class distribution:
    ~20% PSIF-positive  (severity_potential ∈ {serious,fatality}
                         AND severity_actual ∈ {none,first_aid,medical_treatment})
    ~80% PSIF-negative  (all other combinations)

Design notes:
    - Narratives are generated from domain-specific templates with Faker variation.
      They do NOT contain phrases like "potentially fatal" or "could have been a
      fatality" that would trivially leak the target label into text.
    - Severity fields follow the heuristic rule, but narratives describe the
      scenario without referencing the PSIF classification directly.
    - Multiple departments, locations, equipment, injury types, and root causes
      ensure the classification problem is not trivially separable.
"""
import random
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

from apps.incidents.models import Incident
from ml_engine.text_preprocessing import build_composite_narrative

logger = logging.getLogger(__name__)
fake = Faker()
Faker.seed(42)
random.seed(42)

# ── Domain vocabularies ──────────────────────────────────────────────────────

DEPARTMENTS = [
    "Maintenance", "Fabrication", "Chemical Processing", "Logistics",
    "Assembly", "Utilities", "Quality Control", "Packaging",
    "Electrical", "Construction", "Painting", "Welding",
]

LOCATIONS = [
    "Bay 1", "Bay 2", "Bay 3", "Bay 4", "Bay 5",
    "Warehouse Aisle 3", "Warehouse Aisle 7", "Warehouse Aisle 12",
    "Unit 1 Reactor", "Unit 2 Reactor", "Unit 3 Reactor",
    "Welding Station 1", "Welding Station 2",
    "Loading Dock A", "Loading Dock B",
    "Roof Level", "Basement Pump Room", "Control Room",
    "Parking Area", "Line 1 Packaging", "Line 2 Assembly",
    "Tank Farm", "Pipe Rack North", "Pipe Rack South",
    "Compressor House", "Electrical Substation",
]

JOB_TASKS = [
    "Crane rigging", "Grinding pipe welds", "Valve maintenance",
    "Forklift transit", "Carton stacking", "Pipe fitting",
    "Scaffold erection", "Confined space entry", "Hot work",
    "Electrical panel maintenance", "Tank cleaning",
    "Chemical transfer", "Machine setup", "Manual material handling",
    "Conveyor maintenance", "Roof repair", "Cable pulling",
    "Equipment inspection", "Pump alignment", "Filter replacement",
    "Painting operations", "Quality sampling", "Tool changeover",
]

EQUIPMENT = [
    "Overhead Crane 5T", "Angle Grinder", "Acid Transfer Line",
    "Forklift FL-09", "Pallet Jack", "Scaffold Tower",
    "Pneumatic Drill", "Band Saw", "Lathe CNC-04",
    "Welding Machine MIG-200", "Hydraulic Press HP-100",
    "Compressed Air Line", "Chemical Pump CP-12",
    "Conveyor Belt CB-3", "Electrical Panel EP-7",
    "Boom Lift BL-40", "Chain Hoist CH-2T",
    "Portable Generator PG-5", "Pressure Washer PW-3000",
    "Hand Truck", "Step Ladder 8ft", "Extension Ladder 24ft",
    "Circular Saw CS-10", "Bench Grinder BG-6",
]

INJURY_TYPES = [
    "Laceration", "Sprain/Strain", "Contusion/Bruise",
    "Chemical Burn", "Thermal Burn", "Fracture",
    "Abrasion", "Puncture", "Amputation",
    "Electric Shock", "Inhalation", "Eye Injury",
    "Hearing Loss", "Crush Injury", "None",
]

BODY_PARTS = [
    "Left Hand", "Right Hand", "Left Forearm", "Right Forearm",
    "Left Foot", "Right Foot", "Left Eye", "Right Eye",
    "Head", "Lower Back", "Upper Back", "Left Shoulder",
    "Right Shoulder", "Left Knee", "Right Knee", "Chest",
    "Abdomen", "Left Leg", "Right Leg", "Neck", "None",
]

IMMEDIATE_CAUSES = [
    "Defective wire sling", "Slipped while holding workpiece",
    "Gasket failure under pressure", "Excess speed around blind corner",
    "Lifting heavy object with poor posture", "Inadequate lockout/tagout",
    "Improper PPE usage", "Failure to follow procedure",
    "Poor housekeeping", "Obstructed view", "Fatigue",
    "Distraction", "Equipment malfunction", "Improper tool for task",
    "Wet/slippery surface", "Unsecured load", "Pinch point exposure",
    "Electrical fault", "Pressure release failure",
    "Tripping hazard", "Falling object", "Chemical splash",
]

ROOT_CAUSE_CATEGORIES = [
    "Equipment Failure", "Inadequate Guarding", "Inadequate Maintenance",
    "Unsafe Behavior", "Ergonomic", "Training Deficiency",
    "Procedure Violation", "Design Deficiency", "Management System",
    "Communication Failure", "Supervision Gap", "PPE Failure",
]

# ── Narrative templates ──────────────────────────────────────────────────────
# These templates describe scenarios WITHOUT revealing the PSIF classification.
# A "near miss" narrative does not say "potentially fatal" — it describes what
# happened factually.

_NEAR_MISS_DESCRIPTIONS = [
    "During {task} in {location}, a {equipment} component detached unexpectedly. "
    "The component struck the guardrail {distance} from the nearest worker. "
    "No injuries were sustained.",

    "While performing {task}, an operator noticed {equipment} making unusual sounds. "
    "Investigation revealed a cracked mounting bracket. Operations were halted and "
    "the area was cleared before any failure occurred.",

    "A {equipment} load shifted during {task} in {location}. The load swung and "
    "contacted a structural beam. Workers in the area evacuated immediately. "
    "No personnel were struck.",

    "During routine {task}, a pressure gauge on {equipment} indicated abnormal "
    "readings. The operator initiated emergency shutdown. Subsequent inspection "
    "found a corroded fitting that was near failure point.",

    "An unsecured {equipment} rolled toward the work area during {task}. "
    "A nearby worker stepped clear. The equipment stopped against a barrier. "
    "No injuries resulted.",

    "While {task} was underway in {location}, a section of temporary scaffolding "
    "partially collapsed. All workers had already descended for a break. "
    "No one was in the affected area.",

    "A chemical line connected to {equipment} developed a small leak during {task}. "
    "The area was evacuated and the line was isolated. Air monitoring confirmed "
    "no harmful exposure levels were reached.",

    "During {task} operations, a tool fell from {distance} above the work area. "
    "The tool landed in the exclusion zone. No workers were present below.",
]

_MINOR_INJURY_DESCRIPTIONS = [
    "While performing {task} in {location}, the operator sustained a minor "
    "{injury_type} to the {body_part}. First aid was administered on site. "
    "The worker returned to duties the same shift.",

    "During {task}, a worker experienced a small {injury_type} on their {body_part} "
    "when contact was made with {equipment}. The injury was treated with standard "
    "first aid supplies.",

    "An employee working on {task} reported discomfort in the {body_part} area. "
    "Assessment showed a minor {injury_type}. Ice and rest were prescribed. "
    "No time was lost.",

    "While operating {equipment} during {task}, the worker received a superficial "
    "{injury_type} to the {body_part}. The wound was cleaned and bandaged. "
    "Work continued after treatment.",
]

_MEDICAL_TREATMENT_DESCRIPTIONS = [
    "During {task} in {location}, an employee sustained a {injury_type} to the "
    "{body_part} requiring medical evaluation. The physician prescribed "
    "treatment and {days} days of modified duty.",

    "While performing {task} with {equipment}, a worker experienced a {injury_type} "
    "to the {body_part}. Emergency medical services transported the employee to "
    "the clinic for treatment.",

    "An incident during {task} resulted in a {injury_type} affecting the worker's "
    "{body_part}. Medical treatment was required, including prescription medication "
    "and {days} follow-up visits.",
]

_CORRECTIVE_ACTIONS = [
    "Replaced {equipment} component. Added daily inspection checklist.",
    "Installed additional guarding on {equipment}. Updated SOP for {task}.",
    "Conducted refresher training for all {department} personnel.",
    "Implemented engineering control: {improvement}.",
    "Revised risk assessment for {task}. Updated permit-to-work requirements.",
    "Added warning signage and floor markings in {location}.",
    "Procured improved PPE for {task} activities. Updated PPE matrix.",
    "Installed physical barrier around {equipment} work zone.",
    "Scheduled preventive maintenance overhaul for {equipment}.",
    "Added buddy system requirement for {task} in {location}.",
]

_IMPROVEMENTS = [
    "mechanical interlock on access door",
    "automated shut-off valve",
    "load-limiting device",
    "anti-slip coating on work platform",
    "remote monitoring system",
    "ergonomic workstation redesign",
    "ventilation extraction system",
    "secondary containment bund",
]

_WITNESS_STATEMENTS = [
    "I was working nearby and heard a loud noise. I looked over and saw the aftermath. "
    "The area was cleared quickly.",
    "I observed the worker performing the task when the incident occurred. Everything "
    "happened very fast.",
    "I was in the adjacent bay and came over when I heard shouting. The supervisor had "
    "already called for assistance.",
    "I noticed something was wrong when I heard an unusual sound from the equipment. "
    "I immediately notified the shift supervisor.",
    "",  # Some incidents have no witness statement
    "",
]


def _generate_incident(
    *,
    severity_actual: str,
    severity_potential: str,
    near_miss: bool,
    incident_number: int,
) -> dict:
    """Generate a single synthetic incident record."""
    department = random.choice(DEPARTMENTS)
    location = random.choice(LOCATIONS)
    task = random.choice(JOB_TASKS)
    equipment = random.choice(EQUIPMENT)
    injury_type = random.choice(INJURY_TYPES)
    body_part = random.choice(BODY_PARTS)

    # Near-miss incidents typically have no injury
    if near_miss or severity_actual == "none":
        injury_type = "None"
        body_part = "None"

    immediate_cause = random.choice(IMMEDIATE_CAUSES)
    root_cause = random.choice(ROOT_CAUSE_CATEGORIES)

    # Select narrative template based on severity
    context = {
        "task": task,
        "location": location,
        "equipment": equipment,
        "injury_type": injury_type.lower(),
        "body_part": body_part.lower(),
        "department": department,
        "distance": f"{random.randint(1, 10)} feet",
        "days": random.randint(2, 14),
        "improvement": random.choice(_IMPROVEMENTS),
    }

    if severity_actual == "none":
        template = random.choice(_NEAR_MISS_DESCRIPTIONS)
    elif severity_actual == "first_aid":
        template = random.choice(_MINOR_INJURY_DESCRIPTIONS)
    elif severity_actual == "medical_treatment":
        template = random.choice(_MEDICAL_TREATMENT_DESCRIPTIONS)
    else:
        template = random.choice(_MINOR_INJURY_DESCRIPTIONS)

    description = template.format(**context)
    corrective_action_tpl = random.choice(_CORRECTIVE_ACTIONS)
    corrective_actions = corrective_action_tpl.format(**context)

    witness = random.choice(_WITNESS_STATEMENTS)

    # Random date within last 2 years
    days_ago = random.randint(1, 730)
    incident_date = (timezone.now() - timedelta(days=days_ago)).date()

    return {
        "external_id": f"SEED-{incident_number:04d}",
        "incident_date": incident_date,
        "department": department,
        "location": location,
        "job_task": task,
        "equipment_involved": equipment,
        "injury_type": injury_type,
        "body_part": body_part,
        "immediate_cause": immediate_cause,
        "root_cause_category": root_cause,
        "severity_actual": severity_actual,
        "severity_potential": severity_potential,
        "near_miss": near_miss,
        "description": description,
        "corrective_actions": corrective_actions,
        "witness_statement": witness if witness else None,
    }


class Command(BaseCommand):
    help = (
        "Generate ~750 synthetic workplace incidents for PSIF model training. "
        "This is SYNTHETIC DEMONSTRATION DATA — NOT real OIL data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", type=int, default=750,
            help="Number of incidents to generate (default: 750).",
        )
        parser.add_argument(
            "--clear", action="store_true",
            help="Delete all existing seed incidents (external_id starting with SEED-) before generating.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        clear = options["clear"]

        if clear:
            deleted, _ = Incident.objects.filter(external_id__startswith="SEED-").delete()
            self.stdout.write(f"Deleted {deleted} existing seed incidents.")

        # ── Class distribution ────────────────────────────────────────────────
        # ~20% PSIF-positive, ~80% PSIF-negative
        n_positive = int(count * 0.20)
        n_negative = count - n_positive

        incidents_data = []
        incident_num = 1

        # ── Generate PSIF-POSITIVE incidents ──────────────────────────────────
        for _ in range(n_positive):
            sev_pot = random.choice(["serious", "fatality"])
            sev_act = random.choice(["none", "first_aid", "medical_treatment"])
            near_miss = sev_act == "none"

            data = _generate_incident(
                severity_actual=sev_act,
                severity_potential=sev_pot,
                near_miss=near_miss,
                incident_number=incident_num,
            )
            data["sif_label"] = 1
            incidents_data.append(data)
            incident_num += 1

        # ── Generate PSIF-NEGATIVE incidents ──────────────────────────────────
        negative_combos = [
            # Low/moderate potential — any actual
            ("low", "none", True),
            ("low", "first_aid", False),
            ("low", "medical_treatment", False),
            ("moderate", "none", True),
            ("moderate", "first_aid", False),
            ("moderate", "medical_treatment", False),
            # High potential but high actual (not PSIF by definition)
            ("serious", "lost_time", False),
            ("serious", "fatality", False),
            ("fatality", "lost_time", False),
            ("fatality", "fatality", False),
            # Low potential, lost time / fatality
            ("low", "lost_time", False),
            ("moderate", "lost_time", False),
        ]

        for i in range(n_negative):
            combo = negative_combos[i % len(negative_combos)]
            sev_pot, sev_act, near_miss = combo

            data = _generate_incident(
                severity_actual=sev_act,
                severity_potential=sev_pot,
                near_miss=near_miss,
                incident_number=incident_num,
            )
            data["sif_label"] = 0
            incidents_data.append(data)
            incident_num += 1

        # ── Shuffle to avoid ordered blocks ───────────────────────────────────
        random.shuffle(incidents_data)

        # ── Create Incident objects ───────────────────────────────────────────
        incident_objs = []
        for data in incidents_data:
            composite = build_composite_narrative(
                description=data["description"],
                corrective_actions=data["corrective_actions"],
                witness_statement=data.get("witness_statement"),
            )
            incident = Incident(
                external_id=data["external_id"],
                incident_date=data["incident_date"],
                department=data["department"],
                location=data["location"],
                job_task=data["job_task"],
                equipment_involved=data["equipment_involved"],
                injury_type=data["injury_type"],
                body_part=data["body_part"],
                immediate_cause=data["immediate_cause"],
                root_cause_category=data["root_cause_category"],
                severity_actual=data["severity_actual"],
                severity_potential=data["severity_potential"],
                near_miss=data["near_miss"],
                description=data["description"],
                corrective_actions=data["corrective_actions"],
                witness_statement=data.get("witness_statement"),
                composite_narrative=composite,
                is_synthetic=True,
                psif_label_source=Incident.PsifLabelSource.SYNTHETIC,
                raw_row={
                    "external_id": data["external_id"],
                    "sif_label": data.get("sif_label", 0),
                    "synthetic": True,
                },
            )
            incident_objs.append(incident)

        Incident.objects.bulk_create(incident_objs, batch_size=200)

        # ── Summary ───────────────────────────────────────────────────────────
        total = len(incident_objs)
        pos = sum(1 for inc in incident_objs if (inc.raw_row or {}).get("sif_label") == 1)
        neg = sum(1 for inc in incident_objs if (inc.raw_row or {}).get("sif_label") == 0)

        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*60}\n"
            f"SYNTHETIC SEED DATA GENERATED\n"
            f"{'='*60}\n"
            f"Total incidents:    {total}\n"
            f"PSIF positive:      {pos} ({pos/total*100:.1f}%)\n"
            f"PSIF negative:      {neg} ({neg/total*100:.1f}%)\n"
            f"Class ratio (neg/pos): {neg/pos:.2f}\n"
            f"\n"
            f"WARNING: This is SYNTHETIC DEMONSTRATION DATA.\n"
            f"It is NOT real OIL data and must not be treated as such.\n"
            f"{'='*60}\n"
        ))
