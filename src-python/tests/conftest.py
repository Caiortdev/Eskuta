"""Fixtures globais dos testes do sidecar Eskuta."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Importa todos os models ANTES da app FastAPI pra garantir que estão
# registrados em Base.metadata quando o engine de teste cria as tabelas.
from app import models as _models  # noqa: F401
from app.db.base import Base
from app.db.database import create_engine_from_settings
from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """
    HTTP client async em cima do app FastAPI, sem precisar subir uvicorn
    de verdade. Usa ASGI transport — chama o handler direto.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://eskuta-test",
    ) as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """
    Sessão SQLAlchemy contra um SQLite in-memory limpo por teste.
    Cria todas as tabelas (Base.metadata.create_all) no setup e descarta
    a engine no teardown.
    """
    engine = create_engine_from_settings("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()
