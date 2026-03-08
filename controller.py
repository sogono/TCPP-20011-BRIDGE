"""
Taito TCPP-20011 Shinkansen Densha de GO! Controller Driver

USB Protocol driver for the Taito Shinkansen train simulator controller
originally designed for Sony PlayStation 2.

Controller features:
  Inputs:  Brake handle (7 notches + emergency), Power handle (13 notches),
           Horn pedal, D-Pad, 6 buttons (A, B, C, D, Select, Start)
  Outputs: Numerical speedometer (BCD, 0-999), Speed gauge bar (0-22 LEDs),
           Limit approach bar (0-10 LEDs), ATC speed limit (BCD, 0-999),
           Door lamp, Left/Right rumble motors

References:
  https://traincontrollerdb.marcriera.cat/hardware/tcpp20011
"""

import usb.core
import usb.util
import usb.backend.libusb1
import struct
import time
import threading
import platform
import os
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Callable


def _get_libusb_backend():
    """Locate the libusb-1.0 DLL from the pip-installed 'libusb' package and return a backend."""
    # Try default backend first
    backend = usb.backend.libusb1.get_backend()
    if backend is not None:
        return backend

    # Locate DLL from pip-installed libusb package
    try:
        import libusb
        pkg_dir = libusb.__path__[0]
        arch = 'x86_64' if platform.machine().endswith('64') else 'x86'
        if platform.machine().lower() in ('arm64', 'aarch64'):
            arch = 'arm64'
        dll_path = os.path.join(pkg_dir, '_platform', 'windows', arch, 'libusb-1.0.dll')
        if os.path.isfile(dll_path):
            backend = usb.backend.libusb1.get_backend(find_library=lambda x: dll_path)
            if backend is not None:
                return backend
    except ImportError:
        pass

    # Try finding any libusb-1.0.dll in the libusb package tree
    try:
        import libusb
        pkg_dir = libusb.__path__[0]
        for root, dirs, files in os.walk(pkg_dir):
            for f in files:
                if f.lower() == 'libusb-1.0.dll':
                    candidate = os.path.join(root, f)
                    backend = usb.backend.libusb1.get_backend(find_library=lambda x, p=candidate: p)
                    if backend is not None:
                        return backend
    except ImportError:
        pass

    return None


_usb_backend = _get_libusb_backend()


# USB identifiers
VENDOR_ID = 0x0AE4   # Taito
PRODUCT_ID = 0x0005   # TCPP-20011 Shinkansen Controller
PRODUCT_NAME = "TAITO_DENSYA_CON_T02"
SERIAL_NUMBER = "TCPP20011"

# USB endpoint
ENDPOINT_IN = 0x81
PACKET_SIZE = 8
POLL_INTERVAL_MS = 20

# Control transfer parameters for output
BM_REQUEST_TYPE = 0x40
B_REQUEST = 0x09
W_VALUE = 0x0301
W_INDEX = 0x0000
W_LENGTH = 0x0008


# ─── Input Enumerations ──────────────────────────────────────────────────────

class BrakeNotch(IntEnum):
    """Brake handle positions. Values are the raw byte values from the controller."""
    RELEASED   = 0x1C
    B1         = 0x38
    B2         = 0x54
    B3         = 0x70
    B4         = 0x8B
    B5         = 0xA7
    B6         = 0xC3
    B7         = 0xDF
    EMERGENCY  = 0xFB


class PowerNotch(IntEnum):
    """Power handle positions. Values are the raw byte values from the controller."""
    N          = 0x12
    P1         = 0x24
    P2         = 0x36
    P3         = 0x48
    P4         = 0x5A
    P5         = 0x6C
    P6         = 0x7E
    P7         = 0x90
    P8         = 0xA2
    P9         = 0xB4
    P10        = 0xC6
    P11        = 0xD7
    P12        = 0xE9
    P13        = 0xFB


class DPad(IntEnum):
    """D-Pad directions. Standard hat switch encoding."""
    N      = 0x00
    NE     = 0x01
    E      = 0x02
    SE     = 0x03
    S      = 0x04
    SW     = 0x05
    W      = 0x06
    NW     = 0x07
    CENTER = 0x08


# Button bit masks for byte 5
class Button:
    """Button bitmask constants for the button byte."""
    D      = 0x01  # Bit 0
    C      = 0x02  # Bit 1
    B      = 0x04  # Bit 2
    A      = 0x08  # Bit 3
    SELECT = 0x10  # Bit 4
    START  = 0x20  # Bit 5


# ─── Input State ─────────────────────────────────────────────────────────────

@dataclass
class ControllerInput:
    """Represents the current state of all controller inputs."""
    brake: BrakeNotch = BrakeNotch.RELEASED
    power: PowerNotch = PowerNotch.N
    pedal_pressed: bool = False
    dpad: DPad = DPad.CENTER
    button_a: bool = False
    button_b: bool = False
    button_c: bool = False
    button_d: bool = False
    button_select: bool = False
    button_start: bool = False
    raw_bytes: bytes = b'\x00' * 6

    @property
    def brake_name(self) -> str:
        return self.brake.name

    @property
    def power_name(self) -> str:
        return self.power.name

    @property
    def dpad_name(self) -> str:
        return self.dpad.name

    @property
    def buttons_pressed(self) -> list[str]:
        pressed = []
        if self.button_a: pressed.append("A")
        if self.button_b: pressed.append("B")
        if self.button_c: pressed.append("C")
        if self.button_d: pressed.append("D")
        if self.button_select: pressed.append("SELECT")
        if self.button_start: pressed.append("START")
        return pressed

    def __str__(self) -> str:
        parts = [
            f"Brake: {self.brake_name:>10s}",
            f"Power: {self.power_name:>10s}",
            f"Pedal: {'PRESSED' if self.pedal_pressed else 'released':>10s}",
            f"DPad: {self.dpad_name:>10s}",
            f"Buttons: {', '.join(self.buttons_pressed) or 'none'}",
        ]
        return " | ".join(parts)


# ─── Output State ────────────────────────────────────────────────────────────

@dataclass
class ControllerOutput:
    """Represents the desired state of all controller outputs/displays."""
    left_rumble: bool = False
    right_rumble: bool = False
    door_lamp: bool = False
    limit_approach: int = 0       # 0-10 (number of LEDs lit above speedometer)
    speed_gauge: int = 0          # 0-22 (number of LEDs lit on speed gauge bar)
    speedometer: int = 0          # 0-999 (numerical speed in km/h, displayed as BCD)
    atc_limit: int = 0            # 0-999 (ATC speed limit in km/h, displayed as BCD)

    def _int_to_bcd_le(self, value: int) -> bytes:
        """Convert an integer (0-999) to 2-byte BCD Little Endian."""
        value = max(0, min(999, value))
        hundreds = value // 100
        tens = (value % 100) // 10
        ones = value % 10
        # BCD: 0x0120 for 120 km/h -> byte layout in LE: low byte first
        bcd_high = hundreds
        bcd_low = (tens << 4) | ones
        return bytes([bcd_low, bcd_high])

    def to_bytes(self) -> bytes:
        """Serialize output state to the 8-byte control transfer payload."""
        byte1 = 0x01 if self.left_rumble else 0x00
        byte2 = 0x01 if self.right_rumble else 0x00

        # Byte 3: Door lamp (high nibble) + Limit approach (low nibble)
        door_nibble = 0x80 if self.door_lamp else 0x00
        limit_nibble = max(0, min(0x0A, self.limit_approach))
        byte3 = door_nibble | limit_nibble

        # Byte 4: Speed gauge (0x00-0x16)
        byte4 = max(0, min(0x16, self.speed_gauge))

        # Bytes 5-6: Speedometer (BCD, Little Endian)
        speed_bcd = self._int_to_bcd_le(self.speedometer)

        # Bytes 7-8: ATC limit (BCD, Little Endian)
        atc_bcd = self._int_to_bcd_le(self.atc_limit)

        return bytes([byte1, byte2, byte3, byte4]) + speed_bcd + atc_bcd

    def __str__(self) -> str:
        parts = [
            f"Speed: {self.speedometer:3d} km/h",
            f"Gauge: {self.speed_gauge:2d}/22 LEDs",
            f"Limit: {self.atc_limit:3d} km/h",
            f"Approach: {self.limit_approach:2d}/10 LEDs",
            f"Door: {'ON' if self.door_lamp else 'off'}",
            f"Rumble L/R: {'ON' if self.left_rumble else 'off'}/{'ON' if self.right_rumble else 'off'}",
        ]
        return " | ".join(parts)


# ─── Byte Parsing Helpers ────────────────────────────────────────────────────

def _parse_brake(raw: int) -> Optional[BrakeNotch]:
    """Parse brake byte to the nearest known notch position.
    Returns None for transition values (0xFF) which should be ignored."""
    if raw == 0xFF:
        return None
    try:
        return BrakeNotch(raw)
    except ValueError:
        # Find nearest known notch by value distance
        closest = min(BrakeNotch, key=lambda n: abs(n.value - raw))
        return closest


def _parse_power(raw: int) -> Optional[PowerNotch]:
    """Parse power byte to the nearest known notch position.
    Returns None for transition values (0xFF) which should be ignored."""
    if raw == 0xFF:
        return None
    try:
        return PowerNotch(raw)
    except ValueError:
        closest = min(PowerNotch, key=lambda n: abs(n.value - raw))
        return closest


def _parse_dpad(raw: int) -> DPad:
    """Parse D-pad byte."""
    try:
        return DPad(raw)
    except ValueError:
        return DPad.CENTER


def _parse_buttons(raw: int) -> dict[str, bool]:
    """Parse button byte into individual button states."""
    return {
        'button_d':      bool(raw & Button.D),
        'button_c':      bool(raw & Button.C),
        'button_b':      bool(raw & Button.B),
        'button_a':      bool(raw & Button.A),
        'button_select': bool(raw & Button.SELECT),
        'button_start':  bool(raw & Button.START),
    }


def parse_input(data: bytes, previous: Optional[ControllerInput] = None) -> ControllerInput:
    """Parse a 6-byte input report into a ControllerInput object.

    Transition states (0xFF) on the brake/power bytes are ignored;
    the lever keeps its previous position until a valid notch is read.
    If no previous state is supplied, defaults are RELEASED / N.
    """
    if len(data) < 6:
        raise ValueError(f"Expected at least 6 bytes, got {len(data)}")

    brake = _parse_brake(data[0])
    power = _parse_power(data[1])

    if brake is None:
        brake = previous.brake if previous is not None else BrakeNotch.RELEASED
    if power is None:
        power = previous.power if previous is not None else PowerNotch.N

    pedal_pressed = (data[2] == 0x00)
    dpad = _parse_dpad(data[3])
    buttons = _parse_buttons(data[4])

    return ControllerInput(
        brake=brake,
        power=power,
        pedal_pressed=pedal_pressed,
        dpad=dpad,
        raw_bytes=bytes(data[:6]),
        **buttons,
    )


# ─── Controller Device Class ────────────────────────────────────────────────

class ShinkansenController:
    """
    High-level interface to the Taito TCPP-20011 Shinkansen Controller.

    Usage:
        controller = ShinkansenController()
        controller.open()

        # Read input
        state = controller.read_input()
        print(state)

        # Write output
        output = ControllerOutput(speedometer=120, atc_limit=130, door_lamp=True)
        controller.write_output(output)

        controller.close()
    """

    def __init__(self):
        self.device: Optional[usb.core.Device] = None
        self.interface: int = 0
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_running: bool = False
        self._last_input: Optional[ControllerInput] = None
        self._input_callback: Optional[Callable[[ControllerInput], None]] = None
        self._lock = threading.Lock()

    @staticmethod
    def find_device() -> Optional[usb.core.Device]:
        """Find the Shinkansen controller on the USB bus."""
        return usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID, backend=_usb_backend)

    @staticmethod
    def list_all_taito_devices() -> list[usb.core.Device]:
        """Find all Taito USB devices."""
        devices = list(usb.core.find(idVendor=VENDOR_ID, find_all=True, backend=_usb_backend))
        return devices

    def open(self) -> None:
        """Open connection to the controller."""
        self.device = self.find_device()
        if self.device is None:
            raise RuntimeError(
                f"Shinkansen controller not found (VID=0x{VENDOR_ID:04X}, "
                f"PID=0x{PRODUCT_ID:04X}). Ensure the controller is plugged in "
                f"and the libwdi/WinUSB driver is installed."
            )

        # Detach kernel driver if necessary (Linux/macOS)
        try:
            if self.device.is_kernel_driver_active(self.interface):
                self.device.detach_kernel_driver(self.interface)
        except (usb.core.USBError, NotImplementedError):
            pass

        # Set configuration
        try:
            self.device.set_configuration()
        except usb.core.USBError:
            pass  # May already be configured

        # Claim interface
        try:
            usb.util.claim_interface(self.device, self.interface)
        except usb.core.USBError:
            pass  # May already be claimed

        print(f"Connected to: {self._get_device_info()}")

    def close(self) -> None:
        """Close connection to the controller."""
        self.stop_polling()
        if self.device is not None:
            try:
                usb.util.release_interface(self.device, self.interface)
            except usb.core.USBError:
                pass
            try:
                usb.util.dispose_resources(self.device)
            except usb.core.USBError:
                pass
            self.device = None

    def _get_device_info(self) -> str:
        """Get human-readable device information."""
        if self.device is None:
            return "No device"
        try:
            manufacturer = usb.util.get_string(self.device, self.device.iManufacturer)
            product = usb.util.get_string(self.device, self.device.iProduct)
            serial = usb.util.get_string(self.device, self.device.iSerialNumber)
            return (
                f"{manufacturer} {product} (Serial: {serial}, "
                f"VID=0x{self.device.idVendor:04X}, PID=0x{self.device.idProduct:04X})"
            )
        except Exception:
            return f"VID=0x{self.device.idVendor:04X}, PID=0x{self.device.idProduct:04X}"

    def read_input(self, timeout_ms: int = 1000) -> Optional[ControllerInput]:
        """
        Read a single input report from the controller.
        Returns None if read times out.
        Transition states on the levers are filtered out; the previous
        position is retained until a valid notch is read.
        """
        if self.device is None:
            raise RuntimeError("Controller not opened. Call open() first.")

        try:
            data = self.device.read(ENDPOINT_IN, PACKET_SIZE, timeout=timeout_ms)
            if data is not None and len(data) >= 6:
                state = parse_input(bytes(data), self._last_input)
                self._last_input = state
                return state
        except usb.core.USBTimeoutError:
            return None
        except usb.core.USBError as e:
            print(f"USB read error: {e}")
            return None
        return None

    def read_input_raw(self, timeout_ms: int = 1000) -> Optional[bytes]:
        """Read raw bytes from the controller for debugging."""
        if self.device is None:
            raise RuntimeError("Controller not opened. Call open() first.")

        try:
            data = self.device.read(ENDPOINT_IN, PACKET_SIZE, timeout=timeout_ms)
            return bytes(data) if data is not None else None
        except usb.core.USBTimeoutError:
            return None
        except usb.core.USBError as e:
            print(f"USB read error: {e}")
            return None

    def write_output(self, output: ControllerOutput) -> bool:
        """
        Send output state to the controller displays.
        Returns True on success.
        """
        if self.device is None:
            raise RuntimeError("Controller not opened. Call open() first.")

        payload = output.to_bytes()

        try:
            self.device.ctrl_transfer(
                bmRequestType=BM_REQUEST_TYPE,
                bRequest=B_REQUEST,
                wValue=W_VALUE,
                wIndex=W_INDEX,
                data_or_wLength=payload,
            )
            return True
        except usb.core.USBError as e:
            print(f"USB write error: {e}")
            return False

    def write_output_raw(self, data: bytes) -> bool:
        """Send raw 8-byte payload to the controller for debugging."""
        if self.device is None:
            raise RuntimeError("Controller not opened. Call open() first.")
        if len(data) != 8:
            raise ValueError(f"Payload must be exactly 8 bytes, got {len(data)}")

        try:
            self.device.ctrl_transfer(
                bmRequestType=BM_REQUEST_TYPE,
                bRequest=B_REQUEST,
                wValue=W_VALUE,
                wIndex=W_INDEX,
                data_or_wLength=data,
            )
            return True
        except usb.core.USBError as e:
            print(f"USB write error: {e}")
            return False

    # ─── Polling Mode ────────────────────────────────────────────────────

    def start_polling(self, callback: Optional[Callable[[ControllerInput], None]] = None,
                      interval_ms: int = POLL_INTERVAL_MS) -> None:
        """
        Start polling the controller for input in a background thread.
        Optionally provide a callback that fires on every state change.
        """
        if self._poll_running:
            return

        self._input_callback = callback
        self._poll_running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            args=(interval_ms,),
            daemon=True,
        )
        self._poll_thread.start()

    def stop_polling(self) -> None:
        """Stop the polling thread."""
        self._poll_running = False
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2.0)
            self._poll_thread = None

    def _poll_loop(self, interval_ms: int) -> None:
        """Internal polling loop."""
        while self._poll_running:
            state = self.read_input(timeout_ms=max(interval_ms, 100))
            if state is not None:
                changed = (self._last_input is None or
                           state.raw_bytes != self._last_input.raw_bytes)
                with self._lock:
                    self._last_input = state
                if changed and self._input_callback is not None:
                    try:
                        self._input_callback(state)
                    except Exception as e:
                        print(f"Callback error: {e}")

    @property
    def last_input(self) -> Optional[ControllerInput]:
        """Get the most recently polled input state."""
        with self._lock:
            return self._last_input

    # ─── Context Manager ─────────────────────────────────────────────────

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
