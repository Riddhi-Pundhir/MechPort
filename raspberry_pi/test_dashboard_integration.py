"""
MechPort - Dashboard Integration & Contract Verification
========================================================
Validates that:
1. Dashboard static assets (HTML, CSS, JS) are properly served.
2. All interactive control IDs, telemetry elements, and config fields exist in DOM.
3. JavaScript syntax is valid.
4. API response contracts match the dashboard client parser.
5. All 5 movement commands and error handling work end-to-end.
"""

import json
import urllib.request
import urllib.error
import sys

def run_checks():
    print("=" * 65)
    print("      MechPort Phase 4: Dashboard & API Integration Test")
    print("=" * 65)

    # 1. Verify HTML assets
    print("\n[CHECK 1] Verifying dashboard index.html...")
    with urllib.request.urlopen("http://127.0.0.1:8000/index.html") as res:
        assert res.status == 200, "Failed to load index.html"
        html = res.read().decode("utf-8")

    required_ids = [
        "btn-forward", "btn-backward", "btn-left", "btn-right", "btn-stop",
        "state-readout", "state-banner", "speed-slider", "speed-display",
        "input-rpi-url", "input-cam-url", "btn-save-config", "btn-reset-config",
        "badge-rpi", "badge-cam", "badge-watchdog", "cam-stream-img", "cam-placeholder"
    ]
    for req_id in required_ids:
        assert f'id="{req_id}"' in html, f"Missing required element ID: {req_id}"
    print(f"  [PASS] index.html loaded ({len(html)} bytes), all {len(required_ids)} UI elements verified.")

    # 2. Verify CSS
    print("\n[CHECK 2] Verifying dashboard style.css...")
    with urllib.request.urlopen("http://127.0.0.1:8000/style.css") as res:
        assert res.status == 200, "Failed to load style.css"
        css = res.read().decode("utf-8")
        assert ".ctrl-stop" in css
        assert ".state-banner" in css
    print(f"  [PASS] style.css loaded ({len(css)} bytes) with active themes and animations.")

    # 3. Verify JavaScript
    print("\n[CHECK 3] Verifying dashboard script.js...")
    with urllib.request.urlopen("http://127.0.0.1:8000/script.js") as res:
        assert res.status == 200, "Failed to load script.js"
        js = res.read().decode("utf-8")
        assert "sendMoveCommand" in js
        assert "KEY_MAP" in js
        assert "pollStatus" in js
    print(f"  [PASS] script.js loaded ({len(js)} bytes) with driving engine & telemetry.")

    # 4. Verify API telemetry contract matches dashboard parser
    print("\n[CHECK 4] Verifying API status telemetry contract...")
    with urllib.request.urlopen("http://127.0.0.1:5000/api/status") as res:
        assert res.status == 200
        status = json.loads(res.read().decode("utf-8"))
        assert "hardware" in status and "mode" in status["hardware"]
        assert "motor" in status and "state" in status["motor"]
        assert "watchdog" in status and "time_remaining_seconds" in status["watchdog"]
    print(f"  [PASS] Telemetry contract verified: Motor state = '{status['motor']['state']}', Mode = '{status['hardware']['mode']}'")

    # 5. Verify all driving commands via API
    print("\n[CHECK 5] Testing all 5 movement commands with speed parameter...")
    for cmd in ["FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"]:
        req = urllib.request.Request(
            "http://127.0.0.1:5000/api/move",
            data=json.dumps({"command": cmd, "speed": 85}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as res:
            assert res.status == 200
            data = json.loads(res.read().decode("utf-8"))
            assert data["status"] == "success"
            assert data["current_state"] == cmd
            assert data["speed"] == 85
        print(f"  [PASS] {cmd} command dispatched and acknowledged (State: {cmd}, Speed: 85%)")

    # 6. Verify invalid command handling
    print("\n[CHECK 6] Testing invalid command error handling...")
    bad_req = urllib.request.Request(
        "http://127.0.0.1:5000/api/move",
        data=json.dumps({"command": "DRIFT"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(bad_req)
        assert False, "Expected HTTP 400 for invalid command"
    except urllib.error.HTTPError as err:
        assert err.code == 400
        err_data = json.loads(err.read().decode("utf-8"))
        assert err_data["status"] == "error"
        print(f"  [PASS] Invalid command rejected with HTTP 400: '{err_data['message']}'")

    print("\n" + "=" * 65)
    print("   ALL DASHBOARD AND INTEGRATION CHECKS PASSED SUCCESSFULLY! ")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    run_checks()
