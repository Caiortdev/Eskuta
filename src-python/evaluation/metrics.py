"""
Métricas do eval framework (Fase 1.9.5 / Bloco A.2).

3 funções:
- `compute_wer(reference, hypothesis)` — Word Error Rate via jiwer.
- `compute_der(reference, hypothesis)` — Diarization Error Rate via pyannote.metrics.
- `compute_ata_score(...)` — LLM-as-judge usando VALIDATION_PROMPT da 1.8.

Todas funções puras (exceto ata_score que precisa de LLM router) —
testáveis isoladamente sem pipeline real.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.services.diarization.pyannote_service import SpeakerSegment
from app.services.llm.base import LLMMessage, LLMResponse
from app.services.llm.router import LLMRouter
from app.services.minutes.prompts import (
    VALIDATION_PROMPT,
    build_validation_user_prompt,
)


@dataclass(frozen=True)
class AtaScore:
    """Resultado do ata-score (LLM-as-judge)."""

    score: float  # 0-100; 100 = sem inconsistências
    issues: list[dict[str, Any]]  # array `issues` do VALIDATION_PROMPT
    llm_response: LLMResponse


# ============================================================
# Word Error Rate (WER)
# ============================================================


def compute_wer(reference: str, hypothesis: str) -> float:
    """
    WER via jiwer. Range 0.0 a 1.0+ (0 = perfeito; >1 possível com
    muitas inserções).

    Não normaliza pontuação nem capitalização — fica a cargo do caller
    (jiwer tem `Compose([...])` se quiser pre-process customizado).
    """
    from jiwer import wer as _wer

    if not reference.strip():
        # WER em referência vazia é mal-definido; convencionamos 1.0
        # (qualquer hypothesis não-vazia "erra tudo") ou 0.0 se hyp também vazia.
        return 0.0 if not hypothesis.strip() else 1.0
    return float(_wer(reference, hypothesis))


# ============================================================
# Diarization Error Rate (DER)
# ============================================================


def compute_der(
    reference: Sequence[SpeakerSegment],
    hypothesis: Sequence[SpeakerSegment],
) -> float:
    """
    DER via pyannote.metrics. Range 0.0+ (0 = perfeito).

    Calcula erro composto: tempo perdido (miss), falsamente atribuído
    (false alarm) e mal-atribuído entre speakers (speaker confusion).
    """
    from pyannote.metrics.diarization import DiarizationErrorRate

    if not reference and not hypothesis:
        return 0.0
    if not reference:
        # Hipótese diz que tem fala onde referência diz que não tem
        return 1.0

    ref_ann = _to_annotation(reference)
    hyp_ann = _to_annotation(hypothesis)
    der = DiarizationErrorRate()
    return float(der(ref_ann, hyp_ann))


def _to_annotation(segments: Sequence[SpeakerSegment]) -> Any:
    from pyannote.core import Annotation, Segment

    ann = Annotation()
    for s in segments:
        if s.end_sec > s.start_sec:
            ann[Segment(s.start_sec, s.end_sec)] = s.speaker_id
    return ann


# ============================================================
# Ata score (LLM-as-judge)
# ============================================================


async def compute_ata_score(
    minutes_json: str,
    transcript: str,
    llm_router: LLMRouter,
    *,
    preferred: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> AtaScore:
    """
    Roda VALIDATION_PROMPT (Fase 1.8) num LLM pra auditar a ata
    contra a transcrição. Score derivado:

        score = max(0, 100 - 10 * issue_count)

    8 ou mais issues → score 20 (já é ruim demais).
    Validação local via rapidfuzz (1.7) é mais barata e suficiente
    pra MVP; LLM-as-judge é pra eval quando custo de chamada é OK.
    """
    response = await llm_router.complete(
        messages=[
            LLMMessage(role="system", content=VALIDATION_PROMPT),
            LLMMessage(
                role="user",
                content=build_validation_user_prompt(transcript, minutes_json),
            ),
        ],
        preferred=preferred,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    issues = _parse_issues(response.content)
    score = max(0.0, 100.0 - 10.0 * len(issues))
    logger.info(
        "Ata score calculado",
        provider=response.provider,
        issue_count=len(issues),
        score=score,
    )
    return AtaScore(score=score, issues=issues, llm_response=response)


def _parse_issues(raw_content: str) -> list[dict[str, Any]]:
    """Extrai `issues` do JSON do LLM. Tolerante: se quebrar, retorna []."""
    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError:
        logger.warning("LLM-as-judge devolveu JSON inválido", preview=raw_content[:200])
        return []
    if not isinstance(data, dict):
        return []
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        return []
    return [i for i in issues if isinstance(i, dict)]
