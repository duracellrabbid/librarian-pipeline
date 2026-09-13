"""Unit tests for URL domain validation and SSRF security checks."""

import pytest
from app.core.security import is_allowed_url


class TestDomainValidation:
    """Unit tests verifying is_allowed_url behavior."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://en.wikipedia.org/wiki/Python_(programming_language)",
            "https://en.wikipedia.org/",
            "https://en.wikipedia.org",
            "https://en.wikipedia.org/wiki/Artificial_intelligence?query=1#section",
            "HTTPS://EN.WIKIPEDIA.ORG/wiki/Case_Insensitive_Host",
        ],
    )
    def test_allowed_wikipedia_urls_succeed(self, url: str) -> None:
        """Verify default allowed Wikipedia URLs are accepted."""
        assert is_allowed_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://fr.wikipedia.org/wiki/Python",
            "https://de.wikipedia.org/wiki/Hauptseite",
            "https://sub.en.wikipedia.org/wiki/Python",
            "https://m.en.wikipedia.org/wiki/Python",
        ],
    )
    def test_unallowed_subdomains_rejected(self, url: str) -> None:
        """Verify subdomains not in allowlist are rejected."""
        assert is_allowed_url(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://en.wikipedia.org.attacker.com",
            "https://en.wikipedia.org.evil.com/wiki/Python",
            "https://en.wikipedia.org@attacker.com/wiki/Python",
            "https://en.wikipedia.org:password@attacker.com/",
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:8000/admin",
            "http://localhost:5432",
            "http://10.0.0.1",
            "http://192.168.1.1",
            "http://[::1]:8080",
        ],
    )
    def test_ssrf_and_domain_spoofing_rejected(self, url: str) -> None:
        """Verify SSRF targets and spoofed domain prefixes are rejected."""
        assert is_allowed_url(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            "http://en.wikipedia.org/wiki/Python",  # HTTP instead of HTTPS
            "https://en.wikipedia.org:8443/wiki/Python",  # Non-standard port
        ],
    )
    def test_scheme_and_port_mismatch_rejected(self, url: str) -> None:
        """Verify scheme and port must match allowed domain."""
        assert is_allowed_url(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "   ",
            "not-a-valid-url",
            "://invalid",
            "file:///etc/passwd",
            "ftp://en.wikipedia.org/wiki/Python",
            "javascript:alert(1)",
        ],
    )
    def test_malformed_and_non_http_urls_rejected(self, url: str) -> None:
        """Verify malformed and non-HTTP/HTTPS URLs are rejected."""
        assert is_allowed_url(url) is False

    def test_custom_allowed_domains_override(self) -> None:
        """Verify custom allowed domains list overrides default."""
        allowed = ["https://docs.python.org", "https://api.github.com"]
        assert is_allowed_url("https://docs.python.org/3/library/", allowed_domains=allowed) is True
        assert is_allowed_url("https://api.github.com/repos", allowed_domains=allowed) is True
        assert is_allowed_url("https://en.wikipedia.org/wiki/Python", allowed_domains=allowed) is False

    def test_empty_allowed_domains_rejects_all(self) -> None:
        """Verify empty allowed domains list rejects any URL."""
        assert is_allowed_url("https://en.wikipedia.org/wiki/Python", allowed_domains=[]) is False

    def test_allowed_domain_with_path_prefix(self) -> None:
        """Verify allowed domain with specific path prefix behaves correctly."""
        allowed = ["https://example.com/allowed/path"]
        assert is_allowed_url("https://example.com/allowed/path", allowed_domains=allowed) is True
        assert is_allowed_url("https://example.com/allowed/path/child", allowed_domains=allowed) is True
        assert is_allowed_url("https://example.com/allowed/pathway", allowed_domains=allowed) is False
        assert is_allowed_url("https://example.com/other", allowed_domains=allowed) is False

    def test_default_uses_settings(self) -> None:
        """Verify None for allowed_domains falls back to settings."""
        assert is_allowed_url("https://en.wikipedia.org/wiki/Test", allowed_domains=None) is True

    def test_non_string_input_rejected(self) -> None:
        """Verify non-string input returns False."""
        assert is_allowed_url(None) is False  # type: ignore[arg-type]
        assert is_allowed_url(12345) is False  # type: ignore[arg-type]

    def test_value_error_in_url_or_allowed_domains(self) -> None:
        """Verify ValueError during urlsplit returns False."""
        # Malformed IPv6 literal triggers ValueError in urlsplit
        assert is_allowed_url("http://[invalid-ipv6/") is False
        assert is_allowed_url("https://en.wikipedia.org/wiki/Test", allowed_domains=["http://[invalid-ipv6/"]) is False

    def test_malformed_allowed_domains_ignored(self) -> None:
        """Verify allowed domain entries lacking scheme or hostname are ignored."""
        assert (
            is_allowed_url(
                "https://en.wikipedia.org/wiki/Test",
                allowed_domains=["not-a-url", "http://", "///only-path", "https://en.wikipedia.org"],
            )
            is True
        )
