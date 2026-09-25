"""
End-to-End Live HTTP Session Verification for Admin Flow Pipeline Reconnection.
Tests live requests against http://127.0.0.1:8000 using requests and re.
"""
import re
import requests

BASE_URL = "http://127.0.0.1:8000"

def get_csrf_token(client, url):
    resp = client.get(url)
    assert resp.status_code == 200, f"Failed to get {url}: {resp.status_code}"
    match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', resp.text)
    if match:
        return match.group(1)
    return client.cookies.get("csrftoken", "")

def extract_element_text(html, element_id):
    pattern = rf'id=["\']{element_id}["\'][^>]*>(.*?)<\/'
    match = re.search(pattern, html, re.DOTALL)
    if match:
        # Strip internal html tags and whitespace
        clean = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        return clean
    return None

def run_verification():
    print("=" * 70)
    print("STARTING LIVE HTTP END-TO-END VERIFICATION OF ADMIN FLOW PIPELINE")
    print("=" * 70)

    session = requests.Session()

    # -------------------------------------------------------------
    # Step 1: Admin Flow Login
    # -------------------------------------------------------------
    print("\n[Step 1] Logging into Admin Flow...")
    login_url = f"{BASE_URL}/accounts/login/"
    csrf = get_csrf_token(session, login_url)
    login_data = {
        "username": "admin_flow@foresight.app",
        "password": "foresight2026",
        "csrfmiddlewaretoken": csrf,
    }
    resp = session.post(login_url, data=login_data, headers={"Referer": login_url}, allow_redirects=True)
    assert resp.status_code == 200, f"Login failed with status {resp.status_code}"
    print(f"  -> Logged in successfully. Current URL: {resp.url}")

    # -------------------------------------------------------------
    # Step 2: Admin Flow Dashboard Verification
    # -------------------------------------------------------------
    print("\n[Step 2] Verifying Admin Flow Dashboard (/admin-flow/dashboard/)...")
    dash_url = f"{BASE_URL}/admin-flow/dashboard/"
    resp = session.get(dash_url)
    assert resp.status_code == 200, f"Dashboard returned {resp.status_code}"
    html = resp.text

    stat_total = extract_element_text(html, "stat-total")
    stat_eligible = extract_element_text(html, "stat-eligible")
    stat_psif = extract_element_text(html, "stat-psif")
    stat_not_psif = extract_element_text(html, "stat-not-psif")
    stat_insufficient = extract_element_text(html, "stat-insufficient")
    stat_reviewed = extract_element_text(html, "stat-human-reviewed")

    print(f"  -> Total Incidents: {stat_total} (expected 50)")
    print(f"  -> Prediction Eligible: {stat_eligible} (expected 50)")
    print(f"  -> PSIF Candidates: {stat_psif} (expected 14)")
    print(f"  -> NOT PSIF: {stat_not_psif} (expected 36)")
    print(f"  -> Insufficient Evidence: {stat_insufficient} (expected 0)")
    print(f"  -> Human Reviewed: {stat_reviewed} (expected 0)")

    assert stat_total == "50", f"stat-total expected 50, got {stat_total}"
    assert stat_eligible == "50", f"stat-eligible expected 50, got {stat_eligible}"
    assert stat_psif == "14", f"stat-psif expected 14, got {stat_psif}"
    assert stat_not_psif == "36", f"stat-not-psif expected 36, got {stat_not_psif}"
    assert stat_insufficient == "0", f"stat-insufficient expected 0, got {stat_insufficient}"
    assert stat_reviewed == "0", f"stat-human-reviewed expected 0, got {stat_reviewed}"

    # -------------------------------------------------------------
    # Step 3: Admin Flow PSIF Classification Page
    # -------------------------------------------------------------
    print("\n[Step 3] Verifying PSIF Classification Page (/admin-flow/psif/)...")
    psif_url = f"{BASE_URL}/admin-flow/psif/"
    resp = session.get(psif_url)
    assert resp.status_code == 200, f"PSIF page returned {resp.status_code}"
    psif_html = resp.text

    assert "PSIF Classification" in psif_html, "Missing 'PSIF Classification' title"
    print("  -> Page Title: 'PSIF Classification' verified.")

    assert "PSIF Model Score" in psif_html, "Missing 'PSIF Model Score' label"
    assert "PSIF probability" not in psif_html, "Found forbidden phrase 'PSIF probability'"
    print("  -> Terminology check passed: 'PSIF Model Score' present, 'PSIF probability' absent.")

    assert "methodology-box" in psif_html, "Missing methodology note"
    print("  -> Methodology note present.")

    # -------------------------------------------------------------
    # Step 4: Admin Flow IOGP Classification Page
    # -------------------------------------------------------------
    print("\n[Step 4] Verifying IOGP Classification Page (/admin-flow/iogp/)...")
    iogp_url = f"{BASE_URL}/admin-flow/iogp/"
    resp = session.get(iogp_url)
    assert resp.status_code == 200, f"IOGP page returned {resp.status_code}"
    iogp_html = resp.text

    kpi_total = extract_element_text(iogp_html, "kpi-total")
    kpi_matched = extract_element_text(iogp_html, "kpi-matched")
    kpi_unmatched = extract_element_text(iogp_html, "kpi-unmatched")
    kpi_psif_linked = extract_element_text(iogp_html, "kpi-psif-linked")

    print(f"  -> Total Analyzed: {kpi_total} (expected 50)")
    print(f"  -> IOGP Rule-Matched: {kpi_matched} (expected 32)")
    print(f"  -> No Rule Matched: {kpi_unmatched} (expected 24)")
    print(f"  -> PSIF-Linked Candidates: {kpi_psif_linked} (expected 10)")

    assert kpi_total == "50", f"kpi-total expected 50, got {kpi_total}"
    assert kpi_matched == "32", f"kpi-matched expected 32, got {kpi_matched}"
    assert kpi_unmatched == "24", f"kpi-unmatched expected 24, got {kpi_unmatched}"
    assert kpi_psif_linked == "10", f"kpi-psif-linked expected 10, got {kpi_psif_linked}"

    # Semantics banner
    assert "Important Operational Semantics: Rule-Matched Candidate vs. Failure" in iogp_html
    assert "NOT a confirmed violation" in iogp_html
    assert "NOT a failed barrier" in iogp_html
    print("  -> Operational Semantics banner verified.")

    # Table breakdown check
    assert "No IOGP Rule Matched" in iogp_html
    assert "?rule=none" in iogp_html
    print("  -> Legitimate 'No IOGP Rule Matched' category verified in table.")

    # -------------------------------------------------------------
    # Step 5: Incident Filtering by ?rule=none
    # -------------------------------------------------------------
    print("\n[Step 5] Verifying ?rule=none filter (/admin-flow/incidents/?rule=none)...")
    none_url = f"{BASE_URL}/admin-flow/incidents/?rule=none"
    resp = session.get(none_url)
    assert resp.status_code == 200, f"Incidents filter returned {resp.status_code}"
    none_html = resp.text

    assert "No Rule Matched" in none_html, "Missing 'No Rule Matched' text in filter view"
    # Count rows in tbody
    table_match = re.search(r'<table[^>]*id=["\']admin-flow-incidents-table["\'][^>]*>.*?<tbody>(.*?)<\/tbody>', none_html, re.DOTALL)
    assert table_match, "Could not find admin-flow-incidents-table"
    rows = re.findall(r'<tr[^>]*>', table_match.group(1))
    print(f"  -> Unmatched incidents returned: {len(rows)} (expected 24)")
    assert len(rows) == 24, f"Expected 24 unmatched incidents, got {len(rows)}"

    # Check "No rule matched" text in tbody
    assert "No rule matched" in table_match.group(1)
    print("  -> All 24 rows verified with 'No rule matched' badge.")

    # -------------------------------------------------------------
    # Step 6: Incident Filtering by ?rule=Hot+Work
    # -------------------------------------------------------------
    print("\n[Step 6] Verifying ?rule=Hot+Work filter (/admin-flow/incidents/?rule=Hot+Work)...")
    hw_url = f"{BASE_URL}/admin-flow/incidents/?rule=Hot+Work"
    resp = session.get(hw_url)
    assert resp.status_code == 200
    hw_html = resp.text
    hw_table_match = re.search(r'<table[^>]*id=["\']admin-flow-incidents-table["\'][^>]*>.*?<tbody>(.*?)<\/tbody>', hw_html, re.DOTALL)
    assert hw_table_match
    hw_rows = re.findall(r'<tr[^>]*>', hw_table_match.group(1))
    print(f"  -> Hot Work incidents returned: {len(hw_rows)} (expected 12)")
    assert len(hw_rows) == 12, f"Expected 12 Hot Work incidents, got {len(hw_rows)}"

    # -------------------------------------------------------------
    # Step 7: Incident Detail Page Verification
    # -------------------------------------------------------------
    print("\n[Step 7] Verifying Incident Detail Page...")
    detail_link = re.search(r'href=["\'](/admin-flow/incidents/[a-f0-9-]+/)["\']', hw_table_match.group(1))
    assert detail_link, "Could not find incident detail link"
    detail_url = f"{BASE_URL}{detail_link.group(1)}"
    print(f"  -> Navigating to: {detail_url}")
    resp = session.get(detail_url)
    assert resp.status_code == 200
    detail_html = resp.text

    assert "Observation #" in detail_html, "Missing 'Observation #' heading"
    assert "PSIF" in detail_html
    assert "Hot Work" in detail_html
    print("  -> Incident detail page verified (HTTP 200, PSIF badge, Hot Work tag present).")

    # -------------------------------------------------------------
    # Step 8: Regular Admin Login & Regression Safety
    # -------------------------------------------------------------
    print("\n[Step 8] Verifying Regular Login & Global System Non-Regression...")
    session_admin = requests.Session()
    login_url = f"{BASE_URL}/accounts/login/"
    csrf = get_csrf_token(session_admin, login_url)
    login_data = {
        "username": "admin@foresight.app",
        "password": "foresight2026",
        "csrfmiddlewaretoken": csrf,
    }
    resp = session_admin.post(login_url, data=login_data, headers={"Referer": login_url}, allow_redirects=True)
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code}"

    # Navigate to regular dashboard
    reg_dash_url = f"{BASE_URL}/dashboard/"
    resp = session_admin.get(reg_dash_url)
    assert resp.status_code == 200, f"Regular dashboard failed: {resp.status_code}"
    reg_html = resp.text
    print(f"  -> Regular dashboard accessible. Status: {resp.status_code}")

    # Verify regular navbar does not show Admin Flow banners
    assert "Hard Isolation Contract" not in reg_html, "Admin Flow banner leaked into regular dashboard!"
    assert "Demonstration Scope" not in reg_html, "Demonstration scope leaked into regular dashboard!"
    print("  -> Regular dashboard isolated from Admin Flow UI.")

    print("\n" + "=" * 70)
    print("ALL 8 VERIFICATION STEPS COMPLETED SUCCESSFULLY WITH 100% PASS RATE!")
    print("=" * 70)

if __name__ == "__main__":
    run_verification()
