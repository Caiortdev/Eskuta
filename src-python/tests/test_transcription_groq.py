"""
Testes do adapter Groq (app.services.transcription.groq_provider).

Mockamos `groq.AsyncGroq` e exceptions do SDK pra não precisar bater
na API real. Validamos args (verbose_json, temperature=0.0,
language explícita), mapeamento de segments e tradução das exceptions
do SDK pras nossas (RateLimitError, ProviderAPIError, etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import groq
import pytest

from app.services.transcription.base import (
    ProviderAPIError,
    ProviderUnavailableError,
    RateLimitError,
    TranscriptionTimeoutError,
)
from app.services.transcription.groq_provider import (
    GROQ_COST_PER_HOUR,
    GROQ_MODEL,
    GroqProvider,
    _extract_retry_after,
    _segment_attr,
)


def _audio_file(tmp_path: Path) -> Path:
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"fake-audio-bytes")
    return f


def _make_response(
    *,
    text: str = "olá mundo",
    language: str = "portuguese",
    duration: float = 3.0,
    segments: list[Any] | None = None,
) -> MagicMock:
    """
    Resposta no formato verbose_json — atributos como mock pra
    cobrir tanto o caminho dict quanto attribute access.
    """
    response = MagicMock()
    response.text = text
    response.language = language
    response.duration = duration
    response.segments = segments if segments is not None else []
    return response


def test_name_is_groq() -> None:
    assert GroqProvider().name == "groq"


def test_is_available_false_without_api_key(in_memory_keyring) -> None:
    assert GroqProvider().is_available() is False


def test_is_available_true_with_api_key(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("groq", "sk-test")
    assert GroqProvider().is_available() is True


async def test_transcribe_missing_file_raises(tmp_path: Path, in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("groq", "sk-test")
    with pytest.raises(FileNotFoundError):
        await GroqProvider().transcribe(tmp_path / "missing.mp3")


async def test_transcribe_without_api_key_raises_unavailable(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    audio = _audio_file(tmp_path)
    with pytest.raises(ProviderUnavailableError) as exc:
        await GroqProvider().transcribe(audio)
    assert exc.value.provider == "groq"


async def test_transcribe_passes_correct_args_to_sdk(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("groq", "sk-test")
    audio = _audio_file(tmp_path)

    mock_response = _make_response(
        text="olá",
        language="portuguese",
        duration=2.5,
        segments=[{"start": 0.0, "end": 2.5, "text": "olá", "avg_logprob": -0.3}],
    )
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    with patch("groq.AsyncGroq", return_value=mock_client) as MockAsync:
        await GroqProvider().transcribe(audio, language="pt")

    MockAsync.assert_called_once_with(api_key="sk-test")
    call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == GROQ_MODEL
    assert call_kwargs["language"] == "pt"
    assert call_kwargs["response_format"] == "verbose_json"
    assert call_kwargs["temperature"] == 0.0  # anti-alucinação
    assert call_kwargs["file"][0] == audio.name


async def test_transcribe_maps_segments_dict_format(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("groq", "sk-test")
    audio = _audio_file(tmp_path)

    mock_response = _make_response(
        text="oi tudo bem",
        duration=4.0,
        segments=[
            {"start": 0.0, "end": 1.5, "text": "  oi ", "avg_logprob": -0.5},
            {"start": 2.0, "end": 4.0, "text": "tudo bem", "avg_logprob": -0.2},
        ],
    )
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    with patch("groq.AsyncGroq", return_value=mock_client):
        result = await GroqProvider().transcribe(audio)

    assert result.provider_used == "groq"
    assert result.model_used == GROQ_MODEL
    assert result.duration_sec == 4.0
    assert len(result.segments) == 2
    # Trim de whitespace e leitura via dict
    assert result.segments[0].text == "oi"
    assert result.segments[0].start_sec == 0.0
    assert result.segments[0].end_sec == 1.5
    assert result.segments[0].confidence == -0.5
    # Custo calculado pela duração
    assert result.cost_usd == pytest.approx(4.0 / 3600 * GROQ_COST_PER_HOUR)


async def test_transcribe_maps_segments_attribute_format(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    """SDK pode retornar segments como pydantic — testa o caminho de attribute access."""
    from app.services import keys as keys_service

    keys_service.save_api_key("groq", "sk-test")
    audio = _audio_file(tmp_path)

    # Simula pydantic com attribute access (sem ser dict)
    seg_obj = MagicMock(spec=["start", "end", "text", "avg_logprob"])
    seg_obj.start = 0.0
    seg_obj.end = 1.0
    seg_obj.text = " falando "
    seg_obj.avg_logprob = -0.1

    mock_response = _make_response(segments=[seg_obj])
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

    with patch("groq.AsyncGroq", return_value=mock_client):
        result = await GroqProvider().transcribe(audio)

    assert result.segments[0].text == "falando"
    assert result.segments[0].confidence == -0.1


async def test_transcribe_maps_rate_limit_exception(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("groq", "sk-test")
    audio = _audio_file(tmp_path)

    response_mock = MagicMock()
    response_mock.headers = {"retry-after": "7"}
    sdk_exc = groq.RateLimitError(
        message="429",
        response=response_mock,
        body=None,
    )

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(side_effect=sdk_exc)

    with (
        patch("groq.AsyncGroq", return_value=mock_client),
        pytest.raises(RateLimitError) as exc,
    ):
        await GroqProvider().transcribe(audio)

    assert exc.value.provider == "groq"
    assert exc.value.retry_after_sec == 7.0


async def test_transcribe_maps_timeout_exception(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("groq", "sk-test")
    audio = _audio_file(tmp_path)

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        side_effect=groq.APITimeoutError(request=MagicMock()),
    )

    with (
        patch("groq.AsyncGroq", return_value=mock_client),
        pytest.raises(TranscriptionTimeoutError) as exc,
    ):
        await GroqProvider().transcribe(audio)

    assert exc.value.provider == "groq"


async def test_transcribe_maps_api_error(tmp_path: Path, in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("groq", "sk-test")
    audio = _audio_file(tmp_path)

    sdk_exc = groq.APIError(
        message="server crashed",
        request=MagicMock(),
        body=None,
    )
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(side_effect=sdk_exc)

    with (
        patch("groq.AsyncGroq", return_value=mock_client),
        pytest.raises(ProviderAPIError) as exc,
    ):
        await GroqProvider().transcribe(audio)

    assert exc.value.provider == "groq"


async def test_transcribe_log_does_not_leak_api_key(
    tmp_path: Path,
    in_memory_keyring,
    loguru_messages: list[str],
) -> None:
    """Logs nunca podem conter o valor literal da chave."""
    from app.services import keys as keys_service

    secret = "groq-do-not-leak-12345"
    keys_service.save_api_key("groq", secret)
    audio = _audio_file(tmp_path)

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create = AsyncMock(
        return_value=_make_response(),
    )
    with patch("groq.AsyncGroq", return_value=mock_client):
        await GroqProvider().transcribe(audio)

    combined = "\n".join(loguru_messages)
    # Sanity: a fixture capturou ALGUMA coisa (provedor loga sucesso) —
    # garante que o teste não passa vacuamente.
    assert combined, "loguru_messages vazio — fixture não capturou nada"
    assert secret not in combined


# ============================================================
# Helpers internos
# ============================================================


def test_segment_attr_dict_path() -> None:
    assert _segment_attr({"start": 1.5}, "start") == 1.5
    assert _segment_attr({}, "start", 0.0) == 0.0


def test_segment_attr_object_path() -> None:
    obj = MagicMock(spec=["start"])
    obj.start = 2.5
    assert _segment_attr(obj, "start") == 2.5
    assert _segment_attr(obj, "missing", "default") == "default"


def test_extract_retry_after_with_header() -> None:
    exc = MagicMock()
    exc.response.headers = {"retry-after": "10"}
    assert _extract_retry_after(exc) == 10.0


def test_extract_retry_after_with_capitalized_header() -> None:
    exc = MagicMock()
    exc.response.headers = {"Retry-After": "5"}
    assert _extract_retry_after(exc) == 5.0


def test_extract_retry_after_no_response() -> None:
    exc = MagicMock()
    exc.response = None
    assert _extract_retry_after(exc) is None


def test_extract_retry_after_no_headers_attr() -> None:
    exc = MagicMock()
    exc.response = MagicMock(spec=[])
    assert _extract_retry_after(exc) is None


def test_extract_retry_after_invalid_value() -> None:
    exc = MagicMock()
    exc.response.headers = {"retry-after": "not-a-number"}
    assert _extract_retry_after(exc) is None
