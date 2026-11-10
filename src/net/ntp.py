"""Asynchronous DNS and NTP synchronization for MicroPython."""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import usocket as socket
except ImportError:
    import socket

try:
    import utime as time
except ImportError:
    import time

try:
    import uos as os
except ImportError:
    import os

from core.logger import log


NTP_PORT = 123
DNS_PORT = 53
NTP_UNIX_DELTA = 2208988800
NTP_ERA_SECONDS = 1 << 32
MIN_UNIX_TIME = 946684800  # 2000-01-01 UTC


class NTPError(Exception):
    pass


def _monotonic_ms():
    ticks_ms = getattr(time, "ticks_ms", None)
    if ticks_ms is not None:
        return ticks_ms()
    return int(time.monotonic() * 1000)


def _elapsed_ms(start):
    ticks_diff = getattr(time, "ticks_diff", None)
    now = _monotonic_ms()
    if ticks_diff is not None:
        return ticks_diff(now, start)
    return now - start


def _is_ipv4(value):
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part or not part.isdigit():
            return False
        if len(part) > 1 and part[0] == "0":
            return False
        if int(part) > 255:
            return False
    return True


def _encode_dns_name(hostname):
    if not isinstance(hostname, str):
        raise NTPError("NTP server name must be text")
    hostname = hostname.rstrip(".")
    if not hostname or len(hostname) > 253:
        raise NTPError("Invalid NTP server name")
    encoded = bytearray()
    for label in hostname.split("."):
        try:
            label_bytes = label.encode("ascii")
        except UnicodeError as exc:
            raise NTPError("NTP server name must be ASCII") from exc
        if not label_bytes or len(label_bytes) > 63:
            raise NTPError("Invalid NTP server name")
        encoded.append(len(label_bytes))
        encoded.extend(label_bytes)
    encoded.append(0)
    return bytes(encoded)


def _skip_dns_name(packet, offset):
    steps = 0
    while True:
        if offset >= len(packet):
            raise NTPError("Truncated DNS name")
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                raise NTPError("Truncated DNS pointer")
            return offset + 2
        if length & 0xC0:
            raise NTPError("Invalid DNS label")
        offset += 1
        if length == 0:
            return offset
        offset += length
        steps += 1
        if offset > len(packet) or steps > 127:
            raise NTPError("Invalid DNS name")


def parse_dns_a_response(packet, query_id):
    if len(packet) < 12:
        raise NTPError("Truncated DNS response")
    response_id = (packet[0] << 8) | packet[1]
    flags = (packet[2] << 8) | packet[3]
    if response_id != query_id or not flags & 0x8000:
        raise NTPError("DNS response does not match query")
    if flags & 0x000F:
        raise NTPError("DNS server returned an error")
    question_count = (packet[4] << 8) | packet[5]
    answer_count = (packet[6] << 8) | packet[7]
    if question_count != 1:
        raise NTPError("Unexpected DNS question count")

    offset = _skip_dns_name(packet, 12)
    if offset + 4 > len(packet):
        raise NTPError("Truncated DNS question")
    offset += 4
    for _ in range(answer_count):
        offset = _skip_dns_name(packet, offset)
        if offset + 10 > len(packet):
            raise NTPError("Truncated DNS answer")
        record_type = (packet[offset] << 8) | packet[offset + 1]
        record_class = (packet[offset + 2] << 8) | packet[offset + 3]
        data_length = (packet[offset + 8] << 8) | packet[offset + 9]
        offset += 10
        if offset + data_length > len(packet):
            raise NTPError("Truncated DNS record data")
        if record_type == 1 and record_class == 1 and data_length == 4:
            return "{}.{}.{}.{}".format(
                packet[offset], packet[offset + 1],
                packet[offset + 2], packet[offset + 3]
            )
        offset += data_length
    raise NTPError("DNS response contains no IPv4 address")


def _is_leap_year(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def unix_to_rtc_datetime(unix_seconds):
    if type(unix_seconds) is not int or unix_seconds < 0:
        raise NTPError("Invalid Unix timestamp")
    days, seconds = divmod(unix_seconds, 86400)
    weekday = (days + 3) % 7  # 1970-01-01 was Thursday, Monday is zero.
    year = 1970
    while True:
        year_days = 366 if _is_leap_year(year) else 365
        if days < year_days:
            break
        days -= year_days
        year += 1
        if year > 2200:
            raise NTPError("NTP timestamp is outside supported range")
    month_days = [31, 29 if _is_leap_year(year) else 28, 31, 30, 31, 30,
                  31, 31, 30, 31, 30, 31]
    month = 1
    for count in month_days:
        if days < count:
            break
        days -= count
        month += 1
    hour, seconds = divmod(seconds, 3600)
    minute, second = divmod(seconds, 60)
    return (year, month, days + 1, weekday, hour, minute, second, 0)


class NTPClient:
    def __init__(self, server="pool.ntp.org", dns_server=None, timeout=3,
                 retries=3, poll_interval=0.05, socket_module=None,
                 random_bytes=None):
        if not server:
            raise ValueError("NTP server must not be empty")
        if timeout <= 0 or retries <= 0 or poll_interval <= 0:
            raise ValueError("NTP timing values must be positive")
        if not _is_ipv4(server):
            _encode_dns_name(server)
        if dns_server is not None and not _is_ipv4(dns_server):
            raise ValueError("DNS server must be an IPv4 address")
        self.server = server
        self.dns_server = dns_server
        self.timeout = timeout
        self.retries = retries
        self.poll_interval = poll_interval
        self.socket = socket_module or socket
        self.random_bytes = random_bytes or os.urandom

    async def _exchange(self, payload, address, max_size):
        last_error = None
        for _ in range(self.retries):
            sock = self.socket.socket(self.socket.AF_INET, self.socket.SOCK_DGRAM)
            try:
                sock.setblocking(False)
                start = _monotonic_ms()
                while True:
                    try:
                        sock.sendto(payload, address)
                        break
                    except OSError as exc:
                        last_error = exc
                        if _elapsed_ms(start) >= int(self.timeout * 1000):
                            break
                        await asyncio.sleep(self.poll_interval)
                while _elapsed_ms(start) < int(self.timeout * 1000):
                    try:
                        data, source = sock.recvfrom(max_size)
                        if source[0] == address[0] and source[1] == address[1]:
                            return data
                    except OSError as exc:
                        last_error = exc
                    await asyncio.sleep(self.poll_interval)
            finally:
                sock.close()
        error_name = type(last_error).__name__ if last_error else "timeout"
        raise NTPError("UDP request timed out ({})".format(error_name))

    async def resolve(self):
        if _is_ipv4(self.server):
            return self.server
        if not self.dns_server:
            raise NTPError("DNS server is required for an NTP hostname")
        query_id_bytes = self.random_bytes(2)
        query_id = (query_id_bytes[0] << 8) | query_id_bytes[1]
        query = bytearray(12)
        query[0:2] = query_id_bytes
        query[2] = 1  # Recursion desired.
        query[5] = 1  # One question.
        query.extend(_encode_dns_name(self.server))
        query.extend(b"\x00\x01\x00\x01")  # A, IN
        response = await self._exchange(
            bytes(query), (self.dns_server, DNS_PORT), 512
        )
        return parse_dns_a_response(response, query_id)

    async def query(self):
        server_ip = await self.resolve()
        token = self.random_bytes(8)
        if len(token) != 8:
            raise NTPError("Random source returned an invalid token")
        request = bytearray(48)
        request[0] = 0x23  # LI=0, version=4, client mode=3.
        request[40:48] = token
        response = await self._exchange(
            bytes(request), (server_ip, NTP_PORT), 512
        )
        if len(response) < 48:
            raise NTPError("Truncated NTP response")
        leap = response[0] >> 6
        mode = response[0] & 0x07
        stratum = response[1]
        if leap == 3 or mode not in (4, 5) or not 1 <= stratum <= 15:
            raise NTPError("Invalid NTP server status")
        if response[24:32] != token:
            raise NTPError("NTP response does not match request")
        seconds_1900 = int.from_bytes(response[40:44], "big")
        if seconds_1900 < NTP_UNIX_DELTA:
            seconds_1900 += NTP_ERA_SECONDS
        unix_seconds = seconds_1900 - NTP_UNIX_DELTA
        if unix_seconds < MIN_UNIX_TIME:
            raise NTPError("NTP response time is implausible")
        return {
            "unix_time": unix_seconds,
            "stratum": stratum,
            "server_ip": server_ip,
        }

    async def synchronize(self, rtc=None):
        result = await self.query()
        if rtc is None:
            try:
                import machine
            except ImportError as exc:
                raise NTPError("RTC is unavailable") from exc
            rtc = machine.RTC()
        rtc.datetime(unix_to_rtc_datetime(result["unix_time"]))
        log.info("NTP synchronization completed")
        return result
