"""Unit tests for extractor abstractions, domain exceptions, and implementations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.exceptions import ExtractionError
from app.services.extractors.base import BaseExtractor, ExtractedDocument
from app.services.extractors.cleaning import clean_markdown
from app.services.extractors.web import Crawl4AIExtractor
from pydantic import ValidationError


def test_extracted_document_instantiation():
    """Test ExtractedDocument creation with required and default fields."""
    doc = ExtractedDocument(
        content="# Sample Title\n\nSample content body.",
        title="Sample Title",
        source_url="https://en.wikipedia.org/wiki/Sample",
    )
    assert doc.content == "# Sample Title\n\nSample content body."
    assert doc.title == "Sample Title"
    assert doc.source_url == "https://en.wikipedia.org/wiki/Sample"
    assert doc.metadata == {}

    # With explicit metadata
    meta = {"language": "en", "author": "Wiki"}
    doc_with_meta = ExtractedDocument(
        content="Content",
        title="Title",
        source_url="https://example.com",
        metadata=meta,
    )
    assert doc_with_meta.metadata == meta


def test_extracted_document_validation():
    """Test ExtractedDocument raises validation error when required fields are missing."""
    with pytest.raises(ValidationError):
        # Missing content and title
        ExtractedDocument(source_url="https://example.com")  # type: ignore[call-arg]


def test_base_extractor_protocol():
    """Test BaseExtractor runtime protocol checking."""

    class DummyExtractor:
        async def extract(self, source: str) -> ExtractedDocument:
            return ExtractedDocument(content="dummy", title="dummy", source_url=source)

    class IncompleteExtractor:
        pass

    assert isinstance(DummyExtractor(), BaseExtractor)
    assert not isinstance(IncompleteExtractor(), BaseExtractor)


def test_extraction_error():
    """Test ExtractionError attributes and hierarchy."""
    err = ExtractionError("Failed to fetch content", url="https://example.com", status_code=404)
    assert isinstance(err, Exception)
    assert str(err) == "Failed to fetch content"
    assert err.url == "https://example.com"
    assert err.status_code == 404


def test_clean_markdown_edit_links():
    """Test removal of Wikipedia edit links in headings and body text."""
    raw = """# Alan Turing [edit]

## Early life[edit | edit source]
Alan Mathison Turing was born in London.[edit]

### Education [edit](https://en.wikipedia.org/w/index.php?title=Alan_Turing&action=edit)
He studied at King's College, Cambridge.
"""
    cleaned = clean_markdown(raw)
    assert "[edit]" not in cleaned
    assert "[edit | edit source]" not in cleaned
    assert "action=edit" not in cleaned
    assert "# Alan Turing" in cleaned
    assert "## Early life" in cleaned
    assert "### Education" in cleaned
    assert "born in London." in cleaned


def test_clean_markdown_edit_links_variants():
    """Test removal of escaped and double-bracketed edit link variants."""
    raw = (
        "Section\\[edit\\]\n"
        "Topic\\[\\[edit | edit source\\]\\]\n"
        "Wikitext [[edit]] link\n"
        "Escaped link \\[edit\\](https://example.com/edit)"
    )
    cleaned = clean_markdown(raw)
    assert "edit" not in cleaned
    assert "Section" in cleaned
    assert "Topic" in cleaned
    assert "Wikitext" in cleaned
    assert "Escaped link" in cleaned


def test_clean_markdown_citation_markers():
    """Test removal of citation markers while preserving standard markdown links."""
    raw = (
        "Turing was a mathematician[1] and computer scientist[2][3].\n"
        "He played a pivotal role in cracking intercepted messages[4](https://en.wikipedia.org/#cite-4).\n"
        "Some claims required verification[citation needed] or had notes[note 1].\n"
        "Read more about [Computer Science](https://en.wikipedia.org/wiki/Computer_science)."
    )
    cleaned = clean_markdown(raw)

    assert "[1]" not in cleaned
    assert "[2]" not in cleaned
    assert "[3]" not in cleaned
    assert "[4]" not in cleaned
    assert "#cite-4" not in cleaned
    assert "[citation needed]" not in cleaned
    assert "[note 1]" not in cleaned
    # Ensure real hyperlinks are preserved
    assert "[Computer Science](https://en.wikipedia.org/wiki/Computer_science)" in cleaned
    assert "Turing was a mathematician and computer scientist." in cleaned


def test_clean_markdown_excess_blank_lines():
    """Test collapsing excess blank lines and trimming line trailing whitespace."""
    raw = "Line 1    \n\n\n\n\nLine 2\n\n\nLine 3\n\n"
    cleaned = clean_markdown(raw)
    assert cleaned == "Line 1\n\nLine 2\n\nLine 3"


def test_clean_markdown_empty_or_whitespace():
    """Test clean_markdown with empty input."""
    assert clean_markdown("") == ""
    assert clean_markdown("   \n\n  ") == ""


@pytest.mark.asyncio
async def test_crawl4ai_extractor_protocol_compliance():
    """Test Crawl4AIExtractor conforms to BaseExtractor protocol."""
    extractor = Crawl4AIExtractor()
    assert isinstance(extractor, BaseExtractor)


@pytest.mark.asyncio
async def test_crawl4ai_extractor_success():
    """Test successful extraction with metadata normalization and cleaned markdown."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.status_code = 200
    mock_result.markdown = (
        "# Alan Turing [edit]\n\n"
        "Alan Turing was a mathematician[1] and logician.\n\n\n\n"
        "## Career [edit]\n"
        "He worked at Bletchley Park[2]."
    )
    mock_result.metadata = {
        "title": "Alan Turing - Wikipedia",
        "language": "en",
    }
    mock_result.redirected_url = None

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_result

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    url = "https://en.wikipedia.org/wiki/Alan_Turing"
    doc = await extractor.extract(url)

    assert isinstance(doc, ExtractedDocument)
    assert doc.source_url == url
    assert doc.title == "Alan Turing - Wikipedia"
    assert "[edit]" not in doc.content
    assert "[1]" not in doc.content
    assert "[2]" not in doc.content
    assert "Alan Turing was a mathematician and logician." in doc.content
    assert "\n\n\n" not in doc.content
    assert doc.metadata["language"] == "en"
    assert doc.metadata["canonical_url"] == url
    assert "crawled_at" in doc.metadata
    mock_crawler.arun.assert_awaited_once()


@pytest.mark.asyncio
async def test_crawl4ai_extractor_title_fallback():
    """Test title extraction falls back to first markdown heading when metadata has no title."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.status_code = 200
    mock_result.markdown = "# Ada Lovelace\n\nFirst computer programmer."
    mock_result.metadata = {}
    mock_result.redirected_url = None

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_result

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/Ada_Lovelace")

    assert doc.title == "Ada Lovelace"


@pytest.mark.asyncio
async def test_crawl4ai_extractor_http_error():
    """Test ExtractionError is raised on HTTP error status."""
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.status_code = 404
    mock_result.error_message = "Page Not Found"

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_result

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    with pytest.raises(ExtractionError) as exc_info:
        await extractor.extract("https://en.wikipedia.org/wiki/Missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.url == "https://en.wikipedia.org/wiki/Missing"
    assert "Page Not Found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_crawl4ai_extractor_crawl_exception():
    """Test ExtractionError is raised when crawler raises an exception."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = TimeoutError("Connection timed out")

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    with pytest.raises(ExtractionError) as exc_info:
        await extractor.extract("https://en.wikipedia.org/wiki/Slow")

    assert exc_info.value.url == "https://en.wikipedia.org/wiki/Slow"
    assert "Connection timed out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_crawl4ai_extractor_default_crawler_lifecycle():
    """Test AsyncWebCrawler context manager lifecycle when crawler is omitted."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.status_code = 200
    mock_result.markdown = "# Context Manager Test\n\nContent body."
    mock_result.metadata = {"title": "Context Manager Test"}

    mock_crawler_instance = AsyncMock()
    mock_crawler_instance.arun.return_value = mock_result

    with patch("app.services.extractors.web.AsyncWebCrawler") as mock_crawler_cls:
        mock_crawler_cls.return_value.__aenter__.return_value = mock_crawler_instance

        from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

        custom_browser = BrowserConfig(headless=True, verbose=False)
        custom_run = CrawlerRunConfig()
        extractor = Crawl4AIExtractor(browser_config=custom_browser, run_config=custom_run)
        doc = await extractor.extract("https://en.wikipedia.org/wiki/Context")

        assert doc.title == "Context Manager Test"
        assert doc.content == "# Context Manager Test\n\nContent body."
        mock_crawler_cls.assert_called_once_with(config=custom_browser)
        mock_crawler_instance.arun.assert_awaited_once_with(
            url="https://en.wikipedia.org/wiki/Context",
            config=custom_run,
        )


def test_normalize_whitespace_indented_blocks():
    """Test that 4-space and tab indented lines preserve leading whitespace."""
    from app.services.extractors.cleaning import normalize_whitespace

    raw = "Intro\n    code line with    multiple spaces\n\ttab indented line"
    cleaned = normalize_whitespace(raw)
    assert "    code line with    multiple spaces" in cleaned
    assert "\ttab indented line" in cleaned


@pytest.mark.asyncio
async def test_crawl4ai_extractor_none_result():
    """Test ExtractionError is raised when crawler returns None."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = None

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    with pytest.raises(ExtractionError, match="No result returned"):
        await extractor.extract("https://en.wikipedia.org/wiki/None")


@pytest.mark.asyncio
async def test_crawl4ai_extractor_unsuccessful_crawl():
    """Test ExtractionError is raised when crawl returns success=False with 200."""
    mock_result = MagicMock()
    mock_result.status_code = 200
    mock_result.success = False
    mock_result.error_message = "Crawl was unsuccessful"

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_result

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    with pytest.raises(ExtractionError, match="Crawl was unsuccessful"):
        await extractor.extract("https://en.wikipedia.org/wiki/Unsuccessful")


@pytest.mark.asyncio
async def test_crawl4ai_extractor_markdown_object_attribute():
    """Test extracting markdown from result object with .raw_markdown attribute."""

    class MarkdownResult:
        raw_markdown = "# Markdown Object\n\nBody content."

    mock_result = MagicMock()
    mock_result.status_code = 200
    mock_result.success = True
    mock_result.markdown = MarkdownResult()
    mock_result.metadata = {"title": "Object Title"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_result

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/Obj")
    assert doc.title == "Object Title"
    assert "Body content." in doc.content


@pytest.mark.asyncio
async def test_crawl4ai_extractor_slug_fallback():
    """Test title fallback to URL slug when no metadata title and no H1 heading exists."""
    mock_result = MagicMock()
    mock_result.status_code = 200
    mock_result.success = True
    mock_result.markdown = "Paragraph without heading."
    mock_result.metadata = {}

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_result

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/fallback-slug")
    assert doc.title == "fallback-slug"


@pytest.mark.asyncio
async def test_crawl4ai_extractor_unregistered_domain_raises_error():
    """Test ExtractionError is raised immediately when no extraction strategy is registered for domain."""
    extractor = Crawl4AIExtractor()
    with pytest.raises(ExtractionError) as exc_info:
        await extractor.extract("https://unregistered-domain.com/article")

    assert exc_info.value.url == "https://unregistered-domain.com/article"
    assert "No extraction strategy registered" in str(exc_info.value)


@pytest.mark.asyncio
async def test_crawl4ai_extractor_custom_registry():
    """Test Crawl4AIExtractor with explicitly provided ExtractionStrategyRegistry."""
    from app.services.extractors.strategies.registry import ExtractionStrategyRegistry
    from app.services.extractors.strategies.wikipedia import WikipediaExtractionStrategy

    mock_result = MagicMock()
    mock_result.status_code = 200
    mock_result.success = True
    mock_result.markdown = "# Custom Registry\n\nCustom content."
    mock_result.metadata = {"title": "Custom Registry"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_result

    custom_registry = ExtractionStrategyRegistry(strategies=[WikipediaExtractionStrategy()])
    extractor = Crawl4AIExtractor(registry=custom_registry, crawler=mock_crawler)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/Custom_Reg")
    assert doc.title == "Custom Registry"


@pytest.mark.asyncio
async def test_crawl4ai_extractor_retry_on_429_success(monkeypatch):
    """Test retry sequence on HTTP 429 rate limit that succeeds on subsequent attempt."""
    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    mock_res_429 = MagicMock()
    mock_res_429.success = False
    mock_res_429.status_code = 429
    mock_res_429.error_message = "Rate limited"
    mock_res_429.response_headers = {}

    mock_res_200 = MagicMock()
    mock_res_200.success = True
    mock_res_200.status_code = 200
    mock_res_200.markdown = "# Success\n\nBody content."
    mock_res_200.metadata = {"title": "Success"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = [mock_res_429, mock_res_200]

    extractor = Crawl4AIExtractor(
        crawler=mock_crawler,
        max_retries=2,
        backoff_factor=1.0,
        user_agent="CustomTestBot/1.0",
    )
    doc = await extractor.extract("https://en.wikipedia.org/wiki/Retry429")
    assert doc.title == "Success"
    assert mock_crawler.arun.await_count == 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 1.0


@pytest.mark.asyncio
async def test_crawl4ai_extractor_retry_on_5xx_success(monkeypatch):
    """Test retry sequence on HTTP 503 error that succeeds on subsequent attempt."""
    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    mock_res_503 = MagicMock()
    mock_res_503.success = False
    mock_res_503.status_code = 503
    mock_res_503.error_message = "Service Unavailable"
    mock_res_503.response_headers = {}

    mock_res_200 = MagicMock()
    mock_res_200.success = True
    mock_res_200.status_code = 200
    mock_res_200.markdown = "# Recovered\n\nBody content."
    mock_res_200.metadata = {"title": "Recovered"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = [mock_res_503, mock_res_200]

    extractor = Crawl4AIExtractor(crawler=mock_crawler, max_retries=2, backoff_factor=1.0)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/Retry503")
    assert doc.title == "Recovered"
    assert mock_crawler.arun.await_count == 2
    assert len(sleep_calls) == 1


@pytest.mark.asyncio
async def test_crawl4ai_extractor_retry_on_network_timeout(monkeypatch):
    """Test retry sequence on Playwright/network timeout exception."""
    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    mock_res_200 = MagicMock()
    mock_res_200.success = True
    mock_res_200.status_code = 200
    mock_res_200.markdown = "# After Timeout\n\nBody content."
    mock_res_200.metadata = {"title": "After Timeout"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = [TimeoutError("Page navigation timed out"), mock_res_200]

    extractor = Crawl4AIExtractor(crawler=mock_crawler, max_retries=2)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/Timeout")
    assert doc.title == "After Timeout"
    assert mock_crawler.arun.await_count == 2
    assert len(sleep_calls) == 1


@pytest.mark.asyncio
async def test_crawl4ai_extractor_retry_exhaustion_5xx(monkeypatch):
    """Test retry exhaustion on persistent 5xx errors raises ExtractionError."""
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    mock_res_500 = MagicMock()
    mock_res_500.success = False
    mock_res_500.status_code = 500
    mock_res_500.error_message = "Internal Server Error"
    mock_res_500.response_headers = {}

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_res_500

    extractor = Crawl4AIExtractor(crawler=mock_crawler, max_retries=2)
    with pytest.raises(ExtractionError) as exc_info:
        await extractor.extract("https://en.wikipedia.org/wiki/Persistent500")

    assert exc_info.value.status_code == 500
    assert exc_info.value.url == "https://en.wikipedia.org/wiki/Persistent500"
    assert "Internal Server Error" in str(exc_info.value)
    assert mock_crawler.arun.await_count == 3


@pytest.mark.asyncio
async def test_crawl4ai_extractor_fast_fail_on_4xx_client_error():
    """Test non-retriable 4xx client errors fail immediately without retry."""
    mock_res_404 = MagicMock()
    mock_res_404.success = False
    mock_res_404.status_code = 404
    mock_res_404.error_message = "Not Found"

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_res_404

    extractor = Crawl4AIExtractor(crawler=mock_crawler, max_retries=3)
    with pytest.raises(ExtractionError) as exc_info:
        await extractor.extract("https://en.wikipedia.org/wiki/NotFound")

    assert exc_info.value.status_code == 404
    assert mock_crawler.arun.await_count == 1


@pytest.mark.asyncio
async def test_crawl4ai_extractor_retry_after_within_cap(monkeypatch):
    """Test HTTP 429 with Retry-After header within cap pauses for header interval."""
    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    mock_res_429 = MagicMock()
    mock_res_429.success = False
    mock_res_429.status_code = 429
    mock_res_429.error_message = "Rate limited"
    mock_res_429.response_headers = {"retry-after": "5"}

    mock_res_200 = MagicMock()
    mock_res_200.success = True
    mock_res_200.status_code = 200
    mock_res_200.markdown = "# Allowed\n\nContent"
    mock_res_200.metadata = {"title": "Allowed"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = [mock_res_429, mock_res_200]

    extractor = Crawl4AIExtractor(crawler=mock_crawler, max_retries=2, max_retry_delay=60.0)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/RetryAfter")
    assert doc.title == "Allowed"
    assert mock_crawler.arun.await_count == 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 5.0


@pytest.mark.asyncio
async def test_crawl4ai_extractor_retry_after_http_date_format(monkeypatch):
    """Test HTTP 429 with Retry-After in HTTP-date format parses correctly."""
    from datetime import UTC, datetime, timedelta

    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    future_dt = datetime.now(UTC) + timedelta(seconds=10)
    date_str = future_dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

    mock_res_429 = MagicMock()
    mock_res_429.success = False
    mock_res_429.status_code = 429
    mock_res_429.error_message = "Rate limited"
    mock_res_429.response_headers = {"Retry-After": date_str}

    mock_res_200 = MagicMock()
    mock_res_200.success = True
    mock_res_200.status_code = 200
    mock_res_200.markdown = "# Date OK\n\nContent"
    mock_res_200.metadata = {"title": "Date OK"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = [mock_res_429, mock_res_200]

    extractor = Crawl4AIExtractor(crawler=mock_crawler, max_retries=2, max_retry_delay=60.0)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/DateHeader")
    assert doc.title == "Date OK"
    assert len(sleep_calls) == 1
    assert 8.0 <= sleep_calls[0] <= 12.0


@pytest.mark.asyncio
async def test_crawl4ai_extractor_retry_after_exceeds_cap_fails_fast(monkeypatch):
    """Test HTTP 429 with Retry-After exceeding max_retry_delay fails fast without waiting."""
    mock_sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    mock_res_429 = MagicMock()
    mock_res_429.success = False
    mock_res_429.status_code = 429
    mock_res_429.error_message = "Rate limited"
    mock_res_429.response_headers = {"Retry-After": "3600"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_res_429

    extractor = Crawl4AIExtractor(crawler=mock_crawler, max_retries=3, max_retry_delay=60.0)
    with pytest.raises(ExtractionError) as exc_info:
        await extractor.extract("https://en.wikipedia.org/wiki/ExceedsCap")

    assert exc_info.value.status_code == 429
    assert "exceeds maximum allowed cap" in str(exc_info.value)
    mock_sleep.assert_not_awaited()
    assert mock_crawler.arun.await_count == 1


def test_crawl4ai_extractor_user_agent_warning_when_default():
    """Test warning logged when user_agent is not configured."""
    from loguru import logger

    logs = []
    handler_id = logger.add(lambda msg: logs.append(msg), level="WARNING")
    try:
        _ = Crawl4AIExtractor(user_agent=None)
        assert any("User-Agent is not explicitly configured" in str(m) for m in logs)
    finally:
        logger.remove(handler_id)


@pytest.mark.asyncio
async def test_crawl4ai_extractor_uses_rate_limiter():
    """Test that Crawl4AIExtractor acquires the rate limiter during extraction."""
    from contextlib import asynccontextmanager

    from app.services.extractors.limiter import InProcessDomainRateLimiter

    limiter = InProcessDomainRateLimiter(max_concurrency=1)
    acquired_urls = []

    orig_acquire = limiter.acquire

    @asynccontextmanager
    async def track_acquire(url: str):
        acquired_urls.append(url)
        async with orig_acquire(url):
            yield

    limiter.acquire = track_acquire  # type: ignore

    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.success = True
    mock_res.markdown = "# Limiter Test\n\nBody"
    mock_res.metadata = {"title": "Limiter Test"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_res

    extractor = Crawl4AIExtractor(crawler=mock_crawler, rate_limiter=limiter)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/RateLimitedCall")
    assert doc.title == "Limiter Test"
    assert acquired_urls == ["https://en.wikipedia.org/wiki/RateLimitedCall"]


def test_wikipedia_strategy_user_agent_and_timeout():
    """Test WikipediaExtractionStrategy config generation with custom user_agent and page_timeout."""
    from app.services.extractors.strategies.wikipedia import WikipediaExtractionStrategy

    strategy = WikipediaExtractionStrategy(user_agent="WikiBot/1.0", page_timeout=15.0)
    run_cfg = strategy.get_run_config()
    browser_cfg = strategy.get_browser_config()

    assert run_cfg.user_agent == "WikiBot/1.0"
    assert run_cfg.page_timeout == 15000
    assert browser_cfg.user_agent == "WikiBot/1.0"


def test_crawl4ai_extractor_resolves_user_agent_from_settings(monkeypatch):
    """Test Crawl4AIExtractor resolves user_agent from settings when omitted in constructor."""
    monkeypatch.setenv("SCRAPER_USER_AGENT", "FromEnv/1.0")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        extractor = Crawl4AIExtractor(user_agent=None)
        assert extractor.user_agent == "FromEnv/1.0"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_crawl4ai_extractor_retry_after_malformed_fallback(monkeypatch):
    """Test HTTP 429 with malformed Retry-After header falls back to exponential backoff."""
    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    mock_res_429 = MagicMock()
    mock_res_429.success = False
    mock_res_429.status_code = 429
    mock_res_429.error_message = "Rate limited"
    mock_res_429.response_headers = {"Retry-After": "not-a-valid-date-or-number"}

    mock_res_200 = MagicMock()
    mock_res_200.success = True
    mock_res_200.status_code = 200
    mock_res_200.markdown = "# Recovered\n\nBody"
    mock_res_200.metadata = {"title": "Recovered"}

    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = [mock_res_429, mock_res_200]

    extractor = Crawl4AIExtractor(crawler=mock_crawler, max_retries=2, backoff_factor=1.0)
    doc = await extractor.extract("https://en.wikipedia.org/wiki/MalformedRetryAfter")
    assert doc.title == "Recovered"
    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 1.0
