"""Unit tests for the extract_to_markdown utility script."""

from unittest.mock import AsyncMock, patch

import pytest
from app.core.exceptions import ExtractionError
from app.services.extractors.base import ExtractedDocument
from scripts.extract_to_markdown import derive_output_filename, extract_and_save, main


def test_derive_output_filename():
    """Test filename derivation from URL and title."""
    assert derive_output_filename("https://en.wikipedia.org/wiki/Ada_Lovelace") == "ada_lovelace.md"
    assert derive_output_filename("https://example.com/some/path/") == "path.md"
    assert (
        derive_output_filename("https://example.com", title="Hello World! - Page")
        == "hello_world_page.md"
    )


@pytest.mark.asyncio
async def test_extract_and_save_success(tmp_path):
    """Test extract_and_save invokes extractor and writes markdown file."""
    mock_doc = ExtractedDocument(
        content="# Sample Title\n\nSanitized content body.",
        title="Sample Title",
        source_url="https://en.wikipedia.org/wiki/Sample",
        metadata={"language": "en"},
    )

    out_file = tmp_path / "sample.md"

    with patch("scripts.extract_to_markdown.Crawl4AIExtractor") as mock_extractor_cls:
        mock_instance = AsyncMock()
        mock_instance.extract.return_value = mock_doc
        mock_extractor_cls.return_value = mock_instance

        saved_path = await extract_and_save("https://en.wikipedia.org/wiki/Sample", out_file)

        assert saved_path == out_file
        assert out_file.exists()
        assert out_file.read_text(encoding="utf-8") == "# Sample Title\n\nSanitized content body."
        mock_instance.extract.assert_awaited_once_with("https://en.wikipedia.org/wiki/Sample")


def test_main_cli_success(tmp_path):
    """Test main CLI execution with successful extraction."""
    mock_doc = ExtractedDocument(
        content="# Test Article\n\nTest content.",
        title="Test Article",
        source_url="https://example.com/test",
    )
    out_file = tmp_path / "output.md"

    with patch("scripts.extract_to_markdown.Crawl4AIExtractor") as mock_extractor_cls:
        mock_instance = AsyncMock()
        mock_instance.extract.return_value = mock_doc
        mock_extractor_cls.return_value = mock_instance

        ret = main(["https://example.com/test", "-o", str(out_file)])
        assert ret == 0
        assert out_file.exists()
        assert out_file.read_text(encoding="utf-8") == "# Test Article\n\nTest content."


def test_main_cli_extraction_error():
    """Test main CLI handles ExtractionError gracefully with non-zero exit code."""
    with patch("scripts.extract_to_markdown.Crawl4AIExtractor") as mock_extractor_cls:
        mock_instance = AsyncMock()
        mock_instance.extract.side_effect = ExtractionError("HTTP 404 Not Found", status_code=404)
        mock_extractor_cls.return_value = mock_instance

        ret = main(["https://example.com/missing"])
        assert ret == 1
