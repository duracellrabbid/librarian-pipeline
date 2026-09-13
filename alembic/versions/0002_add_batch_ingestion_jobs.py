"""Add batch_ingestion_jobs table and batch_id column to ingestion_jobs.

Revision ID: 0002_add_batch_ingestion_jobs
Revises: 0001_initial_metadata_schema
Create Date: 2026-09-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_batch_ingestion_jobs"
down_revision: str | None = "0001_initial_metadata_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration creating batch_ingestion_jobs table and linking ingestion_jobs."""
    # 1. Create batch_ingestion_jobs table
    op.create_table(
        "batch_ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_details", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_ingestion_jobs_status"), "batch_ingestion_jobs", ["status"], unique=False)

    # 2. Add batch_id to ingestion_jobs with batch mode for SQLite support
    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.add_column(sa.Column("batch_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_ingestion_jobs_batch_id_batch_ingestion_jobs",
            "batch_ingestion_jobs",
            ["batch_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            batch_op.f("ix_ingestion_jobs_batch_id"),
            ["batch_id"],
            unique=False,
        )


def downgrade() -> None:
    """Revert migration by dropping batch_id column and batch_ingestion_jobs table."""
    with op.batch_alter_table("ingestion_jobs") as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingestion_jobs_batch_id"))
        batch_op.drop_constraint(
            "fk_ingestion_jobs_batch_id_batch_ingestion_jobs",
            type_="foreignkey",
        )
        batch_op.drop_column("batch_id")

    op.drop_index(op.f("ix_batch_ingestion_jobs_status"), table_name="batch_ingestion_jobs")
    op.drop_table("batch_ingestion_jobs")
