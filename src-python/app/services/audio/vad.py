"""
Voice Activity Detection (VAD) usando Silero — modelo pequeno (~30MB)
que roda em CPU rápido e identifica trechos de fala num áudio.

Por que VAD antes de transcrever:
- Remove 20-25% típicos de silêncio → upload menor pro STT
- Reduz alucinação do Whisper (silêncio às vezes vira texto fantasma)
- Permite chunking inteligente (cortar em pausas naturais)

Modelo é carregado lazy + cacheado em singleton (torch.hub baixa na
primeira chamada e cacheia no disco).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from loguru import logger

# Sample rate exigido pelo modelo Silero.
SILERO_SAMPLE_RATE = 16000

# Defaults sensatos pra reunião em português (vide RELATORIO_TECNICO §1.3.2)
DEFAULT_MIN_SPEECH_MS = 250  # blocos menores que isso provavelmente são ruído
DEFAULT_MIN_SILENCE_MS = 500  # pausas menores ficam dentro do mesmo segmento
DEFAULT_THRESHOLD = 0.5

_model: Any | None = None
_model_lock = Lock()


@dataclass(frozen=True)
class SpeechSegment:
    """Intervalo de fala detectado pelo VAD, em segundos."""

    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def _get_model() -> Any:
    """Carrega o modelo Silero (singleton thread-safe)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # Import lazy — silero_vad puxa torch (pesado)
                from silero_vad import load_silero_vad

                logger.info("Carregando modelo Silero VAD (primeira chamada)")
                _model = load_silero_vad()
    return _model


def reset_model_cache() -> None:
    """Útil pra testes: força o re-carregamento na próxima chamada."""
    global _model
    with _model_lock:
        _model = None


def detect_speech_segments(
    audio_path: Path,
    *,
    min_speech_duration_ms: int = DEFAULT_MIN_SPEECH_MS,
    min_silence_duration_ms: int = DEFAULT_MIN_SILENCE_MS,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[SpeechSegment]:
    """
    Detecta trechos de fala em `audio_path` (precisa estar em 16kHz mono;
    use `convert_to_optimized_mp3` antes pra garantir).

    Retorna lista de `SpeechSegment` ordenada por `start_sec`.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")

    from silero_vad import (
        get_speech_timestamps,
        read_audio,
    )

    model = _get_model()
    wav = read_audio(str(audio_path), sampling_rate=SILERO_SAMPLE_RATE)

    raw_timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=SILERO_SAMPLE_RATE,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        threshold=threshold,
    )

    segments = [
        SpeechSegment(
            start_sec=ts["start"] / SILERO_SAMPLE_RATE,
            end_sec=ts["end"] / SILERO_SAMPLE_RATE,
        )
        for ts in raw_timestamps
    ]
    logger.info(
        "VAD concluído",
        audio=str(audio_path),
        segments=len(segments),
        total_speech_sec=round(sum(s.duration_sec for s in segments), 2),
    )
    return segments
