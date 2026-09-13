"""Domain extraction strategy abstractions and registry."""

from app.services.extractors.strategies.base import DomainExtractionStrategy
from app.services.extractors.strategies.registry import (
    ExtractionStrategyRegistry,
    get_default_strategy_registry,
)
from app.services.extractors.strategies.wikipedia import (
    DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR,
    DEFAULT_WIKIPEDIA_EXCLUDED_TAGS,
    WikipediaExtractionStrategy,
)

__all__ = [
    "DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR",
    "DEFAULT_WIKIPEDIA_EXCLUDED_TAGS",
    "DomainExtractionStrategy",
    "ExtractionStrategyRegistry",
    "WikipediaExtractionStrategy",
    "get_default_strategy_registry",
]
