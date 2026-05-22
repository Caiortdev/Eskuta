"""
Testes do cache de VAD (app.services.audio.vad_cache).

Mockamos `detect_speech_segments` pra não rodar Silero real. Usamos
APP_DIR redirecionado pra tmp_path via monkeypatch (não polui o
diretório real do usuário).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.audio import vad_cache
from app.services.audio.vad import SpeechSegment
from app.services.audio.vad_cache import (
    CACHE_SCHEMA_VERSION,
    DEFAULT_CACHE_TTL_SEC,
    _audio_fingerprint,
    _cache_key,
    cleanup_expired,
    detect_speech_segments_cached,
)


@pytest.fixture
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Redireciona APP_DIR pra tmp_path. Cache de VAD fica em tmp."""
    monkeypatch.setattr(vad_cache.settings, "APP_DIR", tmp_path / "eskuta")
    return tmp_path / "eskuta" / "cache" / "vad"


def _make_audio(tmp_path: Path, *, size_bytes: int = 1024) -> Path:
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"x" * size_bytes)
    return f


def _fake_segments() -> list[SpeechSegment]:
    return [
        SpeechSegment(start_sec=0.0, end_sec=2.5),
        SpeechSegment(start_sec=3.0, end_sec=8.0),
    ]


# ============================================================
# Constants
# ============================================================


def test_default_ttl_is_30_days() -> None:
    assert DEFAULT_CACHE_TTL_SEC == 30 * 24 * 60 * 60


def test_schema_version_starts_at_1() -> None:
    assert CACHE_SCHEMA_VERSION == 1


# ============================================================
# Audio fingerprint
# ============================================================


def test_audio_fingerprint_same_file_same_hash(tmp_path: Path) -> None:
    audio = _make_audio(tmp_path)
    assert _audio_fingerprint(audio) == _audio_fingerprint(audio)


def test_audio_fingerprint_different_content_different_hash(tmp_path: Path) -> None:
    a = tmp_path / "a.mp3"
    a.write_bytes(b"content-A")
    b = tmp_path / "b.mp3"
    b.write_bytes(b"content-B")
    assert _audio_fingerprint(a) != _audio_fingerprint(b)


def test_audio_fingerprint_handles_large_file(tmp_path: Path) -> None:
    """File grande (>2MB) usa head + tail. Não deve crashar."""
    big = tmp_path / "big.mp3"
    big.write_bytes(b"x" * (4 * 1024 * 1024))
    assert len(_audio_fingerprint(big)) == 32


# ============================================================
# Cache key
# ============================================================


def test_cache_key_includes_params_hash() -> None:
    fp = "abc"
    k1 = _cache_key(fp, min_speech_ms=250, min_silence_ms=500, threshold=0.5)
    k2 = _cache_key(fp, min_speech_ms=300, min_silence_ms=500, threshold=0.5)
    assert k1 != k2


def test_cache_key_same_params_same_key() -> None:
    fp = "abc"
    k1 = _cache_key(fp, min_speech_ms=250, min_silence_ms=500, threshold=0.5)
    k2 = _cache_key(fp, min_speech_ms=250, min_silence_ms=500, threshold=0.5)
    assert k1 == k2


def test_cache_key_threshold_changes_key() -> None:
    fp = "abc"
    k1 = _cache_key(fp, min_speech_ms=250, min_silence_ms=500, threshold=0.5)
    k2 = _cache_key(fp, min_speech_ms=250, min_silence_ms=500, threshold=0.7)
    assert k1 != k2


# ============================================================
# detect_speech_segments_cached — primeira chamada (miss)
# ============================================================


async def test_first_call_is_cache_miss_runs_real_vad(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio = _make_audio(tmp_path)
    real_mock = MagicMock(return_value=_fake_segments())
    with patch("app.services.audio.vad_cache.detect_speech_segments", real_mock):
        result = detect_speech_segments_cached(audio)

    assert len(result) == 2
    real_mock.assert_called_once()
    # Cache foi escrito
    assert any(isolated_cache.glob("*.json"))


# ============================================================
# Segunda chamada com mesmos params (hit)
# ============================================================


def test_second_call_same_params_uses_cache(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio = _make_audio(tmp_path)
    real_mock = MagicMock(return_value=_fake_segments())
    with patch("app.services.audio.vad_cache.detect_speech_segments", real_mock):
        detect_speech_segments_cached(audio)
        # 2a chamada — não deveria chamar o real
        result = detect_speech_segments_cached(audio)

    assert real_mock.call_count == 1  # só 1x: a segunda foi cache hit
    assert len(result) == 2


def test_cached_results_have_correct_types(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    """Cache deserializa corretamente — segments são SpeechSegment de novo."""
    audio = _make_audio(tmp_path)
    with patch(
        "app.services.audio.vad_cache.detect_speech_segments",
        return_value=_fake_segments(),
    ):
        detect_speech_segments_cached(audio)  # popula cache
        cached_result = detect_speech_segments_cached(audio)

    assert all(isinstance(s, SpeechSegment) for s in cached_result)
    assert cached_result[0].start_sec == 0.0
    assert cached_result[0].end_sec == 2.5


# ============================================================
# Params diferentes (miss apesar de mesmo áudio)
# ============================================================


def test_different_params_force_recompute(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio = _make_audio(tmp_path)
    real_mock = MagicMock(return_value=_fake_segments())
    with patch("app.services.audio.vad_cache.detect_speech_segments", real_mock):
        detect_speech_segments_cached(audio, threshold=0.5)
        # Threshold diferente — cache MISS
        detect_speech_segments_cached(audio, threshold=0.7)

    assert real_mock.call_count == 2


def test_different_audio_force_recompute(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio_a = tmp_path / "a.mp3"
    audio_a.write_bytes(b"audio-a-content")
    audio_b = tmp_path / "b.mp3"
    audio_b.write_bytes(b"audio-b-content-diferente")
    real_mock = MagicMock(return_value=_fake_segments())
    with patch("app.services.audio.vad_cache.detect_speech_segments", real_mock):
        detect_speech_segments_cached(audio_a)
        detect_speech_segments_cached(audio_b)

    assert real_mock.call_count == 2


# ============================================================
# use_cache=False (bypass)
# ============================================================


def test_use_cache_false_bypasses_cache(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio = _make_audio(tmp_path)
    real_mock = MagicMock(return_value=_fake_segments())
    with patch("app.services.audio.vad_cache.detect_speech_segments", real_mock):
        detect_speech_segments_cached(audio)
        # use_cache=False — força recompute
        detect_speech_segments_cached(audio, use_cache=False)

    assert real_mock.call_count == 2


# ============================================================
# Missing file
# ============================================================


def test_missing_audio_raises(isolated_cache: Path, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        detect_speech_segments_cached(tmp_path / "no.mp3")


# ============================================================
# TTL e expiração
# ============================================================


def test_expired_cache_triggers_recompute(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio = _make_audio(tmp_path)
    real_mock = MagicMock(return_value=_fake_segments())
    with patch("app.services.audio.vad_cache.detect_speech_segments", real_mock):
        detect_speech_segments_cached(audio)
        # ttl=0 garante que tudo está "expirado"
        detect_speech_segments_cached(audio, ttl_sec=0)

    assert real_mock.call_count == 2


# ============================================================
# Robustez: arquivo de cache corrompido
# ============================================================


def test_corrupted_cache_file_triggers_recompute(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio = _make_audio(tmp_path)
    real_mock = MagicMock(return_value=_fake_segments())
    with patch("app.services.audio.vad_cache.detect_speech_segments", real_mock):
        detect_speech_segments_cached(audio)  # popula
    # Corrompe o arquivo de cache existente
    cache_files = list(isolated_cache.glob("*.json"))
    cache_files[0].write_text("not valid json {{{")
    with patch("app.services.audio.vad_cache.detect_speech_segments", real_mock):
        # Não levanta, só recomputa
        result = detect_speech_segments_cached(audio)

    assert real_mock.call_count == 2
    assert len(result) == 2


# ============================================================
# cleanup_expired
# ============================================================


def test_cleanup_removes_expired_files(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio = _make_audio(tmp_path)
    with patch(
        "app.services.audio.vad_cache.detect_speech_segments",
        return_value=_fake_segments(),
    ):
        detect_speech_segments_cached(audio)

    # ttl=0 → tudo está "expirado"
    removed = cleanup_expired(ttl_sec=0)
    assert removed == 1
    assert list(isolated_cache.glob("*.json")) == []


def test_cleanup_keeps_fresh_files(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    audio = _make_audio(tmp_path)
    with patch(
        "app.services.audio.vad_cache.detect_speech_segments",
        return_value=_fake_segments(),
    ):
        detect_speech_segments_cached(audio)

    # ttl=1 dia → cache fresco continua
    removed = cleanup_expired(ttl_sec=86400)
    assert removed == 0
    assert len(list(isolated_cache.glob("*.json"))) == 1


def test_cleanup_handles_missing_dir(
    isolated_cache: Path,
) -> None:
    """Se a pasta nem existe ainda — retorna 0 sem erro."""
    assert cleanup_expired() == 0


def test_cleanup_removes_corrupted_files(
    isolated_cache: Path,
    tmp_path: Path,
) -> None:
    isolated_cache.mkdir(parents=True, exist_ok=True)
    corrupted = isolated_cache / "broken.json"
    corrupted.write_text("not json {")
    removed = cleanup_expired()
    assert removed == 1
    assert not corrupted.exists()
