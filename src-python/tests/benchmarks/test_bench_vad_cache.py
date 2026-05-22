"""
Benchmark do cache de VAD (Fase 1.9.5 / Bloco A.4).

Foca no **delta** entre cache miss e cache hit — esse é o ganho real
do A.3. Os números absolutos não importam tanto (VAD real está mockado);
o que importa é o cache hit ser dramaticamente mais rápido que o miss.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.audio import vad_cache
from app.services.audio.vad import SpeechSegment
from app.services.audio.vad_cache import detect_speech_segments_cached


@pytest.fixture
def isolated_bench_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(vad_cache.settings, "APP_DIR", tmp_path / "bench")


def _fake_segments() -> list[SpeechSegment]:
    """Resultado típico do VAD pra um chunk de ~10min."""
    return [SpeechSegment(start_sec=float(i * 5), end_sec=float(i * 5 + 3)) for i in range(100)]


@pytest.mark.benchmark(group="vad-cache")
def test_bench_vad_cache_miss(benchmark, tmp_path: Path, isolated_bench_cache) -> None:
    """
    Cache miss — chama o VAD real (mockado aqui). Mede o overhead do
    hash + serialização + escrita do cache. Em produção o tempo é
    dominado pelo VAD real (~5-10s por hora de áudio).
    """
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"x" * 1024)

    def fresh_call():
        # Garante miss limpando o cache a cada iteração
        cache_dir = tmp_path / "bench" / "cache" / "vad"
        if cache_dir.exists():
            for f in cache_dir.glob("*.json"):
                f.unlink()
        with patch(
            "app.services.audio.vad_cache.detect_speech_segments",
            return_value=_fake_segments(),
        ):
            return detect_speech_segments_cached(audio)

    result = benchmark(fresh_call)
    assert len(result) == 100


@pytest.mark.benchmark(group="vad-cache")
def test_bench_vad_cache_hit(benchmark, tmp_path: Path, isolated_bench_cache) -> None:
    """
    Cache hit — só lê JSON do disco e deserializa. Deve ser ordens
    de magnitude mais rápido que o miss.
    """
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"x" * 1024)

    # Popula o cache antes do benchmark
    with patch(
        "app.services.audio.vad_cache.detect_speech_segments",
        return_value=_fake_segments(),
    ):
        detect_speech_segments_cached(audio)

    def cached_call():
        # Cache já populado — não chama o VAD real
        return detect_speech_segments_cached(audio)

    result = benchmark(cached_call)
    assert len(result) == 100
