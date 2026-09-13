"""English Wikipedia extraction strategy implementation."""

from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

from app.services.extractors.cleaning import clean_markdown

DEFAULT_WIKIPEDIA_EXCLUDED_TAGS: list[str] = [
    "nav",
    "footer",
    "header",
]

DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR: str = (
    ".vector-header, .vector-sidebar, #mw-navigation, .reference, .reflist, .mw-editsection, .infobox, table.infobox"
)


class WikipediaExtractionStrategy:
    """Extraction strategy tailored for Wikipedia content and page structures."""

    domain_prefix: str = "https://en.wikipedia.org"

    def __init__(
        self,
        *,
        excluded_tags: list[str] | None = None,
        excluded_selector: str | None = None,
        headless: bool = True,
    ) -> None:
        """Initialize WikipediaExtractionStrategy with default or customized selectors."""
        self.excluded_tags = excluded_tags if excluded_tags is not None else list(DEFAULT_WIKIPEDIA_EXCLUDED_TAGS)
        self.excluded_selector = (
            excluded_selector if excluded_selector is not None else DEFAULT_WIKIPEDIA_EXCLUDED_SELECTOR
        )
        self.headless = headless

    def get_run_config(self) -> CrawlerRunConfig:
        """Return Crawl4AI run configuration with Wikipedia excluded tags and selectors."""
        return CrawlerRunConfig(
            excluded_tags=self.excluded_tags,
            excluded_selector=self.excluded_selector,
        )

    def get_browser_config(self) -> BrowserConfig:
        """Return Crawl4AI browser configuration."""
        return BrowserConfig(headless=self.headless, verbose=False)

    def clean(self, markdown: str) -> str:
        """Sanitize Wikipedia edit links, citation markers, and excess whitespace."""
        return clean_markdown(markdown)
