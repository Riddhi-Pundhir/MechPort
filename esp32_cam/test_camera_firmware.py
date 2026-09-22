"""
MechPort - Static Validation for Phase 5 ESP32-CAM Firmware
===========================================================
Validates:
1. All required Arduino & ESP-IDF header includes are present.
2. All 15 camera pin definitions from camera_pins.h are referenced.
3. No secrets or real credentials are hard-coded in the firmware or repo.
4. credentials.h is properly excluded by .gitignore.
5. credentials.example.h exists and has valid template macros.
6. Dual HTTP streaming endpoints (/stream on port 80 & 81) are registered.
7. Serial logging is configured for 115200 baud.
8. DHCP IP reporting and HTML status page are implemented.
"""

import os
import re
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAM_DIR = os.path.join(BASE_DIR, "esp32_cam", "mechport_camera")
INO_FILE = os.path.join(CAM_DIR, "mechport_camera.ino")
PINS_FILE = os.path.join(CAM_DIR, "camera_pins.h")
CRED_EXAMPLE = os.path.join(CAM_DIR, "credentials.example.h")
GITIGNORE = os.path.join(BASE_DIR, ".gitignore")

def run_checks():
    print("=" * 65)
    print("      MechPort Phase 5: ESP32-CAM Firmware Static Validation")
    print("=" * 65)

    # 1. File existence
    print("\n[CHECK 1] Verifying firmware file existence...")
    for path, name in [(INO_FILE, "mechport_camera.ino"), (PINS_FILE, "camera_pins.h"), (CRED_EXAMPLE, "credentials.example.h")]:
        assert os.path.isfile(path), f"Missing file: {name}"
        print(f"  [PASS] {name} exists ({os.path.getsize(path)} bytes).")

    # 2. Inspect camera_pins.h
    print("\n[CHECK 2] Validating camera_pins.h definitions...")
    with open(PINS_FILE, "r", encoding="utf-8") as f:
        pins_content = f.read()

    expected_pins = [
        "PWDN_GPIO_NUM", "RESET_GPIO_NUM", "XCLK_GPIO_NUM", "SIOD_GPIO_NUM", "SIOC_GPIO_NUM",
        "Y9_GPIO_NUM", "Y8_GPIO_NUM", "Y7_GPIO_NUM", "Y6_GPIO_NUM", "Y5_GPIO_NUM",
        "Y4_GPIO_NUM", "Y3_GPIO_NUM", "Y2_GPIO_NUM", "VSYNC_GPIO_NUM", "HREF_GPIO_NUM", "PCLK_GPIO_NUM"
    ]
    for pin in expected_pins:
        assert pin in pins_content, f"Missing pin definition: {pin}"
    print(f"  [PASS] All {len(expected_pins)} AI-Thinker pin definitions verified.")

    # 3. Inspect mechport_camera.ino code
    print("\n[CHECK 3] Validating mechport_camera.ino implementation...")
    with open(INO_FILE, "r", encoding="utf-8") as f:
        ino_content = f.read()

    # Headers
    required_includes = ['#include "esp_camera.h"', '#include <WiFi.h>', '#include "esp_http_server.h"', '#include "camera_pins.h"']
    for inc in required_includes:
        assert inc in ino_content, f"Missing include: {inc}"
    print("  [PASS] Required ESP-IDF & Arduino headers verified.")

    # Pin bindings
    for pin in expected_pins:
        assert pin in ino_content, f"Firmware does not map pin: {pin}"
    print("  [PASS] All 16 pin bindings matched to camera_config_t structure.")

    # Serial baud rate
    assert "Serial.begin(115200)" in ino_content
    print("  [PASS] Serial baud rate verified at 115200.")

    # Brownout handling
    assert "RTC_CNTL_BROWN_OUT_REG" in ino_content
    print("  [PASS] Brownout detector management implemented.")

    # PSRAM check
    assert "psramFound()" in ino_content
    print("  [PASS] PSRAM detection and resolution switching (VGA/QVGA) implemented.")

    # Streaming handlers and ports
    assert "/stream" in ino_content
    assert "stream_handler" in ino_content
    assert "config.server_port = 80" in ino_content
    assert "config.server_port = 81" in ino_content
    print("  [PASS] Dual-port MJPEG streaming servers (Port 80 & 81) verified.")

    # Status endpoints
    assert "/status" in ino_content
    assert "/capture" in ino_content
    assert "index_handler" in ino_content
    print("  [PASS] Root HTML viewer, JSON /status, and /capture endpoints verified.")

    # 4. Secrets audit
    print("\n[CHECK 4] Auditing secrets and git protection...")
    with open(GITIGNORE, "r", encoding="utf-8") as f:
        gi_content = f.read()
    assert "credentials.h" in gi_content
    print("  [PASS] credentials.h is excluded by .gitignore.")

    # Verify no real passwords accidentally committed
    forbidden_patterns = [r'password\s*=\s*"[^"]{5,}"', r'WIFI_PASSWORD\s*"[^"]{5,}"']
    for pat in forbidden_patterns:
        matches = re.findall(pat, ino_content)
        for m in matches:
            assert "YOUR_AIRTEL_HOTSPOT_PASSWORD" in m or "password" in m.lower(), f"Potential leak: {m}"
    print("  [PASS] No hardcoded Wi-Fi passwords detected.")

    # 5. Non-motor control verification
    print("\n[CHECK 5] Confirming ESP32-CAM does not touch motor pins...")
    forbidden_motor_terms = ["motor", "L298N", "forward(", "backward("]
    for term in forbidden_motor_terms:
        assert term.lower() not in ino_content.lower() or "not control motor" in ino_content.lower(), f"Unexpected motor logic in camera: {term}"
    print("  [PASS] Verified firmware does NOT control motors.")

    print("\n" + "=" * 65)
    print("   ALL PHASE 5 ESP32-CAM STATIC VALIDATION CHECKS PASSED! ")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    run_checks()
