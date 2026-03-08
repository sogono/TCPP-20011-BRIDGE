"""
Interactive Test Tool for the Taito TCPP-20011 Shinkansen Controller

Provides a live console UI to:
  - Monitor all inputs in real-time (levers, pedal, buttons, d-pad)
  - Control all outputs (speedometer, speed gauge, limit approach, ATC limit, door lamp, rumble)
  - Run automated display test sequences
"""

import sys
import time
import threading
import os

from controller import (
    ShinkansenController, ControllerInput, ControllerOutput, parse_input,
    BrakeNotch, PowerNotch, DPad, Button,
)
from gui import ControllerGUI


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║     TAITO TCPP-20011 SHINKANSEN CONTROLLER - INTERACTIVE TEST  ║")
    print("╚══════════════════════════════════════════════════════════════════╝")


# ─── Input Monitor ───────────────────────────────────────────────────────────

def monitor_inputs(ctrl: ShinkansenController):
    """Live monitor of all controller inputs."""
    print()
    print("── INPUT MONITOR ──────────────────────────────────────────────────")
    print("  Monitoring all inputs. Move levers, press buttons, step on pedal.")
    print("  Press Ctrl+C to return to menu.")
    print()

    prev_line = ""
    try:
        while True:
            state = ctrl.read_input(timeout_ms=100)
            if state is None:
                continue

            raw_hex = " ".join(f"{b:02X}" for b in state.raw_bytes)

            # Build a single-line display
            brake_bar = _brake_bar(state.brake)
            power_bar = _power_bar(state.power)

            line = (
                f"\r  Brake: {state.brake_name:>10s} {brake_bar}  "
                f"Power: {state.power_name:>10s} {power_bar}  "
                f"Pedal: {'██' if state.pedal_pressed else '░░'}  "
                f"DPad: {state.dpad_name:>6s}  "
                f"Btns: {_button_display(state)}  "
                f"Raw:[{raw_hex}]"
            )

            if line != prev_line:
                sys.stdout.write(line + "   ")
                sys.stdout.flush()
                prev_line = line

            _gui_update(state)

    except KeyboardInterrupt:
        print("\n")


def _brake_bar(brake: BrakeNotch) -> str:
    """Visual bar for brake position."""
    positions = [
        BrakeNotch.RELEASED, BrakeNotch.B1, BrakeNotch.B2, BrakeNotch.B3,
        BrakeNotch.B4, BrakeNotch.B5, BrakeNotch.B6, BrakeNotch.B7,
        BrakeNotch.EMERGENCY,
    ]
    try:
        idx = positions.index(brake)
    except ValueError:
        idx = 0
    return "[" + "█" * idx + "░" * (8 - idx) + "]"


def _power_bar(power: PowerNotch) -> str:
    """Visual bar for power position."""
    positions = [
        PowerNotch.N, PowerNotch.P1, PowerNotch.P2, PowerNotch.P3,
        PowerNotch.P4, PowerNotch.P5, PowerNotch.P6, PowerNotch.P7,
        PowerNotch.P8, PowerNotch.P9, PowerNotch.P10, PowerNotch.P11,
        PowerNotch.P12, PowerNotch.P13,
    ]
    try:
        idx = positions.index(power)
    except ValueError:
        idx = 0
    return "[" + "█" * idx + "░" * (13 - idx) + "]"


def _button_display(state: ControllerInput) -> str:
    """Compact button state display."""
    parts = []
    parts.append("A" if state.button_a else ".")
    parts.append("B" if state.button_b else ".")
    parts.append("C" if state.button_c else ".")
    parts.append("D" if state.button_d else ".")
    parts.append("Se" if state.button_select else "..")
    parts.append("St" if state.button_start else "..")
    return "".join(parts)


# ─── Raw Byte Dump ───────────────────────────────────────────────────────────

def raw_byte_dump(ctrl: ShinkansenController):
    """Dump raw bytes for protocol analysis."""
    print()
    print("── RAW BYTE DUMP ──────────────────────────────────────────────────")
    print("  Showing raw bytes from the controller. Useful for reverse engineering.")
    print("  Press Ctrl+C to return to menu.")
    print()
    print("  Byte:  [  1  ] [  2  ] [  3  ] [  4  ] [  5  ] [  6  ] [  7  ] [  8  ]")
    print("  Desc:  [Brake] [Power] [Pedal] [DPad ] [Btns ] [Unused]  ...     ...  ")
    print()

    prev_data = None
    count = 0
    try:
        while True:
            raw = ctrl.read_input_raw(timeout_ms=100)
            if raw is None:
                continue
            if raw != prev_data:
                count += 1
                hex_str = "  ".join(f"0x{b:02X}" for b in raw)
                bin_str = "  ".join(f"{b:08b}" for b in raw[:6])
                print(f"  #{count:4d}  Hex: {hex_str}")
                print(f"         Bin: {bin_str}")
                prev_data = raw
                try:
                    _gui_update(parse_input(raw))
                except Exception:
                    pass

    except KeyboardInterrupt:
        print(f"\n  {count} unique states captured.")
        print()


# ─── Output Control ──────────────────────────────────────────────────────────

def output_control(ctrl: ShinkansenController):
    """Interactive output/display control."""
    print()
    print("── OUTPUT CONTROL ─────────────────────────────────────────────────")
    print("  Control the controller's displays and outputs.")
    print()

    output = ControllerOutput()

    while True:
        print(f"  Current: {output}")
        print()
        print("  Commands:")
        print("    speed <0-999>       Set numerical speedometer (km/h)")
        print("    gauge <0-22>        Set speed gauge bar (LED count)")
        print("    limit <0-999>       Set ATC speed limit display (km/h)")
        print("    approach <0-10>     Set limit approach bar (LED count)")
        print("    door <on|off>       Toggle door lamp")
        print("    rumble <l|r|both|off>  Control rumble motors")
        print("    test                Run automated display test")
        print("    clear               Turn off all outputs")
        print("    back                Return to main menu")
        print()

        try:
            cmd = input("  > ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not cmd:
            continue

        parts = cmd.split()
        action = parts[0]

        try:
            if action == "speed" and len(parts) > 1:
                output.speedometer = max(0, min(999, int(parts[1])))
            elif action == "gauge" and len(parts) > 1:
                output.speed_gauge = max(0, min(22, int(parts[1])))
            elif action == "limit" and len(parts) > 1:
                output.atc_limit = max(0, min(999, int(parts[1])))
            elif action == "approach" and len(parts) > 1:
                output.limit_approach = max(0, min(10, int(parts[1])))
            elif action == "door" and len(parts) > 1:
                output.door_lamp = parts[1] in ("on", "1", "true")
            elif action == "rumble" and len(parts) > 1:
                if parts[1] == "l":
                    output.left_rumble = True
                    output.right_rumble = False
                elif parts[1] == "r":
                    output.left_rumble = False
                    output.right_rumble = True
                elif parts[1] == "both":
                    output.left_rumble = True
                    output.right_rumble = True
                else:
                    output.left_rumble = False
                    output.right_rumble = False
            elif action == "test":
                run_display_test(ctrl)
                continue
            elif action == "clear":
                output = ControllerOutput()
            elif action == "back":
                # Turn off everything before leaving
                ctrl.write_output(ControllerOutput())
                break
            else:
                print("  Unknown command.")
                continue

            success = ctrl.write_output(output)
            if success:
                print("  Output updated.")
            else:
                print("  Failed to send output!")

        except ValueError:
            print("  Invalid value.")
        except Exception as e:
            print(f"  Error: {e}")

        print()


def run_display_test(ctrl: ShinkansenController):
    """Run an automated test sequence through all displays."""
    print()
    print("  Running display test sequence... (Ctrl+C to abort)")
    print()

    output = ControllerOutput()

    try:
        # Test 1: Door lamp
        print("  [1/6] Door lamp: ON")
        output.door_lamp = True
        ctrl.write_output(output)
        time.sleep(1.0)
        output.door_lamp = False
        ctrl.write_output(output)
        time.sleep(0.5)

        # Test 2: Speedometer count up
        print("  [2/6] Speedometer: counting 0 -> 300")
        for speed in range(0, 301, 10):
            output.speedometer = speed
            ctrl.write_output(output)
            time.sleep(0.05)
        time.sleep(0.5)
        output.speedometer = 0
        ctrl.write_output(output)
        time.sleep(0.3)

        # Test 3: Speed gauge bar sweep
        print("  [3/6] Speed gauge: sweep 0 -> 22")
        for g in range(23):
            output.speed_gauge = g
            ctrl.write_output(output)
            time.sleep(0.1)
        time.sleep(0.5)
        output.speed_gauge = 0
        ctrl.write_output(output)
        time.sleep(0.3)

        # Test 4: Limit approach bar sweep
        print("  [4/6] Limit approach: sweep 0 -> 10")
        for a in range(11):
            output.limit_approach = a
            ctrl.write_output(output)
            time.sleep(0.15)
        time.sleep(0.5)
        output.limit_approach = 0
        ctrl.write_output(output)
        time.sleep(0.3)

        # Test 5: ATC limit display
        print("  [5/6] ATC limit: counting 0 -> 300")
        for limit in range(0, 301, 10):
            output.atc_limit = limit
            ctrl.write_output(output)
            time.sleep(0.05)
        time.sleep(0.5)
        output.atc_limit = 0
        ctrl.write_output(output)
        time.sleep(0.3)

        # Test 6: Rumble motors
        print("  [6/6] Rumble: Left, Right, Both")
        output.left_rumble = True
        ctrl.write_output(output)
        time.sleep(0.5)
        output.left_rumble = False
        output.right_rumble = True
        ctrl.write_output(output)
        time.sleep(0.5)
        output.left_rumble = True
        ctrl.write_output(output)
        time.sleep(0.5)
        output.left_rumble = False
        output.right_rumble = False
        ctrl.write_output(output)

        # Full demo: simulate acceleration
        print("  [BONUS] Simulated acceleration 0 -> 250 km/h with limit at 275...")
        output.door_lamp = False
        output.atc_limit = 275
        for speed in range(0, 251, 1):
            output.speedometer = speed
            output.speed_gauge = min(22, speed // 15)
            # Limit approach: light up as we get within 10 km/h of limit
            if speed >= (275 - 10):
                output.limit_approach = min(10, speed - (275 - 10))
            else:
                output.limit_approach = 0
            ctrl.write_output(output)
            time.sleep(0.03)
        time.sleep(1.0)

        # Clear
        ctrl.write_output(ControllerOutput())
        print("  Test complete. All outputs cleared.")

    except KeyboardInterrupt:
        ctrl.write_output(ControllerOutput())
        print("\n  Test aborted. Outputs cleared.")

    print()


# ─── Main Menu ───────────────────────────────────────────────────────────────

_gui: ControllerGUI | None = None


def _gui_update(state: ControllerInput):
    """Feed state to the GUI if it is running."""
    if _gui is not None and _gui.is_alive():
        _gui.update_state(state)


def main():
    global _gui

    use_gui = "--gui" in sys.argv

    clear_screen()
    print_header()
    print()

    try:
        ctrl = ShinkansenController()
        ctrl.open()
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        print()
        print("  Troubleshooting:")
        print("    1. Ensure the controller is plugged in via USB")
        print("    2. Ensure a libwdi/WinUSB driver is installed (use Zadig)")
        print("    3. Run discover.py to scan for the device")
        print("    4. Check that libusb-1.0.dll is accessible")
        return

    if use_gui:
        _gui = ControllerGUI()
        _gui.start()
        print("  GUI window opened.")

    print()

    try:
        while True:
            print("── MAIN MENU ──────────────────────────────────────────────────────")
            print()
            print("  1. Monitor Inputs       (live view of levers, buttons, pedal)")
            print("  2. Raw Byte Dump        (hex/binary output for protocol analysis)")
            print("  3. Control Outputs      (set speedometer, gauges, lamp, rumble)")
            print("  4. Full Duplex Test     (monitor inputs + control outputs)")
            print("  5. Quit")
            print()

            try:
                choice = input("  Select [1-5]: ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if choice == "1":
                monitor_inputs(ctrl)
            elif choice == "2":
                raw_byte_dump(ctrl)
            elif choice == "3":
                output_control(ctrl)
            elif choice == "4":
                full_duplex_test(ctrl)
            elif choice == "5":
                break
            else:
                print("  Invalid selection.")
                print()

    except KeyboardInterrupt:
        pass
    finally:
        if _gui is not None:
            _gui.close()
        ctrl.close()
        print()
        print("  Controller disconnected. Goodbye.")


def full_duplex_test(ctrl: ShinkansenController):
    """Monitor inputs while allowing output commands."""
    print()
    print("── FULL DUPLEX TEST ───────────────────────────────────────────────")
    print("  Input monitoring active in background.")
    print("  Type output commands (same as Output Control menu).")
    print("  Type 'back' to return to main menu.")
    print()

    output = ControllerOutput()

    def on_input_change(state: ControllerInput):
        raw_hex = " ".join(f"{b:02X}" for b in state.raw_bytes)
        print(f"\r  IN:  {state}  [{raw_hex}]")
        sys.stdout.write("  > ")
        sys.stdout.flush()
        _gui_update(state)

    ctrl.start_polling(callback=on_input_change)

    try:
        while True:
            try:
                cmd = input("  > ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                break

            if not cmd:
                continue

            parts = cmd.split()
            action = parts[0]

            if action == "back":
                break

            try:
                if action == "speed" and len(parts) > 1:
                    output.speedometer = max(0, min(999, int(parts[1])))
                elif action == "gauge" and len(parts) > 1:
                    output.speed_gauge = max(0, min(22, int(parts[1])))
                elif action == "limit" and len(parts) > 1:
                    output.atc_limit = max(0, min(999, int(parts[1])))
                elif action == "approach" and len(parts) > 1:
                    output.limit_approach = max(0, min(10, int(parts[1])))
                elif action == "door" and len(parts) > 1:
                    output.door_lamp = parts[1] in ("on", "1", "true")
                elif action == "clear":
                    output = ControllerOutput()
                else:
                    continue

                ctrl.write_output(output)
                print(f"  OUT: {output}")
            except ValueError:
                print("  Invalid value.")

    finally:
        ctrl.stop_polling()
        ctrl.write_output(ControllerOutput())
        print()


if __name__ == "__main__":
    main()
