import os
import sys
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fritz.tr064 import TR064Client, TR064Error
from fritz.hosts import HostsService
from fritz.capabilities import ServiceCapabilities

MOCKS_DIR = os.path.join(os.path.dirname(__file__), "mocks")

def load_mock(filename):
    with open(os.path.join(MOCKS_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()

def test_hosts_get_number_of_entries():
    async def run():
        client = MagicMock(spec=TR064Client)
        client.call_action = AsyncMock(return_value=load_mock("hosts_count.xml"))

        service = HostsService(client)
        count = await service.get_host_number_of_entries()
        assert count == 3
        client.call_action.assert_awaited_once_with(
            control_url="/upnp/control/hosts",
            service_type="urn:dslforum-org:service:Hosts:1",
            action_name="GetHostNumberOfEntries"
        )
    asyncio.run(run())

def test_hosts_rejects_unadvertised_optional_action():
    async def run():
        client = MagicMock(spec=TR064Client)
        service = HostsService(
            client, capabilities=ServiceCapabilities("urn:test", "/scpd", [])
        )
        with pytest.raises(TR064Error, match="does not advertise"):
            await service.get_specific_host_by_ip("192.168.178.20")
        client.call_action.assert_not_called()
    asyncio.run(run())

def test_hosts_rejects_invalid_ipv4_before_router_call():
    async def run():
        client = MagicMock(spec=TR064Client)
        service = HostsService(client)
        with pytest.raises(ValueError):
            await service.get_specific_host_by_ip("192.168.1.999")
        client.call_action.assert_not_called()
    asyncio.run(run())

def test_hosts_get_generic_host_entry():
    async def run():
        client = MagicMock(spec=TR064Client)
        client.call_action = AsyncMock(return_value=load_mock("hosts_entry_0.xml"))

        service = HostsService(client)
        host = await service.get_generic_host_entry(0)
        assert host["ip"] == "192.168.178.20"
        assert host["mac"] == "AA:BB:CC:DD:EE:01"
        assert host["hostname"] == "Kids-Tablet"
        assert host["active"] is True
        assert host["interface"] == "802.11"
        assert host["lease_time"] == 86400
    asyncio.run(run())

def test_hosts_get_specific_host_by_ip():
    async def run():
        client = MagicMock(spec=TR064Client)
        client.call_action = AsyncMock(return_value=load_mock("hosts_specific_ip.xml"))

        capabilities = ServiceCapabilities(
            "urn:test", "/scpd", ["X_AVM-DE_GetSpecificHostEntryByIP"]
        )
        service = HostsService(client, capabilities=capabilities)
        host = await service.get_specific_host_by_ip("192.168.178.20")
        assert host["ip"] == "192.168.178.20"
        assert host["friendly_name"] == "Kid Tablet Pro"
        assert host["wan_access"] == "granted"
        assert host["disallow"] is False
    asyncio.run(run())

def test_hosts_get_all_hosts_with_714_termination():
    async def run():
        client = MagicMock(spec=TR064Client)
        
        async def mock_call(control_url, service_type, action_name, params=None):
            if action_name == "GetHostNumberOfEntries":
                return load_mock("hosts_count.xml")
            elif action_name == "GetGenericHostEntry":
                idx = int(params["NewIndex"])
                if idx == 0:
                    return load_mock("hosts_entry_0.xml")
                else:
                    raise TR064Error("NoSuchEntryInArray", error_code=714)
            return ""

        client.call_action = AsyncMock(side_effect=mock_call)

        service = HostsService(client)
        hosts = await service.get_all_hosts()
        assert len(hosts) == 1
        assert hosts[0]["hostname"] == "Kids-Tablet"
    asyncio.run(run())

def test_tr064_digest_auth_header_generation():
    client = TR064Client(username="testuser", password="secretpassword")
    
    # Simulate receiving WWW-Authenticate
    www_auth = 'Digest realm="avm_fritz_box", nonce="12345678", qop="auth"'
    client._parse_www_authenticate(www_auth)
    
    assert client.realm == "avm_fritz_box"
    assert client.nonce == "12345678"
    assert client.qop == "auth"

    header = client._build_auth_header("POST", "/upnp/control/hosts")
    assert 'Digest username="testuser"' in header
    assert 'realm="avm_fritz_box"' in header
    assert 'nonce="12345678"' in header
    assert 'qop=auth' in header
    assert 'nc=00000001' in header
