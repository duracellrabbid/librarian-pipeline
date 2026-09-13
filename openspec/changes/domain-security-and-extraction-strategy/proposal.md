## Why

Currently, the web crawler configuration in `Crawl4AIExtractor` unconditionally applies Wikipedia-specific exclusion tags and selectors to all incoming URLs. Furthermore, any arbitrary HTTP URL is accepted by the ingestion endpoint without domain validation, creating security risks (such as SSRF attacks against internal network targets or untrusted adversarial payloads) and extraction failures when scraping non-Wikipedia sites. Restricting ingestion to an explicit full-URL allowlist and routing crawling through domain-specific extraction strategies ensures secure, extensible, and high-fidelity content extraction.

## What Changes

- Add configurable `allowed_domains` to application settings with an initial hardcoded strict allowlist entry: `https://en.wikipedia.org` (strict full-URL base matching, no wildcard matching).
- Enforce domain validation at the API boundary in `POST /documents/ingest`: any URL not matching the allowlist is skipped with reason `domain_not_allowed` while allowing valid URLs in the batch to proceed.
- Enforce domain validation at the background worker / pipeline level (defense-in-depth): if an unallowed URL reaches the extraction pipeline, extraction immediately fails with a descriptive error.
- Refactor web extraction to use a Strategy pattern (`DomainExtractionStrategy`):
  - Introduce `WikipediaExtractionStrategy` encapsulating Wikipedia selectors and tags.
  - Implement a strategy resolver that maps allowed URLs to their domain extraction strategy.
  - Fail extraction explicitly if a domain is allowed but has no matching strategy registered (generic extraction fallback is disallowed).

## Capabilities

### Modified Capabilities
- `document-ingestion-api`: Add domain allowlist pre-flight check in batch ingestion, recording `domain_not_allowed` in skipped details.
- `content-extraction`: Introduce `DomainExtractionStrategy` protocol, `WikipediaExtractionStrategy`, registry dispatching, and strict rejection for unmapped domains.
- `ingestion-pipeline-service`: Add defensive worker-level allowlist validation before invoking extraction.

## Impact

- **Settings / Config**: Added `allowed_domains: list[str] = ["https://en.wikipedia.org"]` to `app/core/config.py`.
- **API & Schemas**: `POST /documents/ingest` and repository `create_batch_and_jobs` check URLs against allowed domain prefixes and add `domain_not_allowed` to `SkippedDocumentItem`.
- **Extractors**: `app/services/extractors/` introduces domain strategy abstractions and registry. `Crawl4AIExtractor` delegates configuration and extraction to matched domain strategies.
- **Workers / Pipeline**: `app/services/pipeline.py` adds worker-level URL validation prior to extraction.
