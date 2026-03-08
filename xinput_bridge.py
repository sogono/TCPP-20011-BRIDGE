"""
Shinkansen Controller -> Virtual XInput (Xbox 360) Bridge

Reads input from the physical Taito TCPP-20011 controller and feeds it
to a virtual Xbox 360 controller via ViGEmBus, compatible with any
XInput-only game (e.g. Train Simulator World 5).

Default mapping (configurable via CLI):
  Brake notch up   -> RT click (momentary right trigger press)
  Brake notch down -> LT click (momentary left trigger press)
  Power notch up   -> RB click (momentary right shoulder press)
  Power notch down -> LB click (momentary left shoulder press)
  Button A         -> A
  Button B         -> B
  Button C         -> X
  Button D         -> Y
  Select           -> Back
  Start            -> Start
  Horn pedal       -> LS (left stick click)
  D-Pad            -> D-Pad (direct)

Usage:
  python xinput_bridge.py
  python xinput_bridge.py --gui
  python xinput_bridge.py --pulse-ms 100
  python xinput_bridge.py --brake-up LB --brake-down RB --power-up RT --power-down LT
"""

import argparse
import sys
import time
import os

from controller import (
    ShinkansenController, ControllerInput,
    BrakeNotch, PowerNotch, DPad,
)
from xinput_device import VirtualXInputDevice, XButton
from gui import ControllerGUI


# --- Lever Position Ordinals ------------------------------------------------

BRAKE_ORDER = [
    BrakeNotch.RELEASED,
    BrakeNotch.B1,
    BrakeNotch.B2,
    BrakeNotch.B3,
    BrakeNotch.B4,
    BrakeNotch.B5,
    BrakeNotch.B6,
    BrakeNotch.B7,
    BrakeNotch.EMERGENCY,
]

POWER_ORDER = [
    PowerNotch.N,
    PowerNotch.P1,
    PowerNotch.P2,
    PowerNotch.P3,
    PowerNotch.P4,
    PowerNotch.P5,
    PowerNotch.P6,
    PowerNotch.P7,
    PowerNotch.P8,
    PowerNotch.P9,
    PowerNotch.P10,
    PowerNotch.P11,
    PowerNotch.P12,
    PowerNotch.P13,
]


# --- Button Name Mapping ---------------------------------------------------

XBOX_BUTTON_NAMES = {
    "A":  XButton.A,
    "B":  XButton.B,
    "X":  XButton.X,
    "Y":  XButton.Y,
    "LB": XButton.LEFT_SHOULDER,
    "RB": XButton.RIGHT_SHOULDER,
    "LT": "LT",
    "RT": "RT",
    "LS": XButton.LEFT_THUMB,
    "RS": XButton.RIGHT_THUMB,
    "START": XButton.START,
    "BACK":  XButton.BACK,
    "GUIDE": XButton.GUIDE,
    "DPAD_UP":    XButton.DPAD_UP,
    "DPAD_DOWN":  XButton.DPAD_DOWN,
    "DPAD_LEFT":  XButton.DPAD_LEFT,
    "DPAD_RIGHT": XButton.DPAD_RIGHT,
}


def resolve_action(name: str):
    """Resolve a button/trigger name string to an XButton constant or trigger string."""
    upper = name.upper()
    if upper in XBOX_BUTTON_NAMES:
        return XBOX_BUTTON_NAMES[upper]
    raise ValueError(f"Unknown Xbox button name: {name}")


# --- D-Pad Mapping ----------------------------------------------------------

DPAD_MAP = {
    DPad.N:      (True,  False, False, False),
    DPad.NE:     (True,  False, False, True),
    DPad.E:      (False, False, False, True),
    DPad.SE:     (False, True,  False, True),
    DPad.S:      (False, True,  False, False),
    DPad.SW:     (False, True,  True,  False),
    DPad.W:      (False, False, True,  False),
    DPad.NW:     (True,  False, True,  False),
    DPad.CENTER: (False, False, False, False),
}


# --- Sequential Lever Handler -----------------------------------------------

class XInputLever:
    """
    Each notch change fires a momentary button/trigger press on the
    virtual Xbox 360 controller.

    One pulse per notch of movement in the corresponding direction.
    """

    def __init__(self, order_list, xbox, up_action, down_action, pulse_ms=80):
        self.order_list = order_list
        self.xbox = xbox
        self.up_action = up_action
        self.down_action = down_action
        self.pulse_ms = pulse_ms
        self._prev_index = -1

    def update(self, notch):
        try:
            idx = self.order_list.index(notch)
        except ValueError:
            return

        if self._prev_index >= 0 and idx != self._prev_index:
            diff = idx - self._prev_index
            action = self.up_action if diff > 0 else self.down_action
            count = abs(diff)
            for _ in range(count):
                self._pulse(action)

        self._prev_index = idx

    def _pulse(self, action):
        """Pulse a button or trigger."""
        if action == "LT":
            self.xbox.set_left_trigger(255)
            time.sleep(self.pulse_ms / 1000.0)
            self.xbox.set_left_trigger(0)
        elif action == "RT":
            self.xbox.set_right_trigger(255)
            time.sleep(self.pulse_ms / 1000.0)
            self.xbox.set_right_trigger(0)
        else:
            self.xbox.pulse_button(action, self.pulse_ms)


# --- XInput Bridge -----------------------------------------------------------

class XInputBridge:
    """
    Reads from the physical Shinkansen controller and maps inputs
    to a virtual Xbox 360 controller via ViGEmBus.
    """

    def __init__(self, brake_up="RT", brake_down="LT",
                 power_up="RB", power_down="LB",
                 horn="LS", face_a="A", face_b="B",
                 face_c="X", face_d="Y",
                 select="BACK", start="START",
                 pulse_ms=80, gui=False):
        self.pulse_ms = pulse_ms
        self.use_gui = gui

        # Resolve button mappings
        self.brake_up_action = resolve_action(brake_up)
        self.brake_down_action = resolve_action(brake_down)
        self.power_up_action = resolve_action(power_up)
        self.power_down_action = resolve_action(power_down)
        self.horn_button = resolve_action(horn)
        self.face_a_button = resolve_action(face_a)
        self.face_b_button = resolve_action(face_b)
        self.face_c_button = resolve_action(face_c)
        self.face_d_button = resolve_action(face_d)
        self.select_button = resolve_action(select)
        self.start_button = resolve_action(start)

        # Store names for display
        self.brake_up_name = brake_up.upper()
        self.brake_down_name = brake_down.upper()
        self.power_up_name = power_up.upper()
        self.power_down_name = power_down.upper()

        self.controller = ShinkansenController()
        self.xbox = VirtualXInputDevice()
        self._gui = None

        self.brake_handler = None
        self.power_handler = None
        self._running = False

    def open(self):
        """Connect to both physical controller and virtual device."""
        self.controller.open()
        self.xbox.open()

        if self.use_gui:
            self._gui = ControllerGUI()
            self._gui.start()
            print("  GUI window opened.")

        self.brake_handler = XInputLever(
            BRAKE_ORDER, self.xbox,
            self.brake_up_action, self.brake_down_action,
            self.pulse_ms,
        )
        self.power_handler = XInputLever(
            POWER_ORDER, self.xbox,
            self.power_up_action, self.power_down_action,
            self.pulse_ms,
        )

    def close(self):
        """Disconnect everything."""
        self._running = False
        if self._gui is not None:
            try:
                self._gui.close()
            except Exception:
                pass
        try:
            self.xbox.close()
        except Exception:
            pass
        try:
            self.controller.close()
        except Exception:
            pass

    def _map_buttons(self, state):
        """Map physical buttons to Xbox 360 buttons."""
        self._set_xbox_button(self.face_a_button, state.button_a)
        self._set_xbox_button(self.face_b_button, state.button_b)
        self._set_xbox_button(self.face_c_button, state.button_c)
        self._set_xbox_button(self.face_d_button, state.button_d)
        self._set_xbox_button(self.select_button, state.button_select)
        self._set_xbox_button(self.start_button, state.button_start)
        self._set_xbox_button(self.horn_button, state.pedal_pressed)

    def _set_xbox_button(self, action, pressed):
        """Set a button or trigger based on the resolved action."""
        if action == "LT":
            self.xbox.set_left_trigger(255 if pressed else 0)
        elif action == "RT":
            self.xbox.set_right_trigger(255 if pressed else 0)
        else:
            self.xbox.set_button(action, pressed)

    def _map_dpad(self, state):
        """Map D-pad to Xbox 360 D-pad."""
        directions = DPAD_MAP.get(state.dpad, (False, False, False, False))
        self.xbox.set_dpad(*directions)

    def _process_input(self, state):
        """Process one input frame and update the virtual device."""
        # Levers
        self.brake_handler.update(state.brake)
        self.power_handler.update(state.power)

        # Buttons
        self._map_buttons(state)

        # D-pad
        self._map_dpad(state)

    def run(self):
        """Main polling loop. Runs until Ctrl+C."""
        self._running = True
        prev_raw = None

        print()
        print("  Bridge active. Controller inputs -> Xbox 360 (XInput) virtual device.")
        print(f"  Brake up/down : {self.brake_up_name} / {self.brake_down_name}")
        print(f"  Power up/down : {self.power_up_name} / {self.power_down_name}")
        print(f"  Pulse (ms)    : {self.pulse_ms}")
        print()
        print("  Press Ctrl+C to stop.")
        print()

        try:
            while self._running:
                state = self.controller.read_input(timeout_ms=100)
                if state is None:
                    continue

                # Only process on change
                if state.raw_bytes != prev_raw:
                    self._process_input(state)
                    prev_raw = state.raw_bytes

                    # Status line
                    sys.stdout.write(
                        f"\r  Brake: {state.brake_name:>10s}  "
                        f"Power: {state.power_name:>10s}  "
                        f"Pedal: {'##' if state.pedal_pressed else '..'}  "
                        f"DPad: {state.dpad_name:>6s}  "
                        f"Btns: {_btn_str(state)}   "
                    )
                    sys.stdout.flush()

                    if self._gui is not None and self._gui.is_alive():
                        self._gui.update_state(state)

        except KeyboardInterrupt:
            pass

        print("\n")
        print("  Bridge stopped.")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def _btn_str(state):
    parts = []
    parts.append("A" if state.button_a else ".")
    parts.append("B" if state.button_b else ".")
    parts.append("C" if state.button_c else ".")
    parts.append("D" if state.button_d else ".")
    parts.append("Se" if state.button_select else "..")
    parts.append("St" if state.button_start else "..")
    return "".join(parts)


# --- CLI ---------------------------------------------------------------------

VALID_BUTTONS = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT",
                 "LS", "RS", "START", "BACK", "GUIDE"]


def print_banner():
    print("+=================================================================+")
    print("|   SHINKANSEN CONTROLLER -> VIRTUAL XBOX 360 (XINPUT) BRIDGE     |")
    print("+=================================================================+")


def main():
    parser = argparse.ArgumentParser(
        description="Bridge Taito Shinkansen controller to a virtual Xbox 360 controller via ViGEmBus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Default button mapping (for Train Simulator World 5):
  Brake notch up   -> RT    Brake notch down -> LT
  Power notch up   -> RB    Power notch down -> LB
  Button A -> A    Button B -> B    Button C -> X    Button D -> Y
  Select -> Back   Start -> Start   Horn pedal -> LS (left stick click)
  D-Pad -> D-Pad (direct mapping)

Configurable buttons: A B X Y LB RB LT RT LS RS START BACK GUIDE

Examples:
  python xinput_bridge.py
  python xinput_bridge.py --gui
  python xinput_bridge.py --pulse-ms 100
  python xinput_bridge.py --brake-up LB --brake-down RB
  python xinput_bridge.py --power-up A --power-down B
""",
    )
    parser.add_argument(
        "--brake-up", default="RT", choices=VALID_BUTTONS,
        help="Xbox button/trigger for brake notch increase (default: RT)",
    )
    parser.add_argument(
        "--brake-down", default="LT", choices=VALID_BUTTONS,
        help="Xbox button/trigger for brake notch decrease (default: LT)",
    )
    parser.add_argument(
        "--power-up", default="RB", choices=VALID_BUTTONS,
        help="Xbox button/trigger for power notch increase (default: RB)",
    )
    parser.add_argument(
        "--power-down", default="LB", choices=VALID_BUTTONS,
        help="Xbox button/trigger for power notch decrease (default: LB)",
    )
    parser.add_argument(
        "--horn", default="LS", choices=VALID_BUTTONS,
        help="Xbox button for horn pedal (default: LS = left stick click)",
    )
    parser.add_argument(
        "--face-a", default="A", choices=VALID_BUTTONS,
        help="Xbox button for controller A button (default: A)",
    )
    parser.add_argument(
        "--face-b", default="B", choices=VALID_BUTTONS,
        help="Xbox button for controller B button (default: B)",
    )
    parser.add_argument(
        "--face-c", default="X", choices=VALID_BUTTONS,
        help="Xbox button for controller C button (default: X)",
    )
    parser.add_argument(
        "--face-d", default="Y", choices=VALID_BUTTONS,
        help="Xbox button for controller D button (default: Y)",
    )
    parser.add_argument(
        "--select", default="BACK", choices=VALID_BUTTONS,
        help="Xbox button for Select (default: BACK)",
    )
    parser.add_argument(
        "--start", default="START", choices=VALID_BUTTONS,
        help="Xbox button for Start (default: START)",
    )
    parser.add_argument(
        "--pulse-ms", type=int, default=80,
        help="Button pulse duration in ms for lever notch changes (default: 80)",
    )
    parser.add_argument(
        "--gui", action="store_true",
        help="Open a GUI window showing live controller state",
    )

    args = parser.parse_args()

    os.system('cls' if os.name == 'nt' else 'clear')
    print_banner()
    print()

    try:
        with XInputBridge(
            brake_up=args.brake_up,
            brake_down=args.brake_down,
            power_up=args.power_up,
            power_down=args.power_down,
            horn=args.horn,
            face_a=args.face_a,
            face_b=args.face_b,
            face_c=args.face_c,
            face_d=args.face_d,
            select=args.select,
            start=args.start,
            pulse_ms=args.pulse_ms,
            gui=args.gui,
        ) as bridge:
            bridge.run()
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        print()
        print("  Troubleshooting:")
        print("    1. Install vgamepad: pip install vgamepad")
        print("       (first install will also set up ViGEmBus driver)")
        print("    2. Ensure the Shinkansen controller is plugged in with WinUSB driver")
        sys.exit(1)

    print()
    print("  Goodbye.")


if __name__ == "__main__":
    main()
