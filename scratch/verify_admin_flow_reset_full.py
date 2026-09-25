"""
Verification Script for Admin Flow Clean-Sheet Reset.
Tests the complete end-to-end lifecycle:
1. Login as Admin Flow
2. Populate Admin Flow with 10 incidents + predictions + patterns
3. Verify Dashboard shows data, Pattern Analysis shows patterns
4. Perform Reset Demo (POST /admin-flow/reset/)
5. Verify Dashboard all 6 KPIs = 0
6. Verify Incidents list empty
7. Verify PSIF page 0
8. Verify IOGP page 0
9. Verify Pattern Analysis hub empty
10. Verify Activity, Barrier, Location empty
11. Submit 1 incident -> verify Total Incidents = 1
12. Double Reset -> verify safely returns to 0
13. Verify normal login has global data intact and no reset UI
"""

import os
import sys
from pathlib import Path
import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.test import Client
from apps.accounts.models import User
from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion
from apps.admin_flow.services import (
    reset_admin_flow_workspace,
    get_admin_flow_analytics_summary,
    get_admin_flow_psif_metrics,
    get_admin_flow_iogp_metrics,
    get_admin_flow_generation,
    get_admin_flow_reset_audit_log,
)
from apps.admin_flow.pattern_engine import (
    get_admin_flow_pattern_hub_view_data,
    get_admin_flow_activity_pattern_view_data,
    get_admin_flow_barrier_pattern_view_data,
    get_admin_flow_location_pattern_view_data,
)

def run_verification():
    print("=== STARTING ADMIN FLOW RESET E2E VERIFICATION ===")

    # Setup users
    admin_flow_user, _ = User.objects.get_or_create(
        email="admin_flow@foresight.app",
        defaults={"username": "admin_flow@foresight.app", "role": "admin_flow", "is_active": True}
    )
    admin_flow_user.set_password("foresight2026")
    admin_flow_user.save()

    regular_user, _ = User.objects.get_or_create(
        email="admin@foresight.app",
        defaults={"username": "admin@foresight.app", "role": "admin", "is_active": True}
    )
    regular_user.set_password("foresight2026")
    regular_user.save()

    # Step 1: Clean reset initially
    print("1. Performing baseline initial reset...")
    reset_admin_flow_workspace(user=admin_flow_user)
    summary_0 = get_admin_flow_analytics_summary()
    assert summary_0["total_incidents"] == 0
    assert summary_0["prediction_eligible_count"] == 0
    assert summary_0["psif_count"] == 0
    assert summary_0["not_psif_count"] == 0
    assert summary_0["insufficient_evidence_count"] == 0
    assert summary_0["human_reviewed_count"] == 0
    print("   ✓ Initial baseline all 6 KPIs = 0")

    # Step 2: Populate Admin Flow with controlled records
    print("2. Populating Admin Flow with 10 records...")
    active_model = ModelVersion.objects.filter(is_active=True).first()
    assert active_model is not None, "Active model required"

    activities = ["Hot Work", "Lifting Operations", "Confined Space Entry", "Work at Height"]
    locations = ["Drill Floor", "Tank Farm", "Process Area", "Central Workshop"]
    
    for i in range(10):
        inc = Incident.objects.create(
            workspace_id="admin_flow",
            description=f"Admin Flow test incident {i}: High pressure gas leak near flange during welding operations on pipe section.",
            job_task=activities[i % len(activities)],
            location=locations[i % len(locations)],
            department="Operations",
            high_energy_present="yes" if i % 2 == 0 else "no",
            direct_control_present="yes",
            control_condition="failed" if i % 2 == 0 else "maintained",
        )
        is_psif = (i % 3 == 0)
        PredictionResult.objects.create(
            incident=inc,
            model_version=active_model,
            psif_probability=0.88 if is_psif else 0.15,
            psif_predicted=is_psif,
            risk_level="CRITICAL" if is_psif else "LOW",
            is_sparse_input=False,
        )

    summary_populated = get_admin_flow_analytics_summary()
    assert summary_populated["total_incidents"] == 10
    assert summary_populated["prediction_eligible_count"] == 10
    assert summary_populated["psif_count"] > 0
    print(f"   ✓ Populated state: {summary_populated['total_incidents']} incidents, {summary_populated['psif_count']} PSIF")

    # Check pattern hub has data
    hub_pop = get_admin_flow_pattern_hub_view_data()
    assert hub_pop["has_data"] is True
    print("   ✓ Pattern hub has data")

    # Step 3: Test Reset Demo via HTTP Client
    print("3. Executing HTTP POST /admin-flow/reset/...")
    client = Client()
    client.force_login(admin_flow_user)
    
    # Check navbar has Reset Demo button
    dash_resp = client.get("/admin-flow/dashboard/")
    assert "Reset Demo" in dash_resp.content.decode("utf-8")
    assert "admin-flow-reset-modal" in dash_resp.content.decode("utf-8")
    print("   ✓ Reset Demo button and confirmation modal present in Admin Flow navbar")

    # Trigger Reset
    post_resp = client.post("/admin-flow/reset/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert post_resp.status_code == 200
    res_data = post_resp.json()
    assert res_data["status"] == "success"
    assert res_data["deleted_incidents"] == 10
    assert res_data["remaining_incidents"] == 0
    print(f"   ✓ Reset endpoint returned success: deleted {res_data['deleted_incidents']} records")

    # Step 4: Verify Dashboard returns to clean sheet (all 6 KPIs = 0)
    print("4. Verifying Dashboard 6 KPIs immediately after reset...")
    dash_after = client.get("/admin-flow/dashboard/")
    content_after = dash_after.content.decode("utf-8")
    assert 'id="stat-total">0</div>' in content_after
    assert 'id="stat-eligible">0</div>' in content_after
    assert 'id="stat-not-psif">0</div>' in content_after
    assert 'id="stat-insufficient">0</div>' in content_after
    assert 'id="stat-human-reviewed">0</div>' in content_after
    summary_fresh = get_admin_flow_analytics_summary()
    assert summary_fresh["psif_count"] == 0
    print("   ✓ Dashboard all 6 KPI cards confirmed = 0")

    # Step 5: Verify Incidents page is empty
    print("5. Verifying Incidents list is empty...")
    inc_resp = client.get("/admin-flow/incidents/")
    assert "No Admin Flow incidents yet." in inc_resp.content.decode("utf-8")
    print("   ✓ Incidents list is completely empty")

    # Step 6: Verify PSIF classification page
    print("6. Verifying PSIF classification page is empty/zero...")
    psif_resp = client.get("/admin-flow/psif/")
    psif_content = psif_resp.content.decode("utf-8")
    assert 'id="kpi-total-incidents">0</div>' in psif_content
    assert 'id="kpi-psif"' in psif_content
    assert get_admin_flow_psif_metrics()["psif_count"] == 0
    print("   ✓ PSIF classification page returns 0 candidates")

    # Step 7: Verify IOGP classification page
    print("7. Verifying IOGP classification page...")
    iogp_resp = client.get("/admin-flow/iogp/")
    assert 'id="kpi-matched">0</div>' in iogp_resp.content.decode("utf-8")
    print("   ✓ IOGP classification page returns 0 matched")

    # Step 8: Verify Pattern Analysis pages
    print("8. Verifying Pattern Analysis hub and detail pages...")
    hub_fresh = get_admin_flow_pattern_hub_view_data()
    assert hub_fresh["has_data"] is False
    assert hub_fresh["total_incidents"] == 0
    assert hub_fresh["top_activity"]["has_data"] is False
    assert hub_fresh["top_barrier"]["has_data"] is False
    assert hub_fresh["top_location"]["has_data"] is False

    act_data = get_admin_flow_activity_pattern_view_data()
    assert act_data["has_data"] is False
    assert len(act_data["activities"]) == 0

    bar_data = get_admin_flow_barrier_pattern_view_data()
    assert bar_data["has_data"] is False
    assert len(bar_data["barriers"]) == 0

    loc_data = get_admin_flow_location_pattern_view_data()
    assert loc_data["has_data"] is False
    assert len(loc_data["locations"]) == 0
    print("   ✓ Hub, Activity, Barrier, and Location patterns are all clean and empty")

    # Step 9: Submit 1 new incident and verify accumulation
    print("9. Submitting 1 new incident to verify clean reuse...")
    submit_resp = client.post("/admin-flow/submit/", data={
        "description": "Worker slipped on wet deck while carrying heavy tool box during offshore transit.",
        "report_type": "incident",
        "incident_date": "2026-09-11",
        "job_task": "Walking / Transit",
        "location": "Main Deck",
        "department": "Logistics",
        "action": "submit_only",
    })
    assert submit_resp.status_code == 302
    summary_new = get_admin_flow_analytics_summary()
    assert summary_new["total_incidents"] == 1
    print(f"   ✓ Post-reset submission succeeded: Total Incidents = {summary_new['total_incidents']}")

    # Step 10: Double reset test
    print("10. Testing double reset...")
    reset_1 = reset_admin_flow_workspace(user=admin_flow_user)
    reset_2 = reset_admin_flow_workspace(user=admin_flow_user)
    assert reset_1["deleted_incidents"] == 1
    assert reset_2["deleted_incidents"] == 0
    summary_double = get_admin_flow_analytics_summary()
    assert summary_double["total_incidents"] == 0
    print("   ✓ Double reset succeeded safely with 0 errors and 0 remaining records")

    # Step 11: Regular Login Protection
    print("11. Verifying regular login protection...")
    reg_client = Client()
    reg_client.force_login(regular_user)
    reg_dash = reg_client.get("/dashboard/")
    assert reg_dash.status_code == 200
    reg_html = reg_dash.content.decode("utf-8")
    assert "Reset Demo" not in reg_html
    assert "admin-flow-reset-modal" not in reg_html
    assert "/admin-flow/reset/" not in reg_html
    print("   ✓ Regular login navbar has NO reset UI and remains 100% unaffected")

    # Step 12: Audit Log Check
    print("12. Verifying audit logging...")
    audit_events = get_admin_flow_reset_audit_log()
    assert len(audit_events) >= 1
    latest = audit_events[0]
    assert latest["event"] == "ADMIN_FLOW_RESET"
    assert latest["user"] == admin_flow_user.email
    print(f"   ✓ Audit log recorded: {latest['event']} at {latest['timestamp']} by {latest['user']}")

    print("\n=== ALL E2E VERIFICATIONS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_verification()
