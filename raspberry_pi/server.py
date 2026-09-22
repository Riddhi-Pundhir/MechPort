"""
MechPort - Raspberry Pi HTTP API Server
=======================================
Exposes REST API endpoints for the laptop control dashboard:
  - GET  /api/status : Returns system health, motor state, watchdog status, and mode.
  - POST /api/move   : Receives driving commands (FORWARD, BACKWARD, LEFT, RIGHT, STOP).
  - POST /api/shutdown: Gracefully stops motors and releases GPIO pins.

Safety:
  - Startup state defaults to STOP.
  - Commands feed the hardware watchdog timer; silence triggers automatic STOP.
  - Graceful shutdown stops motors and cleans up GPIO.
  - All motor/GPIO logic delegates to the MotorController module.
"""

import atexit
import logging
import os
import signal
import sys
import time
from typing import Any, Dict

from flask import Flask, jsonify, request
from flask_cors import CORS

# Ensure current directory is accessible in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    import config
    from motor_control import MotorController, get_motor_controller
    from sensor_manager import SensorManager, get_sensor_manager
except ImportError:
    from . import config
    from .motor_control import MotorController, get_motor_controller
    from .sensor_manager import SensorManager, get_sensor_manager


# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MechPort.Server] %(message)s",
)
logger = logging.getLogger("MechPort.Server")

# Initialize Flask application
app = Flask(__name__)

# Configure Cross-Origin Resource Sharing (CORS) so the laptop dashboard can connect
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Track server start time for uptime metrics
SERVER_START_TIME = time.time()

# Supported movement commands
VALID_COMMANDS = {
    MotorController.STATE_FORWARD,
    MotorController.STATE_BACKWARD,
    MotorController.STATE_LEFT,
    MotorController.STATE_RIGHT,
    MotorController.STATE_STOPPED,
}


def get_controller() -> MotorController:
    """Returns the singleton MotorController instance."""
    return get_motor_controller()


def get_sensors() -> SensorManager:
    """Returns the singleton SensorManager instance."""
    return get_sensor_manager()



@app.before_request
def log_request_info():
    """Logs incoming HTTP requests."""
    if request.path.startswith("/api/"):
        logger.debug("Request: %s %s from %s", request.method, request.path, request.remote_addr)


@app.route("/", methods=["GET"])
def index():
    """Root landing endpoint with system status overview."""
    return jsonify({
        "project": "MechPort Robotic Car",
        "description": "Raspberry Pi Motor Control API",
        "endpoints": {
            "GET /api/status": "Get system telemetry, motor state, watchdog timer",
            "POST /api/move": "Send movement command (FORWARD, BACKWARD, LEFT, RIGHT, STOP)",
            "POST /api/shutdown": "Safely shut down the motor controller and server"
        }
    }), 200


@app.route("/api/status", methods=["GET"])
def get_status():
    """
    Returns telemetry including:
      - server status & uptime
      - current motor state
      - watchdog status
      - mock vs physical hardware mode
    """
    try:
        controller = get_controller()
        motor_status = controller.get_status()
        sensor_mgr = get_sensors()
        sensor_status = sensor_mgr.read_all()

        response_data: Dict[str, Any] = {
            "server": {
                "status": "online",
                "host": config.SERVER_HOST,
                "port": config.SERVER_PORT,
                "uptime_seconds": round(time.time() - SERVER_START_TIME, 2),
            },
            "motor": {
                "state": motor_status["state"],
                "speed": motor_status["speed"],
                "is_active": motor_status["is_active"],
            },
            "watchdog": {
                "timeout_seconds": motor_status["watchdog_timeout_sec"],
                "time_remaining_seconds": motor_status["watchdog_time_remaining_sec"],
                "expired": motor_status["watchdog_expired"],
            },
            "hardware": {
                "mode": "MOCK" if motor_status["is_mock"] else "PHYSICAL",
                "is_mock": motor_status["is_mock"],
                "pins": motor_status["pins"],
            },
            "sensors": sensor_status,
            "camera": {
                "stream_url": config.ESP32_CAM_STREAM_URL,
            },
            "timestamp": time.time(),
        }
        return jsonify(response_data), 200


    except Exception as err:
        logger.error("Error retrieving status: %s", err, exc_info=True)
        return jsonify({"status": "error", "message": "Failed to read device status"}), 500


@app.route("/api/move", methods=["POST"])
def post_move():
    """
    Accepts JSON payload:
      {
        "command": "FORWARD",  # FORWARD | BACKWARD | LEFT | RIGHT | STOP
        "speed": 80            # Optional: 0 to 100
      }
    """
    # 1. Validate JSON content
    if not request.is_json:
        logger.warning("Rejected move request: Content-Type must be application/json")
        return jsonify({
            "status": "error",
            "message": "Invalid request: Content-Type must be application/json"
        }), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        logger.warning("Rejected move request: JSON payload is malformed")
        return jsonify({
            "status": "error",
            "message": "Invalid request: JSON body must be an object"
        }), 400

    # 2. Validate command field
    raw_command = data.get("command")
    if not raw_command or not isinstance(raw_command, str):
        logger.warning("Rejected move request: Missing 'command' field")
        return jsonify({
            "status": "error",
            "message": "Missing required field: 'command'. Valid commands: FORWARD, BACKWARD, LEFT, RIGHT, STOP"
        }), 400

    command = raw_command.strip().upper()
    if command not in VALID_COMMANDS:
        logger.warning("Rejected move request: Invalid command '%s'", command)
        return jsonify({
            "status": "error",
            "message": f"Invalid command '{raw_command}'. Supported commands: {', '.join(sorted(VALID_COMMANDS))}"
        }), 400

    # 3. Validate optional speed
    speed = data.get("speed")
    if speed is not None:
        try:
            speed = int(speed)
            if speed < 0 or speed > 100:
                return jsonify({
                    "status": "error",
                    "message": "Invalid 'speed' parameter: Must be an integer between 0 and 100"
                }), 400
        except (ValueError, TypeError):
            return jsonify({
                "status": "error",
                "message": "Invalid 'speed' parameter: Must be a valid integer"
            }), 400

    # 4. Execute command via MotorController
    controller = get_controller()
    success = controller.execute_command(command, speed=speed)

    if success:
        logger.info("Executed move command: %s (speed: %s)", command, controller.current_speed)
        return jsonify({
            "status": "success",
            "command": command,
            "current_state": controller.current_state,
            "speed": controller.current_speed,
            "watchdog_timeout_seconds": config.WATCHDOG_TIMEOUT_SECONDS,
            "timestamp": time.time(),
        }), 200
    else:
        logger.error("Failed to execute command: %s", command)
        return jsonify({
            "status": "error",
            "message": "Failed to execute command on motor controller"
        }), 500


@app.route("/api/shutdown", methods=["POST"])
def post_shutdown():
    """Gracefully stops all motors, cleans up sensors, and releases GPIO."""
    logger.info("Received API shutdown request. Stopping motors and releasing pins...")
    controller = get_controller()
    controller.cleanup()
    sensor_mgr = get_sensors()
    sensor_mgr.cleanup()
    return jsonify({
        "status": "success",
        "message": "Motor controller and sensors safely shut down and GPIO resources released."
    }), 200


def run_server():
    """Initializes and runs the Flask HTTP server."""
    logger.info("Starting MechPort API Server...")
    logger.info("Listening on http://%s:%s", config.SERVER_HOST, config.SERVER_PORT)
    logger.info("Watchdog timeout: %s seconds", config.WATCHDOG_TIMEOUT_SECONDS)

    # Pre-initialize motor controller so motors start safely at STOP
    controller = get_controller()
    logger.info(
        "MotorController status: %s (Mode: %s)",
        controller.current_state,
        "MOCK" if controller.is_mock else "PHYSICAL"
    )

    # Pre-initialize sensor manager safely
    sensor_mgr = get_sensors()
    logger.info(
        "SensorManager initialized (Mode: %s)",
        "MOCK" if sensor_mgr.is_mock else "PHYSICAL"
    )


    # Run the Flask app
    app.run(
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        threaded=True,
        debug=False
    )


if __name__ == "__main__":
    run_server()
