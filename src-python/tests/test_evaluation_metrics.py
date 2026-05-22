"""Testes das métricas (evaluation.metrics) — WER, DER, ata_score."""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from app.services.diarization.pyannote_service import SpeakerSegment
from app.services.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.services.llm.router import LLMRouter
from evaluation.metrics import (
    AtaScore,
    _parse_issues,
    compute_ata_score,
    compute_der,
    compute_wer,
)

# ============================================================
# compute_wer
# ============================================================


def test_wer_identical_strings_is_zero() -> None:
    assert compute_wer("olá mundo", "olá mundo") == 0.0


def test_wer_one_word_substitution() -> None:
    # 1 erro em 2 palavras → 0.5
    score = compute_wer("olá mundo", "olá galaxia")
    assert score == pytest.approx(0.5)


def test_wer_completely_different() -> None:
    # Todas palavras diferentes — WER >= 1.0 (todas erradas)
    score = compute_wer("abc def", "xyz qwerty")
    assert score >= 1.0


def test_wer_empty_reference_empty_hyp_is_zero() -> None:
    assert compute_wer("", "") == 0.0


def test_wer_empty_reference_nonempty_hyp_is_one() -> None:
    """Convenção: refs vazia + hyp com texto = 1.0 (mal-definido)."""
    assert compute_wer("", "qualquer coisa") == 1.0


def test_wer_extra_words_in_hypothesis() -> None:
    # 1 inserção em 2 palavras de ref → 0.5
    score = compute_wer("olá mundo", "olá mundo extra")
    assert score > 0.0


# ============================================================
# compute_der
# ============================================================


def _seg(start: float, end: float, speaker: str) -> SpeakerSegment:
    return SpeakerSegment(start_sec=start, end_sec=end, speaker_id=speaker)


def test_der_identical_diarizations_is_zero() -> None:
    ref = [_seg(0.0, 5.0, "A"), _seg(5.0, 10.0, "B")]
    hyp = [_seg(0.0, 5.0, "A"), _seg(5.0, 10.0, "B")]
    assert compute_der(ref, hyp) == pytest.approx(0.0)


def test_der_both_empty_is_zero() -> None:
    assert compute_der([], []) == 0.0


def test_der_empty_reference_hyp_nonempty_is_one() -> None:
    assert compute_der([], [_seg(0.0, 5.0, "A")]) == 1.0


def test_der_completely_wrong_speakers() -> None:
    """Mesmo intervalos, speakers trocados — DER alto (depende do mapping)."""
    ref = [_seg(0.0, 5.0, "A"), _seg(5.0, 10.0, "B")]
    hyp = [_seg(0.0, 10.0, "C")]
    # Não checamos valor exato; só que reporta erro significativo
    assert compute_der(ref, hyp) > 0.0


def test_der_ignores_degenerate_segments() -> None:
    """Segments com end <= start são puladas."""
    ref = [_seg(0.0, 5.0, "A"), _seg(7.0, 5.0, "BAD")]  # 2o segment inválido
    hyp = [_seg(0.0, 5.0, "A")]
    # Sem o segment inválido, ref == hyp → DER 0
    assert compute_der(ref, hyp) == pytest.approx(0.0)


# ============================================================
# _parse_issues (helper interno)
# ============================================================


def test_parse_issues_valid_json() -> None:
    raw = json.dumps({"issues": [{"type": "fabricated_evidence", "location": "x"}]})
    issues = _parse_issues(raw)
    assert len(issues) == 1
    assert issues[0]["type"] == "fabricated_evidence"


def test_parse_issues_invalid_json_returns_empty() -> None:
    assert _parse_issues("not json {") == []


def test_parse_issues_non_dict_returns_empty() -> None:
    assert _parse_issues(json.dumps([1, 2, 3])) == []


def test_parse_issues_missing_issues_field_returns_empty() -> None:
    assert _parse_issues(json.dumps({"foo": "bar"})) == []


def test_parse_issues_non_list_issues_returns_empty() -> None:
    assert _parse_issues(json.dumps({"issues": "not a list"})) == []


def test_parse_issues_filters_non_dict_items() -> None:
    raw = json.dumps({"issues": [{"x": 1}, "not a dict", 42, {"y": 2}]})
    issues = _parse_issues(raw)
    assert len(issues) == 2


# ============================================================
# compute_ata_score
# ============================================================


class _FakeLLMProvider(LLMProvider):
    def __init__(self, content: str) -> None:
        self.content = content

    @property
    def name(self) -> str:
        return "fake"

    @property
    def default_model(self) -> str:
        return "fake-model"

    def is_available(self) -> bool:
        return True

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            content=self.content,
            provider=self.name,
            model=self.default_model,
            tokens_input=100,
            tokens_output=50,
            cost_usd=0.001,
        )


def _router_with_response(content: str) -> LLMRouter:
    return LLMRouter({"fake": _FakeLLMProvider(content)})


async def test_ata_score_no_issues_is_100() -> None:
    router = _router_with_response(json.dumps({"issues": []}))
    result = await compute_ata_score("{}", "transcript", router)
    assert isinstance(result, AtaScore)
    assert result.score == 100.0
    assert result.issues == []


async def test_ata_score_one_issue_subtracts_10() -> None:
    router = _router_with_response(
        json.dumps({"issues": [{"type": "fabricated_evidence", "location": "x"}]})
    )
    result = await compute_ata_score("{}", "transcript", router)
    assert result.score == 90.0
    assert len(result.issues) == 1


async def test_ata_score_capped_at_zero() -> None:
    """20+ issues → score não vira negativo."""
    issues = [{"type": "other", "location": str(i)} for i in range(20)]
    router = _router_with_response(json.dumps({"issues": issues}))
    result = await compute_ata_score("{}", "transcript", router)
    assert result.score == 0.0


async def test_ata_score_malformed_json_treats_as_zero_issues() -> None:
    """LLM-as-judge devolveu lixo — não crasha, assume 0 issues."""
    router = _router_with_response("not even close to JSON")
    result = await compute_ata_score("{}", "transcript", router)
    assert result.score == 100.0


async def test_ata_score_uses_validation_prompt_as_system() -> None:
    """Garante que o VALIDATION_PROMPT da Fase 1.8 é usado como system."""
    captured: dict = {}

    class _SpyProvider(_FakeLLMProvider):
        async def complete(self, messages, *args, **kwargs):
            captured["messages"] = list(messages)
            return await super().complete(messages, *args, **kwargs)

    router = LLMRouter({"fake": _SpyProvider(json.dumps({"issues": []}))})
    await compute_ata_score("{}", "qualquer transcript", router)

    msgs = captured["messages"]
    assert msgs[0].role == "system"
    assert "auditor" in msgs[0].content.lower()
    assert msgs[1].role == "user"
    assert "qualquer transcript" in msgs[1].content


async def test_ata_score_forces_json_response_format() -> None:
    captured: dict = {}

    class _SpyProvider(_FakeLLMProvider):
        async def complete(self, messages, *, response_format=None, **kwargs):
            captured["response_format"] = response_format
            return await super().complete(messages, response_format=response_format, **kwargs)

    router = LLMRouter({"fake": _SpyProvider(json.dumps({"issues": []}))})
    await compute_ata_score("{}", "x", router)

    assert captured["response_format"] == {"type": "json_object"}
