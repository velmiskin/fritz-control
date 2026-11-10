"""Erase an ESP32 and flash a selected MicroPython firmware image."""

import argparse
from pathlib import Path
import subprocess
import sys


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="serial port, for example COM3")
    parser.add_argument("firmware", type=Path, help="path to a .bin firmware image")
    parser.add_argument("--yes", action="store_true",
                        help="confirm destructive flash erase without prompting")
    return parser


def flash(port, firmware, confirmed=False, input_func=input):
    firmware = firmware.resolve()
    if not firmware.is_file():
        raise ValueError("Firmware image does not exist: {}".format(firmware))
    if firmware.suffix.lower() != ".bin":
        raise ValueError("Firmware image must use the .bin extension")
    if not confirmed:
        answer = input_func(
            "This will erase all data on {}. Type the port name to continue: ".format(port)
        )
        if answer.strip() != port:
            raise ValueError("Flash cancelled")

    base = [sys.executable, "-m", "esptool", "--port", port]
    subprocess.run(base + ["erase_flash"], check=True)
    subprocess.run(base + [
        "--chip", "esp32", "--baud", "460800", "write_flash", "-z",
        "0x1000", str(firmware),
    ], check=True)
    print("Flashing completed successfully and all commands returned zero.")


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        flash(args.port, args.firmware, confirmed=args.yes)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print("Flashing failed: {}".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
