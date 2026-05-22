"""
Testes do chunker (app.services.audio.chunker).

`plan_chunks` é lógica pura — testamos sem mocks com vários cenários.
`chunk_audio_smart` chama ffmpeg pra extrair os chunks — mockamos isso.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.audio.chunker import (
    DEFAULT_MAX_CHUNK_DURATION_SEC,
    DEFAULT_SNAP_MAX_DELTA_SEC,
    AudioChunk,
    _compute_silences,
    _snap_to_silence,
    chunk_audio_smart,
    plan_chunks,
)
from app.services.audio.vad import SpeechSegment


def _segs(*pairs: tuple[float, float]) -> list[SpeechSegment]:
    return [SpeechSegment(start_sec=s, end_sec=e) for s, e in pairs]


# ============================================================
# plan_chunks — lógica pura
# ============================================================


def test_plan_empty_input_returns_empty() -> None:
    assert plan_chunks([]) == []


def test_plan_single_segment_returns_single_chunk() -> None:
    segs = _segs((10.0, 12.0))
    chunks = plan_chunks(segs)
    assert chunks == [
        AudioChunk(index=0, start_sec=10.0, end_sec=12.0, segment_count=1, file_path=None)
    ]


def test_plan_groups_segments_within_max_duration() -> None:
    # 3 segments cabendo em < 600s — vai pra 1 chunk
    segs = _segs((0.0, 5.0), (10.0, 15.0), (20.0, 25.0))
    chunks = plan_chunks(segs)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.start_sec == 0.0
    assert c.end_sec == 25.0
    assert c.segment_count == 3


def test_plan_splits_when_exceeding_max_duration() -> None:
    # Segments espaçados por 200s — limite de 600s vai estourar no 4o segment
    segs = _segs(
        (0.0, 10.0),
        (200.0, 210.0),
        (400.0, 410.0),
        (650.0, 660.0),  # adiciona estouraria pra ~660s > 600 -> fecha
        (700.0, 710.0),
    )
    chunks = plan_chunks(segs, max_chunk_duration_sec=600)
    assert len(chunks) == 2
    # Chunk 0 acumula até segment[2] (até 410s); segment[3] em 650 fecha o chunk
    assert chunks[0].index == 0
    assert chunks[0].start_sec == 0.0
    assert chunks[0].end_sec == 410.0
    assert chunks[0].segment_count == 3
    # Chunk 1 começa em 650s, contém segment[3] e segment[4]
    assert chunks[1].index == 1
    assert chunks[1].start_sec == 650.0
    assert chunks[1].end_sec == 710.0
    assert chunks[1].segment_count == 2


def test_plan_segments_arrive_unsorted() -> None:
    """Aceita lista fora de ordem (ordena internamente)."""
    segs = _segs((20.0, 25.0), (0.0, 5.0), (10.0, 15.0))
    chunks = plan_chunks(segs)
    assert chunks[0].start_sec == 0.0
    assert chunks[0].end_sec == 25.0


def test_plan_single_long_segment_becomes_own_chunk() -> None:
    """Edge: um único segment maior que o limite vira chunk único."""
    segs = _segs((0.0, 700.0))
    chunks = plan_chunks(segs, max_chunk_duration_sec=600)
    assert len(chunks) == 1
    assert chunks[0].duration_sec == 700.0


def test_plan_uses_default_max_duration() -> None:
    assert DEFAULT_MAX_CHUNK_DURATION_SEC == 600


def test_audio_chunk_duration_property() -> None:
    c = AudioChunk(index=0, start_sec=10.0, end_sec=25.0, segment_count=1)
    assert c.duration_sec == 15.0


# ============================================================
# chunk_audio_smart — integração com ffmpeg mockado
# ============================================================


def _make_audio_file(tmp_path: Path) -> Path:
    f = tmp_path / "meeting.mp3"
    f.write_bytes(b"")
    return f


def test_chunk_audio_smart_writes_one_file_per_planned_chunk(tmp_path: Path) -> None:
    audio = _make_audio_file(tmp_path)
    out_dir = tmp_path / "chunks"
    segs = _segs((0.0, 10.0), (200.0, 210.0), (650.0, 660.0))

    # Mock do `ffmpeg.input(...).output(...).overwrite_output().run(...)`
    fake_stream = MagicMock()
    fake_stream.output.return_value = fake_stream
    fake_stream.overwrite_output.return_value = fake_stream
    fake_stream.run.return_value = (b"", b"")

    with patch("ffmpeg.input", return_value=fake_stream) as input_mock:
        chunks = chunk_audio_smart(audio, segs, out_dir, max_chunk_duration_sec=600)

    assert out_dir.is_dir()
    assert len(chunks) == 2  # mesma divisão do test_plan_splits_when_exceeding_max_duration
    for ch in chunks:
        assert ch.file_path is not None
        assert ch.file_path.parent == out_dir
        assert ch.file_path.name == f"meeting_chunk_{ch.index:03d}.mp3"

    # ffmpeg.input foi chamado com `ss` e `to` corretos pra cada chunk
    calls = input_mock.call_args_list
    assert calls[0].kwargs == {"ss": chunks[0].start_sec, "to": chunks[0].end_sec}
    assert calls[1].kwargs == {"ss": chunks[1].start_sec, "to": chunks[1].end_sec}


def test_chunk_audio_smart_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        chunk_audio_smart(tmp_path / "no.mp3", [], tmp_path / "out")


def test_chunk_audio_smart_empty_segments_returns_empty(tmp_path: Path) -> None:
    audio = _make_audio_file(tmp_path)
    out_dir = tmp_path / "chunks"

    chunks = chunk_audio_smart(audio, [], out_dir)

    assert chunks == []
    assert out_dir.is_dir()  # criou o dir mesmo sem chunks


# ============================================================
# Snap-to-silence (Fase 1.9.5 / Bloco A.1)
# ============================================================


def test_default_snap_max_delta_is_15s() -> None:
    assert DEFAULT_SNAP_MAX_DELTA_SEC == 15.0


def test_snap_to_silence_empty_silences_returns_target() -> None:
    assert _snap_to_silence(120.0, []) == 120.0


def test_snap_to_silence_zero_max_delta_returns_target() -> None:
    """max_delta=0 desliga o snap (escape hatch)."""
    assert _snap_to_silence(120.0, [(118.0, 122.0)], max_delta_sec=0.0) == 120.0


def test_snap_to_silence_picks_midpoint_of_nearest() -> None:
    """Silêncio (118, 122) tem midpoint 120 — bate exato com o target."""
    assert _snap_to_silence(120.0, [(118.0, 122.0)]) == 120.0


def test_snap_to_silence_picks_midpoint_within_delta() -> None:
    """Target 120; silêncio (115, 119) midpoint=117 — dentro do raio 15."""
    assert _snap_to_silence(120.0, [(115.0, 119.0)], max_delta_sec=15.0) == 117.0


def test_snap_to_silence_outside_delta_returns_target() -> None:
    """Target 120; silêncio (150, 160) midpoint=155, dist=35 > 15. Não snap."""
    assert _snap_to_silence(120.0, [(150.0, 160.0)], max_delta_sec=15.0) == 120.0


def test_snap_to_silence_chooses_closest_among_multiple() -> None:
    """Dois silêncios candidatos — pega o midpoint mais perto."""
    silences = [
        (115.0, 119.0),  # midpoint=117 dist=3
        (124.0, 130.0),  # midpoint=127 dist=7
    ]
    assert _snap_to_silence(120.0, silences) == 117.0


def test_snap_to_silence_ignores_degenerate_silence() -> None:
    """Silêncio com start >= end é inválido — ignora."""
    silences = [
        (130.0, 125.0),  # degenerado: end < start
        (118.0, 122.0),  # válido
    ]
    assert _snap_to_silence(120.0, silences) == 120.0


def test_compute_silences_single_segment_returns_empty() -> None:
    assert _compute_silences(_segs((10.0, 20.0))) == []


def test_compute_silences_returns_gaps_between_adjacent_segments() -> None:
    segs = _segs((0.0, 5.0), (8.0, 12.0), (15.0, 20.0))
    silences = _compute_silences(segs)
    assert silences == [(5.0, 8.0), (12.0, 15.0)]


def test_compute_silences_ignores_overlapping_segments() -> None:
    """Segments com overlap (raro mas possível) — não geram silêncio."""
    segs = _segs((0.0, 10.0), (5.0, 15.0))
    assert _compute_silences(segs) == []


def test_plan_chunks_snaps_chunk_boundary_to_midpoint_of_gap() -> None:
    """
    2 chunks separados por gap pequeno: cut deve cair no meio do gap,
    não no fim da fala.

    seg1 = (0, 10), seg2 = (250, 260) com max=300 → tudo num chunk.
    Vamos forçar split com max=15: seg1 vira chunk 0; seg2 vira chunk 1.
    Gap = (10, 250), distância 120s > 15s → SEM snap. End = 10.0.

    Pra testar snap aplicado: gap pequeno (dentro de 15s).
    """
    segs = _segs((0.0, 10.0), (16.0, 20.0))
    # max=15 força split: chunk 0 = seg1, chunk 1 = seg2.
    chunks = plan_chunks(segs, max_chunk_duration_sec=15.0)
    assert len(chunks) == 2
    # Gap (10, 16) midpoint=13, distância 3 — dentro de 15. Snap aplica.
    assert chunks[0].end_sec == 13.0
    # Chunk seguinte começa no start de seg2 — snap não muda start_sec
    assert chunks[1].start_sec == 16.0


def test_plan_chunks_skips_snap_when_gap_too_far() -> None:
    """
    Quando o gap entre chunks é maior que max_delta (default 15s), o
    cut original é mantido (fim do último segment do chunk).
    """
    segs = _segs((0.0, 10.0), (200.0, 210.0))
    chunks = plan_chunks(segs, max_chunk_duration_sec=15.0)
    assert len(chunks) == 2
    # Gap (10, 200) midpoint=105, dist=95 do target 10 → fora de 15. Sem snap.
    assert chunks[0].end_sec == 10.0


def test_plan_chunks_last_chunk_never_snapped() -> None:
    """
    O último chunk não tem "próximo segment" — então nunca aplica snap.
    """
    segs = _segs((0.0, 10.0), (200.0, 210.0))
    chunks = plan_chunks(segs, max_chunk_duration_sec=15.0)
    # chunks[1] é o último — end_sec sempre = end do último segment
    assert chunks[1].end_sec == 210.0


def test_plan_chunks_custom_snap_delta_allows_larger_snaps() -> None:
    """Aumentar max_delta amplia o raio de snap."""
    segs = _segs((0.0, 10.0), (30.0, 40.0))
    # Gap (10, 30) midpoint=20, dist=10. Com max=15 → snap; com max=5 → não.
    chunks_snapped = plan_chunks(segs, max_chunk_duration_sec=15.0, snap_max_delta_sec=15.0)
    chunks_not_snapped = plan_chunks(segs, max_chunk_duration_sec=15.0, snap_max_delta_sec=5.0)
    assert chunks_snapped[0].end_sec == 20.0
    assert chunks_not_snapped[0].end_sec == 10.0


def test_chunk_audio_smart_passes_snapped_boundaries_to_ffmpeg(tmp_path: Path) -> None:
    """
    Sanity end-to-end: chunk_audio_smart respeita o snap aplicado em
    plan_chunks — `ss`/`to` do ffmpeg refletem os snapped boundaries.
    """
    audio = _make_audio_file(tmp_path)
    out_dir = tmp_path / "chunks"
    segs = _segs((0.0, 10.0), (16.0, 20.0))

    fake_stream = MagicMock()
    fake_stream.output.return_value = fake_stream
    fake_stream.overwrite_output.return_value = fake_stream
    fake_stream.run.return_value = (b"", b"")

    with patch("ffmpeg.input", return_value=fake_stream) as input_mock:
        chunks = chunk_audio_smart(audio, segs, out_dir, max_chunk_duration_sec=15.0)

    # Snap aplicado em chunk[0]: end=13.0 (midpoint do gap 10-16)
    assert chunks[0].end_sec == 13.0
    assert input_mock.call_args_list[0].kwargs == {"ss": 0.0, "to": 13.0}
