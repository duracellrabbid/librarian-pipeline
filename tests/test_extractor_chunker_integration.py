"""Integration tests connecting content extraction with hybrid chunking."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.chunkers.base import DocumentChunk
from app.services.chunkers.hybrid import HybridMarkdownChunker
from app.services.extractors.base import ExtractedDocument
from app.services.extractors.web import Crawl4AIExtractor

# Representative Wikipedia article extract with navigational chrome, edit links, and citations
WIKIPEDIA_ADA_LOVELACE_SAMPLE = (
    "# Ada Lovelace [edit]\n\n"
    "Augusta Ada King, Countess of Lovelace was an English mathematician and writer[1].\n"
    "She is best known for work on Babbage's mechanical general-purpose computer[2].\n\n"
    "## Early life [edit | edit source]\n\n"
    "Ada Gordon was born on 10 December 1815 in London[3].\n"
    "Her mother promoted Ada's interest in mathematics and logic[4][note 1].\n\n"
    "## Career and contributions [edit]\n\n"
    "Lovelace met Charles Babbage in June 1833[5].\n"
    "She became fascinated with Babbage's work on the Difference Engine[6].\n\n"
    "### First computer program [edit]\n\n"
    "Between 1842 and 1843, Lovelace translated an article by Luigi Menabrea.\n"
    "She appended an elaborate set of notes, simply called 'Notes'[7].\n"
    "Section G contains an algorithm for calculating a sequence of Bernoulli numbers[8].\n"
    "This is recognized as the first published computer program in history[9][citation needed].\n\n"
    "### Vision for computing [edit]\n\n"
    "Lovelace envisioned that the Analytical Engine might act upon things other than number.\n"
    "She suggested that the engine might compose elaborate and scientific pieces of music[10].\n\n"
    "## Legacy [edit]\n\n"
    "The computer language Ada was named after her in tribute to her pioneer work[11].\n"
)


@pytest.mark.asyncio
async def test_extractor_to_chunker_pipeline_integration():
    """Test full integration from web crawling extractor through hybrid markdown chunker."""
    # 1. Setup mocked crawler returning representative Wikipedia crawl result
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.status_code = 200
    mock_result.markdown = WIKIPEDIA_ADA_LOVELACE_SAMPLE
    mock_result.metadata = {
        "title": "Ada Lovelace - Wikipedia",
        "canonical_url": "https://en.wikipedia.org/wiki/Ada_Lovelace",
        "language": "en",
    }
    mock_result.redirected_url = None

    mock_crawler = AsyncMock()
    mock_crawler.arun.return_value = mock_result

    extractor = Crawl4AIExtractor(crawler=mock_crawler)
    chunker = HybridMarkdownChunker(
        max_chunk_size=1000,
        chunk_overlap=150,
        inject_breadcrumbs=True,
    )

    # 2. Extract content from Wikipedia URL
    source_url = "https://en.wikipedia.org/wiki/Ada_Lovelace"
    doc = await extractor.extract(source_url)

    # Assert extractor contract
    assert isinstance(doc, ExtractedDocument)
    assert doc.title == "Ada Lovelace - Wikipedia"
    assert doc.source_url == source_url
    assert doc.metadata["language"] == "en"
    assert doc.metadata["canonical_url"] == source_url
    assert "[edit]" not in doc.content
    assert "[1]" not in doc.content
    assert "[note 1]" not in doc.content
    assert "[citation needed]" not in doc.content

    # 3. Chunk extracted document
    chunks = chunker.chunk(doc)

    # Assert chunker output contract
    assert len(chunks) >= 4
    for i, chunk in enumerate(chunks):
        assert isinstance(chunk, DocumentChunk)
        assert chunk.chunk_index == i
        assert len(chunk.text) > 0
        assert chunk.char_count == len(chunk.text)
        assert chunk.token_count == max(1, len(chunk.text) // 4)

        # Ensure document metadata is preserved in every chunk
        assert chunk.metadata["source_url"] == source_url
        assert chunk.metadata["document_title"] == "Ada Lovelace - Wikipedia"
        assert chunk.metadata["language"] == "en"
        assert "crawled_at" in chunk.metadata

        # Ensure no uncleaned wiki markers leaked into chunks
        assert "[edit]" not in chunk.text
        assert "[1]" not in chunk.text
        assert "[citation needed]" not in chunk.text

    # Verify hierarchical breadcrumb propagation
    h3_chunks = [c for c in chunks if "First computer program" in c.metadata["heading_path"]]
    assert len(h3_chunks) == 1
    assert h3_chunks[0].metadata["heading_path"] == [
        "Ada Lovelace",
        "Career and contributions",
        "First computer program",
    ]
    assert "[Context: Ada Lovelace > Career and contributions > First computer program]" in h3_chunks[0].text
    assert "Bernoulli numbers" in h3_chunks[0].text

    legacy_chunks = [c for c in chunks if "Legacy" in c.metadata["heading_path"]]
    assert len(legacy_chunks) == 1
    assert legacy_chunks[0].metadata["heading_path"] == ["Ada Lovelace", "Legacy"]
    assert "[Context: Ada Lovelace > Legacy]" in legacy_chunks[0].text
    assert "pioneer work" in legacy_chunks[0].text
