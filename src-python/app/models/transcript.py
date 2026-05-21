"""
Models: transcripts (1:1 com meetings), transcript_segments (N:1) e
speakers (N:1 com meetings).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, new_uuid, utcnow

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class Transcript(Base):
    """Transcrição completa de uma reunião (texto bruto + metadados)."""

    __tablename__ = "transcripts"
    __table_args__ = (Index("idx_transcripts_meeting_id", "meeting_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    language_detected: Mapped[str | None] = mapped_column(String(8), nullable=True)
    provider_used: Mapped[str] = mapped_column(String(32), nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    processing_time_sec: Mapped[float | None] = mapped_column(nullable=True)
    word_count: Mapped[int | None] = mapped_column(nullable=True)
    avg_confidence: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    meeting: Mapped[Meeting] = relationship(back_populates="transcript")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="transcript",
        cascade="all, delete-orphan",
    )


class TranscriptSegment(Base):
    """
    Segmentos individuais da transcrição (chunks de fala com timestamp).
    Volume alto — PK INTEGER autoincrement, sem UUID.
    """

    __tablename__ = "transcript_segments"
    __table_args__ = (
        Index("idx_segments_transcript_start", "transcript_id", "start_sec"),
        Index("idx_segments_meeting_id", "meeting_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transcript_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
    )
    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment_index: Mapped[int] = mapped_column(nullable=False)
    start_sec: Mapped[float] = mapped_column(nullable=False)
    end_sec: Mapped[float] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    speaker_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    transcript: Mapped[Transcript] = relationship(back_populates="segments")
    meeting: Mapped[Meeting] = relationship(back_populates="segments")


class Speaker(Base):
    """
    Speakers identificados pela diarização. O usuário pode renomear
    (display_name) — o speaker_id original é o "SPEAKER_00" do pyannote.
    """

    __tablename__ = "speakers"
    __table_args__ = (Index("idx_speakers_meeting", "meeting_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    speaker_id: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_speaking_sec: Mapped[float] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    meeting: Mapped[Meeting] = relationship(back_populates="speakers")
