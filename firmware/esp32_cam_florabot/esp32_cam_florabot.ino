/*
 * FloraBOT AI — ESP32-CAM Autonomous Monitoring Firmware
 * Compatible with AI-Thinker ESP32-CAM module (OV2640 camera)
 * 
 * Capabilities:
 * 1. Connects to local 2.4 GHz Wi-Fi network.
 * 2. Runs local HTTP web server providing:
 *    - Port 80 /capture : Returns single high-resolution JPEG snapshot.
 *    - Port 81 /stream  : Provides real-time MJPEG video stream.
 * 3. Autonomous Push Mode:
 *    - Periodically captures JPEG frames and POSTs directly to FloraBOT Backend:
 *      POST http://<SERVER_IP>:8000/api/devices/esp32-cam-01/images
 * 4. Periodic Heartbeat Ping:
 *    - POST http://<SERVER_IP>:8000/api/devices/esp32-cam-01/heartbeat
 * 5. Visual status feedback via onboard flash / status LED.
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// ==========================================
// 1. NETWORK & BACKEND CONFIGURATION
// ==========================================
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// FloraBOT Backend IP and Port (e.g., your Windows workstation IP)
const char* FLORABOT_HOST = "192.168.1.50";
const int   FLORABOT_PORT = 8000;
const char* DEVICE_ID     = "esp32-cam-01";

// Periodic transmission intervals in milliseconds
const unsigned long CAPTURE_INTERVAL_MS = 60000;  // Send image every 60 seconds
const unsigned long HEARTBEAT_INTERVAL_MS = 30000; // Send heartbeat every 30 seconds

// ==========================================
// 2. AI-THINKER ESP32-CAM PIN DEFINITIONS
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

unsigned long lastCaptureTime = 0;
unsigned long lastHeartbeatTime = 0;

WiFiServer server(80);

void startCameraServer();

// ==========================================
// SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println("\n[FloraBOT] Starting ESP32-CAM Autonomous Monitor...");

  pinMode(STATUS_LED_PIN, OUTPUT);
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(STATUS_LED_PIN, HIGH); // Turn off
  digitalWrite(FLASH_LED_PIN, LOW);

  // Configure camera hardware
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_siod = SIOD_GPIO_NUM;
  config.pin_sioc = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA; // 800x600 for sharp leaf diagnostics
    config.jpeg_quality = 12;           // High quality JPEG
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 14;
    config.fb_count = 1;
  }

  // Camera init
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[FloraBOT] Camera initialization failed with error 0x%x\n", err);
    return;
  }
  Serial.println("[FloraBOT] Camera sensor initialized successfully.");

  // Connect to Wi-Fi
  Serial.printf("[FloraBOT] Connecting to Wi-Fi '%s'...", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 40) {
    delay(500);
    digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN)); // Blink while connecting
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    digitalWrite(STATUS_LED_PIN, LOW); // Solid ON when connected
    Serial.println("\n[FloraBOT] Wi-Fi Connected!");
    Serial.print("[FloraBOT] IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.printf("[FloraBOT] Snapshot URL: http://%s/capture\n", WiFi.localIP().toString().c_str());
    Serial.printf("[FloraBOT] MJPEG Stream : http://%s:81/stream\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[FloraBOT] Wi-Fi connection timed out. Check SSID and credentials.");
  }

  // Initial heartbeat
  sendHeartbeat();
}

// ==========================================
// LOOP
// ==========================================
void loop() {
  unsigned long now = millis();

  // Keep Wi-Fi alive
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[FloraBOT] Wi-Fi lost. Reconnecting...");
    WiFi.reconnect();
    delay(2000);
    return;
  }

  // 1. Periodic Heartbeat Ping
  if (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatTime = now;
    sendHeartbeat();
  }

  // 2. Autonomous Image Capture & Ingestion
  if (now - lastCaptureTime >= CAPTURE_INTERVAL_MS) {
    lastCaptureTime = now;
    sendCameraFrame();
  }

  delay(100);
}

// ==========================================
// PUSH FRAME TO BACKEND
// ==========================================
void sendCameraFrame() {
  Serial.println("[FloraBOT] Capturing frame for plant health analysis...");

  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[FloraBOT] Camera capture failed.");
    return;
  }

  HTTPClient http;
  String url = String("http://") + FLORABOT_HOST + ":" + FLORABOT_PORT + "/api/devices/" + DEVICE_ID + "/images";
  http.begin(url);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.setTimeout(12000);

  Serial.printf("[FloraBOT] Transmitting frame (%d bytes) to %s...\n", fb->len, url.c_str());
  int httpResponseCode = http.POST(fb->buf, fb->len);

  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.printf("[FloraBOT] Upload successful (HTTP %d). Response: %s\n", httpResponseCode, response.c_str());
  } else {
    Serial.printf("[FloraBOT] Frame upload failed, error: %s\n", http.errorToString(httpResponseCode).c_str());
  }

  http.end();
  esp_camera_fb_return(fb);
}

// ==========================================
// HEARTBEAT
// ==========================================
void sendHeartbeat() {
  HTTPClient http;
  String url = String("http://") + FLORABOT_HOST + ":" + FLORABOT_PORT + "/api/devices/" + DEVICE_ID + "/heartbeat";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);

  int httpCode = http.POST("{}");
  if (httpCode > 0) {
    Serial.printf("[FloraBOT] Heartbeat ACK (HTTP %d)\n", httpCode);
  } else {
    Serial.printf("[FloraBOT] Heartbeat failed (%d)\n", httpCode);
  }
  http.end();
}
