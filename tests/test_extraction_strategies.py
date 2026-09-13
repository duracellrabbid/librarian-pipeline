"""Unit tests for domain extraction strategies and strategy registry."""

import pytest
from app.core.exceptions import ExtractionError
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
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig


class DummyCustomStrategy:
    """Mock strategy for testing registry dispatch."""

    domain_prefix = "https://custom-docs.org"

    def get_run_config(self) -> CrawlerRunConfig:
        return CrawlerRunConfig(excluded_tags=["aside"])

    def get_browser_config(self) -> BrowserConfig:
        return BrowserConfig(headless=True)

    def clean(self, markdown: str) -> str:
        return markdown.replace("CUSTOM_TAG", "").strip()


class IncompleteStrategy:
    """Dummy class missing required protocol methods."""

    domain_prefix = "https://incomplete.org"


class TestDomainExtractionStrategyProtocol:
    """Tests verifying DomainExtractionStrategy protocol conformance."""

    def test_wikipedia_strategy_conforms_to_protocol(self) -> None:
        strategy = WikipediaExtractionStrategy()
        assert isinstance(strategy, DomainExtractionStrategy)

    def test_custom_strategy_conforms_to_protocol(self) -> None:
        strategy = DummyCustomStrategy()
        assert isinstance(strategy, DomainExtractionStrategy)

    def test_incomplete_strategy_fails_protocol_check(self) -> None:
        strategy = IncompleteStrategy()
        assert not isinstance(strategy, DomainExtractionStrategy)


class TestWikipediaExtractionStrategy:
    """Tests verifying WikipediaExtractionStrategy properties and behavior."""

    def test_domain_prefix(self) -> None:
        strategy = WikipediaExtractionStrategy()
        assert strategy.domain_prefix == "https://en.wikipedia.org"

    def test_get_run_config(self) -> None:
        strategy = WikipediaExtractionStrategy()
        config = strategy.get_run_config()
        assert isinstance(config, CrawlerRunConfig)
        assert config.excluded_tags == DEFAULT_WIKIPEDIA_EXCLUDED_TAGS
        assert config.excluded_selector == DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR

    def test_get_browser_config(self) -> None:
        strategy = WikipediaExtractionStrategy()
        config = strategy.get_browser_config()
        assert isinstance(config, BrowserConfig)
        assert config.headless is True

    def test_clean_markdown(self) -> None:
        strategy = WikipediaExtractionStrategy()
        raw = "# Alan Turing [edit]\n\nTuring was a mathematician[1].\n\n\n\nNext line."
        cleaned = strategy.clean(raw)
        assert "[edit]" not in cleaned
        assert "[1]" not in cleaned
        assert "\n\n\n" not in cleaned
        assert "Turing was a mathematician." in cleaned


class TestExtractionStrategyRegistry:
    """Tests verifying ExtractionStrategyRegistry registration and resolution."""

    def test_default_registry_contains_wikipedia_strategy(self) -> None:
        registry = ExtractionStrategyRegistry()
        strategy = registry.get_strategy("https://en.wikipedia.org/wiki/Python")
        assert isinstance(strategy, WikipediaExtractionStrategy)

    def test_get_default_strategy_registry_singleton(self) -> None:
        r1 = get_default_strategy_registry()
        r2 = get_default_strategy_registry()
        assert r1 is r2
        assert isinstance(r1.get_strategy("https://en.wikipedia.org/wiki/Test"), WikipediaExtractionStrategy)

    def test_register_and_resolve_custom_strategy(self) -> None:
        registry = ExtractionStrategyRegistry()
        custom = DummyCustomStrategy()
        registry.register(custom)

        resolved = registry.get_strategy("https://custom-docs.org/guide/intro")
        assert resolved is custom

    def test_find_strategy_returns_none_when_not_found(self) -> None:
        registry = ExtractionStrategyRegistry()
        assert registry.find_strategy("https://unregistered-domain.com/page") is None

    def test_get_strategy_raises_extraction_error_when_unmapped(self) -> None:
        registry = ExtractionStrategyRegistry()
        url = "https://unregistered-domain.com/page"
        with pytest.raises(ExtractionError) as exc_info:
            registry.get_strategy(url)

        assert exc_info.value.url == url
        assert "No extraction strategy registered" in str(exc_info.value)

    def test_registry_with_explicit_strategies_list(self) -> None:
        custom = DummyCustomStrategy()
        registry = ExtractionStrategyRegistry(strategies=[custom])
        assert registry.get_strategy("https://custom-docs.org/test") is custom
        with pytest.raises(ExtractionError):
            registry.get_strategy("https://en.wikipedia.org/wiki/Test")

    def test_trailing_slash_normalization_in_registration(self) -> None:
        class TrailingSlashStrategy(DummyCustomStrategy):
            domain_prefix = "https://trailing-slash.com/"

        registry = ExtractionStrategyRegistry(strategies=[TrailingSlashStrategy()])
        resolved = registry.get_strategy("https://trailing-slash.com/docs")
        assert resolved.domain_prefix == "https://trailing-slash.com/"

    def test_find_strategy_invalid_or_malformed_url_returns_none(self) -> None:
        registry = ExtractionStrategyRegistry()
        assert registry.find_strategy(None) is None  # type: ignore[arg-type]
        assert registry.find_strategy("") is None
        assert registry.find_strategy("   ") is None
        assert registry.find_strategy("http://[invalid-ipv6/") is None
        assert registry.find_strategy("not-a-url") is None
        assert registry.find_strategy("/just/a/path") is None
