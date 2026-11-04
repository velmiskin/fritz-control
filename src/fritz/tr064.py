"""
src/fritz/tr064.py - Async TR-064 SOAP Client with HTTP Digest Auth
Compatible with both MicroPython (uasyncio / uhashlib) and CPython (asyncio / hashlib).
"""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import uhashlib as hashlib
    import ubinascii
    def md5_hex(s):
        h = hashlib.md5(s.encode("utf-8") if isinstance(s, str) else s)
        return ubinascii.hexlify(h.digest()).decode("utf-8")
except ImportError:
    import hashlib
    def md5_hex(s):
        return hashlib.md5(s.encode("utf-8") if isinstance(s, str) else s).hexdigest()

try:
    import gc
except ImportError:
    gc = None

from core.logger import log
from fritz.soap import build_soap_envelope, parse_soap_fault

class TR064Error(Exception):
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code

class TR064Client:
    def __init__(self, host="192.168.178.1", port=49000, username="", password="", timeout=10):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        
        # Digest auth state cache
        self.realm = None
        self.nonce = None
        self.qop = None
        self.nc = 0

    def _parse_www_authenticate(self, header_val):
        """Extracts realm, nonce, and qop from WWW-Authenticate header."""
        parts = {}
        # Remove 'Digest ' prefix
        clean = header_val.strip()
        if clean.lower().startswith("digest "):
            clean = clean[7:]
            
        items = clean.split(",")
        for item in items:
            kv = item.strip().split("=", 1)
            if len(kv) == 2:
                k = kv[0].strip().lower()
                v = kv[1].strip().strip('"')
                parts[k] = v
                
        self.realm = parts.get("realm")
        self.nonce = parts.get("nonce")
        self.qop = parts.get("qop")
        self.nc = 0

    def _build_auth_header(self, method, uri):
        """Builds HTTP Digest Authorization header."""
        if not self.realm or not self.nonce:
            return None

        self.nc += 1
        nc_str = f"{self.nc:08x}"
        cnonce = "0a4f113b"

        ha1 = md5_hex(f"{self.username}:{self.realm}:{self.password}")
        ha2 = md5_hex(f"{method}:{uri}")

        if self.qop and "auth" in self.qop:
            resp = md5_hex(f"{ha1}:{self.nonce}:{nc_str}:{cnonce}:auth:{ha2}")
            return (
                f'Digest username="{self.username}", realm="{self.realm}", '
                f'nonce="{self.nonce}", uri="{uri}", response="{resp}", '
                f'qop=auth, nc={nc_str}, cnonce="{cnonce}"'
            )
        else:
            resp = md5_hex(f"{ha1}:{self.nonce}:{ha2}")
            return (
                f'Digest username="{self.username}", realm="{self.realm}", '
                f'nonce="{self.nonce}", uri="{uri}", response="{resp}"'
            )

    async def _send_raw_http(self, uri, action, envelope_xml, auth_header=None):
        """Sends raw HTTP POST over asyncio stream and returns (status_code, headers_dict, body)."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.timeout
        )

        try:
            req_lines = [
                f"POST {uri} HTTP/1.1",
                f"Host: {self.host}:{self.port}",
                'Content-Type: text/xml; charset="utf-8"',
                f'SOAPAction: "{action}"',
                f"Content-Length: {len(envelope_xml)}",
                "Connection: close",
            ]
            if auth_header:
                req_lines.append(f"Authorization: {auth_header}")

            req_payload = "\r\n".join(req_lines) + "\r\n\r\n" + envelope_xml
            writer.write(req_payload.encode("utf-8"))
            await writer.drain()

            # Read status line
            status_line = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
            if not status_line:
                raise TR064Error("Empty HTTP response from router")

            status_str = status_line.decode("utf-8").strip()
            parts = status_str.split(" ", 2)
            status_code = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

            # Read headers
            headers = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=self.timeout)
                if not line or line == b"\r\n" or line == b"\n":
                    break
                header_line = line.decode("utf-8").strip()
                if ":" in header_line:
                    hk, hv = header_line.split(":", 1)
                    headers[hk.strip().lower()] = hv.strip()

            # Read body
            body_chunks = []
            while True:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=self.timeout)
                if not chunk:
                    break
                body_chunks.append(chunk.decode("utf-8", "ignore"))

            body = "".join(body_chunks)
            return status_code, headers, body

        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            if gc:
                gc.collect()

    async def call_action(self, control_url, service_type, action_name, params=None):
        """
        Executes a SOAP TR-064 action, transparently handling Digest Auth challenges.
        """
        envelope = build_soap_envelope(service_type, action_name, params)
        soap_action = f"{service_type}#{action_name}"

        # Attempt 1: with cached auth header (if any)
        auth_header = self._build_auth_header("POST", control_url) if self.nonce else None
        status_code, headers, body = await self._send_raw_http(
            control_url, soap_action, envelope, auth_header
        )

        # Attempt 2: Handle 401 Unauthorized challenge
        if status_code == 401:
            www_auth = headers.get("www-authenticate")
            if not www_auth:
                raise TR064Error("HTTP 401 Unauthorized but WWW-Authenticate header missing")

            self._parse_www_authenticate(www_auth)
            auth_header = self._build_auth_header("POST", control_url)
            log.debug(f"Handling 401 challenge for {action_name}, retrying with Digest...")

            status_code, headers, body = await self._send_raw_http(
                control_url, soap_action, envelope, auth_header
            )

        # Check for SOAP fault
        fault = parse_soap_fault(body)
        if fault:
            err_code = fault.get("error_code")
            err_desc = fault.get("error_description")
            log.error(f"SOAP Fault on {action_name}: [{err_code}] {err_desc}")
            raise TR064Error(f"SOAP Fault: {err_desc} (Code {err_code})", error_code=err_code)

        if status_code >= 400:
            raise TR064Error(f"HTTP Error {status_code} on {action_name}: {body[:200]}")

        return body
