"""Tests for utils/security.py SSRF protection."""

import pytest

from utils.security import SSRFError, validate_download_url


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
        validate_download_url("http://example.com/file.pdf", ["*"])
        with pytest.raises(SSRFError, match="private/internal"):
            validate_download_url("http://192.168.1.1/file.pdf", ["*"])

    def test_not_in_allowed_hosts_rejected(self):
        with pytest.raises(SSRFError, match="not in the allowed_hosts"):
            validate_download_url("http://evil.com/file.pdf", ["example.com"])

    def test_no_hostname_rejected(self):
        with pytest.raises(SSRFError, match="no valid hostname"):
            validate_download_url("http:///file.pdf", ["*"])
