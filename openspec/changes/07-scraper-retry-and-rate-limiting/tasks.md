## 1. Scraper Configuration & Settings

- [x] 1.1 Write unit tests in `tests/test_config.py` for scraper configuration fields (`scraper_max_retries`, `scraper_backoff_factor`, `scraper_max_retry_delay`, `scraper_max_concurrency_per_domain`, `scraper_page_timeout`, `scraper_user_agent`).
- [x] 1.2 Implement scraper configuration fields in `app/core/config.py` with validation and update `.env.example`.

## 2. In-Process Domain Concurrency Limiter

- [x] 2.1 Write unit tests in `tests/test_rate_limiter.py` verifying `InProcessDomainRateLimiter` per-domain concurrency gating, independent domain isolation, and semaphore acquisition/release lifecycle.
- [x] 2.2 Implement `InProcessDomainRateLimiter` in `app/services/extractors/limiter.py` with domain extraction and semaphore management.

## 3. Scraper Retry, Jitter, and User-Agent

- [x] 3.1 Write unit tests in `tests/test_extractors.py` verifying retry sequences on 429 and 5xx, timeout retries, fast failure on 4xx, `Retry-After` parsing and cap enforcement, and User-Agent header and warning behavior.
- [x] 3.2 Update `WikipediaExtractionStrategy` and `Crawl4AIExtractor` in `app/services/extractors/web.py` to support `InProcessDomainRateLimiter`, exponential backoff with jitter, `Retry-After` parsing with fail-fast cap, page timeouts, and polite User-Agent headers.

## 4. Worker & Pipeline Integration

- [x] 4.1 Update `app/workers/tasks.py` `startup` to instantiate `InProcessDomainRateLimiter` in worker `ctx["rate_limiter"]` and pass it into `IngestionPipelineService` and `Crawl4AIExtractor`.
- [x] 4.2 Write unit and integration tests in `tests/test_worker_tasks.py` and `tests/test_pipeline.py` verifying worker context rate limiter injection and end-to-end extraction retry handling.

## 5. Verification & Documentation

- [x] 5.1 Run linting and full test suite with 100% statement coverage (`ruff check .`, `ruff format --check .`, `pytest --cov=app --cov-fail-under=100`).
- [x] 5.2 Update `README.md` to document the new scraper retry parameters, rate limiting mechanics, and Wikipedia User-Agent policy.
