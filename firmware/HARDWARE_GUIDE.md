# FloraBOT ESP32-CAM Hardware Integration & Flashing Guide

## 1. Hardware Overview & Bill of Materials
- **Microcontroller:** AI-Thinker ESP32-CAM (ESP32-S chip with 4MB PSRAM).
- **Camera Sensor:** OmniVision OV2640 (2-Megapixel CMOS sensor with 160° or standard 66° lens).
- **USB-to-TTL Programmer:** FTDI FT232RL or CP2102 module (must be switched to **3.3V logic**).
- **Storage:** Standard MicroSD card (FAT32, Class 10, up to 32GB) for offline image caching during network dropouts.
- **Power Supply:** External regulated $5\text{V} \ge 2\text{A}$ power adapter connected directly to the $5\text{V}$ and `GND` pins of the ESP32-CAM.
  > [!IMPORTANT]
  > Do **not** power the ESP32-CAM solely from the FTDI programmer's 3.3V pin during Wi-Fi transmission. Wi-Fi RF power spikes draw up to $350\text{--}450\text{ mA}$, causing brownout resets (`Brownout detector was triggered`).

---

## 2. Flashing Wiring Diagram (FTDI Programmer to ESP32-CAM)

| FTDI Pin | ESP32-CAM Pin | Purpose |
|---|---|---|
| **VCC (5V)** | **5V** | Power delivery |
| **GND** | **GND** | Common ground |
| **TX** | **U0R (GPIO 3)** | Serial RX |
| **RX** | **U0T (GPIO 1)** | Serial TX |
| **—** | **GPIO 0 connected to GND** | **Flashing Mode Strap** (Remove after flashing!) |

### Flashing Procedure
1. Jumper **GPIO 0 to GND**.
2. Plug FTDI programmer into USB.
3. Open Arduino IDE or PlatformIO.
   - **Board:** `AI Thinker ESP32-CAM`
   - **CPU Frequency:** `240MHz (WiFi/BT)`
   - **Flash Frequency:** `80MHz`
   - **Flash Mode:** `QIO`
   - **Partition Scheme:** `Huge APP (3MB No OTA/1MB SPIFFS)`
   - **PSRAM:** `Enabled`
4. Compile and flash `firmware/esp32_cam_florabot/esp32_cam_florabot.ino`.
5. **Crucial:** Once flashing completes (`Leaving... Hard resetting via RTS pin...`), disconnect **GPIO 0 from GND** and press the tiny **RST** button on the bottom of the ESP32-CAM.

---

## 3. Firmware Capabilities (v2.0)
1. **Dual HTTP Camera Web Server:**
   - `http://<ESP32_IP>/capture` : Delivers single fresh high-resolution SVGA ($800\times600$) JPEG snapshot.
   - `http://<ESP32_IP>:81/stream` : Streams continuous multi-part MJPEG video.
   - `http://<ESP32_IP>/status` : Returns live JSON diagnostics (free heap, uptime, SD status).
2. **Autonomous Ingestion & Heartbeat:**
   - Autonomous JPEG upload to `POST /api/devices/{id}/images` every 60 seconds with `X-Async: true` header.
   - Periodic heartbeat to `POST /api/devices/{id}/heartbeat` every 30 seconds.
3. **Resilient Wi-Fi Connection:**
   - Exponential backoff reconnect logic ($2\text{s} \to 4\text{s} \to 8\text{s} \dots \text{up to } 60\text{s}$).
   - Onboard red status LED (GPIO 33) blinks rapidly during connection attempts, stays solid ON when connected, and turns OFF when disconnected.
4. **Offline MicroSD Buffering:**
   - If Wi-Fi is lost, captures are written directly to `/florabot/captures/img_<timestamp>.jpg` using 1-bit SD mode (avoiding GPIO4 flash pin conflicts).

---

## 4. Optical Focus & Positioning Recommendations
- **Focal Length:** The OV2640 stock lens is glued for infinity focus by default. Carefully break the glue bead with tweezers or an exacto knife, then rotate the lens ring counter-clockwise by $\approx 15\text{--}30^\circ$ to set sharp macro focus at $15\text{--}40\text{ cm}$.
- **Distance:** Position the camera $15\text{ to }40\text{ cm}$ from the plant canopy.
- **Illumination:** Ensure indirect, balanced ambient light. Avoid placing the camera facing directly toward a glaring window or heat source.
