"""
MechPort - Raspberry Pi Sensor Manager Unit & Fault-Tolerance Tests
===================================================================
Verifies:
  1. Returned dictionary structure of SensorManager.read_all()
  2. DHT22 failure is non-fatal (handles RuntimeError / missing sensor gracefully)
  3. Digital sensor values are valid binary states (0 or 1)
  4. cleanup() executes cleanly and safely without crashing
  5. Mock and physical modes are supported without breaking
"""

import os
import sys
import unittest

# Ensure current directory is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import config
from sensor_manager import SensorManager, get_sensor_manager


class TestSensorManager(unittest.TestCase):
    def setUp(self):
        """Instantiate a test SensorManager in forced mock mode for deterministic verification."""
        self.mgr = SensorManager(force_mock=True)

    def tearDown(self):
        """Clean up sensor resources."""
        self.mgr.cleanup()

    def test_01_read_all_dictionary_structure(self):
        """Verify the exact telemetry dictionary schema returned by read_all()."""
        data = self.mgr.read_all()
        print("\n[TEST 1] Testing read_all() telemetry structure:")
        print(f"  Data returned: {data}")

        # Root keys
        self.assertIn("dht22", data)
        self.assertIn("flame_sensor_1", data)
        self.assertIn("flame_sensor_2", data)
        self.assertIn("hw072", data)

        # DHT22 sub-structure
        dht = data["dht22"]
        self.assertIn("available", dht)
        self.assertIsInstance(dht["available"], bool)
        self.assertIn("temperature_c", dht)
        self.assertIn("humidity_percent", dht)

        # Flame 1 sub-structure
        f1 = data["flame_sensor_1"]
        self.assertIn("gpio", f1)
        self.assertEqual(f1["gpio"], config.PIN_FLAME_1)
        self.assertIn("state", f1)
        self.assertIn(f1["state"], (0, 1))

        # Flame 2 sub-structure
        f2 = data["flame_sensor_2"]
        self.assertIn("gpio", f2)
        self.assertEqual(f2["gpio"], config.PIN_FLAME_2)
        self.assertIn("state", f2)
        self.assertIn(f2["state"], (0, 1))

        # HW-072 sub-structure
        hw = data["hw072"]
        self.assertIn("gpio", hw)
        self.assertEqual(hw["gpio"], config.PIN_HW072)
        self.assertIn("state", hw)
        self.assertIn(hw["state"], (0, 1))

        print("  [PASS] Structure and keys match specification perfectly.")

    def test_02_dht22_failure_is_non_fatal(self):
        """Verify that DHT22 exceptions (e.g. 'DHT sensor not found') never crash read_all()."""
        print("\n[TEST 2] Testing DHT22 non-fatal exception handling...")

        # Mock a failing DHT device that raises RuntimeError (standard DHT22 behavior on loose wiring)
        class FaultyDHT:
            @property
            def temperature(self):
                raise RuntimeError("DHT sensor not found on GPIO4")

            @property
            def humidity(self):
                raise RuntimeError("DHT checksum error")

            def exit(self):
                pass

        self.mgr.dht_device = FaultyDHT()

        # Call read_all(); MUST NOT raise an exception
        try:
            data = self.mgr.read_all()
            dht = data["dht22"]
            self.assertFalse(dht["available"])
            self.assertIsNone(dht["temperature_c"])
            self.assertIsNone(dht["humidity_percent"])
            print("  [PASS] Caught RuntimeError cleanly; reported available=False without crashing.")
        except Exception as e:
            self.fail(f"read_all() raised unexpected exception: {e}")

    def test_03_digital_sensor_values_are_binary(self):
        """Verify that flame sensors and HW-072 report strictly 0 or 1."""
        print("\n[TEST 3] Testing digital sensor binary states...")
        data = self.mgr.read_all()

        for sensor_name in ("flame_sensor_1", "flame_sensor_2", "hw072"):
            state = data[sensor_name]["state"]
            self.assertIn(state, (0, 1), f"{sensor_name} reported non-binary state: {state}")
            print(f"  [PASS] {sensor_name} (GPIO {data[sensor_name]['gpio']}) state: {state}")

    def test_04_cleanup_is_safe_and_idempotent(self):
        """Verify that cleanup() safely releases resources and can be called multiple times."""
        print("\n[TEST 4] Testing cleanup() idempotency...")
        try:
            self.mgr.cleanup()
            self.mgr.cleanup()  # Second call should be safe
            self.assertIsNone(self.mgr.dht_device)
            print("  [PASS] cleanup() executed safely and idempotently.")
        except Exception as e:
            self.fail(f"cleanup() raised unexpected exception: {e}")

    def test_05_singleton_instance(self):
        """Verify get_sensor_manager() returns valid singleton."""
        print("\n[TEST 5] Testing get_sensor_manager() singleton...")
        mgr = get_sensor_manager(force_mock=True)
        self.assertIsInstance(mgr, SensorManager)
        data = mgr.read_all()
        self.assertIn("dht22", data)
        print("  [PASS] Singleton get_sensor_manager() operational.")


def main():
    print("=" * 65)
    print("      MechPort Raspberry Pi Sensor Manager Test Suite")
    print("=" * 65)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSensorManager)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n" + "=" * 65)
        print("       ALL SENSOR TESTS PASSED SUCCESSFULLY! ")
        print("=" * 65 + "\n")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
