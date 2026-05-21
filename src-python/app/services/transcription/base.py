"""
Interfaces e tipos compartilhados da camada de transcrição.

O resto do app (router, pipeline de ata, endpoints REST) só conhece
a interface `TranscriptionProvider` e o resultado normalizado
`TranscriptionResult` — nunca o SDK do Groq ou AssemblyAI direto.
Cada provider concreto vive em seu próprio módulo, então adicionar
um novo (Deepgram, Whisper local, etc.) é só implementar a interface.

Nota sobre nomenclatura: usamos `TranscriptionSegment` (e não
`TranscriptSegment`) pra não colidir com o model SQLAlchemy de mesmo
nome em `app.models.transcript`. O dataclass aqui é transiente
(in-memory); o model do DB é a forma persistida.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

KnownTranscriptionProvider = Literal["groq", "assemblyai"]
KNOWN_TRANSCRIPTION_PROVIDERS: Final[tuple[KnownTranscriptionProvider, ...]] = (
    "groq",
    "assemblyai",
)


@dataclass(frozen=True)
class TranscriptionSegment:
    """Trecho de transcrição com timestamps em segundos."""

    start_sec: float
    end_sec: float
    text: str
    speaker: str | None = None
    confidence: float | None = None

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


@dataclass(frozen=True)
class TranscriptionResult:
    """Resultado normalizado de uma transcrição (independente do provider)."""

    full_text: str
    segments: list[TranscriptionSegment]
    language: str
    duration_sec: float
    provider_used: str
    model_used: str
    cost_usd: float = 0.0


# ============================================================
# Hierarquia de exceptions
# ============================================================


class TranscriptionError(RuntimeError):
    """Erro genérico de transcrição. Subclasses capturam casos específicos."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class ProviderUnavailableError(TranscriptionError):
    """Provider não pode ser usado agora (sem API key, SDK não instalado)."""


class RateLimitError(TranscriptionError):
    """
    Provider retornou 429 ou equivalente.

    Pode incluir `retry_after_sec` se a API informou — o router usa
    esse valor (quando presente) em vez do backoff exponencial padrão.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        retry_after_sec: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider)
        self.retry_after_sec = retry_after_sec


class ProviderAPIError(TranscriptionError):
    """Provider retornou erro não-recuperável (auth, request inválido, 5xx)."""


class TranscriptionTimeoutError(TranscriptionError):
    """Provider demorou demais — bater retry ou fallback."""


class AllProvidersFailedError(TranscriptionError):
    """
    O router exauriu todos os providers sem sucesso.

    `failures` é um dict {provider_name: motivo} com o último erro
    de cada provider — útil pra logar e expor pro usuário.
    """

    def __init__(
        self,
        message: str,
        *,
        failures: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.failures = failures or {}


# ============================================================
# Interface dos providers
# ============================================================


class TranscriptionProvider(ABC):
    """Interface única que TODOS os providers concretos implementam."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool:
        """True se o provider tem credenciais e dá pra usar agora."""
        ...

    @abstractmethod
    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str = "pt",
    ) -> TranscriptionResult:
        """
        Transcreve `audio_path` (idealmente já preprocessado — 16kHz mono).

        Levanta uma das subclasses de `TranscriptionError` em caso de
        falha. Nunca retorna `None` — sucesso é resultado, fracasso é
        exception.
        """
        ...
