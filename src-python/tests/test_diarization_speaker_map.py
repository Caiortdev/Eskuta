"""
Testes do speaker_map (app.services.diarization.speaker_map).

apply_speaker_map substitui IDs anônimos por nomes humanos.
extract_unique_speakers lista IDs únicos preservando ordem de fala.
"""

from __future__ import annotations

from app.services.diarization.speaker_map import (
    apply_speaker_map,
    extract_unique_speakers,
)
from app.services.transcription.base import TranscriptionSegment


def _ts(text: str, speaker: str | None) -> TranscriptionSegment:
    return TranscriptionSegment(start_sec=0.0, end_sec=1.0, text=text, speaker=speaker)


# ============================================================
# apply_speaker_map
# ============================================================


def test_none_map_returns_segments_unchanged() -> None:
    ts = [_ts("oi", "SPEAKER_00")]
    out = apply_speaker_map(ts, None)
    assert out == ts
    assert out is not ts  # cópia rasa


def test_empty_map_returns_segments_unchanged() -> None:
    ts = [_ts("oi", "SPEAKER_00")]
    out = apply_speaker_map(ts, {})
    assert out[0].speaker == "SPEAKER_00"


def test_map_substitutes_known_ids() -> None:
    ts = [
        _ts("oi", "SPEAKER_00"),
        _ts("tudo bem?", "SPEAKER_01"),
    ]
    out = apply_speaker_map(ts, {"SPEAKER_00": "João", "SPEAKER_01": "Maria"})
    assert out[0].speaker == "João"
    assert out[1].speaker == "Maria"


def test_unmapped_speakers_preserved_as_is() -> None:
    """Se a UI só nomeou um speaker, o outro fica como SPEAKER_XX."""
    ts = [
        _ts("oi", "SPEAKER_00"),
        _ts("tudo bem?", "SPEAKER_01"),
    ]
    out = apply_speaker_map(ts, {"SPEAKER_00": "João"})
    assert out[0].speaker == "João"
    assert out[1].speaker == "SPEAKER_01"  # não inventou nome


def test_none_speakers_stay_none() -> None:
    ts = [_ts("oi", None)]
    out = apply_speaker_map(ts, {"SPEAKER_00": "João"})
    assert out[0].speaker is None


def test_apply_does_not_mutate_input() -> None:
    ts = [_ts("oi", "SPEAKER_00")]
    apply_speaker_map(ts, {"SPEAKER_00": "João"})
    assert ts[0].speaker == "SPEAKER_00"  # frozen dataclass garante


def test_text_and_timestamps_preserved() -> None:
    ts = [
        TranscriptionSegment(
            start_sec=10.0,
            end_sec=12.5,
            text="palavra",
            speaker="SPEAKER_00",
            confidence=0.9,
        ),
    ]
    out = apply_speaker_map(ts, {"SPEAKER_00": "João"})
    assert out[0].start_sec == 10.0
    assert out[0].end_sec == 12.5
    assert out[0].text == "palavra"
    assert out[0].confidence == 0.9
    assert out[0].speaker == "João"


# ============================================================
# extract_unique_speakers
# ============================================================


def test_extract_unique_preserves_first_appearance_order() -> None:
    ts = [
        _ts("a", "SPEAKER_01"),
        _ts("b", "SPEAKER_00"),
        _ts("c", "SPEAKER_01"),  # repete, não duplica
        _ts("d", "SPEAKER_02"),
        _ts("e", "SPEAKER_00"),  # repete, não duplica
    ]
    assert extract_unique_speakers(ts) == ["SPEAKER_01", "SPEAKER_00", "SPEAKER_02"]


def test_extract_unique_ignores_none_speakers() -> None:
    ts = [
        _ts("a", None),
        _ts("b", "SPEAKER_00"),
        _ts("c", None),
    ]
    assert extract_unique_speakers(ts) == ["SPEAKER_00"]


def test_extract_unique_returns_empty_for_empty_input() -> None:
    assert extract_unique_speakers([]) == []


def test_extract_unique_returns_empty_when_all_none() -> None:
    ts = [_ts("a", None), _ts("b", None)]
    assert extract_unique_speakers(ts) == []


def test_extract_unique_single_speaker() -> None:
    ts = [_ts("a", "SPEAKER_00"), _ts("b", "SPEAKER_00")]
    assert extract_unique_speakers(ts) == ["SPEAKER_00"]
