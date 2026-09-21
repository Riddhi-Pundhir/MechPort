# MechPort - Raspberry Pi Motor Control

This subsystem runs on the Raspberry Pi mounted on the MechPort robotic car. It controls the two DC motor channels (left and right) through an L298N Dual H-Bridge motor driver with strict safety guarantees.

---

## Hardware Connections (Raspberry Pi to L298N)

The L298N motor driver interfaces between the Raspberry Pi's low-voltage GPIO pins and the high-current DC motors.

### L298N Pin Table

| L298N Pin | Function | Raspberry Pi Pin (BCM) | Configuration Variable |
|---|---|---|---|
| **ENA** | Left Motor Speed (PWM) | *(User Choice)* e.g. BCM 12 or 18 | `PIN_ENA` (Optional if 5V jumper present) |
| **IN1** | Left Motor Forward | *(User Choice)* e.g. BCM 17 | `PIN_IN1` (**Required**) |
| **IN2** | Left Motor Backward | *(User Choice)* e.g. BCM 27 | `PIN_IN2` (**Required**) |
| **IN3** | Right Motor Forward | *(User Choice)* e.g. BCM 22 | `PIN_IN3` (**Required**) |
| **IN4** | Right Motor Backward | *(User Choice)* e.g. BCM 23 | `PIN_IN4` (**Required**) |
| **ENB** | Right Motor Speed (PWM) | *(User Choice)* e.g. BCM 13 or 19 | `PIN_ENB` (Optional if 5V jumper present) |
| **GND** | Common Ground | Raspberry Pi GND pin | *Direct wire* (**Critical! Must share GND**) |

> [!IMPORTANT]
> **COMMON GROUND**: You MUST connect the GND pin of the L298N to one of the GND pins on the Raspberry Pi. Without a common ground reference, the control signals will float and the motors will behave erratically or fail to respond.

---

## Configuring GPIO Pins

Before running on physical hardware:

1. Copy `.env.example` to `.env` in the project root:
   ```bash
   cp ../.env.example ../.env
   ```
2. Open `raspberry_pi/config.py` (or `.env`) and enter your actual BCM pin numbers:
   ```python
   PIN_IN1 = 17  # Replace with your actual BCM pin
   PIN_IN2 = 27  # Replace with your actual BCM pin
   PIN_IN3 = 22  # Replace with your actual BCM pin
   PIN_IN4 = 23  # Replace with your actual BCM pin
   ```
3. If you removed the 5V black jumper caps from ENA and ENB to enable speed control, set `PIN_ENA` and `PIN_ENB`. If the jumpers are kept in place, leave them as `None`.

---

## Safety Guarantees

1. **Safe Startup**: Motors always initialize to `STOP` (all direction pins driven LOW, PWM set to 0).
2. **Watchdog Protection**: If no command is received for `WATCHDOG_TIMEOUT_SECONDS` (default: 1.5 seconds), the motors automatically stop.
3. **Safe Shutdown**: The system registers process exit handlers (`atexit`, `SIGINT`, `SIGTERM`) to stop motors and reset GPIO pins on termination or Ctrl+C.
4. **Mock Simulation Mode**: Automatically runs in mock mode when tested on laptops/PCs or when physical pins are unconfigured.

---

## How to Test Safely

### 1. Test in Simulation / Mock Mode (PC or Laptop)
```bash
python test_motor.py --mock
```
This runs the full test suite in simulation without requiring physical hardware.

### 2. Physical Hardware Test (Wheels Elevated)
> [!CAUTION]
> **ELEVATE CAR BEFORE TESTING**: Always place the robotic car on a block or box so that all wheels are raised off the table/ground. This prevents runaway car incidents during testing!

```bash
python test_motor.py
```

### 3. Interactive Keyboard Test
To test motor response interactively via keyboard keys (W, A, S, D, SPACE):
```bash
python test_motor.py --interactive
```
