import os
import sys
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fritz.tr064 import TR064Client, TR064Error
from fritz.host_filter import HostFilterService

MOCKS_DIR = os.path.join(os.path.dirname(__file__), "mocks")

def load_mock(filename):
    with open(os.path.join(MOCKS_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()

def test_host_filter_get_wan_access_allowed():
    async def run():
        client = MagicMock(spec=TR064Client)
        client.call_action = AsyncMock(return_value=load_mock("host_filter_get_wan_allowed.xml"))

        service = HostFilterService(client)
        status = await service.get_wan_access_by_ip("192.168.178.20")
        assert status["ip"] == "192.168.178.20"
        assert status["disallow"] is False
        assert status["wan_access"] == "granted"

        client.call_action.assert_awaited_once_with(
            control_url="/upnp/control/x_hostfilter",
            service_type="urn:dslforum-org:service:X_AVM-DE_HostFilter:1",
            action_name="GetWANAccessByIP",
            params={"NewIPv4Address": "192.168.178.20"}
        )
    asyncio.run(run())

def test_host_filter_get_wan_access_disallowed():
    async def run():
        client = MagicMock(spec=TR064Client)
        client.call_action = AsyncMock(return_value=load_mock("host_filter_get_wan_disallowed.xml"))

        service = HostFilterService(client)
        status = await service.get_wan_access_by_ip("192.168.178.20")
        assert status["ip"] == "192.168.178.20"
        assert status["disallow"] is True
        assert status["wan_access"] == "denied"
    asyncio.run(run())

def test_host_filter_disallow_wan_access():
    async def run():
        client = MagicMock(spec=TR064Client)
        client.call_action = AsyncMock(return_value=load_mock("host_filter_disallow_response.xml"))

        service = HostFilterService(client)
        # Test blocking (disallow=True)
        await service.disallow_wan_access_by_ip("192.168.178.20", disallow=True)
        client.call_action.assert_awaited_with(
            control_url="/upnp/control/x_hostfilter",
            service_type="urn:dslforum-org:service:X_AVM-DE_HostFilter:1",
            action_name="DisallowWANAccessByIP",
            params={"NewIPv4Address": "192.168.178.20", "NewDisallow": "1"}
        )

        # Test unblocking (disallow=False)
        await service.disallow_wan_access_by_ip("192.168.178.20", disallow=False)
        client.call_action.assert_awaited_with(
            control_url="/upnp/control/x_hostfilter",
            service_type="urn:dslforum-org:service:X_AVM-DE_HostFilter:1",
            action_name="DisallowWANAccessByIP",
            params={"NewIPv4Address": "192.168.178.20", "NewDisallow": "0"}
        )
    asyncio.run(run())

def test_host_filter_set_and_verify_success():
    async def run():
        client = MagicMock(spec=TR064Client)
        call_count = 0

        async def mock_call(control_url, service_type, action_name, params=None):
            nonlocal call_count
            if action_name == "DisallowWANAccessByIP":
                return load_mock("host_filter_disallow_response.xml")
            elif action_name == "GetWANAccessByIP":
                call_count += 1
                # First check: still allowed, second check: disallowed
                if call_count == 1:
                    return load_mock("host_filter_get_wan_allowed.xml")
                else:
                    return load_mock("host_filter_get_wan_disallowed.xml")
            return ""

        client.call_action = AsyncMock(side_effect=mock_call)

        service = HostFilterService(client)
        res = await service.set_wan_access_and_verify("192.168.178.20", disallow=True, retries=2, delay_sec=0.01)
        assert res["verified"] is True
        assert res["disallow"] is True
        assert call_count == 2
    asyncio.run(run())

def test_host_filter_batch_wan_access():
    async def run():
        client = MagicMock(spec=TR064Client)
        
        async def mock_call(control_url, service_type, action_name, params=None):
            if action_name == "DisallowWANAccessByIP":
                return load_mock("host_filter_disallow_response.xml")
            elif action_name == "GetWANAccessByIP":
                return load_mock("host_filter_get_wan_disallowed.xml")
            return ""

        client.call_action = AsyncMock(side_effect=mock_call)

        service = HostFilterService(client)
        targets = ["192.168.178.20", "192.168.178.21"]
        batch_res = await service.set_batch_wan_access(targets, disallow=True, delay_between_sec=0.01)
        assert len(batch_res) == 2
        assert batch_res["192.168.178.20"]["verified"] is True
        assert batch_res["192.168.178.21"]["verified"] is True
    asyncio.run(run())

def test_host_filter_get_host_entry_by_ip():
    async def run():
        client = MagicMock(spec=TR064Client)
        client.call_action = AsyncMock(return_value=load_mock("host_filter_host_entry.xml"))

        service = HostFilterService(client)
        entry = await service.get_host_entry_by_ip("192.168.178.20")
        assert entry["ip"] == "192.168.178.20"
        assert entry["hostname"] == "Kids-Tablet"
        assert entry["profile_id"] == "2"
        assert entry["time_used"] == 1800
        assert entry["time_max"] == 7200
        assert entry["wan_access"] == "granted"
    asyncio.run(run())
