"""Unit tests for chunker abstractions, models, heading parsing, and hybrid chunker."""

import pytest
from app.services.chunkers.base import BaseChunker, DocumentChunk
from app.services.chunkers.hybrid import (
    HybridMarkdownChunker,
    parse_markdown_sections,
    recursive_split_text,
)
from app.services.extractors.base import ExtractedDocument
from pydantic import ValidationError


def test_document_chunk_instantiation():
    """Test DocumentChunk creation and default/computed fields."""
    chunk = DocumentChunk(
        chunk_index=0,
        text="This is chunk content.",
        char_count=22,
        token_count=6,
        metadata={"heading_path": ["Title", "Section"]},
    )
    assert chunk.chunk_index == 0
    assert chunk.text == "This is chunk content."
    assert chunk.char_count == 22
    assert chunk.token_count == 6
    assert chunk.metadata == {"heading_path": ["Title", "Section"]}


def test_document_chunk_auto_counts():
    """Test DocumentChunk automatically computes char_count and token_count if omitted."""
    chunk = DocumentChunk(
        chunk_index=1,
        text="Hello world! This is a test.",
    )
    assert chunk.chunk_index == 1
    assert chunk.text == "Hello world! This is a test."
    assert chunk.char_count == len("Hello world! This is a test.")
    assert chunk.token_count > 0
    assert chunk.metadata == {}


def test_document_chunk_validation():
    """Test DocumentChunk validation errors for negative index or empty text."""
    with pytest.raises(ValidationError):
        # Negative chunk index
        DocumentChunk(chunk_index=-1, text="Sample text")

    with pytest.raises(ValidationError):
        # Empty text
        DocumentChunk(chunk_index=0, text="")


def test_base_chunker_protocol():
    """Test BaseChunker runtime protocol check."""

    class DummyChunker:
        def chunk(
            self,
            document: ExtractedDocument | str,
            metadata: dict | None = None,
        ) -> list[DocumentChunk]:
            return [
                DocumentChunk(
                    chunk_index=0,
                    text="chunk",
                )
            ]

    class IncompleteChunker:
        pass

    assert isinstance(DummyChunker(), BaseChunker)
    assert not isinstance(IncompleteChunker(), BaseChunker)


def test_parse_markdown_sections_hierarchy():
    """Test heading parser correctly tracks breadcrumbs across nested heading levels."""
    md = """Introduction text.

# Computer Science
Overview of CS.

## Algorithms
Sorting and searching.

### Quicksort
Details of quicksort.

## Data Structures
Trees and graphs.

# Mathematics
Discrete math.
"""
    sections = parse_markdown_sections(md)

    assert len(sections) == 6

    # Section 0: Preamble
    assert sections[0].heading_path == []
    assert sections[0].content == "Introduction text."

    # Section 1: H1 Computer Science
    assert sections[1].heading_path == ["Computer Science"]
    assert sections[1].title == "Computer Science"
    assert sections[1].level == 1
    assert sections[1].content == "Overview of CS."

    # Section 2: H2 Algorithms
    assert sections[2].heading_path == ["Computer Science", "Algorithms"]
    assert sections[2].title == "Algorithms"
    assert sections[2].level == 2
    assert sections[2].content == "Sorting and searching."

    # Section 3: H3 Quicksort
    assert sections[3].heading_path == ["Computer Science", "Algorithms", "Quicksort"]
    assert sections[3].title == "Quicksort"
    assert sections[3].level == 3
    assert sections[3].content == "Details of quicksort."

    # Section 4: H2 Data Structures (popped Quicksort & Algorithms)
    assert sections[4].heading_path == ["Computer Science", "Data Structures"]
    assert sections[4].title == "Data Structures"
    assert sections[4].level == 2
    assert sections[4].content == "Trees and graphs."

    # Section 5: H1 Mathematics
    assert sections[5].heading_path == ["Mathematics"]
    assert sections[5].title == "Mathematics"
    assert sections[5].level == 1
    assert sections[5].content == "Discrete math."


def test_parse_markdown_sections_code_block_protection():
    """Test that '#' comments inside fenced code blocks are not parsed as headings."""
    md = """# Programming

Here is python code:

```python
# This is a comment, not a heading
def hello():
    # Another comment
    return "world"
```

End of section.
"""
    sections = parse_markdown_sections(md)
    assert len(sections) == 1
    assert sections[0].heading_path == ["Programming"]
    assert "# This is a comment" in sections[0].content


def test_parse_markdown_sections_no_headings():
    """Test document with no headings produces a single section with empty heading_path."""
    md = "Just plain text.\nAnother paragraph."
    sections = parse_markdown_sections(md)
    assert len(sections) == 1
    assert sections[0].heading_path == []
    assert sections[0].content == "Just plain text.\nAnother paragraph."


def test_recursive_split_text_small():
    """Test text smaller than max_chunk_size is not split."""
    text = "Short text under the limit."
    result = recursive_split_text(text, max_chunk_size=100, chunk_overlap=20)
    assert result == [text]


def test_recursive_split_text_paragraphs_and_overlap():
    """Test recursive splitting along paragraph boundaries with overlap."""
    p1 = "Paragraph 1 is about introductory topics in science."
    p2 = "Paragraph 2 delves into intermediate concepts and logic."
    p3 = "Paragraph 3 concludes with summary and final remarks."
    full_text = f"{p1}\n\n{p2}\n\n{p3}"

    chunks = recursive_split_text(full_text, max_chunk_size=80, chunk_overlap=20)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 80


def test_recursive_split_text_single_giant_word():
    """Test recursive splitting handles giant strings without spaces."""
    giant = "A" * 150
    chunks = recursive_split_text(giant, max_chunk_size=50, chunk_overlap=10)
    assert len(chunks) == 4
    for chunk in chunks:
        assert len(chunk) <= 50


def test_hybrid_chunker_basic_hierarchy():
    """Test HybridMarkdownChunker preserves headings, breadcrumbs, and increases chunk_index."""
    md = """# Alan Turing

## Early life
Alan Turing was born in London.

## Career
He worked at Bletchley Park.

### Enigma
He cracked the Enigma code.
"""
    chunker = HybridMarkdownChunker(inject_breadcrumbs=True)
    chunks = chunker.chunk(md)

    assert len(chunks) == 3
    assert [c.chunk_index for c in chunks] == [0, 1, 2]

    # Chunk 0: Early life
    assert chunks[0].metadata["heading_path"] == ["Alan Turing", "Early life"]
    assert chunks[0].metadata["breadcrumb"] == "Alan Turing > Early life"
    assert "[Context: Alan Turing > Early life]" in chunks[0].text
    assert "Alan Turing was born in London." in chunks[0].text

    # Chunk 1: Career
    assert chunks[1].metadata["heading_path"] == ["Alan Turing", "Career"]
    assert chunks[1].metadata["breadcrumb"] == "Alan Turing > Career"
    assert "[Context: Alan Turing > Career]" in chunks[1].text
    assert "He worked at Bletchley Park." in chunks[1].text

    # Chunk 2: Enigma
    assert chunks[2].metadata["heading_path"] == ["Alan Turing", "Career", "Enigma"]
    assert chunks[2].metadata["breadcrumb"] == "Alan Turing > Career > Enigma"
    assert "[Context: Alan Turing > Career > Enigma]" in chunks[2].text
    assert "He cracked the Enigma code." in chunks[2].text


def test_hybrid_chunker_document_without_headings():
    """Test HybridMarkdownChunker handles plain text with no headings."""
    text = "This is a plain document without any markdown headings."
    chunker = HybridMarkdownChunker()
    chunks = chunker.chunk(text)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].metadata["heading_path"] == []
    assert chunks[0].metadata["breadcrumb"] == ""
    assert "[Context:" not in chunks[0].text
    assert chunks[0].text == text


def test_hybrid_chunker_oversized_section_splitting():
    """Test HybridMarkdownChunker recursively splits sections exceeding max_chunk_size."""
    long_paragraph = "Sentence about technology and algorithms. " * 30  # ~1260 chars
    md = f"""# Overview

## Long Section
{long_paragraph}
"""
    # Configure small max_chunk_size to force section splitting
    chunker = HybridMarkdownChunker(max_chunk_size=400, chunk_overlap=50)
    chunks = chunker.chunk(md)

    assert len(chunks) > 1
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
        assert len(c.text) <= 450
        assert c.metadata["heading_path"] == ["Overview", "Long Section"]
        assert "[Context: Overview > Long Section]" in c.text


def test_hybrid_chunker_extracted_document_integration():
    """Test HybridMarkdownChunker processes ExtractedDocument and propagates doc metadata."""
    doc = ExtractedDocument(
        content="# Title\n\nContent paragraph.",
        title="Document Title",
        source_url="https://en.wikipedia.org/wiki/Doc",
        metadata={"language": "en", "author": "Wikipedia"},
    )
    chunker = HybridMarkdownChunker()
    chunks = chunker.chunk(doc)

    assert len(chunks) == 1
    assert chunks[0].metadata["source_url"] == "https://en.wikipedia.org/wiki/Doc"
    assert chunks[0].metadata["document_title"] == "Document Title"
    assert chunks[0].metadata["language"] == "en"
    assert chunks[0].metadata["author"] == "Wikipedia"


def test_hybrid_chunker_disable_breadcrumbs():
    """Test HybridMarkdownChunker with inject_breadcrumbs=False omits prefix in text."""
    md = "# Heading 1\n\n## Subheading\nContent under subheading."
    chunker = HybridMarkdownChunker(inject_breadcrumbs=False)
    chunks = chunker.chunk(md)

    assert len(chunks) == 1
    assert "[Context:" not in chunks[0].text
    assert chunks[0].text == "Content under subheading."
    assert chunks[0].metadata["heading_path"] == ["Heading 1", "Subheading"]


def test_hybrid_chunker_empty_input():
    """Test HybridMarkdownChunker returns empty list for empty content."""
    chunker = HybridMarkdownChunker()
    assert chunker.chunk("") == []
    assert chunker.chunk("   \n\n  ") == []


def test_hybrid_chunker_invalid_configs():
    """Test HybridMarkdownChunker raises ValueError for invalid sizing configs."""
    with pytest.raises(ValueError, match="max_chunk_size must be positive"):
        HybridMarkdownChunker(max_chunk_size=0)

    with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
        HybridMarkdownChunker(max_chunk_size=500, chunk_overlap=-1)

    with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
        HybridMarkdownChunker(max_chunk_size=500, chunk_overlap=500)


def test_choose_separator_no_match():
    """Test _choose_separator returns empty string and length when no separator matches."""
    from app.services.chunkers.hybrid import _choose_separator

    sep, idx = _choose_separator("abcd", ["\n\n", "\n"])
    assert sep == ""
    assert idx == 2


def test_recursive_split_text_zero_overlap():
    """Test recursive_split_text with chunk_overlap=0."""
    text = "Word1 " * 50
    chunks = recursive_split_text(text, max_chunk_size=50, chunk_overlap=0)
    assert len(chunks) > 1


def test_recursive_split_text_multi_tier_split():
    """Test recursive_split_text when a split piece exceeds max_chunk_size and subdivides."""
    text = "Small paragraph.\n\n" + ("LongSentence " * 30)
    chunks = recursive_split_text(text, max_chunk_size=60, chunk_overlap=10)
    assert len(chunks) >= 3


def test_recursive_split_text_overlap_trimmed_to_fit():
    """Test recursive_split_text trims overlap pieces when new piece plus overlap exceeds max."""
    text = "aaa bbb ccc ddd eee fff ggg hhh"
    chunks = recursive_split_text(text, max_chunk_size=15, chunk_overlap=10, separators=[" "])
    assert len(chunks) > 1


def test_hybrid_chunker_with_extra_metadata():
    """Test HybridMarkdownChunker.chunk merges caller-provided metadata."""
    chunker = HybridMarkdownChunker()
    chunks = chunker.chunk("Some text", metadata={"extra_field": "val"})
    assert len(chunks) == 1
    assert chunks[0].metadata["extra_field"] == "val"


def test_compute_overlap_trimmed_for_large_piece():
    """Test _compute_overlap pops pieces when candidate overlap plus piece exceeds max."""
    from app.services.chunkers.hybrid import _compute_overlap

    overlap = _compute_overlap(
        accumulator=["abcde"],
        separator=" ",
        chunk_overlap=10,
        new_piece="x" * 18,
        max_chunk_size=20,
    )
    assert overlap == []
