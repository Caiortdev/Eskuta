"""
Model: evidences — anti-alucinação core. Cada decisão / action item /
tópico da ata precisa apontar pra uma evidence com o trecho exato da
transcrição.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, new_uuid, utcnow

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class Evidence(Base):
    __tablename__ = "evidences"
    __table_args__ = (
        CheckConstraint(
            "parent_type IN ('topic', 'decision', 'action_item')",
            name="ck_evidences_parent_type",
        ),
        Index("idx_evidences_parent", "parent_type", "parent_id"),
        Index("idx_evidences_meeting", "meeting_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_type: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_id: Mapped[str] = mapped_column(String(32), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    speaker: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_sec: Mapped[float | None] = mapped_column(nullable=True)
    end_sec: Mapped[float | None] = mapped_column(nullable=True)
    validated: Mapped[bool] = mapped_column(default=False, nullable=False)
    validation_score: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    meeting: Mapped[Meeting] = relationship(back_populates="evidences")
