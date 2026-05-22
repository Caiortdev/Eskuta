"""
Camada de transcrição (STT) do Eskuta.

Implementa o padrão adapter pra que o resto do app não dependa
diretamente dos SDKs Groq/AssemblyAI. Use o router pra obter
fallback automático e o helper paralelo pra transcrever chunks.
"""

from app.services.transcription.assemblyai_provider import AssemblyAIProvider
from app.services.transcription.base import (
    KNOWN_TRANSCRIPTION_PROVIDERS,
    AllProvidersFailedError,
    ProviderAPIError,
    ProviderUnavailableError,
    RateLimitError,
    TranscriptionError,
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
    TranscriptionTimeoutError,
)
from app.services.transcription.groq_provider import GroqProvider
from app.services.transcription.parallel import (
    merge_chunk_transcriptions,
    transcribe_chunks_parallel,
)
from app.services.transcription.router import TranscriptionRouter

__all__ = [
    "KNOWN_TRANSCRIPTION_PROVIDERS",
    "AllProvidersFailedError",
    "AssemblyAIProvider",
    "GroqProvider",
    "ProviderAPIError",
    "ProviderUnavailableError",
    "RateLimitError",
    "TranscriptionError",
    "TranscriptionProvider",
    "TranscriptionResult",
    "TranscriptionRouter",
    "TranscriptionSegment",
    "TranscriptionTimeoutError",
    "merge_chunk_transcriptions",
    "transcribe_chunks_parallel",
]
