"""
Base declarativa e mixins compartilhados pelos models do Eskuta.

Convenções:
- UUID stringificado (TEXT em SQLite, UUID em Postgres) gerado em Python
  via `uuid.uuid4().hex` — uma única estratégia funcionando em ambos os
  SGBDs sem precisar de extensão (Postgres aceita TEXT como UUID quando
  o coltype é Uuid e o valor é uma string UUID válida).
- Timestamps sempre em UTC. `created_at` e `updated_at` mantidos via
  mixin reutilizável.
- JSON via `JSON` type — SQLite armazena como TEXT (sem validação),
  Postgres usa JSONB automaticamente (via dialect).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Timestamp UTC consistente — usado como default Python-side."""
    return datetime.now(UTC)


def new_uuid() -> str:
    """UUID v4 em string hex sem hífens (mesma estratégia do SCHEMA_BD)."""
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """Declarative base do ORM. Todos os models herdam daqui."""

    # type_annotation_map permite usar `datetime` em Mapped[datetime]
    # sem precisar declarar DateTime explicitamente em cada coluna.
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """Mixin que adiciona created_at / updated_at em UTC."""

    created_at: Mapped[datetime] = mapped_column(
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
