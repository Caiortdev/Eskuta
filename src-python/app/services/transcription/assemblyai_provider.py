"""
Adapter pro AssemblyAI Universal — fallback do Groq.

Free tier de ~100h/mês; modelo "universal" suporta pt-BR com
qualidade ligeiramente menor que Whisper Turbo mas estável (e
inclui diarização nativa via `speaker_labels`, que ignoramos no
MVP porque cuidamos disso via pyannote na Fase 1.5).

Diferenças vs Groq:
- API é assíncrona via polling — o SDK oficial encapsula isso, mas
  internamente é blocking. Rodamos via `run_in_executor`.
- Timestamps das utterances vêm em ms (não segundos).
- Não emite Retry-After explícito em rate limit; usamos o backoff
  default do router.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

from loguru import logger

from app.services import keys as keys_service
from app.services.transcription.base import (
    ProviderAPIError,
    ProviderUnavailableError,
    RateLimitError,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)

if TYPE_CHECKING:
    import assemblyai as aai

ASSEMBLYAI_MODEL: Final[str] = "universal"
# Estimativa de custo no tier pago (jan/2026). Free tier custa 0.
ASSEMBLYAI_COST_PER_HOUR: Final[float] = 0.12


class AssemblyAIProvider(TranscriptionProvider):
    """Adapter AssemblyAI (SDK blocking internally; exposto como async)."""

    @property
    def name(self) -> str:
        return "assemblyai"

    def is_available(self) -> bool:
        return keys_service.has_api_key("assemblyai")

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str = "pt",
    ) -> TranscriptionResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

        api_key = keys_service.get_api_key("assemblyai")
        if not api_key:
            raise ProviderUnavailableError(
                "AssemblyAI sem API key configurada",
                provider="assemblyai",
            )

        # Import lazy — SDK assemblyai puxa websockets etc.
        import assemblyai as aai

        aai.settings.api_key = api_key
        config = aai.TranscriptionConfig(
            language_code=language,
            punctuate=True,
            format_text=True,
        )

        started = time.monotonic()
        loop = asyncio.get_event_loop()

        def _run_blocking() -> aai.Transcript:
            transcriber = aai.Transcriber(config=config)
            return transcriber.transcribe(str(audio_path))

        try:
            transcript = await loop.run_in_executor(None, _run_blocking)
        except Exception as exc:
            msg = str(exc).lower()
            if "rate" in msg and "limit" in msg:
                raise RateLimitError(
                    f"AssemblyAI rate limit: {exc}",
                    provider="assemblyai",
                ) from exc
            raise ProviderAPIError(
                f"AssemblyAI erro: {exc}",
                provider="assemblyai",
            ) from exc

        # SDK marca status de erro no objeto retornado em vez de raise
        if transcript.status == aai.TranscriptStatus.error:
            err = transcript.error or "Falha desconhecida no AssemblyAI"
            if "rate" in err.lower() and "limit" in err.lower():
                raise RateLimitError(err, provider="assemblyai")
            raise ProviderAPIError(err, provider="assemblyai")

        segments = _build_segments(transcript)
        duration = float(transcript.audio_duration or 0.0)
        elapsed = time.monotonic() - started

        logger.info(
            "AssemblyAI transcrição concluída",
            provider="assemblyai",
            duration_sec=duration,
            segments=len(segments),
            elapsed_sec=round(elapsed, 2),
        )

        return TranscriptionResult(
            full_text=(transcript.text or "").strip(),
            segments=segments,
            language=language,
            duration_sec=duration,
            provider_used="assemblyai",
            model_used=ASSEMBLYAI_MODEL,
            cost_usd=duration / 3600 * ASSEMBLYAI_COST_PER_HOUR,
        )


def _build_segments(transcript: aai.Transcript) -> list[TranscriptionSegment]:
    """Converte utterances/sentences do AssemblyAI em TranscriptionSegment."""
    utterances = transcript.utterances or []
    if utterances:
        return [
            TranscriptionSegment(
                start_sec=float(u.start) / 1000.0,
                end_sec=float(u.end) / 1000.0,
                text=(u.text or "").strip(),
                speaker=u.speaker,
                confidence=float(u.confidence) if u.confidence is not None else None,
            )
            for u in utterances
        ]
    # Sem utterances (config padrão) — colapsa em segmento único.
    duration = float(transcript.audio_duration or 0.0)
    return [
        TranscriptionSegment(
            start_sec=0.0,
            end_sec=duration,
            text=(transcript.text or "").strip(),
        )
    ]
