"""
Benchmark do `validate_minutes` (Fase 1.9.5 / Bloco A.4).

Mede tempo de validação anti-alucinação via rapidfuzz contra
transcrições de tamanho variado. Esta é a operação que roda em TODA
geração de ata; regressão aqui multiplica direto na UX.
"""

from __future__ import annotations

import pytest

from app.services.minutes.schemas import (
    ActionItem,
    Decision,
    Evidence,
    MinutesOutput,
    Topic,
)
from app.services.minutes.validator import validate_minutes


def _make_transcript(repetitions: int) -> str:
    """Gera transcript sintético com N repetições do mesmo fragmento."""
    base = (
        "João: então gente, sobre o projeto Alpha eu acho que devemos adiar. "
        "Maria: concordo, vou avisar o cliente. "
    )
    return base * repetitions


def _make_minutes(invented: bool = False) -> MinutesOutput:
    """Ata canônica — com quote real ou inventada."""
    quote = (
        "sobre o projeto Alpha eu acho que devemos adiar"
        if not invented
        else "decisão fantasma inventada"
    )
    return MinutesOutput(
        title="Reunião X",
        executive_summary="Resumo",
        topics=[
            Topic(title="A", summary="B", evidence=Evidence(quote=quote)),
        ],
        decisions=[
            Decision(description="X", evidence=Evidence(quote=quote)),
        ],
        action_items=[
            ActionItem(description="Y", evidence=Evidence(quote=quote)),
        ],
    )


@pytest.mark.benchmark(group="validator")
def test_bench_validate_minutes_small_transcript(benchmark) -> None:
    """Transcript ~1KB — reunião curta."""
    transcript = _make_transcript(5)
    minutes = _make_minutes()
    result = benchmark(validate_minutes, minutes, transcript)
    assert result.is_valid


@pytest.mark.benchmark(group="validator")
def test_bench_validate_minutes_medium_transcript(benchmark) -> None:
    """Transcript ~100KB — reunião de ~1h."""
    transcript = _make_transcript(500)
    minutes = _make_minutes()
    result = benchmark(validate_minutes, minutes, transcript)
    assert result.is_valid


@pytest.mark.benchmark(group="validator")
def test_bench_validate_minutes_large_transcript(benchmark) -> None:
    """Transcript ~500KB — reunião de 3h (limite MVP)."""
    transcript = _make_transcript(2500)
    minutes = _make_minutes()
    result = benchmark(validate_minutes, minutes, transcript)
    assert result.is_valid


@pytest.mark.benchmark(group="validator")
def test_bench_validate_invalid_minutes_fast_path(benchmark) -> None:
    """
    Quote inventada — sai rápido do fast path (exato fail) e cai no
    fuzzy. Mede pior caso: tem que percorrer transcript inteiro.
    """
    transcript = _make_transcript(500)
    minutes = _make_minutes(invented=True)
    result = benchmark(validate_minutes, minutes, transcript)
    assert not result.is_valid
