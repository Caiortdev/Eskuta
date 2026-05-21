"""Fixtures globais dos testes do sidecar Eskuta."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

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
