"""
Virtual XInput (Xbox 360) Controller via ViGEmBus

Wraps vgamepad to create a virtual Xbox 360 controller visible to any
XInput-compatible PC game. Used as the output target for the XInput
bridge mode.

Xbox 360 controller layout:
  Buttons:  A, B, X, Y, LB, RB, Back, Start, Guide, LS, RS
  Triggers: LT (0-255), RT (0-255)
  Sticks:   Left (-32768..32767), Right (-32768..32767)
  D-Pad:    Up, Down, Left, Right

Requires:
  - ViGEmBus driver installed (bundled with vgamepad on first install)
  - pip install vgamepad
"""

import time

try:
    import vgamepad as vg
    VGAMEPAD_AVAILABLE = True
except ImportError:
    VGAMEPAD_AVAILABLE = False


class XButton:
    """Xbox 360 button constants matching vgamepad's XUSB_BUTTON."""
    DPAD_UP        = 0x0001
    DPAD_DOWN      = 0x0002
    DPAD_LEFT      = 0x0004
    DPAD_RIGHT     = 0x0008
    START          = 0x0010
    BACK           = 0x0020
    LEFT_THUMB     = 0x0040
    RIGHT_THUMB    = 0x0080
    LEFT_SHOULDER  = 0x0100
    RIGHT_SHOULDER = 0x0200
    GUIDE          = 0x0400
    A              = 0x1000
    B              = 0x2000
    X              = 0x4000
    Y              = 0x8000


class VirtualXInputDevice:
    """
    Manages a virtual Xbox 360 controller via ViGEmBus.

    Provides high-level methods for setting buttons, triggers, sticks,
    and D-pad with immediate updates.
    """

    def __init__(self):
        if not VGAMEPAD_AVAILABLE:
            raise RuntimeError(
                "vgamepad is not installed. Run: pip install vgamepad\n"
                "The first install will also set up the ViGEmBus driver."
            )
        self._gamepad = None

    def open(self) -> None:
        """Create and connect the virtual Xbox 360 controller."""
        try:
            self._gamepad = vg.VX360Gamepad()
        except Exception as e:
            raise RuntimeError(
                f"Failed to create virtual Xbox 360 controller: {e}\n"
                "Ensure ViGEmBus driver is installed.\n"
                "Run: pip install vgamepad  (installs driver on first run)"
            ) from e

        self._gamepad.reset()
        self._gamepad.update()
        print("  Virtual Xbox 360 controller connected via ViGEmBus.")

    def close(self) -> None:
        """Disconnect the virtual controller."""
        if self._gamepad is not None:
            try:
                self._gamepad.reset()
                self._gamepad.update()
            except Exception:
                pass
            self._gamepad = None

    # ─── Button Control ──────────────────────────────────────────────────

    def press_button(self, button: int) -> None:
        """Press a button. Use XButton constants."""
        if self._gamepad is None:
            return
        self._gamepad.press_button(button=button)
        self._gamepad.update()

    def release_button(self, button: int) -> None:
        """Release a button. Use XButton constants."""
        if self._gamepad is None:
            return
        self._gamepad.release_button(button=button)
        self._gamepad.update()

    def set_button(self, button: int, pressed: bool) -> None:
        """Set a button to pressed or released."""
        if pressed:
            self.press_button(button)
        else:
            self.release_button(button)

    def pulse_button(self, button: int, duration_ms: int = 80) -> None:
        """Press and release a button with a short delay."""
        self.press_button(button)
        time.sleep(duration_ms / 1000.0)
        self.release_button(button)

    # ─── Trigger Control ─────────────────────────────────────────────────

    def set_left_trigger(self, value: int) -> None:
        """Set left trigger. Value 0-255."""
        if self._gamepad is None:
            return
        self._gamepad.left_trigger(value=max(0, min(255, value)))
        self._gamepad.update()

    def set_right_trigger(self, value: int) -> None:
        """Set right trigger. Value 0-255."""
        if self._gamepad is None:
            return
        self._gamepad.right_trigger(value=max(0, min(255, value)))
        self._gamepad.update()

    def set_left_trigger_float(self, value: float) -> None:
        """Set left trigger. Value 0.0-1.0."""
        if self._gamepad is None:
            return
        self._gamepad.left_trigger_float(value_float=max(0.0, min(1.0, value)))
        self._gamepad.update()

    def set_right_trigger_float(self, value: float) -> None:
        """Set right trigger. Value 0.0-1.0."""
        if self._gamepad is None:
            return
        self._gamepad.right_trigger_float(value_float=max(0.0, min(1.0, value)))
        self._gamepad.update()

    # ─── Stick Control ───────────────────────────────────────────────────

    def set_left_stick(self, x: int = 0, y: int = 0) -> None:
        """Set left stick. Values -32768 to 32767."""
        if self._gamepad is None:
            return
        self._gamepad.left_joystick(x_value=x, y_value=y)
        self._gamepad.update()

    def set_right_stick(self, x: int = 0, y: int = 0) -> None:
        """Set right stick. Values -32768 to 32767."""
        if self._gamepad is None:
            return
        self._gamepad.right_joystick(x_value=x, y_value=y)
        self._gamepad.update()

    # ─── D-Pad Convenience ───────────────────────────────────────────────

    def release_dpad(self) -> None:
        """Release all D-pad directions."""
        if self._gamepad is None:
            return
        for btn in (XButton.DPAD_UP, XButton.DPAD_DOWN,
                    XButton.DPAD_LEFT, XButton.DPAD_RIGHT):
            self._gamepad.release_button(button=btn)
        self._gamepad.update()

    def set_dpad(self, up: bool = False, down: bool = False,
                 left: bool = False, right: bool = False) -> None:
        """Set D-pad state directly."""
        if self._gamepad is None:
            return
        for btn, pressed in ((XButton.DPAD_UP, up), (XButton.DPAD_DOWN, down),
                             (XButton.DPAD_LEFT, left), (XButton.DPAD_RIGHT, right)):
            if pressed:
                self._gamepad.press_button(button=btn)
            else:
                self._gamepad.release_button(button=btn)
        self._gamepad.update()

    # ─── Reset ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all inputs to default (neutral) state."""
        if self._gamepad is None:
            return
        self._gamepad.reset()
        self._gamepad.update()

    # ─── Context Manager ─────────────────────────────────────────────────

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
