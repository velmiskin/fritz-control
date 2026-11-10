"""Allocation-light validation helpers shared by TR-064 services."""


def validate_ipv4(ip_address):
    if not isinstance(ip_address, str):
        raise ValueError("IPv4 address must be a string")
    parts = ip_address.split(".")
    if len(parts) != 4:
        raise ValueError("Invalid IPv4 address")
    for part in parts:
        if (not part or not part.isdigit() or
                (len(part) > 1 and part[0] == "0")):
            raise ValueError("Invalid IPv4 address")
        value = int(part)
        if value < 0 or value > 255:
            raise ValueError("Invalid IPv4 address")
    return ip_address
