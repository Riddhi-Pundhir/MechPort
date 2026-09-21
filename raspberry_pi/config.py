"""
MechPort - Centralized Hardware & System Configuration
======================================================
This module holds all configuration values for the MechPort robotic car.
Hardware GPIO pin assignments, network settings, and safety parameters
are centralized here.

IMPORTANT:
- DO NOT guess GPIO pin numbers!
- Verify your physical jumper wire connections between the Raspberry Pi
  and the L298N motor driver before setting the pin numbers.
- Uses BCM (Broadcom) GPIO numbering by default.
"""

import os
from typing import Optional

# Attempt to load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    # Look for .env in current directory or parent directory
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
    load_dotenv()
except ImportError:
    pass


def _get_pin_env(name: str) -> Optional[int]:
    """Helper to parse an integer pin number from environment variables."""
    val = os.getenv(name)
    if val is not None and val.strip() != "":
        try:
            return int(val.strip())
        except ValueError:
            raise ValueError(f"Invalid integer value for pin environment variable {name}: {val}")
    return None


# ==============================================================================
# 1. RASPBERRY PI GPIO PIN ASSIGNMENTS (BCM Numbering)
# ==============================================================================
# Enter your actual BCM pin numbers below, or set them in the .env file.
# Direction pins (IN1-IN4) are REQUIRED for motor operation.
# Speed pins (ENA, ENB) are OPTIONAL if your L298N has the 5V jumpers attached.

# --- Left Motor Channel ---
# ENA: Speed control via PWM (e.g., BCM 12 or 18). Leave None if 5V jumper installed.
PIN_ENA: Optional[int] = _get_pin_env("PIN_ENA") or None

# IN1: Left motor forward direction control pin
PIN_IN1: Optional[int] = _get_pin_env("PIN_IN1") or None

# IN2: Left motor backward direction control pin
PIN_IN2: Optional[int] = _get_pin_env("PIN_IN2") or None


# --- Right Motor Channel ---
# IN3: Right motor forward direction control pin
PIN_IN3: Optional[int] = _get_pin_env("PIN_IN3") or None

# IN4: Right motor backward direction control pin
PIN_IN4: Optional[int] = _get_pin_env("PIN_IN4") or None

# ENB: Speed control via PWM (e.g., BCM 13 or 19). Leave None if 5V jumper installed.
PIN_ENB: Optional[int] = _get_pin_env("PIN_ENB") or None


# ==============================================================================
# 2. MOTOR SAFETY & PERFORMANCE CONFIGURATION
# ==============================================================================
# Safety Watchdog: Duration in seconds without new commands before motors auto-stop
WATCHDOG_TIMEOUT_SECONDS: float = float(os.getenv("WATCHDOG_TIMEOUT_SECONDS", "1.5"))

# PWM Frequency in Hertz (typically 100 Hz to 1000 Hz for L298N)
PWM_FREQUENCY_HZ: int = int(os.getenv("PWM_FREQUENCY_HZ", "100"))

# Default motor speed percentage (0 to 100)
DEFAULT_SPEED: int = int(os.getenv("DEFAULT_SPEED", "80"))

# Force Mock GPIO mode:
# If True, simulates GPIO outputs in console without accessing hardware.
# If False, will attempt to use physical RPi.GPIO (falls back to mock on non-Pi platforms).
ENABLE_MOCK_GPIO: bool = os.getenv("ENABLE_MOCK_GPIO", "False").lower() in ("true", "1", "yes")


# ==============================================================================
# 3. HTTP SERVER & NETWORK CONFIGURATION
# ==============================================================================
# IP address the Raspberry Pi API server binds to (0.0.0.0 binds to all network interfaces)
SERVER_HOST: str = os.getenv("RPI_HOST", "0.0.0.0")

# Port for the Raspberry Pi API server
SERVER_PORT: int = int(os.getenv("RPI_PORT", "5000"))


# ==============================================================================
# 4. CONFIGURATION VALIDATION
# ==============================================================================
class ConfigurationError(Exception):
    """Raised when hardware configuration is invalid or missing required pins."""
    pass


def validate_hardware_config(require_physical: bool = False) -> None:
    """
    Validates that required pin numbers are configured.
    
    Args:
        require_physical: If True, raises ConfigurationError if any required pins
                         are None, regardless of mock settings.
    """
    if ENABLE_MOCK_GPIO and not require_physical:
        return

    missing_pins = []
    if PIN_IN1 is None:
        missing_pins.append("PIN_IN1 (Left Motor Forward)")
    if PIN_IN2 is None:
        missing_pins.append("PIN_IN2 (Left Motor Backward)")
    if PIN_IN3 is None:
        missing_pins.append("PIN_IN3 (Right Motor Forward)")
    if PIN_IN4 is None:
        missing_pins.append("PIN_IN4 (Right Motor Backward)")

    if missing_pins:
        raise ConfigurationError(
            "Hardware pins are unconfigured! The following pins must be assigned:\n"
            + "\n".join(f"  - {pin}" for pin in missing_pins)
            + "\n\nPlease update 'raspberry_pi/config.py' or create a '.env' file "
            "with your physical BCM pin numbers before running on physical hardware.\n"
            "To test without hardware, run in mock mode (ENABLE_MOCK_GPIO = True)."
        )

    # Check for duplicate pin assignments
    configured_pins = {
        "PIN_IN1": PIN_IN1,
        "PIN_IN2": PIN_IN2,
        "PIN_IN3": PIN_IN3,
        "PIN_IN4": PIN_IN4,
    }
    if PIN_ENA is not None:
        configured_pins["PIN_ENA"] = PIN_ENA
    if PIN_ENB is not None:
        configured_pins["PIN_ENB"] = PIN_ENB

    seen = {}
    for name, pin in configured_pins.items():
        if pin in seen:
            raise ConfigurationError(
                f"Duplicate GPIO pin assignment: {name} and {seen[pin]} both use GPIO {pin}!"
            )
        seen[pin] = name
