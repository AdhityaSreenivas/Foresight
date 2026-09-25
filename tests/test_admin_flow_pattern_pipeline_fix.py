"""
Targeted tests for Admin Flow Pattern Recognition Surgical Data-Pipeline Fix.

Validates:
1. 5-record controlled fixture:
   - Filter replacement in Parking Area
   - Conveyor maintenance in Workshop
   - Pressure-line maintenance in Compressor Area (deficiency-linked, PSIF-linked)
   - Hot work in Process Area (deficiency-linked, PSIF-linked)
   - Lifting operation in Pipe Rack (effective control, non-deficiency)
2. 50-record benchmark dataset:
   - Total records = 50
   - Activity extraction: 0 / 50 UNKNOWN
   - Location extraction: 16 extracted, 34 genuine unknowns
   - Barrier deficiency signals: only evidence-supported deficiency states appear
3. Pattern Hub and detail pages consistency and multi-dimensional synthesis integrity.
"""

import json
import pytest
from django.contrib.auth import get_user_model

from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.pattern_engine import (
    ADMIN_FLOW_WORKSPACE,
    extract_all_admin_flow_pattern_observations,
    compute_activity_patterns,
    compute_location_patterns,
    compute_barrier_patterns,
    normalize_admin_flow_activity,
    normalize_admin_flow_location,
    extract_admin_flow_barrier_observations,
    get_admin_flow_pattern_hub_view_data,
    get_admin_flow_activity_pattern_view_data,
    get_admin_flow_location_pattern_view_data,
    get_admin_flow_barrier_pattern_view_data,
    invalidate_admin_flow_pattern_cache,
    DEFICIENCY_CONTROL_STATES,
)

User = get_user_model()


@pytest.fixture
def active_model(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_pipeline_fix_test",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.fixture
def controlled_5_incidents(db, active_model):
    """
    Creates the 5-record controlled validation fixture:
    1. Filter replacement in Parking Area
    2. Conveyor maintenance in Workshop
    3. Pressure-line maintenance in Compressor Area (PSIF + Energy Isolation NOT_VERIFIED)
    4. Hot work in Process Area (PSIF + Energy Isolation / Work Authorization ABSENT)
    5. Lifting operation in Pipe Rack (Safe Mechanical Lifting, EFFECTIVE)
    """
    Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
    invalidate_admin_flow_pattern_cache()

    incidents = []

    # 1. Filter replacement in Parking Area
    i1 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        incident_date="2026-03-01",
        description="While performing Filter replacement in Parking Area, technicians replaced secondary fuel filters on mobile utility trucks. Standard hand tools were used and no pressure was present.",
        control_condition="effective",
    )
    PredictionResult.objects.create(
        incident=i1,
        model_version=active_model,
        psif_predicted=False,
        psif_probability=0.15,
        risk_level=PredictionResult.RiskLevel.LOW,
        is_sparse_input=False,
    )
    incidents.append(i1)

    # 2. Conveyor maintenance in Workshop
    i2 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        incident_date="2026-03-02",
        description="An employee working on Conveyor maintenance in Workshop was lubricating roller bearings with the motor stopped and breaker opened. Routine work completed safely.",
        control_condition="effective",
    )
    PredictionResult.objects.create(
        incident=i2,
        model_version=active_model,
        psif_predicted=False,
        psif_probability=0.18,
        risk_level=PredictionResult.RiskLevel.LOW,
        is_sparse_input=False,
    )
    incidents.append(i2)

    # 3. Pressure-line maintenance in Compressor Area (Deficiency + PSIF)
    i3 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        incident_date="2026-03-03",
        description="While conducting Pressure-line maintenance in Compressor Area, mechanics prepared to break a flange on a discharge manifold. Isolation locks were not verified before unbolting began, resulting in sudden gas pressure release into the breathing zone.",
        control_condition="not_verified",
    )
    PredictionResult.objects.create(
        incident=i3,
        model_version=active_model,
        psif_predicted=True,
        psif_probability=0.92,
        risk_level=PredictionResult.RiskLevel.CRITICAL,
        is_sparse_input=False,
    )
    incidents.append(i3)

    # 4. Hot work in Process Area (Deficiency + PSIF)
    i4 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        incident_date="2026-03-04",
        description="An incident during Hot work in Process Area occurred when welders ignited an arc near a live hydrocarbon line without gas testing and with no hot work permit in place. Arc flash occurred.",
        control_condition="absent",
    )
    PredictionResult.objects.create(
        incident=i4,
        model_version=active_model,
        psif_predicted=True,
        psif_probability=0.88,
        risk_level=PredictionResult.RiskLevel.HIGH,
        is_sparse_input=False,
    )
    incidents.append(i4)

    # 5. Lifting operation in Pipe Rack (Effective control)
    i5 = Incident.objects.create(
        workspace_id=ADMIN_FLOW_WORKSPACE,
        incident_date="2026-03-05",
        description="While performing Lifting operation in Pipe Rack, a certified rigger and crane operator lifted heavy steel headers. Rigging held securely and physical exclusion barricades were strictly maintained.",
        control_condition="effective",
    )
    PredictionResult.objects.create(
        incident=i5,
        model_version=active_model,
        psif_predicted=False,
        psif_probability=0.20,
        risk_level=PredictionResult.RiskLevel.LOW,
        is_sparse_input=False,
    )
    incidents.append(i5)

    invalidate_admin_flow_pattern_cache()
    return incidents


@pytest.mark.django_db
class TestAdminFlowPatternPipelineFix:
    """Test suite verifying the surgical pipeline fix on both 5-record fixture and 50-record benchmark."""

    def test_controlled_5_record_fixture(self, controlled_5_incidents):
        """Validates the 5-record fixture against exact prompt expectations."""
        observations = extract_all_admin_flow_pattern_observations(controlled_5_incidents)
        assert len(observations) >= 15  # At least 3 dimensions per record

        # 1. Activity Patterns
        act_patterns = compute_activity_patterns(observations)
        act_names = {a["category"] for a in act_patterns}
        # Verify all 5 activities are recognized (none are UNKNOWN)
        assert "UNKNOWN ACTIVITY" not in act_names
        assert any("Filter Replacement" in a for a in act_names)
        assert any("Conveyor Maintenance" in a for a in act_names)
        assert any("Pressure-Line Maintenance" in a for a in act_names)
        assert any("Hot Work" in a for a in act_names)
        assert any("Safe Mechanical Lifting" in a or "Lifting Operation" in a for a in act_names)

        # 2. Location Patterns
        loc_patterns = compute_location_patterns(observations)
        loc_counts = {l["internal_location"]: l["incident_count"] for l in loc_patterns}
        assert "UNKNOWN LOCATION" not in loc_counts
        assert loc_counts.get("Parking Area") == 1
        assert loc_counts.get("Workshop / Maintenance Bay") == 1
        assert loc_counts.get("Compressor Area") == 1
        assert loc_counts.get("Process Area / Refining Unit") == 1
        assert loc_counts.get("Pipe Rack / Manifold") == 1

        # 3. Barrier Patterns (Only evidence-supported deficiency states appear)
        bar_patterns = compute_barrier_patterns(observations)
        deficiency_signals = [b for b in bar_patterns if b["deficiency_linked_count"] > 0]
        assert len(deficiency_signals) >= 1
        # Energy Isolation should appear with NOT_VERIFIED or ABSENT
        ei = next((b for b in deficiency_signals if b["barrier_domain"] == "Energy Isolation"), None)
        assert ei is not None
        assert ei["dominant_control_state"] in ["NOT_VERIFIED", "ABSENT", "FAILED"]
        assert ei["deficiency_linked_count"] >= 1

        # Effective controls (Records 1, 2, 5) must NOT be counted as deficiency failures
        total_deficiencies = sum(b["deficiency_linked_count"] for b in bar_patterns)
        assert total_deficiencies == 2  # Only records 3 and 4

        # 4. PSIF Linkage
        psif_linked_deficiencies = sum(b["psif_linked_count"] for b in bar_patterns)
        assert psif_linked_deficiencies == 2  # Records 3 and 4 are PSIF-predicted

    def test_50_record_benchmark_coverage(self):
        """Validates that the 50-record benchmark no longer has 50/50 unknown activity or 42/50 unknown location."""
        with open("tests/fixtures/admin_flow_50_benchmark.json") as f:
            raw_data = json.load(f)

        assert len(raw_data) == 50

        # Build in-memory incident objects
        mock_incidents = []
        for idx, d in enumerate(raw_data):
            inc = Incident(
                id=idx + 1,
                description=d.get("description", ""),
                job_task=d.get("job_task"),
                location=d.get("location"),
                department=d.get("department"),
                control_condition=d.get("control_condition"),
                control_type=d.get("control_type"),
                workspace_id=ADMIN_FLOW_WORKSPACE,
            )
            mock_incidents.append(inc)

        observations = extract_all_admin_flow_pattern_observations(mock_incidents)

        # 1. Activity Verification
        act_patterns = compute_activity_patterns(observations)
        unknown_act = [a for a in act_patterns if a["category"] == "UNKNOWN ACTIVITY"]
        unknown_act_count = unknown_act[0]["incident_count"] if unknown_act else 0
        assert unknown_act_count == 0, f"Expected 0 unknown activities, got {unknown_act_count}"
        total_act_count = sum(a["incident_count"] for a in act_patterns)
        assert total_act_count == 50

        # 2. Location Verification
        loc_patterns = compute_location_patterns(observations)
        loc_counts = {l["internal_location"]: l["incident_count"] for l in loc_patterns}
        # 16 records have explicit locations mentioned in narrative; 34 genuine unknowns remain
        assert loc_counts.get("UNKNOWN LOCATION") == 34, f"Expected 34 genuine unknown locations, got {loc_counts.get('UNKNOWN LOCATION')}"
        extracted_locations_count = sum(count for loc, count in loc_counts.items() if loc != "UNKNOWN LOCATION")
        assert extracted_locations_count == 16, f"Expected 16 extracted locations, got {extracted_locations_count}"
        assert loc_counts.get("Electrical Substation") == 4
        assert loc_counts.get("Parking Area") == 4
        assert loc_counts.get("Basement Pump Room") == 2
        assert loc_counts.get("Compressor Area") == 2
        assert loc_counts.get("Loading Dock") == 2
        assert loc_counts.get("Workshop / Maintenance Bay") == 2

        # 3. Barrier Verification
        bar_patterns = compute_barrier_patterns(observations)
        # Records with real control failure evidence (13, 14, 21, 30) produce deficiency signals
        deficiency_bars = [b for b in bar_patterns if b["deficiency_linked_count"] > 0]
        assert len(deficiency_bars) >= 1
        total_deficiencies = sum(b["deficiency_linked_count"] for b in deficiency_bars)
        assert total_deficiencies == 4

    def test_hub_and_detail_views_agreement(self, controlled_5_incidents):
        """Ensures Pattern Hub and detailed pages consume the exact same underlying aggregates."""
        hub_data = get_admin_flow_pattern_hub_view_data()
        act_data = get_admin_flow_activity_pattern_view_data()
        loc_data = get_admin_flow_location_pattern_view_data()
        bar_data = get_admin_flow_barrier_pattern_view_data()

        assert hub_data["total_incidents"] == 5
        assert act_data["total_workspace_incidents"] == 5
        assert loc_data["total_workspace_incidents"] == 5

        # Check multi-dimensional relationship pathway in Hub
        assert hub_data["has_relationships_data"] is True
        assert hub_data["primary_pathway"] is not None
        pw = hub_data["primary_pathway"]
        # Must NOT contain UNKNOWN sentinels
        assert pw["activity"] != "UNKNOWN ACTIVITY"
        assert pw["location"] != "UNKNOWN LOCATION"
        assert pw["barrier"] != "Undetermined / Non-Specific Control"
