"""Explicit host-side WAN access operation for hardware acceptance."""

import argparse
import asyncio
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from core.config import Config
from fritz.host_filter import HostFilterService, validate_ipv4
from fritz.tr064 import TR064Client, TR064Error


async def create_service(config_path):
    config = Config.load(str(config_path))
    if not config.fritz_password:
        raise ValueError("FRITZ!Box password is missing")

    client = TR064Client(
        host=config.fritz_host,
        port=config.fritz_port,
        username=config.fritz_user,
        password=config.fritz_password,
        use_ssl=config.fritz_use_ssl,
    )
    service = HostFilterService(client)
    capabilities = await service.discover_capabilities()
    for action in ("GetWANAccessByIP", "DisallowWANAccessByIP"):
        if not capabilities.supports(action):
            raise TR064Error("Router does not advertise {}".format(action))
    return client, service


async def read_status(config_path, ip_address):
    _, service = await create_service(config_path)
    status = await service.get_wan_access_by_ip(ip_address)
    print("Status: ip={} disallow={} wan_access={}".format(
        ip_address, status["disallow"], status["wan_access"]
    ))
    return status


async def set_and_verify(config_path, ip_address, disallow):
    client, service = await create_service(config_path)

    try:
        before = await service.get_wan_access_by_ip(ip_address)
    except TR064Error as exc:
        if exc.status_code == 401:
            print(
                "Digest challenge: algorithm={} qop={} charset={} "
                "opaque_present={} userhash={}".format(
                    client.algorithm, client.qop, client.charset or "not-advertised",
                    client.opaque is not None, client.userhash,
                )
            )
        raise
    print("Before: ip={} disallow={} wan_access={}".format(
        ip_address, before["disallow"], before["wan_access"]
    ))
    result = await service.set_wan_access_and_verify(
        ip_address, disallow=disallow, retries=10, delay_sec=1
    )
    print("After: ip={} disallow={} wan_access={} verified={} reason={}".format(
        ip_address, result["disallow"], result["wan_access"],
        result["verified"], result["reason"],
    ))
    if not result["verified"]:
        raise TR064Error("Block command was not verified")
    return before, result


async def block_and_verify(config_path, ip_address):
    return await set_and_verify(config_path, ip_address, disallow=True)


async def allow_and_verify(config_path, ip_address):
    return await set_and_verify(config_path, ip_address, disallow=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--status", help="read IPv4 WAN status without changes")
    operation.add_argument("--block", help="IPv4 address to block")
    operation.add_argument("--allow", help="IPv4 address to allow")
    parser.add_argument(
        "--confirm-block",
        help="must exactly repeat --block to authorize the state change",
    )
    parser.add_argument(
        "--confirm-allow",
        help="must exactly repeat --allow to authorize the state change",
    )
    args = parser.parse_args(argv)
    try:
        if not args.config.is_file():
            raise ValueError("Configuration file does not exist")
        if args.status:
            if args.confirm_block is not None or args.confirm_allow is not None:
                raise ValueError("confirmation flags are only valid with a state change")
            asyncio.run(read_status(args.config, validate_ipv4(args.status)))
        elif args.block:
            if args.confirm_allow is not None:
                raise ValueError("--confirm-allow is only valid with --allow")
            ip_address = validate_ipv4(args.block)
            if args.confirm_block != ip_address:
                raise ValueError("--confirm-block must exactly match --block")
            asyncio.run(block_and_verify(args.config, ip_address))
        else:
            if args.confirm_block is not None:
                raise ValueError("--confirm-block is only valid with --block")
            ip_address = validate_ipv4(args.allow)
            if args.confirm_allow != ip_address:
                raise ValueError("--confirm-allow must exactly match --allow")
            asyncio.run(allow_and_verify(args.config, ip_address))
    except (OSError, ValueError, TR064Error) as exc:
        print("Access operation failed: {}".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
