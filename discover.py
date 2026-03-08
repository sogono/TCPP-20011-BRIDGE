"""
USB Device Discovery Tool

Scans for the Taito TCPP-20011 Shinkansen controller and prints
detailed device information. Also lists all USB devices to help
identify the controller if VID/PID differ from expected.
"""

import sys
import usb.core
import usb.util

from controller import (
    VENDOR_ID, PRODUCT_ID, PRODUCT_NAME, SERIAL_NUMBER,
    ShinkansenController, _usb_backend,
)


def print_separator(char="─", width=72):
    print(char * width)


def print_device_details(dev: usb.core.Device, indent: str = "  "):
    """Print detailed information about a USB device."""
    print(f"{indent}VID:PID        = 0x{dev.idVendor:04X}:0x{dev.idProduct:04X}")
    print(f"{indent}Bus/Address    = {dev.bus}/{dev.address}")
    print(f"{indent}USB Version    = {dev.bcdUSB >> 8}.{(dev.bcdUSB >> 4) & 0xF}{dev.bcdUSB & 0xF}")
    print(f"{indent}Device Class   = 0x{dev.bDeviceClass:02X} / Sub 0x{dev.bDeviceSubClass:02X} / Proto 0x{dev.bDeviceProtocol:02X}")
    print(f"{indent}Max Packet     = {dev.bMaxPacketSize0}")
    print(f"{indent}bcdDevice      = {dev.bcdDevice >> 8}.{(dev.bcdDevice >> 4) & 0xF}{dev.bcdDevice & 0xF}")
    print(f"{indent}Configurations = {dev.bNumConfigurations}")

    # String descriptors
    try:
        manufacturer = usb.util.get_string(dev, dev.iManufacturer)
        print(f"{indent}Manufacturer   = {manufacturer}")
    except Exception:
        print(f"{indent}Manufacturer   = (unavailable)")

    try:
        product = usb.util.get_string(dev, dev.iProduct)
        print(f"{indent}Product        = {product}")
    except Exception:
        print(f"{indent}Product        = (unavailable)")

    try:
        serial = usb.util.get_string(dev, dev.iSerialNumber)
        print(f"{indent}Serial Number  = {serial}")
    except Exception:
        print(f"{indent}Serial Number  = (unavailable)")

    # Configuration & Interface details
    for cfg in dev:
        print(f"{indent}Configuration {cfg.bConfigurationValue}:")
        print(f"{indent}  Max Power    = {cfg.bMaxPower * 2} mA")
        print(f"{indent}  Self Powered = {bool(cfg.bmAttributes & 0x40)}")
        print(f"{indent}  Remote Wake  = {bool(cfg.bmAttributes & 0x20)}")

        for intf in cfg:
            print(f"{indent}  Interface {intf.bInterfaceNumber} (Alt {intf.bAlternateSetting}):")
            class_name = {0x03: "HID", 0xFF: "Vendor-Specific"}.get(
                intf.bInterfaceClass, f"0x{intf.bInterfaceClass:02X}"
            )
            print(f"{indent}    Class      = {class_name}")
            print(f"{indent}    SubClass   = 0x{intf.bInterfaceSubClass:02X}")
            print(f"{indent}    Protocol   = 0x{intf.bInterfaceProtocol:02X}")
            print(f"{indent}    Endpoints  = {intf.bNumEndpoints}")

            for ep in intf:
                direction = "IN" if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else "OUT"
                transfer_type = {
                    usb.util.ENDPOINT_TYPE_CTRL: "Control",
                    usb.util.ENDPOINT_TYPE_ISO: "Isochronous",
                    usb.util.ENDPOINT_TYPE_BULK: "Bulk",
                    usb.util.ENDPOINT_TYPE_INTR: "Interrupt",
                }.get(usb.util.endpoint_type(ep.bmAttributes), "Unknown")

                print(f"{indent}    Endpoint 0x{ep.bEndpointAddress:02X}:")
                print(f"{indent}      Direction    = {direction}")
                print(f"{indent}      Type         = {transfer_type}")
                print(f"{indent}      Max Packet   = {ep.wMaxPacketSize}")
                print(f"{indent}      Interval     = {ep.bInterval}")


def scan_for_controller():
    """Look specifically for the TCPP-20011 controller."""
    print_separator("═")
    print("  TAITO TCPP-20011 SHINKANSEN CONTROLLER SCANNER")
    print_separator("═")
    print()

    # Step 1: Check if libusb backend is available
    print("[1/3] Checking USB backend...")
    if _usb_backend is None:
        print("  ERROR: No libusb backend found.")
        print("  Install libusb or place libusb-1.0.dll in PATH.")
        return False
    else:
        print("  libusb1 backend: OK")
    print()

    # Step 2: Search for the specific controller
    print(f"[2/3] Searching for Taito controller (VID=0x{VENDOR_ID:04X}, PID=0x{PRODUCT_ID:04X})...")
    dev = ShinkansenController.find_device()

    if dev is not None:
        print("  FOUND! Controller details:")
        print()
        print_device_details(dev, indent="    ")
        print()
        print("  Controller is ready to use.")
        return True
    else:
        print("  NOT FOUND with expected VID:PID.")
        print()

    # Step 3: List all USB devices to help identify
    print("[3/3] Listing all USB devices to help identify the controller...")
    print()

    all_devices = list(usb.core.find(find_all=True, backend=_usb_backend))
    if not all_devices:
        print("  No USB devices found at all. Check:")
        print("    - Is the controller plugged in?")
        print("    - Is a libwdi/WinUSB driver installed for it?")
        print("    - Is libusb DLL accessible? (try placing libusb-1.0.dll in this directory)")
        return False

    # Also look for other Taito devices
    taito_devices = [d for d in all_devices if d.idVendor == VENDOR_ID]
    if taito_devices:
        print(f"  Found {len(taito_devices)} Taito device(s) with different PID:")
        for dev in taito_devices:
            print()
            print_device_details(dev, indent="    ")
        print()
        print("  One of these may be your controller with a different PID.")
        print("  Update PRODUCT_ID in controller.py if needed.")
        return False

    # List all devices
    print(f"  Found {len(all_devices)} USB device(s) total:")
    print()
    for i, dev in enumerate(all_devices):
        try:
            product = usb.util.get_string(dev, dev.iProduct) if dev.iProduct else "(no name)"
        except Exception:
            product = "(unavailable)"

        try:
            manufacturer = usb.util.get_string(dev, dev.iManufacturer) if dev.iManufacturer else ""
        except Exception:
            manufacturer = ""

        label = f"{manufacturer} {product}".strip() or "(unknown)"
        print(f"  [{i+1:2d}] 0x{dev.idVendor:04X}:0x{dev.idProduct:04X}  {label}")

    print()
    print("  The controller was not found among these devices.")
    print("  Ensure the libwdi driver is installed and the controller is connected.")
    return False


def try_read_test():
    """Attempt to read a few input reports from the controller."""
    print()
    print_separator("═")
    print("  INPUT READ TEST")
    print_separator("═")
    print()

    try:
        with ShinkansenController() as ctrl:
            print("Reading 20 input reports (press Ctrl+C to stop)...")
            print()
            for i in range(20):
                raw = ctrl.read_input_raw(timeout_ms=500)
                if raw:
                    hex_str = " ".join(f"{b:02X}" for b in raw)
                    parsed = ctrl.read_input.__wrapped__(ctrl, timeout_ms=500) if hasattr(ctrl.read_input, '__wrapped__') else None
                    state = None
                    from controller import parse_input
                    try:
                        state = parse_input(raw)
                    except Exception:
                        pass

                    line = f"  [{i+1:2d}] Raw: {hex_str}"
                    if state:
                        line += f"  =>  {state}"
                    print(line)
                else:
                    print(f"  [{i+1:2d}] (timeout - no data)")
                import time
                time.sleep(0.05)
    except RuntimeError as e:
        print(f"  Error: {e}")
    except KeyboardInterrupt:
        print("\n  Stopped by user.")


if __name__ == "__main__":
    found = scan_for_controller()

    if found and "--read" in sys.argv:
        try_read_test()
    elif found:
        print()
        print("  Run with --read to test reading input from the controller.")

    print()
    print_separator("═")
    print("  Scan complete.")
    print_separator("═")
