"""Tests for async database engine and session dependency."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import text


def test_engine_creation():
    """Verify async engine is created and configured as AsyncEngine."""
    from app.core.db import engine, get_engine

    assert isinstance(engine, AsyncEngine)
    active_engine = get_engine()
    assert isinstance(active_engine, AsyncEngine)
    assert active_engine is engine


@pytest.mark.asyncio
async def test_session_factory():
    """Verify async_session_factory creates an AsyncSession instance."""
    from app.core.db import async_session_factory

    async with async_session_factory() as session:
        assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_get_async_session_yields_session():
    """Verify get_async_session yields an AsyncSession and closes cleanly."""
    from app.core.db import get_async_session

    session_generator = get_async_session()
    session = await anext(session_generator)
    assert isinstance(session, AsyncSession)

    # Session should be open
    assert session.is_active

    # Complete the generator
    with pytest.raises(StopAsyncIteration):
        await anext(session_generator)


@pytest.mark.asyncio
async def test_get_async_session_rollback_on_exception(monkeypatch):
    """Verify get_async_session rolls back when an unhandled exception occurs."""
    from app.core.db import get_async_session

    rolled_back = False

    original_rollback = AsyncSession.rollback

    async def fake_rollback(self: AsyncSession):
        nonlocal rolled_back
        rolled_back = True
        await original_rollback(self)

    monkeypatch.setattr(AsyncSession, "rollback", fake_rollback)

    session_gen = get_async_session()
    session = await anext(session_gen)
    assert isinstance(session, AsyncSession)

    with pytest.raises(RuntimeError, match="Test failure"):
        try:
            raise RuntimeError("Test failure")
        except Exception as exc:
            await session_gen.athrow(exc)

    assert rolled_back is True


@pytest.mark.asyncio
async def test_session_execute_query(monkeypatch):
    """Verify session can execute async query against test in-memory SQLite."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Use SQLite async for unit testing execution
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        scalar = result.scalar()
        assert scalar == 1

    await test_engine.dispose()
