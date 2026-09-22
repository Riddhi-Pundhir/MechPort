"""
MechPort - Raspberry Pi Sensor Manager
======================================
Interfaces with environmental and safety sensors:
  - DHT22 Temperature & Humidity sensor (BCM GPIO 4 / board.D4)
  - Flame Sensor 1 (BCM GPIO 24)
  - Flame Sensor 2 (BCM GPIO 25)
  - HW-072 Vibration/Digital Sensor (BCM GPIO 5)

Safety & Fault Tolerance:
  - DHT22 initialization and read exceptions are caught and reported as unavailable
    without interrupting the server or crashing the process.
  - Sensor failures are non-fatal.
  - Transparent mock fallback for non-Raspberry Pi / development platforms.
  - Clean resource release on shutdown via cleanup().
"""

import logging
import threading
from typing import Any, Dict, Optional

try:
    import config
except ImportError:
    from . import config

logger = logging.getLogger("MechPort.Sensors")

# ==============================================================================
# HARDWARE / MOCK ADAPTERS
# ==============================================================================
HAS_HARDWARE = False
board = None
adafruit_dht = None
GPIO = None

if not config.ENABLE_MOCK_GPIO:
    try:
        import RPi.GPIO as RealGPIO
        GPIO = RealGPIO
        HAS_HARDWARE = True
    except (ImportError, RuntimeError):
        pass

    try:
        import board as real_board
        import adafruit_dht as real_adafruit_dht
        board = real_board
        adafruit_dht = real_adafruit_dht
    except (ImportError, RuntimeError, NotImplementedError):
        pass


class SensorManager:
    """
    Thread-safe manager for environmental and safety sensors.
    Guarantees non-fatal failure handling and zero server crashes.
    """

    def __init__(self, force_mock: Optional[bool] = None):
        self._lock = threading.Lock()
        self.is_mock = force_mock if force_mock is not None else (config.ENABLE_MOCK_GPIO or not HAS_HARDWARE)
        self.dht_device = None
        self._initialized = False

        # Pin assignments from configuration
        self.pin_dht22 = config.PIN_DHT22          # BCM 4
        self.pin_flame1 = config.PIN_FLAME_1        # BCM 24
        self.pin_flame2 = config.PIN_FLAME_2        # BCM 25
        self.pin_hw072 = config.PIN_HW072          # BCM 5

        # Initialize hardware/mock
        self._setup_sensors()

    def _setup_sensors(self):
        """Initializes GPIO inputs and DHT22 instance safely."""
        with self._lock:
            # 1. Setup Digital Inputs (Flame 1, Flame 2, HW-072)
            if not self.is_mock and GPIO is not None:
                try:
                    GPIO.setmode(GPIO.BCM)
                    GPIO.setup(self.pin_flame1, GPIO.IN)
                    GPIO.setup(self.pin_flame2, GPIO.IN)
                    GPIO.setup(self.pin_hw072, GPIO.IN)
                    logger.info(
                        "Digital inputs initialized on BCM GPIO %s (Flame 1), %s (Flame 2), %s (HW-072).",
                        self.pin_flame1,
                        self.pin_flame2,
                        self.pin_hw072,
                    )
                except Exception as err:
                    logger.warning("Failed to initialize digital GPIO pins (%s). Falling back to mock inputs.", err)
                    self.is_mock = True

            # 2. Setup DHT22 Sensor on board.D4
            # Failure is non-fatal: if DHT22 is missing or throws error, report unavailable
            if not self.is_mock and adafruit_dht is not None and board is not None:
                try:
                    # Initialize DHT22 on board.D4 using use_pulseio=False per specifications
                    self.dht_device = adafruit_dht.DHT22(board.D4, use_pulseio=False)
                    logger.info("DHT22 sensor initialized on board.D4 (use_pulseio=False).")
                except Exception as err:
                    logger.warning(
                        "DHT22 initialization exception on board.D4 (non-fatal): %s. Reporting DHT22 unavailable.",
                        err,
                    )
                    self.dht_device = None
            else:
                logger.info("DHT22 hardware driver not loaded (Mode: %s).", "MOCK" if self.is_mock else "UNAVAILABLE")
                self.dht_device = None

            self._initialized = True

    def read_dht22(self) -> Dict[str, Any]:
        """
        Reads temperature and humidity from DHT22.
        Catches RuntimeError and Exception safely, reporting available=False on failure.
        """
        result = {
            "available": False,
            "temperature_c": None,
            "humidity_percent": None,
        }

        if self.dht_device is None:
            return result

        try:
            # DHT sensors require reading within try block; transient checksum/timeout errors are standard
            temp = self.dht_device.temperature
            hum = self.dht_device.humidity

            if temp is not None and hum is not None:
                result["available"] = True
                result["temperature_c"] = round(float(temp), 1)
                result["humidity_percent"] = round(float(hum), 1)
        except (RuntimeError, Exception) as err:
            # Non-fatal error: DHT sensor reading failed or sensor not found
            logger.debug("DHT22 read exception (non-fatal): %s", err)
            result["available"] = False
            result["temperature_c"] = None
            result["humidity_percent"] = None

        return result

    def _read_digital_pin(self, pin: int, default_val: int = 1) -> int:
        """Reads digital input pin safely returning 0 or 1."""
        if not self.is_mock and GPIO is not None:
            try:
                val = GPIO.input(pin)
                return 1 if val else 0
            except Exception as err:
                logger.debug("Error reading GPIO %s: %s", pin, err)
                return default_val
        # Mock mode returns default valid binary state (0 or 1)
        return default_val

    def read_all(self) -> Dict[str, Any]:
        """
        Returns full sensor telemetry dictionary:
          - dht22: availability, temperature (°C), humidity (%)
          - flame_sensor_1: gpio, state (0 or 1)
          - flame_sensor_2: gpio, state (0 or 1)
          - hw072: gpio, state (0 or 1)
        """
        with self._lock:
            dht_data = self.read_dht22()
            flame1_state = self._read_digital_pin(self.pin_flame1, default_val=1)
            flame2_state = self._read_digital_pin(self.pin_flame2, default_val=1)
            hw072_state = self._read_digital_pin(self.pin_hw072, default_val=0)

            return {
                "dht22": dht_data,
                "flame_sensor_1": {
                    "gpio": self.pin_flame1,
                    "state": flame1_state,
                },
                "flame_sensor_2": {
                    "gpio": self.pin_flame2,
                    "state": flame2_state,
                },
                "hw072": {
                    "gpio": self.pin_hw072,
                    "state": hw072_state,
                },
            }

    def cleanup(self):
        """Releases sensor resources and closes DHT device safely."""
        with self._lock:
            if self.dht_device is not None:
                try:
                    self.dht_device.exit()
                    logger.info("DHT22 driver exited cleanly.")
                except Exception as err:
                    logger.debug("Exception during DHT exit: %s", err)
                self.dht_device = None

            # Clean up digital sensor pins specifically without affecting motor pins if separate
            if not self.is_mock and GPIO is not None:
                try:
                    GPIO.cleanup([self.pin_flame1, self.pin_flame2, self.pin_hw072])
                    logger.info("Sensor GPIO pins released.")
                except Exception as err:
                    logger.debug("Exception during sensor GPIO cleanup: %s", err)


# Global singleton instance
_sensor_manager_instance: Optional[SensorManager] = None


def get_sensor_manager(force_mock: Optional[bool] = None) -> SensorManager:
    """Returns the global SensorManager singleton instance."""
    global _sensor_manager_instance
    if _sensor_manager_instance is None:
        _sensor_manager_instance = SensorManager(force_mock=force_mock)
    return _sensor_manager_instance
