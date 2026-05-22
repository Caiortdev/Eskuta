"""
Chunking inteligente: divide um áudio longo em chunks de até ~10 min,
cortando sempre em silêncio (gap entre SpeechSegments detectados pelo
VAD) — nunca no meio de uma palavra.

Por que chunkar:
- Provedores STT (Groq) limitam tamanho de arquivo (~25MB) e duração
- Paralelizar transcrição de chunks acelera reunião longa (3h → ~3min)
- Cortar em silêncios preserva palavras (cortar em 30s exatos pode
  partir palavras no meio)

**Snap-to-silence (Fase 1.9.5, item A.1 de MELHORIAS-CONCORRENTE):**
Quando há gap (silêncio) entre o último segment do chunk e o primeiro
do próximo, em vez de cortar no FIM da fala, ajustamos o cut pro MEIO
do silêncio adjacente. Isso dá buffer de margem nos dois lados,
reduzindo a chance de o ASR confundir borda de fala no chunk seguinte.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from loguru import logger

from app.services.audio.vad import SpeechSegment

# Limite do Groq pra um único request — ficamos com 10min/chunk pra
# ter folga + bom paralelismo.
DEFAULT_MAX_CHUNK_DURATION_SEC = 600

# Raio máximo (em segundos) pra mover o cut em direção à silência
# mais próxima. ±15s é o default sugerido em MELHORIAS-CONCORRENTE A.1.
DEFAULT_SNAP_MAX_DELTA_SEC = 15.0


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


def _compute_silences(
    speech_segments: Sequence[SpeechSegment],
) -> list[tuple[float, float]]:
    """
    Retorna as silências (gaps) entre `SpeechSegments` adjacentes —
    tuplas `(silence_start, silence_end)` em segundos. Não inclui
    silêncio antes do primeiro segment nem depois do último (não temos
    duração total do áudio aqui).
    """
    if len(speech_segments) < 2:
        return []
    ordered = sorted(speech_segments, key=lambda s: s.start_sec)
    silences: list[tuple[float, float]] = []
    for prev, nxt in pairwise(ordered):
        gap_start = prev.end_sec
        gap_end = nxt.start_sec
        if gap_end > gap_start:
            silences.append((gap_start, gap_end))
    return silences


def _snap_to_silence(
    target_sec: float,
    silences: Sequence[tuple[float, float]],
    *,
    max_delta_sec: float = DEFAULT_SNAP_MAX_DELTA_SEC,
) -> float:
    """
    Acha o silêncio com **midpoint** mais próximo de `target_sec` dentro
    de `max_delta_sec`. Retorna esse midpoint (cut point ótimo, com
    margem em ambos os lados). Se nenhum silêncio dentro do raio,
    retorna `target_sec` inalterado.

    Função pura — testável isoladamente, sem dependência de áudio nem
    de SpeechSegment. Usada pelo `plan_chunks` (snap-to-silence chunking,
    MELHORIAS-CONCORRENTE A.1) mas também pode ser usada em qualquer
    contexto que precise "ajustar um cut pro silêncio mais próximo"
    (ex: Fase 2 real-time streaming pode reusar).
    """
    if not silences or max_delta_sec <= 0:
        return target_sec
    best_midpoint: float | None = None
    best_distance = float("inf")
    for s_start, s_end in silences:
        if s_end <= s_start:
            continue  # silêncio degenerado/inválido
        midpoint = (s_start + s_end) / 2.0
        distance = abs(midpoint - target_sec)
        if distance < best_distance and distance <= max_delta_sec:
            best_distance = distance
            best_midpoint = midpoint
    return best_midpoint if best_midpoint is not None else target_sec


def plan_chunks(
    speech_segments: list[SpeechSegment],
    *,
    max_chunk_duration_sec: float = DEFAULT_MAX_CHUNK_DURATION_SEC,
    snap_max_delta_sec: float = DEFAULT_SNAP_MAX_DELTA_SEC,
) -> list[AudioChunk]:
    """
    Calcula as janelas de chunk SEM tocar em arquivo nenhum — só lógica
    sobre os SpeechSegments. Cada chunk começa no primeiro segment dele
    e termina no último, garantindo cortes em silêncio.

    Estratégia:
    1. Acumula segments enquanto o chunk corrente cabe em `max_chunk_duration_sec`
    2. Quando o próximo segment estouraria o limite, fecha o chunk atual
       e começa um novo a partir do próximo segment
    3. **Snap-to-silence:** quando há gap entre o último segment do chunk
       e o primeiro do próximo, move o cut pro MEIO do gap (em vez do
       fim da fala). Dá buffer de silêncio nos dois lados.
    4. Edge: 1 segment maior que `max_chunk_duration_sec` vira chunk único
       (raro — VAD agrupa por padrão)

    Retorna lista ordenada de AudioChunks com `file_path=None`.
    """
    if not speech_segments:
        return []

    segments = sorted(speech_segments, key=lambda s: s.start_sec)
    silences = _compute_silences(segments)
    chunks: list[AudioChunk] = []

    current_start = segments[0].start_sec
    current_end = segments[0].end_sec
    current_count = 1
    chunk_idx = 0
    snaps_applied = 0

    def _finalize_chunk(
        idx: int,
        start: float,
        end: float,
        count: int,
        next_segment_start: float | None,
    ) -> AudioChunk:
        """Aplica snap no `end` se houver silêncio entre `end` e o próximo segment."""
        nonlocal snaps_applied
        snapped_end = end
        if next_segment_start is not None and next_segment_start > end:
            # Apenas o silêncio adjacente entre este chunk e o próximo
            # segment é candidato — preserva o invariante "snap nunca
            # invade fala".
            adjacent = [(end, next_segment_start)]
            snapped_end = _snap_to_silence(
                end,
                adjacent,
                max_delta_sec=snap_max_delta_sec,
            )
            if snapped_end != end:
                snaps_applied += 1
        return AudioChunk(
            index=idx,
            start_sec=start,
            end_sec=snapped_end,
            segment_count=count,
        )

    for _i, seg in enumerate(segments[1:], start=1):
        # Próxima janela hipotética se acoplarmos o segment
        projected_duration = seg.end_sec - current_start

        if projected_duration > max_chunk_duration_sec and current_count >= 1:
            # Fecha chunk atual antes de adicionar o segment novo. O snap
            # move o cut pro meio do gap entre current_end e seg.start_sec.
            chunks.append(
                _finalize_chunk(
                    chunk_idx,
                    current_start,
                    current_end,
                    current_count,
                    next_segment_start=seg.start_sec,
                )
            )
            chunk_idx += 1
            current_start = seg.start_sec
            current_end = seg.end_sec
            current_count = 1
        else:
            current_end = seg.end_sec
            current_count += 1

    # Último chunk pendente — não há próximo segment, então sem snap.
    chunks.append(
        _finalize_chunk(
            chunk_idx,
            current_start,
            current_end,
            current_count,
            next_segment_start=None,
        )
    )

    logger.info(
        "Chunking planejado",
        chunks=len(chunks),
        max_duration_sec=max_chunk_duration_sec,
        silences_in_audio=len(silences),
        snaps_applied=snaps_applied,
        total_speech_sec=round(sum(c.duration_sec for c in chunks), 2),
    )
    return chunks


def chunk_audio_smart(
    audio_path: Path,
    speech_segments: list[SpeechSegment],
    output_dir: Path,
    *,
    max_chunk_duration_sec: float = DEFAULT_MAX_CHUNK_DURATION_SEC,
    snap_max_delta_sec: float = DEFAULT_SNAP_MAX_DELTA_SEC,
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
    plan = plan_chunks(
        speech_segments,
        max_chunk_duration_sec=max_chunk_duration_sec,
        snap_max_delta_sec=snap_max_delta_sec,
    )

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
