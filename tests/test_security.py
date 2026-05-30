"""Tests for utils/security.py SSRF protection."""

from unittest.mock import patch

import pytest

from utils.security import SSRFError, validate_download_url


def _fake_getaddrinfo(ip):
    """Build a socket.getaddrinfo replacement that always resolves to `ip`."""

    def _inner(host, *args, **kwargs):
        return [(2, 1, 6, "", (ip, 0))]

    return _inner


class TestSSRFValidation:
    def test_private_ip_10_blocked(self):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_download_url("http://10.0.0.1/file.pdf", ["*"])

    def test_private_ip_172_blocked(self):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_download_url("http://172.16.0.1/file.pdf", ["*"])

    def test_private_ip_192_168_blocked(self):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_download_url("http://192.168.1.1/file.pdf", ["*"])

    def test_loopback_blocked(self):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_download_url("http://127.0.0.1/file.pdf", ["*"])

    def test_localhost_blocked(self):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_download_url("http://localhost/file.pdf", ["*"])

    def test_cloud_metadata_blocked(self):
        with pytest.raises(SSRFError, match="private/internal"):
            validate_download_url("http://169.254.169.254/latest/meta-data/", ["*"])

    def test_allowed_hosts_bypasses_private_check(self):
        # When host is in allowed_hosts, private IP check is skipped
        validate_download_url("http://example.com/file.pdf", ["example.com"])

    def test_wildcard_allows_public_but_blocks_private(self):
        # Public hostname resolves to a public IP → allowed.
        with patch("utils.security.socket.getaddrinfo", _fake_getaddrinfo("93.184.216.34")):
            validate_download_url("http://example.com/file.pdf", ["*"])
        with pytest.raises(SSRFError, match="private/internal"):
            validate_download_url("http://192.168.1.1/file.pdf", ["*"])

    def test_not_in_allowed_hosts_rejected(self):
        with pytest.raises(SSRFError, match="not in the allowed_hosts"):
            validate_download_url("http://evil.com/file.pdf", ["example.com"])

    def test_no_hostname_rejected(self):
        with pytest.raises(SSRFError, match="no valid hostname"):
            validate_download_url("http:///file.pdf", ["*"])

    # ── DNS-rebinding hardening ──────────────────────────────────────────────

    def test_public_host_resolving_to_metadata_ip_blocked(self):
        # A public-looking hostname that resolves to the cloud metadata IP.
        with patch("utils.security.socket.getaddrinfo", _fake_getaddrinfo("169.254.169.254")):
            with pytest.raises(SSRFError, match="resolves to a private/internal"):
                validate_download_url("http://evil.example/file.pdf", ["*"])

    def test_public_host_resolving_to_rfc1918_blocked(self):
        with patch("utils.security.socket.getaddrinfo", _fake_getaddrinfo("10.1.2.3")):
            with pytest.raises(SSRFError, match="resolves to a private/internal"):
                validate_download_url("http://rebind.example/file.pdf", ["*"])

    def test_unresolvable_host_fails_closed(self):
        import socket as _socket

        def _boom(*a, **k):
            raise _socket.gaierror("name or service not known")

        with patch("utils.security.socket.getaddrinfo", _boom):
            with pytest.raises(SSRFError, match="Could not resolve host"):
                validate_download_url("http://nope.invalid/file.pdf", ["*"])

    def test_explicit_allowlisted_host_skips_dns_resolution(self):
        # Operator opt-in: an explicitly allowlisted host is trusted and not resolved.
        validate_download_url("http://internal.corp/file.pdf", ["internal.corp"])
