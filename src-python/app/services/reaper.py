"""
Reaper de meetings travadas — roda no startup do sidecar.

Se o sidecar foi morto durante o processing de uma meeting (kill -9,
crash, OS shutdown), a row em `meetings` fica num status intermediário
(`converting`, `transcribing`, etc) e nunca avança. O reaper detecta
esse estado e marca como `failed` com mensagem clara.

Critério: meeting com `status NOT IN ('completed', 'failed', 'pending')`
e `updated_at` mais antigo que `STALE_THRESHOLD_SEC` (padrão 1 hora) é
considerada travada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Meeting

# Estados terminais — nunca são "travados"
_TERMINAL_STATUSES = ("completed", "failed", "pending")

# Quanto tempo sem updated_at antes de considerar travada.
# 1 hora é folga generosa pra reuniões longas + retry de provider.
STALE_THRESHOLD_SEC: int = 60 * 60


async def reap_stale_meetings(
    db: AsyncSession,
    *,
    threshold_sec: int = STALE_THRESHOLD_SEC,
) -> int:
    """
    Marca meetings travadas como failed. Retorna quantas foram reapeadas.

    Idempotente — se rodar 2x seguidas, segunda chamada retorna 0.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_sec)

    stmt = select(Meeting).where(
        Meeting.status.notin_(_TERMINAL_STATUSES),
        Meeting.updated_at < cutoff,
    )
    result = await db.execute(stmt)
    stale = result.scalars().all()

    if not stale:
        return 0

    for m in stale:
        prev_status = m.status
        m.status = "failed"
        metadata = dict(m.extra_metadata or {})
        metadata["error"] = (
            f"Processamento interrompido (sidecar reiniciado). Reabra a reunião "
            f"e tente reprocessar. Status anterior: {prev_status}."
        )
        metadata["reaped_at"] = datetime.now(UTC).isoformat()
        m.extra_metadata = metadata

    await db.commit()

    logger.warning(
        "Reaper marcou meetings como failed",
        count=len(stale),
        ids=[str(m.id) for m in stale],
    )
    return len(stale)
