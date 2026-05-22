"""
Testes do adapter AssemblyAI (app.services.transcription.assemblyai_provider).

Mockamos o módulo `assemblyai` inteiro pra não precisar bater na API
real. Validamos config (language_code, punctuate), mapeamento de
utterances → segments com timestamps em segundos (não ms), e tradução
das condições de erro (status.error, rate limit detectado por mensagem).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import assemblyai as aai
import pytest

from app.services.transcription.assemblyai_provider import (
    ASSEMBLYAI_COST_PER_HOUR,
    ASSEMBLYAI_MODEL,
    AssemblyAIProvider,
    _build_segments,
)
from app.services.transcription.base import (
    ProviderAPIError,
    ProviderUnavailableError,
    RateLimitError,
)


def _audio_file(tmp_path: Path) -> Path:
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"fake-audio-bytes")
    return f


def _make_transcript(
    *,
    status: object | None = None,
    text: str = "olá mundo",
    duration: float = 5.0,
    utterances: list[MagicMock] | None = None,
    error: str | None = None,
) -> MagicMock:
    """Constrói um transcript fake compatível com o SDK assemblyai."""
    transcript = MagicMock()
    transcript.status = status if status is not None else aai.TranscriptStatus.completed
    transcript.text = text
    transcript.audio_duration = duration
    transcript.utterances = utterances
    transcript.error = error
    return transcript


def _utterance(
    *,
    start_ms: int,
    end_ms: int,
    text: str,
    speaker: str | None = None,
    confidence: float | None = 0.92,
) -> MagicMock:
    u = MagicMock()
    u.start = start_ms
    u.end = end_ms
    u.text = text
    u.speaker = speaker
    u.confidence = confidence
    return u


def test_name_is_assemblyai() -> None:
    assert AssemblyAIProvider().name == "assemblyai"


def test_is_available_false_without_api_key(in_memory_keyring) -> None:
    assert AssemblyAIProvider().is_available() is False


def test_is_available_true_with_api_key(in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    assert AssemblyAIProvider().is_available() is True


async def test_transcribe_missing_file_raises(tmp_path: Path, in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    with pytest.raises(FileNotFoundError):
        await AssemblyAIProvider().transcribe(tmp_path / "missing.mp3")


async def test_transcribe_without_api_key_raises_unavailable(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    audio = _audio_file(tmp_path)
    with pytest.raises(ProviderUnavailableError):
        await AssemblyAIProvider().transcribe(audio)


async def test_transcribe_passes_correct_config(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    audio = _audio_file(tmp_path)

    transcript = _make_transcript()
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = transcript

    with (
        patch("assemblyai.Transcriber", return_value=mock_transcriber) as TranscriberCls,
        patch("assemblyai.TranscriptionConfig", wraps=aai.TranscriptionConfig) as ConfigCls,
    ):
        await AssemblyAIProvider().transcribe(audio, language="pt")

    config_kwargs = ConfigCls.call_args.kwargs
    assert config_kwargs["language_code"] == "pt"
    assert config_kwargs["punctuate"] is True
    assert config_kwargs["format_text"] is True
    # Transcriber recebeu o config
    assert "config" in TranscriberCls.call_args.kwargs
    # Áudio chega como string (path absoluto via str(audio_path))
    mock_transcriber.transcribe.assert_called_once_with(str(audio))


async def test_transcribe_sets_api_key_on_sdk_settings(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    """Verifica que aai.settings.api_key recebe a chave do keyring."""
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    audio = _audio_file(tmp_path)

    transcript = _make_transcript()
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = transcript

    with patch("assemblyai.Transcriber", return_value=mock_transcriber):
        # Reset antes
        aai.settings.api_key = None
        await AssemblyAIProvider().transcribe(audio)
        assert aai.settings.api_key == "sk-aai-test"


async def test_transcribe_maps_utterances_to_segments(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    """Utterances vêm com ms — segments devem sair em segundos."""
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    audio = _audio_file(tmp_path)

    utterances = [
        _utterance(start_ms=0, end_ms=2500, text="  oi  ", speaker="A", confidence=0.95),
        _utterance(start_ms=3000, end_ms=5000, text="tudo bem", speaker="B", confidence=0.88),
    ]
    transcript = _make_transcript(
        text="oi tudo bem",
        duration=5.0,
        utterances=utterances,
    )

    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = transcript

    with patch("assemblyai.Transcriber", return_value=mock_transcriber):
        result = await AssemblyAIProvider().transcribe(audio)

    assert result.provider_used == "assemblyai"
    assert result.model_used == ASSEMBLYAI_MODEL
    assert len(result.segments) == 2
    # ms → segundos
    assert result.segments[0].start_sec == 0.0
    assert result.segments[0].end_sec == 2.5
    assert result.segments[0].text == "oi"
    assert result.segments[0].speaker == "A"
    assert result.segments[0].confidence == 0.95
    assert result.segments[1].start_sec == 3.0
    assert result.cost_usd == pytest.approx(5.0 / 3600 * ASSEMBLYAI_COST_PER_HOUR)


async def test_transcribe_falls_back_to_single_segment_when_no_utterances(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    """Sem utterances, devolve UM segment com toda a transcrição."""
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    audio = _audio_file(tmp_path)

    transcript = _make_transcript(
        text="texto inteiro sem speaker labels",
        duration=10.0,
        utterances=None,
    )
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = transcript

    with patch("assemblyai.Transcriber", return_value=mock_transcriber):
        result = await AssemblyAIProvider().transcribe(audio)

    assert len(result.segments) == 1
    assert result.segments[0].start_sec == 0.0
    assert result.segments[0].end_sec == 10.0
    assert result.segments[0].text == "texto inteiro sem speaker labels"


async def test_transcribe_error_status_raises_api_error(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    audio = _audio_file(tmp_path)

    transcript = _make_transcript(
        status=aai.TranscriptStatus.error,
        error="server boom",
    )
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = transcript

    with (
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
        pytest.raises(ProviderAPIError) as exc,
    ):
        await AssemblyAIProvider().transcribe(audio)

    assert exc.value.provider == "assemblyai"


async def test_transcribe_error_status_with_rate_limit_message_raises_rate_limit(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    """Se o erro do AssemblyAI mencionar rate limit, devolvemos RateLimitError."""
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    audio = _audio_file(tmp_path)

    transcript = _make_transcript(
        status=aai.TranscriptStatus.error,
        error="Rate limit exceeded, try again later",
    )
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = transcript

    with (
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
        pytest.raises(RateLimitError) as exc,
    ):
        await AssemblyAIProvider().transcribe(audio)

    assert exc.value.provider == "assemblyai"


async def test_transcribe_sdk_exception_with_rate_limit_message(
    tmp_path: Path,
    in_memory_keyring,
) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    audio = _audio_file(tmp_path)

    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.side_effect = RuntimeError("HTTP 429: Rate Limit hit")

    with (
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
        pytest.raises(RateLimitError),
    ):
        await AssemblyAIProvider().transcribe(audio)


async def test_transcribe_sdk_exception_generic(tmp_path: Path, in_memory_keyring) -> None:
    from app.services import keys as keys_service

    keys_service.save_api_key("assemblyai", "sk-aai-test")
    audio = _audio_file(tmp_path)

    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.side_effect = RuntimeError("connection refused")

    with (
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
        pytest.raises(ProviderAPIError),
    ):
        await AssemblyAIProvider().transcribe(audio)


async def test_transcribe_log_does_not_leak_api_key(
    tmp_path: Path,
    in_memory_keyring,
    loguru_messages: list[str],
) -> None:
    from app.services import keys as keys_service

    secret = "assemblyai-do-not-leak-987654"
    keys_service.save_api_key("assemblyai", secret)
    audio = _audio_file(tmp_path)

    transcript = _make_transcript()
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = transcript

    with patch("assemblyai.Transcriber", return_value=mock_transcriber):
        await AssemblyAIProvider().transcribe(audio)

    combined = "\n".join(loguru_messages)
    assert combined, "loguru_messages vazio — fixture não capturou nada"
    assert secret not in combined


# ============================================================
# Helpers internos
# ============================================================


def test_build_segments_from_utterances() -> None:
    transcript = _make_transcript(
        utterances=[
            _utterance(start_ms=500, end_ms=1500, text="oi", confidence=0.9),
        ],
    )
    segments = _build_segments(transcript)
    assert segments[0].start_sec == 0.5
    assert segments[0].end_sec == 1.5
    assert segments[0].confidence == 0.9


def test_build_segments_single_when_no_utterances() -> None:
    transcript = _make_transcript(text="texto", duration=3.0, utterances=None)
    segments = _build_segments(transcript)
    assert len(segments) == 1
    assert segments[0].text == "texto"
    assert segments[0].end_sec == 3.0


def test_build_segments_handles_none_confidence_on_utterance() -> None:
    u = _utterance(start_ms=0, end_ms=1000, text="oi", confidence=None)
    transcript = _make_transcript(utterances=[u])
    segments = _build_segments(transcript)
    assert segments[0].confidence is None
