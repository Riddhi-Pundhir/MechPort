/**
 * MechPort - ESP32-CAM Wi-Fi Live Video Streamer (Phase 5 Foundation)
 * 
 * IMPORTANT:
 * DO NOT hardcode your real Wi-Fi credentials here!
 * Create credentials.h or enter them via build-time macros.
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "camera_pins.h"

// Placeholder Wi-Fi credentials - will be loaded securely in Phase 5
const char* ssid = "YOUR_AIRTEL_HOTSPOT_NAME";
const char* password = "YOUR_AIRTEL_HOTSPOT_PASSWORD";

void setup() {
  Serial.begin(115200);
  Serial.println("\n--- MechPort ESP32-CAM Starting ---");
  // Camera initialization and streaming server will be completed in Phase 5
}

void loop() {
  delay(10000);
}
