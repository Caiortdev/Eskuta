"""
Testes do adapter GPT (app.services.llm.gpt_provider).

Mockamos `openai.AsyncOpenAI` pra não bater na API real. Validamos:
mensagens pass-through (já em formato OpenAI), response_format
nativo, mapeamento de exceptions, cálculo de custo.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from app.services.llm.base import (
    LLMAPIError,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.services.llm.gpt_provider import (
    GPT_INPUT_PER_MTOK,
    GPT_MODEL,
    GPT_OUTPUT_PER_MTOK,
    GPTProvider,
)


def _make_response(
    *,
    text: str = "olá",
    model: str = GPT_MODEL,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = text
    response.model = model
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    return response


def test_name_and_default_model() -> None:
    p = GPTProvider()
    assert p.name == "gpt"
    assert p.default_model == GPT_MODEL


def test_is_available_false_without_key(in_memory_keyring) -> None:
    assert GPTProvider().is_available() is False


def test_is_available_true_with_key(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")
    assert GPTProvider().is_available() is True


async def test_complete_without_key_raises_unavailable(in_memory_keyring) -> None:
    with pytest.raises(LLMProviderUnavailableError):
        await GPTProvider().complete([LLMMessage(role="user", content="oi")])


async def test_complete_passes_messages_directly(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

    with patch("openai.AsyncOpenAI", return_value=mock_client) as MockCls:
        await GPTProvider().complete(
            [
                LLMMessage(role="system", content="você é assistente"),
                LLMMessage(role="user", content="oi"),
                LLMMessage(role="assistant", content="olá!"),
            ],
            max_tokens=500,
            temperature=0.7,
        )

    MockCls.assert_called_once_with(api_key="sk-test")
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == GPT_MODEL
    assert call_kwargs["max_tokens"] == 500
    assert call_kwargs["temperature"] == 0.7
    # OpenAI já espera system como msg comum — passa todas
    assert call_kwargs["messages"] == [
        {"role": "system", "content": "você é assistente"},
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "olá!"},
    ]


async def test_complete_json_mode_passes_native_response_format(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        await GPTProvider().complete(
            [LLMMessage(role="user", content="oi")],
            response_format={"type": "json_object"},
        )

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}


async def test_complete_without_json_mode_no_response_format(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        await GPTProvider().complete([LLMMessage(role="user", content="oi")])

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "response_format" not in call_kwargs


async def test_complete_returns_normalized_response(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_response(
            text="resposta final",
            prompt_tokens=1000,
            completion_tokens=500,
        )
    )

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        result = await GPTProvider().complete([LLMMessage(role="user", content="oi")])

    assert result.provider == "gpt"
    assert result.content == "resposta final"
    assert result.tokens_input == 1000
    assert result.tokens_output == 500
    expected_cost = 1000 / 1_000_000 * GPT_INPUT_PER_MTOK + 500 / 1_000_000 * GPT_OUTPUT_PER_MTOK
    assert result.cost_usd == pytest.approx(expected_cost)


async def test_complete_uses_custom_model(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response(model="gpt-5-mini"))

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        await GPTProvider().complete(
            [LLMMessage(role="user", content="oi")],
            model="gpt-5-mini",
        )

    assert mock_client.chat.completions.create.call_args.kwargs["model"] == "gpt-5-mini"


async def test_complete_handles_none_content(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    response = _make_response()
    response.choices[0].message.content = None

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        result = await GPTProvider().complete([LLMMessage(role="user", content="oi")])

    assert result.content == ""


async def test_complete_maps_rate_limit(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    response_mock = MagicMock()
    response_mock.headers = {}
    sdk_exc = openai.RateLimitError(
        message="429",
        response=response_mock,
        body=None,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=sdk_exc)

    with (
        patch("openai.AsyncOpenAI", return_value=mock_client),
        pytest.raises(LLMRateLimitError) as exc,
    ):
        await GPTProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "gpt"


async def test_complete_maps_timeout(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=MagicMock())
    )

    with (
        patch("openai.AsyncOpenAI", return_value=mock_client),
        pytest.raises(LLMTimeoutError) as exc,
    ):
        await GPTProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "gpt"


async def test_complete_maps_api_error(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("openai", "sk-test")

    sdk_exc = openai.APIError(
        message="boom",
        request=MagicMock(),
        body=None,
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=sdk_exc)

    with (
        patch("openai.AsyncOpenAI", return_value=mock_client),
        pytest.raises(LLMAPIError) as exc,
    ):
        await GPTProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "gpt"


async def test_complete_log_does_not_leak_api_key(
    in_memory_keyring,
    loguru_messages: list[str],
) -> None:
    from app.services import keys as keys_service

    secret = "sk-do-not-leak-gpt-77777"
    keys_service.save_api_key("openai", secret)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_make_response())

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        await GPTProvider().complete([LLMMessage(role="user", content="oi")])

    combined = "\n".join(loguru_messages)
    assert combined, "loguru_messages vazio — fixture não capturou nada"
    assert secret not in combined
