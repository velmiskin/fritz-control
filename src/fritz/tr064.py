"""Bounded async TR-064 SOAP transport with HTTP Digest authentication."""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import uhashlib as hashlib
    import ubinascii as binascii
except ImportError:
    import hashlib
    import binascii

try:
    import uos as os
except ImportError:
    import os

import gc

from core.logger import log
from fritz.soap import build_soap_envelope, parse_soap_fault


DEFAULT_MAX_RESPONSE_SIZE = 16 * 1024
DEFAULT_MAX_DOCUMENT_SIZE = 32 * 1024
MAX_HEADER_BYTES = 8 * 1024
MAX_HEADER_LINE = 1024


def md5_hex(value):
    data = value.encode("utf-8") if isinstance(value, str) else value
    digest = hashlib.md5(data).digest()
    return binascii.hexlify(digest).decode("ascii")


def _quote_digest_value(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _parse_digest_fields(value):
    fields = {}
    pos = 0
    length = len(value)
    while pos < length:
        while pos < length and value[pos] in " ,\t":
            pos += 1
        key_start = pos
        while pos < length and value[pos] not in "=,":
            pos += 1
        if pos >= length or value[pos] != "=":
            break
        key = value[key_start:pos].strip().lower()
        pos += 1
        while pos < length and value[pos] in " \t":
            pos += 1
        if pos < length and value[pos] == '"':
            pos += 1
            chars = []
            while pos < length:
                char = value[pos]
                pos += 1
                if char == '"':
                    break
                if char == "\\" and pos < length:
                    char = value[pos]
                    pos += 1
                chars.append(char)
            field_value = "".join(chars)
        else:
            value_start = pos
            while pos < length and value[pos] != ",":
                pos += 1
            field_value = value[value_start:pos].strip()
        if key:
            fields[key] = field_value
        while pos < length and value[pos] != ",":
            pos += 1
        if pos < length:
            pos += 1
    return fields


class TR064Error(Exception):
    def __init__(self, message, error_code=None, status_code=None):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class TR064Client:
    def __init__(self, host="192.168.178.1", port=49000, username="",
                 password="", timeout=10, max_response_size=DEFAULT_MAX_RESPONSE_SIZE,
                 use_ssl=False):
        if use_ssl:
            raise ValueError(
                "HTTPS requires certificate validation and hardware memory verification; "
                "use_ssl=True is not supported yet"
            )
        if not isinstance(max_response_size, int) or max_response_size <= 0:
            raise ValueError("max_response_size must be a positive integer")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.max_response_size = max_response_size
        self.realm = None
        self.nonce = None
        self.qop = None
        self.opaque = None
        self.algorithm = "MD5"
        self.charset = None
        self.userhash = False
        self.nc = 0
        self._cnonce_fallback = 0

    def _parse_www_authenticate(self, header_value):
        clean = header_value.strip()
        if not clean.lower().startswith("digest "):
            raise TR064Error("Router did not offer HTTP Digest authentication")
        fields = _parse_digest_fields(clean[7:])
        realm = fields.get("realm")
        nonce = fields.get("nonce")
        if not realm or not nonce:
            raise TR064Error("Incomplete HTTP Digest challenge")
        algorithm = fields.get("algorithm", "MD5").upper()
        if algorithm != "MD5":
            raise TR064Error("Unsupported HTTP Digest algorithm: {}".format(algorithm))
        qop = fields.get("qop")
        if qop:
            qop_values = [item.strip().lower() for item in qop.split(",")]
            if "auth" not in qop_values:
                raise TR064Error("Router does not offer supported Digest qop=auth")
            qop = "auth"
        self.realm = realm
        self.nonce = nonce
        self.qop = qop
        self.opaque = fields.get("opaque")
        self.algorithm = algorithm
        self.charset = fields.get("charset")
        self.userhash = fields.get("userhash", "false").lower() == "true"
        self.nc = 0
        return fields

    def _new_cnonce(self):
        try:
            return binascii.hexlify(os.urandom(8)).decode("ascii")
        except Exception:
            self._cnonce_fallback += 1
            return md5_hex("{}:{}".format(self.nonce, self._cnonce_fallback))[:16]

    def _build_auth_header(self, method, uri):
        if not self.realm or not self.nonce:
            return None
        self.nc += 1
        nc_value = "{:08x}".format(self.nc)
        cnonce = self._new_cnonce()
        ha1 = md5_hex("{}:{}:{}".format(self.username, self.realm, self.password))
        ha2 = md5_hex("{}:{}".format(method, uri))
        if self.qop:
            response = md5_hex("{}:{}:{}:{}:auth:{}".format(
                ha1, self.nonce, nc_value, cnonce, ha2
            ))
        else:
            response = md5_hex("{}:{}:{}".format(ha1, self.nonce, ha2))
        parts = [
            'Digest username="{}"'.format(_quote_digest_value(self.username)),
            'realm="{}"'.format(_quote_digest_value(self.realm)),
            'nonce="{}"'.format(_quote_digest_value(self.nonce)),
            'uri="{}"'.format(_quote_digest_value(uri)),
            'response="{}"'.format(response),
            "algorithm=MD5",
        ]
        if self.opaque is not None:
            parts.append('opaque="{}"'.format(_quote_digest_value(self.opaque)))
        if self.qop:
            parts.extend(("qop=auth", "nc={}".format(nc_value),
                          'cnonce="{}"'.format(cnonce)))
        return ", ".join(parts)

    async def _wait(self, awaitable):
        return await asyncio.wait_for(awaitable, self.timeout)

    async def _readline(self, reader, total_header_bytes=None):
        line = await self._wait(reader.readline())
        if len(line) > MAX_HEADER_LINE:
            raise TR064Error("HTTP header line exceeds limit")
        if total_header_bytes is not None and total_header_bytes + len(line) > MAX_HEADER_BYTES:
            raise TR064Error("HTTP headers exceed limit")
        return line

    async def _read_body(self, reader, status_code, headers, max_body_size):
        if status_code in (204, 304):
            return b""
        transfer_encoding = headers.get("transfer-encoding", "").lower()
        content_length = headers.get("content-length")
        if transfer_encoding:
            if transfer_encoding != "chunked":
                raise TR064Error("Unsupported Transfer-Encoding")
            body = bytearray()
            while True:
                size_line = await self._readline(reader)
                if not size_line:
                    raise TR064Error("Unexpected EOF in chunked response")
                try:
                    chunk_size = int(size_line.split(b";", 1)[0].strip(), 16)
                except (ValueError, TypeError):
                    raise TR064Error("Invalid HTTP chunk size")
                if chunk_size == 0:
                    while True:
                        trailer = await self._readline(reader)
                        if trailer in (b"\r\n", b"\n", b""):
                            return bytes(body)
                if len(body) + chunk_size > max_body_size:
                    raise TR064Error("HTTP response body exceeds limit")
                try:
                    chunk = await self._wait(reader.readexactly(chunk_size))
                    terminator = await self._wait(reader.readexactly(2))
                except EOFError:
                    raise TR064Error("Unexpected EOF in chunked response")
                if terminator != b"\r\n":
                    raise TR064Error("Invalid HTTP chunk terminator")
                body.extend(chunk)
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                raise TR064Error("Invalid Content-Length header")
            if length < 0 or length > max_body_size:
                raise TR064Error("HTTP response body exceeds limit")
            try:
                return await self._wait(reader.readexactly(length))
            except EOFError:
                raise TR064Error("HTTP response body ended early")
        body = bytearray()
        while True:
            read_size = min(1024, max_body_size - len(body) + 1)
            chunk = await self._wait(reader.read(read_size))
            if not chunk:
                return bytes(body)
            body.extend(chunk)
            if len(body) > max_body_size:
                raise TR064Error("HTTP response body exceeds limit")

    async def _request(self, method, uri, headers=None, body=b"", max_body_size=None):
        max_body_size = max_body_size or self.max_response_size
        writer = None
        try:
            if "\r" in method or "\n" in method or "\r" in uri or "\n" in uri:
                raise TR064Error("Invalid HTTP request target")
            reader, writer = await self._wait(asyncio.open_connection(self.host, self.port))
            request_headers = {
                "Host": "{}:{}".format(self.host, self.port),
                "Connection": "close",
            }
            if body:
                request_headers["Content-Length"] = str(len(body))
            if headers:
                request_headers.update(headers)
            for key, value in request_headers.items():
                if ("\r" in str(key) or "\n" in str(key) or
                        "\r" in str(value) or "\n" in str(value)):
                    raise TR064Error("Invalid HTTP header value")
            lines = ["{} {} HTTP/1.1".format(method, uri)]
            for key, value in request_headers.items():
                lines.append("{}: {}".format(key, value))
            writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))
            if body:
                writer.write(body)
            await self._wait(writer.drain())
            status_line = await self._readline(reader)
            if not status_line:
                raise TR064Error("Empty HTTP response from router")
            try:
                status_text = status_line.decode("ascii").strip()
            except UnicodeError:
                raise TR064Error("Invalid HTTP status line encoding")
            parts = status_text.split(" ", 2)
            if (len(parts) < 2 or parts[0] not in ("HTTP/1.0", "HTTP/1.1") or
                    len(parts[1]) != 3 or not parts[1].isdigit()):
                raise TR064Error("Malformed HTTP status line")
            status_code = int(parts[1])
            response_headers = {}
            header_bytes = 0
            while True:
                line = await self._readline(reader, header_bytes)
                header_bytes += len(line)
                if line in (b"\r\n", b"\n"):
                    break
                if not line:
                    raise TR064Error("HTTP headers ended unexpectedly")
                try:
                    header_line = line.decode("iso-8859-1").strip()
                except UnicodeError:
                    raise TR064Error("Invalid HTTP header encoding")
                if ":" not in header_line:
                    raise TR064Error("Malformed HTTP header")
                key, value = header_line.split(":", 1)
                response_headers[key.strip().lower()] = value.strip()
            response_body = await self._read_body(
                reader, status_code, response_headers, max_body_size
            )
            return status_code, response_headers, response_body
        except TR064Error:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise TR064Error("TR-064 transport failed: {}".format(type(exc).__name__))
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
            gc.collect()

    @staticmethod
    def _decode_body(body):
        try:
            return body.decode("utf-8")
        except UnicodeError:
            raise TR064Error("TR-064 response is not valid UTF-8")

    async def _request_with_digest(self, method, uri, headers=None, body=b"",
                                   max_body_size=None):
        request_headers = dict(headers or {})
        if self.nonce:
            request_headers["Authorization"] = self._build_auth_header(method, uri)
        status, response_headers, response_body = await self._bounded_request(
            method, uri, request_headers, body, max_body_size
        )
        if status == 401:
            challenge = response_headers.get("www-authenticate")
            if not challenge:
                raise TR064Error("HTTP 401 without WWW-Authenticate", status_code=401)
            self._parse_www_authenticate(challenge)
            request_headers["Authorization"] = self._build_auth_header(method, uri)
            status, response_headers, response_body = await self._bounded_request(
                method, uri, request_headers, body, max_body_size
            )
            if status == 401:
                raise TR064Error("HTTP Digest authentication failed", status_code=401)
        return status, response_headers, response_body

    async def _bounded_request(self, method, uri, headers, body, max_body_size):
        try:
            return await self._wait(
                self._request(method, uri, headers, body, max_body_size)
            )
        except TR064Error:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise TR064Error("TR-064 request timed out: {}".format(type(exc).__name__))

    async def call_action(self, control_url, service_type, action_name, params=None):
        envelope = build_soap_envelope(service_type, action_name, params)
        body = envelope.encode("utf-8")
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": '"{}#{}"'.format(service_type, action_name),
        }
        status, _, response_body = await self._request_with_digest(
            "POST", control_url, headers, body
        )
        response_text = self._decode_body(response_body)
        fault = parse_soap_fault(response_text)
        if fault:
            error_code = fault.get("error_code")
            error_description = fault.get("error_description")
            log.error("SOAP Fault on {}: [{}] {}".format(
                action_name, error_code, error_description
            ))
            raise TR064Error(
                "SOAP Fault: {} (Code {})".format(error_description, error_code),
                error_code=error_code,
                status_code=status,
            )
        if status < 200 or status >= 300:
            raise TR064Error("HTTP status {} on {}".format(status, action_name),
                             status_code=status)
        return response_text

    async def get_document(self, uri, max_body_size=DEFAULT_MAX_DOCUMENT_SIZE):
        status, _, response_body = await self._request_with_digest(
            "GET", uri, max_body_size=max_body_size
        )
        if status < 200 or status >= 300:
            raise TR064Error("HTTP status {} fetching document".format(status),
                             status_code=status)
        return self._decode_body(response_body)
