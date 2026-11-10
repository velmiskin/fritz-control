"""Read-only login and dashboard API acceptance probe."""

import argparse
import http.client
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _request(connection, method, path, body=None, headers=None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        request_headers["Content-Length"] = str(len(payload))
    connection.request(method, path, body=payload, headers=request_headers)
    response = connection.getresponse()
    data = response.read()
    if response.status < 200 or response.status >= 300:
        raise RuntimeError("Dashboard returned HTTP {} for {}".format(
            response.status, path
        ))
    return response, data


def probe_dashboard(host, port, config_path, connection_factory=None):
    with Path(config_path).open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    password = config.get("web", {}).get("admin_password", "")
    if not isinstance(password, str) or len(password) < 12:
        raise RuntimeError("Configuration requires a unique web admin password")
    factory = connection_factory or http.client.HTTPConnection
    # Entry-by-entry Hosts:1 discovery is deliberately sequential on the ESP32
    # and can take over 30 seconds on a populated router.
    connection = factory(host, port, timeout=90)
    try:
        _, page = _request(connection, "GET", "/")
        if b"FritzControl" not in page:
            raise RuntimeError("Dashboard HTML marker is missing")
        login_response, login_body = _request(
            connection, "POST", "/api/login", {"password": password}
        )
        login = json.loads(login_body.decode("utf-8"))
        cookie = login_response.getheader("Set-Cookie", "").split(";", 1)[0]
        if not cookie or not login.get("csrf"):
            raise RuntimeError("Login did not return session and CSRF tokens")
        headers = {"Cookie": cookie}
        _, status_body = _request(connection, "GET", "/api/status", headers=headers)
        _, timers_body = _request(connection, "GET", "/api/timers", headers=headers)
        _, schedules_body = _request(connection, "GET", "/api/schedules", headers=headers)
        status = json.loads(status_body.decode("utf-8"))
        timers = json.loads(timers_body.decode("utf-8"))["timers"]
        schedules = json.loads(schedules_body.decode("utf-8"))["policies"]
        devices = []
        offset = 0
        total = 1
        while offset < total:
            _, devices_body = _request(
                connection, "GET",
                "/api/devices?offset={}&limit=8".format(offset),
                headers=headers,
            )
            page = json.loads(devices_body.decode("utf-8"))
            devices.extend(page["devices"])
            total = page["total"]
            offset += len(page["devices"])
            if not page["devices"]:
                break
        print("dashboard_probe PASS")
        print("recovery_ok", status.get("recovery_ok"))
        print("clock_synchronized", status.get("clock_synchronized"))
        print("devices", len(devices))
        print("timers", len(timers))
        print("schedules", len(schedules))
        return status, devices
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="ESP32 LAN IPv4 address")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    args = parser.parse_args(argv)
    try:
        probe_dashboard(args.host, args.port, args.config)
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError,
            http.client.HTTPException) as exc:
        print("Dashboard probe failed: {}".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
