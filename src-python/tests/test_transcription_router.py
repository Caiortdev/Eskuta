"""
Testes do TranscriptionRouter — fallback inteligente entre providers.

Usamos providers fake controláveis (não mock os adapters reais) pra
exercer a lógica de retry/backoff/fallback isoladamente, sem depender
dos SDKs Groq/AssemblyAI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.services.transcription.base import (
    AllProvidersFailedError,
    ProviderAPIError,
    ProviderUnavailableError,
    RateLimitError,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionTimeoutError,
)
from app.services.transcription.router import (
    DEFAULT_MAX_ATTEMPTS_PER_PROVIDER,
    TranscriptionRouter,
    _build_default_providers,
)


class _FakeProvider(TranscriptionProvider):
    """
    Provider controlado pelos testes: configurável com sequência de
    comportamentos por chamada (exceptions ou success).
    """

    def __init__(
        self,
        name: str,
        *,
        behaviors: list[Any] | None = None,
        available: bool = True,
    ) -> None:
        self._name = name
        self.available = available
        self.behaviors = list(behaviors or [])
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return self.available

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str = "pt",
    ) -> TranscriptionResult:
        self.calls += 1
        if not self.behaviors:
            raise RuntimeError(f"FakeProvider {self._name} sem behaviors configurados")
        behavior = self.behaviors.pop(0)
        if isinstance(behavior, BaseException):
            raise behavior
        if callable(behavior):
            return behavior(audio_path, language)
        return behavior


def _ok_result(provider: str = "fake") -> TranscriptionResult:
    return TranscriptionResult(
        full_text="ok",
        segments=[],
        language="pt",
        duration_sec=1.0,
        provider_used=provider,
        model_used="model-x",
    )


@pytest.fixture
def disable_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """
    Substitui asyncio.sleep por no-op e registra os intervalos pedidos
    — pra checar backoff sem atrasar testes.
    """
    intervals: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        intervals.append(seconds)

    monkeypatch.setattr("app.services.transcription.router.asyncio.sleep", fake_sleep)
    return intervals


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"")
    return f


# ============================================================
# Construção e ordenação
# ============================================================


def test_default_providers_order_respects_preferred_stt(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default settings tem groq como preferred
    providers = _build_default_providers()
    assert providers[0].name == "groq"
    assert providers[1].name == "assemblyai"


def test_default_providers_reorder_when_assemblyai_preferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.transcription.router.settings.PREFERRED_STT", "assemblyai")
    providers = _build_default_providers()
    assert providers[0].name == "assemblyai"
    assert providers[1].name == "groq"


def test_router_rejects_invalid_max_attempts() -> None:
    with pytest.raises(ValueError):
        TranscriptionRouter(providers=[], max_attempts_per_provider=0)


# ============================================================
# Happy path
# ============================================================


async def test_first_provider_succeeds(audio: Path) -> None:
    p1 = _FakeProvider("p1", behaviors=[_ok_result("p1")])
    p2 = _FakeProvider("p2", behaviors=[])
    router = TranscriptionRouter([p1, p2])
    result = await router.transcribe(audio)
    assert result.provider_used == "p1"
    assert p1.calls == 1
    assert p2.calls == 0


async def test_second_provider_used_when_first_unavailable(audio: Path) -> None:
    p1 = _FakeProvider("p1", available=False)
    p2 = _FakeProvider("p2", behaviors=[_ok_result("p2")])
    router = TranscriptionRouter([p1, p2])
    result = await router.transcribe(audio)
    assert result.provider_used == "p2"
    assert p1.calls == 0  # nem foi chamado, só pulado
    assert p2.calls == 1


# ============================================================
# Rate limit + backoff exponencial
# ============================================================


async def test_rate_limit_triggers_retry_with_exponential_backoff(
    audio: Path,
    disable_sleep: list[float],
) -> None:
    p1 = _FakeProvider(
        "p1",
        behaviors=[
            RateLimitError("429", provider="p1"),
            RateLimitError("429", provider="p1"),
            _ok_result("p1"),
        ],
    )
    router = TranscriptionRouter([p1], backoff_base_sec=1.0)
    result = await router.transcribe(audio)
    assert result.provider_used == "p1"
    assert p1.calls == 3
    # Backoff exponencial: 1s (2^0), 2s (2^1)
    assert disable_sleep == [1.0, 2.0]


async def test_rate_limit_uses_retry_after_when_provided(
    audio: Path,
    disable_sleep: list[float],
) -> None:
    p1 = _FakeProvider(
        "p1",
        behaviors=[
            RateLimitError("429", provider="p1", retry_after_sec=7.0),
            _ok_result("p1"),
        ],
    )
    router = TranscriptionRouter([p1])
    await router.transcribe(audio)
    # Respeitou retry_after em vez do backoff padrão
    assert disable_sleep == [7.0]


async def test_rate_limit_exhausts_attempts_then_moves_to_next_provider(
    audio: Path,
    disable_sleep: list[float],
) -> None:
    p1 = _FakeProvider(
        "p1",
        behaviors=[RateLimitError("429", provider="p1")] * DEFAULT_MAX_ATTEMPTS_PER_PROVIDER,
    )
    p2 = _FakeProvider("p2", behaviors=[_ok_result("p2")])
    router = TranscriptionRouter([p1, p2])
    result = await router.transcribe(audio)
    assert result.provider_used == "p2"
    assert p1.calls == DEFAULT_MAX_ATTEMPTS_PER_PROVIDER
    # Após a última tentativa do p1, não esperou (não tem mais tentativas)
    assert len(disable_sleep) == DEFAULT_MAX_ATTEMPTS_PER_PROVIDER - 1


# ============================================================
# Erros não-recuperáveis → fallback
# ============================================================


async def test_api_error_immediately_falls_back(
    audio: Path,
    disable_sleep: list[float],
) -> None:
    p1 = _FakeProvider("p1", behaviors=[ProviderAPIError("auth failed", provider="p1")])
    p2 = _FakeProvider("p2", behaviors=[_ok_result("p2")])
    router = TranscriptionRouter([p1, p2])
    result = await router.transcribe(audio)
    assert result.provider_used == "p2"
    # APIError quebra o loop interno — só 1 call no p1
    assert p1.calls == 1
    # Nenhum sleep (erro não-recuperável não tem backoff)
    assert disable_sleep == []


async def test_timeout_falls_back(audio: Path, disable_sleep: list[float]) -> None:
    p1 = _FakeProvider("p1", behaviors=[TranscriptionTimeoutError("timeout", provider="p1")])
    p2 = _FakeProvider("p2", behaviors=[_ok_result("p2")])
    router = TranscriptionRouter([p1, p2])
    result = await router.transcribe(audio)
    assert result.provider_used == "p2"
    assert p1.calls == 1


async def test_provider_unavailable_during_call_falls_back(
    audio: Path,
    disable_sleep: list[float],
) -> None:
    """is_available retorna True, mas transcribe levanta ProviderUnavailableError."""
    p1 = _FakeProvider("p1", behaviors=[ProviderUnavailableError("sumiu", provider="p1")])
    p2 = _FakeProvider("p2", behaviors=[_ok_result("p2")])
    router = TranscriptionRouter([p1, p2])
    result = await router.transcribe(audio)
    assert result.provider_used == "p2"


# ============================================================
# Todos os providers falharam
# ============================================================


async def test_all_providers_failed_raises_with_failures_dict(
    audio: Path,
    disable_sleep: list[float],
) -> None:
    p1 = _FakeProvider("p1", behaviors=[ProviderAPIError("oops", provider="p1")])
    p2 = _FakeProvider("p2", behaviors=[ProviderAPIError("nope", provider="p2")])
    router = TranscriptionRouter([p1, p2])
    with pytest.raises(AllProvidersFailedError) as exc:
        await router.transcribe(audio)
    assert set(exc.value.failures.keys()) == {"p1", "p2"}


async def test_all_providers_unavailable_raises_with_no_key_reason(
    audio: Path,
    disable_sleep: list[float],
) -> None:
    p1 = _FakeProvider("p1", available=False)
    p2 = _FakeProvider("p2", available=False)
    router = TranscriptionRouter([p1, p2])
    with pytest.raises(AllProvidersFailedError) as exc:
        await router.transcribe(audio)
    assert exc.value.failures == {"p1": "sem API key", "p2": "sem API key"}


# ============================================================
# Mistura — primeiro provider em rate limit persistente, fallback funciona
# ============================================================


async def test_first_in_rate_limit_second_succeeds(
    audio: Path,
    disable_sleep: list[float],
) -> None:
    p1 = _FakeProvider("p1", behaviors=[RateLimitError("429")] * 3)
    p2 = _FakeProvider("p2", behaviors=[_ok_result("p2")])
    router = TranscriptionRouter([p1, p2])
    result = await router.transcribe(audio)
    assert result.provider_used == "p2"
    assert p1.calls == 3
    assert p2.calls == 1


# ============================================================
# Language pass-through
# ============================================================


async def test_language_argument_is_forwarded(audio: Path) -> None:
    captured: dict[str, str] = {}

    def behavior(path: Path, lang: str) -> TranscriptionResult:
        captured["lang"] = lang
        return _ok_result("p1")

    p1 = _FakeProvider("p1", behaviors=[behavior])
    router = TranscriptionRouter([p1])
    await router.transcribe(audio, language="en")
    assert captured["lang"] == "en"
