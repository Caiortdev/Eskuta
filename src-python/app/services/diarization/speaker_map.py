"""
Aplicação do mapeamento de speakers anônimos → nomes humanos.

Fluxo (RELATORIO_TECNICO §1.5.3):
1. Pyannote identifica `SPEAKER_00`, `SPEAKER_01`, ...
2. Frontend (Fase 1.10) mostra amostras pro usuário e pede pra nomear
3. UI salva o mapeamento em `meetings.speaker_map` (JSON, campo da
   tabela `meetings` da Fase 1.2)
4. Pipeline de ata (Fase 1.9) aplica o mapeamento ao gerar texto final

Este módulo cobre só o passo 4 — substituir IDs por nomes antes de
emitir resultado pro LLM ou pra UI. Não toca em DB nem em rede.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.services.transcription.base import TranscriptionSegment


def apply_speaker_map(
    segments: Sequence[TranscriptionSegment],
    speaker_map: dict[str, str] | None,
) -> list[TranscriptionSegment]:
    """
    Substitui o `speaker` de cada segment pelo nome do mapa, quando
    presente.

    - `speaker_map=None` ou vazio: retorna cópia rasa, sem mudança.
    - Speaker em `segments` que não está no mapa: preserva o ID
      original (não fingir que tem nome quando não tem).
    - Segments com `speaker=None`: continuam None.
    """
    if not speaker_map:
        return list(segments)

    return [
        TranscriptionSegment(
            start_sec=s.start_sec,
            end_sec=s.end_sec,
            text=s.text,
            speaker=speaker_map.get(s.speaker, s.speaker) if s.speaker else None,
            confidence=s.confidence,
        )
        for s in segments
    ]


def extract_unique_speakers(
    segments: Sequence[TranscriptionSegment],
) -> list[str]:
    """
    Retorna os IDs únicos de speaker presentes em `segments`,
    ordenados pela primeira aparição. Ignora `None`.

    Útil pra UI montar a lista "renomeie estes speakers" sem
    duplicar e preservando ordem de fala — quem falou primeiro
    aparece primeiro.
    """
    seen: set[str] = set()
    unique: list[str] = []
    for s in segments:
        if s.speaker and s.speaker not in seen:
            seen.add(s.speaker)
            unique.append(s.speaker)
    return unique
