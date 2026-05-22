"""
Testes do transcribe_chunks_parallel + merge_chunk_transcriptions.

Validamos:
- Semáforo respeitado (no máximo N simultâneos em qualquer momento)
- Timestamps no merge ficam absolutos (chunk.start_sec + seg.start_sec)
- Falha de UM chunk não cancela os outros (return_exceptions=True)
- Merge ignora chunks que falharam, mas levanta se TODOS falharam
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.audio.chunker import AudioChunk
from app.services.transcription.base import (
    ProviderAPIError,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)
from app.services.transcription.parallel import (
    merge_chunk_transcriptions,
    transcribe_chunks_parallel,
)
from app.services.transcription.router import TranscriptionRouter


class _CountingProvider(TranscriptionProvider):
    """
    Provider que conta concorrência: incrementa contador on enter,
    decrementa on exit, registrando o pico de inflight.
    """

    def __init__(
        self,
        *,
        delay_sec: float = 0.02,
        fail_indexes: set[int] | None = None,
    ) -> None:
        self.inflight = 0
        self.peak_inflight = 0
        self.delay = delay_sec
        self.fail_indexes = fail_indexes or set()
        self._lock = asyncio.Lock()
        self.calls = 0

    @property
    def name(self) -> str:
        return "counting"

    def is_available(self) -> bool:
        return True

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str = "pt",
    ) -> TranscriptionResult:
        async with self._lock:
            self.calls += 1
            self.inflight += 1
            self.peak_inflight = max(self.peak_inflight, self.inflight)
            idx = self.calls - 1
        try:
            await asyncio.sleep(self.delay)
            if idx in self.fail_indexes:
                raise ProviderAPIError(f"falha forçada no chunk {idx}", provider="counting")
            return TranscriptionResult(
                full_text=f"texto chunk {idx}",
                segments=[
                    TranscriptionSegment(start_sec=0.0, end_sec=1.0, text=f"chunk {idx}"),
                ],
                language="pt",
                duration_sec=1.0,
                provider_used="counting",
                model_used="model-x",
                cost_usd=0.001,
            )
        finally:
            async with self._lock:
                self.inflight -= 1


def _chunks(tmp_path: Path, n: int) -> list[AudioChunk]:
    """Gera N chunks materializados (file_path apontando pra tmp_path)."""
    chunks: list[AudioChunk] = []
    for i in range(n):
        path = tmp_path / f"chunk_{i:03d}.mp3"
        path.write_bytes(b"")
        chunks.append(
            AudioChunk(
                index=i,
                start_sec=i * 100.0,  # 100s de offset entre chunks
                end_sec=(i + 1) * 100.0,
                segment_count=1,
                file_path=path,
            )
        )
    return chunks


# ============================================================
# transcribe_chunks_parallel
# ============================================================


async def test_empty_chunks_returns_empty(tmp_path: Path) -> None:
    provider = _CountingProvider()
    router = TranscriptionRouter([provider])
    results = await transcribe_chunks_parallel([], router)
    assert results == []


async def test_chunk_without_file_path_raises_in_results(tmp_path: Path) -> None:
    """Chunks sem file_path materializado retornam ValueError no resultado."""
    chunk = AudioChunk(
        index=0,
        start_sec=0.0,
        end_sec=10.0,
        segment_count=1,
        file_path=None,
    )
    provider = _CountingProvider()
    router = TranscriptionRouter([provider])
    results = await transcribe_chunks_parallel([chunk], router)
    assert len(results) == 1
    assert isinstance(results[0], ValueError)


async def test_semaphore_limits_concurrency(tmp_path: Path) -> None:
    """Com 10 chunks e limit=3, peak inflight nunca passa de 3."""
    chunks = _chunks(tmp_path, 10)
    provider = _CountingProvider(delay_sec=0.05)
    router = TranscriptionRouter([provider])
    results = await transcribe_chunks_parallel(chunks, router, max_parallel=3)
    assert len(results) == 10
    assert all(isinstance(r, TranscriptionResult) for r in results)
    assert provider.peak_inflight <= 3
    # Sanity: com 10 chunks e limit 3 deve dar pelo menos 2 simultâneos
    assert provider.peak_inflight >= 2


async def test_default_max_parallel_from_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.transcription.parallel.settings.MAX_PARALLEL_CHUNKS",
        2,
    )
    chunks = _chunks(tmp_path, 6)
    provider = _CountingProvider(delay_sec=0.03)
    router = TranscriptionRouter([provider])
    await transcribe_chunks_parallel(chunks, router)
    assert provider.peak_inflight <= 2


async def test_invalid_max_parallel_raises(tmp_path: Path) -> None:
    chunks = _chunks(tmp_path, 1)
    router = TranscriptionRouter([_CountingProvider()])
    with pytest.raises(ValueError):
        await transcribe_chunks_parallel(chunks, router, max_parallel=0)


async def test_failure_in_one_chunk_does_not_kill_others(tmp_path: Path) -> None:
    """Chunk 1 falha — outros 4 ainda completam."""
    chunks = _chunks(tmp_path, 5)
    provider = _CountingProvider(fail_indexes={1})
    router = TranscriptionRouter([provider])
    results = await transcribe_chunks_parallel(chunks, router, max_parallel=2)
    success_count = sum(1 for r in results if isinstance(r, TranscriptionResult))
    assert success_count == 4


# ============================================================
# merge_chunk_transcriptions
# ============================================================


def test_merge_adjusts_timestamps_to_absolute(tmp_path: Path) -> None:
    chunks = _chunks(tmp_path, 2)  # offsets 0s e 100s
    results: list[TranscriptionResult] = [
        TranscriptionResult(
            full_text="primeiro chunk",
            segments=[
                TranscriptionSegment(start_sec=2.0, end_sec=5.0, text="aaa"),
            ],
            language="pt",
            duration_sec=5.0,
            provider_used="x",
            model_used="m",
            cost_usd=0.01,
        ),
        TranscriptionResult(
            full_text="segundo chunk",
            segments=[
                TranscriptionSegment(start_sec=1.0, end_sec=3.0, text="bbb"),
            ],
            language="pt",
            duration_sec=3.0,
            provider_used="x",
            model_used="m",
            cost_usd=0.005,
        ),
    ]
    merged = merge_chunk_transcriptions(chunks, results)
    # Chunk 0 não muda; chunk 1 ganha +100s
    assert merged.segments[0].start_sec == 2.0
    assert merged.segments[0].end_sec == 5.0
    assert merged.segments[1].start_sec == 101.0
    assert merged.segments[1].end_sec == 103.0
    # Texto preserva ordem
    assert merged.full_text == "primeiro chunk segundo chunk"
    # Soma de custos
    assert merged.cost_usd == pytest.approx(0.015)
    # Duração somada
    assert merged.duration_sec == pytest.approx(8.0)


def test_merge_preserves_speaker_and_confidence(tmp_path: Path) -> None:
    chunks = _chunks(tmp_path, 1)
    results: list[TranscriptionResult] = [
        TranscriptionResult(
            full_text="oi",
            segments=[
                TranscriptionSegment(
                    start_sec=0.0,
                    end_sec=1.0,
                    text="oi",
                    speaker="A",
                    confidence=0.95,
                ),
            ],
            language="pt",
            duration_sec=1.0,
            provider_used="x",
            model_used="m",
        ),
    ]
    merged = merge_chunk_transcriptions(chunks, results)
    assert merged.segments[0].speaker == "A"
    assert merged.segments[0].confidence == 0.95


def test_merge_skips_exceptions(tmp_path: Path) -> None:
    chunks = _chunks(tmp_path, 3)
    ok = TranscriptionResult(
        full_text="ok",
        segments=[TranscriptionSegment(start_sec=0.0, end_sec=1.0, text="ok")],
        language="pt",
        duration_sec=1.0,
        provider_used="x",
        model_used="m",
    )
    results = [ok, RuntimeError("explodiu"), ok]
    merged = merge_chunk_transcriptions(chunks, results)  # type: ignore[arg-type]
    # Pulou o chunk 1; usa offset 0s e 200s do chunk 2
    assert len(merged.segments) == 2
    assert merged.segments[0].start_sec == 0.0
    assert merged.segments[1].start_sec == 200.0


def test_merge_raises_when_all_failed(tmp_path: Path) -> None:
    chunks = _chunks(tmp_path, 2)
    results = [RuntimeError("a"), RuntimeError("b")]
    with pytest.raises(ValueError):
        merge_chunk_transcriptions(chunks, results)  # type: ignore[arg-type]


def test_merge_size_mismatch_raises(tmp_path: Path) -> None:
    chunks = _chunks(tmp_path, 2)
    results: list[TranscriptionResult] = []
    with pytest.raises(ValueError):
        merge_chunk_transcriptions(chunks, results)
