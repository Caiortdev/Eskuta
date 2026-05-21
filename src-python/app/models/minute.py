"""
Models de ata: Minutes (1:1 com Meeting), MinuteVersion (histórico),
ActionItem e Decision.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_uuid, utcnow

if TYPE_CHECKING:
    from app.models.evidence import Evidence
    from app.models.meeting import Meeting


class Minutes(Base, TimestampMixin):
    """Ata gerada por LLM com base na transcrição."""

    __tablename__ = "minutes"
    __table_args__ = (Index("uq_minutes_meeting_id", "meeting_id", unique=True),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    date_extracted: Mapped[date | None] = mapped_column(Date, nullable=True)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    participants: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    topics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    open_questions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_input: Mapped[int] = mapped_column(nullable=False, default=0)
    tokens_output: Mapped[int] = mapped_column(nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    validation_passed: Mapped[bool] = mapped_column(default=False, nullable=False)
    validation_issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    user_edited: Mapped[bool] = mapped_column(default=False, nullable=False)

    meeting: Mapped[Meeting] = relationship(back_populates="minutes")
    versions: Mapped[list[MinuteVersion]] = relationship(
        back_populates="minute",
        cascade="all, delete-orphan",
    )
    action_items: Mapped[list[ActionItem]] = relationship(
        back_populates="minute",
        cascade="all, delete-orphan",
    )
    decisions: Mapped[list[Decision]] = relationship(
        back_populates="minute",
        cascade="all, delete-orphan",
    )


class MinuteVersion(Base):
    """Snapshot histórico de uma ata (pra cada regeneração ou edição)."""

    __tablename__ = "minute_versions"
    __table_args__ = (Index("idx_versions_minute_created", "minute_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    minute_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("minutes.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    minute: Mapped[Minutes] = relationship(back_populates="versions")


class ActionItem(Base):
    """Tarefa designada durante a reunião — quem faz o quê até quando."""

    __tablename__ = "action_items"
    __table_args__ = (
        CheckConstraint(
            "priority IN ('low', 'normal', 'high')",
            name="ck_action_items_priority",
        ),
        CheckConstraint(
            "status IN ('pending', 'done', 'cancelled')",
            name="ck_action_items_status",
        ),
        Index("idx_actions_minute_id", "minute_id"),
        Index("idx_actions_meeting_id", "meeting_id"),
        Index("idx_actions_status", "status"),
        Index("idx_actions_deadline", "deadline_parsed"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    minute_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("minutes.id", ondelete="CASCADE"),
        nullable=False,
    )
    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline_parsed: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("evidences.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    minute: Mapped[Minutes] = relationship(back_populates="action_items")
    meeting: Mapped[Meeting] = relationship(back_populates="action_items")
    evidence: Mapped[Evidence | None] = relationship()


class Decision(Base):
    """Decisão formal registrada durante a reunião."""

    __tablename__ = "decisions"
    __table_args__ = (
        Index("idx_decisions_minute_id", "minute_id"),
        Index("idx_decisions_meeting_id", "meeting_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    minute_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("minutes.id", ondelete="CASCADE"),
        nullable=False,
    )
    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("evidences.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    minute: Mapped[Minutes] = relationship(back_populates="decisions")
    meeting: Mapped[Meeting] = relationship(back_populates="decisions")
    evidence: Mapped[Evidence | None] = relationship()
