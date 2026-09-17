## Why

Currently, `Crawl4AIExtractor` executes a single, one-shot crawl attempt when fetching web content. Any transient error—such as HTTP 429 (Too Many Requests), HTTP 5xx server issues, or Playwright network timeouts—causes the ingestion pipeline to immediately fail the entire job. Furthermore, when processing batch ingestion requests, parallel background tasks hit remote host domains simultaneously without concurrency restrictions or polite User-Agent headers, leading to avoidable rate limit blocks and IP throttling.

## What Changes

- **Exponential Backoff Retry**: Introduce automated retry logic in `Crawl4AIExtractor` with configurable attempts (`SCRAPER_MAX_RETRIES`), exponential backoff (`SCRAPER_BACKOFF_FACTOR`), and randomized jitter to prevent the thundering herd problem.
- **Selective Retriable Error Handling**: Differentiate transient retriable errors (HTTP 429, 500, 502, 503, 504, network connection drops, timeouts) from permanent non-retriable client errors (HTTP 400, 401, 403, 404, 422, unmapped domains), failing fast on the latter.
- **`Retry-After` Header Handling with Cap**: Parse HTTP `Retry-After` headers on rate limits, respecting server-requested delays up to a configurable cap (`SCRAPER_MAX_RETRY_DELAY`), failing fast if the delay exceeds the cap.
- **In-Process Domain Concurrency Limiter**: Implement an in-memory, per-domain rate limiter (`InProcessDomainRateLimiter`) using `asyncio.Semaphore` to bound simultaneous crawl operations per host (`SCRAPER_MAX_CONCURRENCY_PER_DOMAIN`).
- **Configurable Page Timeout & User-Agent**: Add `SCRAPER_PAGE_TIMEOUT` to enforce timely crawler termination, and `SCRAPER_USER_AGENT` to comply with Wikimedia/bot policies, emitting a warning when unset.
- **Worker & Pipeline Integration**: Inject the shared limiter instance across worker tasks via ARQ worker execution context (`ctx["rate_limiter"]`).

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `content-extraction`: Expand extraction requirements to mandate retry with exponential backoff and jitter for transient errors (429, 5xx, timeouts), `Retry-After` support with cap enforcement, in-process per-domain concurrency limiting, and Wikimedia-compliant User-Agent identification.

## Impact

- **Configuration (`app/core/config.py`, `.env.example`, `README.md`)**: New scraper settings for retries, backoff, retry delay cap, per-domain concurrency, page timeout, and user agent.
- **Extraction Services (`app/services/extractors/`)**: Enhanced `Crawl4AIExtractor` with retry loop, new `InProcessDomainRateLimiter` class, and updated extraction strategies.
- **Worker Lifecycle (`app/workers/tasks.py`)**: Rate limiter initialized in worker `startup` context and injected into `IngestionPipelineService`.
- **Test Suite (`tests/test_extractors.py`, `tests/test_pipeline.py`)**: Comprehensive unit and integration tests covering retry sequences, backoff jitter, `Retry-After` limits, concurrency gating, and non-retriable failure fast paths.
