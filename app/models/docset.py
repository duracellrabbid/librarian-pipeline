"""Docset entity model representing logical document collections."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.document import Document


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class Docset(SQLModel, table=True):
    """Docset model representing logical document partitions with auto-pruning support."""

    __tablename__ = "docsets"

    name: str = Field(
        primary_key=True,
        max_length=64,
        description="Normalized lowercase docset identifier",
    )
    document_count: int = Field(
        default=0,
        ge=0,
        description="Total active documents tracked under this docset",
    )
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

    documents: list["Document"] = Relationship(
        back_populates="docset_rel",
    )
