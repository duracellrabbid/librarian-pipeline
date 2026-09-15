## Context

See `proposal.md` for motivation. Currently, `Crawl4AIExtractor` in `app/services/extractors/web.py` uses hardcoded Wikipedia selectors (`DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR`, `DEFAULT_WIKIPEDIA_EXCLUDED_TAGS`) for all crawls. The API layer in `app/api/v1/endpoints/documents.py` and `app/services/repository.py` accepts any arbitrary `HttpUrl` without validation, exposing the system to SSRF and extraction degradation on non-Wikipedia sites.

## Goals / Non-Goals

**Goals:**
- Provide tight full-URL allowlist validation in `Settings` (`allowed_domains = ["https://en.wikipedia.org"]`).
- Implement defense-in-depth: skip disallowed URLs at the API layer with reason `domain_not_allowed`, and fail fast at the worker pipeline level if an unallowed URL reaches execution.
- Implement `DomainExtractionStrategy` and `ExtractionStrategyRegistry` to isolate site-specific crawl configurations (selectors, excluded tags, cleaning rules).
- Enforce strict strategy availability: fail extraction if an allowed domain lacks a registered strategy.

**Non-Goals:**
- Dynamic or regex wildcard domain matching (e.g. `*.wikipedia.org` or `*`). Validation requires exact prefix matching against full URLs (e.g., `https://en.wikipedia.org`).
- Providing a generic/fallback crawler strategy. All extracted domains must have an explicit strategy.
- Automated CAPTCHA solving or authenticated crawling for restricted domains.

## Decisions

1. **Exact Full-URL Prefix Validation in Settings and Core Utility**
   - *Decision*: Define `allowed_domains: list[str] = ["https://en.wikipedia.org"]` in `app/core/config.py`. Provide a validation function `is_allowed_url(url: str, allowed_domains: list[str] | None = None) -> bool` in `app/core/security.py` (or `app/core/validation.py`).
   - *Rationale*: Exact prefix checking (normalized scheme and host) prevents SSRF vulnerabilities, DNS rebinding edge-cases, and attacker subdomains like `https://en.wikipedia.org.attacker.com`.
   - *Alternative considered*: Wildcard regexes (`*.wikipedia.org`). Rejected because wildcards increase attack surface and risk accidental ReDoS.

2. **Pre-flight Partitioning in Batch Registration**
   - *Decision*: In `app/services/repository.py` (`create_batch_and_jobs`), check each unique URL against `is_allowed_url`. If invalid, append to `skipped_items` with `reason="domain_not_allowed"` and omit from `accepted_pairs`.
   - *Rationale*: Aligns with the existing batch contract where duplicate or active URLs are gracefully skipped without failing valid sibling URLs in the batch.

3. **Defensive Validation in Worker Pipeline**
   - *Decision*: In `app/services/pipeline.py` (`_execute_pipeline`), assert `is_allowed_url(url)` prior to calling the extractor.
   - *Rationale*: Defense-in-depth. If a job is enqueued directly via CLI, task queue injection, or administrative tools, the worker refuses execution before triggering network I/O.

4. **Strategy Pattern for Domain Extractors**
   - *Decision*: Create `DomainExtractionStrategy` protocol and `ExtractionStrategyRegistry` in `app/services/extractors/strategies/`.
     - `WikipediaExtractionStrategy` implements the strategy for `https://en.wikipedia.org`.
     - `Crawl4AIExtractor` resolves the strategy from the registry for the target URL.
     - If no strategy exists for the domain, raise `ExtractionError("No extraction strategy registered for domain: ...")`.
   - *Rationale*: Clean separation of concerns. New domains (e.g., StackOverflow, Reddit) can be introduced by adding a strategy class and registering it without touching core crawler logic.

## Risks / Trade-offs

- **[Risk] Adding new allowed domains without strategies**: If an administrator adds a domain to `Settings.allowed_domains` without registering an extraction strategy, background jobs will fail during extraction.
  - *Mitigation*: The error is explicitly typed and recorded in the database job error message (`ExtractionError: No extraction strategy registered for domain ...`).
- **[Risk] URL scheme and trailing slash variations** (`http://` vs `https://`, trailing slashes):
  - *Mitigation*: URL normalization strips trailing slashes and validates normalized prefixes to ensure legitimate articles like `https://en.wikipedia.org/wiki/Python` match `https://en.wikipedia.org`.
