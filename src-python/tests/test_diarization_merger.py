"""
Testes do merger (app.services.diarization.merger).

Foco: para cada TranscriptionSegment, escolhe o speaker que mais
sobrepõe temporalmente. Sem overlap algum, preserva o speaker
original (que pode vir do AssemblyAI). Lista de speakers vazia
retorna a transcrição inalterada.
"""

from __future__ import annotations

from app.services.diarization.merger import merge_transcription_and_diarization
from app.services.diarization.pyannote_service import SpeakerSegment
from app.services.transcription.base import TranscriptionSegment


def _ts(
    start: float,
    end: float,
    *,
    text: str = "x",
    speaker: str | None = None,
    confidence: float | None = None,
) -> TranscriptionSegment:
    return TranscriptionSegment(
        start_sec=start,
        end_sec=end,
        text=text,
        speaker=speaker,
        confidence=confidence,
    )


def _sp(start: float, end: float, speaker_id: str) -> SpeakerSegment:
    return SpeakerSegment(start_sec=start, end_sec=end, speaker_id=speaker_id)


# ============================================================
# Edge cases
# ============================================================


def test_empty_speakers_returns_transcription_unchanged() -> None:
    ts = [_ts(0.0, 1.0, text="oi", speaker="X")]
    out = merge_transcription_and_diarization(ts, [])
    assert out == ts
    # cópia rasa, não a mesma lista
    assert out is not ts


def test_empty_transcription_returns_empty() -> None:
    out = merge_transcription_and_diarization([], [_sp(0.0, 5.0, "SPEAKER_00")])
    assert out == []


# ============================================================
# Cenários típicos
# ============================================================


def test_single_speaker_assigned_to_all_transcription_segments() -> None:
    ts = [
        _ts(0.0, 2.0, text="primeira frase"),
        _ts(2.0, 4.0, text="segunda frase"),
        _ts(4.0, 6.0, text="terceira frase"),
    ]
    speakers = [_sp(0.0, 6.0, "SPEAKER_00")]
    out = merge_transcription_and_diarization(ts, speakers)
    assert all(s.speaker == "SPEAKER_00" for s in out)
    # texto e timestamps preservados
    assert [(s.start_sec, s.end_sec, s.text) for s in out] == [
        (0.0, 2.0, "primeira frase"),
        (2.0, 4.0, "segunda frase"),
        (4.0, 6.0, "terceira frase"),
    ]


def test_two_speakers_split_by_overlap() -> None:
    """SPEAKER_00 fala de 0-5s, SPEAKER_01 fala de 5-10s."""
    ts = [
        _ts(0.0, 4.0),  # toda dentro de SPEAKER_00
        _ts(6.0, 9.0),  # toda dentro de SPEAKER_01
    ]
    speakers = [
        _sp(0.0, 5.0, "SPEAKER_00"),
        _sp(5.0, 10.0, "SPEAKER_01"),
    ]
    out = merge_transcription_and_diarization(ts, speakers)
    assert out[0].speaker == "SPEAKER_00"
    assert out[1].speaker == "SPEAKER_01"


def test_dominant_speaker_wins_when_segment_spans_two() -> None:
    """
    Frase atravessa 2 speakers: 0-1s em SPEAKER_00, 1-4s em SPEAKER_01.
    Deve atribuir SPEAKER_01 (3s vs 1s).
    """
    ts = [_ts(0.0, 4.0)]
    speakers = [
        _sp(0.0, 1.0, "SPEAKER_00"),
        _sp(1.0, 4.0, "SPEAKER_01"),
    ]
    out = merge_transcription_and_diarization(ts, speakers)
    assert out[0].speaker == "SPEAKER_01"


def test_first_speaker_wins_on_exact_tie() -> None:
    """50/50 split — primeiro na lista ganha (determinístico)."""
    ts = [_ts(0.0, 2.0)]
    speakers = [
        _sp(0.0, 1.0, "SPEAKER_00"),
        _sp(1.0, 2.0, "SPEAKER_01"),
    ]
    out = merge_transcription_and_diarization(ts, speakers)
    # Ambos com overlap=1.0; mas SPEAKER_00 vem primeiro e é
    # registrado como best_speaker primeiro; SPEAKER_01 também
    # tem overlap=1.0, mas a comparação é `>`, não `>=`, então
    # SPEAKER_00 ganha
    assert out[0].speaker == "SPEAKER_00"


def test_no_overlap_preserves_original_speaker() -> None:
    """Gap na diarização: speakers do TranscriptionSegment original ficam."""
    ts = [_ts(10.0, 12.0, speaker="ORIGINAL_FROM_AAI")]
    # Speakers existem mas em outro intervalo
    speakers = [_sp(0.0, 5.0, "SPEAKER_00")]
    out = merge_transcription_and_diarization(ts, speakers)
    assert out[0].speaker == "ORIGINAL_FROM_AAI"


def test_no_overlap_and_no_original_stays_none() -> None:
    ts = [_ts(10.0, 12.0, speaker=None)]
    speakers = [_sp(0.0, 5.0, "SPEAKER_00")]
    out = merge_transcription_and_diarization(ts, speakers)
    assert out[0].speaker is None


def test_confidence_and_text_preserved() -> None:
    ts = [_ts(0.0, 1.0, text="palavra", confidence=0.95, speaker="OLD")]
    speakers = [_sp(0.0, 1.0, "NEW")]
    out = merge_transcription_and_diarization(ts, speakers)
    assert out[0].text == "palavra"
    assert out[0].confidence == 0.95
    assert out[0].speaker == "NEW"


def test_returns_new_list_does_not_mutate_input() -> None:
    ts = [_ts(0.0, 1.0, speaker="OLD")]
    speakers = [_sp(0.0, 1.0, "NEW")]
    out = merge_transcription_and_diarization(ts, speakers)
    assert out is not ts
    # Input intacto (frozen dataclass garante imutabilidade)
    assert ts[0].speaker == "OLD"


# ============================================================
# Sobreposição parcial (cenário real)
# ============================================================


def test_partial_overlap_picks_speaker_with_most_intersection() -> None:
    """
    TS de 5-15s.
    SPEAKER_00 fala de 3-8s (3s de overlap: 5-8)
    SPEAKER_01 fala de 7-20s (8s de overlap: 7-15)
    → SPEAKER_01 deve ganhar.
    """
    ts = [_ts(5.0, 15.0)]
    speakers = [
        _sp(3.0, 8.0, "SPEAKER_00"),
        _sp(7.0, 20.0, "SPEAKER_01"),
    ]
    out = merge_transcription_and_diarization(ts, speakers)
    assert out[0].speaker == "SPEAKER_01"
