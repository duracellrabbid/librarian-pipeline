## 1. Extractor Abstraction & Web Extractor Implementation

- [x] 1.1 Define `ExtractedDocument` model and `BaseExtractor` protocol in `app/services/extractors/base.py`.
- [x] 1.2 Define `ExtractionError` domain exception in `app/core/exceptions.py`.
- [x] 1.3 Implement `Crawl4AIExtractor` in `app/services/extractors/web.py` using `crawl4ai.AsyncWebCrawler` with Wikipedia boilerplate exclusion selectors.
- [x] 1.4 Implement markdown cleaning helpers to sanitize excess blank lines, edit links (`[edit]`), and citation markers (`[1]`).
- [x] 1.5 Write unit tests in `tests/test_extractors.py` for `Crawl4AIExtractor` verifying successful extraction, metadata normalization, and error handling using mocked crawl results.


## 2. Hybrid Markdown Chunker Implementation

- [x] 2.1 Define `DocumentChunk` model and `BaseChunker` protocol in `app/services/chunkers/base.py`.
- [x] 2.2 Implement heading parser in `app/services/chunkers/hybrid.py` to identify `#`, `##`, `###` boundaries and construct breadcrumb hierarchies.
- [x] 2.3 Implement recursive text splitting utility in `app/services/chunkers/hybrid.py` with configurable chunk size and overlap bounds.
- [x] 2.4 Implement `HybridMarkdownChunker` coordinating heading segmentation, recursive splitting of oversized sections, and breadcrumb metadata injection.
- [x] 2.5 Write unit tests in `tests/test_chunkers.py` verifying heading tree preservation, breadcrumb attachment, recursive splitting on oversized inputs, and documents without headings.


## 3. Integration & Documentation

- [x] 3.1 Write an integration test connecting extractor output directly to the chunker using a representative Wikipedia article sample.
- [x] 3.2 Update `README.md` to describe the extractor and chunker architecture, components, and configuration settings.

