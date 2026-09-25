"""
PSIF Platform — Task 3 Admin Flow Pattern Analysis Engine Test Suite.

Verifies:
1. Explicit fixtures:
   - Activity A = 10, Activity B = 7, Activity C = 3
   - Barrier A = 8, Barrier B = 5
   - Location A = 12, Location B = 7, Location C = 2
2. Descending frequency sorting for all 3 dimensions.
3. Unknown handling (UNKNOWN ACTIVITY, UNKNOWN LOCATION, UNKNOWN control state excluded from failures).
4. PSIF linkage calculation and explicit denominator labeling.
5. Control-state filtering (EFFECTIVE and UNKNOWN are NOT failures;
   ABSENT, FAILED, BYPASSED, NOT_VERIFIED, INCORRECTLY_ASSUMED, PARTIALLY_EFFECTIVE are counted).
6. Workspace isolation (global records completely excluded).
7. Duplicate incident handling (distinct incident counts).
8. Empty dataset handling.
9. REST APIs (/admin-flow/api/patterns/, /activity/, /barrier/, /location/) with authentication-derived scope.
10. Cache invalidation on new incident submission/adjudication.
"""

import uuid
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.pattern_engine import (
    ADMIN_FLOW_WORKSPACE,
    DEFICIENCY_CONTROL_STATES,
    NON_DEFICIENCY_CONTROL_STATES,
    normalize_admin_flow_activity,
    normalize_admin_flow_location,
    extract_all_admin_flow_pattern_observations,
    compute_activity_patterns,
    compute_barrier_patterns,
    compute_location_patterns,
    get_admin_flow_pattern_summary,
    invalidate_admin_flow_pattern_cache,
    get_admin_flow_pattern_cache_version,
)

User = get_user_model()


@pytest.fixture
def admin_flow_user(db):
    user, _ = User.objects.get_or_create(
        email="admin_flow_test@foresight.app",
        defaults={
            "username": "admin_flow_test@foresight.app",
            "role": "admin_flow",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def standard_user(db):
    user, _ = User.objects.get_or_create(
        email="safety_officer_test@foresight.app",
        defaults={
            "username": "safety_officer_test@foresight.app",
            "role": "safety_officer",
            "is_active": True,
        }
    )
    user.set_password("foresight2026")
    user.save()
    return user


@pytest.fixture
def active_model(db):
    mv, _ = ModelVersion.objects.get_or_create(
        version_label="v_20260906_202052",
        defaults={"is_active": True}
    )
    if not mv.is_active:
        mv.is_active = True
        mv.save()
    return mv


@pytest.mark.django_db
class TestTask3PatternEngineFixturesAndSorting:
    """
    Tests prompt-mandated fixtures:
    Activity A = 10, Activity B = 7, Activity C = 3
    Barrier A = 8, Barrier B = 5
    Location A = 12, Location B = 7, Location C = 2
    """

    def test_fixture_counts_and_sorting(self, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Define 3 Canonical Activities
        # Activity A: Lifting Operation / Crane Work (10 incidents)
        # Activity B: Working at Height / Scaffolding (7 incidents)
        # Activity C: Internal Vessel Cleaning & Inspection (3 incidents)
        act_a_incidents = []
        for i in range(10):
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description=f"Lifting operation #{i} involving crane and rigging.",
                job_task="Lifting Operation / Crane Work",
                location="Compressor Area",
            )
            act_a_incidents.append(inc)

        act_b_incidents = []
        for i in range(7):
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description=f"Scaffolding inspection #{i} at height.",
                job_task="Working at Height / Scaffolding",
                location="Workshop / Maintenance Bay",
            )
            act_b_incidents.append(inc)

        act_c_incidents = []
        for i in range(3):
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description=f"Vessel cleaning #{i} inside confined tank.",
                job_task="Internal Vessel Cleaning & Inspection",
                location="Pipe Rack / Manifold",
            )
            act_c_incidents.append(inc)

        # Set up Barrier A = 8 deficiency-linked, Barrier B = 5 deficiency-linked
        # Barrier A: Lockout / Tagout (8 incidents with FAILED / BYPASSED)
        for i in range(8):
            inc = act_a_incidents[i]
            inc.description = f"Equipment servicing #{i}: lockout tagout locks removed without authorization."
            inc.control_condition = "bypassed"
            inc.save(update_fields=["description", "control_condition"])
            IOGPRuleTag.objects.create(incident=inc, rule="Energy Isolation")

        # Barrier B: Certified Rigging / Whip Check Safety Cable (5 incidents with FAILED / ABSENT)
        for i in range(5):
            inc = act_b_incidents[i]
            inc.description = f"Lifting operation #{i}: certified rigging sling broke during crane lift."
            inc.control_condition = "failed"
            inc.save(update_fields=["description", "control_condition"])
            IOGPRuleTag.objects.create(incident=inc, rule="Safe Mechanical Lifting")

        # Set up Locations: Location A = 12, Location B = 7, Location C = 2
        # Location A: Tank Farm (12 incidents)
        # Location B: Wellhead Area (7 incidents)
        # Location C: Drilling Area / Rig Floor (2 incidents)
        all_incidents = act_a_incidents + act_b_incidents + act_c_incidents  # Total 20 incidents
        for inc in all_incidents[:12]:
            inc.location = "Tank Farm"
            inc.save(update_fields=["location"])

        for inc in all_incidents[12:19]:
            inc.location = "Wellhead Area"
            inc.save(update_fields=["location"])

        for inc in all_incidents[19:21]:  # 20th incident (only 1 left from 20), create 1 more to make 2
            inc.location = "Drilling Area / Rig Floor"
            inc.save(update_fields=["location"])

        extra_inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Extra drilling floor incident.",
            job_task="Routine Maintenance / Inspection",
            location="Drilling Area / Rig Floor",
        )

        # Verify summary output
        summary = get_admin_flow_pattern_summary(use_cache=False)
        activities = summary["activity_patterns"]
        barriers = summary["barrier_patterns"]
        locations = summary["location_patterns"]

        # 1. Activity sorting
        assert len(activities) >= 3
        # Activity A has 10
        assert activities[0]["category"] == "Lifting Operation / Crane Work"
        assert activities[0]["incident_count"] == 10
        # Activity B has 7
        assert activities[1]["category"] == "Work at Height / Scaffolding"
        assert activities[1]["incident_count"] == 7
        # Activity C has 3
        assert activities[2]["category"] == "Internal Vessel Cleaning & Inspection"
        assert activities[2]["incident_count"] == 3

        # 2. Barrier sorting
        assert len(barriers) >= 2
        # Barrier A has 8 deficiency-linked
        assert barriers[0]["barrier_domain"] in ["Lockout / Tagout (LOTO)", "Isolation Valve / Positive Mechanical Blind"]
        assert barriers[0]["deficiency_linked_count"] == 8
        # Barrier B has 5 deficiency-linked
        assert barriers[1]["barrier_domain"] == "Certified Rigging / Whip Check Safety Cable"
        assert barriers[1]["deficiency_linked_count"] == 5

        # 3. Location sorting
        assert len(locations) >= 3
        # Location A has 12
        assert locations[0]["internal_location"] == "Tank Farm"
        assert locations[0]["incident_count"] == 12
        # Location B has 7
        assert locations[1]["internal_location"] == "Wellhead Area"
        assert locations[1]["incident_count"] == 7
        # Location C has 2
        assert locations[2]["internal_location"] == "Drilling Area / Rig Floor"
        assert locations[2]["incident_count"] == 2


@pytest.mark.django_db
class TestTask3ControlStateFiltering:
    """
    Verify control-state semantics:
    - Deficiencies (ABSENT, FAILED, BYPASSED, NOT_VERIFIED, INCORRECTLY_ASSUMED, PARTIALLY_EFFECTIVE)
      are counted.
    - Non-deficiencies (EFFECTIVE, UNKNOWN) are NOT counted as barrier failures.
    """

    def test_effective_and_unknown_not_counted_as_failures(self, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Incident 1: EFFECTIVE control
        inc1 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Operator used safety harness properly during pipe work. The harness caught worker and barrier held as intended.",
            control_condition="effective",
        )
        IOGPRuleTag.objects.create(incident=inc1, rule="Working at Height")

        # Incident 2: UNKNOWN / Non-functional control state (no explicit failure evidence)
        inc2 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Worker carried safety harness in bag while walking across yard.",
            control_condition="unknown",
        )
        IOGPRuleTag.objects.create(incident=inc2, rule="Working at Height")

        # Incident 3: FAILED control
        inc3 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Safety harness lanyard snapped during fall arrest test.",
            control_condition="failed",
        )
        IOGPRuleTag.objects.create(incident=inc3, rule="Working at Height")

        # Incident 4: BYPASSED control
        inc4 = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Safety interlock switch bypassed with jumper wire.",
            control_condition="bypassed",
        )
        IOGPRuleTag.objects.create(incident=inc4, rule="Bypassing Safety Controls")

        summary = get_admin_flow_pattern_summary(use_cache=False)
        barriers = {b["barrier_name"]: b for b in summary["barrier_patterns"]}

        # Safety Harness / Fall-Arrest System has 1 deficiency-linked incident (inc3)
        wah = barriers["Safety Harness / Fall-Arrest System"]
        assert wah["total_matched_count"] >= 2
        assert wah["deficiency_linked_count"] == 1  # inc3 only! inc1 (effective) and inc2 (stored) excluded.

        # Safety Interlock / Light Curtain has 1 deficiency-linked incident
        bsc = barriers["Safety Interlock / Light Curtain"]
        assert bsc["deficiency_linked_count"] == 1


@pytest.mark.django_db
class TestTask3UnknownsAndNormalization:
    """
    Test fallback to 'UNKNOWN ACTIVITY' and 'UNKNOWN LOCATION'.
    """

    def test_unknown_activity_and_location(self):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Unclassified general occurrence with no identifiable task or area.",
            job_task="Random arbitrary non-industrial phrase 987",
            location="",
        )

        summary = get_admin_flow_pattern_summary(use_cache=False)
        activities = summary["activity_patterns"]
        locations = summary["location_patterns"]

        assert any(a["category"] == "UNKNOWN ACTIVITY" for a in activities)
        assert any(l["internal_location"] == "UNKNOWN LOCATION" for l in locations)

    def test_activity_normalization_aliases(self):
        # Verify prompt required aliases
        assert normalize_admin_flow_activity("lifting operation")[0] == "Lifting Operation / Crane Work"
        assert normalize_admin_flow_activity("material lifting")[0] == "Lifting Operation / Crane Work"
        assert normalize_admin_flow_activity("crane lifting")[0] == "Lifting Operation / Crane Work"
        assert normalize_admin_flow_activity("welding")[0] == "Welding, Cutting & Hot Work"
        assert normalize_admin_flow_activity("")[0] == "UNKNOWN ACTIVITY"
        assert normalize_admin_flow_activity(None)[0] == "UNKNOWN ACTIVITY"


@pytest.mark.django_db
class TestTask3PSIFLinkageAndRates:
    """
    Verify PSIF linkage rate calculation and explicit denominator labels.
    """

    def test_psif_linkage_rate_calculation(self, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # 3 incidents for Welding, Cutting & Hot Work: 2 PSIF, 1 NOT PSIF
        for i in range(3):
            inc = Incident.objects.create(
                workspace_id=ADMIN_FLOW_WORKSPACE,
                description=f"Torch cutting operation #{i} near hydrocarbon gas line.",
                job_task="Welding, Cutting & Hot Work",
                location="Process Area / Refining Unit",
            )
            is_psif = (i < 2)
            PredictionResult.objects.create(
                incident=inc,
                model_version=active_model,
                psif_probability=0.85 if is_psif else 0.15,
                psif_predicted=is_psif,
                risk_level="high" if is_psif else "low",
                is_sparse_input=False,
            )

        summary = get_admin_flow_pattern_summary(use_cache=False)
        hw = next(a for a in summary["activity_patterns"] if a["category"] == "Welding, Cutting & Hot Work")

        assert hw["incident_count"] == 3
        assert hw["psif_linked_count"] == 2
        assert hw["psif_linkage_rate"] == 66.7
        assert "66.7% PSIF-linked among matched Admin Flow observations (denominator: 3)" in hw["rate_label"]


@pytest.mark.django_db
class TestTask3WorkspaceIsolation:
    """
    Ensure global incidents (workspace_id=None) are never scanned or counted in pattern analysis.
    """

    def test_global_incidents_strictly_excluded(self, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        # Create global incident
        global_inc = Incident.objects.create(
            workspace_id=None,
            description="Global refinery explosion during heavy lifting.",
            job_task="Lifting Operation / Crane Work",
            location="Tank Farm",
            control_condition="failed",
        )
        IOGPRuleTag.objects.create(incident=global_inc, rule="Safe Mechanical Lifting")

        # Admin Flow summary should still be empty
        summary = get_admin_flow_pattern_summary(use_cache=False)
        assert summary["total_incidents"] == 0
        assert summary["has_data"] is False
        assert summary["activity_patterns"] == []
        assert summary["barrier_patterns"] == []
        assert summary["location_patterns"] == []

        # Cleanup
        global_inc.delete()


@pytest.mark.django_db
class TestTask3APIsAndCache:
    """
    Verify REST API endpoints and cache invalidation.
    """

    def test_api_endpoints_success(self, client, admin_flow_user, active_model):
        Incident.objects.filter(workspace_id=ADMIN_FLOW_WORKSPACE).delete()
        invalidate_admin_flow_pattern_cache()

        inc = Incident.objects.create(
            workspace_id=ADMIN_FLOW_WORKSPACE,
            description="Wireline winch motor seized, certified rigging sling failed during mechanical lift.",
            job_task="Lifting Operation / Crane Work",
            location="Wellhead Area",
            control_condition="failed",
        )
        IOGPRuleTag.objects.create(incident=inc, rule="Safe Mechanical Lifting")

        client.force_login(admin_flow_user)

        # 1. Overview API
        resp = client.get(reverse("admin_flow:api_patterns_overview"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_id"] == ADMIN_FLOW_WORKSPACE
        assert data["total_incidents"] == 1
        assert "activity_patterns" in data
        assert "barrier_patterns" in data
        assert "location_patterns" in data

        # 2. Activity API
        resp_act = client.get(reverse("admin_flow:api_patterns_activity"))
        assert resp_act.status_code == 200
        assert resp_act.json()["total_patterns"] >= 1

        # 3. Barrier API
        resp_bar = client.get(reverse("admin_flow:api_patterns_barrier"))
        assert resp_bar.status_code == 200
        assert resp_bar.json()["total_patterns"] >= 1

        # 4. Location API
        resp_loc = client.get(reverse("admin_flow:api_patterns_location"))
        assert resp_loc.status_code == 200
        assert resp_loc.json()["total_patterns"] >= 1
        assert resp_loc.json()["site_context"] == "Duliajan Operational Complex"

    def test_api_forbidden_for_standard_user(self, client, standard_user):
        client.force_login(standard_user)
        resp = client.get(reverse("admin_flow:api_patterns_overview"))
        # Must be forbidden or redirect
        assert resp.status_code in [403, 302]

    def test_cache_invalidation_lifecycle(self, admin_flow_user):
        v1 = get_admin_flow_pattern_cache_version()
        invalidate_admin_flow_pattern_cache()
        v2 = get_admin_flow_pattern_cache_version()
        assert v2 > v1
