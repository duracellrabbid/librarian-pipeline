"""Unit tests for InProcessDomainRateLimiter."""

import asyncio

import pytest
from app.services.extractors.limiter import InProcessDomainRateLimiter


def test_limiter_initialization_invalid_concurrency():
    """Verify ValueError is raised if max_concurrency is less than 1."""
    with pytest.raises(ValueError, match="max_concurrency must be at least 1"):
        InProcessDomainRateLimiter(max_concurrency=0)


def test_extract_domain():
    """Verify domain extraction from various URL formats."""
    limiter = InProcessDomainRateLimiter(max_concurrency=2)
    assert limiter.extract_domain("https://en.wikipedia.org/wiki/Python") == "en.wikipedia.org"
    assert limiter.extract_domain("http://localhost:8000/api/v1") == "localhost:8000"
    assert limiter.extract_domain("https://EXAMPLE.org/path?query=1") == "example.org"
    assert limiter.extract_domain("en.wikipedia.org") == "en.wikipedia.org"
    assert limiter.extract_domain("") == ""


@pytest.mark.asyncio
async def test_per_domain_concurrency_gating():
    """Verify that concurrent tasks on the same domain are throttled to max_concurrency."""
    limiter = InProcessDomainRateLimiter(max_concurrency=2)
    active_count = 0
    max_observed_active = 0
    completed = []

    async def worker(task_id: int):
        nonlocal active_count, max_observed_active
        async with limiter.acquire("https://en.wikipedia.org/wiki/Item"):
            active_count += 1
            if active_count > max_observed_active:
                max_observed_active = active_count
            await asyncio.sleep(0.05)
            active_count -= 1
        completed.append(task_id)

    tasks = [asyncio.create_task(worker(i)) for i in range(5)]
    await asyncio.gather(*tasks)

    assert len(completed) == 5
    assert max_observed_active == 2


@pytest.mark.asyncio
async def test_independent_domain_isolation():
    """Verify that tasks targeting different domains execute concurrently without blocking each other."""
    limiter = InProcessDomainRateLimiter(max_concurrency=1)
    concurrent_domains = set()
    observed_multi_domain = False

    async def worker(url: str, domain_label: str):
        nonlocal observed_multi_domain
        async with limiter.acquire(url):
            concurrent_domains.add(domain_label)
            if len(concurrent_domains) == 2:
                observed_multi_domain = True
            await asyncio.sleep(0.05)
            concurrent_domains.remove(domain_label)

    t1 = asyncio.create_task(worker("https://en.wikipedia.org/wiki/1", "wiki"))
    t2 = asyncio.create_task(worker("https://other-domain.org/doc", "other"))
    await asyncio.gather(t1, t2)

    assert observed_multi_domain is True


@pytest.mark.asyncio
async def test_semaphore_release_on_exception():
    """Verify that semaphore is released even if an exception occurs inside the context block."""
    limiter = InProcessDomainRateLimiter(max_concurrency=1)

    with pytest.raises(RuntimeError, match="Simulated crash"):
        async with limiter.acquire("https://en.wikipedia.org"):
            raise RuntimeError("Simulated crash")

    acquired_after = False
    async with limiter.acquire("https://en.wikipedia.org"):
        acquired_after = True

    assert acquired_after is True
