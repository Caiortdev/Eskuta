"""
Models operacionais: ApiKey (referência ao OS keyring), ProcessingJob
(estado de pipelines async), UserPreference (configs do usuário em
runtime) e AuditLog (compliance).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_uuid, utcnow

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class ApiKey(Base, TimestampMixin):
    """
    Referência a uma API key — o valor real fica no OS keyring (Fase 1.11).
    Esta tabela só guarda metadata (provider, último status de validação).
    """

    __tablename__ = "api_keys"
    __table_args__ = (Index("uq_api_keys_provider", "provider", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    is_configured: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_validation_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProcessingJob(Base):
    """Fila / estado de jobs assíncronos (pipeline da ata, etc)."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint("progress_pct BETWEEN 0 AND 100", name="ck_jobs_progress"),
        Index("idx_jobs_meeting_id", "meeting_id"),
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    progress_pct: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)

    meeting: Mapped[Meeting] = relationship(back_populates="processing_jobs")


class UserPreference(Base):
    """Preferências do usuário em runtime — sobrepoem defaults de Settings."""

    __tablename__ = "user_preferences"
    __table_args__ = (Index("uq_prefs_key", "key", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), default="string", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)


class AuditLog(Base):
    """Log de operações sensíveis (LGPD/GDPR — retenção 90 dias)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_action_created", "action", "created_at"),
        Index("idx_audit_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
