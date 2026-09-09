"""API dependency injection helpers for database sessions, task dispatching, and vector storage."""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_async_session
from app.core.dispatcher import TaskDispatcher
from app.services.vector_store.qdrant import QdrantVectorStore
from app.workers.dispatcher import ArqTaskDispatcher

_default_dispatcher: TaskDispatcher | None = None
_default_vector_store: QdrantVectorStore | None = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency yielding an active database AsyncSession."""
    async for session in get_async_session():
        yield session


def get_dispatcher(request: Request = None) -> TaskDispatcher:  # type: ignore[assignment]
    """Dependency resolving the TaskDispatcher instance."""
    if (
        request is not None
        and hasattr(request, "app")
        and hasattr(request.app, "state")
        and hasattr(request.app.state, "dispatcher")
        and request.app.state.dispatcher is not None
    ):
        return request.app.state.dispatcher

    global _default_dispatcher
    if _default_dispatcher is None:
        _default_dispatcher = ArqTaskDispatcher()
    return _default_dispatcher


def set_default_dispatcher(dispatcher: TaskDispatcher | None) -> None:
    """Set the fallback default dispatcher instance."""
    global _default_dispatcher
    _default_dispatcher = dispatcher


def get_vector_store(request: Request = None) -> QdrantVectorStore:  # type: ignore[assignment]
    """Dependency resolving the QdrantVectorStore instance."""
    if (
        request is not None
        and hasattr(request, "app")
        and hasattr(request.app, "state")
        and hasattr(request.app.state, "vector_store")
        and request.app.state.vector_store is not None
    ):
        return request.app.state.vector_store

    global _default_vector_store
    if _default_vector_store is None:
        _default_vector_store = QdrantVectorStore()
    return _default_vector_store


def set_default_vector_store(vector_store: QdrantVectorStore | None) -> None:
    """Set the fallback default vector store instance."""
    global _default_vector_store
    _default_vector_store = vector_store


def reset_dependencies() -> None:
    """Reset default cached singletons (useful for test isolation)."""
    global _default_dispatcher, _default_vector_store
    _default_dispatcher = None
    _default_vector_store = None
