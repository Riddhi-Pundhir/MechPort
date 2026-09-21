"""
MechPort - HTTP API Server Test Suite
=====================================
Tests all REST API endpoints, validation logic, safety watchdog,
and graceful shutdown in MOCK mode.

Usage:
  python test_api.py
"""

import json
import os
import sys
import time
import unittest

# Ensure current directory is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Force Mock GPIO for testing
os.environ["ENABLE_MOCK_GPIO"] = "True"

import config
config.ENABLE_MOCK_GPIO = True

from server import app, get_controller
from motor_control import MotorController


class TestMechPortAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up Flask test client and ensure mock controller."""
        cls.client = app.test_client()
        cls.controller = get_controller()

    def setUp(self):
        """Ensure controller is active and stopped before each test."""
        self.controller._is_active = True
        self.controller.stop(reason="Test setup")


    def test_01_get_status_initial_safe_state(self):
        """Verify GET /api/status returns 200, online status, and initial STOP state."""
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertIn("server", data)
        self.assertEqual(data["server"]["status"], "online")
        self.assertIn("motor", data)
        self.assertEqual(data["motor"]["state"], "STOP")
        self.assertIn("watchdog", data)
        self.assertEqual(data["watchdog"]["timeout_seconds"], config.WATCHDOG_TIMEOUT_SECONDS)
        self.assertIn("hardware", data)
        self.assertEqual(data["hardware"]["mode"], "MOCK")
        self.assertTrue(data["hardware"]["is_mock"])
        print("\n[TEST 1 PASSED] GET /api/status verified initial state (STOP, MOCK mode).")

    def test_02_move_forward(self):
        """Verify POST /api/move FORWARD works."""
        response = self.client.post(
            "/api/move",
            data=json.dumps({"command": "FORWARD"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["current_state"], "FORWARD")
        self.assertEqual(self.controller.current_state, "FORWARD")
        print("\n[TEST 2 PASSED] POST /api/move FORWARD verified.")

    def test_03_move_backward(self):
        """Verify POST /api/move BACKWARD works."""
        response = self.client.post(
            "/api/move",
            data=json.dumps({"command": "BACKWARD"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["current_state"], "BACKWARD")
        self.assertEqual(self.controller.current_state, "BACKWARD")
        print("\n[TEST 3 PASSED] POST /api/move BACKWARD verified.")

    def test_04_move_left(self):
        """Verify POST /api/move LEFT works."""
        response = self.client.post(
            "/api/move",
            data=json.dumps({"command": "LEFT"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["current_state"], "LEFT")
        self.assertEqual(self.controller.current_state, "LEFT")
        print("\n[TEST 4 PASSED] POST /api/move LEFT verified.")

    def test_05_move_right(self):
        """Verify POST /api/move RIGHT works."""
        response = self.client.post(
            "/api/move",
            data=json.dumps({"command": "RIGHT"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["current_state"], "RIGHT")
        self.assertEqual(self.controller.current_state, "RIGHT")
        print("\n[TEST 5 PASSED] POST /api/move RIGHT verified.")

    def test_06_move_stop(self):
        """Verify POST /api/move STOP works."""
        # First set to forward
        self.controller.forward()
        self.assertEqual(self.controller.current_state, "FORWARD")

        response = self.client.post(
            "/api/move",
            data=json.dumps({"command": "STOP"}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["current_state"], "STOP")
        self.assertEqual(self.controller.current_state, "STOP")
        print("\n[TEST 6 PASSED] POST /api/move STOP verified.")

    def test_07_invalid_command_returns_400(self):
        """Verify invalid commands return HTTP 400."""
        invalid_commands = ["FLY", "JUMP", "DRIFT", "", "123"]
        for bad_cmd in invalid_commands:
            response = self.client.post(
                "/api/move",
                data=json.dumps({"command": bad_cmd}),
                content_type="application/json"
            )
            self.assertEqual(response.status_code, 400)
            data = response.get_json()
            self.assertEqual(data["status"], "error")
            self.assertTrue(
                "Invalid command" in data["message"] or "Missing required field" in data["message"]
            )
        print("\n[TEST 7 PASSED] Invalid command rejection (HTTP 400) verified.")


    def test_08_malformed_requests_return_400(self):
        """Verify non-JSON and empty payloads return HTTP 400."""
        # Missing Content-Type
        resp1 = self.client.post("/api/move", data="plain text")
        self.assertEqual(resp1.status_code, 400)

        # Missing 'command' field
        resp2 = self.client.post(
            "/api/move",
            data=json.dumps({"speed": 50}),
            content_type="application/json"
        )
        self.assertEqual(resp2.status_code, 400)
        print("\n[TEST 8 PASSED] Malformed requests and missing fields rejected (HTTP 400).")

    def test_09_watchdog_auto_stop_via_api(self):
        """Verify that silence causes the watchdog to auto-stop the vehicle."""
        print(f"\n[TEST 9] Testing Safety Watchdog via API (timeout: {config.WATCHDOG_TIMEOUT_SECONDS}s)...")
        # Send forward command
        resp = self.client.post(
            "/api/move",
            data=json.dumps({"command": "FORWARD"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.controller.current_state, "FORWARD")

        # Wait for watchdog to trigger (timeout + buffer)
        wait_time = config.WATCHDOG_TIMEOUT_SECONDS + 0.6
        print(f"  Waiting {wait_time:.2f}s for watchdog timeout...")
        time.sleep(wait_time)

        # Poll GET /api/status
        status_resp = self.client.get("/api/status")
        self.assertEqual(status_resp.status_code, 200)
        data = status_resp.get_json()
        self.assertEqual(data["motor"]["state"], "STOP")
        self.assertTrue(data["watchdog"]["expired"])
        print("  [TEST 9 PASSED] Safety watchdog successfully stopped vehicle and updated /api/status.")

    def test_10_cors_headers_present(self):
        """Verify CORS header Access-Control-Allow-Origin is configured."""
        resp = self.client.get("/api/status")
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
        print("\n[TEST 10 PASSED] CORS headers verified.")

    def test_11_graceful_shutdown(self):
        """Verify POST /api/shutdown stops motors and cleans up."""
        resp = self.client.post("/api/shutdown")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(self.controller.current_state, "STOP")
        print("\n[TEST 11 PASSED] Graceful shutdown endpoint verified.")


def run_all_tests():
    print("=" * 65)
    print("         MechPort Phase 3: HTTP API Server Test Suite")
    print("=" * 65)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMechPortAPI)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n" + "=" * 65)
        print("     ALL 11 API SERVER TESTS PASSED IN MOCK MODE! ")
        print("=" * 65 + "\n")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
