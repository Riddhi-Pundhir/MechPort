/**
 * ==============================================================================
 * MechPort - ESP32-CAM Wi-Fi Live Video Streamer (Phase 5 Firmware)
 * ==============================================================================
 * Target Hardware:
 *   - AI-Thinker ESP32-CAM module (OV2640 image sensor)
 *   - Uses camera pin definitions in camera_pins.h
 *
 * Network & Connectivity:
 *   - Connects to local Airtel phone hotspot using DHCP.
 *   - Local credentials loaded from "credentials.h" (never committed to git).
 *   - Copy "credentials.example.h" to "credentials.h" and enter your Wi-Fi details.
 *
 * Features:
 *   - Live browser-accessible MJPEG video stream (/stream on Port 80 and Port 81)
 *   - Simple HTML status landing page (/) with device telemetry and stream preview
 *   - JSON status endpoint (/status) with CORS headers for dashboard integration
 *   - Still snapshot capture endpoint (/capture)
 *   - Non-blocking FreeRTOS HTTP servers (esp_http_server)
 *   - Comprehensive Serial diagnostics at 115200 baud
 *
 * Safety & Architecture:
 *   - ESP32-CAM solely provides video telemetry; it DOES NOT control motors.
 *   - Does not assume or hardcode any IP address; reports assigned DHCP IP on boot.
 * ==============================================================================
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"
#include "esp_timer.h"
#include "img_converters.h"
#include "fb_gfx.h"
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// Include AI-Thinker camera pin mapping
#include "camera_pins.h"

// Include local Wi-Fi credentials if present, else use fallback placeholders
#if __has_include("credentials.h")
#include "credentials.h"
#else
#warning "credentials.h not found! Using default placeholders. Copy credentials.example.h to credentials.h."
#define WIFI_SSID     "YOUR_AIRTEL_HOTSPOT_NAME"
#define WIFI_PASSWORD "YOUR_AIRTEL_HOTSPOT_PASSWORD"
#endif

// HTTP Server Handles
httpd_handle_t stream_httpd = NULL;
httpd_handle_t camera_httpd = NULL;

// Multipart Stream Boundary definition
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// ==============================================================================
// 1. HTTP HANDLERS: MJPEG STREAM
// ==============================================================================
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char part_buf[64];

  // Set response headers for MJPEG stream with CORS support
  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "Cache-Control", "no-cache, private");
  httpd_resp_set_hdr(req, "Pragma", "no-cache");

  // Continuous frame transmission loop
  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[STREAM] Camera frame acquisition failed!");
      res = ESP_FAIL;
    } else {
      _jpg_buf_len = fb->len;
      _jpg_buf = fb->buf;
    }

    if (res == ESP_OK) {
      size_t hlen = snprintf(part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    }

    if (fb) {
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    } else if (_jpg_buf) {
      free(_jpg_buf);
      _jpg_buf = NULL;
    }

    // Client disconnected or error occurred
    if (res != ESP_OK) {
      break;
    }
  }

  return res;
}

// ==============================================================================
// 2. HTTP HANDLERS: STILL CAPTURE
// ==============================================================================
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAPTURE] Camera capture failed!");
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

// ==============================================================================
// 3. HTTP HANDLERS: JSON STATUS TELEMETRY
// ==============================================================================
static esp_err_t status_handler(httpd_req_t *req) {
  char json_response[256];
  snprintf(json_response, sizeof(json_response),
    "{"
      "\"device\":\"ESP32-CAM\","
      "\"sensor\":\"OV2640\","
      "\"camera_status\":\"online\","
      "\"ip\":\"%s\","
      "\"stream_url\":\"http://%s/stream\","
      "\"wifi_rssi\":%d,"
      "\"free_heap\":%u,"
      "\"psram\":%s"
    "}",
    WiFi.localIP().toString().c_str(),
    WiFi.localIP().toString().c_str(),
    WiFi.RSSI(),
    ESP.getFreeHeap(),
    psramFound() ? "true" : "false"
  );

  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, json_response, strlen(json_response));
}

// ==============================================================================
// 4. HTTP HANDLERS: ROOT STATUS & PREVIEW LANDING PAGE
// ==============================================================================
static esp_err_t index_handler(httpd_req_t *req) {
  String html = "<!DOCTYPE html><html><head>";
  html += "<meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1.0'>";
  html += "<title>MechPort ESP32-CAM Video Streamer</title>";
  html += "<style>";
  html += "body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#070a14;color:#e2e8f0;margin:0;padding:20px;display:flex;justify-content:center;}";
  html += ".card{background:#10172c;border:1px solid #c084fc40;border-radius:14px;padding:24px;max-width:680px;width:100%;box-shadow:0 10px 30px rgba(0,0,0,0.6);}";
  html += "h1{font-size:1.4rem;color:#c084fc;margin-top:0;display:flex;align-items:center;gap:10px;}";
  html += ".badge{background:#10b98125;border:1px solid #10b981;color:#34d399;padding:3px 10px;border-radius:999px;font-size:0.75rem;font-weight:700;}";
  html += ".view{background:#000;border-radius:8px;overflow:hidden;margin:16px 0;text-align:center;}";
  html += ".view img{max-width:100%;height:auto;display:block;}";
  html += "table{width:100%;border-collapse:collapse;margin-top:12px;font-size:0.85rem;}";
  html += "td{padding:6px 0;border-bottom:1px solid #ffffff10;}";
  html += "td:last-child{text-align:right;font-weight:600;color:#f8fafc;}";
  html += "code{background:#ffffff15;color:#38bdf8;padding:2px 6px;border-radius:4px;font-size:0.82rem;}";
  html += ".btn{display:inline-block;background:#8b5cf6;color:#fff;text-decoration:none;padding:8px 16px;border-radius:8px;font-weight:700;margin-top:14px;}";
  html += "</style></head><body>";
  html += "<div class='card'>";
  html += "<h1><span>📹</span> MechPort ESP32-CAM <span class='badge'>STREAM ONLINE</span></h1>";
  html += "<div class='view'><img src='/stream' alt='Live Stream Preview'></div>";
  html += "<table><tbody>";
  html += "<tr><td>Assigned IP Address</td><td><code>" + WiFi.localIP().toString() + "</code></td></tr>";
  html += "<tr><td>Live Stream URL (Port 80)</td><td><code>http://" + WiFi.localIP().toString() + "/stream</code></td></tr>";
  html += "<tr><td>Alternative Stream (Port 81)</td><td><code>http://" + WiFi.localIP().toString() + ":81/stream</code></td></tr>";
  html += "<tr><td>Wi-Fi SSID</td><td>" + String(WIFI_SSID) + "</td></tr>";
  html += "<tr><td>Signal Strength (RSSI)</td><td>" + String(WiFi.RSSI()) + " dBm</td></tr>";
  html += "<tr><td>Free Heap Memory</td><td>" + String(ESP.getFreeHeap()) + " bytes</td></tr>";
  html += "<tr><td>PSRAM Detected</td><td>" + String(psramFound() ? "Yes (Enabled)" : "No (Disabled)") + "</td></tr>";
  html += "</tbody></table>";
  html += "<a href='/stream' target='_blank' class='btn'>Open Raw Stream</a>";
  html += "</div></body></html>";

  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, html.c_str(), html.length());
}

// ==============================================================================
// 5. SERVER INITIALIZATION (Port 80 & Port 81)
// ==============================================================================
void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.ctrl_port = 32768;

  // 1. Register Port 80 Endpoints
  httpd_uri_t index_uri = {
    .uri       = "/",
    .method    = HTTP_GET,
    .handler   = index_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t status_uri = {
    .uri       = "/status",
    .method    = HTTP_GET,
    .handler   = status_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t capture_uri = {
    .uri       = "/capture",
    .method    = HTTP_GET,
    .handler   = capture_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &index_uri);
    httpd_register_uri_handler(camera_httpd, &stream_uri);
    httpd_register_uri_handler(camera_httpd, &status_uri);
    httpd_register_uri_handler(camera_httpd, &capture_uri);
    Serial.println("[HTTP] Web and stream server listening on Port 80");
  } else {
    Serial.println("[ERROR] Failed to start HTTP server on Port 80!");
  }

  // 2. Start dedicated Port 81 Stream Server for maximum dashboard compatibility
  config.server_port = 81;
  config.ctrl_port = 32769;

  httpd_uri_t stream_p81_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_p81_uri);
    Serial.println("[HTTP] Secondary stream server listening on Port 81");
  } else {
    Serial.println("[WARNING] Could not start secondary Port 81 server; Port 80 stream remains available.");
  }
}

// ==============================================================================
// 6. SETUP ROUTINE
// ==============================================================================
void setup() {
  // Disable brownout detector to prevent reboot loops during camera initialization
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==================================================");
  Serial.println("         MechPort ESP32-CAM Video Streamer        ");
  Serial.println("==================================================");

  // Configure Camera Pinout and Frame Settings
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;

  // Frame resolution and buffer management based on PSRAM availability
  if (psramFound()) {
    Serial.println("[INFO] PSRAM detected! Enabling 640x480 VGA resolution.");
    config.frame_size   = FRAMESIZE_VGA;  // 640x480
    config.jpeg_quality = 12;             // 10-63 lower number = higher quality
    config.fb_count     = 2;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("[WARNING] PSRAM not found. Using 320x240 QVGA resolution.");
    config.frame_size   = FRAMESIZE_QVGA; // 320x240
    config.jpeg_quality = 14;
    config.fb_count     = 1;
    config.fb_location  = CAMERA_FB_IN_DRAM;
  }

  // Initialize Camera Sensor
  Serial.print("[INIT] Initializing camera sensor... ");
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("\n[ERROR] Camera initialization failed with error code: 0x%x\n", err);
    Serial.println("--------------------------------------------------");
    Serial.println("Troubleshooting tips:");
    Serial.println("  1. Verify the OV2640 ribbon cable is firmly seated in the connector.");
    Serial.println("  2. Ensure power supply provides 5V at minimum 1.5A to the ESP32-CAM.");
    Serial.println("  3. Check Board selection in Arduino IDE: 'AI Thinker ESP32-CAM'.");
    Serial.println("  4. Enable PSRAM in Arduino IDE: Tools -> PSRAM -> Enabled.");
    Serial.println("--------------------------------------------------");
    // Halt execution on camera hardware failure
    while (true) {
      delay(1000);
    }
  }
  Serial.println("SUCCESS!");

  // Connect to Wi-Fi
  Serial.println("[WIFI] Setting up Wi-Fi connection...");
  if (String(WIFI_SSID) == "YOUR_AIRTEL_HOTSPOT_NAME") {
    Serial.println("[WARNING] Default placeholder Wi-Fi SSID detected!");
    Serial.println("          Please copy credentials.example.h to credentials.h and configure your hotspot.");
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WIFI] Connecting to SSID '%s' ", WIFI_SSID);

  int wifi_attempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifi_attempts < 30) {
    delay(500);
    Serial.print(".");
    wifi_attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] Wi-Fi connected successfully!");
    Serial.print("     Assigned DHCP IP : ");
    Serial.println(WiFi.localIP());
    Serial.print("     Subnet Mask      : ");
    Serial.println(WiFi.subnetMask());
    Serial.print("     Gateway IP       : ");
    Serial.println(WiFi.gatewayIP());
    Serial.print("     Signal (RSSI)    : ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    Serial.print("     MAC Address      : ");
    Serial.println(WiFi.macAddress());

    // Start Web Servers
    startCameraServer();

    Serial.println("\n--------------------------------------------------");
    Serial.println(" MechPort ESP32-CAM Ready for Dashboard Pairing!  ");
    Serial.println("--------------------------------------------------");
    Serial.printf("  >> Status Page   : http://%s/\n", WiFi.localIP().toString().c_str());
    Serial.printf("  >> MJPEG Stream  : http://%s/stream\n", WiFi.localIP().toString().c_str());
    Serial.printf("  >> Stream Port 81: http://%s:81/stream\n", WiFi.localIP().toString().c_str());
    Serial.printf("  >> Snapshot      : http://%s/capture\n", WiFi.localIP().toString().c_str());
    Serial.println("--------------------------------------------------");
    Serial.println("Copy the MJPEG Stream URL into your MechPort dashboard Settings!");
  } else {
    Serial.println("\n[ERROR] Failed to connect to Wi-Fi!");
    Serial.println("        Please ensure your phone hotspot is turned ON and credentials.h is correct.");
    Serial.println("        (ESP32-CAM supports 2.4 GHz Wi-Fi only. Enable 2.4 GHz band on your hotspot).");
  }
}

// ==============================================================================
// 7. MAIN LOOP (Non-blocking background monitoring)
// ==============================================================================
void loop() {
  // FreeRTOS httpd handles client requests in background tasks.
  // We periodically monitor Wi-Fi connectivity and attempt reconnection if dropped.
  static unsigned long last_check = 0;
  if (millis() - last_check > 10000) {
    last_check = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WIFI] Connection lost. Attempting auto-reconnect...");
      WiFi.reconnect();
    }
  }
  delay(1000);
}
