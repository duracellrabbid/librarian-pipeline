"""Initial metadata schema for documents and ingestion jobs.

Revision ID: 0001_initial_metadata_schema
Revises: None
Create Date: 2026-09-06 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_metadata_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply initial migration creating documents and ingestion_jobs tables."""
    # Create documents table
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_source_url"), "documents", ["source_url"], unique=False)
    op.create_index(op.f("ix_documents_deleted_at"), "documents", ["deleted_at"], unique=False)
    op.create_index(
        "uq_documents_active_source_url",
        "documents",
        ["source_url"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )

    # Create ingestion_jobs table
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("progress_percentage", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_jobs_document_id"), "ingestion_jobs", ["document_id"], unique=False)
    op.create_index(op.f("ix_ingestion_jobs_status"), "ingestion_jobs", ["status"], unique=False)


def downgrade() -> None:
    """Revert initial migration by dropping tables and indices."""
    op.drop_index(op.f("ix_ingestion_jobs_status"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_document_id"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")

    op.drop_index("uq_documents_active_source_url", table_name="documents")
    op.drop_index(op.f("ix_documents_deleted_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_source_url"), table_name="documents")
    op.drop_table("documents")
