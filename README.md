# MechPort: Wi-Fi Controlled Robotic Car 🚗💨

MechPort is a Wi-Fi-controlled robotic car equipped with a **Raspberry Pi**, **L298N Dual H-Bridge motor driver**, two DC motor sides, an **ESP32-CAM** for real-time video streaming, and a responsive **Laptop Web Dashboard**. All components connect seamlessly through an Airtel Wi-Fi hotspot.

---

## Table of Contents
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Network & Wi-Fi Setup](#network--wi-fi-setup)
- [Hardware Wiring & Configuration](#hardware-wiring--configuration)
- [Safety Guarantees](#safety-guarantees)
- [Phase Status & Roadmap](#phase-status--roadmap)
- [Testing the Motor Controller Safely](#testing-the-motor-controller-safely)
- [Finding Local IP Addresses](#finding-local-ip-addresses)
- [Troubleshooting](#troubleshooting)

---

## Architecture

All devices connect to the same Airtel Wi-Fi hotspot on your local network:

```
                      +-----------------------------+
                      |        Airtel Hotspot       |
                      |  (Local Network / 192.168.x)|
                      +--------------+--------------+
                                     |
         +---------------------------+---------------------------+
         |                                                       |
         v                                                       v
+------------------+                                   +------------------+
|  Raspberry Pi    |                                   |    ESP32-CAM     |
|  - Motor Control | <---- HTTP POST /api/move ------- |  - HTTP Server   |
|  - Safety Watchdog| <--- HTTP GET /api/status ------ |  - MJPEG Stream  |
|  - L298N Driver  |                                   +--------+---------+
+--------+---------+                                            |
         |                                                      |
         | (GPIO)                                               | Live Stream
         v                                                      |
+------------------+                                            v
|  L298N + Motors  |                                   +------------------+
| (Left & Right)   |                                   |  Laptop Browser  |
+------------------+                                   | Control Dashboard|
                                                       +------------------+
```

---

## Project Structure

```
MechPort/
├── .env.example                     <- Central configuration template (copy to .env)
├── .gitignore                       <- Protects secrets and build artifacts
├── README.md                        <- Project master documentation
│
├── raspberry_pi/                    <- Raspberry Pi Subsystem
│   ├── config.py                    <- Centralized hardware, GPIO & server config
│   ├── motor_control.py             <- L298N motor driver with watchdog & safety logic
│   ├── test_motor.py                <- Automated & interactive motor test harness
│   ├── server.py                    <- REST API HTTP server (Phase 3)
│   ├── requirements.txt             <- Python dependencies
│   └── README.md                    <- Raspberry Pi wiring & hardware guide
│
├── dashboard/                       <- Laptop Web Dashboard Subsystem (Phase 4)
│   ├── index.html                   <- Control center UI layout
│   ├── style.css                    <- Modern dark theme styling
│   └── script.js                    <- Keyboard bindings & network telemetry
│
└── esp32_cam/                       <- ESP32-CAM Video Subsystem (Phase 5)
    └── mechport_camera/
        ├── mechport_camera.ino      <- Arduino firmware sketch
        └── camera_pins.h            <- Standard AI-Thinker pin definitions
```

---

## Network & Wi-Fi Setup

1. Turn on your **Airtel Wi-Fi Hotspot**.
2. Connect your **Laptop**, **Raspberry Pi**, and **ESP32-CAM** to this hotspot.
3. Keep real credentials out of version control:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Enter your hotspot name (`WIFI_SSID`) and password (`WIFI_PASSWORD`).

---

## Hardware Wiring & Configuration

### Raspberry Pi to L298N Motor Driver

| L298N Pin | Function | Suggested BCM Pin | Config Variable in `config.py` |
|---|---|---|---|
| **ENA** | Left Speed (PWM) | *(Optional)* BCM 12 or 18 | `PIN_ENA` (Leave None if 5V jumper present) |
| **IN1** | Left Forward | BCM 17 | `PIN_IN1` |
| **IN2** | Left Backward | BCM 27 | `PIN_IN2` |
| **IN3** | Right Forward | BCM 22 | `PIN_IN3` |
| **IN4** | Right Backward | BCM 23 | `PIN_IN4` |
| **ENB** | Right Speed (PWM) | *(Optional)* BCM 13 or 19 | `PIN_ENB` (Leave None if 5V jumper present) |
| **GND** | Ground Reference | **Raspberry Pi GND** | *Mandatory shared ground connection* |

> [!IMPORTANT]
> **No Guessed Pins**: The code initializes with pins as `None`. You must specify your physical BCM pins in `raspberry_pi/config.py` or `.env` before running on hardware.

---

## Safety Guarantees

1. **Safe Startup (Default STOP)**: When the Raspberry Pi boots or the script initializes, all motor direction pins are driven `LOW`, guaranteeing zero motion until a valid command is received.
2. **Watchdog Auto-Stop**: An active watchdog timer monitors command heartbeats. If communication ceases for more than `WATCHDOG_TIMEOUT_SECONDS` (default: 1.5s), the car stops automatically.
3. **Safe Shutdown**: Clean exit handlers (`atexit`, `SIGINT`, `SIGTERM`) ensure that if the program is stopped (e.g. Ctrl+C), motors stop and GPIO pins are safely released.
4. **Mock Simulation Mode**: Automatically available for testing without physical hardware on laptops/PCs.

---

## Testing the Motor Controller Safely

### Step 1: Elevate the Car
> [!CAUTION]
> Always prop the car up on a stand so all wheels rotate freely in the air before testing motor movement.

### Step 2: Run Mock / Simulation Test (on PC or Laptop)
```bash
cd raspberry_pi
python test_motor.py --mock
```

### Step 3: Run Automated Hardware Test (on Raspberry Pi)
After filling in your BCM pins in `config.py`:
```bash
cd raspberry_pi
python test_motor.py
```

### Step 4: Run Interactive Keyboard Test
Control the motors directly using `W`, `A`, `S`, `D`, and `SPACE`:
```bash
python test_motor.py --interactive
```

---

## Finding Local IP Addresses

On your Airtel Hotspot network:

- **Raspberry Pi**: Run `hostname -I` on the Pi terminal to find its IP (e.g., `192.168.1.100`).
- **ESP32-CAM**: Open Arduino Serial Monitor at 115200 baud when booting; it prints its assigned IP address (e.g., `192.168.1.50`).
- **Laptop**: Check connected devices in your Airtel Hotspot admin page (`192.168.1.1`).

---

## Troubleshooting

- **Motors not turning**:
  - Check that the L298N GND is connected to the Raspberry Pi GND pin.
  - Verify battery voltage powering the L298N (needs 7V–12V for DC motors).
  - If using ENA/ENB without PWM, check that the 5V jumper caps are firmly in place.
- **Car turns in reverse or opposite direction**:
  - Swap the polarity of the wires connecting the motor to the L298N screw terminals, or swap `PIN_IN1` and `PIN_IN2` (or `PIN_IN3` and `PIN_IN4`) in `config.py`.
- **Watchdog stopping motors too fast**:
  - Increase `WATCHDOG_TIMEOUT_SECONDS` in `config.py` or `.env`.

---

---

## Running the Web Dashboard (Laptop Control Center)

The dashboard allows you to control the car with keyboard keys (`W`, `A`, `S`, `D`, `SPACE`), view real-time telemetry, and watch the live ESP32-CAM video stream.

### 1. Start the Raspberry Pi Server
On the Raspberry Pi (or in mock mode on your laptop):
```bash
cd raspberry_pi
python server.py
```

### 2. Launch the Web Dashboard
You can open `dashboard/index.html` directly in any modern browser (Chrome, Edge, Firefox, Safari), or serve it locally:
```bash
# From project root
python -m http.server 8000 --directory dashboard
```
Open **`http://localhost:8000`** in your browser.

### 3. Configuring Device IP Addresses in the UI
You **do not** need to edit code to point the dashboard to your hardware!
1. Click the **⚙ Settings** button in the top right corner.
2. Enter your **Raspberry Pi API Base URL** (e.g. `http://192.168.1.100:5000` or `http://127.0.0.1:5000`).
3. Enter your **ESP32-CAM Stream URL** (e.g. `http://192.168.1.50:81/stream`).
4. Click **Save & Connect**. Settings are saved in your browser's local storage.

### 4. Driving Controls
| Key | Action | Description |
|---|---|---|
| **W** / **↑** | `FORWARD` | Moves both wheels forward |
| **S** / **↓** | `BACKWARD` | Moves both wheels backward |
| **A** / **←** | `LEFT` | Differential pivot turn left |
| **D** / **→** | `RIGHT` | Differential pivot turn right |
| **SPACE** / **Esc** | `STOP` | Instant Emergency Stop |
| *Key Release* | `STOP` | Automatically halts vehicle when movement key is released |

---

## ESP32-CAM Video Streamer Setup

The AI-Thinker ESP32-CAM provides live video streaming over your Airtel hotspot:
- Firmware Sketch: [esp32_cam/mechport_camera/mechport_camera.ino](file:///c:/Users/Riddhi/OneDrive/%E3%83%89%E3%82%AD%E3%83%A5%E3%83%A1%E3%83%B3%E3%83%88/mechport/MechPort/esp32_cam/mechport_camera/mechport_camera.ino)
- Complete Upload & Hardware Wiring Guide: [esp32_cam/README.md](file:///c:/Users/Riddhi/OneDrive/%E3%83%89%E3%82%AD%E3%83%A5%E3%83%A1%E3%83%B3%E3%83%88/mechport/MechPort/esp32_cam/README.md)
- Credentials Template: [esp32_cam/mechport_camera/credentials.example.h](file:///c:/Users/Riddhi/OneDrive/%E3%83%89%E3%82%AD%E3%83%A5%E3%83%A1%E3%83%B3%E3%83%88/mechport/MechPort/esp32_cam/mechport_camera/credentials.example.h)

---

## Phase Status & Roadmap

- [x] **Phase 1: Project Structure & Centralized Configuration** (Complete)
- [x] **Phase 2: Safe Motor Control Module with Watchdog & Tests** (Complete)
- [x] **Phase 3: Raspberry Pi REST API / Flask Server** (Complete)
- [x] **Phase 4: Laptop Web Dashboard & Keyboard Controller** (Complete)
- [x] **Phase 5: ESP32-CAM Live Video Streamer Firmware** (Complete)
- [ ] **Phase 6: End-to-End Integration & System Verification** (Upcoming)


