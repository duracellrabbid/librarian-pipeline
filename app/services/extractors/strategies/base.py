"""Base protocol definition for domain-specific extraction strategies."""

from typing import Protocol, runtime_checkable

from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig


@runtime_checkable
class DomainExtractionStrategy(Protocol):
    """Protocol defining domain-specific crawling configurations and markdown cleaning rules."""

    domain_prefix: str

    def get_run_config(self) -> CrawlerRunConfig:
        """Return the Crawl4AI CrawlerRunConfig customized for this domain."""
        ...

    def get_browser_config(self) -> BrowserConfig:
        """Return the Crawl4AI BrowserConfig customized for this domain."""
        ...

    def clean(self, markdown: str) -> str:
        """Sanitize and clean raw markdown extracted from this domain."""
        ...
