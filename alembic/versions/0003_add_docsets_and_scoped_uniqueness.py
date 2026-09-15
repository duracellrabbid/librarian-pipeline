"""Add docsets table, document docset column, and scoped composite unique index.

Revision ID: 0003_add_docsets_and_scoped_uniqueness
Revises: 0002_add_batch_ingestion_jobs
Create Date: 2026-09-15 15:00:00.000000

"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_docsets_and_scoped_uniqueness"
down_revision: str | None = "0002_add_batch_ingestion_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration creating docsets table, linking documents, and updating uniqueness."""
    # 1. Create docsets table
    op.create_table(
        "docsets",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_index(op.f("ix_docsets_deleted_at"), "docsets", ["deleted_at"], unique=False)

    # 2. Seed default docset for existing / legacy documents
    now = datetime.now(UTC)
    docsets_table = sa.table(
        "docsets",
        sa.column("name", sa.String(length=64)),
        sa.column("document_count", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        docsets_table.insert().values(
            name="default",
            document_count=0,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
    )

    # 3. Add docset column to documents, backfill, alter constraints with batch mode
    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "docset",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'default'"),
            )
        )
        batch_op.create_foreign_key(
            "fk_documents_docset_docsets",
            "docsets",
            ["docset"],
            ["name"],
        )
        batch_op.create_index(
            batch_op.f("ix_documents_docset"),
            ["docset"],
            unique=False,
        )
        batch_op.drop_index("uq_documents_active_source_url")
        batch_op.create_index(
            "uq_documents_active_docset_source_url",
            ["docset", "source_url"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
            sqlite_where=sa.text("deleted_at IS NULL"),
        )

    # 4. Update default docset document_count
    op.execute(
        "UPDATE docsets SET document_count = ("
        "SELECT COUNT(*) FROM documents WHERE docset = 'default' AND deleted_at IS NULL"
        ") WHERE name = 'default'"
    )


def downgrade() -> None:
    """Revert migration by restoring source_url unique index and dropping docsets."""
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_index("uq_documents_active_docset_source_url")
        batch_op.create_index(
            "uq_documents_active_source_url",
            ["source_url"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
            sqlite_where=sa.text("deleted_at IS NULL"),
        )
        batch_op.drop_index(batch_op.f("ix_documents_docset"))
        batch_op.drop_constraint("fk_documents_docset_docsets", type_="foreignkey")
        batch_op.drop_column("docset")

    op.drop_index(op.f("ix_docsets_deleted_at"), table_name="docsets")
    op.drop_table("docsets")
