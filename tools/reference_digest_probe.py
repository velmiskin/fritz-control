"""Host-only read-only Digest reference probe using CPython urllib."""

import argparse
from pathlib import Path
import sys
import urllib.error
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.config import Config
from fritz.host_filter import HOST_FILTER_CONTROL_URL, HOST_FILTER_SERVICE_TYPE
from fritz.soap import build_soap_envelope
from fritz.soap import extract_tag_value
from fritz.validation import validate_ipv4


def probe(config_path, ip_address):
    config = Config.load(str(config_path))
    if config.fritz_use_ssl:
        raise ValueError("Reference probe supports configured HTTP only")
    password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    url = "http://{}:{}{}".format(
        config.fritz_host, config.fritz_port, HOST_FILTER_CONTROL_URL
    )
    password_manager.add_password(
        None, url, config.fritz_user, config.fritz_password
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(password_manager)
    )
    envelope = build_soap_envelope(
        HOST_FILTER_SERVICE_TYPE,
        "GetWANAccessByIP",
        {"NewIPv4Address": validate_ipv4(ip_address)},
    ).encode("utf-8")
    request = urllib.request.Request(
        url, data=envelope, method="POST",
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": '"{}#GetWANAccessByIP"'.format(HOST_FILTER_SERVICE_TYPE),
        },
    )
    with opener.open(request, timeout=5) as response:
        body = response.read().decode("utf-8")
        disallow = extract_tag_value(body, "NewDisallow")
        wan_access = extract_tag_value(body, "NewWANAccess")
        print(
            "CPython reference Digest probe: HTTP {} disallow={} wan_access={}".format(
                response.status, disallow, wan_access
            )
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    parser.add_argument("--ip", required=True)
    args = parser.parse_args(argv)
    try:
        probe(args.config, args.ip)
    except urllib.error.HTTPError as exc:
        print("CPython reference Digest probe: HTTP {}".format(exc.code))
        return 1
    except (OSError, ValueError) as exc:
        print("CPython reference Digest probe failed: {}".format(type(exc).__name__))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
