"""
Model: meetings — uma reunião processada pelo Eskuta.
1:1 com transcripts e minutes (quando processada com sucesso).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.evidence import Evidence
    from app.models.minute import ActionItem, Decision, Minutes
    from app.models.operational import ProcessingJob
    from app.models.tag import MeetingTag
    from app.models.transcript import Speaker, Transcript, TranscriptSegment


class Meeting(Base, TimestampMixin):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint(
            "source IN ('upload', 'realtime')",
            name="ck_meetings_source",
        ),
        Index("idx_meetings_created_at", "created_at"),
        Index("idx_meetings_status", "status"),
        Index("idx_meetings_audio_hash", "audio_hash"),
        Index("idx_meetings_deleted_at", "deleted_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str] = mapped_column(Text, nullable=False)
    audio_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_sec: Mapped[float | None] = mapped_column(nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="pt")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="upload")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    speaker_map: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relacionamentos
    transcript: Mapped[Transcript | None] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        uselist=False,
    )
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    minutes: Mapped[Minutes | None] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        uselist=False,
    )
    action_items: Mapped[list[ActionItem]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    decisions: Mapped[list[Decision]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    evidences: Mapped[list[Evidence]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    speakers: Mapped[list[Speaker]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    tag_links: Mapped[list[MeetingTag]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
