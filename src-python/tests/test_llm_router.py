"""
Testes do LLMRouter — seleção de provider conforme preferência + fallback.

Usamos providers fake controláveis (não mockamos os adapters reais) pra
exercer a lógica de seleção isoladamente.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.services.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMResponse,
)
from app.services.llm.router import LLMRouter, _build_default_providers


class _FakeProvider(LLMProvider):
    """Provider controlado pelos testes."""

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        default_model: str = "fake-model",
    ) -> None:
        self._name = name
        self._available = available
        self._default_model = default_model
        self.last_call: dict | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def default_model(self) -> str:
        return self._default_model

    def is_available(self) -> bool:
        return self._available

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        self.last_call = {
            "messages": list(messages),
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": response_format,
        }
        return LLMResponse(
            content=f"resposta de {self._name}",
            provider=self._name,
            model=model or self._default_model,
            tokens_input=1,
            tokens_output=1,
        )


# ============================================================
# Construção
# ============================================================


def test_default_providers_includes_all_three() -> None:
    providers = _build_default_providers()
    assert set(providers.keys()) == {"claude", "gpt", "gemini"}


def test_default_router_has_three_providers() -> None:
    router = LLMRouter()
    assert set(router.providers.keys()) == {"claude", "gpt", "gemini"}


# ============================================================
# get_provider
# ============================================================


def test_preferred_argument_wins_when_available() -> None:
    p_claude = _FakeProvider("claude")
    p_gpt = _FakeProvider("gpt")
    router = LLMRouter({"claude": p_claude, "gpt": p_gpt})

    assert router.get_provider("gpt") is p_gpt
    assert router.get_provider("claude") is p_claude


def test_falls_back_to_settings_preferred_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.llm.router.settings.PREFERRED_LLM", "gemini")
    p_claude = _FakeProvider("claude")
    p_gemini = _FakeProvider("gemini")
    router = LLMRouter({"claude": p_claude, "gemini": p_gemini})

    assert router.get_provider() is p_gemini


def test_preferred_unavailable_falls_back_to_any_available() -> None:
    p_claude = _FakeProvider("claude", available=False)
    p_gpt = _FakeProvider("gpt", available=True)
    router = LLMRouter({"claude": p_claude, "gpt": p_gpt})

    # Preferiu claude, mas não tem key → cai pro gpt
    picked = router.get_provider("claude")
    assert picked.name == "gpt"


def test_unknown_preferred_falls_back_to_any_available() -> None:
    p_claude = _FakeProvider("claude", available=True)
    router = LLMRouter({"claude": p_claude, "gpt": _FakeProvider("gpt", available=False)})

    # "deepseek" não existe — vai pro fallback
    picked = router.get_provider("deepseek")
    assert picked.name == "claude"


def test_raises_when_no_providers_available() -> None:
    router = LLMRouter(
        {
            "claude": _FakeProvider("claude", available=False),
            "gpt": _FakeProvider("gpt", available=False),
            "gemini": _FakeProvider("gemini", available=False),
        }
    )
    with pytest.raises(LLMProviderUnavailableError):
        router.get_provider()


def test_fallback_logs_warning_with_preferred_and_picked(
    loguru_messages: list[str],
) -> None:
    router = LLMRouter(
        {
            "claude": _FakeProvider("claude", available=False),
            "gpt": _FakeProvider("gpt", available=True),
        }
    )
    router.get_provider("claude")
    combined = "\n".join(loguru_messages)
    assert "preferred" in combined
    assert "claude" in combined
    assert "gpt" in combined


# ============================================================
# complete (delegação)
# ============================================================


async def test_complete_delegates_to_picked_provider() -> None:
    p_claude = _FakeProvider("claude")
    p_gpt = _FakeProvider("gpt")
    router = LLMRouter({"claude": p_claude, "gpt": p_gpt})

    result = await router.complete(
        [LLMMessage(role="user", content="oi")],
        preferred="gpt",
        max_tokens=200,
        temperature=0.5,
        response_format={"type": "json_object"},
    )
    assert result.provider == "gpt"
    assert p_gpt.last_call is not None
    assert p_gpt.last_call["max_tokens"] == 200
    assert p_gpt.last_call["temperature"] == 0.5
    assert p_gpt.last_call["response_format"] == {"type": "json_object"}
    # Não tocou no claude
    assert p_claude.last_call is None


async def test_complete_uses_default_when_no_preferred() -> None:
    p_claude = _FakeProvider("claude")
    router = LLMRouter({"claude": p_claude})

    result = await router.complete([LLMMessage(role="user", content="oi")])
    assert result.provider == "claude"


async def test_complete_raises_when_none_available() -> None:
    router = LLMRouter(
        {
            "claude": _FakeProvider("claude", available=False),
            "gpt": _FakeProvider("gpt", available=False),
            "gemini": _FakeProvider("gemini", available=False),
        }
    )
    with pytest.raises(LLMProviderUnavailableError):
        await router.complete([LLMMessage(role="user", content="oi")])
