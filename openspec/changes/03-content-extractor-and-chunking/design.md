## Context

See `proposal.md` for motivation. Phase 1 established project scaffolding and local backing services, and Phase 2 established the PostgreSQL schema and metadata repositories for `Document` and `IngestionJob`. In this phase, we implement the core data extraction and transformation engine: extracting clean Markdown from web URLs using Crawl4AI, and chunking that content hierarchically using a hybrid Markdown-aware chunking strategy.

## Goals / Non-Goals

**Goals:**
- Define a reusable, abstract `BaseExtractor` protocol and `ExtractedDocument` data model in `app/services/extractors/base.py`.
- Implement `Crawl4AIExtractor` in `app/services/extractors/web.py` using `crawl4ai.AsyncWebCrawler` with CSS selection, exclusion filters, and markdown sanitization tailored for Wikipedia and general web pages.
- Define a standardized `DocumentChunk` model representing chunk index, text, token count, and metadata.
- Implement `HybridMarkdownChunker` in `app/services/chunkers/hybrid.py` that parses heading trees, propagates breadcrumbs (`Section: H1 > H2 > H3`), and recursively splits oversized sections.
- Thorough unit tests verifying extraction mocking, error handling, heading hierarchy splitting, and recursive chunk sizing.

**Non-Goals:**
- Embedding generation or calling Ollama (deferred to Phase 4).
- Vector indexing in Qdrant (deferred to Phase 4).
- Background queue / ARQ worker execution (deferred to Phase 5).
- Exposing HTTP endpoints for ingestion (deferred to Phase 6).

## Decisions

### Decision: Protocol-Based `BaseExtractor` Interface
- **Rationale**: Using Python `typing.Protocol` or `abc.ABC` allows future extractors (e.g. `PDFExtractor`, `TextExtractor`) to be implemented as drop-in components without altering downstream pipeline or chunking code.
- **Alternatives considered**: Concrete class inheritance without explicit interface (less extensible, harder to mock in unit tests).

### Decision: `AsyncWebCrawler` Configuration for Wikipedia
- **Rationale**: Crawl4AI provides headless Playwright browsing with rich markdown extraction. For Wikipedia, we configure crawl options to exclude standard boilerplate selectors:
  - Excluded tags: `nav`, `footer`, `header`, `.vector-header`, `.vector-sidebar`, `#mw-navigation`, `.reference`, `.reflist`, `.mw-editsection`.
  - Extracted metadata: page title, canonical URL, language, and crawl timestamp.
- **Alternatives considered**: Raw `httpx` + `BeautifulSoup` (faster for static pages, but cannot handle dynamic DOM rendering or modern web apps that future extractors will target).

### Decision: Hybrid Heading-Aware + Recursive Splitting
- **Rationale**: Naive token chunking breaks sentences and loses all section context. By first partitioning along `#`, `##`, and `###` headers, each chunk stays semantically bounded to a topic. Prepending `[Context: Breadcrumb]` to the chunk text ensures vector embeddings capture the topic context even when a paragraph doesn't explicitly mention the entity name.
- **Sizing Strategy**:
  - Max chunk size: ~800 tokens (~3200 characters).
  - Overlap: ~100 tokens (~400 characters).
  - Oversized sections are recursively split by double newlines (`\n\n`), single newlines (`\n`), and spaces (` `).

## Risks / Trade-offs

- **[Risk] Playwright Browser Resource Usage**: Launching browser instances repeatedly can be slow or consume excess memory.
  - *Mitigation*: Configure `Crawl4AIExtractor` with sensible browser launch options (headless mode, disabled sandbox in containerized environments, reused browser contexts).
- **[Risk] Markdown Format Inconsistencies**: Some web pages have irregular heading structures (e.g., jumping from `h1` directly to `h3`, or no headings at all).
  - *Mitigation*: The chunker will gracefully handle missing parent levels and fall back to pure recursive paragraph/sentence chunking when headings are absent.
