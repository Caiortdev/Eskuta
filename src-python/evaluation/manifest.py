"""
Schemas do manifest do eval framework (Fase 1.9.5 / Bloco A.2).

Um `GoldenManifest` descreve uma reunião de referência:
- O áudio original (`.mp3`)
- A transcrição humana revisada (`.txt`)
- Opcionalmente, diarização humana com timestamps (`.json`)
- Opcionalmente, ata "ideal" escrita por humano (`.json` no schema MinutesOutput)

Um `BenchmarkManifest` agrupa N goldens — é o que o runner consome.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GoldenManifest(BaseModel):
    """Reunião de referência pra eval. Paths são RELATIVOS ao manifest."""

    id: str = Field(min_length=1, description="ID único da golden (ex: 'sprint-planning-01').")
    audio_path: str = Field(min_length=1)
    reference_transcript_path: str = Field(min_length=1)
    reference_diarization_path: str | None = Field(
        default=None,
        description="JSON com list de {start_sec, end_sec, speaker_id}.",
    )
    reference_minutes_path: str | None = Field(
        default=None,
        description="JSON com MinutesOutput humano (ata 'ideal' pra comparação).",
    )
    duration_sec: float = Field(gt=0)
    language: str = "pt"
    notes: str | None = None


class BenchmarkManifest(BaseModel):
    """Lista de goldens — entrada do runner."""

    name: str = Field(min_length=1)
    description: str | None = None
    goldens: list[GoldenManifest] = Field(default_factory=list)
