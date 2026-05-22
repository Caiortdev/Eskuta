"""Fixtures globais dos testes do sidecar Eskuta."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx
import keyring
import keyring.backend
import pytest
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Importa todos os models ANTES da app FastAPI pra garantir que estão
# registrados em Base.metadata quando o engine de teste cria as tabelas.
from app import models as _models  # noqa: F401
from app.db.base import Base
from app.db.database import create_engine_from_settings, get_db
from app.main import app


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
async def client_with_db() -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    """
    Como `client`, mas com `get_db` sobrescrito pra usar uma sessão
    in-memory dedicada por teste. Retorna o par (client, session) — o
    teste pode inspecionar o DB diretamente via session.
    """
    engine = create_engine_from_settings("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    test_session = factory()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        # Uma session NOVA por request — pra simular o ciclo real do FastAPI.
        # Compartilha a mesma engine in-memory que `test_session`.
        async with factory() as request_session:
            yield request_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://eskuta-test",
    ) as ac:
        yield ac, test_session

    app.dependency_overrides.pop(get_db, None)
    await test_session.close()
    await engine.dispose()


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    """Backend simples de keyring pra testes — não toca no OS."""

    priority = 1.0

    def __init__(self) -> None:
        self._storage: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._storage.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._storage[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self._storage:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._storage[key]


@pytest.fixture
def in_memory_keyring() -> Iterator[_InMemoryKeyring]:
    """Substitui o backend do keyring por um in-memory durante o teste."""
    original = keyring.get_keyring()
    backend = _InMemoryKeyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(original)


@pytest.fixture
def loguru_messages() -> Iterator[list[str]]:
    """
    Captura mensagens emitidas via `loguru.logger` durante um teste.

    `caplog` do pytest só pega o logging stdlib — Loguru tem seu próprio
    pipeline e escreve direto em stderr. Use esta fixture quando precisar
    asserir algo sobre o conteúdo de um log (positivo ou negativo) emitido
    via Loguru, por exemplo verificar que uma API key NÃO aparece no log.

    O formato inclui `{extra}` pra que os kwargs estruturados (ex:
    `logger.info("msg", provider="groq")`) sejam parte do texto capturado.
    """
    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message} | {extra}",
    )
    try:
        yield captured
    finally:
        logger.remove(sink_id)
