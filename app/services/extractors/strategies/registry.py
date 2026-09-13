"""Registry for domain-specific extraction strategies."""

from collections.abc import Sequence
from functools import lru_cache
from urllib.parse import urlsplit

from app.core.exceptions import ExtractionError
from app.core.security import _matches_domain
from app.services.extractors.strategies.base import DomainExtractionStrategy
from app.services.extractors.strategies.wikipedia import WikipediaExtractionStrategy


class ExtractionStrategyRegistry:
    """Registry mapping domain prefixes to concrete extraction strategies."""

    def __init__(self, strategies: Sequence[DomainExtractionStrategy] | None = None) -> None:
        """Initialize registry with optional strategies, defaulting to Wikipedia strategy."""
        self._strategies: list[DomainExtractionStrategy] = []
        if strategies is not None:
            for strategy in strategies:
                self.register(strategy)
        else:
            self.register(WikipediaExtractionStrategy())

    def register(self, strategy: DomainExtractionStrategy) -> None:
        """Register a domain extraction strategy."""
        # Replace existing strategy if same prefix is registered
        self._strategies = [
            s for s in self._strategies if s.domain_prefix.rstrip("/") != strategy.domain_prefix.rstrip("/")
        ]
        self._strategies.append(strategy)

    def find_strategy(self, url: str) -> DomainExtractionStrategy | None:
        """Find matching strategy for a target URL, or return None if unmapped."""
        if not isinstance(url, str) or not url.strip():
            return None

        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return None

        if not parsed.scheme or not parsed.hostname:
            return None

        for strategy in self._strategies:
            if _matches_domain(parsed, strategy.domain_prefix):
                return strategy

        return None

    def get_strategy(self, url: str) -> DomainExtractionStrategy:
        """Resolve extraction strategy for target URL, raising ExtractionError if unmapped."""
        strategy = self.find_strategy(url)
        if strategy is None:
            raise ExtractionError(
                f"No extraction strategy registered for domain: '{url}'",
                url=url,
            )
        return strategy


@lru_cache
def get_default_strategy_registry() -> ExtractionStrategyRegistry:
    """Return a cached default singleton instance of ExtractionStrategyRegistry."""
    return ExtractionStrategyRegistry()
