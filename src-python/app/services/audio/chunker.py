"""
Chunking inteligente: divide um áudio longo em chunks de até ~10 min,
cortando sempre em silêncio (gap entre SpeechSegments detectados pelo
VAD) — nunca no meio de uma palavra.

Por que chunkar:
- Provedores STT (Groq) limitam tamanho de arquivo (~25MB) e duração
- Paralelizar transcrição de chunks acelera reunião longa (3h → ~3min)
- Cortar em silêncios preserva palavras (cortar em 30s exatos pode
  partir palavras no meio)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.services.audio.vad import SpeechSegment

# Limite do Groq pra um único request — ficamos com 10min/chunk pra
# ter folga + bom paralelismo.
DEFAULT_MAX_CHUNK_DURATION_SEC = 600


@dataclass(frozen=True)
class AudioChunk:
    """Representa um chunk do áudio original — janela temporal."""

    index: int
    start_sec: float
    end_sec: float
    segment_count: int  # quantos SpeechSegments cabem dentro
    file_path: Path | None = None  # preenchido depois da extração via ffmpeg

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def plan_chunks(
    speech_segments: list[SpeechSegment],
    *,
    max_chunk_duration_sec: float = DEFAULT_MAX_CHUNK_DURATION_SEC,
) -> list[AudioChunk]:
    """
    Calcula as janelas de chunk SEM tocar em arquivo nenhum — só lógica
    sobre os SpeechSegments. Cada chunk começa no primeiro segment dele
    e termina no último, garantindo cortes em silêncio.

    Estratégia:
    1. Acumula segments enquanto o chunk corrente cabe em `max_chunk_duration_sec`
    2. Quando o próximo segment estouraria o limite, fecha o chunk atual
       e começa um novo a partir do próximo segment
    3. Edge: 1 segment maior que `max_chunk_duration_sec` vira chunk único
       (raro — VAD agrupa por padrão)

    Retorna lista ordenada de AudioChunks com `file_path=None`.
    """
    if not speech_segments:
        return []

    segments = sorted(speech_segments, key=lambda s: s.start_sec)
    chunks: list[AudioChunk] = []

    current_start = segments[0].start_sec
    current_end = segments[0].end_sec
    current_count = 1
    chunk_idx = 0

    for seg in segments[1:]:
        # Próxima janela hipotética se acoplarmos o segment
        projected_duration = seg.end_sec - current_start

        if projected_duration > max_chunk_duration_sec and current_count >= 1:
            # Fecha chunk atual antes de adicionar o segment novo
            chunks.append(
                AudioChunk(
                    index=chunk_idx,
                    start_sec=current_start,
                    end_sec=current_end,
                    segment_count=current_count,
                )
            )
            chunk_idx += 1
            current_start = seg.start_sec
            current_end = seg.end_sec
            current_count = 1
        else:
            current_end = seg.end_sec
            current_count += 1

    # Último chunk pendente
    chunks.append(
        AudioChunk(
            index=chunk_idx,
            start_sec=current_start,
            end_sec=current_end,
            segment_count=current_count,
        )
    )

    logger.info(
        "Chunking planejado",
        chunks=len(chunks),
        max_duration_sec=max_chunk_duration_sec,
        total_speech_sec=round(sum(c.duration_sec for c in chunks), 2),
    )
    return chunks


def chunk_audio_smart(
    audio_path: Path,
    speech_segments: list[SpeechSegment],
    output_dir: Path,
    *,
    max_chunk_duration_sec: float = DEFAULT_MAX_CHUNK_DURATION_SEC,
    sample_rate: int = 16000,
    bitrate: str = "32k",
) -> list[AudioChunk]:
    """
    Planeja chunks via `plan_chunks` e materializa cada um como MP3
    em `output_dir`. Retorna os chunks com `file_path` preenchido.

    Cada arquivo segue o padrão `{audio_path.stem}_chunk_{index}.mp3`.
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {audio_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    plan = plan_chunks(speech_segments, max_chunk_duration_sec=max_chunk_duration_sec)

    # Import lazy do ffmpeg pra que `plan_chunks` continue testável sem o
    # binário instalado.
    import ffmpeg

    materialized: list[AudioChunk] = []
    for chunk in plan:
        out_path = output_dir / f"{audio_path.stem}_chunk_{chunk.index:03d}.mp3"
        (
            ffmpeg.input(str(audio_path), ss=chunk.start_sec, to=chunk.end_sec)
            .output(
                str(out_path),
                format="mp3",
                acodec="libmp3lame",
                ac=1,
                ar=sample_rate,
                audio_bitrate=bitrate,
                loglevel="error",
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        materialized.append(
            AudioChunk(
                index=chunk.index,
                start_sec=chunk.start_sec,
                end_sec=chunk.end_sec,
                segment_count=chunk.segment_count,
                file_path=out_path,
            )
        )

    return materialized
