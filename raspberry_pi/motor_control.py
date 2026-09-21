"""
MechPort - Motor Control Module (L298N Dual H-Bridge Driver)
============================================================
Provides safe motor primitives, differential steering, PWM speed control,
automatic watchdog timer, and graceful shutdown handling.

Safety Guarantees:
1. Safe Initial State: Motors are immediately set to STOP on startup.
2. Watchdog Protection: An active background watchdog auto-stops motors if no
   command is received within WATCHDOG_TIMEOUT_SECONDS.
3. Safe Shutdown: Registers atexit and signal handlers (SIGINT, SIGTERM) to
   ensure motors stop and GPIO pins are cleaned up on exit.
4. Mock Fallback: Allows testing on PC/Mac/laptop without physical hardware.
"""

import atexit
import logging
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional

# Import centralized configuration
try:
    import config
except ImportError:
    from . import config


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MotorControl] %(message)s",
)
logger = logging.getLogger("MechPort.MotorControl")


# ==============================================================================
# MOCK GPIO ADAPTER (For safe testing on non-Raspberry Pi devices or dry runs)
# ==============================================================================
class MockPWM:
    """Mock PWM object simulating RPi.GPIO.PWM."""
    def __init__(self, pin: int, freq: int):
        self.pin = pin
        self.freq = freq
        self.duty_cycle = 0
        self.running = False
        logger.info("[MockGPIO] PWM initialized on Pin %s at %s Hz", pin, freq)

    def start(self, duty_cycle: float):
        self.running = True
        self.duty_cycle = duty_cycle
        logger.info("[MockGPIO] PWM started on Pin %s with duty cycle %s%%", self.pin, duty_cycle)

    def ChangeDutyCycle(self, duty_cycle: float):
        self.duty_cycle = duty_cycle
        logger.debug("[MockGPIO] PWM Pin %s duty cycle changed to %s%%", self.pin, duty_cycle)

    def stop(self):
        self.running = False
        logger.info("[MockGPIO] PWM stopped on Pin %s", self.pin)


class MockGPIO:
    """Mock RPi.GPIO module that logs pin operations."""
    BCM = "BCM"
    OUT = "OUT"
    IN = "IN"
    HIGH = 1
    LOW = 0

    @classmethod
    def setmode(cls, mode):
        logger.info("[MockGPIO] GPIO Mode set to %s", mode)

    @classmethod
    def setwarnings(cls, flag):
        pass

    @classmethod
    def setup(cls, pin, mode, initial=0):
        logger.info("[MockGPIO] Pin %s configured as %s (Initial: %s)", pin, mode, initial)

    @classmethod
    def output(cls, pin, state):
        state_str = "HIGH (1)" if state == cls.HIGH else "LOW (0)"
        logger.info("[MockGPIO] Pin %s -> %s", pin, state_str)

    @classmethod
    def PWM(cls, pin, freq):
        return MockPWM(pin, freq)

    @classmethod
    def cleanup(cls):
        logger.info("[MockGPIO] GPIO cleanup executed")


# ==============================================================================
# GPIO SELECTION: REAL VS MOCK
# ==============================================================================
GPIO = None
IS_MOCK_MODE = False

if config.ENABLE_MOCK_GPIO:
    logger.info("Mock GPIO explicitly enabled in configuration.")
    GPIO = MockGPIO
    IS_MOCK_MODE = True
else:
    try:
        import RPi.GPIO as RealGPIO
        GPIO = RealGPIO
        IS_MOCK_MODE = False
        logger.info("Physical RPi.GPIO successfully loaded.")
    except (ImportError, RuntimeError) as err:
        logger.warning("Physical RPi.GPIO unavailable (%s). Falling back to Mock GPIO.", err)
        GPIO = MockGPIO
        IS_MOCK_MODE = True


# ==============================================================================
# MOTOR CONTROLLER CLASS
# ==============================================================================
class MotorController:
    """
    Thread-safe controller for the L298N Dual H-Bridge Motor Driver.
    
    Commands:
        - FORWARD
        - BACKWARD
        - LEFT (differential pivot)
        - RIGHT (differential pivot)
        - STOP
    """

    STATE_STOPPED = "STOP"
    STATE_FORWARD = "FORWARD"
    STATE_BACKWARD = "BACKWARD"
    STATE_LEFT = "LEFT"
    STATE_RIGHT = "RIGHT"

    def __init__(self, force_mock: Optional[bool] = None):
        global GPIO, IS_MOCK_MODE

        self._lock = threading.Lock()
        self._is_active = True
        self.current_state = self.STATE_STOPPED
        self.current_speed = config.DEFAULT_SPEED
        self.last_command_time = time.time()
        self.watchdog_expired = False

        if force_mock is not None:
            if force_mock:
                GPIO = MockGPIO
                IS_MOCK_MODE = True
            else:
                import RPi.GPIO as RealGPIO
                GPIO = RealGPIO
                IS_MOCK_MODE = False

        self.is_mock = IS_MOCK_MODE

        # Validate configuration before touching pins
        if not self.is_mock:
            config.validate_hardware_config(require_physical=True)

        self._pwm_left = None
        self._pwm_right = None

        # Initialize hardware safely
        self._setup_gpio()

        # Guarantee safe stop state
        self.stop(reason="Initial startup safe state")

        # Register cleanup handlers for safe exit
        atexit.register(self.cleanup)
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError):
            # Signal handling might be restricted in non-main threads
            pass

        # Start background watchdog monitor
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name="MotorSafetyWatchdog",
            daemon=True
        )
        self._watchdog_thread.start()
        logger.info(
            "MotorController initialized successfully. Watchdog timeout: %ss. Mode: %s.",
            config.WATCHDOG_TIMEOUT_SECONDS,
            "MOCK" if self.is_mock else "PHYSICAL"
        )

    def _setup_gpio(self):
        """Initializes GPIO pins and PWM instances."""
        with self._lock:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            # Use mock dummy pins if in mock mode and pins are not assigned
            self.pin_in1 = config.PIN_IN1 if config.PIN_IN1 is not None else 17
            self.pin_in2 = config.PIN_IN2 if config.PIN_IN2 is not None else 27
            self.pin_in3 = config.PIN_IN3 if config.PIN_IN3 is not None else 22
            self.pin_in4 = config.PIN_IN4 if config.PIN_IN4 is not None else 23
            self.pin_ena = config.PIN_ENA
            self.pin_enb = config.PIN_ENB

            # Setup direction pins as OUTPUT with initial state LOW
            for pin in (self.pin_in1, self.pin_in2, self.pin_in3, self.pin_in4):
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

            # Setup PWM speed pins if configured
            if self.pin_ena is not None:
                GPIO.setup(self.pin_ena, GPIO.OUT)
                self._pwm_left = GPIO.PWM(self.pin_ena, config.PWM_FREQUENCY_HZ)
                self._pwm_left.start(0)

            if self.pin_enb is not None:
                GPIO.setup(self.pin_enb, GPIO.OUT)
                self._pwm_right = GPIO.PWM(self.pin_enb, config.PWM_FREQUENCY_HZ)
                self._pwm_right.start(0)

    def _set_motor_pins(self, in1: int, in2: int, in3: int, in4: int):
        """Low-level helper to write direction pin values."""
        GPIO.output(self.pin_in1, in1)
        GPIO.output(self.pin_in2, in2)
        GPIO.output(self.pin_in3, in3)
        GPIO.output(self.pin_in4, in4)

    def _apply_speed(self, speed: Optional[int]):
        """Sets PWM duty cycle for speed control if PWM pins are connected."""
        if speed is None:
            speed = self.current_speed
        else:
            speed = max(0, min(100, int(speed)))
            self.current_speed = speed

        if self._pwm_left is not None:
            self._pwm_left.ChangeDutyCycle(speed)
        if self._pwm_right is not None:
            self._pwm_right.ChangeDutyCycle(speed)

    def forward(self, speed: Optional[int] = None):
        """Moves both left and right wheels forward."""
        with self._lock:
            if not self._is_active:
                logger.warning("Cannot move: MotorController has been shut down.")
                return

            self._apply_speed(speed)
            # Left forward: IN1=HIGH, IN2=LOW | Right forward: IN3=HIGH, IN4=LOW
            self._set_motor_pins(GPIO.HIGH, GPIO.LOW, GPIO.HIGH, GPIO.LOW)
            self.current_state = self.STATE_FORWARD
            self.last_command_time = time.time()
            self.watchdog_expired = False
            logger.info("Command executed: FORWARD (Speed: %s%%)", self.current_speed)

    def backward(self, speed: Optional[int] = None):
        """Moves both left and right wheels backward."""
        with self._lock:
            if not self._is_active:
                logger.warning("Cannot move: MotorController has been shut down.")
                return

            self._apply_speed(speed)
            # Left backward: IN1=LOW, IN2=HIGH | Right backward: IN3=LOW, IN4=HIGH
            self._set_motor_pins(GPIO.LOW, GPIO.HIGH, GPIO.LOW, GPIO.HIGH)
            self.current_state = self.STATE_BACKWARD
            self.last_command_time = time.time()
            self.watchdog_expired = False
            logger.info("Command executed: BACKWARD (Speed: %s%%)", self.current_speed)

    def left(self, speed: Optional[int] = None):
        """Differential turn LEFT: Left motor backward, Right motor forward."""
        with self._lock:
            if not self._is_active:
                logger.warning("Cannot move: MotorController has been shut down.")
                return

            self._apply_speed(speed)
            # Left backward: IN1=LOW, IN2=HIGH | Right forward: IN3=HIGH, IN4=LOW
            self._set_motor_pins(GPIO.LOW, GPIO.HIGH, GPIO.HIGH, GPIO.LOW)
            self.current_state = self.STATE_LEFT
            self.last_command_time = time.time()
            self.watchdog_expired = False
            logger.info("Command executed: LEFT (Speed: %s%%)", self.current_speed)

    def right(self, speed: Optional[int] = None):
        """Differential turn RIGHT: Left motor forward, Right motor backward."""
        with self._lock:
            if not self._is_active:
                logger.warning("Cannot move: MotorController has been shut down.")
                return

            self._apply_speed(speed)
            # Left forward: IN1=HIGH, IN2=LOW | Right backward: IN3=LOW, IN4=HIGH
            self._set_motor_pins(GPIO.HIGH, GPIO.LOW, GPIO.LOW, GPIO.HIGH)
            self.current_state = self.STATE_RIGHT
            self.last_command_time = time.time()
            self.watchdog_expired = False
            logger.info("Command executed: RIGHT (Speed: %s%%)", self.current_speed)

    def stop(self, reason: str = "User stop"):
        """
        Immediately stops all motor motion.
        All direction pins driven LOW, PWM set to 0.
        """
        with self._lock:
            # Set all direction pins LOW
            self._set_motor_pins(GPIO.LOW, GPIO.LOW, GPIO.LOW, GPIO.LOW)

            # Set PWM output to 0 duty cycle
            if self._pwm_left is not None:
                self._pwm_left.ChangeDutyCycle(0)
            if self._pwm_right is not None:
                self._pwm_right.ChangeDutyCycle(0)

            self.current_state = self.STATE_STOPPED
            self.last_command_time = time.time()
            logger.info("Command executed: STOP (%s)", reason)

    def execute_command(self, command: str, speed: Optional[int] = None) -> bool:
        """
        Dispatches command string to corresponding motor action.
        
        Supported commands:
            FORWARD, BACKWARD, LEFT, RIGHT, STOP
            
        Returns:
            True if command recognized and executed, False otherwise.
        """
        cmd = str(command).strip().upper()
        if cmd == self.STATE_FORWARD:
            self.forward(speed)
            return True
        elif cmd == self.STATE_BACKWARD:
            self.backward(speed)
            return True
        elif cmd == self.STATE_LEFT:
            self.left(speed)
            return True
        elif cmd == self.STATE_RIGHT:
            self.right(speed)
            return True
        elif cmd == self.STATE_STOPPED:
            self.stop("Manual STOP command")
            return True
        else:
            logger.warning("Unknown motor command received: '%s'", command)
            return False

    def get_status(self) -> Dict[str, Any]:
        """Returns current operational status and telemetry."""
        with self._lock:
            elapsed = time.time() - self.last_command_time
            time_remaining = max(0.0, config.WATCHDOG_TIMEOUT_SECONDS - elapsed)

            return {
                "state": self.current_state,
                "speed": self.current_speed,
                "is_mock": self.is_mock,
                "watchdog_timeout_sec": config.WATCHDOG_TIMEOUT_SECONDS,
                "watchdog_time_remaining_sec": round(time_remaining, 2),
                "watchdog_expired": self.watchdog_expired,
                "pins": {
                    "in1": self.pin_in1,
                    "in2": self.pin_in2,
                    "in3": self.pin_in3,
                    "in4": self.pin_in4,
                    "ena": self.pin_ena,
                    "enb": self.pin_enb,
                },
                "is_active": self._is_active,
            }

    # ==========================================================================
    # WATCHDOG & SAFETY LIFECYCLE
    # ==========================================================================
    def _watchdog_loop(self):
        """Background thread monitoring command heartbeat."""
        logger.info("Motor safety watchdog thread started.")
        while self._is_active:
            time.sleep(0.1)  # 100ms polling cycle
            with self._lock:
                if not self._is_active:
                    break

                # Only monitor watchdog if we are currently moving
                if self.current_state != self.STATE_STOPPED:
                    elapsed = time.time() - self.last_command_time
                    if elapsed > config.WATCHDOG_TIMEOUT_SECONDS:
                        logger.warning(
                            "WATCHDOG TIMEOUT: No command received for %.2fs (limit: %.2fs). Triggering emergency STOP!",
                            elapsed,
                            config.WATCHDOG_TIMEOUT_SECONDS,
                        )
                        # Emergency stop
                        self._set_motor_pins(GPIO.LOW, GPIO.LOW, GPIO.LOW, GPIO.LOW)
                        if self._pwm_left is not None:
                            self._pwm_left.ChangeDutyCycle(0)
                        if self._pwm_right is not None:
                            self._pwm_right.ChangeDutyCycle(0)
                        self.current_state = self.STATE_STOPPED
                        self.watchdog_expired = True

    def _handle_signal(self, signum, frame):
        """Signal handler for graceful shutdown on SIGINT / SIGTERM."""
        logger.info("Received OS signal %s. Shutting down safely...", signum)
        self.cleanup()
        sys.exit(0)

    def cleanup(self):
        """
        Stops all motors and cleans up GPIO resources.
        Safe to call multiple times.
        """
        with self._lock:
            if not self._is_active:
                return
            logger.info("Performing safe shutdown of MotorController...")
            self._is_active = False

            # Stop hardware PWM
            try:
                if self._pwm_left is not None:
                    self._pwm_left.stop()
                if self._pwm_right is not None:
                    self._pwm_right.stop()
            except Exception as err:
                logger.error("Error stopping PWM: %s", err)

            # Ensure all pins are LOW
            try:
                self._set_motor_pins(GPIO.LOW, GPIO.LOW, GPIO.LOW, GPIO.LOW)
            except Exception as err:
                logger.error("Error setting pins to LOW: %s", err)

            # Release GPIO pins
            try:
                GPIO.cleanup()
            except Exception as err:
                logger.error("Error during GPIO.cleanup(): %s", err)

            self.current_state = self.STATE_STOPPED
            logger.info("MotorController shutdown complete. Pins released safely.")


# Global singleton controller instance for application use
_motor_controller_instance: Optional[MotorController] = None


def get_motor_controller(force_mock: Optional[bool] = None) -> MotorController:
    """Returns the global MotorController singleton instance."""
    global _motor_controller_instance
    if _motor_controller_instance is None:
        _motor_controller_instance = MotorController(force_mock=force_mock)
    return _motor_controller_instance
