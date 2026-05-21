"""
Setup da engine async, session factory e helpers.

A engine usa o dialeto `sqlite+aiosqlite` apontado pelo `settings.DB_PATH`.
Em produção (Fase 3), basta trocar a DATABASE_URL pra Postgres — modelos
e queries continuam idênticos graças ao SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import settings
from app.db.base import Base

__all__ = [
    "Base",
    "create_engine_from_settings",
    "engine",
    "get_db",
    "get_session_factory",
]


def _build_database_url() -> str:
    """Monta o DSN async — pode ser sobrescrito por env var ESKUTA_DATABASE_URL no futuro."""
    db_path = settings.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Liga FOREIGN KEYS no SQLite (desligado por default — diferença do Postgres)."""
    if dbapi_connection.__class__.__module__.startswith("aiosqlite") or "sqlite" in str(
        type(dbapi_connection)
    ):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL melhora concorrência leitura/escrita em SQLite local
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def create_engine_from_settings(
    database_url: str | None = None, *, echo: bool = False
) -> AsyncEngine:
    """Factory da engine. Útil pra testes que querem in-memory."""
    url = database_url or _build_database_url()
    return create_async_engine(
        url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
    )


# Engine singleton — usado pelo app FastAPI.
engine: AsyncEngine = create_engine_from_settings()


def get_session_factory(
    target_engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Cria session factory pra a engine fornecida (ou a singleton)."""
    return async_sessionmaker(
        target_engine or engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


# Session factory singleton.
AsyncSessionLocal: async_sessionmaker[AsyncSession] = get_session_factory()


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    Dependency do FastAPI: fornece uma session por request.

    Uso:

        from fastapi import Depends
        from app.db.database import get_db

        @app.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
