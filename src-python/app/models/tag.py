"""Models: Tag (catálogo) + MeetingTag (junção N:N com Meeting)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (Index("uq_tags_name", "name", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    meeting_links: Mapped[list[MeetingTag]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
    )


class MeetingTag(Base):
    """Junction N:N entre meetings e tags."""

    __tablename__ = "meeting_tags"

    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Não usa default=new_uuid — gerado pela combinação PK.
    # mas registramos when foi taggado
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    meeting: Mapped[Meeting] = relationship(back_populates="tag_links")
    tag: Mapped[Tag] = relationship(back_populates="meeting_links")
