"""
Testes do adapter Gemini (app.services.llm.gemini_provider).

Mockamos `google.genai.Client` pra não bater na API real. Validamos:
- system → config.system_instruction
- role "assistant" → "model"
- contents em formato {role, parts:[{text}]}
- JSON mode via response_mime_type
- mapeamento de exceptions, cálculo de custo
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors as genai_errors

from app.services.llm.base import (
    LLMAPIError,
    LLMMessage,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.services.llm.gemini_provider import (
    GEMINI_INPUT_PER_MTOK,
    GEMINI_MODEL,
    GEMINI_OUTPUT_PER_MTOK,
    GeminiProvider,
)


def _make_response(
    *,
    text: str = "olá",
    prompt_tokens: int = 100,
    candidates_tokens: int = 50,
) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.usage_metadata = MagicMock()
    response.usage_metadata.prompt_token_count = prompt_tokens
    response.usage_metadata.candidates_token_count = candidates_tokens
    return response


def _make_api_error(message: str) -> Exception:
    """Cria APIError do google-genai (assinatura pode variar entre versões)."""
    try:
        return genai_errors.APIError(code=500, response_json={"error": {"message": message}})
    except TypeError:
        # Fallback se a assinatura for diferente
        return genai_errors.APIError(message)


def test_name_and_default_model() -> None:
    p = GeminiProvider()
    assert p.name == "gemini"
    assert p.default_model == GEMINI_MODEL


def test_is_available_false_without_key(in_memory_keyring) -> None:
    assert GeminiProvider().is_available() is False


def test_is_available_true_with_key(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")
    assert GeminiProvider().is_available() is True


async def test_complete_without_key_raises_unavailable(in_memory_keyring) -> None:
    with pytest.raises(LLMProviderUnavailableError):
        await GeminiProvider().complete([LLMMessage(role="user", content="oi")])


async def test_complete_maps_system_to_config(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=_make_response())

    with patch("google.genai.Client", return_value=mock_client):
        await GeminiProvider().complete(
            [
                LLMMessage(role="system", content="você é assistente"),
                LLMMessage(role="user", content="oi"),
            ]
        )

    call = mock_client.aio.models.generate_content.call_args
    assert call.kwargs["model"] == GEMINI_MODEL
    # system_instruction está no config (objeto pydantic)
    config = call.kwargs["config"]
    assert "você é assistente" in config.system_instruction
    # contents NÃO inclui system
    assert call.kwargs["contents"] == [{"role": "user", "parts": [{"text": "oi"}]}]


async def test_complete_maps_assistant_to_model(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=_make_response())

    with patch("google.genai.Client", return_value=mock_client):
        await GeminiProvider().complete(
            [
                LLMMessage(role="user", content="oi"),
                LLMMessage(role="assistant", content="olá!"),
                LLMMessage(role="user", content="tudo bem?"),
            ]
        )

    contents = mock_client.aio.models.generate_content.call_args.kwargs["contents"]
    assert contents == [
        {"role": "user", "parts": [{"text": "oi"}]},
        {"role": "model", "parts": [{"text": "olá!"}]},
        {"role": "user", "parts": [{"text": "tudo bem?"}]},
    ]


async def test_complete_json_mode_sets_response_mime(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=_make_response())

    with patch("google.genai.Client", return_value=mock_client):
        await GeminiProvider().complete(
            [LLMMessage(role="user", content="oi")],
            response_format={"type": "json_object"},
        )

    config = mock_client.aio.models.generate_content.call_args.kwargs["config"]
    assert config.response_mime_type == "application/json"


async def test_complete_returns_normalized_response(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        return_value=_make_response(
            text="resposta final",
            prompt_tokens=10000,
            candidates_tokens=5000,
        )
    )

    with patch("google.genai.Client", return_value=mock_client):
        result = await GeminiProvider().complete([LLMMessage(role="user", content="oi")])

    assert result.provider == "gemini"
    assert result.model == GEMINI_MODEL
    assert result.content == "resposta final"
    assert result.tokens_input == 10000
    assert result.tokens_output == 5000
    expected_cost = (
        10000 / 1_000_000 * GEMINI_INPUT_PER_MTOK + 5000 / 1_000_000 * GEMINI_OUTPUT_PER_MTOK
    )
    assert result.cost_usd == pytest.approx(expected_cost)


async def test_complete_uses_custom_model(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=_make_response())

    with patch("google.genai.Client", return_value=mock_client):
        await GeminiProvider().complete(
            [LLMMessage(role="user", content="oi")],
            model="gemini-2.5-pro",
        )

    assert mock_client.aio.models.generate_content.call_args.kwargs["model"] == "gemini-2.5-pro"


async def test_complete_handles_none_text(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    response = _make_response()
    response.text = None

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=response)

    with patch("google.genai.Client", return_value=mock_client):
        result = await GeminiProvider().complete([LLMMessage(role="user", content="oi")])
    assert result.content == ""


async def test_complete_handles_missing_usage_metadata(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    response = _make_response()
    response.usage_metadata = None

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=response)

    with patch("google.genai.Client", return_value=mock_client):
        result = await GeminiProvider().complete([LLMMessage(role="user", content="oi")])
    assert result.tokens_input == 0
    assert result.tokens_output == 0
    assert result.cost_usd == 0.0


async def test_complete_maps_rate_limit_from_message(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=_make_api_error("Rate limit exceeded for project")
    )

    with (
        patch("google.genai.Client", return_value=mock_client),
        pytest.raises(LLMRateLimitError) as exc,
    ):
        await GeminiProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "gemini"


async def test_complete_maps_timeout_from_message(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=_make_api_error("Deadline exceeded")
    )

    with (
        patch("google.genai.Client", return_value=mock_client),
        pytest.raises(LLMTimeoutError) as exc,
    ):
        await GeminiProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "gemini"


async def test_complete_maps_generic_api_error(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("google", "AIza-test")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=_make_api_error("internal server error")
    )

    with (
        patch("google.genai.Client", return_value=mock_client),
        pytest.raises(LLMAPIError) as exc,
    ):
        await GeminiProvider().complete([LLMMessage(role="user", content="oi")])
    assert exc.value.provider == "gemini"


async def test_complete_log_does_not_leak_api_key(
    in_memory_keyring,
    loguru_messages: list[str],
) -> None:
    from app.services import keys as keys_service

    secret = "AIza-do-not-leak-44444"
    keys_service.save_api_key("google", secret)

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=_make_response())

    with patch("google.genai.Client", return_value=mock_client):
        await GeminiProvider().complete([LLMMessage(role="user", content="oi")])

    combined = "\n".join(loguru_messages)
    assert combined, "loguru_messages vazio — fixture não capturou nada"
    assert secret not in combined
