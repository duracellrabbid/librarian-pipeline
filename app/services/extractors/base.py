"""Extractor protocols and normalized extracted document models."""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ExtractedDocument(BaseModel):
    """Normalized document representation returned by extractors."""

    model_config = ConfigDict(frozen=True)

    content: str = Field(description="Extracted clean markdown or text content")
    title: str = Field(description="Document title")
    source_url: str = Field(description="Source URL or file path")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary source metadata (timestamps, language, headers, etc.)",
    )


@runtime_checkable
class BaseExtractor(Protocol):
    """Extensible extractor protocol returning a normalized ExtractedDocument."""

    async def extract(self, source: str) -> ExtractedDocument:
        """Extract content, title, and metadata from target source.

        Args:
            source: Source URL, URI, or file path.

        Returns:
            Normalized ExtractedDocument instance.

        Raises:
            ExtractionError: If extraction fails due to network, timeout, or parsing issues.
        """
        ...
