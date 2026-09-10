"""Input validation utilities for network tools."""
import ipaddress
import re


def validate_ip(ip: str) -> str:
    """Validate and return a sanitized IP address string.

    Raises ValueError if the input is not a valid IPv4 or IPv6 address.
    """
    addr = ipaddress.ip_address(ip.strip())
    return str(addr)


def validate_port(port: int) -> int:
    """Validate a port number is in valid range.

    Raises ValueError if port is outside 1-65535.
    """
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError(f"Invalid port number: {port}. Must be between 1 and 65535.")
    return port


def validate_hours_back(hours_back: int) -> int:
    """Validate hours_back is a reasonable positive integer."""
    if not isinstance(hours_back, int) or hours_back < 1 or hours_back > 720:
        raise ValueError(f"Invalid hours_back: {hours_back}. Must be between 1 and 720.")
    return hours_back


def validate_limit(limit: int) -> int:
    """Validate limit is a reasonable positive integer."""
    if not isinstance(limit, int) or limit < 1 or limit > 10000:
        raise ValueError(f"Invalid limit: {limit}. Must be between 1 and 10000.")
    return limit


def sanitize_sg_id(sg_id: str) -> str:
    """Validate a security group ID format."""
    if not re.match(r'^sg-[a-f0-9]+$', sg_id.strip()):
        raise ValueError(f"Invalid security group ID format: {sg_id}")
    return sg_id.strip()


def sanitize_subnet_id(subnet_id: str) -> str:
    """Validate a subnet ID format."""
    if not re.match(r'^subnet-[a-f0-9]+$', subnet_id.strip()):
        raise ValueError(f"Invalid subnet ID format: {subnet_id}")
    return subnet_id.strip()
