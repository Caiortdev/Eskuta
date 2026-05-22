"""
Camada de diarização do Eskuta — "quem falou o quê" via pyannote.audio.

Diarização é **opcional no MVP** (relatório §1.5): se HF_TOKEN não
estiver configurado, `is_available()` retorna False e o pipeline de
ata segue sem rótulo de speaker. Quando o token está presente, o
serviço identifica `SPEAKER_00`, `SPEAKER_01`, ... e o `merger`
combina com a transcrição (1.5.2). O `speaker_map` aplica rótulos
humanos quando o usuário renomeia (1.5.3).
"""

from app.services.diarization.merger import merge_transcription_and_diarization
from app.services.diarization.pyannote_service import (
    PYANNOTE_MODEL,
    DiarizationError,
    DiarizationUnavailableError,
    SpeakerSegment,
    diarize,
    is_available,
    reset_pipeline_cache,
)
from app.services.diarization.speaker_map import (
    apply_speaker_map,
    extract_unique_speakers,
)

__all__ = [
    "PYANNOTE_MODEL",
    "DiarizationError",
    "DiarizationUnavailableError",
    "SpeakerSegment",
    "apply_speaker_map",
    "diarize",
    "extract_unique_speakers",
    "is_available",
    "merge_transcription_and_diarization",
    "reset_pipeline_cache",
]
