"""
Testes do adapter Claude (app.services.llm.claude_provider).

Mockamos `anthropic.AsyncAnthropic` e exceptions do SDK pra não bater
na API real. Validamos: separação system/messages, JSON instruction
injetada no system, mapeamento de exceptions, cálculo de custo.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from app.services.llm.base import (
    LLMAPIError,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.services.llm.claude_provider import (
    CLAUDE_INPUT_PER_MTOK,
    CLAUDE_MODEL,
    CLAUDE_OUTPUT_PER_MTOK,
    ClaudeProvider,
)


def _make_response(
    *,
    text: str = "olá",
    model: str = CLAUDE_MODEL,
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> MagicMock:
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.model = model
    response.usage = MagicMock()
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    return response


def test_name_and_default_model() -> None:
    p = ClaudeProvider()
    assert p.name == "claude"
    assert p.default_model == CLAUDE_MODEL


def test_is_available_false_without_key(in_memory_keyring) -> None:
    assert ClaudeProvider().is_available() is False


def test_is_available_true_with_key(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")
    assert ClaudeProvider().is_available() is True


async def test_complete_without_key_raises_unavailable(in_memory_keyring) -> None:
    with pytest.raises(LLMProviderUnavailableError):
        await ClaudeProvider().complete([LLMMessage(role="user", content="oi")])


async def test_complete_separates_system_from_messages(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_make_response())

    with patch("anthropic.AsyncAnthropic", return_value=mock_client) as MockCls:
        await ClaudeProvider().complete(
            [
                LLMMessage(role="system", content="Você é um assistente"),
                LLMMessage(role="user", content="oi"),
                LLMMessage(role="assistant", content="olá!"),
                LLMMessage(role="user", content="tudo bem?"),
            ],
            max_tokens=500,
            temperature=0.5,
        )

    MockCls.assert_called_once_with(api_key="sk-ant-test")
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == CLAUDE_MODEL
    assert call_kwargs["max_tokens"] == 500
    assert call_kwargs["temperature"] == 0.5
    assert "Você é um assistente" in call_kwargs["system"]
    # Apenas user/assistant entram em messages
    assert call_kwargs["messages"] == [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "olá!"},
        {"role": "user", "content": "tudo bem?"},
    ]


async def test_complete_concatenates_multiple_system_messages(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_make_response())

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await ClaudeProvider().complete(
            [
                LLMMessage(role="system", content="parte 1"),
                LLMMessage(role="system", content="parte 2"),
                LLMMessage(role="user", content="oi"),
            ]
        )

    system = mock_client.messages.create.call_args.kwargs["system"]
    assert "parte 1" in system
    assert "parte 2" in system


async def test_complete_json_mode_injects_instruction(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_make_response())

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await ClaudeProvider().complete(
            [LLMMessage(role="user", content="oi")],
            response_format={"type": "json_object"},
        )

    system = mock_client.messages.create.call_args.kwargs["system"]
    assert "JSON" in system
    assert "markdown" in system.lower() or "fences" in system.lower()


async def test_complete_returns_normalized_response(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        return_value=_make_response(
            text="resposta final",
            input_tokens=1000,
            output_tokens=500,
        )
    )

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await ClaudeProvider().complete([LLMMessage(role="user", content="oi")])

    assert result.provider == "claude"
    assert result.content == "resposta final"
    assert result.tokens_input == 1000
    assert result.tokens_output == 500
    expected_cost = (
        1000 / 1_000_000 * CLAUDE_INPUT_PER_MTOK + 500 / 1_000_000 * CLAUDE_OUTPUT_PER_MTOK
    )
    assert result.cost_usd == pytest.approx(expected_cost)


async def test_complete_concatenates_multiple_content_blocks(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    response = _make_response()
    block_a = MagicMock(spec=["text"])
    block_a.text = "parte A "
    block_b = MagicMock(spec=["text"])
    block_b.text = "parte B"
    response.content = [block_a, block_b]

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=response)

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await ClaudeProvider().complete([LLMMessage(role="user", content="oi")])
    assert result.content == "parte A parte B"


async def test_complete_uses_custom_model(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_make_response(model="custom-x"))

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await ClaudeProvider().complete(
            [LLMMessage(role="user", content="oi")],
            model="claude-opus-4-7",
        )
    assert mock_client.messages.create.call_args.kwargs["model"] == "claude-opus-4-7"


async def test_complete_maps_rate_limit(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    response_mock = MagicMock()
    response_mock.headers = {}
    sdk_exc = anthropic.RateLimitError(
        message="429",
        response=response_mock,
        body=None,
    )
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=sdk_exc)

    with (
        patch("anthropic.AsyncAnthropic", return_value=mock_client),
        pytest.raises(LLMRateLimitError) as exc,
    ):
        await ClaudeProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "claude"


async def test_complete_maps_timeout(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=anthropic.APITimeoutError(request=MagicMock())
    )

    with (
        patch("anthropic.AsyncAnthropic", return_value=mock_client),
        pytest.raises(LLMTimeoutError) as exc,
    ):
        await ClaudeProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "claude"


async def test_complete_maps_api_error(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("anthropic", "sk-ant-test")

    sdk_exc = anthropic.APIError(
        message="server crashed",
        request=MagicMock(),
        body=None,
    )
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=sdk_exc)

    with (
        patch("anthropic.AsyncAnthropic", return_value=mock_client),
        pytest.raises(LLMAPIError) as exc,
    ):
        await ClaudeProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "claude"


async def test_complete_log_does_not_leak_api_key(
    in_memory_keyring,
    loguru_messages: list[str],
) -> None:
    from app.services import keys as keys_service

    secret = "sk-ant-do-not-leak-99999"
    keys_service.save_api_key("anthropic", secret)

    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_make_response())

    with patch("anthropic.AsyncAnthropic", return_value=mock_client):
        await ClaudeProvider().complete([LLMMessage(role="user", content="oi")])

    combined = "\n".join(loguru_messages)
    assert combined, "loguru_messages vazio — fixture não capturou nada"
    assert secret not in combined
