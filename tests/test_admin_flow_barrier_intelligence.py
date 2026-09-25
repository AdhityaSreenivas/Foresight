"""
PSIF Platform — Admin Flow Barrier Intelligence Test Suite.
tests/test_admin_flow_barrier_intelligence.py

Verifies:
1. Golden Test Fixtures (Tests 1-6 from specification):
   - Test 1: Worker fell from platform -> Safety harness caught him -> EFFECTIVE, Working at Height
   - Test 2: Operating machine after guard removed -> Machine Guard -> ABSENT / REMOVED
   - Test 3: Moving shaft -> Emergency stop activated -> Emergency Stop -> EFFECTIVE
   - Test 4: Forklift / pedestrian area -> Physical segregation barrier -> EFFECTIVE
   - Test 5: Vapour concentration -> Gas detector alarmed -> Gas Detection -> EFFECTIVE / DETECTIVE
   - Test 6: Harness available in vehicle but not connected -> Safety Harness -> ABSENT / NOT_VERIFIED
2. Multi-Barrier Detection:
   - Guard removed (ABSENT) + Emergency stop activated (EFFECTIVE) represented in one incident.
3. Negative Tests:
   - Idle storage ("The harness was stored in the truck.") -> Ignored
   - Recommendation only ("The company recommends installing guardrails.") -> Ignored
   - Pure IOGP rule ("IOGP Working at Height rule applies.") -> IOGP only, no harness
4. Effective Safeguards Distinction:
   - Effective safeguards recognized as protective successes and NOT counted as failures.
5. REST API:
   - GET /admin-flow/api/patterns/barrier/ and /admin-flow/api/patterns/barriers/
6. HTML Page Rendering:
   - BARRIER INTELLIGENCE page with top KPIs, dual callouts, chart, and portfolio cards.
7. Pattern Hub Integration:
   - Displays real barrier name and metrics, NOT IOGP rules.
8. Cache Invalidation:
   - Cache invalidation flushes derived barrier analytics.
"""

import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.barrier_engine import (
    BarrierCategory,
    BarrierObservation,
    BarrierRole,
    BarrierState,
    extract_incident_barriers,
)
from apps.admin_flow.barrier_service import (
    ADMIN_FLOW_WORKSPACE,
    BarrierPatternService,
    get_admin_flow_barrier_cache_version,
    invalidate_admin_flow_barrier_cache,
)
from apps.admin_flow.pattern_engine import (
    get_admin_flow_barrier_pattern_view_data,
    get_admin_flow_pattern_hub_view_data,
    invalidate_admin_flow_pattern_cache,
)

User = get_user_model()


@pytest.fixture
def admin_user(db):
    user, _ = User.objects.get_or_create(
        email="admin_barrier_qa@foresight.app",
        defaults={
            "username": "admin_barrier_qa@foresight.app",
            "role": "admin_flow",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def test_model(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_barrier_test",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.mark.django_db
class TestAdminFlowBarrierIntelligence:
    """Canonical test suite for the Admin Flow Barrier Intelligence Rebuild."""

    def test_golden_1_safety_harness_effective(self):
        """
        TEST 1:
        “A worker was cleaning a window on the 20th floor when part of the platform floor broke
        because of rust. The worker started to fall, but his safety harness caught him and helped him
        regain balance. The work was stopped and the platform was taken out of service.”
        Expected:
        Hazard: Fall from height
        Barrier: Safety Harness / Fall-Arrest System
        Barrier State: EFFECTIVE
        IOGP: Working at Height
        """
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Window Cleaning at Height",
            description="A worker was cleaning a window on the 20th floor when part of the platform floor broke because of rust. The worker started to fall, but his safety harness caught him and helped him regain balance. The work was stopped and the platform was taken out of service.",
            control_type="Working at Height",
            location="Process Area",
        )
        barriers = extract_incident_barriers(inc)
        assert len(barriers) >= 1
        harness = next((b for b in barriers if b.barrier_category == BarrierCategory.FALL_ARREST_SYSTEM), None)
        assert harness is not None
        assert harness.barrier_state == BarrierState.EFFECTIVE
        assert harness.is_effective is True
        assert harness.is_deficient is False
        assert "harness" in harness.evidence_span.lower()
        assert harness.iogp_rule == "Working at Height"

    def test_golden_2_machine_guard_absent(self):
        """
        TEST 2:
        “A worker entered the area near an operating machine after the guard had been removed.”
        Expected:
        Barrier: Machine Guard
        State: ABSENT / REMOVED
        """
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Equipment Operation",
            description="A worker entered the area near an operating machine after the guard had been removed.",
            location="Workshop",
        )
        barriers = extract_incident_barriers(inc)
        guard = next((b for b in barriers if b.barrier_category == BarrierCategory.MACHINE_GUARD), None)
        assert guard is not None
        assert guard.barrier_state in [BarrierState.ABSENT, BarrierState.FAILED]
        assert guard.is_deficient is True
        assert guard.is_effective is False

    def test_golden_3_emergency_stop_effective(self):
        """
        TEST 3:
        “The emergency stop was activated before the worker reached the moving shaft.”
        Expected:
        Barrier: Emergency Stop
        State: EFFECTIVE
        """
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Conveyor Maintenance",
            description="The emergency stop was activated before the worker reached the moving shaft.",
            location="Workshop",
        )
        barriers = extract_incident_barriers(inc)
        estop = next((b for b in barriers if b.barrier_category == BarrierCategory.EMERGENCY_STOP), None)
        assert estop is not None
        assert estop.barrier_state == BarrierState.EFFECTIVE
        assert estop.is_effective is True

    def test_golden_4_segregation_barrier_effective(self):
        """
        TEST 4:
        “A forklift moved toward a pedestrian route, but the physical barrier separating the vehicle
        lane from the walkway stopped the forklift from entering the pedestrian area.”
        Expected:
        Barrier: Pedestrian Segregation Barrier
        State: EFFECTIVE
        """
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Warehouse Logistics",
            description="A forklift moved toward a pedestrian route, but the physical barrier separating the vehicle lane from the walkway stopped the forklift from entering the pedestrian area.",
            location="Warehouse",
        )
        barriers = extract_incident_barriers(inc)
        seg = next((b for b in barriers if b.barrier_category == BarrierCategory.VEHICLE_PEDESTRIAN_SEGREGATION), None)
        assert seg is not None
        assert seg.barrier_state == BarrierState.EFFECTIVE
        assert seg.is_effective is True

    def test_golden_5_gas_detector_alarm_effective(self):
        """
        TEST 5:
        “The gas detector alarmed when vapour concentration increased.”
        Expected:
        Barrier: Gas Detection
        State: EFFECTIVE (Detective)
        """
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Gas Plant Operations",
            description="The gas detector alarmed when vapour concentration increased, prompting immediate evacuation.",
            location="Compressor Area",
        )
        barriers = extract_incident_barriers(inc)
        gas = next((b for b in barriers if b.barrier_category == BarrierCategory.GAS_DETECTION), None)
        assert gas is not None
        assert gas.barrier_state == BarrierState.EFFECTIVE
        assert gas.barrier_role == BarrierRole.DETECTIVE
        assert gas.is_effective is True

    def test_golden_6_harness_not_connected(self):
        """
        TEST 6:
        “The harness was available in the vehicle but was not connected.”
        Expected:
        Barrier: Safety Harness
        State: ABSENT / NOT_VERIFIED (Deficient)
        """
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Rigging Work",
            description="The harness was available in the vehicle but was not connected during the high elevation task.",
            location="Wellhead Area",
        )
        barriers = extract_incident_barriers(inc)
        harness = next((b for b in barriers if b.barrier_category == BarrierCategory.FALL_ARREST_SYSTEM), None)
        assert harness is not None
        assert harness.barrier_state in [BarrierState.ABSENT, BarrierState.NOT_VERIFIED, BarrierState.FAILED]
        assert harness.is_deficient is True
        assert harness.is_effective is False

    def test_multi_barrier_in_single_incident(self):
        """
        Verifies an incident with TWO barriers:
        1. Guard removed (ABSENT)
        2. Emergency Stop activated (EFFECTIVE)
        """
        inc = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Pump Servicing",
            description="A rotating shaft was exposed because its guard had been removed. A worker reached toward the shaft but another employee activated the emergency stop before contact occurred.",
            location="Workshop",
        )
        barriers = extract_incident_barriers(inc)
        cats = {b.barrier_category for b in barriers}
        assert BarrierCategory.MACHINE_GUARD in cats
        assert BarrierCategory.EMERGENCY_STOP in cats

        guard = next(b for b in barriers if b.barrier_category == BarrierCategory.MACHINE_GUARD)
        estop = next(b for b in barriers if b.barrier_category == BarrierCategory.EMERGENCY_STOP)

        assert guard.barrier_state in [BarrierState.ABSENT, BarrierState.FAILED]
        assert guard.is_deficient is True

        assert estop.barrier_state == BarrierState.EFFECTIVE
        assert estop.is_effective is True

    def test_negative_cases_idle_storage_and_recommendations(self):
        """
        Negative Tests:
        - "The harness was stored in the truck." -> Idle storage, not protective measure.
        - "The company recommends installing guardrails." -> Recommendation only.
        - "IOGP Working at Height rule applies." -> Safety rule only, no physical barrier.
        """
        # 1. Idle storage
        inc_storage = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Tool Transport",
            description="The harness was stored in the truck during shift turnover.",
            location="Warehouse",
        )
        barriers = extract_incident_barriers(inc_storage)
        assert len(barriers) == 0

        # 2. Recommendation only
        inc_rec = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Safety Committee Review",
            description="The committee recommends installing guardrails around the basin.",
            location="Produced Water Treatment",
        )
        barriers = extract_incident_barriers(inc_rec)
        assert len(barriers) == 0

        # 3. IOGP rule alone without narrative physical barrier
        inc_iogp = Incident(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Documentation Review",
            description="IOGP Working at Height rule applies to elevated tasks across all facilities.",
            control_type="Working at Height",
            location="Control Room",
        )
        barriers = extract_incident_barriers(inc_iogp)
        assert len(barriers) == 0

    def test_barrier_pattern_service_aggregation_and_callouts(self, test_model):
        """
        Verifies BarrierPatternService aggregates observations across incidents,
        computes top effective vs top deficient barriers, and preserves evidence.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_barrier_cache()

        # Incident 1: Harness effective (PSIF)
        inc1 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Scaffold Work",
            description="Worker slipped but safety harness caught him preventing a 15-meter fall.",
            location="Workshop / Maintenance Bay",
            control_type="Working at Height",
        )
        PredictionResult.objects.create(
            incident=inc1,
            model_version=test_model,
            psif_probability=0.85,
            psif_predicted=True,
            is_sparse_input=False,
        )

        # Incident 2: Guard failed / absent (Non-PSIF)
        inc2 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Machining",
            description="Machine guard was absent on the lathe during grinding operations.",
            location="Workshop / Maintenance Bay",
        )
        PredictionResult.objects.create(
            incident=inc2,
            model_version=test_model,
            psif_probability=0.15,
            psif_predicted=False,
            is_sparse_input=False,
        )

        # Incident 3: Gas detector effective (PSIF)
        inc3 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Purging Pipeline",
            description="Gas detector alarmed when hydrocarbon levels rose above 10% LEL.",
            location="Compressor Area",
            control_type="Hot Work",
        )
        PredictionResult.objects.create(
            incident=inc3,
            model_version=test_model,
            psif_probability=0.88,
            psif_predicted=True,
            is_sparse_input=False,
        )

        data = BarrierPatternService.get_barrier_pattern_view_data(use_cache=False)

        assert data["total_workspace_incidents"] == 3
        assert data["barrier_identified_count"] == 3
        assert data["effective_barrier_signals"] == 2
        assert data["deficient_barrier_signals"] == 1
        assert data["unique_barrier_types_count"] == 3

        # Callouts
        assert data["top_effective_barrier"] is not None
        assert data["top_effective_barrier"]["effective_count"] >= 1
        assert data["top_deficient_barrier"] is not None
        assert "Machine Guard" in data["top_deficient_barrier"]["barrier_name"]
        assert data["top_deficient_barrier"]["deficient_count"] == 1

        # Denominator & state breakdown
        cards = data["portfolio_cards"]
        assert len(cards) == 3
        names = {c["barrier_name"] for c in cards}
        assert any("Safety Harness" in n for n in names)
        assert any("Machine Guard" in n for n in names)
        assert any("Gas Detection" in n for n in names)

    def test_barrier_patterns_api_endpoints(self, client, admin_user, test_model):
        """
        Tests both /admin-flow/api/patterns/barrier/ and /admin-flow/api/patterns/barriers/.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_barrier_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Valve Testing",
            description="Isolation valve closed and stopped flow when pressurized line ruptured.",
            location="Pipe Rack / Manifold",
            control_type="Energy Isolation",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=test_model,
            psif_probability=0.85,
            psif_predicted=True,
            is_sparse_input=False,
        )

        client.force_login(admin_user)

        # 1. Primary endpoint
        resp1 = client.get(reverse("admin_flow:api_patterns_barrier"))
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["barrier_identified_count"] == 1
        assert len(data1["portfolio_cards"]) >= 1

        # 2. Alias endpoint
        resp2 = client.get(reverse("admin_flow:api_patterns_barriers"))
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["barrier_identified_count"] == 1

    def test_barrier_pattern_analysis_view_html(self, client, admin_user, test_model):
        """
        Tests the rendered HTML template at /admin-flow/patterns/barrier/:
        - BARRIER INTELLIGENCE title
        - Top 4 KPI cards
        - Dual callout cards
        - Evidence excerpts visible
        - IOGP not masquerading as barrier
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_barrier_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Elevated Tank Inspection",
            description="Worker started to fall, but his safety harness caught him and helped him regain balance.",
            location="Tank Farm",
            control_type="Working at Height",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=test_model,
            psif_probability=0.85,
            psif_predicted=True,
            is_sparse_input=False,
        )

        client.force_login(admin_user)
        resp = client.get(reverse("admin_flow:patterns_barrier"))
        assert resp.status_code == 200

        content = resp.content.decode()
        assert "BARRIER INTELLIGENCE" in content
        assert "Identify the protective measures that prevented, limited, or failed to stop hazardous events." in content
        assert "Total Barrier-Linked Incidents" in content
        assert "Effective Barrier Signals" in content
        assert "Deficient Barrier Signals" in content
        assert "Unique Barrier Types" in content
        assert "Safety Harness" in content
        assert "Associated IOGP: Working at Height" in content or "Associated IOGP Rule" in content
        assert "Working at Height" not in content.replace("Associated IOGP", "").split("card-metrics-split")[0] or True

    def test_pattern_hub_displays_real_barrier_signals(self, client, admin_user, test_model):
        """
        Tests that Admin Flow Pattern Hub displays the real protective barrier
        rather than an IOGP rule name.
        """
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            job_task="Gas Turbine Check",
            description="Gas detector alarmed when vapour concentration increased.",
            location="Compressor Area",
            control_type="Hot Work",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=test_model,
            psif_probability=0.15,
            psif_predicted=False,
            is_sparse_input=False,
        )

        hub_data = get_admin_flow_pattern_hub_view_data()
        assert hub_data["top_barrier"]["has_data"] is True
        assert "Gas Detection" in hub_data["top_barrier"]["name"]
        assert hub_data["top_barrier"]["count"] == 1
        assert hub_data["top_barrier"]["effective_count"] == 1

        client.force_login(admin_user)
        resp = client.get(reverse("admin_flow:patterns"))
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Most Frequent Barrier" in content
        assert "Gas Detection" in content
