"""Document entity model representing ingested sources."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, text
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.job import IngestionJob


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class Document(SQLModel, table=True):
    """Document model representing ingested web/file sources with soft-delete support."""

    __tablename__ = "documents"
    __table_args__ = (
        Index(
            "uq_documents_active_source_url",
            "source_url",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_type: str = Field(nullable=False, description="Source type, e.g. url, pdf, text")
    source_url: str = Field(index=True, nullable=False, description="Source URL or path")
    content_hash: str | None = Field(default=None, description="Content hash for deduplication")
    title: str | None = Field(default=None, description="Extracted or provided title")
    chunk_count: int = Field(default=0, ge=0, description="Total chunks indexed for document")
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        index=True,
        nullable=True,
    )

    jobs: list["IngestionJob"] = Relationship(
        back_populates="document",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
