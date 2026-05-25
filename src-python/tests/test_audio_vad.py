"""
Testes do VAD (app.services.audio.vad).

Mockamos `silero_vad.load_silero_vad`, `_read_audio_ffmpeg` e
`get_speech_timestamps` pra evitar baixar modelo (~30MB) ou precisar
de áudio real nos testes unitários. Em testes que exercitam o
`NoSpeechDetectedError`, usamos torch.Tensor real (mas pequeno) pra
que `compute_volume_db` consiga rodar.
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import patch

import pytest
import torch

from app.services.audio import vad as vad_module
from app.services.audio.vad import (
    DEFAULT_MIN_SILENCE_MS,
    DEFAULT_MIN_SPEECH_MS,
    DEFAULT_THRESHOLD,
    SILENCE_DB_THRESHOLD,
    SILERO_SAMPLE_RATE,
    NoSpeechDetectedError,
    SpeechSegment,
    compute_volume_db,
    detect_speech_segments,
    reset_model_cache,
)


@pytest.fixture(autouse=True)
def _reset_vad_cache():
    reset_model_cache()
    yield
    reset_model_cache()


def _existing_audio(tmp_path: Path) -> Path:
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"")
    return f


# Tensores fixos pra simular o output do `_read_audio_ffmpeg` em testes:
# - SILENT: volume RMS = -inf dB (toda a amostra zerada)
# - SOUND_NO_SPEECH: tensor com volume médio acima de SILENCE_DB_THRESHOLD,
#   mas que faremos o silero retornar [] pra simular "tem som mas não é voz".
_SILENT_TENSOR = torch.zeros(SILERO_SAMPLE_RATE, dtype=torch.float32)
_SOUND_TENSOR = torch.full((SILERO_SAMPLE_RATE,), 0.3, dtype=torch.float32)


def test_input_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        detect_speech_segments(tmp_path / "missing.mp3")


def test_speech_segment_duration() -> None:
    s = SpeechSegment(start_sec=10.0, end_sec=13.5)
    assert s.duration_sec == 3.5


def test_detect_converts_raw_timestamps_to_seconds(tmp_path: Path) -> None:
    audio = _existing_audio(tmp_path)
    raw = [
        {"start": 0, "end": SILERO_SAMPLE_RATE},  # 0s -> 1s
        {"start": SILERO_SAMPLE_RATE * 3, "end": SILERO_SAMPLE_RATE * 5},  # 3s -> 5s
    ]

    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model"),
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value=_SOUND_TENSOR),
        patch("silero_vad.get_speech_timestamps", return_value=raw) as gst,
    ):
        segments = detect_speech_segments(audio)

    assert segments == [
        SpeechSegment(start_sec=0.0, end_sec=1.0),
        SpeechSegment(start_sec=3.0, end_sec=5.0),
    ]
    # Defaults do relatório técnico aplicados
    kwargs = gst.call_args.kwargs
    assert kwargs["sampling_rate"] == SILERO_SAMPLE_RATE
    assert kwargs["min_speech_duration_ms"] == DEFAULT_MIN_SPEECH_MS
    assert kwargs["min_silence_duration_ms"] == DEFAULT_MIN_SILENCE_MS
    assert kwargs["threshold"] == DEFAULT_THRESHOLD


def test_custom_thresholds_propagate(tmp_path: Path) -> None:
    """Thresholds chegam ao silero. Áudio tem som → no_speech, então levanta."""
    audio = _existing_audio(tmp_path)
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model"),
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value=_SOUND_TENSOR),
        patch("silero_vad.get_speech_timestamps", return_value=[]) as gst,
        pytest.raises(NoSpeechDetectedError),
    ):
        detect_speech_segments(
            audio,
            min_speech_duration_ms=100,
            min_silence_duration_ms=300,
            threshold=0.7,
        )

    kwargs = gst.call_args.kwargs
    assert kwargs["min_speech_duration_ms"] == 100
    assert kwargs["min_silence_duration_ms"] == 300
    assert kwargs["threshold"] == 0.7


def test_model_loaded_only_once_across_calls(tmp_path: Path) -> None:
    """Singleton: chamadas subsequentes não recarregam o modelo Silero."""
    audio = _existing_audio(tmp_path)
    raw = [{"start": 0, "end": SILERO_SAMPLE_RATE}]
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model") as load_mock,
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value=_SOUND_TENSOR),
        patch("silero_vad.get_speech_timestamps", return_value=raw),
    ):
        detect_speech_segments(audio)
        detect_speech_segments(audio)
        detect_speech_segments(audio)

    assert load_mock.call_count == 1


def test_reset_model_cache_forces_reload(tmp_path: Path) -> None:
    audio = _existing_audio(tmp_path)
    raw = [{"start": 0, "end": SILERO_SAMPLE_RATE}]
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model") as load_mock,
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value=_SOUND_TENSOR),
        patch("silero_vad.get_speech_timestamps", return_value=raw),
    ):
        detect_speech_segments(audio)
        reset_model_cache()
        detect_speech_segments(audio)

    assert load_mock.call_count == 2


def test_get_model_internal_singleton() -> None:
    """Verifica o singleton interno (cobre _get_model sem passar por detect)."""
    with patch("silero_vad.load_silero_vad", return_value="x") as load_mock:
        m1 = vad_module._get_model()
        m2 = vad_module._get_model()
    assert m1 is m2
    assert load_mock.call_count == 1


def test_silent_audio_raises_with_silent_reason(tmp_path: Path) -> None:
    """Tensor zerado → reason='silent_audio', mensagem fala em microfone."""
    audio = _existing_audio(tmp_path)
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model"),
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value=_SILENT_TENSOR),
        patch("silero_vad.get_speech_timestamps", return_value=[]),
    ):
        with pytest.raises(NoSpeechDetectedError) as exc_info:
            detect_speech_segments(audio)

    err = exc_info.value
    assert err.reason == "silent_audio"
    assert err.volume_db == -math.inf
    assert err.duration_sec == 1.0
    assert "microfone" in str(err).lower()


def test_sound_no_speech_raises_with_no_speech_reason(tmp_path: Path) -> None:
    """Tensor com som mas silero vazio → reason='no_speech'."""
    audio = _existing_audio(tmp_path)
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model"),
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value=_SOUND_TENSOR),
        patch("silero_vad.get_speech_timestamps", return_value=[]),
    ):
        with pytest.raises(NoSpeechDetectedError) as exc_info:
            detect_speech_segments(audio)

    err = exc_info.value
    assert err.reason == "no_speech"
    assert err.volume_db > SILENCE_DB_THRESHOLD
    assert "música" in str(err).lower() or "fala humana" in str(err).lower()


def test_compute_volume_db_zero_tensor_is_minus_inf() -> None:
    assert compute_volume_db(torch.zeros(100)) == -math.inf


def test_compute_volume_db_empty_tensor_is_minus_inf() -> None:
    assert compute_volume_db(torch.zeros(0)) == -math.inf


def test_compute_volume_db_full_scale_sine_is_zero_dbfs() -> None:
    """RMS dum sinal full-scale dá ≈ 0 dBFS (limite superior do tensor float [-1,1])."""
    # Tensor com ones em uma metade e zeros na outra dá RMS ≈ 0.707 = -3dBFS.
    # Usamos full ones pra ter rms=1.0 → 0 dBFS exato.
    t = torch.ones(1000, dtype=torch.float32)
    assert compute_volume_db(t) == pytest.approx(0.0, abs=1e-6)


def test_no_speech_error_carries_metadata() -> None:
    err = NoSpeechDetectedError("msg", reason="silent_audio", volume_db=-95.0, duration_sec=12.3)
    assert str(err) == "msg"
    assert err.reason == "silent_audio"
    assert err.volume_db == -95.0
    assert err.duration_sec == 12.3
