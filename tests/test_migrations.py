"""Tests for Alembic database migration upgrade and downgrade cycles."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import settings
from sqlalchemy import inspect
from sqlalchemy.engine import create_engine


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provide a path for an isolated temporary test SQLite database file."""
    return tmp_path / "test_migration.db"


@pytest.fixture
def alembic_cfg(temp_db_path: Path) -> Config:
    """Create Alembic configuration targeting an isolated temporary database."""
    cfg = Config("alembic.ini")
    db_uri = f"sqlite+aiosqlite:///{temp_db_path.as_posix()}"
    cfg.set_main_option("sqlalchemy.url", db_uri)
    return cfg


def test_alembic_upgrade_and_downgrade_cycle(alembic_cfg: Config, temp_db_path: Path):
    """Verify that Alembic upgrade head applies schema and downgrade base cleanly reverts it."""
    # 1. Apply upgrade to head
    command.upgrade(alembic_cfg, "head")

    sync_uri = f"sqlite:///{temp_db_path.as_posix()}"
    sync_engine = create_engine(sync_uri)

    try:
        inspector = inspect(sync_engine)
        tables = inspector.get_table_names()

        assert "documents" in tables
        assert "ingestion_jobs" in tables
        assert "batch_ingestion_jobs" in tables
        assert "docsets" in tables

        # Verify docsets columns
        docset_cols = {col["name"]: col for col in inspector.get_columns("docsets")}
        assert "name" in docset_cols
        assert "document_count" in docset_cols
        assert "created_at" in docset_cols
        assert "updated_at" in docset_cols
        assert "deleted_at" in docset_cols

        # Verify documents columns
        doc_cols = {col["name"]: col for col in inspector.get_columns("documents")}
        assert "id" in doc_cols
        assert "docset" in doc_cols
        assert "source_type" in doc_cols
        assert "source_url" in doc_cols
        assert "chunk_count" in doc_cols
        assert "created_at" in doc_cols
        assert "updated_at" in doc_cols
        assert "deleted_at" in doc_cols

        # Verify batch_ingestion_jobs columns
        batch_cols = {col["name"]: col for col in inspector.get_columns("batch_ingestion_jobs")}
        assert "id" in batch_cols
        assert "status" in batch_cols
        assert "total_count" in batch_cols
        assert "accepted_count" in batch_cols
        assert "skipped_count" in batch_cols
        assert "skipped_details" in batch_cols
        assert "created_at" in batch_cols
        assert "finished_at" in batch_cols

        # Verify ingestion_jobs columns & foreign keys
        job_cols = {col["name"]: col for col in inspector.get_columns("ingestion_jobs")}
        assert "id" in job_cols
        assert "batch_id" in job_cols
        assert "document_id" in job_cols
        assert "status" in job_cols
        assert "progress_percentage" in job_cols
        assert "finished_at" in job_cols

        fks = inspector.get_foreign_keys("ingestion_jobs")
        referred_tables = {fk["referred_table"] for fk in fks}
        assert "documents" in referred_tables
        assert "batch_ingestion_jobs" in referred_tables

        doc_fks = inspector.get_foreign_keys("documents")
        doc_referred_tables = {fk["referred_table"] for fk in doc_fks}
        assert "docsets" in doc_referred_tables

        # Verify partial unique index
        doc_indices = inspector.get_indexes("documents")
        partial_idx = next(
            (idx for idx in doc_indices if idx["name"] == "uq_documents_active_docset_source_url"),
            None,
        )
        assert partial_idx is not None
        assert bool(partial_idx["unique"]) is True
        assert "docset" in partial_idx["column_names"]
        assert "source_url" in partial_idx["column_names"]

    finally:
        sync_engine.dispose()

    # 2. Apply downgrade to base
    command.downgrade(alembic_cfg, "base")

    sync_engine = create_engine(sync_uri)
    try:
        inspector = inspect(sync_engine)
        remaining_tables = inspector.get_table_names()
        assert "docsets" not in remaining_tables
        assert "documents" not in remaining_tables
        assert "ingestion_jobs" not in remaining_tables
        assert "batch_ingestion_jobs" not in remaining_tables
    finally:
        sync_engine.dispose()


def test_alembic_postgres_if_available():
    """Verify migrations against PostgreSQL if the backing service is reachable."""
    from scripts.check_env import check_tcp_port

    pg_reachable = check_tcp_port(settings.postgres_host, settings.postgres_port)
    if not pg_reachable:
        pytest.skip(f"PostgreSQL unreachable at {settings.postgres_host}:{settings.postgres_port}")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
