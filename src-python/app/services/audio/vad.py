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


def _read_audio_as_tensor(audio_path: Path, sampling_rate: int) -> Any:
    """
    Lê áudio do disco e devolve `torch.Tensor` mono 1-D em `sampling_rate`.

    Substitui `silero_vad.read_audio()`, que internamente chama
    `torchaudio.list_audio_backends()` — função REMOVIDA no torchaudio
    2.9+. Como o projeto pode usar torchaudio 2.11+ (puxado por
    pyannote), o read_audio do silero crasha com AttributeError.

    Pipeline:
    1. ffmpeg (via imageio-ffmpeg) → WAV mono 16kHz em memória (stream)
    2. soundfile lê o WAV → numpy float32
    3. torch.from_numpy → Tensor 1-D

    Usar ffmpeg em vez de soundfile direto porque o input pode ser
    qualquer formato (MP3, MP4, M4A, etc.) — soundfile só lê WAV/FLAC/OGG.
    O MP3 otimizado que vem do converter passa direto também, sem
    re-encode pesado (só decode pra PCM).
    """
    import subprocess

    import numpy as np
    import torch

    from app.services.audio.converter import _ffmpeg_exe

    # ffmpeg → WAV PCM s16le mono no stdout. Pipe binário direto, não
    # toca em disco temporário.
    cmd = [
        _ffmpeg_exe(),
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-f",
        "s16le",  # raw PCM signed 16-bit little-endian
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",  # mono
        "-ar",
        str(sampling_rate),
        "-",  # stdout
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        check=False,
        # Em Windows sem essa flag, abre cmd window quando rodado do
        # bundle PyInstaller --windowed.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ffmpeg falhou ao decodificar áudio pro VAD: {stderr}")

    # Converte PCM s16le → float32 normalizado em [-1, 1] (formato esperado
    # pelo silero, equivalente ao que torchaudio.load entrega).
    pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return torch.from_numpy(pcm)


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

    from silero_vad import get_speech_timestamps

    model = _get_model()
    # Usa wrapper próprio (ffmpeg → numpy → tensor) em vez de
    # silero_vad.read_audio() — esse último depende de
    # torchaudio.list_audio_backends() que foi removida em torchaudio 2.9+.
    wav = _read_audio_as_tensor(audio_path, sampling_rate=SILERO_SAMPLE_RATE)

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
