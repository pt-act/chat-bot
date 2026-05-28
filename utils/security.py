import ipaddress
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFError(ValueError):
    """Raised when a URL resolves to a private/internal IP address."""


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private, link-local, or loopback IP."""
    try:
        # Try to parse as an IP address directly
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
    except ValueError:
        pass

    # Common blocked hostnames (cloud metadata, internal services)
    blocked_hosts = {
        "localhost",
        "metadata.google.internal",
        "metadata",  # AWS/Azure metadata short name
    }
    if hostname.lower() in blocked_hosts:
        return True

    return False


def validate_download_url(url: str, allowed_hosts: list[str]) -> None:
    """
    Validate that a URL is safe to download from.

    Blocks:
      - Private IP ranges (10/8, 172.16/12, 192.168/16, 127/8)
      - Link-local addresses (169.254/16, fe80::/10)
      - Loopback (::1/128)
      - Cloud metadata endpoints (169.254.169.254)

    Allows:
      - Any public host when allowed_hosts contains "*"
      - Specific hosts listed in allowed_hosts
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no valid hostname")

    # Allowlist check
    if "*" in allowed_hosts:
        # Still block private IPs even with wildcard allow
        if _is_private_ip(hostname):
            raise SSRFError(f"URL resolves to a private/internal IP address: {hostname}")
        return

    if hostname in allowed_hosts:
        return

    # Not in allowlist — check if it's private anyway
    if _is_private_ip(hostname):
        raise SSRFError(f"URL resolves to a private/internal IP address: {hostname}")

    raise SSRFError(f"Host '{hostname}' is not in the allowed_hosts list")
