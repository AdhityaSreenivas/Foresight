"""
PSIF Platform — Comprehensive Admin Flow Activity Intelligence Test Suite.
tests/test_admin_flow_activity_intelligence.py

Verifies:
1. Semantic Separation of Analytical Dimensions:
   - ACTIVITY != IOGP RULE
   - ACTIVITY != BARRIER / CONTROL
   - ACTIVITY != HAZARD / ENERGY
   - ACTIVITY != LOCATION
   - ACTIVITY != PSIF CLASSIFICATION
2. Golden Fixtures (Prompt Sections 40, 41, 42):
   - Painting (30), Cleaning (20), Digging / Excavation (40), Laboratory / Research (10), Vehicle / Parking Operations (50)
   - Ranked strictly by incident frequency, NOT PSIF count and NOT IOGP rule.
   - Independent IOGP association.
   - Independent barrier association.
3. Negative Tests (Prompt Section 43):
   - IOGP Hot Work != Activity Hot Work
   - Barrier Safety Harness != Activity Working at Height
   - Hazard Pressure != Activity Energy Isolation
4. Full Pipeline Test (Prompt Section 44):
   - Narrative -> Activity -> Location -> Barrier -> IOGP -> PSIF
5. Temporal & Grammar Parsing (Prompt Sections 8, 9):
   - "After completing welding, workers began cleaning." -> Cleaning, not Welding.
   - "Pump maintenance" -> Activity = Equipment Maintenance, not Pump.
6. Cross-Dimensional Matrix & API Tests (Prompt Sections 21, 33).
"""

import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.activity_engine import (
    normalize_admin_flow_activity,
    extract_activity_from_narrative,
    ActivityCategory,
    ACTIVITY_DISPLAY_NAMES,
)
from apps.admin_flow.activity_service import (
    ActivityPatternService,
    invalidate_admin_flow_activity_cache,
)
from apps.admin_flow.pattern_engine import (
    ADMIN_FLOW_WORKSPACE,
    invalidate_admin_flow_pattern_cache,
)

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        email="admin_flow_verifier@foresight.app",
        defaults={
            "username": "admin_flow_verifier@foresight.app",
            "role": "admin_flow",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def active_model(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_activity_intelligence_test",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.mark.django_db
class TestAdminFlowActivityIntelligence:
    """Core test suite for Admin Flow Activity Intelligence Rebuild."""

    def test_golden_frequency_ranking_fixture(self, client, admin_flow_user, active_model):
        """
        Prompt Section 40:
        Controlled fixture:
        Vehicle / Parking Operations = 50 (10 PSIF)
        Digging / Excavation = 40 (15 PSIF)
        Painting = 30 (8 PSIF)
        Cleaning = 20 (2 PSIF)
        Laboratory / Research = 10 (1 PSIF)
        Total = 150 incidents.

        Verifies:
        - Ranking follows total incident frequency (Vehicle 50 -> Digging 40 -> Painting 30 -> Cleaning 20 -> Lab 10).
        - NOT ranked by PSIF count (Digging has 15 PSIF, but ranks #2 behind Vehicle with 10 PSIF).
        - Explicit denominator formulas.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()
        invalidate_admin_flow_activity_cache()

        distribution = [
            ("Vehicle / Parking Operations", "Vehicle movement and transit in the yard", 50, 10),
            ("Digging / Excavation", "An excavator was used to dig a trench", 40, 15),
            ("Painting & Surface Coating", "Workers were painting equipment in the process area", 30, 8),
            ("Cleaning & Housekeeping", "Workers cleaned the workshop floor and removed oil", 20, 2),
            ("Laboratory / Research", "A researcher cleaned glassware in the laboratory", 10, 1),
        ]

        for act_name, narrative, total_count, psif_count in distribution:
            for i in range(total_count):
                is_psif = (i < psif_count)
                inc = Incident.objects.create(
                    workspace_id=ADMIN_FLOW_WORKSPACE,
                    job_task=act_name,
                    description=f"{narrative} observation #{i}",
                    location="Process Area / Refining Unit",
                    incident_date="2026-04-10",
                )
                PredictionResult.objects.create(
                    incident=inc,
                    model_version=active_model,
                    psif_probability=0.85 if is_psif else 0.15,
                    psif_predicted=is_psif,
                    risk_level="HIGH" if is_psif else "LOW",
                )

        data = ActivityPatternService.get_activity_pattern_view_data()

        assert data["total_filtered_incidents"] == 150
        assert len(data["activities"]) == 5

        # Ranking must follow incident volume:
        acts = data["activities"]
        assert acts[0]["activity"] == "Vehicle / Parking Operations"
        assert acts[0]["rank"] == 1
        assert acts[0]["incident_count"] == 50
        assert acts[0]["psif_linked_count"] == 10
        assert acts[0]["dataset_share"] == round((50 / 150) * 100, 1)  # 33.3%

        assert acts[1]["activity"] == "Digging / Excavation"
        assert acts[1]["rank"] == 2
        assert acts[1]["incident_count"] == 40
        assert acts[1]["psif_linked_count"] == 15

        assert acts[2]["activity"] == "Painting & Surface Coating"
        assert acts[2]["rank"] == 3
        assert acts[2]["incident_count"] == 30
        assert acts[2]["psif_linked_count"] == 8

        assert acts[3]["activity"] == "Cleaning & Housekeeping"
        assert acts[3]["rank"] == 4
        assert acts[3]["incident_count"] == 20
        assert acts[3]["psif_linked_count"] == 2

        assert acts[4]["activity"] == "Laboratory / Research"
        assert acts[4]["rank"] == 5
        assert acts[4]["incident_count"] == 10
        assert acts[4]["psif_linked_count"] == 1

        # Top Activity callout
        assert data["top_activity"]["activity"] == "Vehicle / Parking Operations"
        assert data["top_activity"]["incident_count"] == 50
        assert data["top_activity"]["callout_caption"] == "Most frequently observed activity in the current Admin Flow dataset."

    def test_iogp_association_independence_fixture(self, active_model):
        """
        Prompt Section 41:
        Painting: IOGP = Hot Work
        Cleaning: IOGP = Work Authorization
        Digging: IOGP = Work Authorization
        Vehicle: IOGP = Driving

        The Activity chart must STILL rank:
        Vehicle -> Digging -> Painting -> Cleaning
        based strictly on activity counts, NOT grouping by IOGP rule.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()
        invalidate_admin_flow_activity_cache()

        matrix = [
            ("Vehicle / Parking Operations", "Driving", 40),
            ("Digging / Excavation", "Work Authorization", 30),
            ("Painting & Surface Coating", "Hot Work", 20),
            ("Cleaning & Housekeeping", "Work Authorization", 10),
        ]

        for act_name, iogp_rule, count in matrix:
            for i in range(count):
                inc = Incident.objects.create(
                    workspace_id=ADMIN_FLOW_WORKSPACE,
                    job_task=act_name,
                    description=f"{act_name} task with associated rule {iogp_rule} #{i}",
                    location="Workshop / Maintenance Bay",
                )
                IOGPRuleTag.objects.create(
                    incident=inc,
                    rule=iogp_rule,
                    classifier_version="v_test",
                )

        data = ActivityPatternService.get_activity_pattern_view_data()
        acts = data["activities"]

        assert len(acts) == 4
        assert acts[0]["activity"] == "Vehicle / Parking Operations"
        assert acts[0]["top_iogp_rule"] == "Driving"

        assert acts[1]["activity"] == "Digging / Excavation"
        assert acts[1]["top_iogp_rule"] == "Work Authorization"

        assert acts[2]["activity"] == "Painting & Surface Coating"
        assert acts[2]["top_iogp_rule"] == "Hot Work"

        assert acts[3]["activity"] == "Cleaning & Housekeeping"
        assert acts[3]["top_iogp_rule"] == "Work Authorization"

    def test_barrier_association_independence_fixture(self, active_model):
        """
        Prompt Section 42:
        Painting -> Gas Detector
        Digging -> Trench Shoring
        Vehicle -> Seat Belt
        Window Cleaning -> Safety Harness

        Activities must remain:
        Painting, Digging, Vehicle, Window Cleaning (Elevated Work).
        NOT grouped by barrier names!
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()
        invalidate_admin_flow_activity_cache()

        samples = [
            ("Painting & Surface Coating", "Gas detector monitored atmosphere while workers were painting piping.", 10),
            ("Digging / Excavation", "Trench shoring was installed before workers entered the trench excavation.", 8),
            ("Vehicle / Parking Operations", "Driver fastened seat belt before vehicle movement in the yard.", 6),
            ("Work at Height / Scaffolding", "Safety harness was connected during window cleaning at height on scaffolding.", 4),
        ]

        for act_name, narrative, count in samples:
            for i in range(count):
                Incident.objects.create(
                    workspace_id=ADMIN_FLOW_WORKSPACE,
                    job_task=act_name,
                    description=f"{narrative} instance {i}",
                    location="Pipe Rack / Manifold",
                )

        data = ActivityPatternService.get_activity_pattern_view_data()
        acts = data["activities"]

        # Ensure primary activities are work activities, not barrier names
        act_names = [a["activity"] for a in acts]
        assert "Painting & Surface Coating" in act_names
        assert "Digging / Excavation" in act_names
        assert "Vehicle / Parking Operations" in act_names
        assert "Work at Height / Scaffolding" in act_names

        for name in act_names:
            assert "Gas Detector" not in name
            assert "Trench Shoring" not in name
            assert "Seat Belt" not in name
            assert "Safety Harness" not in name

    def test_negative_anti_contamination_rules(self):
        """
        Prompt Section 43:
        Negative Tests:
        - IOGP = Hot Work must NOT automatically produce Activity = Hot Work
        - Barrier = Safety Harness must NOT produce Activity = Working at Height
        - Hazard = Pressure must NOT produce Activity = Energy Isolation
        """
        # 1. Hot Work given as raw_value with painting narrative
        disp, cat, method = normalize_admin_flow_activity(
            raw_value="Hot Work",
            narrative="Workers were painting equipment in the process area."
        )
        assert cat == ActivityCategory.PAINTING
        assert disp == "Painting & Surface Coating"
        assert disp != "Hot Work"

        # 2. Safety Harness given as raw_value
        disp2, cat2, method2 = normalize_admin_flow_activity(
            raw_value="Safety Harness",
            narrative="Workers were cleaning the compressor floor and removing oil."
        )
        assert cat2 == ActivityCategory.CLEANING
        assert disp2 == "Cleaning & Housekeeping"
        assert disp2 != "Working at Height"
        assert disp2 != "Safety Harness"

        # 3. Pressure given as raw_value
        disp3, cat3, method3 = normalize_admin_flow_activity(
            raw_value="Stored Pressure",
            narrative="An excavator was used to dig a trench for drainage."
        )
        assert cat3 == ActivityCategory.DIGGING_EXCAVATION
        assert disp3 == "Digging / Excavation"
        assert disp3 != "Energy Isolation"

    def test_temporal_event_activity_parsing(self):
        """
        Prompt Section 9 & 10:
        'After completing welding, workers began cleaning.'
        Event time activity is Cleaning, NOT Welding.
        """
        narrative = "After completing welding, workers began cleaning the workshop floor."
        cat, method = extract_activity_from_narrative(narrative)
        assert cat == ActivityCategory.CLEANING

        disp, cat_norm, _ = normalize_admin_flow_activity(raw_value=None, narrative=narrative)
        assert cat_norm == ActivityCategory.CLEANING
        assert disp == "Cleaning & Housekeeping"

    def test_equipment_vs_activity_separation(self):
        """
        Prompt Section 8:
        'pump maintenance'
        Activity: Equipment Maintenance
        Equipment: Pump (not the activity itself)
        """
        disp, cat, _ = normalize_admin_flow_activity(
            raw_value="pump maintenance",
            narrative="During pump maintenance in the refinery, technicians replaced seals."
        )
        assert cat == ActivityCategory.EQUIPMENT_MAINTENANCE
        assert disp == "Equipment Maintenance & Servicing"
        assert disp != "Pump"

    def test_full_pipeline_multi_dimensional_separation(self, client, admin_flow_user, active_model):
        """
        Prompt Section 44:
        For one incident verify:
        Raw narrative -> Activity extraction -> Activity normalization -> Location -> Barrier -> IOGP -> PSIF
        Then confirm each remains in its independent dimension.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()
        invalidate_admin_flow_activity_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task=None,  # Missing structured task; must extract from narrative
            description="During painting, a gas detector was active while workers operated in the process area.",
            location="Process Area / Refining Unit",
            incident_date="2026-05-15",
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Hot Work",
            classifier_version="v1",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.80,
            psif_predicted=True,
            risk_level="HIGH",
        )

        data = ActivityPatternService.get_activity_pattern_view_data()

        assert data["total_filtered_incidents"] == 1
        act = data["activities"][0]

        # 1. Activity is Painting
        assert act["activity"] == "Painting & Surface Coating"
        # 2. Location is Process Area
        assert act["top_location"] == "Process Area / Refining Unit"
        # 3. Barrier is Gas Detection
        assert "Gas Detection" in act["top_barrier"]
        # 4. Associated IOGP rule is Hot Work
        assert act["top_iogp_rule"] == "Hot Work"
        # 5. PSIF is True
        assert act["psif_linked_count"] == 1

    def test_activity_patterns_api_contract(self, client, admin_flow_user, active_model):
        """
        Prompt Section 33:
        Verifies GET /admin-flow/api/patterns/activity/ returns JSON matching contract:
        - summary: { total_incidents, known_activity_incidents, unknown_activity_incidents, ... }
        - activities: [ { activity, incident_count, psif_linked_count, dataset_share, top_locations, ... } ]
        - location_matrix: { columns, rows }
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()
        invalidate_admin_flow_activity_cache()

        for i in range(5):
            Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                job_task="Painting & Surface Coating",
                description=f"Painting observation #{i}",
                location="Tank Farm",
            )

        client.force_login(admin_flow_user)
        url = reverse("admin_flow:api_patterns_activity")
        resp = client.get(url)

        assert resp.status_code == 200
        data = resp.json()

        assert "summary" in data
        assert data["summary"]["total_incidents"] == 5
        assert data["summary"]["known_activity_incidents"] == 5
        assert data["summary"]["unknown_activity_incidents"] == 0

        assert "activities" in data
        assert len(data["activities"]) == 1
        act = data["activities"][0]
        assert act["activity"] == "Painting & Surface Coating"
        assert act["incident_count"] == 5
        assert act["top_location"] == "Tank Farm"

        assert "location_matrix" in data
        assert "columns" in data["location_matrix"]
        assert "rows" in data["location_matrix"]
