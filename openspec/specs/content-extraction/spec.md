# content-extraction Specification

## Purpose
Defines a standardized content extraction interface and web crawler implementation to extract structured text, titles, and metadata from web pages.
## Requirements
### Requirement: Standard Content Extractor Protocol
The system SHALL provide an extensible extractor protocol (`BaseExtractor`) returning a normalized `ExtractedDocument` containing text content, title, source URL, and metadata dictionary.

#### Scenario: Unified extraction interface
- **WHEN** any concrete extractor executes extraction on a target source
- **THEN** it returns an `ExtractedDocument` instance containing `content`, `title`, `source_url`, and `metadata`.

### Requirement: Crawl4AI Web Content Extractor
The system SHALL implement a web extractor using Crawl4AI (`AsyncWebCrawler`) capable of fetching web content and rendering clean Markdown.

#### Scenario: Wikipedia article extraction
- **WHEN** a valid Wikipedia URL is provided to the web extractor
- **THEN** it asynchronously crawls the page, strips navigational elements, infoboxes, and edit links, and returns clean Markdown content with the page title.

#### Scenario: Extraction timeout or network failure
- **WHEN** the target URL fails to respond or encounters a non-2xx HTTP status code
- **THEN** the extractor catches the failure and raises a typed `ExtractionError` with failure details.

### Requirement: Content Cleaning and Normalization
The extractor SHALL sanitize raw crawled Markdown to eliminate redundant whitespace, empty headings, and excessive link references.

#### Scenario: Markdown sanitization
- **WHEN** crawled Markdown contains repeated blank lines or trailing reference syntax
- **THEN** the extractor normalizes whitespace and removes trailing Wikipedia reference citations (e.g. `[1]`, `[2]`).

