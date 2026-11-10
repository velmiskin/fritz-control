"""Run isolated, read-only authenticated Hosts discovery on an ESP32."""

import argparse
import json
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING_DIR = "phase1_discovery"
FILES = (
    ("src/core/config.py", "core/config.py"),
    ("src/core/logger.py", "core/logger.py"),
    ("src/fritz/soap.py", "fritz/soap.py"),
    ("src/fritz/tr064.py", "fritz/tr064.py"),
    ("src/fritz/capabilities.py", "fritz/capabilities.py"),
    ("src/fritz/validation.py", "fritz/validation.py"),
    ("src/fritz/hosts.py", "fritz/hosts.py"),
    ("src/net/wifi.py", "net/wifi.py"),
)


def _run(command, check=True):
    print("->", subprocess.list2cmdline([str(item) for item in command]))
    command = [str(item) for item in command]
    result = subprocess.run(
        command, check=False, capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="")
        raise subprocess.CalledProcessError(
            result.returncode, command, output=result.stdout, stderr=result.stderr
        )
    return result


def _validate_config(config_path):
    if not config_path.is_file():
        raise RuntimeError("Configuration file does not exist")
    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except (OSError, ValueError) as exc:
        raise RuntimeError("Configuration file is not valid JSON") from exc

    required = (
        ("wifi", "ssid"),
        ("wifi", "password"),
        ("fritzbox", "host"),
        ("fritzbox", "username"),
        ("fritzbox", "password"),
    )
    for section, key in required:
        value = data.get(section, {}).get(key)
        if not isinstance(value, str) or not value or value.startswith("YOUR_"):
            raise RuntimeError(
                "Configuration requires a non-placeholder {}.{} value".format(
                    section, key
                )
            )
    if data.get("fritzbox", {}).get("use_ssl", False):
        raise RuntimeError("Hardware discovery does not support use_ssl=true")


def run_hardware_discovery(port, config_path, project_root=PROJECT_ROOT):
    config_path = Path(config_path)
    _validate_config(config_path)
    prefix = ["mpremote", "connect", port]
    remote_root = ":{}".format(STAGING_DIR)
    existing = _run(prefix + ["fs", "ls", remote_root], check=False)
    if existing.returncode == 0:
        raise RuntimeError(
            "Refusing to overwrite existing /{} directory".format(STAGING_DIR)
        )

    created = False
    try:
        _run(prefix + ["fs", "mkdir", remote_root])
        created = True
        for directory in ("core", "fritz", "net"):
            _run(prefix + ["fs", "mkdir", ":{}/{}".format(STAGING_DIR, directory)])
        for local_name, remote_name in FILES:
            local_path = project_root / local_name
            if not local_path.is_file():
                raise RuntimeError("Missing discovery-test input: {}".format(local_path))
            _run(prefix + [
                "fs", "cp", str(local_path),
                ":{}/{}".format(STAGING_DIR, remote_name),
            ])
        _run(prefix + [
            "fs", "cp", str(config_path),
            ":{}/config.json".format(STAGING_DIR),
        ])
        script = project_root / "tests" / "hardware" / "phase1_discovery.py"
        result = _run(prefix + ["run", str(script)])
        print(result.stdout, end="")
        if "phase1_discovery PASS" not in result.stdout:
            raise RuntimeError("ESP32 discovery test did not report PASS")
        return result.stdout
    finally:
        if created:
            cleanup = _run(prefix + ["fs", "rm", "-r", remote_root], check=False)
            if cleanup.returncode != 0:
                raise RuntimeError(
                    "Failed to remove /{}; remove it manually because it may "
                    "contain config.json".format(STAGING_DIR)
                )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="ESP32 serial port, for example COM3")
    parser.add_argument(
        "--config", type=Path, default=PROJECT_ROOT / "config.json",
        help="local configuration copied temporarily to the isolated staging directory",
    )
    args = parser.parse_args(argv)
    try:
        run_hardware_discovery(args.port, args.config)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Hardware discovery failed: {}".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
