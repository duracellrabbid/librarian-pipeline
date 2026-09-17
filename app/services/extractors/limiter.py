"""In-process per-domain concurrency limiter using asyncio.Semaphore."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

__all__ = ["InProcessDomainRateLimiter"]


class InProcessDomainRateLimiter:
    """Limits concurrent asynchronous operations per host domain using in-process semaphores."""

    def __init__(self, max_concurrency: int = 2) -> None:
        """Initialize the rate limiter with maximum concurrent operations per domain.

        Args:
            max_concurrency: Maximum number of concurrent tasks allowed per domain. Must be >= 1.

        Raises:
            ValueError: If max_concurrency is less than 1.
        """
        if max_concurrency < 1:
            raise ValueError(f"max_concurrency must be at least 1, got {max_concurrency}")
        self.max_concurrency = max_concurrency
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def extract_domain(self, url: str) -> str:
        """Extract normalized domain/host netloc from a URL string.

        Args:
            url: Target URL or raw host string.

        Returns:
            Normalized lowercase netloc or stripped host string.
        """
        if not url:
            return ""
        parsed = urlparse(url)
        if parsed.netloc:
            return parsed.netloc.lower()
        return url.split("/")[0].strip().lower()

    def _get_semaphore(self, domain: str) -> asyncio.Semaphore:
        """Retrieve or create an asyncio.Semaphore for the specified domain."""
        if domain not in self._semaphores:
            self._semaphores[domain] = asyncio.Semaphore(self.max_concurrency)
        return self._semaphores[domain]

    @asynccontextmanager
    async def acquire(self, url_or_domain: str) -> AsyncIterator[None]:
        """Async context manager acquiring a concurrency slot for the target URL's domain.

        Args:
            url_or_domain: Target URL or domain string.

        Yields:
            None when the semaphore slot is successfully acquired.
        """
        domain = self.extract_domain(url_or_domain)
        semaphore = self._get_semaphore(domain)
        async with semaphore:
            yield
