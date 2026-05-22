"""
Benchmark do `plan_chunks` (Fase 1.9.5 / Bloco A.4).

Mede a lógica pura do chunker — sem ffmpeg, sem I/O. O objetivo é
flagear regressão caso alguma mudança na heurística de snap-to-silence
ou no agrupamento de segments piore o tempo de cálculo do plano.
"""

from __future__ import annotations

import pytest

from app.services.audio.chunker import plan_chunks
from app.services.audio.vad import SpeechSegment


def _generate_segments(count: int) -> list[SpeechSegment]:
    """Gera N segments espaçados — simula reunião longa."""
    return [SpeechSegment(start_sec=float(i * 5), end_sec=float(i * 5 + 3)) for i in range(count)]


@pytest.mark.benchmark(group="chunker")
def test_bench_plan_chunks_small(benchmark) -> None:
    """100 segments — reunião de ~8min."""
    segments = _generate_segments(100)
    result = benchmark(plan_chunks, segments, max_chunk_duration_sec=600)
    assert len(result) >= 1


@pytest.mark.benchmark(group="chunker")
def test_bench_plan_chunks_medium(benchmark) -> None:
    """1.000 segments — reunião de ~1h."""
    segments = _generate_segments(1000)
    result = benchmark(plan_chunks, segments, max_chunk_duration_sec=600)
    assert len(result) >= 5


@pytest.mark.benchmark(group="chunker")
def test_bench_plan_chunks_large(benchmark) -> None:
    """3.000 segments — reunião de ~3h (limite superior do MVP)."""
    segments = _generate_segments(3000)
    result = benchmark(plan_chunks, segments, max_chunk_duration_sec=600)
    assert len(result) >= 15
