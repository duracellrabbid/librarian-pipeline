"""Alembic async environment configuration using SQLModel metadata and application settings."""

import asyncio
from logging.config import fileConfig

from alembic import context
from app.core.config import settings

# Import all models so that SQLModel.metadata detects their tables
from app.models import Document, IngestionJob, JobStatus  # noqa: F401
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def get_url() -> str:
    """Return database URL from alembic config or fallback to application settings."""
    url = config.get_main_option("sqlalchemy.url")
    if not url or url.startswith("driver://"):
        return settings.database_url
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations within a synchronous connection callback."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using an async engine connection."""
    url = get_url()
    if "+asyncpg" not in url and "+aiosqlite" not in url:
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("sqlite:///"):
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
