"""
MechPort - Safe Motor Control Test Script
=========================================
Safely tests the L298N motor controller, all movement directions,
safe startup, emergency stop, and watchdog auto-timeout behavior.

Usage:
  # Automated test suite in mock mode (safe on any laptop):
  python test_motor.py --mock

  # Automated test suite on physical Raspberry Pi:
  python test_motor.py

  # Interactive keyboard test (W/A/S/D/SPACE):
  python test_motor.py --interactive
"""

import argparse
import os
import sys
import time

# Ensure current directory is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    # Handle both direct execution and package import
    from motor_control import MotorController
    from config import (
        WATCHDOG_TIMEOUT_SECONDS,
        ConfigurationError,
        validate_hardware_config,
    )
except ImportError:
    from .motor_control import MotorController
    from .config import (
        WATCHDOG_TIMEOUT_SECONDS,
        ConfigurationError,
        validate_hardware_config,
    )



def print_banner():
    print("=" * 65)
    print("           MechPort Motor Controller Safety Test")
    print("=" * 65)


def run_automated_tests(controller: MotorController):
    """Executes automated sequence to verify all motor primitives and safety watchdog."""
    print("\n[TEST 1] Verifying Safe Initial Startup State...")
    status = controller.get_status()
    print(f"  -> Initial state: {status['state']}")
    assert status["state"] == MotorController.STATE_STOPPED, "ERROR: Controller did not start in STOP state!"
    print("  [PASS] Safe initial startup verified (STOP).")

    time.sleep(0.5)

    print("\n[TEST 2] Testing Movement Primitives (1 second each)...")
    primitives = [
        (MotorController.STATE_FORWARD, "FORWARD"),
        (MotorController.STATE_STOPPED, "STOP"),
        (MotorController.STATE_BACKWARD, "BACKWARD"),
        (MotorController.STATE_STOPPED, "STOP"),
        (MotorController.STATE_LEFT, "LEFT (Pivot)"),
        (MotorController.STATE_STOPPED, "STOP"),
        (MotorController.STATE_RIGHT, "RIGHT (Pivot)"),
        (MotorController.STATE_STOPPED, "STOP"),
    ]

    for cmd, label in primitives:
        print(f"  -> Executing: {label}...")
        controller.execute_command(cmd)
        curr = controller.get_status()["state"]
        print(f"     Status state: {curr}")
        assert curr == cmd, f"ERROR: Expected {cmd}, got {curr}"
        time.sleep(0.8 if cmd != MotorController.STATE_STOPPED else 0.4)

    print("  [PASS] All movement primitives executed successfully.")

    print(f"\n[TEST 3] Testing Safety Watchdog (Timeout: {WATCHDOG_TIMEOUT_SECONDS}s)...")
    print("  -> Sending FORWARD command...")
    controller.forward()
    assert controller.get_status()["state"] == MotorController.STATE_FORWARD

    wait_duration = WATCHDOG_TIMEOUT_SECONDS + 0.6
    print(f"  -> Ceasing all commands and waiting {wait_duration:.2f}s for watchdog trigger...")
    time.sleep(wait_duration)

    status = controller.get_status()
    print(f"  -> State after timeout: {status['state']}")
    print(f"  -> Watchdog expired flag: {status['watchdog_expired']}")
    assert status["state"] == MotorController.STATE_STOPPED, "ERROR: Watchdog failed to stop motors!"
    assert status["watchdog_expired"] is True, "ERROR: Watchdog expired flag was not set!"
    print("  [PASS] Safety watchdog successfully stopped motors on command timeout.")

    print("\n[TEST 4] Testing Safe Cleanup...")
    controller.cleanup()
    assert controller.get_status()["state"] == MotorController.STATE_STOPPED
    print("  [PASS] Cleanup completed safely.")

    print("\n" + "=" * 65)
    print("       ALL SAFETY AND MOVEMENT TESTS PASSED SUCCESSFULLY! ")
    print("=" * 65 + "\n")


def run_interactive(controller: MotorController):
    """Interactive terminal control loop for manual testing."""
    print("\n--- Interactive Terminal Control ---")
    print("Controls:")
    print("  W = FORWARD")
    print("  S = BACKWARD")
    print("  A = LEFT")
    print("  D = RIGHT")
    print("  SPACE / X = STOP")
    print("  Q = QUIT")
    print(f"Watchdog is active ({WATCHDOG_TIMEOUT_SECONDS}s). Keep pressing or car will auto-stop.")
    print("------------------------------------\n")

    try:
        while True:
            cmd = input("Command [W/A/S/D/SPACE/Q]: ").strip().upper()
            if cmd == "W":
                controller.forward()
            elif cmd == "S":
                controller.backward()
            elif cmd == "A":
                controller.left()
            elif cmd == "D":
                controller.right()
            elif cmd in (" ", "X", "STOP"):
                controller.stop("User manual stop")
            elif cmd == "Q":
                print("Exiting interactive test...")
                break
            else:
                print(f"Unrecognized key: {cmd}. Use W, A, S, D, or SPACE.")
            print(f"Current state: {controller.get_status()['state']}")
    finally:
        controller.cleanup()


def main():
    parser = argparse.ArgumentParser(description="MechPort Safe Motor Controller Test")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock GPIO mode (safe dry run without physical hardware)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run interactive keyboard test in terminal instead of automated suite"
    )
    args = parser.parse_args()

    print_banner()

    # If physical test requested, check configuration first
    if not args.mock:
        try:
            validate_hardware_config(require_physical=True)
            print("Physical GPIO pins validated.")
            print("\n*** SAFETY WARNING ***")
            print("Place the robotic car on a stand or block so that all wheels")
            print("can rotate freely in the air WITHOUT touching the ground!")
            input("Press ENTER once the car is safely elevated to proceed...")
        except ConfigurationError as err:
            print(f"\n[CONFIGURATION NOTICE] {err}")
            print("\nAuto-switching to MOCK mode for safe simulation.")
            args.mock = True

    print(f"\nInitializing MotorController (Mode: {'MOCK' if args.mock else 'PHYSICAL'})...")
    controller = MotorController(force_mock=args.mock)

    if args.interactive:
        run_interactive(controller)
    else:
        run_automated_tests(controller)


if __name__ == "__main__":
    main()
