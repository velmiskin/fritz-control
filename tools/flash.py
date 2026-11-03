"""
tools/flash.py - Erase flash and flash MicroPython firmware to ESP32

Usage:
    python tools/flash.py COM3 firmware/esp32-20230426-v1.20.0.bin
"""

import sys
import subprocess

def main():
    if len(sys.argv) < 3:
        print("Usage: python tools/flash.py <COM_PORT> <FIRMWARE_BIN_PATH>")
        print("Example: python tools/flash.py COM3 firmware/esp32-ESP32_GENERIC-20240222-v1.22.2.bin")
        sys.exit(1)

    port = sys.argv[1]
    firmware_path = sys.argv[2]

    print(f"Erasing flash on {port}...")
    subprocess.run(f"esptool.py --port {port} erase_flash", shell=True, check=True)

    print(f"Flashing firmware {firmware_path} to {port}...")
    subprocess.run(
        f"esptool.py --chip esp32 --port {port} --baud 460800 write_flash -z 0x1000 {firmware_path}",
        shell=True,
        check=True
    )
    print("Flashing completed successfully!")

if __name__ == "__main__":
    main()
