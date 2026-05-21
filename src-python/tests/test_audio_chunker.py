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
    AudioChunk,
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
