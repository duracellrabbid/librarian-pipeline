## 1. Domain Configuration and Security Validation

- [ ] 1.1 Add failing unit tests in `tests/test_domain_validation.py` for `is_allowed_url` verifying exact full-URL prefix matching against allowed domains and rejection of subdomains/SSRF targets.
- [ ] 1.2 Add `allowed_domains: list[str] = Field(default_factory=lambda: ["https://en.wikipedia.org"])` to `Settings` in [app/core/config.py](file:///D:/Shared/rag-ingestion-pipeline/app/core/config.py#L25-L30).
- [ ] 1.3 Implement `is_allowed_url(url: str, allowed_domains: list[str] | None = None) -> bool` in `app/core/security.py` and verify tests pass.
- [ ] 1.4 Add failing unit tests in `tests/test_documents_endpoints.py` and `tests/test_repository.py` verifying that batch submission skips URLs with unallowed domains using reason `domain_not_allowed`.
- [ ] 1.5 Update `create_batch_and_jobs` in [app/services/repository.py](file:///D:/Shared/rag-ingestion-pipeline/app/services/repository.py#L113-L125) to check `is_allowed_url` and record `SkippedDocumentItem(url=url_str, reason="domain_not_allowed")`.

## 2. Domain Extraction Strategy Pattern

- [ ] 2.1 Add failing unit tests in `tests/test_extraction_strategies.py` verifying the strategy protocol, `WikipediaExtractionStrategy`, registry strategy lookup, and error raising when no strategy matches an allowed domain.
- [ ] 2.2 Create `app/services/extractors/strategies/base.py` defining the `DomainExtractionStrategy` protocol (`domain_prefix`, `get_run_config()`, `get_browser_config()`, `clean()`).
- [ ] 2.3 Create `app/services/extractors/strategies/wikipedia.py` implementing `WikipediaExtractionStrategy` extracting the constants from [app/services/extractors/web.py](file:///D:/Shared/rag-ingestion-pipeline/app/services/extractors/web.py#L14-L24).
- [ ] 2.4 Create `app/services/extractors/strategies/registry.py` implementing `ExtractionStrategyRegistry` to register and resolve strategies by domain prefix, raising `ExtractionError` when no strategy is found.
- [ ] 2.5 Refactor `Crawl4AIExtractor` in [app/services/extractors/web.py](file:///D:/Shared/rag-ingestion-pipeline/app/services/extractors/web.py#L28-L86) to resolve strategy from registry and execute crawl with the strategy's configuration.

## 3. Worker Defense-in-Depth and Pipeline Verification

- [ ] 3.1 Add failing unit tests in `tests/test_pipeline_service.py` asserting that `IngestionPipelineService.run` rejects unallowed URLs before invoking extraction.
- [ ] 3.2 Update `_execute_pipeline` in [app/services/pipeline.py](file:///D:/Shared/rag-ingestion-pipeline/app/services/pipeline.py#L152-L160) to validate `is_allowed_url(url)` and raise `ExtractionError` on violation.
- [ ] 3.3 Run `ruff check .` and `pytest --cov=app --cov-fail-under=100` to verify full test suite passes with 100% coverage.
