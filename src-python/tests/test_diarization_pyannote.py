"""
Testes do serviço pyannote (app.services.diarization.pyannote_service).

Mockamos `pyannote.audio.Pipeline` pra não baixar modelo de ~500MB nem
precisar de HF_TOKEN real. O singleton é resetado antes de cada teste
pra que o estado de um não vaze pra outro.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.diarization import pyannote_service as svc
from app.services.diarization.pyannote_service import (
    PYANNOTE_MODEL,
    DiarizationError,
    DiarizationUnavailableError,
    SpeakerSegment,
    diarize,
    is_available,
    reset_pipeline_cache,
)


@pytest.fixture(autouse=True)
def _reset_pipeline():
    reset_pipeline_cache()
    yield
    reset_pipeline_cache()


def _audio_file(tmp_path: Path) -> Path:
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"")
    return f


def _make_track(start: float, end: float, speaker: str) -> tuple:
    """Simula a tupla (turn, track_id, speaker) que itertracks devolve."""
    turn = MagicMock()
    turn.start = start
    turn.end = end
    return (turn, None, speaker)


def _make_pipeline_return(tracks: list[tuple]) -> MagicMock:
    """Pipeline callable retorna Annotation com .itertracks(yield_label=True)."""
    annotation = MagicMock()
    annotation.itertracks.return_value = iter(tracks)
    return annotation


# ============================================================
# Dataclass SpeakerSegment
# ============================================================


def test_speaker_segment_duration() -> None:
    s = SpeakerSegment(start_sec=10.0, end_sec=15.5, speaker_id="SPEAKER_00")
    assert s.duration_sec == 5.5


def test_speaker_segment_is_frozen() -> None:
    s = SpeakerSegment(start_sec=0.0, end_sec=1.0, speaker_id="SPEAKER_00")
    with pytest.raises((AttributeError, TypeError)):
        s.speaker_id = "OUTRO"  # type: ignore[misc]


# ============================================================
# is_available
# ============================================================


def test_is_available_false_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", None)
    assert is_available() is False


def test_is_available_false_with_empty_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "")
    assert is_available() is False


def test_is_available_true_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    assert is_available() is True


# ============================================================
# diarize — pré-condições
# ============================================================


def test_diarize_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        diarize(tmp_path / "missing.mp3")


def test_diarize_without_token_raises_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", None)
    audio = _audio_file(tmp_path)
    with pytest.raises(DiarizationUnavailableError):
        diarize(audio)


# ============================================================
# diarize — mapeamento de output
# ============================================================


def test_diarize_returns_segments_sorted_by_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    audio = _audio_file(tmp_path)

    # Devolvido fora de ordem propositalmente
    tracks = [
        _make_track(5.0, 7.0, "SPEAKER_01"),
        _make_track(0.0, 2.0, "SPEAKER_00"),
        _make_track(2.5, 4.0, "SPEAKER_00"),
    ]
    pipeline_callable = MagicMock(return_value=_make_pipeline_return(tracks))

    with patch(
        "pyannote.audio.Pipeline.from_pretrained",
        return_value=pipeline_callable,
    ):
        segments = diarize(audio)

    assert [s.start_sec for s in segments] == [0.0, 2.5, 5.0]
    assert segments[0].speaker_id == "SPEAKER_00"
    assert segments[2].speaker_id == "SPEAKER_01"


def test_diarize_calls_pipeline_with_audio_path_string(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    audio = _audio_file(tmp_path)
    pipeline_callable = MagicMock(return_value=_make_pipeline_return([]))

    with patch(
        "pyannote.audio.Pipeline.from_pretrained",
        return_value=pipeline_callable,
    ):
        diarize(audio)

    pipeline_callable.assert_called_once_with(str(audio))


def test_diarize_empty_returns_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    audio = _audio_file(tmp_path)
    pipeline_callable = MagicMock(return_value=_make_pipeline_return([]))

    with patch(
        "pyannote.audio.Pipeline.from_pretrained",
        return_value=pipeline_callable,
    ):
        assert diarize(audio) == []


def test_diarize_log_includes_unique_speaker_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loguru_messages: list[str],
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    audio = _audio_file(tmp_path)
    tracks = [
        _make_track(0.0, 1.0, "SPEAKER_00"),
        _make_track(1.0, 2.0, "SPEAKER_01"),
        _make_track(2.0, 3.0, "SPEAKER_00"),
    ]
    pipeline_callable = MagicMock(return_value=_make_pipeline_return(tracks))

    with patch(
        "pyannote.audio.Pipeline.from_pretrained",
        return_value=pipeline_callable,
    ):
        diarize(audio)

    combined = "\n".join(loguru_messages)
    # 2 speakers únicos contados, mesmo com 3 tracks
    assert "unique_speakers" in combined
    assert "2" in combined


# ============================================================
# Singleton
# ============================================================


def test_pipeline_loaded_only_once_across_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    audio = _audio_file(tmp_path)
    pipeline_callable = MagicMock(return_value=_make_pipeline_return([]))

    with patch(
        "pyannote.audio.Pipeline.from_pretrained",
        return_value=pipeline_callable,
    ) as load_mock:
        diarize(audio)
        diarize(audio)
        diarize(audio)

    assert load_mock.call_count == 1


def test_reset_pipeline_cache_forces_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    audio = _audio_file(tmp_path)
    pipeline_callable = MagicMock(return_value=_make_pipeline_return([]))

    with patch(
        "pyannote.audio.Pipeline.from_pretrained",
        return_value=pipeline_callable,
    ) as load_mock:
        diarize(audio)
        reset_pipeline_cache()
        diarize(audio)

    assert load_mock.call_count == 2


def test_pipeline_passes_token_to_from_pretrained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_secret_token")
    audio = _audio_file(tmp_path)
    pipeline_callable = MagicMock(return_value=_make_pipeline_return([]))

    with patch(
        "pyannote.audio.Pipeline.from_pretrained",
        return_value=pipeline_callable,
    ) as load_mock:
        diarize(audio)

    load_mock.assert_called_once_with(
        PYANNOTE_MODEL,
        use_auth_token="hf_secret_token",
    )


# ============================================================
# Falhas
# ============================================================


def test_pipeline_load_failure_raises_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    audio = _audio_file(tmp_path)
    with (
        patch(
            "pyannote.audio.Pipeline.from_pretrained",
            side_effect=RuntimeError("403 forbidden — accept terms"),
        ),
        pytest.raises(DiarizationUnavailableError) as exc,
    ):
        diarize(audio)
    assert "403" in str(exc.value)


def test_diarize_runtime_failure_raises_diarization_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(svc.settings, "HF_TOKEN", "hf_xxx")
    audio = _audio_file(tmp_path)
    pipeline_callable = MagicMock(side_effect=RuntimeError("CUDA OOM"))

    with (
        patch(
            "pyannote.audio.Pipeline.from_pretrained",
            return_value=pipeline_callable,
        ),
        pytest.raises(DiarizationError) as exc,
    ):
        diarize(audio)
    assert "CUDA OOM" in str(exc.value)


def test_diarize_log_does_not_leak_hf_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loguru_messages: list[str],
) -> None:
    """HF_TOKEN é credencial; logs nunca podem mostrar o valor."""
    secret = "hf_super_secret_token_dont_leak"
    monkeypatch.setattr(svc.settings, "HF_TOKEN", secret)
    audio = _audio_file(tmp_path)
    pipeline_callable = MagicMock(return_value=_make_pipeline_return([]))

    with patch(
        "pyannote.audio.Pipeline.from_pretrained",
        return_value=pipeline_callable,
    ):
        diarize(audio)

    combined = "\n".join(loguru_messages)
    assert combined, "loguru_messages vazio — fixture não capturou nada"
    assert secret not in combined
