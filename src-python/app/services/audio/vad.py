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

# Threshold em dBFS pra distinguir "áudio quase silente" de "áudio com som
# mas sem fala detectável pelo VAD" — vide `NoSpeechDetectedError`.
SILENCE_DB_THRESHOLD = -60.0


@dataclass(frozen=True)
class SpeechSegment:
    """Intervalo de fala detectado pelo VAD, em segundos."""

    start_sec: float
    end_sec: float

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


class NoSpeechDetectedError(RuntimeError):
    """
    Áudio existe mas o VAD não conseguiu detectar nenhum trecho de fala.

    Pode ser:
    - **silent_audio**: o arquivo tá praticamente em silêncio absoluto (volume
      médio abaixo de `SILENCE_DB_THRESHOLD`). Microfone provavelmente desligado
      no momento da gravação.
    - **no_speech**: o arquivo tem som (música, ruído, animais) mas nenhuma
      fala humana foi detectada — pode ser idioma/qualidade/efeitos.

    A mensagem (`args[0]`) é amigável e pode ser mostrada direto ao usuário
    pelo frontend.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        volume_db: float,
        duration_sec: float,
    ) -> None:
        super().__init__(message)
        self.reason = reason  # "silent_audio" | "no_speech"
        self.volume_db = volume_db
        self.duration_sec = duration_sec


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


def _read_audio_ffmpeg(audio_path: Path, sampling_rate: int) -> Any:
    """
    Decodifica `audio_path` (qualquer formato suportado pelo ffmpeg) para
    um torch.Tensor 1-D float32 normalizado em [-1, 1] no `sampling_rate`
    pedido.

    Usado em vez de `silero_vad.read_audio` / `torchaudio.load` porque:
    - silero-vad 5.1.2 chama `torchaudio.list_audio_backends()` (removida em
      torchaudio 2.7+; pyannote.audio 4.x exige torchaudio 2.11+).
    - silero-vad 6.x usa `torchcodec`, cuja DLL nativa não carrega no Windows
      (`libtorchcodec_core4.dll`).
    - Bypassamos torchaudio totalmente: o ffmpeg já está no PATH como dep
      do projeto desde a Etapa 0.1.
    """
    import ffmpeg
    import numpy as np
    import torch

    # Pipe de PCM 16-bit signed little-endian (s16le): formato bruto,
    # determinístico, sem header. Convertemos pra mono no sample rate alvo.
    out, _ = (
        ffmpeg.input(str(audio_path))
        .output(
            "pipe:",
            format="s16le",
            acodec="pcm_s16le",
            ac=1,
            ar=sampling_rate,
            loglevel="error",
        )
        .run(capture_stdout=True, capture_stderr=True)
    )
    samples_int16 = np.frombuffer(out, dtype=np.int16)
    # Normaliza pra [-1, 1] em float32 (range esperado pelo modelo Silero).
    samples_float = samples_int16.astype(np.float32) / 32768.0
    return torch.from_numpy(samples_float)


def compute_volume_db(wav: Any) -> float:
    """
    Calcula o RMS do tensor de áudio (float32 em [-1, 1]) em dBFS.
    Retorna `-inf` se o tensor for vazio ou todo zero.
    """
    import math

    import torch

    if wav.numel() == 0:
        return -math.inf
    rms = float(torch.sqrt((wav.float() ** 2).mean()))
    if rms <= 0.0:
        return -math.inf
    return 20.0 * math.log10(rms)


def detect_speech_segments(
    audio_path: Path,
    *,
    min_speech_duration_ms: int = DEFAULT_MIN_SPEECH_MS,
    min_silence_duration_ms: int = DEFAULT_MIN_SILENCE_MS,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[SpeechSegment]:
    """
    Detecta trechos de fala em `audio_path` (qualquer formato suportado pelo
    ffmpeg — não precisa estar pré-convertido).

    Retorna lista de `SpeechSegment` ordenada por `start_sec`.

    Levanta `NoSpeechDetectedError` com mensagem amigável quando o VAD não
    consegue identificar nenhum trecho de fala — distingue entre áudio
    silente (`reason='silent_audio'`) e áudio com som mas sem fala humana
    (`reason='no_speech'`) usando o RMS do tensor.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")

    from silero_vad import get_speech_timestamps

    model = _get_model()
    wav = _read_audio_ffmpeg(audio_path, sampling_rate=SILERO_SAMPLE_RATE)
    duration_sec = float(wav.numel()) / SILERO_SAMPLE_RATE

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

    if not segments:
        volume_db = compute_volume_db(wav)
        if volume_db <= SILENCE_DB_THRESHOLD:
            display_db = "−∞" if volume_db == float("-inf") else f"{volume_db:.1f}"
            message = (
                f"Áudio sem som detectável (volume médio {display_db} dB). "
                "Verifique se o microfone estava ligado durante a gravação."
            )
            reason = "silent_audio"
        else:
            message = (
                f"Áudio tem som (volume médio {volume_db:.1f} dB) mas nenhuma fala "
                "humana foi detectada. Pode ser música, ruído ambiente, ou idioma "
                "fora do esperado. Suba um arquivo com voz em português."
            )
            reason = "no_speech"
        logger.warning(
            "Nenhum trecho de fala detectado",
            audio=str(audio_path),
            reason=reason,
            volume_db=round(volume_db, 2) if volume_db != float("-inf") else "-inf",
        )
        raise NoSpeechDetectedError(
            message,
            reason=reason,
            volume_db=volume_db,
            duration_sec=duration_sec,
        )

    return segments
