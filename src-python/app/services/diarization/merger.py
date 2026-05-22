"""
Merge das saídas de diarização (pyannote) com a transcrição (Whisper).

Pyannote retorna *speaker segments* (trechos contínuos de um único
falante). Whisper retorna *transcription segments* (trechos de texto
com timestamp). Os dois nem sempre se alinham — uma frase do Whisper
pode atravessar dois speakers, ou um turno do pyannote pode conter
várias frases.

Estratégia (RELATORIO_TECNICO §1.5.2): para cada `TranscriptionSegment`,
atribuímos o speaker que **mais se sobrepõe** com ele temporalmente.
Em empate, o primeiro speaker da lista ganha (determinístico). Se
nenhum speaker se sobrepõe (gap na diarização), preservamos o speaker
já presente no segmento — alguns providers (AssemblyAI) emitem
speaker labels nativos.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.services.diarization.pyannote_service import SpeakerSegment
from app.services.transcription.base import TranscriptionSegment


def merge_transcription_and_diarization(
    transcription_segments: Sequence[TranscriptionSegment],
    speaker_segments: Sequence[SpeakerSegment],
) -> list[TranscriptionSegment]:
    """
    Retorna nova lista de `TranscriptionSegment` com o campo `speaker`
    preenchido a partir dos `SpeakerSegment` do pyannote.

    Regras:
    - Se houver sobreposição, escolhe o speaker que **dominou** o
      trecho de transcrição (maior interseção temporal).
    - Em empate, o primeiro speaker da lista vence (determinístico).
    - Sem sobreposição alguma, preserva o `speaker` original do
      `TranscriptionSegment` (que pode ter vindo do AssemblyAI).
    - Lista vazia de speakers → retorna `transcription_segments`
      idêntica (cópia rasa).
    """
    if not speaker_segments:
        return list(transcription_segments)

    result: list[TranscriptionSegment] = []
    for ts in transcription_segments:
        best_speaker: str | None = None
        best_overlap = 0.0
        for sp in speaker_segments:
            overlap = max(
                0.0,
                min(ts.end_sec, sp.end_sec) - max(ts.start_sec, sp.start_sec),
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = sp.speaker_id

        result.append(
            TranscriptionSegment(
                start_sec=ts.start_sec,
                end_sec=ts.end_sec,
                text=ts.text,
                speaker=best_speaker if best_speaker is not None else ts.speaker,
                confidence=ts.confidence,
            )
        )
    return result
