"""
Router de transcrição com fallback inteligente.

Estratégia (RELATORIO_TECNICO §1.4.2):
1. Tenta o provider preferido (`settings.PREFERRED_STT`) primeiro.
2. Em 429 (rate limit), retry com backoff exponencial — usa
   `retry_after_sec` da exception quando o provider informa, senão
   `backoff_base * 2^(attempt-1)`.
3. Em erro não-recuperável (auth, 5xx, timeout, indisponível), pula
   pro próximo provider sem esperar.
4. Se todos falharem, levanta `AllProvidersFailedError` com o
   histórico de falhas (não vaza valor de API key).

Logs estruturados deixam claro qual provider foi tentado, quantas
vezes, qual erro fechou a porta, e quem entregou no final.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from loguru import logger

from app.core.settings import settings
from app.services.transcription.assemblyai_provider import AssemblyAIProvider
from app.services.transcription.base import (
    AllProvidersFailedError,
    ProviderAPIError,
    ProviderUnavailableError,
    RateLimitError,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionTimeoutError,
)
from app.services.transcription.groq_provider import GroqProvider

DEFAULT_MAX_ATTEMPTS_PER_PROVIDER = 3
DEFAULT_BACKOFF_BASE_SEC = 1.0


def _build_default_providers() -> list[TranscriptionProvider]:
    """Ordem default: respeita `settings.PREFERRED_STT` na primeira posição."""
    by_name: dict[str, TranscriptionProvider] = {
        "groq": GroqProvider(),
        "assemblyai": AssemblyAIProvider(),
    }
    preferred = settings.PREFERRED_STT
    rest = [p for n, p in by_name.items() if n != preferred]
    return [by_name[preferred], *rest]


class TranscriptionRouter:
    """Orquestra transcrição com fallback entre providers."""

    def __init__(
        self,
        providers: Sequence[TranscriptionProvider] | None = None,
        *,
        max_attempts_per_provider: int = DEFAULT_MAX_ATTEMPTS_PER_PROVIDER,
        backoff_base_sec: float = DEFAULT_BACKOFF_BASE_SEC,
    ) -> None:
        if max_attempts_per_provider < 1:
            raise ValueError("max_attempts_per_provider deve ser >= 1")
        self.providers: list[TranscriptionProvider] = (
            list(providers) if providers is not None else _build_default_providers()
        )
        self.max_attempts = max_attempts_per_provider
        self.backoff_base = backoff_base_sec

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str = "pt",
    ) -> TranscriptionResult:
        failures: dict[str, str] = {}

        for provider in self.providers:
            if not provider.is_available():
                logger.warning(
                    "Provider indisponível, pulando",
                    provider=provider.name,
                )
                failures[provider.name] = "sem API key"
                continue

            last_error: Exception | None = None

            for attempt in range(1, self.max_attempts + 1):
                logger.info(
                    "Tentando transcrição",
                    provider=provider.name,
                    attempt=attempt,
                    max_attempts=self.max_attempts,
                )
                try:
                    return await provider.transcribe(audio_path, language=language)
                except RateLimitError as exc:
                    last_error = exc
                    wait_sec = exc.retry_after_sec or (self.backoff_base * (2 ** (attempt - 1)))
                    logger.warning(
                        "Rate limit no provider — backoff",
                        provider=provider.name,
                        attempt=attempt,
                        wait_sec=wait_sec,
                    )
                    if attempt < self.max_attempts:
                        await asyncio.sleep(wait_sec)
                    else:
                        logger.error(
                            "Provider esgotou tentativas em rate limit",
                            provider=provider.name,
                        )
                except (
                    ProviderAPIError,
                    TranscriptionTimeoutError,
                    ProviderUnavailableError,
                ) as exc:
                    last_error = exc
                    logger.error(
                        "Erro não-recuperável no provider — pulando pro próximo",
                        provider=provider.name,
                        attempt=attempt,
                        error=str(exc),
                    )
                    break

            failures[provider.name] = (
                str(last_error) if last_error else "esgotou tentativas sem erro registrado"
            )

        raise AllProvidersFailedError(
            f"Todos os providers de transcrição falharam: {failures}",
            failures=failures,
        )
