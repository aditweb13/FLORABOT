/*
 * FloraBOT AI — ESP32-CAM Autonomous Monitoring Firmware (v2.0 Production)
 * Compatible with AI-Thinker ESP32-CAM module (OV2640 camera & MicroSD slot)
 * 
 * Capabilities:
 * 1. Connects to 2.4 GHz Wi-Fi with exponential backoff reconnect and error LED signaling.
 * 2. High-Performance Dual HTTP Camera Web Server:
 *    - Port 80 /capture  : Returns single fresh JPEG snapshot.
 *    - Port 81 /stream   : Streams high-framerate multipart MJPEG video directly.
 * 3. Autonomous Backend Push Mode:
 *    - Periodically captures JPEG frames and POSTs directly to FloraBOT Backend:
 *      POST http://<FLORABOT_HOST>:8000/api/devices/esp32-cam-01/images
 * 4. Periodic Heartbeat Telemetry:
 *    - Periodically pings backend with health status and device state.
 * 5. Offline SD Card Buffering:
 *    - If network drops or Wi-Fi is lost, saves captures locally to microSD card
 *      under /florabot/captures/ so zero botanical data is lost during outages.
 * 6. Non-blocking Task Timing:
 *    - Uses millisecond timer state machine avoiding blocking delays.
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_timer.h"
#include "esp_http_server.h"
#include "FS.h"
#include "SD_MMC.h"

// ==========================================
// 1. NETWORK & BACKEND CONFIGURATION
// ==========================================
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// FloraBOT Backend Host & Port
const char* FLORABOT_HOST = "192.168.1.50";
const int   FLORABOT_PORT = 8000;
const char* DEVICE_ID     = "esp32-cam-01";

// Periodic transmission intervals in milliseconds
const unsigned long CAPTURE_INTERVAL_MS   = 60000; // Capture & upload every 60s
const unsigned long HEARTBEAT_INTERVAL_MS = 30000; // Heartbeat telemetry every 30s

// ==========================================
// 2. AI-THINKER PIN DEFINITIONS
// ==========================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define FLASH_LED_PIN      4
#define STATUS_LED_PIN    33 // Active LOW on AI-Thinker

// ==========================================
// 3. SERVER & STREAM CONSTANTS
// ==========================================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* _STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* _STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* _STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t stream_httpd = NULL;
httpd_handle_t camera_httpd = NULL;

unsigned long lastCaptureTime   = 0;
unsigned long lastHeartbeatTime = 0;
unsigned long lastReconnectAttempt = 0;
unsigned int  reconnectBackoffMs = 2000;
bool sdCardAvailable = false;

// Function declarations
void startCameraServer();
void sendCameraFrame();
void sendHeartbeat();
void checkWiFiConnection();
void initSDCard();
void saveFrameToSD(camera_fb_t * fb);

// ==========================================
// HTTP HANDLERS: /capture & /stream
// ==========================================

// 1. Port 80 /capture handler: Returns single fresh JPEG
static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[FloraBOT Server] Camera capture failed on /capture");
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

// 2. Port 81 /stream handler: Returns continuous MJPEG stream
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t * fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t * _jpg_buf = NULL;
  char part_buf[64];

  res = httpd_resp_set_type(req, _STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("[FloraBOT Stream] Camera capture failed during stream");
      res = ESP_FAIL;
      break;
    }
    _jpg_buf_len = fb->len;
    _jpg_buf = fb->buf;

    if (res == ESP_OK) res = httpd_resp_send_chunk(req, _STREAM_BOUNDARY, strlen(_STREAM_BOUNDARY));
    if (res == ESP_OK) {
      size_t hlen = snprintf(part_buf, 64, _STREAM_PART, _jpg_buf_len);
      res = httpd_resp_send_chunk(req, part_buf, hlen);
    }
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);

    esp_camera_fb_return(fb);
    fb = NULL;
    _jpg_buf = NULL;

    if (res != ESP_OK) break;
  }
  return res;
}

// 3. Port 80 /status handler: Returns basic device diagnostics
static esp_err_t status_handler(httpd_req_t *req) {
  char json_response[256];
  snprintf(json_response, sizeof(json_response),
    "{\"device_id\":\"%s\",\"status\":\"online\",\"uptime_ms\":%lu,\"sd_card\":%s,\"free_heap\":%u}",
    DEVICE_ID, millis(), sdCardAvailable ? "true" : "false", ESP.getFreeHeap()
  );
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, json_response, strlen(json_response));
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.ctrl_port = 32768;

  httpd_uri_t capture_uri = {
    .uri       = "/capture",
    .method    = HTTP_GET,
    .handler   = capture_handler,
    .user_ctx  = NULL
  };

  httpd_uri_t status_uri = {
    .uri       = "/status",
    .method    = HTTP_GET,
    .handler   = status_handler,
    .user_ctx  = NULL
  };

  Serial.println("[FloraBOT Server] Starting HTTP server on port 80 (/capture, /status)...");
  if (httpd_start(&camera_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(camera_httpd, &capture_uri);
    httpd_register_uri_handler(camera_httpd, &status_uri);
  }

  // Start dedicated high-framerate stream server on Port 81
  config.server_port = 81;
  config.ctrl_port = 32769;

  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  Serial.println("[FloraBOT Server] Starting MJPEG stream server on port 81 (/stream)...");
  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
  }
}

// ==========================================
// SD CARD INITIALIZATION & OFFLINE CACHE
// ==========================================
void initSDCard() {
  Serial.println("[FloraBOT] Initializing 1-bit MicroSD card interface...");
  // Use 1-bit mode to avoid conflict with GPIO4 flash LED
  if (!SD_MMC.begin("/sdcard", true)) {
    Serial.println("[FloraBOT] MicroSD card mount failed (offline buffering disabled).");
    sdCardAvailable = false;
    return;
  }
  uint8_t cardType = SD_MMC.cardType();
  if (cardType == CARD_NONE) {
    Serial.println("[FloraBOT] No MicroSD card attached.");
    sdCardAvailable = false;
    return;
  }
  SD_MMC.mkdir("/florabot");
  SD_MMC.mkdir("/florabot/captures");
  sdCardAvailable = true;
  Serial.printf("[FloraBOT] MicroSD card initialized successfully (Size: %llu MB).\n", SD_MMC.cardSize() / (1024 * 1024));
}

void saveFrameToSD(camera_fb_t * fb) {
  if (!sdCardAvailable || !fb) return;
  char path[64];
  snprintf(path, sizeof(path), "/florabot/captures/img_%lu.jpg", millis());
  File file = SD_MMC.open(path, FILE_WRITE);
  if (!file) {
    Serial.println("[FloraBOT] Failed to open file on SD for buffering.");
    return;
  }
  file.write(fb->buf, fb->len);
  file.close();
  Serial.printf("[FloraBOT Offline Cache] Frame buffered to SD: %s (%d bytes)\n", path, fb->len);
}

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  Serial.println("\n========================================================");
  Serial.println("  FloraBOT AI — ESP32-CAM Autonomous Monitor v2.0");
  Serial.println("========================================================");

  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, HIGH); // Active LOW: HIGH is OFF
  digitalWrite(FLASH_LED_PIN, LOW);

  // Configure camera hardware
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
  config.pin_siod     = SIOD_GPIO_NUM;
  config.pin_sioc     = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size   = FRAMESIZE_SVGA; // 800x600 keeps sharp leaf venation
    config.jpeg_quality = 12;             // High clarity
    config.fb_count     = 2;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
    config.grab_mode    = CAMERA_GRAB_LATEST; // Drop stale buffers to ensure live stream
    Serial.println("[FloraBOT] PSRAM detected: 800x600 SVGA double-buffered mode enabled.");
  } else {
    config.frame_size   = FRAMESIZE_VGA;  // 640x480 fallback
    config.jpeg_quality = 14;
    config.fb_count     = 1;
    config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
    Serial.println("[FloraBOT] No PSRAM: 640x480 VGA single-buffer mode enabled.");
  }

  // Camera sensor init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[FloraBOT ERROR] Camera init failed (0x%x). Check ribbon cable!\n", err);
    while (true) {
      digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN));
      delay(150);
    }
  }
  Serial.println("[FloraBOT] Camera sensor initialized.");

  // Initialize MicroSD card
  initSDCard();

  // Connect to Wi-Fi
  Serial.printf("[FloraBOT] Connecting to Wi-Fi '%s'...", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(400);
    digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN)); // Fast blink while connecting
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    digitalWrite(STATUS_LED_PIN, LOW); // Solid ON when connected
    Serial.println("\n[FloraBOT] Wi-Fi Connected!");
    Serial.printf("[FloraBOT] IP Address  : %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("[FloraBOT] Snapshot URL: http://%s/capture\n", WiFi.localIP().toString().c_str());
    Serial.printf("[FloraBOT] MJPEG Stream: http://%s:81/stream\n", WiFi.localIP().toString().c_str());
    startCameraServer();
    sendHeartbeat();
  } else {
    Serial.println("\n[FloraBOT WARNING] Initial Wi-Fi connection timed out. Reconnect loop active.");
  }
}

// ==========================================
// LOOP & RESILIENT WI-FI RECONNECT
// ==========================================
void loop() {
  unsigned long now = millis();

  // 1. Resilient Wi-Fi monitor with exponential backoff
  checkWiFiConnection();

  // 2. Periodic Heartbeat Ping (every 30 seconds)
  if (WiFi.status() == WL_CONNECTED && (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS)) {
    lastHeartbeatTime = now;
    sendHeartbeat();
  }

  // 3. Autonomous Periodic Capture & Ingestion (every 60 seconds)
  if (now - lastCaptureTime >= CAPTURE_INTERVAL_MS) {
    lastCaptureTime = now;
    sendCameraFrame();
  }

  delay(50);
}

void checkWiFiConnection() {
  if (WiFi.status() == WL_CONNECTED) {
    reconnectBackoffMs = 2000; // Reset backoff on healthy connection
    return;
  }

  unsigned long now = millis();
  if (now - lastReconnectAttempt >= reconnectBackoffMs) {
    lastReconnectAttempt = now;
    digitalWrite(STATUS_LED_PIN, HIGH); // LED OFF when disconnected
    Serial.printf("[FloraBOT] Wi-Fi disconnected. Attempting reconnect (backoff: %u ms)...\n", reconnectBackoffMs);
    WiFi.disconnect();
    WiFi.reconnect();
    
    // Exponential backoff up to 60 seconds
    reconnectBackoffMs = min(60000U, reconnectBackoffMs * 2);
  }
}

// ==========================================
// PUSH FRAME TO BACKEND (WITH OFFLINE SD FALLBACK)
// ==========================================
void sendCameraFrame() {
  Serial.println("[FloraBOT] Capturing fresh frame for health analysis...");
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[FloraBOT] Capture failed!");
    return;
  }

  // If Wi-Fi is down, buffer to local MicroSD
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[FloraBOT] Wi-Fi offline. Buffering frame to MicroSD card...");
    saveFrameToSD(fb);
    esp_camera_fb_return(fb);
    return;
  }

  HTTPClient http;
  String url = String("http://") + FLORABOT_HOST + ":" + FLORABOT_PORT + "/api/devices/" + DEVICE_ID + "/images";
  http.begin(url);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("X-Async", "true"); // Request fast asynchronous 202 acknowledgment
  http.setTimeout(12000);

  Serial.printf("[FloraBOT] Uploading frame (%d bytes) to %s...\n", fb->len, url.c_str());
  int httpResponseCode = http.POST(fb->buf, fb->len);

  if (httpResponseCode > 0) {
    Serial.printf("[FloraBOT] Upload OK (HTTP %d)\n", httpResponseCode);
  } else {
    Serial.printf("[FloraBOT] Upload failed (%s). Buffering to MicroSD...\n", http.errorToString(httpResponseCode).c_str());
    saveFrameToSD(fb);
  }

  http.end();
  esp_camera_fb_return(fb);
}

// ==========================================
// HEARTBEAT TELEMETRY
// ==========================================
void sendHeartbeat() {
  HTTPClient http;
  String url = String("http://") + FLORABOT_HOST + ":" + FLORABOT_PORT + "/api/devices/" + DEVICE_ID + "/heartbeat";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);

  char payload[180];
  snprintf(payload, sizeof(payload),
    "{\"status\":\"online\",\"ip_address\":\"%s\",\"uptime_sec\":%lu,\"free_heap\":%u,\"sd_card\":%s}",
    WiFi.localIP().toString().c_str(), millis() / 1000, ESP.getFreeHeap(), sdCardAvailable ? "true" : "false"
  );

  int httpCode = http.POST(payload);
  if (httpCode > 0) {
    Serial.printf("[FloraBOT] Heartbeat OK (HTTP %d)\n", httpCode);
  } else {
    Serial.printf("[FloraBOT] Heartbeat failed (%d)\n", httpCode);
  }
  http.end();
}
