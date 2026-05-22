"""
Transcrição paralela de chunks com semáforo + merge de resultados.

Por que:
- Reunião de 3h vira ~18 chunks de 10min (após VAD + chunker)
- Em série, transcrever 18 chunks via Groq leva ~30 min
- Em paralelo (4 simultâneos), leva ~7 min
- Semáforo respeita rate limit dos providers — Groq free tier
  permite ~4-6 req/s, AssemblyAI ainda mais

Decisão: o limite default vem de `settings.MAX_PARALLEL_CHUNKS` (4),
mas o caller pode sobrescrever via `max_parallel`. O merge ajusta
timestamps pra ficarem absolutos no áudio original (cada chunk tem
seu offset em `chunk.start_sec`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from loguru import logger

from app.core.settings import settings
from app.services.audio.chunker import AudioChunk
from app.services.transcription.base import (
    TranscriptionResult,
    TranscriptionSegment,
)
from app.services.transcription.router import TranscriptionRouter


async def transcribe_chunks_parallel(
    chunks: Sequence[AudioChunk],
    router: TranscriptionRouter,
    *,
    language: str = "pt",
    max_parallel: int | None = None,
) -> list[TranscriptionResult | BaseException]:
    """
    Transcreve N chunks com no máximo `max_parallel` simultâneos.

    Retorna lista alinhada com `chunks` — pode conter exceptions nos
    índices que falharam (não levanta nada por padrão pra não cancelar
    os outros chunks). Faça o merge via `merge_chunk_transcriptions`.
    """
    if not chunks:
        return []
    limit = max_parallel if max_parallel is not None else settings.MAX_PARALLEL_CHUNKS
    if limit < 1:
        raise ValueError("max_parallel deve ser >= 1")
    semaphore = asyncio.Semaphore(limit)

    async def _one(chunk: AudioChunk) -> TranscriptionResult:
        if chunk.file_path is None:
            raise ValueError(
                f"Chunk {chunk.index} sem file_path — esqueceu de materializar via chunk_audio_smart?"
            )
        async with semaphore:
            logger.info(
                "Transcrevendo chunk",
                index=chunk.index,
                file=str(chunk.file_path),
                duration_sec=round(chunk.duration_sec, 2),
            )
            return await router.transcribe(chunk.file_path, language=language)

    return await asyncio.gather(
        *[_one(c) for c in chunks],
        return_exceptions=True,
    )


def merge_chunk_transcriptions(
    chunks: Sequence[AudioChunk],
    results: Sequence[TranscriptionResult | BaseException],
) -> TranscriptionResult:
    """
    Mescla resultados de chunks num único `TranscriptionResult`,
    ajustando timestamps pra ficarem absolutos no áudio original.

    Chunks com exception são pulados (com warning). Se TODOS falharam,
    levanta `ValueError` — chamador decide se vai retry ou propaga.
    """
    if len(chunks) != len(results):
        raise ValueError(
            f"chunks ({len(chunks)}) e results ({len(results)}) têm tamanhos diferentes"
        )

    all_segments: list[TranscriptionSegment] = []
    text_parts: list[str] = []
    total_cost = 0.0
    total_duration = 0.0
    provider_used: str | None = None
    model_used: str | None = None
    language: str | None = None
    successes = 0

    for chunk, result in zip(chunks, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(
                "Chunk falhou no merge — pulando",
                index=chunk.index,
                error=str(result),
            )
            continue
        successes += 1
        for seg in result.segments:
            all_segments.append(
                TranscriptionSegment(
                    start_sec=chunk.start_sec + seg.start_sec,
                    end_sec=chunk.start_sec + seg.end_sec,
                    text=seg.text,
                    speaker=seg.speaker,
                    confidence=seg.confidence,
                )
            )
        if result.full_text.strip():
            text_parts.append(result.full_text.strip())
        total_cost += result.cost_usd
        total_duration += result.duration_sec
        provider_used = provider_used or result.provider_used
        model_used = model_used or result.model_used
        language = language or result.language

    if successes == 0:
        raise ValueError("Nenhum chunk foi transcrito com sucesso — nada pra mesclar")

    return TranscriptionResult(
        full_text=" ".join(text_parts),
        segments=all_segments,
        language=language or "pt",
        duration_sec=total_duration,
        provider_used=provider_used or "unknown",
        model_used=model_used or "unknown",
        cost_usd=total_cost,
    )
