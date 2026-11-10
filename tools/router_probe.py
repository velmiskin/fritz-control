"""Read-only live SCPD capability probe for a FRITZ!Box."""

import argparse
import asyncio
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fritz.capabilities import ServiceCapabilities
from fritz.host_filter import HOST_FILTER_SCPD_URL, HOST_FILTER_SERVICE_TYPE
from fritz.hosts import HOSTS_SCPD_URL, HOSTS_SERVICE_TYPE
from fritz.tr064 import TR064Client, TR064Error


REQUIRED_ACTIONS = {
    HOST_FILTER_SERVICE_TYPE: (
        "DisallowWANAccessByIP", "GetWANAccessByIP", "GetHostEntryByIP",
    ),
    HOSTS_SERVICE_TYPE: (
        "GetHostNumberOfEntries", "GetGenericHostEntry",
        "X_AVM-DE_GetSpecificHostEntryByIP",
    ),
}


async def probe(host, port):
    client = TR064Client(host=host, port=port, timeout=5)
    services = (
        (HOST_FILTER_SERVICE_TYPE, HOST_FILTER_SCPD_URL),
        (HOSTS_SERVICE_TYPE, HOSTS_SCPD_URL),
    )
    for service_type, scpd_url in services:
        capabilities = await ServiceCapabilities.discover(
            client, service_type, scpd_url
        )
        missing = [
            action for action in REQUIRED_ACTIONS[service_type]
            if not capabilities.supports(action)
        ]
        if missing:
            raise TR064Error(
                "{} missing required actions: {}".format(
                    service_type, ", ".join(missing)
                )
            )
        print("{}: required actions present ({} advertised)".format(
            service_type, len(capabilities.actions)
        ))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.178.1")
    parser.add_argument("--port", type=int, default=49000)
    args = parser.parse_args(argv)
    try:
        asyncio.run(probe(args.host, args.port))
    except (OSError, ValueError, TR064Error) as exc:
        print("Router capability probe failed: {}".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
