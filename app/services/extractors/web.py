"""Web content extractor implementation using Crawl4AI."""

import re
from datetime import UTC, datetime
from typing import Any

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

from app.core.exceptions import ExtractionError
from app.services.extractors.base import BaseExtractor, ExtractedDocument
from app.services.extractors.cleaning import clean_markdown

DEFAULT_WIKIPEDIA_EXCLUDED_TAGS: list[str] = [
    "nav",
    "footer",
    "header",
]

DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR: str = (
    ".vector-header, .vector-sidebar, #mw-navigation, .reference, .reflist, .mw-editsection, .infobox, table.infobox"
)

_FIRST_H1_PATTERN = re.compile(r"^#[ \t]+(\S.*)$", re.MULTILINE)


class Crawl4AIExtractor(BaseExtractor):
    """Web extractor powered by Crawl4AI AsyncWebCrawler."""

    def __init__(
        self,
        *,
        browser_config: BrowserConfig | None = None,
        run_config: CrawlerRunConfig | None = None,
        crawler: AsyncWebCrawler | None = None,
    ) -> None:
        """Initialize Crawl4AIExtractor with optional configurations or pre-existing crawler."""
        self.browser_config = browser_config or BrowserConfig(headless=True, verbose=False)
        self.run_config = run_config or CrawlerRunConfig(
            excluded_tags=DEFAULT_WIKIPEDIA_EXCLUDED_TAGS,
            excluded_selector=DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR,
        )
        self._crawler = crawler

    async def extract(self, source: str) -> ExtractedDocument:
        """Extract content, title, and metadata from web URL using Crawl4AI.

        Args:
            source: Target web URL to extract.

        Returns:
            ExtractedDocument containing sanitized markdown and normalized metadata.

        Raises:
            ExtractionError: If crawling fails, returns non-2xx status, or returns unsuccessful.
        """
        result = await self._crawl(source)
        self._validate_crawl_result(result, source)

        raw_text = self._extract_raw_markdown(result)
        cleaned_content = clean_markdown(raw_text)

        res_metadata: dict[str, Any] = dict(getattr(result, "metadata", None) or {})
        title = self._resolve_title(res_metadata, cleaned_content, source)
        metadata = self._build_metadata(res_metadata, title, result, source)

        return ExtractedDocument(
            content=cleaned_content,
            title=title,
            source_url=source,
            metadata=metadata,
        )

    async def _crawl(self, source: str) -> Any:
        """Execute web crawl using configured crawler or ephemeral instance."""
        try:
            if self._crawler is not None:
                return await self._crawler.arun(url=source, config=self.run_config)
            async with AsyncWebCrawler(config=self.browser_config) as crawler:
                return await crawler.arun(url=source, config=self.run_config)
        except Exception as exc:
            raise ExtractionError(
                f"Extraction failed for '{source}': {exc}",
                url=source,
            ) from exc

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
