"""
Diarização de speakers via pyannote.audio.

Carrega o modelo `pyannote/speaker-diarization-3.1` do Hugging Face
Hub (gated — precisa aceitar termos e gerar token) e identifica
trechos de fala por speaker.

Singleton thread-safe: o modelo (~500MB) é carregado lazy na primeira
chamada e cacheado. Em testes, use `reset_pipeline_cache()` pra forçar
re-load.

Decisão de design — `HF_TOKEN` é APP-level, não user-level. Vem do
`.env` em dev e de build secret em prod. Diarização é opcional no
MVP: sem token, `is_available()` retorna False e a transcrição segue
normalmente sem rótulos de speaker (vide [`AUDIT-FASE-1.5`]).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Final

from loguru import logger

from app.core.settings import settings

PYANNOTE_MODEL: Final[str] = "pyannote/speaker-diarization-3.1"

_pipeline: Any | None = None
_pipeline_lock = Lock()


class DiarizationError(RuntimeError):
    """Erro genérico de diarização."""


class DiarizationUnavailableError(DiarizationError):
    """
    Pipeline não pode ser usado agora.

    Causas típicas: HF_TOKEN ausente, sem internet pra baixar modelo
    na primeira execução, ou termos do modelo no Hugging Face não
    aceitos pela conta do APP.
    """


@dataclass(frozen=True)
class SpeakerSegment:
    """Trecho contínuo de fala atribuído a um speaker pelo pyannote."""

    start_sec: float
    end_sec: float
    speaker_id: str  # Ex: "SPEAKER_00", "SPEAKER_01", ...

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def is_available() -> bool:
    """True se HF_TOKEN está configurado (não testa conexão de fato)."""
    return bool(settings.HF_TOKEN)


def reset_pipeline_cache() -> None:
    """Força re-load do pipeline na próxima chamada — útil pra testes."""
    global _pipeline
    with _pipeline_lock:
        _pipeline = None


def _get_pipeline() -> Any:
    """Carrega o pipeline pyannote (singleton thread-safe)."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                token = settings.HF_TOKEN
                if not token:
                    raise DiarizationUnavailableError(
                        "HF_TOKEN não configurado — diarização desabilitada. "
                        "Defina ESKUTA_HF_TOKEN no .env (dev) ou build secret (prod)."
                    )
                # Import lazy — pyannote.audio puxa lightning, transformers, etc.
                from pyannote.audio import Pipeline

                logger.info("Carregando modelo pyannote", model=PYANNOTE_MODEL)
                try:
                    _pipeline = Pipeline.from_pretrained(
                        PYANNOTE_MODEL,
                        use_auth_token=token,
                    )
                except Exception as exc:
                    raise DiarizationUnavailableError(
                        f"Falha ao carregar pipeline pyannote: {exc}",
                    ) from exc
    return _pipeline


def diarize(audio_path: Path) -> list[SpeakerSegment]:
    """
    Identifica trechos de fala por speaker em `audio_path`.

    O áudio deve estar em formato suportado pelo pyannote — usar saída
    de `app.services.audio.converter.convert_to_optimized_mp3` (16kHz
    mono MP3) garante compat. Retorna lista ordenada por `start_sec`,
    com `speaker_id` no padrão "SPEAKER_00", "SPEAKER_01", ...

    Levanta `DiarizationUnavailableError` se HF_TOKEN faltar, ou
    `DiarizationError` em falhas runtime do pipeline.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

    pipeline = _get_pipeline()

    try:
        diarization = pipeline(str(audio_path))
    except Exception as exc:
        raise DiarizationError(f"pyannote falhou ao diarizar: {exc}") from exc

    segments = sorted(
        (
            SpeakerSegment(
                start_sec=float(turn.start),
                end_sec=float(turn.end),
                speaker_id=str(speaker),
            )
            for turn, _, speaker in diarization.itertracks(yield_label=True)
        ),
        key=lambda s: s.start_sec,
    )

    logger.info(
        "Diarização concluída",
        audio=str(audio_path),
        segments=len(segments),
        unique_speakers=len({s.speaker_id for s in segments}),
    )
    return segments
