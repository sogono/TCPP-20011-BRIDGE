"""
Virtual DirectInput Device via vJoy

Wraps vJoy to create a virtual joystick visible to any PC game as a
standard DirectInput device. Used as the output target for the
Shinkansen controller bridge.

vJoy device layout:
  Axes:    X (Brake), Y (Power)
  POV:     Hat switch 1 (D-Pad)
  Buttons: 1=A, 2=B, 3=C, 4=D, 5=Select, 6=Start, 7=Horn
           8=BrakeUp, 9=BrakeDown, 10=PowerUp, 11=PowerDown
           (buttons 8-11 used only in sequential lever mode)

Requires:
  - vJoy driver installed (https://github.com/njz3/vJoy/)
  - vJoy device 1 configured with: 2+ axes, 11+ buttons, 1 continuous POV
  - pip install pyvjoystick
"""

import time
from enum import IntEnum

try:
    import pyvjoystick.vjoy as vjoy
    VJOY_AVAILABLE = True
except ImportError:
    VJOY_AVAILABLE = False


# vJoy axis range
AXIS_MIN = 0x1
AXIS_MAX = 0x8000
AXIS_CENTER = 0x4000

# POV hat values (continuous POV, units of 1/100 degree, -1 = center/neutral)
POV_CENTER = -1
POV_N  = 0
POV_NE = 4500
POV_E  = 9000
POV_SE = 13500
POV_S  = 18000
POV_SW = 22500
POV_W  = 27000
POV_NW = 31500


class VJoyButton(IntEnum):
    """Virtual button assignments on the vJoy device."""
    A          = 1
    B          = 2
    C          = 3
    D          = 4
    SELECT     = 5
    START      = 6
    HORN       = 7
    BRAKE_UP   = 8
    BRAKE_DOWN = 9
    POWER_UP   = 10
    POWER_DOWN = 11


class VirtualJoystick:
    """
    Manages a single vJoy virtual joystick device.

    Provides high-level methods for setting axes, buttons, and POV hat,
    with a batched update model for efficiency.
    """

    def __init__(self, device_id: int = 1):
        if not VJOY_AVAILABLE:
            raise RuntimeError(
                "pyvjoystick is not installed. Run: pip install pyvjoystick\n"
                "Also ensure vJoy driver is installed: https://github.com/njz3/vJoy/"
            )

        self.device_id = device_id
        self._device = None

    def open(self) -> None:
        """Acquire the vJoy device."""
        try:
            self._device = vjoy.VJoyDevice(self.device_id)
        except Exception as e:
            raise RuntimeError(
                f"Failed to open vJoy device {self.device_id}: {e}\n"
                f"Ensure vJoy is installed and device {self.device_id} is configured with:\n"
                f"  - At least 2 axes (X, Y)\n"
                f"  - At least 11 buttons\n"
                f"  - 1 continuous POV hat switch"
            ) from e

        self._device.reset()
        # Set axes to center
        self._device.set_axis(vjoy.HID_USAGE.X, AXIS_CENTER)
        self._device.set_axis(vjoy.HID_USAGE.Y, AXIS_CENTER)
        print(f"  vJoy device {self.device_id} acquired and reset.")

    def close(self) -> None:
        """Release the vJoy device."""
        if self._device is not None:
            try:
                self._device.reset()
            except Exception:
                pass
            self._device = None

    # ─── Axis Control ────────────────────────────────────────────────────

    def set_brake_axis(self, value: int) -> None:
        """Set the brake axis (X). Value in range AXIS_MIN..AXIS_MAX."""
        if self._device is None:
            return
        value = max(AXIS_MIN, min(AXIS_MAX, value))
        self._device.set_axis(vjoy.HID_USAGE.X, value)

    def set_power_axis(self, value: int) -> None:
        """Set the power axis (Y). Value in range AXIS_MIN..AXIS_MAX."""
        if self._device is None:
            return
        value = max(AXIS_MIN, min(AXIS_MAX, value))
        self._device.set_axis(vjoy.HID_USAGE.Y, value)

    def set_brake_axis_float(self, fraction: float) -> None:
        """Set brake axis from 0.0 (min) to 1.0 (max)."""
        fraction = max(0.0, min(1.0, fraction))
        value = int(AXIS_MIN + fraction * (AXIS_MAX - AXIS_MIN))
        self.set_brake_axis(value)

    def set_power_axis_float(self, fraction: float) -> None:
        """Set power axis from 0.0 (min) to 1.0 (max)."""
        fraction = max(0.0, min(1.0, fraction))
        value = int(AXIS_MIN + fraction * (AXIS_MAX - AXIS_MIN))
        self.set_power_axis(value)

    # ─── Button Control ──────────────────────────────────────────────────

    def set_button(self, button: int, pressed: bool) -> None:
        """Set a button state. button is 1-indexed."""
        if self._device is None:
            return
        self._device.set_button(button, 1 if pressed else 0)

    def pulse_button(self, button: int, duration_ms: int = 50) -> None:
        """Press and release a button with a short delay."""
        self.set_button(button, True)
        time.sleep(duration_ms / 1000.0)
        self.set_button(button, False)

    # ─── POV Hat Control ─────────────────────────────────────────────────

    def set_pov(self, angle: int) -> None:
        """
        Set continuous POV hat.
        angle: value in 1/100 degrees (0=N, 9000=E, 18000=S, 27000=W)
               or -1 for center/neutral.
        """
        if self._device is None:
            return
        self._device._data.bHats = angle
        self._device.update()

    # ─── Context Manager ─────────────────────────────────────────────────

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
