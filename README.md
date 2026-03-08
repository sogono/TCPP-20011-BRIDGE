# Densha de GO! Shinkansen Controller (TCPP-20011) — USB Driver

A Python utility to interface with the **Taito TCPP-20011 Shinkansen** train simulator controller on Windows via USB. This controller was originally designed for PlayStation 2 and connects directly via USB.

## Prerequisites

1. **Controller connected via USB**
2. **libwdi/WinUSB driver installed** (e.g. via [Zadig](https://zadig.akeo.ie/))
3. **Python 3.10+**
4. **libusb** — the `libusb-1.0.dll` must be accessible (install via pip or place in PATH)
5. **vJoy driver** — required for the virtual DirectInput bridge (`bridge.py`)
6. **ViGEmBus driver** — required for the virtual XInput bridge (`xinput_bridge.py`), auto-installed with `pip install vgamepad`

## Installation

```bash
cd denusb
pip install -r requirements.txt
```

## Usage

### 1. Discover & Identify Controller
```bash
python discover.py          # Scan for the controller
python discover.py --read   # Scan + read a few input samples
```

### 2. Interactive Test Tool
```bash
python interactive.py          # Console only
python interactive.py --gui    # Console + GUI window
```

Menu options:
- **Monitor Inputs** — live view of lever positions, buttons, pedal, d-pad
- **Raw Byte Dump** — hex/binary for protocol reverse engineering
- **Control Outputs** — set speedometer, gauge, limit, door lamp, rumble
- **Full Duplex** — simultaneous input monitoring + output control

### 3. Virtual DirectInput Bridge
```bash
python bridge.py                                   # Both levers as analog axes
python bridge.py --gui                             # Bridge + GUI window
python bridge.py --brake analog --power sequential  # Mix modes per lever
python bridge.py --brake incremental --step 3000    # Incremental with custom step
python bridge.py --vjoy-id 2                        # Use vJoy device 2
```

#### Lever Modes

| Mode          | Behaviour                                                                 |
|---------------|--------------------------------------------------------------------------|
| **analog**    | Lever notch position maps directly to a virtual axis value (default)     |
| **incremental** | Axis starts at center and accumulates +/- per notch change (throttle wheel) |
| **sequential** | Each notch change fires a momentary button press (up or down)           |

#### Virtual Device Button Map

| vJoy Button | Physical Input | Notes                      |
|:-----------:|----------------|----------------------------|
| 1           | A              |                            |
| 2           | B              |                            |
| 3           | C              |                            |
| 4           | D              |                            |
| 5           | Select         |                            |
| 6           | Start          |                            |
| 7           | Horn Pedal     |                            |
| 8           | Brake Up       | Sequential mode only       |
| 9           | Brake Down     | Sequential mode only       |
| 10          | Power Up       | Sequential mode only       |
| 11          | Power Down     | Sequential mode only       |
| POV Hat 1   | D-Pad          | 8-way + center             |
| Axis X      | Brake lever    | Analog/Incremental modes   |
| Axis Y      | Power lever    | Analog/Incremental modes   |

### 4. Virtual XInput Bridge (Xbox 360)
```bash
python xinput_bridge.py                                  # Default TSW5-friendly mapping
python xinput_bridge.py --gui                            # Bridge + GUI window
python xinput_bridge.py --pulse-ms 100                   # Longer button pulses
python xinput_bridge.py --brake-up LB --brake-down RB    # Remap lever buttons
python xinput_bridge.py --power-up A --power-down B      # Remap power to face buttons
```

Use this bridge for games that only support XInput (Xbox 360) controllers.
Each lever notch change fires a momentary button/trigger press on the virtual Xbox 360 pad.

#### Default XInput Mapping

| Physical Input     | Xbox 360 Button | Notes                              |
|--------------------|:---------------:|------------------------------------|
| Brake notch up     | RT              | Momentary right trigger press      |
| Brake notch down   | LT              | Momentary left trigger press       |
| Power notch up     | RB              | Momentary right shoulder press     |
| Power notch down   | LB              | Momentary left shoulder press      |
| Button A           | A               |                                    |
| Button B           | B               |                                    |
| Button C           | X               |                                    |
| Button D           | Y               |                                    |
| Select             | Back            |                                    |
| Start              | Start           |                                    |
| Horn Pedal         | LS              | Left stick click                   |
| D-Pad              | D-Pad           | Direct 1:1 mapping                 |

All button assignments are configurable via CLI flags (`--brake-up`, `--power-down`, `--horn`, etc.).
Valid button names: `A B X Y LB RB LT RT LS RS START BACK GUIDE`

#### ViGEmBus Setup

The XInput bridge requires the ViGEmBus driver. Installing `vgamepad` via pip will
automatically prompt you to install it:

```bash
pip install vgamepad
```

If the driver prompt doesn't appear, download it manually from
[github.com/ViGEm/ViGEmBus/releases](https://github.com/ViGEm/ViGEmBus/releases).

### 5. GUI Window (Standalone)
```bash
python gui.py                  # Opens GUI reading directly from controller
```

The GUI shows real-time controller state: brake/power lever notch bars, D-pad,
face buttons (A/B/C/D), Select, Start, horn pedal, and raw input bytes.
Add `--gui` to `interactive.py`, `bridge.py`, or `xinput_bridge.py` to show the
GUI alongside the console.

### 6. Programmatic Usage
```python
from controller import ShinkansenController, ControllerOutput

with ShinkansenController() as ctrl:
    # Read input
    state = ctrl.read_input()
    print(f"Brake: {state.brake_name}, Power: {state.power_name}")
    print(f"Pedal: {state.pedal_pressed}, Buttons: {state.buttons_pressed}")

    # Set displays
    output = ControllerOutput(
        speedometer=120,
        speed_gauge=8,        # 8 LEDs = ~120 km/h
        atc_limit=130,
        limit_approach=0,
        door_lamp=True,
    )
    ctrl.write_output(output)
```

## vJoy Setup

The virtual DirectInput bridge requires [vJoy](https://github.com/njz3/vJoy/releases) to create a virtual joystick that games can bind to.

### 1. Install vJoy

1. Download the latest installer from [github.com/njz3/vJoy/releases](https://github.com/njz3/vJoy/releases).
2. Run the installer. When prompted, also install **Configure vJoy** and **vJoy Monitor**.
3. Reboot if prompted.

### 2. Configure a Virtual Device

Open **Configure vJoy** (search the Start menu for "Configure vJoy") and set up **Device 1**:

| Setting                | Required Value                  |
|------------------------|----------------------------------|
| **Axes**               | Enable **X** and **Y**          |
| **Number of Buttons**  | **11** (or more)                |
| **POV Hat Switch**     | **1 Continuous** POV            |

Click **Apply** to save. You should see "Device 1" appear in **vJoy Monitor** with a green status.

### 3. Verify

Run the bridge to confirm vJoy is working:

```bash
python bridge.py
```

If you see `vJoy device 1 acquired and reset.`, the setup is correct.

### Troubleshooting

- **"vJoy does not appear to be installed"** — Reinstall vJoy and reboot.
- **"Failed to open vJoy device 1"** — Open Configure vJoy and ensure Device 1 is enabled with the settings above.
- **"vJoyNotEnabledException"** — The vJoy driver is installed but no devices are configured. Open Configure vJoy and click Apply.
- **"old version" warning** — The bridge still works, but consider updating vJoy to the latest release.
- **Using a different device ID** — Pass `--vjoy-id 2` (etc.) to `bridge.py` and configure that device in Configure vJoy.

## Files

| File               | Purpose                                                    |
|--------------------|------------------------------------------------------------|
| `controller.py`    | Core driver: device class, protocol parsing, I/O           |
| `discover.py`      | USB device scanner and identification                       |
| `interactive.py`   | Interactive console test tool                               |
| `bridge.py`        | Virtual DirectInput bridge (controller → vJoy)              |
| `xinput_bridge.py` | Virtual XInput bridge (controller → Xbox 360 via ViGEmBus) |
| `virtual_device.py`| vJoy wrapper: axis, button, POV hat abstraction             |
| `xinput_device.py` | ViGEmBus wrapper: Xbox 360 virtual controller               |
| `gui.py`           | Tkinter GUI window showing live controller state            |
| `requirements.txt` | Python dependencies                                        |

---

## Technical Details

### Controller Identification

| Property         | Value                    |
|------------------|--------------------------|
| **Manufacturer** | TAITO                    |
| **Product**      | TAITO_DENSYA_CON_T02     |
| **Serial**       | TCPP20011                |
| **Vendor ID**    | `0x0AE4`                |
| **Product ID**   | `0x0005`                |
| **USB Version**  | 1.10                     |
| **Device Class** | `0xFF` (Vendor-Specific) |
| **Interface**    | HID (class `0x03`), no standard HID descriptors |
| **Endpoint**     | `0x81` Interrupt IN, 8 bytes, 20ms interval |

### Physical Layout

#### Inputs
- **Brake handle** — 7 notches (B1–B7) + Emergency + Released
- **Power handle** — 13 notches (P1–P13) + Neutral
- **Horn pedal** — 3.5mm jack, binary (pressed/released)
- **D-Pad** — 8 directions + center
- **Buttons** — A, B, C, D, Select, Start
- **Rumble motors** — one in each handle (output-driven)

#### Outputs (Displays)
- **Numerical speedometer** — 3-digit display, 0–999 km/h
- **Speed gauge bar** — up to 22 LEDs (15 km/h increments)
- **Limit approach bar** — up to 10 LEDs above speedometer (10 km/h below speed limit)
- **ATC speed limit** — 3-digit display, 0–999 km/h
- **Door lamp** — single indicator light
- **Rumble motors** — left and right, on/off

### Input Protocol

The controller sends **6-byte reports** via interrupt IN endpoint `0x81`:

| Byte 1 | Byte 2 | Byte 3 | Byte 4 | Byte 5  | Byte 6   |
|:------:|:------:|:------:|:------:|:-------:|:--------:|
| Brake  | Power  | Pedal  | D-Pad  | Buttons | *Unused* |

#### Brake Handle (Byte 1)

| Position   | Value  |
|------------|--------|
| Released   | `0x1C` |
| B1         | `0x38` |
| B2         | `0x54` |
| B3         | `0x70` |
| B4         | `0x8B` |
| B5         | `0xA7` |
| B6         | `0xC3` |
| B7         | `0xDF` |
| Emergency  | `0xFB` |

> **Note:** The controller sends `0xFF` during lever transitions between notches.
> The driver ignores these and retains the last valid position.

#### Power Handle (Byte 2)

| Position   | Value  |
|------------|--------|
| N (Neutral)| `0x12` |
| P1         | `0x24` |
| P2         | `0x36` |
| P3         | `0x48` |
| P4         | `0x5A` |
| P5         | `0x6C` |
| P6         | `0x7E` |
| P7         | `0x90` |
| P8         | `0xA2` |
| P9         | `0xB4` |
| P10        | `0xC6` |
| P11        | `0xD7` |
| P12        | `0xE9` |
| P13        | `0xFB` |

> **Note:** The controller sends `0xFF` during lever transitions between notches.
> The driver ignores these and retains the last valid position.

#### Horn Pedal (Byte 3)

| State    | Value  |
|----------|--------|
| Released | `0xFF` |
| Pressed  | `0x00` |

#### D-Pad (Byte 4)

| Direction    | Value  |
|--------------|--------|
| N (Up)       | `0x00` |
| NE           | `0x01` |
| E (Right)    | `0x02` |
| SE           | `0x03` |
| S (Down)     | `0x04` |
| SW           | `0x05` |
| W (Left)     | `0x06` |
| NW           | `0x07` |
| Center/None  | `0x08` |

#### Buttons (Byte 5) — Bitmask

| Bit | Button |
|-----|--------|
| 0   | D      |
| 1   | C      |
| 2   | B      |
| 3   | A      |
| 4   | SELECT |
| 5   | START  |

`0` = released, `1` = pressed.

### Output Protocol

The controller receives display updates via **USB control transfer**:

#### Setup Packet

| bmRequestType | bRequest | wValue   | wIndex   | wLength  |
|:-------------:|:--------:|:--------:|:--------:|:--------:|
| `0x40`        | `0x09`   | `0x0301` | `0x0000` | `0x0008` |

#### Data Payload (8 bytes)

| Byte 1      | Byte 2       | Byte 3                     | Byte 4      | Bytes 5–6   | Bytes 7–8 |
|:-----------:|:------------:|:--------------------------:|:-----------:|:-----------:|:---------:|
| Left Rumble | Right Rumble | Door Lamp + Limit Approach | Speed Gauge | Speedometer | ATC Limit |

#### Byte Details

- **Left/Right Rumble** (bytes 1–2): `0x00` = Off, `0x01` = On
- **Door Lamp + Limit Approach** (byte 3):
  - High nibble: `0x0X` = Off, `0x8X` = On
  - Low nibble: `0x0`–`0xA` = number of lit LEDs (0–10)
- **Speed Gauge** (byte 4): `0x00`–`0x16` (0–22 LEDs, 15 km/h increments)
- **Speedometer** (bytes 5–6): BCD 8421, Little Endian. E.g. 120 km/h = `0x0120` → bytes `[0x20, 0x01]`
- **ATC Limit** (bytes 7–8): BCD 8421, Little Endian. Same encoding as speedometer.

## References

- [Train Controller Database — TCPP-20011](https://traincontrollerdb.marcriera.cat/hardware/tcpp20011)
- [Densha de GO! Controller Documentation (GitHub Gist)](https://gist.github.com/QuintusHegie/487348d07e3e24f0c644a9ec23bdce26)
- [PyUSB Documentation](https://pyusb.github.io/pyusb/)
- [vJoy Virtual Joystick](https://github.com/njz3/vJoy/)
- [pyvjoystick (Python vJoy bindings)](https://github.com/fsadannn/pyvjoystick/)
- [vgamepad (Python ViGEmBus bindings)](https://github.com/yannbouteiller/vgamepad)
- [ViGEmBus Virtual Gamepad Driver](https://github.com/ViGEm/ViGEmBus)
