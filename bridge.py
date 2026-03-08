"""
Shinkansen Controller → Virtual DirectInput Bridge

Reads input from the physical Taito TCPP-20011 controller and feeds it
to a vJoy virtual joystick that any PC game can bind to.

Lever modes:
  analog      - Lever notch position maps directly to a virtual axis value.
  incremental - Axis starts at a resting point and accumulates change with
                each notch transition (like a virtual throttle wheel).
  sequential  - Each notch change fires a momentary virtual button press
                (one button for "increase", one for "decrease").

Usage:
  python bridge.py                         # default: analog mode for both levers
  python bridge.py --brake analog --power sequential
  python bridge.py --brake incremental --power incremental --step 2000
"""

import argparse
import sys
import time
import threading
import os

from controller import (
    ShinkansenController, ControllerInput, parse_input,
    BrakeNotch, PowerNotch, DPad,
)
from virtual_device import (
    VirtualJoystick, VJoyButton,
    AXIS_MIN, AXIS_MAX, AXIS_CENTER,
    POV_CENTER, POV_N, POV_NE, POV_E, POV_SE,
    POV_S, POV_SW, POV_W, POV_NW,
)


# ─── Lever Position Ordinals ────────────────────────────────────────────────
# Ordered from minimum to maximum for mapping to axis values.

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

DPAD_TO_POV = {
    DPad.N:      POV_N,
    DPad.NE:     POV_NE,
    DPad.E:      POV_E,
    DPad.SE:     POV_SE,
    DPad.S:      POV_S,
    DPad.SW:     POV_SW,
    DPad.W:      POV_W,
    DPad.NW:     POV_NW,
    DPad.CENTER: POV_CENTER,
}


def notch_index(notch, order_list) -> int:
    """Get the ordinal index of a notch in its order list, or -1 if not found."""
    try:
        return order_list.index(notch)
    except ValueError:
        return -1


def notch_to_axis(notch, order_list) -> int:
    """Map a notch position to an axis value spanning AXIS_MIN..AXIS_MAX."""
    idx = notch_index(notch, order_list)
    if idx < 0:
        return AXIS_CENTER
    max_idx = len(order_list) - 1
    if max_idx == 0:
        return AXIS_CENTER
    fraction = idx / max_idx
    return int(AXIS_MIN + fraction * (AXIS_MAX - AXIS_MIN))


# ─── Lever Mode Handlers ────────────────────────────────────────────────────

class AnalogLever:
    """Maps lever notch directly to an axis value."""

    def __init__(self, order_list: list, set_axis_fn):
        self.order_list = order_list
        self.set_axis = set_axis_fn

    def update(self, notch) -> None:
        value = notch_to_axis(notch, self.order_list)
        self.set_axis(value)


class IncrementalLever:
    """
    Axis accumulates change with each notch transition.
    Moving the lever up one notch adds +step to the axis;
    moving down subtracts -step. The axis value clamps to AXIS_MIN..AXIS_MAX.
    """

    def __init__(self, order_list: list, set_axis_fn, step: int = 2000):
        self.order_list = order_list
        self.set_axis = set_axis_fn
        self.step = step
        self.current_value = AXIS_CENTER
        self._prev_index = -1

    def update(self, notch) -> None:
        idx = notch_index(notch, self.order_list)
        if idx < 0:
            return

        if self._prev_index >= 0 and idx != self._prev_index:
            delta = (idx - self._prev_index) * self.step
            self.current_value = max(AXIS_MIN, min(AXIS_MAX, self.current_value + delta))
            self.set_axis(self.current_value)

        self._prev_index = idx


class SequentialLever:
    """
    Each notch change fires a momentary button press.
    Moving up triggers the 'up' button; moving down triggers the 'down' button.
    One press per notch of movement.
    """

    def __init__(self, order_list: list, vjoy: VirtualJoystick,
                 up_button: int, down_button: int, pulse_ms: int = 50):
        self.order_list = order_list
        self.vjoy = vjoy
        self.up_button = up_button
        self.down_button = down_button
        self.pulse_ms = pulse_ms
        self._prev_index = -1

    def update(self, notch) -> None:
        idx = notch_index(notch, self.order_list)
        if idx < 0:
            return

        if self._prev_index >= 0 and idx != self._prev_index:
            diff = idx - self._prev_index
            button = self.up_button if diff > 0 else self.down_button
            count = abs(diff)
            for _ in range(count):
                self.vjoy.pulse_button(button, self.pulse_ms)

        self._prev_index = idx


# ─── Bridge Core ─────────────────────────────────────────────────────────────

class ControllerBridge:
    """
    Reads from the physical Shinkansen controller and maps inputs
    to a vJoy virtual DirectInput device.
    """

    def __init__(self, brake_mode: str = "analog", power_mode: str = "analog",
                 step: int = 2000, pulse_ms: int = 50, vjoy_id: int = 1):
        self.brake_mode_name = brake_mode
        self.power_mode_name = power_mode
        self.step = step
        self.pulse_ms = pulse_ms
        self.vjoy_id = vjoy_id

        self.controller = ShinkansenController()
        self.vjoy = VirtualJoystick(device_id=vjoy_id)

        self.brake_handler = None
        self.power_handler = None
        self._running = False

    def _create_lever_handler(self, mode: str, order_list: list,
                              set_axis_fn, up_btn: int, down_btn: int):
        """Factory for lever mode handlers."""
        if mode == "analog":
            return AnalogLever(order_list, set_axis_fn)
        elif mode == "incremental":
            return IncrementalLever(order_list, set_axis_fn, self.step)
        elif mode == "sequential":
            return SequentialLever(order_list, self.vjoy, up_btn, down_btn, self.pulse_ms)
        else:
            raise ValueError(f"Unknown lever mode: {mode}")

    def open(self) -> None:
        """Connect to both physical controller and virtual device."""
        self.controller.open()
        self.vjoy.open()

        self.brake_handler = self._create_lever_handler(
            self.brake_mode_name, BRAKE_ORDER,
            self.vjoy.set_brake_axis,
            VJoyButton.BRAKE_UP, VJoyButton.BRAKE_DOWN,
        )
        self.power_handler = self._create_lever_handler(
            self.power_mode_name, POWER_ORDER,
            self.vjoy.set_power_axis,
            VJoyButton.POWER_UP, VJoyButton.POWER_DOWN,
        )

    def close(self) -> None:
        """Disconnect everything."""
        self._running = False
        try:
            self.vjoy.close()
        except Exception:
            pass
        try:
            self.controller.close()
        except Exception:
            pass

    def _map_buttons(self, state: ControllerInput) -> None:
        """Map physical buttons to vJoy buttons."""
        self.vjoy.set_button(VJoyButton.A, state.button_a)
        self.vjoy.set_button(VJoyButton.B, state.button_b)
        self.vjoy.set_button(VJoyButton.C, state.button_c)
        self.vjoy.set_button(VJoyButton.D, state.button_d)
        self.vjoy.set_button(VJoyButton.SELECT, state.button_select)
        self.vjoy.set_button(VJoyButton.START, state.button_start)
        self.vjoy.set_button(VJoyButton.HORN, state.pedal_pressed)

    def _map_dpad(self, state: ControllerInput) -> None:
        """Map D-pad to vJoy POV hat."""
        pov = DPAD_TO_POV.get(state.dpad, POV_CENTER)
        self.vjoy.set_pov(pov)

    def _process_input(self, state: ControllerInput) -> None:
        """Process one input frame and update the virtual device."""
        # Levers (skip TRANSITION states)
        if state.brake != BrakeNotch.TRANSITION:
            self.brake_handler.update(state.brake)
        if state.power != PowerNotch.TRANSITION:
            self.power_handler.update(state.power)

        # Buttons
        self._map_buttons(state)

        # D-pad
        self._map_dpad(state)

    def run(self) -> None:
        """Main polling loop. Runs until Ctrl+C."""
        self._running = True
        prev_raw = None

        print()
        print("  Bridge active. Controller inputs → vJoy virtual device.")
        print(f"  Brake mode : {self.brake_mode_name}")
        print(f"  Power mode : {self.power_mode_name}")
        if self.brake_mode_name == "incremental" or self.power_mode_name == "incremental":
            print(f"  Step size  : {self.step}")
        if self.brake_mode_name == "sequential" or self.power_mode_name == "sequential":
            print(f"  Pulse (ms) : {self.pulse_ms}")
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
                        f"Pedal: {'██' if state.pedal_pressed else '░░'}  "
                        f"DPad: {state.dpad_name:>6s}  "
                        f"Btns: {_btn_str(state)}   "
                    )
                    sys.stdout.flush()

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


def _btn_str(state: ControllerInput) -> str:
    parts = []
    parts.append("A" if state.button_a else ".")
    parts.append("B" if state.button_b else ".")
    parts.append("C" if state.button_c else ".")
    parts.append("D" if state.button_d else ".")
    parts.append("Se" if state.button_select else "..")
    parts.append("St" if state.button_start else "..")
    return "".join(parts)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def print_banner():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║   SHINKANSEN CONTROLLER → VIRTUAL DIRECTINPUT DEVICE BRIDGE    ║")
    print("╚══════════════════════════════════════════════════════════════════╝")


def main():
    parser = argparse.ArgumentParser(
        description="Bridge Taito Shinkansen controller to a virtual DirectInput device via vJoy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Lever modes:
  analog       Lever position maps directly to a virtual axis (default)
  incremental  Axis accumulates change per notch step (like a throttle wheel)
  sequential   Each notch change fires a momentary button press (up/down)

Button mapping on the vJoy device:
  1=A  2=B  3=C  4=D  5=Select  6=Start  7=Horn
  8=BrakeUp  9=BrakeDown  10=PowerUp  11=PowerDown  (sequential mode)
  POV Hat 1 = D-Pad
  Axis X = Brake (analog/incremental)
  Axis Y = Power (analog/incremental)

Examples:
  python bridge.py
  python bridge.py --brake analog --power sequential
  python bridge.py --brake incremental --power incremental --step 3000
  python bridge.py --vjoy-id 2
""",
    )
    parser.add_argument(
        "--brake", choices=["analog", "incremental", "sequential"],
        default="analog", help="Lever mode for the brake handle (default: analog)",
    )
    parser.add_argument(
        "--power", choices=["analog", "incremental", "sequential"],
        default="analog", help="Lever mode for the power handle (default: analog)",
    )
    parser.add_argument(
        "--step", type=int, default=2000,
        help="Axis step size per notch for incremental mode (default: 2000, range: 1-32767)",
    )
    parser.add_argument(
        "--pulse-ms", type=int, default=50,
        help="Button pulse duration in ms for sequential mode (default: 50)",
    )
    parser.add_argument(
        "--vjoy-id", type=int, default=1,
        help="vJoy device ID to use (default: 1)",
    )

    args = parser.parse_args()

    os.system('cls' if os.name == 'nt' else 'clear')
    print_banner()
    print()

    try:
        with ControllerBridge(
            brake_mode=args.brake,
            power_mode=args.power,
            step=args.step,
            pulse_ms=args.pulse_ms,
            vjoy_id=args.vjoy_id,
        ) as bridge:
            bridge.run()
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        print()
        print("  Troubleshooting:")
        print("    1. Install vJoy: https://github.com/njz3/vJoy/releases")
        print("    2. Configure vJoy device with: 2 axes, 11+ buttons, 1 continuous POV")
        print("    3. Install pyvjoystick: pip install pyvjoystick")
        print("    4. Ensure the Shinkansen controller is plugged in with WinUSB driver")
        sys.exit(1)

    print()
    print("  Goodbye.")


if __name__ == "__main__":
    main()
