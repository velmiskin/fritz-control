import asyncio
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fritz.capabilities import ServiceCapabilities, parse_action_names


SCPD = """<?xml version="1.0"?>
<s:scpd xmlns:s="urn:schemas-upnp-org:service-1-0">
  <s:actionList>
    <s:action><s:name>GetWANAccessByIP</s:name></s:action>
    <s:action><s:name>DisallowWANAccessByIP</s:name></s:action>
  </s:actionList>
</s:scpd>"""


def test_parse_action_names_with_namespace():
    assert parse_action_names(SCPD) == (
        "GetWANAccessByIP", "DisallowWANAccessByIP"
    )


def test_capability_discovery():
    async def run():
        client = type("Client", (), {})()
        client.get_document = AsyncMock(return_value=SCPD)
        capabilities = await ServiceCapabilities.discover(
            client, "urn:test", "/x_hostfilterSCPD.xml"
        )
        assert capabilities.supports("GetWANAccessByIP")
        assert not capabilities.supports("GetHostEntryByIP")
    asyncio.run(run())


def test_capability_parser_requires_action_list():
    with pytest.raises(ValueError):
        parse_action_names("<scpd></scpd>")
