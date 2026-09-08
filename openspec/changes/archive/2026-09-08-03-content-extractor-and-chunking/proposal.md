## Why

High-quality RAG retrieval depends directly on clean content extraction and structure-aware chunking. For Wikipedia and web pages, standard naive fixed-size chunking destroys section hierarchy, sentence flow, and contextual meaning. We need an extensible extractor abstraction backed by Crawl4AI, paired with a hybrid Markdown chunker that preserves heading paths and enforces manageable chunk sizes for embedding.

## What Changes

- Create `BaseExtractor` protocol to provide a unified interface for future document formats (PDF, plain text).
- Implement `Crawl4AIExtractor` using Crawl4AI's `AsyncWebCrawler`:
  - Configured for Wikipedia: removes navigational chrome, edit links, citation footers, and infobox clutter.
  - Returns normalized `ExtractedDocument` with title, raw markdown, and source URL metadata.
- Implement `HybridMarkdownChunker`:
  - Splits markdown content along heading boundaries (`#`, `##`, `###`).
  - Prepend/inject hierarchical breadcrumb metadata into each chunk (e.g. `Section: Early life > Education`).
  - Recursively splits oversized sections using a configurable token/character window with overlap.
- Add unit tests validating extraction and chunking against Wikipedia markdown samples.

## Capabilities

### New Capabilities
- `content-extraction`: Unified extractor interface and Crawl4AI implementation for web/Wikipedia content extraction.
- `markdown-chunking`: Context-aware hybrid markdown splitting preserving heading hierarchies and chunk size limits.

### Modified Capabilities
<!-- None -->

## Impact

- Prepares normalized, structured chunks ready for embedding and vectorization.
- Completely decouples extraction and chunking logic from queue and database concerns.
