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
    ".vector-header, .vector-sidebar, #mw-navigation, "
    ".reference, .reflist, .mw-editsection, .infobox, table.infobox"
)

_FIRST_H1_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)


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
        try:
            if self._crawler is not None:
                result = await self._crawler.arun(url=source, config=self.run_config)
            else:
                async with AsyncWebCrawler(config=self.browser_config) as crawler:
                    result = await crawler.arun(url=source, config=self.run_config)
        except Exception as exc:
            raise ExtractionError(
                f"Extraction failed for '{source}': {exc}",
                url=source,
            ) from exc

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

        raw_markdown = getattr(result, "markdown", "")
        if hasattr(raw_markdown, "raw_markdown"):
            raw_text = str(raw_markdown.raw_markdown or "")
        else:
            raw_text = str(raw_markdown or "")

        cleaned_content = clean_markdown(raw_text)

        # Metadata extraction and normalization
        res_metadata: dict[str, Any] = dict(getattr(result, "metadata", None) or {})

        # Resolve title: metadata -> first # H1 heading -> url fallback
        title: str | None = (
            res_metadata.get("title")
            or res_metadata.get("og:title")
            or res_metadata.get("twitter:title")
        )
        if not title:
            match = _FIRST_H1_PATTERN.search(cleaned_content)
            if match:
                title = match.group(1).strip()
            else:
                title = source.rstrip("/").split("/")[-1] or source

        canonical_url = (
            res_metadata.get("canonical_url")
            or res_metadata.get("og:url")
            or getattr(result, "redirected_url", None)
            or source
        )

        language = res_metadata.get("language") or res_metadata.get("lang") or "en"

        metadata: dict[str, Any] = {
            **res_metadata,
            "title": title,
            "canonical_url": canonical_url,
            "language": language,
            "crawled_at": datetime.now(UTC).isoformat(),
        }

        return ExtractedDocument(
            content=cleaned_content,
            title=title,
            source_url=source,
            metadata=metadata,
        )
