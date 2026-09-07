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
    doc = await extractor.extract("https://example.com/ada")

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
        await extractor.extract("https://example.com/missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.url == "https://example.com/missing"
    assert "Page Not Found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_crawl4ai_extractor_crawl_exception():
    """Test ExtractionError is raised when crawler raises an exception."""
    mock_crawler = AsyncMock()
    mock_crawler.arun.side_effect = TimeoutError("Connection timed out")

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    with pytest.raises(ExtractionError) as exc_info:
        await extractor.extract("https://example.com/slow")

    assert exc_info.value.url == "https://example.com/slow"
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

        extractor = Crawl4AIExtractor()
        doc = await extractor.extract("https://example.com/context")

        assert doc.title == "Context Manager Test"
        assert doc.content == "# Context Manager Test\n\nContent body."
        mock_crawler_cls.assert_called_once_with(config=extractor.browser_config)
        mock_crawler_instance.arun.assert_awaited_once_with(
            url="https://example.com/context",
            config=extractor.run_config,
        )
