import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Hostnames that must never be fetched even though they are not literal IPs.
_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",  # AWS/Azure metadata short name
}


class SSRFError(ValueError):
    """Raised when a URL resolves to a private/internal IP address."""


def _ip_is_blocked(ip_str: str) -> bool:
    """Return True if an IP literal falls in a private/internal/reserved range."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Not parseable as an IP — treat as non-blocking here; callers handle hostnames.
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified


def _is_private_ip(hostname: str) -> bool:
    """Check a hostname *string* (literal IP or known-bad name) without DNS resolution."""
    if _ip_is_blocked(hostname):
        return True
    return hostname.lower() in _BLOCKED_HOSTNAMES


def _resolve_and_check(hostname: str) -> None:
    """Resolve a hostname via DNS and block it if *any* resolved IP is private/internal.

    This closes the DNS-rebinding gap: a public-looking hostname (e.g. ``evil.example``)
    that resolves to ``169.254.169.254`` or an RFC1918 address would otherwise pass the
    literal-string checks. Resolution failures fail *closed* (raise SSRFError) so a
    bad/unknown host is never fetched.

    NOTE: a TOCTOU window remains between this check and the actual request (DNS can
    change). Combined with ``allow_redirects=False`` at the call site this is a strong
    mitigation; a fully airtight fix requires pinning the validated IP for the request.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SSRFError(f"Could not resolve host '{hostname}': {e}") from e

    resolved = {info[4][0] for info in infos}
    for ip in resolved:
        if _ip_is_blocked(ip):
            raise SSRFError(f"Host '{hostname}' resolves to a private/internal IP address: {ip}")


def validate_download_url(url: str, allowed_hosts: list[str]) -> None:
    """
    Validate that a URL is safe to download from.

    Blocks:
      - Private IP ranges (10/8, 172.16/12, 192.168/16, 127/8)
      - Link-local addresses (169.254/16, fe80::/10)
      - Loopback (::1/128), reserved and unspecified addresses
      - Cloud metadata endpoints (169.254.169.254)
      - Public hostnames that *resolve* to any of the above (DNS-rebinding defense)

    Allows:
      - Any public host when allowed_hosts contains "*" (after DNS resolution check)
      - Specific hosts explicitly listed in allowed_hosts (operator opt-in; trusted)
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no valid hostname")

    # Wildcard: allow any public host, but block private literals AND hosts that
    # resolve to private addresses.
    if "*" in allowed_hosts:
        if _is_private_ip(hostname):
            raise SSRFError(f"URL resolves to a private/internal IP address: {hostname}")
        _resolve_and_check(hostname)
        return

    # Explicit allowlist entry — operator has vouched for this host; trust it as-is.
    if hostname in allowed_hosts:
        return

    # Not in allowlist — reject (still surface a private-IP reason when applicable).
    if _is_private_ip(hostname):
        raise SSRFError(f"URL resolves to a private/internal IP address: {hostname}")

    raise SSRFError(f"Host '{hostname}' is not in the allowed_hosts list")
