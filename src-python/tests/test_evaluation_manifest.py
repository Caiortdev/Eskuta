"""Testes do schema do manifest (evaluation.manifest)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from evaluation.manifest import BenchmarkManifest, GoldenManifest


def _valid_golden(**overrides) -> dict:
    base = {
        "id": "sprint-01",
        "audio_path": "sprint-01/audio.mp3",
        "reference_transcript_path": "sprint-01/reference.transcript.txt",
        "duration_sec": 3600.0,
    }
    base.update(overrides)
    return base


def test_golden_minimal_valid() -> None:
    g = GoldenManifest.model_validate(_valid_golden())
    assert g.id == "sprint-01"
    assert g.language == "pt"  # default
    assert g.reference_diarization_path is None
    assert g.reference_minutes_path is None
    assert g.notes is None


def test_golden_all_fields() -> None:
    g = GoldenManifest.model_validate(
        _valid_golden(
            reference_diarization_path="sprint-01/ref.json",
            reference_minutes_path="sprint-01/minutes.json",
            language="en",
            notes="reunião gravada via Zoom",
        )
    )
    assert g.reference_diarization_path == "sprint-01/ref.json"
    assert g.language == "en"


def test_golden_empty_id_rejected() -> None:
    with pytest.raises(ValidationError):
        GoldenManifest.model_validate(_valid_golden(id=""))


def test_golden_zero_duration_rejected() -> None:
    with pytest.raises(ValidationError):
        GoldenManifest.model_validate(_valid_golden(duration_sec=0))


def test_golden_negative_duration_rejected() -> None:
    with pytest.raises(ValidationError):
        GoldenManifest.model_validate(_valid_golden(duration_sec=-1.0))


def test_benchmark_manifest_empty_goldens_valid() -> None:
    m = BenchmarkManifest.model_validate({"name": "empty", "goldens": []})
    assert m.goldens == []


def test_benchmark_manifest_requires_name() -> None:
    with pytest.raises(ValidationError):
        BenchmarkManifest.model_validate({"goldens": []})


def test_benchmark_manifest_empty_name_rejected() -> None:
    with pytest.raises(ValidationError):
        BenchmarkManifest.model_validate({"name": "", "goldens": []})


def test_benchmark_manifest_with_goldens() -> None:
    m = BenchmarkManifest.model_validate(
        {
            "name": "MVP suite",
            "description": "5 reuniões reais",
            "goldens": [_valid_golden(), _valid_golden(id="1on1-02")],
        }
    )
    assert len(m.goldens) == 2
    assert m.goldens[0].id == "sprint-01"
    assert m.goldens[1].id == "1on1-02"
