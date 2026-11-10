"""Bounded asynchronous HTTP/1.1 server with Flash file streaming."""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import ujson as json
except ImportError:
    import json

try:
    import uos as os
except ImportError:
    import os

import gc

from core.logger import log


MAX_REQUEST_LINE = 1024
MAX_HEADER_LINE = 1024
MAX_HEADERS = 8 * 1024
MAX_BODY = 8 * 1024
FILE_CHUNK_SIZE = 1024

STATUS_TEXT = {
    200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request",
    401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    405: "Method Not Allowed", 408: "Request Timeout",
    413: "Payload Too Large", 415: "Unsupported Media Type",
    429: "Too Many Requests", 500: "Internal Server Error",
    503: "Service Unavailable",
}


class HTTPError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class Request:
    def __init__(self, method, target, headers, body):
        self.method = method
        self.target = target
        self.path, separator, self.query = target.partition("?")
        self.headers = headers
        self.body = body

    def json(self):
        content_type = self.headers.get("content-type", "").split(";", 1)[0]
        if content_type != "application/json":
            raise HTTPError(415, "Expected application/json")
        try:
            value = json.loads(self.body.decode("utf-8"))
        except (UnicodeError, TypeError, ValueError) as exc:
            raise HTTPError(400, "Invalid JSON body") from exc
        if not isinstance(value, dict):
            raise HTTPError(400, "JSON body must be an object")
        return value


class Response:
    def __init__(self, status=200, body=b"", headers=None):
        self.status = status
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.headers = dict(headers or {})

    @classmethod
    def json(cls, value, status=200, headers=None):
        response_headers = {"Content-Type": "application/json; charset=utf-8"}
        response_headers.update(headers or {})
        return cls(status, json.dumps(value), response_headers)


class FileResponse:
    def __init__(self, path, content_type="application/octet-stream"):
        self.path = path
        self.content_type = content_type
        self.status = 200


class AsyncHTTPServer:
    def __init__(self, handler, host="0.0.0.0", port=80, timeout=10,
                 max_body=MAX_BODY):
        if timeout <= 0 or max_body <= 0:
            raise ValueError("HTTP limits must be positive")
        self.handler = handler
        self.host = host
        self.port = port
        self.timeout = timeout
        self.max_body = max_body
        self.server = None

    async def _wait(self, awaitable):
        return await asyncio.wait_for(awaitable, self.timeout)

    async def _readline(self, reader, limit):
        line = await self._wait(reader.readline())
        if len(line) > limit:
            raise HTTPError(413, "HTTP line exceeds limit")
        return line

    async def read_request(self, reader):
        request_line = await self._readline(reader, MAX_REQUEST_LINE)
        if not request_line:
            raise HTTPError(400, "Empty HTTP request")
        try:
            request_line = request_line.decode("ascii").strip()
        except UnicodeError as exc:
            raise HTTPError(400, "Invalid request-line encoding") from exc
        parts = request_line.split(" ")
        if len(parts) != 3 or parts[2] != "HTTP/1.1":
            raise HTTPError(400, "Malformed HTTP request line")
        method, target, _ = parts
        if method not in ("GET", "POST", "PUT", "DELETE"):
            raise HTTPError(405, "Unsupported HTTP method")
        if not target.startswith("/") or "\r" in target or "\n" in target:
            raise HTTPError(400, "Invalid request target")

        headers = {}
        header_bytes = 0
        while True:
            line = await self._readline(reader, MAX_HEADER_LINE)
            header_bytes += len(line)
            if header_bytes > MAX_HEADERS:
                raise HTTPError(413, "HTTP headers exceed limit")
            if line in (b"\r\n", b"\n"):
                break
            if not line:
                raise HTTPError(400, "HTTP headers ended unexpectedly")
            try:
                text = line.decode("ascii").strip()
            except UnicodeError as exc:
                raise HTTPError(400, "Invalid HTTP header encoding") from exc
            if ":" not in text:
                raise HTTPError(400, "Malformed HTTP header")
            key, value = text.split(":", 1)
            key = key.strip().lower()
            if not key or key in headers:
                raise HTTPError(400, "Invalid or duplicate HTTP header")
            headers[key] = value.strip()

        if headers.get("transfer-encoding"):
            raise HTTPError(400, "Transfer-Encoding is not supported")
        content_length = headers.get("content-length", "0")
        try:
            content_length = int(content_length)
        except ValueError as exc:
            raise HTTPError(400, "Invalid Content-Length") from exc
        if content_length < 0 or content_length > self.max_body:
            raise HTTPError(413, "HTTP body exceeds limit")
        try:
            body = await self._wait(reader.readexactly(content_length)) \
                if content_length else b""
        except EOFError as exc:
            raise HTTPError(400, "HTTP body ended early") from exc
        return Request(method, target, headers, body)

    async def _write_headers(self, writer, status, headers, content_length):
        reason = STATUS_TEXT.get(status, "Unknown")
        output = ["HTTP/1.1 {} {}".format(status, reason)]
        combined = {
            "Connection": "close",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Length": str(content_length),
        }
        combined.update(headers)
        for key, value in combined.items():
            if "\r" in str(key) or "\n" in str(key) or "\r" in str(value) or "\n" in str(value):
                raise HTTPError(500, "Invalid response header")
            output.append("{}: {}".format(key, value))
        writer.write(("\r\n".join(output) + "\r\n\r\n").encode("ascii"))
        await self._wait(writer.drain())

    async def write_response(self, writer, response):
        if isinstance(response, FileResponse):
            try:
                size = os.stat(response.path)[6]
                source = open(response.path, "rb")
            except OSError:
                response = Response.json({"error": "not_found"}, 404)
            else:
                try:
                    await self._write_headers(writer, 200, {
                        "Content-Type": response.content_type,
                        "Cache-Control": "public, max-age=300",
                    }, size)
                    while True:
                        chunk = source.read(FILE_CHUNK_SIZE)
                        if not chunk:
                            break
                        writer.write(chunk)
                        await self._wait(writer.drain())
                    return
                finally:
                    source.close()
        await self._write_headers(
            writer, response.status, response.headers, len(response.body)
        )
        for offset in range(0, len(response.body), FILE_CHUNK_SIZE):
            writer.write(response.body[offset:offset + FILE_CHUNK_SIZE])
            await self._wait(writer.drain())

    async def handle_connection(self, reader, writer):
        try:
            try:
                request = await self.read_request(reader)
                response = await self.handler(request)
                if not isinstance(response, (Response, FileResponse)):
                    raise HTTPError(500, "Handler returned invalid response")
            except HTTPError as exc:
                response = Response.json({"error": exc.message}, exc.status)
            except Exception as exc:
                error_name = type(exc).__name__
                if error_name == "TimeoutError":
                    response = Response.json({"error": "request_timeout"}, 408)
                else:
                    log.error("HTTP request failed: {}".format(error_name))
                    response = Response.json({"error": "internal_server_error"}, 500)
            gc.collect()
            try:
                await self.write_response(writer, response)
            except Exception as exc:
                log.error("HTTP response failed: {}".format(type(exc).__name__))
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            gc.collect()

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_connection, self.host, self.port
        )
        return self.server
