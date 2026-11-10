"""Stage, run and clean the read-only Phase 2.5 ESP32 smoke test."""

import argparse
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING_DIR = "phase25_smoke"
FILES = (
    ("src/core/logger.py", "core/logger.py"),
    ("src/fritz/soap.py", "fritz/soap.py"),
    ("src/fritz/tr064.py", "fritz/tr064.py"),
    ("src/fritz/capabilities.py", "fritz/capabilities.py"),
    ("src/fritz/validation.py", "fritz/validation.py"),
    ("src/fritz/host_filter.py", "fritz/host_filter.py"),
    ("src/fritz/hosts.py", "fritz/hosts.py"),
    ("src/net/wifi.py", "net/wifi.py"),
)


def _run(command, check=True):
    print("->", subprocess.list2cmdline([str(item) for item in command]))
    return subprocess.run(
        [str(item) for item in command], check=check,
        capture_output=True, text=True,
    )


def run_hardware_smoke(port, project_root=PROJECT_ROOT):
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
                raise RuntimeError("Missing smoke-test input: {}".format(local_path))
            _run(prefix + [
                "fs", "cp", str(local_path),
                ":{}/{}".format(STAGING_DIR, remote_name),
            ])
        script = project_root / "tests" / "hardware" / "phase25_smoke.py"
        result = _run(prefix + ["run", str(script)])
        print(result.stdout, end="")
        return result.stdout
    finally:
        if created:
            cleanup = _run(prefix + ["fs", "rm", "-r", remote_root], check=False)
            if cleanup.returncode != 0:
                print("WARNING: failed to remove /{} staging directory".format(STAGING_DIR))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="ESP32 serial port, for example COM3")
    args = parser.parse_args(argv)
    try:
        run_hardware_smoke(args.port)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Hardware smoke test failed: {}".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
