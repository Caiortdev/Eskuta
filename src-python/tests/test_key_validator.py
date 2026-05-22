"""
Testes unitários de `app.services.key_validator`.

Mocka os SDKs externos (groq, anthropic, openai) e o cliente httpx
(usado pra AssemblyAI + Google) pra não fazer chamadas reais. Cobre os
3 status (valid / invalid / error) + classificação de HTTP errors.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.key_validator import (
    ValidationResult,
    _classify_status_error,
    validate_api_key,
)

# ============================================================
# _classify_status_error
# ============================================================


def test_classify_401_is_invalid() -> None:
    r = _classify_status_error(401, "Unauthorized", latency_ms=10)
    assert r.status == "invalid"
    assert r.http_status == 401
    assert "rejeitada" in (r.message or "").lower()


def test_classify_403_is_invalid() -> None:
    r = _classify_status_error(403, "Forbidden", latency_ms=10)
    assert r.status == "invalid"


def test_classify_429_is_error() -> None:
    r = _classify_status_error(429, "Too many", latency_ms=10)
    assert r.status == "error"
    assert "rate limit" in (r.message or "").lower()


def test_classify_500_is_error() -> None:
    r = _classify_status_error(500, "boom", latency_ms=10)
    assert r.status == "error"
    assert "500" in (r.message or "")


def test_classify_unknown_status_is_error() -> None:
    r = _classify_status_error(418, "I'm a teapot", latency_ms=10)
    assert r.status == "error"


# ============================================================
# Dispatcher
# ============================================================


async def test_validate_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="desconhecido"):
        await validate_api_key("bogus", "x")


async def test_validate_empty_key_returns_invalid() -> None:
    r = await validate_api_key("groq", "")
    assert r.status == "invalid"
    assert "vazia" in (r.message or "").lower()


async def test_validate_whitespace_key_returns_invalid() -> None:
    r = await validate_api_key("groq", "   ")
    assert r.status == "invalid"


# ============================================================
# Groq / Anthropic / OpenAI — usam SDK
# ============================================================


async def test_validate_groq_success() -> None:
    # Imports são lazy dentro de _validate_groq, então injetamos um módulo
    # fake em sys.modules ao invés de patchar o symbol do key_validator.
    import sys
    from types import ModuleType

    fake_client = MagicMock()
    fake_client.models = MagicMock()
    fake_client.models.list = AsyncMock(return_value=[{"id": "whisper-large-v3"}])
    fake_client.close = AsyncMock()

    groq_mod = ModuleType("groq")
    groq_mod.AsyncGroq = lambda **kwargs: fake_client  # type: ignore[attr-defined]
    groq_mod.APIStatusError = Exception  # type: ignore[attr-defined]
    sys.modules["groq"] = groq_mod
    try:
        r = await validate_api_key("groq", "sk-real")
    finally:
        del sys.modules["groq"]
    assert r.status == "valid"
    assert r.http_status == 200


async def test_validate_anthropic_invalid_key() -> None:
    import sys
    from types import ModuleType

    class FakeAPIStatusError(Exception):
        def __init__(self, status_code: int):
            super().__init__("invalid api key")
            self.status_code = status_code

    fake_client = MagicMock()
    fake_client.models = MagicMock()
    fake_client.models.list = AsyncMock(side_effect=FakeAPIStatusError(401))
    fake_client.close = AsyncMock()

    anth_mod = ModuleType("anthropic")
    anth_mod.AsyncAnthropic = lambda **kwargs: fake_client  # type: ignore[attr-defined]
    anth_mod.APIStatusError = FakeAPIStatusError  # type: ignore[attr-defined]
    sys.modules["anthropic"] = anth_mod
    try:
        r = await validate_api_key("anthropic", "errada")
    finally:
        del sys.modules["anthropic"]
    assert r.status == "invalid"
    assert r.http_status == 401


async def test_validate_openai_success() -> None:
    import sys
    from types import ModuleType

    fake_client = MagicMock()
    fake_client.models = MagicMock()
    fake_client.models.list = AsyncMock(return_value=[])
    fake_client.close = AsyncMock()

    openai_mod = ModuleType("openai")
    openai_mod.AsyncOpenAI = lambda **kwargs: fake_client  # type: ignore[attr-defined]
    openai_mod.APIStatusError = Exception  # type: ignore[attr-defined]
    sys.modules["openai"] = openai_mod
    try:
        r = await validate_api_key("openai", "sk-x")
    finally:
        del sys.modules["openai"]
    assert r.status == "valid"


# ============================================================
# AssemblyAI / Google — usam httpx
# ============================================================


async def test_validate_assemblyai_success_via_httpx(monkeypatch: Any) -> None:
    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    r = await validate_api_key("assemblyai", "aai-key")
    assert r.status == "valid"


async def test_validate_assemblyai_unauthorized(monkeypatch: Any) -> None:
    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(401, text="bad", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    r = await validate_api_key("assemblyai", "errada")
    assert r.status == "invalid"
    assert r.http_status == 401


async def test_validate_assemblyai_timeout(monkeypatch: Any) -> None:
    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    r = await validate_api_key("assemblyai", "aai-key")
    assert r.status == "error"
    assert "timeout" in (r.message or "").lower()


async def test_validate_google_success(monkeypatch: Any) -> None:
    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    r = await validate_api_key("google", "AIza-key")
    assert r.status == "valid"


async def test_validate_google_network_error(monkeypatch: Any) -> None:
    async def fake_get(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("dns")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    r = await validate_api_key("google", "AIza-key")
    assert r.status == "error"
    assert "rede" in (r.message or "").lower()


# ============================================================
# ValidationResult sanidade
# ============================================================


def test_validation_result_is_immutable() -> None:
    r = ValidationResult(status="valid", message=None, http_status=200, latency_ms=10)
    with pytest.raises((AttributeError, Exception)):
        r.status = "invalid"  # type: ignore[misc]
