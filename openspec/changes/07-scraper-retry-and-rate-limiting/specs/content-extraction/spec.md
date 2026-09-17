## MODIFIED Requirements

### Requirement: Crawl4AI Web Content Extractor
The system SHALL implement a web extractor using Crawl4AI (`AsyncWebCrawler`) capable of fetching web content and rendering clean Markdown using domain-specific extraction strategies, resiliently retrying transient failures with exponential backoff, randomized jitter, and `Retry-After` header adherence.

#### Scenario: Wikipedia article extraction
- **WHEN** a valid Wikipedia URL is provided to the web extractor
- **THEN** it resolves the Wikipedia extraction strategy, asynchronously crawls the page using Wikipedia-specific exclusion filters, and returns clean Markdown content with the page title.

#### Scenario: Extraction retry on transient failure and eventual success
- **WHEN** crawling encounters a transient failure (HTTP status 429, 500, 502, 503, 504, or network timeout) and succeeds on a subsequent attempt within the configured retry limit
- **THEN** the extractor retries with exponential backoff plus randomized jitter and successfully returns the extracted document.

#### Scenario: Extraction retry exhaustion on persistent transient error
- **WHEN** crawling encounters persistent transient failures exceeding the configured maximum retry attempts
- **THEN** the extractor catches the failure and raises a typed `ExtractionError` including the source URL, final status code, and failure details.

#### Scenario: Fast failure on non-retriable client errors
- **WHEN** the target URL returns a non-retriable client error (HTTP 400, 401, 403, 404, or 422)
- **THEN** the extractor fails immediately without retrying and raises a typed `ExtractionError`.

#### Scenario: Rate limit with Retry-After header within cap
- **WHEN** the target URL returns HTTP 429 with a valid `Retry-After` header specifying a delay within the configured maximum retry delay cap
- **THEN** the extractor pauses for the specified `Retry-After` interval before executing the next retry attempt.

#### Scenario: Rate limit with Retry-After header exceeding cap
- **WHEN** the target URL returns HTTP 429 with a `Retry-After` header specifying a delay exceeding the configured maximum retry delay cap
- **THEN** the extractor immediately raises a typed `ExtractionError` indicating that the requested retry delay exceeds the allowable cap without waiting.

#### Scenario: Missing extraction strategy for allowed domain
- **WHEN** a target URL belongs to an allowed domain but lacks a registered extraction strategy
- **THEN** the extractor raises a typed `ExtractionError` indicating unsupported domain extraction strategy, and does not fall back to generic extraction.

## ADDED Requirements

### Requirement: In-Process Domain Concurrency Limiting
The system SHALL provide an in-process, domain-keyed concurrency limiter that constrains concurrent active crawl executions to any individual target domain.

#### Scenario: Concurrent crawling restricted per domain
- **WHEN** multiple concurrent crawl tasks target the same domain exceeding the configured per-domain concurrency limit
- **THEN** the rate limiter queues excess requests until an active crawl slot for that domain is released.

#### Scenario: Independent concurrency across distinct domains
- **WHEN** concurrent crawl tasks target distinct host domains
- **THEN** concurrency limits are evaluated independently per domain, preventing one domain's queue from blocking another.

### Requirement: Polite Crawling and User-Agent Identification
The system SHALL configure crawler browser sessions with a structured, identifiable `User-Agent` string complying with host bot policies, and log an operational warning if not explicitly configured in the environment.

#### Scenario: Custom User-Agent applied to crawler requests
- **WHEN** a custom `SCRAPER_USER_AGENT` is configured in the environment
- **THEN** the crawler run and browser configurations apply this User-Agent to outbound HTTP crawl requests.

#### Scenario: Warning emitted when User-Agent is not explicitly configured
- **WHEN** the scraper initializes without an explicitly customized `SCRAPER_USER_AGENT`
- **THEN** the system logs a warning indicating that the default User-Agent is being used and recommends setting a contact identifier.
