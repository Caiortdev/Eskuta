"""
Testes do VAD (app.services.audio.vad).

Mockamos `silero_vad.load_silero_vad`, `read_audio` e
`get_speech_timestamps` pra evitar baixar modelo (~30MB) ou precisar
de áudio real nos testes unitários.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.audio import vad as vad_module
from app.services.audio.vad import (
    DEFAULT_MIN_SILENCE_MS,
    DEFAULT_MIN_SPEECH_MS,
    DEFAULT_THRESHOLD,
    SILERO_SAMPLE_RATE,
    SpeechSegment,
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
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value="fake-wav"),
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
    audio = _existing_audio(tmp_path)
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model"),
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value="fake-wav"),
        patch("silero_vad.get_speech_timestamps", return_value=[]) as gst,
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
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model") as load_mock,
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value="fake-wav"),
        patch("silero_vad.get_speech_timestamps", return_value=[]),
    ):
        detect_speech_segments(audio)
        detect_speech_segments(audio)
        detect_speech_segments(audio)

    assert load_mock.call_count == 1


def test_reset_model_cache_forces_reload(tmp_path: Path) -> None:
    audio = _existing_audio(tmp_path)
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model") as load_mock,
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value="fake-wav"),
        patch("silero_vad.get_speech_timestamps", return_value=[]),
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


def test_empty_timestamps_returns_empty_list(tmp_path: Path) -> None:
    audio = _existing_audio(tmp_path)
    with (
        patch("silero_vad.load_silero_vad", return_value="fake-model"),
        patch("app.services.audio.vad._read_audio_ffmpeg", return_value="fake-wav"),
        patch("silero_vad.get_speech_timestamps", return_value=[]),
    ):
        assert detect_speech_segments(audio) == []
