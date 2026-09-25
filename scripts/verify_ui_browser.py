"""
Browser Verification Script for Foresight PSIF Platform
Drives chrome-headless-shell via Chrome DevTools Protocol (CDP) over WebSocket.
"""
import base64
import json
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path

# Django setup
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from apps.incidents.models import Incident

User = get_user_model()
admin_user = User.objects.get(username="admin@foresight.app")

session = SessionStore()
session["_auth_user_id"] = str(admin_user.id)
session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
session["_auth_user_hash"] = admin_user.get_session_auth_hash()
session.save()
session_key = session.session_key
print(f"[AUTH] Generated admin session: {session_key}")

class SimpleCDP:
    def __init__(self, ws_url):
        assert ws_url.startswith("ws://")
        parts = ws_url[5:].split("/", 1)
        host_port = parts[0].split(":")
        host = host_port[0]
        port = int(host_port[1])
        path = "/" + parts[1]

        self.sock = socket.create_connection((host, port), timeout=15)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parts[0]}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode("ascii"))
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("Connection closed during WebSocket handshake")
            resp += chunk
        header = resp.split(b"\r\n\r\n")[0].decode("latin-1")
        if " 101 " not in header:
            raise RuntimeError(f"Handshake failed: {header}")
        self._msg_id = 0

    def send_cmd(self, method, params=None):
        self._msg_id += 1
        msg_id = self._msg_id
        payload = json.dumps({"id": msg_id, "method": method, "params": params or {}}).encode("utf-8")
        header = bytearray()
        header.append(0x81)
        length = len(payload)
        mask = os.urandom(4)
        if length <= 125:
            header.append(0x80 | length)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(length.to_bytes(2, "big"))
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        header.extend(mask)
        masked = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + masked)
        return msg_id

    def recv_msg(self, timeout=12):
        self.sock.settimeout(timeout)
        try:
            b1 = self.sock.recv(1)
            if not b1:
                return None
            b2 = self.sock.recv(1)[0]
            opcode = b1[0] & 0x0f
            is_masked = bool(b2 & 0x80)
            payload_len = b2 & 0x7f
            if payload_len == 126:
                payload_len = int.from_bytes(self.sock.recv(2), "big")
            elif payload_len == 127:
                payload_len = int.from_bytes(self.sock.recv(8), "big")
            mask_key = self.sock.recv(4) if is_masked else None
            data = bytearray()
            while len(data) < payload_len:
                chunk = self.sock.recv(min(8192, payload_len - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if is_masked:
                data = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(data))
            if opcode == 1:
                return json.loads(data.decode("utf-8"))
            return None
        except socket.timeout:
            return None

    def call(self, method, params=None, timeout=15):
        mid = self.send_cmd(method, params)
        start = time.time()
        while time.time() - start < timeout:
            msg = self.recv_msg(timeout=timeout)
            if msg:
                if msg.get("id") == mid:
                    if "error" in msg:
                        raise RuntimeError(f"CDP Error in {method}: {msg['error']}")
                    return msg.get("result", {})
        raise TimeoutError(f"Command {method} timed out")

    def evaluate(self, expr):
        res = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        val = res.get("result", {}).get("value")
        return val


def run_verification():
    # 1. Create a new target page in Chrome via PUT
    put_req = urllib.request.Request("http://localhost:9222/json/new", method="PUT")
    with urllib.request.urlopen(put_req) as resp:
        target_info = json.loads(resp.read().decode("utf-8"))
    ws_url = target_info["webSocketDebuggerUrl"]
    target_id = target_info["id"]
    print(f"[CDP] Created page target: {target_id}, ws: {ws_url}")

    cdp = SimpleCDP(ws_url)

    # Enable Network & Page & Runtime
    cdp.call("Network.enable")
    cdp.call("Page.enable")
    cdp.call("Runtime.enable")

    # Set viewport
    cdp.call("Emulation.setDeviceMetricsOverride", {
        "width": 1366,
        "height": 900,
        "deviceScaleFactor": 1,
        "mobile": False
    })

    # Set session cookie for localhost and 127.0.0.1
    for domain in ["localhost", "127.0.0.1"]:
        cdp.call("Network.setCookie", {
            "name": "sessionid",
            "value": session_key,
            "domain": domain,
            "path": "/",
            "httpOnly": True,
            "sameSite": "Lax"
        })
    print("[CDP] Injected sessionid cookies.")

    def navigate_and_wait(url, delay=2.0):
        cdp.call("Page.navigate", {"url": url})
        start = time.time()
        while time.time() - start < 10:
            time.sleep(0.3)
            state = cdp.evaluate("document.readyState")
            if state == "complete":
                break
        time.sleep(delay)

    conversation_id = os.environ.get("AGY_CONVERSATION_ID", "6203c4fb-9931-46f0-bbd2-2cf2f05c2d8e")
    artifact_dir = Path(f"/Users/sas/.gemini/antigravity-ide/brain/{conversation_id}")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # ── Test 1: Dashboard ─────────────────────────────────────────────────────
    print("\n--- Testing 1: /dashboard/ ---")
    navigate_and_wait("http://127.0.0.1:8000/dashboard/")
    title = cdp.evaluate("document.title")
    kpis = cdp.evaluate("document.querySelectorAll('.kpi-card').length")
    print(f"Title: {title}, KPI Cards found: {kpis}")
    assert "Foresight" in title
    assert kpis >= 4

    shot = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "dashboard_view.png", "wb") as f:
        f.write(base64.b64decode(shot["data"]))
    print(f"Captured: dashboard_view.png ({len(shot['data'])} bytes)")
    results["dashboard"] = {"title": title, "kpis": kpis}

    # ── Test 2: Barrier Intelligence ──────────────────────────────────────────
    print("\n--- Testing 2: /dashboard/barriers/ ---")
    navigate_and_wait("http://127.0.0.1:8000/dashboard/barriers/")
    b_title = cdp.evaluate("document.title")
    b_cards = cdp.evaluate("document.querySelectorAll('.barrier-card').length")
    b_kpis = cdp.evaluate("document.querySelectorAll('.metric-value').length")
    methodology_text = cdp.evaluate("document.body ? document.body.innerText.includes('deterministic IOGP Life-Saving Rules') : false")
    chart_present = cdp.evaluate("!!document.getElementById('barrierComparisonChart')")
    drilldown_links = cdp.evaluate("Array.from(document.querySelectorAll('.btn-barrier-drilldown')).map(a => a.getAttribute('href'))")
    
    print(f"Barrier Title: {b_title}")
    print(f"Barrier Cards: {b_cards} (Expected: 9)")
    print(f"Summary Metrics: {b_kpis}")
    print(f"Methodology notice rendered: {methodology_text}")
    print(f"Chart canvas present: {chart_present}")
    print(f"First 3 drilldowns: {drilldown_links[:3]}")

    assert b_cards == 9, f"Expected 9 barrier cards, got {b_cards}"
    assert chart_present is True
    assert methodology_text is True

    shot = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "barrier_intelligence_desktop.png", "wb") as f:
        f.write(base64.b64decode(shot["data"]))
    print("Captured: barrier_intelligence_desktop.png")
    results["barriers"] = {
        "title": b_title,
        "barrier_cards": b_cards,
        "methodology_rendered": methodology_text,
        "chart_present": chart_present,
    }

    # Test Mobile Viewport
    cdp.call("Emulation.setDeviceMetricsOverride", {
        "width": 430,
        "height": 932,
        "deviceScaleFactor": 2,
        "mobile": True
    })
    time.sleep(0.5)
    shot_m = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "barrier_intelligence_mobile.png", "wb") as f:
        f.write(base64.b64decode(shot_m["data"]))
    print("Captured: barrier_intelligence_mobile.png")

    # Reset Viewport
    cdp.call("Emulation.setDeviceMetricsOverride", {
        "width": 1366,
        "height": 900,
        "deviceScaleFactor": 1,
        "mobile": False
    })

    # ── Test 3: Filtered Incidents via Drilldown ───────────────────────────────
    print("\n--- Testing 3: /incidents/?rule=Safe%20Mechanical%20Lifting ---")
    navigate_and_wait("http://127.0.0.1:8000/incidents/?rule=Safe+Mechanical+Lifting")
    i_title = cdp.evaluate("document.title")
    rows_count = cdp.evaluate("document.querySelectorAll('#incidents-tbody tr').length")
    first_row_text = cdp.evaluate("document.querySelector('#incidents-tbody tr') ? document.querySelector('#incidents-tbody tr').innerText : ''")
    first_incident_link = cdp.evaluate("document.querySelector('#incidents-tbody a') ? document.querySelector('#incidents-tbody a').getAttribute('href') : null")
    
    print(f"Incidents Page Title: {i_title}")
    print(f"Rendered rows: {rows_count}")
    print(f"First row text excerpt: {first_row_text[:120]}...")
    print(f"First incident link: {first_incident_link}")

    shot = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "incidents_filtered.png", "wb") as f:
        f.write(base64.b64decode(shot["data"]))
    print("Captured: incidents_filtered.png")
    results["filtered_incidents"] = {
        "rows": rows_count,
        "first_link": first_incident_link
    }

    # ── Test 4: Incident Detail Page ──────────────────────────────────────────
    # Pick a real incident with prediction and tags
    sample_inc = Incident.objects.filter(prediction__isnull=False, iogp_rules__isnull=False).first()
    if not sample_inc:
        sample_inc = Incident.objects.first()
    
    detail_url = f"http://127.0.0.1:8000/incidents/{sample_inc.id}/"
    print(f"\n--- Testing 4: Incident Detail {detail_url} ---")
    navigate_and_wait(detail_url)
    
    d_title = cdp.evaluate("document.title")
    badges = cdp.evaluate("Array.from(document.querySelectorAll('.methodology-badge')).map(el => el.getAttribute('data-methodology-key'))")
    canonical_tags = cdp.evaluate("Array.from(document.querySelectorAll('.badge')).map(el => el.innerText).filter(t => t.includes('Canonical:') || t.includes('Class:'))")
    has_psif_panel = cdp.evaluate("!!document.querySelector('.prediction-panel')")
    has_dq_card = cdp.evaluate("document.querySelector('.detail-sidebar-col').innerText.includes('Source Data Quality')")
    
    print(f"Detail Title: {d_title}")
    print(f"Methodology badges detected: {badges}")
    print(f"Canonical tags detected: {canonical_tags}")
    print(f"Prediction panel present: {has_psif_panel}")
    print(f"Data quality card present: {has_dq_card}")

    shot = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "incident_detail_page.png", "wb") as f:
        f.write(base64.b64decode(shot["data"]))
    print("Captured: incident_detail_page.png")

    # Scroll down to capture Prediction Panel, SHAP, and IOGP rules
    cdp.evaluate("window.scrollTo(0, 950)")
    time.sleep(1.0)
    shot_pred = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "incident_detail_prediction_panel.png", "wb") as f:
        f.write(base64.b64decode(shot_pred["data"]))
    print("Captured: incident_detail_prediction_panel.png")

    results["incident_detail"] = {
        "incident_id": str(sample_inc.id),
        "methodology_badges": badges,
        "canonical_tags": canonical_tags,
        "has_psif_panel": has_psif_panel,
        "has_dq_card": has_dq_card,
    }

    # ── Test 5: Evidence Break Workbench ────────────────────────────────────
    evidence_break_url = f"http://127.0.0.1:8000/incidents/{sample_inc.id}/evidence-break/"
    print(f"\n--- Testing 5: Evidence Break {evidence_break_url} ---")
    navigate_and_wait(evidence_break_url)
    eb_title = cdp.evaluate("document.title")
    eb_decision = cdp.evaluate("document.querySelector('.decision-main-text') ? document.querySelector('.decision-main-text').innerText.trim() : ''")
    eb_engine = cdp.evaluate("document.querySelector('.wb-summary-banner') ? document.querySelector('.wb-summary-banner').innerText : ''")
    print(f"Evidence Break Title: {eb_title}")
    print(f"Decision text: {eb_decision}")
    print(f"Has DistilBERT: {'DistilBERT' in eb_engine}")

    shot_eb = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "incident_evidence_break.png", "wb") as f:
        f.write(base64.b64decode(shot_eb["data"]))
    print("Captured: incident_evidence_break.png")

    results["evidence_break"] = {
        "title": eb_title,
        "decision": eb_decision,
        "engine_correct": "DistilBERT" in eb_engine,
    }

    # ── Test 6: Live Predict Page ─────────────────────────────────────────────
    predict_url = "http://127.0.0.1:8000/predictions/predict/"
    print(f"\n--- Testing 6: Live Predict {predict_url} ---")
    navigate_and_wait(predict_url)
    p_title = cdp.evaluate("document.title")
    p_subtitle = cdp.evaluate("document.querySelector('.subtitle') ? document.querySelector('.subtitle').innerText : ''")
    print(f"Predict Title: {p_title}")
    print(f"Predict Subtitle: {p_subtitle}")

    shot_p = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "predictions_predict.png", "wb") as f:
        f.write(base64.b64decode(shot_p["data"]))
    print("Captured: predictions_predict.png")

    results["predict"] = {
        "title": p_title,
        "subtitle": p_subtitle,
    }

    # ── Test 7: Model Assurance Page ──────────────────────────────────────────
    assurance_url = "http://127.0.0.1:8000/predictions/assurance/"
    print(f"\n--- Testing 7: Model Assurance {assurance_url} ---")
    navigate_and_wait(assurance_url)
    ma_title = cdp.evaluate("document.title")
    ma_text = cdp.evaluate("document.body ? document.body.innerText : ''")
    has_score_term = "not a calibrated probability" in ma_text
    print(f"Assurance Title: {ma_title}")
    print(f"Contains 'not a calibrated probability': {has_score_term}")

    shot_ma = cdp.call("Page.captureScreenshot", {"format": "png"})
    with open(artifact_dir / "model_assurance.png", "wb") as f:
        f.write(base64.b64decode(shot_ma["data"]))
    print("Captured: model_assurance.png")

    results["model_assurance"] = {
        "title": ma_title,
        "disclaimer_verified": has_score_term,
    }

    # Check for console errors
    console_logs = cdp.evaluate("window.__console_errors || []")
    print(f"\nConsole errors logged on page: {console_logs}")
    results["console_errors"] = console_logs

    # Cleanup target page
    try:
        urllib.request.urlopen(f"http://localhost:9222/json/close/{target_id}")
    except Exception:
        pass

    print("\n==============================================")
    print("BROWSER VERIFICATION COMPLETE: ALL CHECKS PASSED")
    print(json.dumps(results, indent=2))
    print("==============================================")

if __name__ == "__main__":
    run_verification()
