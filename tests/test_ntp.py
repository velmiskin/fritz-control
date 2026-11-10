import asyncio
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from net.ntp import (
    NTPClient, NTPError, NTP_UNIX_DELTA, parse_dns_a_response,
    unix_to_rtc_datetime,
)


class FakeSocket:
    def __init__(self, response_factory=None):
        self.response_factory = response_factory
        self.response = None
        self.address = None
        self.closed = False

    def setblocking(self, value):
        assert value is False

    def sendto(self, payload, address):
        self.address = address
        if self.response_factory:
            self.response = self.response_factory(payload)
        return len(payload)

    def recvfrom(self, size):
        if self.response is None:
            raise OSError("would block")
        response = self.response
        self.response = None
        return response[:size], self.address

    def close(self):
        self.closed = True


class FakeSocketModule:
    AF_INET = 2
    SOCK_DGRAM = 2

    def __init__(self, factories):
        self.factories = list(factories)
        self.sockets = []

    def socket(self, family, kind):
        assert family == self.AF_INET
        assert kind == self.SOCK_DGRAM
        sock = FakeSocket(self.factories.pop(0) if self.factories else None)
        self.sockets.append(sock)
        return sock


def ntp_response(unix_time, token, *, mode=4, stratum=2):
    response = bytearray(48)
    response[0] = 0x20 | mode
    response[1] = stratum
    response[24:32] = token
    seconds = unix_time + NTP_UNIX_DELTA
    response[40:44] = seconds.to_bytes(4, "big")
    return bytes(response)


def dns_response(query, address=(192, 0, 2, 123)):
    question = query[12:]
    response = bytearray(query[:2])
    response.extend(b"\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00")
    response.extend(question)
    response.extend(b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04")
    response.extend(bytes(address))
    return bytes(response)


def test_dns_parser_and_async_hostname_resolution():
    async def run():
        random_values = iter((b"\x12\x34", b"12345678"))
        sockets = FakeSocketModule((dns_response, lambda request: ntp_response(
            1798761600, request[40:48]
        )))
        client = NTPClient(
            "pool.example", dns_server="192.168.1.1", socket_module=sockets,
            random_bytes=lambda size: next(random_values), poll_interval=0.001,
        )
        result = await client.query()
        assert result == {
            "unix_time": 1798761600,
            "stratum": 2,
            "server_ip": "192.0.2.123",
        }
        assert all(sock.closed for sock in sockets.sockets)

    asyncio.run(run())


def test_dns_parser_rejects_wrong_query_id():
    query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" \
            b"\x04pool\x07example\x00\x00\x01\x00\x01"
    with pytest.raises(NTPError, match="match"):
        parse_dns_a_response(dns_response(query), 0x5678)


def test_ntp_query_validates_originate_token():
    async def run():
        sockets = FakeSocketModule((lambda request: ntp_response(
            1798761600, b"badtoken"
        ),))
        client = NTPClient(
            "192.0.2.123", socket_module=sockets,
            random_bytes=lambda size: b"12345678", poll_interval=0.001,
        )
        with pytest.raises(NTPError, match="does not match"):
            await client.query()

    asyncio.run(run())


def test_ntp_timeout_is_bounded():
    async def run():
        sockets = FakeSocketModule((None, None))
        client = NTPClient(
            "192.0.2.123", socket_module=sockets,
            random_bytes=lambda size: b"12345678", timeout=0.005,
            retries=2, poll_interval=0.001,
        )
        with pytest.raises(NTPError, match="timed out"):
            await client.query()
        assert len(sockets.sockets) == 2
        assert all(sock.closed for sock in sockets.sockets)

    asyncio.run(run())


def test_synchronize_sets_utc_rtc_only_after_valid_response():
    class FakeRTC:
        value = None

        def datetime(self, value):
            self.value = value

    async def run():
        timestamp = int(datetime.datetime(
            2027, 1, 1, tzinfo=datetime.timezone.utc
        ).timestamp())
        sockets = FakeSocketModule((lambda request: ntp_response(
            timestamp, request[40:48]
        ),))
        rtc = FakeRTC()
        client = NTPClient(
            "192.0.2.123", socket_module=sockets,
            random_bytes=lambda size: b"12345678", poll_interval=0.001,
        )
        result = await client.synchronize(rtc)
        assert result["unix_time"] == timestamp
        assert rtc.value == (2027, 1, 1, 4, 0, 0, 0, 0)
        assert client.is_synchronized() is True
        assert timestamp <= client.now() <= timestamp + 1

    asyncio.run(run())


def test_unix_to_rtc_datetime_handles_leap_day():
    timestamp = int(datetime.datetime(
        2024, 2, 29, 12, 34, 56, tzinfo=datetime.timezone.utc
    ).timestamp())
    assert unix_to_rtc_datetime(timestamp) == (2024, 2, 29, 3, 12, 34, 56, 0)


def test_now_rejects_unsynchronized_clock():
    with pytest.raises(NTPError, match="not been synchronized"):
        NTPClient("192.0.2.123").now()
