"""Embedding services package."""

from app.services.embeddings.base import BaseEmbeddingClient
from app.services.embeddings.ollama import OllamaEmbeddingClient

__all__ = ["BaseEmbeddingClient", "OllamaEmbeddingClient"]
