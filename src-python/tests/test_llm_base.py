"""Testes dos tipos e exceptions compartilhados da camada de LLM."""

from __future__ import annotations

import pytest

from app.services.llm.base import (
    KNOWN_LLM_PROVIDERS,
    LLMAPIError,
    LLMError,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
)


def test_known_providers_constant_is_complete() -> None:
    assert KNOWN_LLM_PROVIDERS == ("claude", "gpt", "gemini")


def test_llm_message_frozen() -> None:
    m = LLMMessage(role="user", content="oi")
    with pytest.raises((AttributeError, TypeError)):
        m.role = "system"  # type: ignore[misc]


def test_llm_response_defaults_cost_zero() -> None:
    r = LLMResponse(
        content="oi",
        provider="claude",
        model="claude-sonnet-4-5",
        tokens_input=10,
        tokens_output=20,
    )
    assert r.cost_usd == 0.0


def test_llm_response_frozen() -> None:
    r = LLMResponse(
        content="oi",
        provider="claude",
        model="x",
        tokens_input=1,
        tokens_output=1,
    )
    with pytest.raises((AttributeError, TypeError)):
        r.content = "outro"  # type: ignore[misc]


def test_llm_error_carries_provider() -> None:
    err = LLMError("falha", provider="claude")
    assert str(err) == "falha"
    assert err.provider == "claude"


def test_llm_error_provider_optional() -> None:
    err = LLMError("falha")
    assert err.provider is None


def test_rate_limit_carries_retry_after() -> None:
    err = LLMRateLimitError("429", provider="gpt", retry_after_sec=5.0)
    assert err.retry_after_sec == 5.0
    assert err.provider == "gpt"


def test_rate_limit_retry_after_optional() -> None:
    err = LLMRateLimitError("429", provider="gpt")
    assert err.retry_after_sec is None


def test_subclasses_inherit_from_llm_error() -> None:
    assert issubclass(LLMProviderUnavailableError, LLMError)
    assert issubclass(LLMRateLimitError, LLMError)
    assert issubclass(LLMAPIError, LLMError)
    assert issubclass(LLMTimeoutError, LLMError)
