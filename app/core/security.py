"""Security utilities and domain validation for ingestion requests."""

from urllib.parse import SplitResult, urlsplit

from app.core.config import get_settings


def _matches_domain(parsed_url: SplitResult, allowed_domain: str) -> bool:
    """Check if parsed target URL matches an allowed domain prefix."""
    try:
        parsed_allowed = urlsplit(allowed_domain.strip())
    except ValueError:
        return False

    if not parsed_allowed.scheme or not parsed_allowed.hostname:
        return False

    if parsed_url.scheme.lower() != parsed_allowed.scheme.lower():
        return False

    url_hostname = parsed_url.hostname.lower() if parsed_url.hostname else ""
    allowed_hostname = parsed_allowed.hostname.lower()
    if url_hostname != allowed_hostname:
        return False

    if parsed_url.port != parsed_allowed.port:
        return False

    allowed_path = parsed_allowed.path.rstrip("/")
    if not allowed_path:
        return not parsed_url.path or parsed_url.path.startswith("/")

    return parsed_url.path == allowed_path or parsed_url.path.startswith(f"{allowed_path}/")


def is_allowed_url(url: str, allowed_domains: list[str] | None = None) -> bool:
    """Verify whether a target URL is strictly allowed for crawling and ingestion.

    Validates exact scheme, hostname, port, and path prefix against configured
    allowlist entries, rejecting subdomains, spoofed hosts, and SSRF targets.
    """
    if not isinstance(url, str) or not url.strip():
        return False

    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return False

    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        return False

    domains = get_settings().allowed_domains if allowed_domains is None else allowed_domains
    if not domains:
        return False

    return any(_matches_domain(parsed, allowed) for allowed in domains)
