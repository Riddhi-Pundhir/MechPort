# MechPort - ESP32-CAM Live Video Streamer Firmware

This folder contains the Arduino firmware sketch for the **AI-Thinker ESP32-CAM** module mounted on the MechPort robotic car. It streams real-time MJPEG video over your local Airtel Wi-Fi hotspot directly to the MechPort laptop dashboard.

---

## 1. Prerequisites & Arduino IDE Setup

### Step 1: Install Arduino IDE
Download and install [Arduino IDE (v2.0 or newer)](https://www.arduino.cc/en/software).

### Step 2: Install the ESP32 Board Package
1. Open Arduino IDE and navigate to **File -> Preferences** (or **Arduino IDE -> Settings** on macOS).
2. Locate the **Additional Boards Manager URLs** field and paste:
   ```text
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Click **OK**.
4. Open **Tools -> Board -> Boards Manager...** (or click the board icon in the left sidebar).
5. Search for **`esp32`** by *Espressif Systems* and click **Install**.

---

## 2. Board Selection & Configuration Settings

In the Arduino IDE top menu under **Tools**, select the following settings:

| Setting | Value |
|---|---|
| **Board** | **AI Thinker ESP32-CAM** |
| **CPU Frequency** | **240MHz (WiFi/BT)** |
| **Flash Frequency** | **80MHz** |
| **Flash Mode** | **QIO** |
| **Partition Scheme** | **Huge APP (3MB No OTA/1MB SPIFFS)** |
| **Core Debug Level** | **None** (or **Info**) |
| **PSRAM** | **Enabled** (*Crucial for 640x480 VGA resolution*) |
| **Port** | *Select your FTDI / USB-to-UART COM port (e.g. COM3, COM4)* |

> [!NOTE]
> All necessary libraries (`esp_camera.h`, `WiFi.h`, `esp_http_server.h`) are included automatically with the official ESP32 board package. No external library installations are needed.

---

## 3. Configuring Local Wi-Fi Credentials

To keep your real credentials safe and out of version control:

1. Inside `esp32_cam/mechport_camera/`, make a copy of `credentials.example.h` named `credentials.h`:
   ```bash
   cp esp32_cam/mechport_camera/credentials.example.h esp32_cam/mechport_camera/credentials.h
   ```
2. Open `credentials.h` and enter your Airtel Wi-Fi hotspot details:
   ```c
   #ifndef CREDENTIALS_H
   #define CREDENTIALS_H

   #define WIFI_SSID     "YOUR_AIRTEL_HOTSPOT_NAME"
   #define WIFI_PASSWORD "YOUR_AIRTEL_HOTSPOT_PASSWORD"

   #endif // CREDENTIALS_H
   ```
3. `credentials.h` is already added to `.gitignore`, so your credentials will never be committed to Git.

> [!IMPORTANT]
> The ESP32 Wi-Fi hardware supports **2.4 GHz only**. Make sure your Airtel phone hotspot is set to broadcast on the **2.4 GHz band** (or disable "5 GHz only").

---

## 4. Hardware Wiring for Flashing (FTDI Programmer to ESP32-CAM)

Because the AI-Thinker ESP32-CAM lacks an onboard USB chip, you need a standard FTDI / USB-to-TTL programmer:

```
FTDI Programmer                ESP32-CAM
----------------                ---------
5V (Set jumper to 5V) --------> 5V
GND --------------------------> GND
TX  --------------------------> U0R (GPIO 3)
RX  --------------------------> U0T (GPIO 1)
                                
                                GPIO 0 ---+ (Bridge with jumper wire)
                                GND ------+ (Only during flashing!)
```

| FTDI Pin | ESP32-CAM Pin | Description |
|---|---|---|
| **5V** | **5V** | Power (ESP32-CAM requires a stable 5V input, minimum 1A) |
| **GND** | **GND** | Ground reference |
| **TX** | **U0R** (GPIO 3) | FTDI Transmit to ESP32 Receive |
| **RX** | **U0T** (GPIO 1) | FTDI Receive to ESP32 Transmit |
| **GND** | **GPIO 0** | **Flashing Jumper**: Must be grounded to enter download mode |

---

## 5. Uploading the Firmware

1. **Bridge GPIO 0 to GND** on the ESP32-CAM using a jumper wire.
2. Plug the FTDI programmer into your laptop's USB port.
3. Press the tiny **RST (Reset)** button on the underside of the ESP32-CAM once to enter flashing mode.
4. In Arduino IDE, open `esp32_cam/mechport_camera/mechport_camera.ino`.
5. Click the **Upload** button (arrow icon).
6. When the console shows:
   ```text
   Connecting........_____....._____
   Writing at 0x00010000... (100 %)
   Leaving...
   Hard resetting via RTS pin...
   ```
7. **Disconnect the GPIO 0 to GND jumper wire**.
8. Press the **RST (Reset)** button on the ESP32-CAM once to reboot into normal running mode.

---

## 6. Serial Monitor & Finding the DHCP IP Address

1. In Arduino IDE, open **Tools -> Serial Monitor**.
2. Set the baud rate to **`115200 baud`**.
3. Press the **RST** button on the ESP32-CAM.
4. You should see the following startup diagnostic output:

```text
==================================================
         MechPort ESP32-CAM Video Streamer        
==================================================
[INFO] PSRAM detected! Enabling 640x480 VGA resolution.
[INIT] Initializing camera sensor... SUCCESS!
[WIFI] Setting up Wi-Fi connection...
[WIFI] Connecting to SSID 'MyAirtelHotspot' .......
[OK] Wi-Fi connected successfully!
     Assigned DHCP IP : 192.168.1.50
     Subnet Mask      : 255.255.255.0
     Gateway IP       : 192.168.1.1
     Signal (RSSI)    : -52 dBm
     MAC Address      : XX:XX:XX:XX:XX:XX
[HTTP] Web and stream server listening on Port 80
[HTTP] Secondary stream server listening on Port 81

--------------------------------------------------
 MechPort ESP32-CAM Ready for Dashboard Pairing!  
--------------------------------------------------
  >> Status Page   : http://192.168.1.50/
  >> MJPEG Stream  : http://192.168.1.50/stream
  >> Stream Port 81: http://192.168.1.50:81/stream
  >> Snapshot      : http://192.168.1.50/capture
--------------------------------------------------
Copy the MJPEG Stream URL into your MechPort dashboard Settings!
```

---

## 7. Connecting to the MechPort Dashboard

1. Copy the **MJPEG Stream URL** printed in the Serial Monitor (e.g. `http://192.168.1.50/stream` or `http://192.168.1.50:81/stream`).
2. Open your MechPort web dashboard in your laptop browser (`http://localhost:8000`).
3. Click the **Settings** tab in the top navigation.
4. Paste the URL into the **ESP32-CAM Stream URL** field and click **Save & Connect**.
5. The live video feed will immediately appear in the camera viewport!

---

## 8. Verification & Troubleshooting

- **Camera initialization failed with error code `0x20001` or `0x105`**:
  - Check that the camera ribbon cable is firmly seated and locked in its connector.
  - Make sure the 5V power supply has adequate current (poor USB ports cause brownouts).
  - Verify that **Tools -> PSRAM -> Enabled** is set in Arduino IDE.
- **Wi-Fi connection timed out**:
  - Verify your Airtel hotspot is turned ON and within range.
  - Confirm the hotspot is operating on the **2.4 GHz band**.
  - Check the spelling of the SSID and password in `credentials.h`.
- **Stream works in browser but dashboard shows offline**:
  - Verify CORS is enabled (already built into this firmware).
  - Check that the laptop and ESP32-CAM are connected to the exact same hotspot network.
