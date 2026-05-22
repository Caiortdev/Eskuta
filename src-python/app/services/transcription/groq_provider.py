"""
Adapter pro Groq Whisper Large v3 Turbo via SDK oficial.

Free tier generoso em 2026 (limites por minuto); ~$0.04/h no tier
pago. Roda extremamente rápido — entre 10x e 30x mais rápido que
alternativas comparáveis pra português brasileiro.

Defaults importantes pra anti-alucinação:
- temperature=0.0 — reduz texto fantasma em silêncio
- language explícito — não deixa o modelo "adivinhar" pt-BR
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Final

from loguru import logger

from app.services import keys as keys_service
from app.services.transcription.base import (
    ProviderAPIError,
    ProviderUnavailableError,
    RateLimitError,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionTimeoutError,
)

GROQ_MODEL: Final[str] = "whisper-large-v3-turbo"
# Tier pago oficial (jan/2026). Free tier custa 0 mas tem rate limit
# bem mais apertado — `cost_usd` deve ser informativo, não bloqueante.
GROQ_COST_PER_HOUR: Final[float] = 0.04


def _segment_attr(segment: Any, attr: str, default: Any = None) -> Any:
    """SDK Groq pode retornar segments como dict ou pydantic — abstrai."""
    if isinstance(segment, dict):
        return segment.get(attr, default)
    return getattr(segment, attr, default)


class GroqProvider(TranscriptionProvider):
    """Adapter pro Groq Whisper (cliente async)."""

    @property
    def name(self) -> str:
        return "groq"

    def is_available(self) -> bool:
        return keys_service.has_api_key("groq")

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str = "pt",
    ) -> TranscriptionResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

        api_key = keys_service.get_api_key("groq")
        if not api_key:
            raise ProviderUnavailableError(
                "Groq sem API key configurada",
                provider="groq",
            )

        # Import lazy — SDK groq puxa httpx e dependências
        from groq import APIError, APITimeoutError, AsyncGroq
        from groq import RateLimitError as GroqRateLimit

        client = AsyncGroq(api_key=api_key)
        started = time.monotonic()

        try:
            with open(audio_path, "rb") as fh:
                response = await client.audio.transcriptions.create(
                    file=(audio_path.name, fh.read()),
                    model=GROQ_MODEL,
                    language=language,
                    response_format="verbose_json",
                    temperature=0.0,
                )
        except GroqRateLimit as exc:
            retry_after = _extract_retry_after(exc)
            raise RateLimitError(
                "Groq rate limit excedido",
                provider="groq",
                retry_after_sec=retry_after,
            ) from exc
        except APITimeoutError as exc:
            raise TranscriptionTimeoutError(
                f"Groq timeout: {exc}",
                provider="groq",
            ) from exc
        except APIError as exc:
            raise ProviderAPIError(
                f"Groq erro de API: {exc}",
                provider="groq",
            ) from exc

        raw_segments = _segment_attr(response, "segments", []) or []
        segments = [
            TranscriptionSegment(
                start_sec=float(_segment_attr(s, "start", 0.0)),
                end_sec=float(_segment_attr(s, "end", 0.0)),
                text=str(_segment_attr(s, "text", "")).strip(),
                confidence=_segment_attr(s, "avg_logprob"),
            )
            for s in raw_segments
        ]

        duration = float(_segment_attr(response, "duration", 0.0))
        elapsed = time.monotonic() - started
        detected_lang = str(_segment_attr(response, "language", language))
        full_text = str(_segment_attr(response, "text", "")).strip()

        logger.info(
            "Groq transcrição concluída",
            provider="groq",
            duration_sec=duration,
            segments=len(segments),
            elapsed_sec=round(elapsed, 2),
        )

        return TranscriptionResult(
            full_text=full_text,
            segments=segments,
            language=detected_lang,
            duration_sec=duration,
            provider_used="groq",
            model_used=GROQ_MODEL,
            cost_usd=duration / 3600 * GROQ_COST_PER_HOUR,
        )


def _extract_retry_after(exc: Exception) -> float | None:
    """Tenta extrair Retry-After do header do erro (segundos)."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
