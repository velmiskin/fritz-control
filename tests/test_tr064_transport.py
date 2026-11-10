import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from fritz.tr064 import TR064Client, TR064Error


SOAP_OK = b"<s:Envelope><s:Body><Result>ok</Result></s:Body></s:Envelope>"


async def read_request(reader):
    request_line = await reader.readline()
    headers = {}
    while True:
        line = await reader.readline()
        if line in (b"\r\n", b"\n", b""):
            break
        key, value = line.decode("iso-8859-1").split(":", 1)
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    body = await reader.readexactly(length) if length else b""
    return request_line, headers, body


async def send_response(writer, status, body=b"", headers=None):
    response_headers = {"Content-Length": str(len(body)), "Connection": "close"}
    response_headers.update(headers or {})
    writer.write("HTTP/1.1 {}\r\n".format(status).encode("ascii"))
    for key, value in response_headers.items():
        writer.write("{}: {}\r\n".format(key, value).encode("ascii"))
    writer.write(b"\r\n" + body)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def run_with_server(handler, client_call):
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        return await client_call(port)
    finally:
        server.close()
        await server.wait_closed()


def test_digest_retry_and_utf8_content_length():
    async def run():
        requests = []

        async def handler(reader, writer):
            request = await read_request(reader)
            requests.append(request)
            if len(requests) == 1:
                await send_response(writer, "401 Unauthorized", headers={
                    "WWW-Authenticate": (
                        'Digest realm="fritz", nonce="abc", '
                        'qop="auth,auth-int", opaque="opaque-value"'
                    )
                })
            else:
                await send_response(writer, "200 OK", SOAP_OK)

        async def client_call(port):
            client = TR064Client("127.0.0.1", port, "user", "password")
            return await client.call_action(
                "/control", "urn:test", "Action", {"NewName": "München & tablet"}
            )

        result = await run_with_server(handler, client_call)
        assert "<Result>ok</Result>" in result
        assert len(requests) == 2
        for _, headers, body in requests:
            assert int(headers["content-length"]) == len(body)
            assert b"M\xc3\xbcnchen &amp; tablet" in body
        assert requests[1][1]["authorization"].startswith("Digest ")
        assert 'opaque="opaque-value"' in requests[1][1]["authorization"]
    asyncio.run(run())


def test_chunked_document_response():
    async def run():
        async def handler(reader, writer):
            await read_request(reader)
            writer.write(
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
                b"5\r\n<root\r\n7\r\n>ok</ro\r\n3\r\not>\r\n0\r\n\r\n"
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        async def client_call(port):
            return await TR064Client("127.0.0.1", port).get_document("/scpd.xml")

        assert await run_with_server(handler, client_call) == "<root>ok</root>"
    asyncio.run(run())


def test_oversized_and_malformed_responses_fail_closed():
    async def run_case(response):
        async def handler(reader, writer):
            await read_request(reader)
            writer.write(response)
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        async def client_call(port):
            client = TR064Client("127.0.0.1", port, max_response_size=8)
            with pytest.raises(TR064Error):
                await client.get_document("/doc", max_body_size=8)

        await run_with_server(handler, client_call)

    async def run():
        await run_case(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n")
        await run_case(b"NOT-HTTP\r\n\r\n")
    asyncio.run(run())


def test_soap_fault_is_reported_even_with_http_500():
    async def run():
        fault = (
            b"<env:Envelope><env:Body><env:Fault><faultstring>UPnPError</faultstring>"
            b"<detail><errorCode>714</errorCode><errorDescription>NoSuchEntryInArray"
            b"</errorDescription></detail></env:Fault></env:Body></env:Envelope>"
        )

        async def handler(reader, writer):
            await read_request(reader)
            await send_response(writer, "500 Internal Server Error", fault)

        async def client_call(port):
            client = TR064Client("127.0.0.1", port)
            with pytest.raises(TR064Error) as exc:
                await client.call_action("/control", "urn:test", "Action")
            assert exc.value.error_code == 714
            assert exc.value.status_code == 500

        await run_with_server(handler, client_call)
    asyncio.run(run())


def test_transport_timeout_and_https_rejection():
    async def run():
        async def handler(reader, writer):
            await read_request(reader)
            await asyncio.sleep(0.05)
            writer.close()
            await writer.wait_closed()

        async def client_call(port):
            client = TR064Client("127.0.0.1", port, timeout=0.01)
            with pytest.raises(TR064Error, match="timed out"):
                await client.get_document("/slow")
            await asyncio.sleep(0.06)

        await run_with_server(handler, client_call)
        with pytest.raises(ValueError, match="HTTPS"):
            TR064Client(use_ssl=True)
    asyncio.run(run())
