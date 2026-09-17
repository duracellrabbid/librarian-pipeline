"""Web content extractor implementation using Crawl4AI."""

import asyncio
import email.utils
import random
import re
from datetime import UTC, datetime
from typing import Any

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from loguru import logger

from app.core.config import get_settings
from app.core.exceptions import ExtractionError
from app.services.extractors.base import BaseExtractor, ExtractedDocument
from app.services.extractors.limiter import InProcessDomainRateLimiter
from app.services.extractors.strategies import (
    DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR,
    DEFAULT_WIKIPEDIA_EXCLUDED_TAGS,
    ExtractionStrategyRegistry,
    get_default_strategy_registry,
)

DEFAULT_SCRAPER_USER_AGENT: str = (
    "RAG-Ingestion-Pipeline/0.1.0 (+https://github.com/duracellrabbid/librarian-pipeline; bot@example.com)"
)

__all__ = [
    "DEFAULT_SCRAPER_USER_AGENT",
    "DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR",
    "DEFAULT_WIKIPEDIA_EXCLUDED_TAGS",
    "Crawl4AIExtractor",
]

_FIRST_H1_PATTERN = re.compile(r"^#[ \t]+(\S.*)$", re.MULTILINE)


class Crawl4AIExtractor(BaseExtractor):
    """Web extractor powered by Crawl4AI AsyncWebCrawler with domain-specific strategies and retry resilience."""

    def __init__(
        self,
        *,
        registry: ExtractionStrategyRegistry | None = None,
        browser_config: BrowserConfig | None = None,
        run_config: CrawlerRunConfig | None = None,
        crawler: AsyncWebCrawler | None = None,
        rate_limiter: InProcessDomainRateLimiter | None = None,
        max_retries: int | None = None,
        backoff_factor: float | None = None,
        max_retry_delay: float | None = None,
        page_timeout: float | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Initialize Crawl4AIExtractor with optional configurations, rate limiter, or pre-existing crawler."""
        settings = get_settings()
        self.registry = registry or get_default_strategy_registry()
        self.browser_config = browser_config
        self.run_config = run_config
        self._crawler = crawler
        self.rate_limiter = rate_limiter or InProcessDomainRateLimiter(
            max_concurrency=settings.scraper_max_concurrency_per_domain
        )
        self.max_retries = max_retries if max_retries is not None else settings.scraper_max_retries
        self.backoff_factor = backoff_factor if backoff_factor is not None else settings.scraper_backoff_factor
        self.max_retry_delay = max_retry_delay if max_retry_delay is not None else settings.scraper_max_retry_delay
        self.page_timeout = page_timeout if page_timeout is not None else settings.scraper_page_timeout
        self.user_agent = self._resolve_user_agent(user_agent, settings.scraper_user_agent)

    @staticmethod
    def _resolve_user_agent(param_ua: str | None, settings_ua: str | None) -> str:
        """Resolve effective user agent from explicit parameter or settings, warning if unset."""
        if param_ua and param_ua.strip():
            return param_ua.strip()
        if settings_ua and settings_ua.strip():
            return settings_ua.strip()
        logger.warning(
            "Scraper User-Agent is not explicitly configured; using default '{}'. "
            "Please set SCRAPER_USER_AGENT in environment to identify your bot.",
            DEFAULT_SCRAPER_USER_AGENT,
        )
        return DEFAULT_SCRAPER_USER_AGENT

    def _prepare_run_config(self, strategy: Any) -> CrawlerRunConfig:
        """Construct CrawlerRunConfig enriched with user agent and page timeout."""
        if self.run_config is not None:
            return self.run_config
        base_cfg = strategy.get_run_config()
        if self.user_agent:
            base_cfg.user_agent = self.user_agent
        if self.page_timeout is not None:
            base_cfg.page_timeout = int(self.page_timeout * 1000)
        return base_cfg

    def _prepare_browser_config(self, strategy: Any) -> BrowserConfig:
        """Construct BrowserConfig enriched with user agent."""
        if self.browser_config is not None:
            return self.browser_config
        base_cfg = strategy.get_browser_config()
        if self.user_agent:
            base_cfg.user_agent = self.user_agent
        return base_cfg

    async def extract(self, source: str) -> ExtractedDocument:
        """Extract content, title, and metadata from web URL using Crawl4AI and resolved domain strategy.

        Args:
            source: Target web URL to extract.

        Returns:
            ExtractedDocument containing sanitized markdown and normalized metadata.

        Raises:
            ExtractionError: If crawling fails, returns non-2xx status, returns unsuccessful,
                or has no registered strategy for the domain.
        """
        strategy = self.registry.get_strategy(source)
        run_cfg = self._prepare_run_config(strategy)
        browser_cfg = self._prepare_browser_config(strategy)

        async with self.rate_limiter.acquire(source):
            result = await self._crawl_with_retry(source, run_config=run_cfg, browser_config=browser_cfg)

        raw_text = self._extract_raw_markdown(result)
        cleaned_content = strategy.clean(raw_text)

        res_metadata: dict[str, Any] = dict(getattr(result, "metadata", None) or {})
        title = self._resolve_title(res_metadata, cleaned_content, source)
        metadata = self._build_metadata(res_metadata, title, result, source)

        return ExtractedDocument(
            content=cleaned_content,
            title=title,
            source_url=source,
            metadata=metadata,
        )

    async def _crawl_with_retry(
        self,
        source: str,
        run_config: CrawlerRunConfig,
        browser_config: BrowserConfig,
    ) -> Any:
        """Execute web crawl with exponential backoff retry and Retry-After header support."""
        attempt = 0
        while True:
            result = None
            try:
                result = await self._crawl(source, run_config=run_config, browser_config=browser_config)
                self._validate_crawl_result(result, source)
                return result
            except ExtractionError as exc:
                headers = getattr(result, "response_headers", None)
                delay = self._evaluate_retry(exc, source, attempt, headers)
            except Exception as exc:
                wrapped = ExtractionError(f"Extraction failed for '{source}': {exc}", url=source)
                delay = self._evaluate_retry(wrapped, source, attempt, None)

            attempt += 1
            await asyncio.sleep(delay)

    def _evaluate_retry(
        self,
        exc: ExtractionError,
        source: str,
        attempt: int,
        headers: dict[str, Any] | None,
    ) -> float:
        """Determine whether to retry or fail fast, returning the backoff delay in seconds."""
        status = exc.status_code
        if status is not None and (400 <= status < 500 and status != 429):
            raise exc

        retry_after_delay = self._parse_retry_after(headers)
        if retry_after_delay is not None and retry_after_delay > self.max_retry_delay:
            raise ExtractionError(
                f"Extraction failed for '{source}': Retry-After delay ({retry_after_delay:.1f}s) "
                f"exceeds maximum allowed cap ({self.max_retry_delay:.1f}s)",
                url=source,
                status_code=status,
            )

        if attempt >= self.max_retries:
            raise exc

        if retry_after_delay is not None:
            return retry_after_delay

        return self._compute_jittered_backoff(attempt)

    def _compute_jittered_backoff(self, attempt: int) -> float:
        """Compute exponential backoff with randomized jitter, bounded by max_retry_delay."""
        backoff = self.backoff_factor * (2**attempt) + random.uniform(0, 1)
        return min(backoff, self.max_retry_delay)

    @staticmethod
    def _parse_retry_after(headers: dict[str, Any] | None) -> float | None:
        """Extract and parse numeric seconds or HTTP-date from Retry-After header."""
        if not headers:
            return None
        val: str | None = None
        for k, v in headers.items():
            if str(k).lower() == "retry-after":
                val = str(v).strip()
                break
        if not val:
            return None

        try:
            return max(0.0, float(val))
        except ValueError:
            pass

        try:
            target_dt = email.utils.parsedate_to_datetime(val)
            diff = target_dt.timestamp() - datetime.now(UTC).timestamp()
            return max(0.0, diff)
        except Exception:
            return None

    async def _crawl(
        self,
        source: str,
        run_config: CrawlerRunConfig | None = None,
        browser_config: BrowserConfig | None = None,
    ) -> Any:
        """Execute web crawl using configured crawler or ephemeral instance."""
        run_cfg = run_config or self.run_config or CrawlerRunConfig()
        browser_cfg = browser_config or self.browser_config or BrowserConfig(headless=True, verbose=False)
        if self._crawler is not None:
            return await self._crawler.arun(url=source, config=run_cfg)
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            return await crawler.arun(url=source, config=run_cfg)

    def _validate_crawl_result(self, result: Any, source: str) -> None:
        """Validate crawl result for non-null, success status, and HTTP error codes."""
        if result is None:
            raise ExtractionError(
                f"No result returned when crawling '{source}'",
                url=source,
            )

        status_code = getattr(result, "status_code", None)
        if status_code is not None and (status_code < 200 or status_code >= 400):
            error_msg = getattr(result, "error_message", None) or f"HTTP status {status_code}"
            raise ExtractionError(
                f"Extraction failed for '{source}': {error_msg}",
                url=source,
                status_code=status_code,
            )

        if not getattr(result, "success", True):
            error_msg = getattr(result, "error_message", None) or "Crawl was unsuccessful"
            raise ExtractionError(
                f"Extraction failed for '{source}': {error_msg}",
                url=source,
                status_code=status_code,
            )

    @staticmethod
    def _extract_raw_markdown(result: Any) -> str:
        """Extract markdown string from Crawl4AI result."""
        raw_markdown = getattr(result, "markdown", "")
        if hasattr(raw_markdown, "raw_markdown"):
            return str(raw_markdown.raw_markdown or "")
        return str(raw_markdown or "")

    @staticmethod
    def _resolve_title(res_metadata: dict[str, Any], content: str, source: str) -> str:
        """Resolve document title from metadata, first H1 heading, or URL fallback."""
        title: str | None = (
            res_metadata.get("title") or res_metadata.get("og:title") or res_metadata.get("twitter:title")
        )
        if title:
            return str(title)

        match = _FIRST_H1_PATTERN.search(content)
        if match:
            return match.group(1).strip()

        return source.rstrip("/").split("/")[-1] or source

    @staticmethod
    def _build_metadata(
        res_metadata: dict[str, Any],
        title: str,
        result: Any,
        source: str,
    ) -> dict[str, Any]:
        """Construct normalized metadata dictionary."""
        canonical_url = (
            res_metadata.get("canonical_url")
            or res_metadata.get("og:url")
            or getattr(result, "redirected_url", None)
            or source
        )
        language = res_metadata.get("language") or res_metadata.get("lang") or "en"
        return {
            **res_metadata,
            "title": title,
            "canonical_url": canonical_url,
            "language": language,
            "crawled_at": datetime.now(UTC).isoformat(),
        }
