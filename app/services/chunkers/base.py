"""Base models and protocols for document chunking."""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.extractors.base import ExtractedDocument


class DocumentChunk(BaseModel):
    """Standardized document chunk entity."""

    model_config = ConfigDict(frozen=True)

    chunk_index: int = Field(ge=0, description="Zero-based sequence index of the chunk")
    text: str = Field(min_length=1, description="Text content of the chunk")
    char_count: int = Field(default=0, ge=0, description="Character count of chunk text")
    token_count: int = Field(default=0, ge=0, description="Estimated token count of chunk text")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Section breadcrumbs and source metadata",
    )

    @model_validator(mode="before")
    @classmethod
    def _populate_counts(cls, data: Any) -> Any:
        """Automatically populate char_count and token_count if not explicitly provided."""
        if isinstance(data, dict):
            text = data.get("text")
            if isinstance(text, str) and text:
                if not data.get("char_count"):
                    data["char_count"] = len(text)
                if not data.get("token_count"):
                    data["token_count"] = max(1, len(text) // 4)
        return data


@runtime_checkable
class BaseChunker(Protocol):
    """Protocol defining document chunking interface."""

    def chunk(
        self,
        document: ExtractedDocument | str,
        metadata: dict[str, Any] | None = None,
    ) -> list[DocumentChunk]:
        """Split extracted document or raw text into standardized DocumentChunk objects.

        Args:
            document: ExtractedDocument instance or raw text string.
            metadata: Optional additional metadata to merge into chunk metadata.

        Returns:
            List of DocumentChunk instances with monotonically increasing chunk_index.
        """
        ...
