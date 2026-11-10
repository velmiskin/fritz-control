import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from net.http_server import AsyncHTTPServer, HTTPError, Request, Response


class FakeReader:
    def __init__(self, data):
        self.data = bytearray(data)

    async def readline(self):
        if not self.data:
            return b""
        position = self.data.find(b"\n")
        if position < 0:
            position = len(self.data) - 1
        line = bytes(self.data[:position + 1])
        del self.data[:position + 1]
        return line

    async def readexactly(self, size):
        if len(self.data) < size:
            raise EOFError()
        value = bytes(self.data[:size])
        del self.data[:size]
        return value


class FakeWriter:
    def __init__(self):
        self.data = bytearray()

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        pass


async def unused_handler(request):
    return Response.json({"ok": True})


def test_bounded_request_parser_and_json_body():
    body = b'{"duration":900}'
    raw = (
        b"POST /api/timer HTTP/1.1\r\nHost: esp\r\n"
        b"Content-Type: application/json\r\nContent-Length: " +
        str(len(body)).encode() + b"\r\n\r\n" + body
    )
    request = asyncio.run(AsyncHTTPServer(unused_handler).read_request(FakeReader(raw)))
    assert request.method == "POST"
    assert request.path == "/api/timer"
    assert request.json() == {"duration": 900}


@pytest.mark.parametrize("raw,status", [
    (b"GET / HTTP/1.0\r\n\r\n", 400),
    (b"GET / HTTP/1.1\r\nHost: a\r\nHost: b\r\n\r\n", 400),
    (b"POST / HTTP/1.1\r\nContent-Length: 99999\r\n\r\n", 413),
    (b"POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n", 400),
])
def test_malformed_or_oversized_requests_fail_closed(raw, status):
    with pytest.raises(HTTPError) as exc:
        asyncio.run(AsyncHTTPServer(unused_handler).read_request(FakeReader(raw)))
    assert exc.value.status == status


def test_response_has_security_and_length_headers():
    writer = FakeWriter()
    asyncio.run(AsyncHTTPServer(unused_handler).write_response(
        writer, Response.json({"ok": True})
    ))
    output = bytes(writer.data)
    assert output.startswith(b"HTTP/1.1 200 OK\r\n")
    assert b"X-Content-Type-Options: nosniff\r\n" in output
    assert b"Content-Length:" in output
