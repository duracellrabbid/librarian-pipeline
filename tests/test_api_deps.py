"""Unit tests for API dependency injection helpers in app/api/deps.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.api.deps import (
    get_db,
    get_dispatcher,
    get_vector_store,
    reset_dependencies,
    set_default_dispatcher,
    set_default_vector_store,
)
from app.core.dispatcher import TaskDispatcher
from app.services.vector_store.qdrant import QdrantVectorStore
from app.workers.dispatcher import ArqTaskDispatcher
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def clean_dependencies() -> None:
    """Reset global dependencies before and after each test."""
    reset_dependencies()
    yield
    reset_dependencies()


class TestGetDbDependency:
    """Tests for get_db async session dependency."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self) -> None:
        mock_session = AsyncMock(spec=AsyncSession)

        async def mock_async_session_gen():
            yield mock_session

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.api.deps.get_async_session", mock_async_session_gen)
            gen = get_db()
            session = await anext(gen)
            assert session is mock_session
            with pytest.raises(StopAsyncIteration):
                await anext(gen)


class TestGetDispatcherDependency:
    """Tests for get_dispatcher dependency helper."""

    def test_get_dispatcher_default(self) -> None:
        dispatcher = get_dispatcher()
        assert isinstance(dispatcher, ArqTaskDispatcher)

    def test_get_dispatcher_from_request_app_state(self) -> None:
        mock_dispatcher = MagicMock(spec=TaskDispatcher)
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.dispatcher = mock_dispatcher

        resolved = get_dispatcher(request=mock_request)
        assert resolved is mock_dispatcher

    def test_get_dispatcher_request_without_app_state(self) -> None:
        mock_request = MagicMock(spec=Request)
        # Mock request with empty state
        del mock_request.app.state.dispatcher
        resolved = get_dispatcher(request=mock_request)
        assert isinstance(resolved, ArqTaskDispatcher)

    def test_set_default_dispatcher(self) -> None:
        custom_dispatcher = MagicMock(spec=TaskDispatcher)
        set_default_dispatcher(custom_dispatcher)
        assert get_dispatcher() is custom_dispatcher


class TestGetVectorStoreDependency:
    """Tests for get_vector_store dependency helper."""

    def test_get_vector_store_default(self) -> None:
        store = get_vector_store()
        assert isinstance(store, QdrantVectorStore)

    def test_get_vector_store_from_request_app_state(self) -> None:
        mock_store = MagicMock(spec=QdrantVectorStore)
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.vector_store = mock_store

        resolved = get_vector_store(request=mock_request)
        assert resolved is mock_store

    def test_get_vector_store_request_without_app_state(self) -> None:
        mock_request = MagicMock(spec=Request)
        del mock_request.app.state.vector_store
        resolved = get_vector_store(request=mock_request)
        assert isinstance(resolved, QdrantVectorStore)

    def test_set_default_vector_store(self) -> None:
        custom_store = MagicMock(spec=QdrantVectorStore)
        set_default_vector_store(custom_store)
        assert get_vector_store() is custom_store
