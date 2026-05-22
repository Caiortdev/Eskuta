"""
Testes dos tipos e exceptions compartilhados da camada de transcrição.
"""

from __future__ import annotations

import pytest

from app.services.transcription.base import (
    KNOWN_TRANSCRIPTION_PROVIDERS,
    AllProvidersFailedError,
    ProviderAPIError,
    ProviderUnavailableError,
    RateLimitError,
    TranscriptionError,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionTimeoutError,
)


def test_known_providers_constant_is_complete() -> None:
    """Mexer em KNOWN_TRANSCRIPTION_PROVIDERS quebra o teste — protege contra typo."""
    assert KNOWN_TRANSCRIPTION_PROVIDERS == ("groq", "assemblyai")


def test_transcription_segment_duration() -> None:
    seg = TranscriptionSegment(start_sec=10.0, end_sec=13.5, text="oi")
    assert seg.duration_sec == 3.5


def test_transcription_segment_is_frozen() -> None:
    seg = TranscriptionSegment(start_sec=0.0, end_sec=1.0, text="oi")
    with pytest.raises((AttributeError, TypeError)):
        seg.text = "outra coisa"  # type: ignore[misc]


def test_transcription_segment_defaults_speaker_and_confidence_to_none() -> None:
    seg = TranscriptionSegment(start_sec=0.0, end_sec=1.0, text="oi")
    assert seg.speaker is None
    assert seg.confidence is None


def test_transcription_result_default_cost_is_zero() -> None:
    result = TranscriptionResult(
        full_text="oi",
        segments=[],
        language="pt",
        duration_sec=1.0,
        provider_used="groq",
        model_used="whisper-large-v3-turbo",
    )
    assert result.cost_usd == 0.0


def test_transcription_error_default_provider_is_none() -> None:
    err = TranscriptionError("falha")
    assert str(err) == "falha"
    assert err.provider is None


def test_transcription_error_with_provider() -> None:
    err = TranscriptionError("falha", provider="groq")
    assert err.provider == "groq"


def test_rate_limit_error_carries_retry_after() -> None:
    err = RateLimitError("429", provider="groq", retry_after_sec=12.5)
    assert err.retry_after_sec == 12.5
    assert err.provider == "groq"


def test_rate_limit_error_retry_after_optional() -> None:
    err = RateLimitError("429", provider="groq")
    assert err.retry_after_sec is None


def test_subclasses_inherit_from_transcription_error() -> None:
    # Todas as subclasses devem ser pegáveis com `except TranscriptionError`
    assert issubclass(ProviderUnavailableError, TranscriptionError)
    assert issubclass(RateLimitError, TranscriptionError)
    assert issubclass(ProviderAPIError, TranscriptionError)
    assert issubclass(TranscriptionTimeoutError, TranscriptionError)
    assert issubclass(AllProvidersFailedError, TranscriptionError)


def test_all_providers_failed_carries_failures_dict() -> None:
    err = AllProvidersFailedError(
        "todos falharam",
        failures={"groq": "auth", "assemblyai": "timeout"},
    )
    assert err.failures == {"groq": "auth", "assemblyai": "timeout"}


def test_all_providers_failed_failures_defaults_to_empty() -> None:
    err = AllProvidersFailedError("vazio")
    assert err.failures == {}
