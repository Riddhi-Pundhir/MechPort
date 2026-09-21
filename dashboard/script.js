/**
 * MechPort Dashboard Script (Phase 4 Foundation)
 * Configurable endpoints for Raspberry Pi API and ESP32-CAM stream.
 */

const CONFIG = {
  // Configurable addresses - replace with your local IP addresses when assigned
  rpiBaseUrl: "http://192.168.1.100:5000",
  esp32CamUrl: "http://192.168.1.50:81/stream",
  heartbeatIntervalMs: 800, // Send movement commands periodically while key is held down
};

console.log("MechPort Dashboard initialized with target:", CONFIG.rpiBaseUrl);
