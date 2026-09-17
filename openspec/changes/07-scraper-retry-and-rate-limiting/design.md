## Context

The system currently runs background ingestion jobs via an ARQ worker pool processing up to 10 jobs concurrently. Each job invokes `IngestionPipelineService.run`, which uses `Crawl4AIExtractor` to crawl web pages.

Currently:
- `Crawl4AIExtractor._crawl()` calls `crawler.arun()` once with no retry wrapper.
- Any transient HTTP error (429, 500, 502, 503, 504) or network timeout immediately fails the pipeline job.
- When batches of URLs targeting the same domain are ingested, parallel worker tasks hit the remote host simultaneously with no concurrency throttle or polite User-Agent headers.

See `proposal.md` and `specs/content-extraction/spec.md` for requirements and motivation.

## Goals / Non-Goals

**Goals:**
- Implement exponential backoff retry with randomized jitter inside `Crawl4AIExtractor` for transient errors.
- Support HTTP `Retry-After` header parsing with a fail-fast cap (`SCRAPER_MAX_RETRY_DELAY`).
- Differentiate retriable transient errors from non-retriable permanent errors (400, 401, 403, 404, 422).
- Build an in-process, domain-keyed concurrency limiter (`InProcessDomainRateLimiter`) using `asyncio.Semaphore`.
- Inject the limiter across ARQ worker jobs via worker `ctx` while providing a clean lazy default for standalone/test execution.
- Add configurable page timeout and Wikimedia-compliant User-Agent header settings.

**Non-Goals:**
- Distributed multi-node rate limiting via Redis (in-process per-worker concurrency limiter is sufficient for current architecture).
- Proxy rotation or CAPTCHA solving.
- Modifying vector storage, chunking, or embedding logic.

## Decisions

### Decision 1: Self-Contained Extractor Retry Loop
- **Approach**: Implement `_crawl_with_retry` within `Crawl4AIExtractor`. The retry loop computes backoff as:
  $$\text{delay} = \min(\text{backoff\_factor} \times 2^{\text{attempt}} + \text{random.uniform}(0, 1), \text{max\_retry\_delay})$$
- **Alternative considered**: ARQ job-level retries via `arq.Retry`.
- **Rationale**: Localized retry in the extractor is fast, avoids re-enqueuing and re-executing pipeline setup overhead, and keeps transient network resilience encapsulated where the external network I/O occurs.

### Decision 2: In-Process Domain Concurrency Limiter (`InProcessDomainRateLimiter`)
- **Approach**: Create `InProcessDomainRateLimiter` in `app/services/extractors/limiter.py` managing a dictionary of `asyncio.Semaphore(max_concurrency)` instances keyed by URL netloc/domain.
- **Alternative considered**: Global semaphore across all domains.
- **Rationale**: Per-domain scoping prevents high-latency crawling or rate-limiting on one domain from starving crawl requests to another allowed domain.

### Decision 3: Worker Context Injection with Lazy Fallback
- **Approach**:
  - In `app/workers/tasks.py:startup(ctx)`, instantiate `InProcessDomainRateLimiter` and store in `ctx["rate_limiter"]`.
  - In `run_ingestion_pipeline`, pass `rate_limiter` to `IngestionPipelineService(extractor=Crawl4AIExtractor(rate_limiter=...))`.
  - In `Crawl4AIExtractor.__init__`, if `rate_limiter is None`, initialize a default limiter so unit tests and independent invocations remain completely decoupled.
- **Rationale**: Preserves clean dependency injection, allows easy unit testing with mock limiters, and guarantees all concurrent tasks in an ARQ worker process share the same limiter.

### Decision 4: Retry-After Parsing & Fail-Fast Cap
- **Approach**: Inspect `response_headers` for `retry-after`. Parse both integer seconds and HTTP-date formats. If the required delay exceeds `SCRAPER_MAX_RETRY_DELAY`, immediately raise `ExtractionError` without waiting.
- **Alternative considered**: Clamping delay to cap and retrying anyway.
- **Rationale**: Retrying after 60s when a server requested 1 hour guarantees repeated 429s or an IP ban while wasting worker execution time.

### Decision 5: Configuration Settings in `Settings`
- Add to `app/core/config.py`:
  - `scraper_max_retries: int = Field(default=3, ge=0)`
  - `scraper_backoff_factor: float = Field(default=1.5, gt=0)`
  - `scraper_max_retry_delay: float = Field(default=60.0, gt=0)`
  - `scraper_max_concurrency_per_domain: int = Field(default=2, ge=1)`
  - `scraper_page_timeout: float = Field(default=30.0, gt=0)`
  - `scraper_user_agent: str | None = Field(default=None)`
- If `scraper_user_agent` is None or empty, log a warning on extractor initialization and use a compliant default (`RAG-Ingestion-Pipeline/0.1.0 (+https://github.com/duracellrabbid/librarian-pipeline; bot@example.com)`).

## Risks / Trade-offs

- **[Risk] Long Worker Hang on Large Retry Backoffs** → **Mitigation**: Cap total individual delay via `SCRAPER_MAX_RETRY_DELAY` (default 60s) and enforce page load timeouts (`SCRAPER_PAGE_TIMEOUT`).
- **[Risk] Memory Leak in Limiter Semaphores** → **Mitigation**: Domains are strictly validated against `allowed_domains` before extraction, bounding the maximum number of semaphores.
- **[Risk] Thundering Herd on Shared 429 Recovery** → **Mitigation**: Add randomized uniform jitter to every backoff interval.
