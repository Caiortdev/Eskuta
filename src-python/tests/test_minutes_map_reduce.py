"""
Testes do pipeline map-reduce (app.services.minutes.map_reduce).

Cobrem:
- Split do transcript em chunks respeitando boundaries de sentenças
- Hard-split como fallback em sentenças gigantes
- Threshold de decisão (single-pass vs map-reduce)
- Map paralelo com FakeLLM
- Reduce consolidando N mini-atas
- Resiliência a chunk individual falhando no map
- Fallback determinístico se reduce falhar
- Roteamento automático via generator.generate_minutes()
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from app.services.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.services.llm.router import LLMRouter
from app.services.minutes.generator import generate_minutes
from app.services.minutes.map_reduce import (
    DEFAULT_MAP_CHUNK_CHARS,
    MAP_REDUCE_THRESHOLD_CHARS,
    PRESERVATION_MAX_RATIO,
    PRESERVATION_MIN_RATIO,
    _compute_preservation,
    _deterministic_merge,
    _find_potential_duplicates,
    generate_minutes_map_reduce,
    split_transcript_for_map,
)
from app.services.minutes.prompts import FEW_SHOT_EXAMPLE_MINUTES
from app.services.minutes.schemas import MinutesOutput

# ============================================================
# Split do transcript
# ============================================================


class TestSplitTranscript:
    def test_empty_returns_empty(self) -> None:
        assert split_transcript_for_map("") == []

    def test_short_text_single_chunk(self) -> None:
        text = "Boa tarde. Tudo bem? Tudo otimo, obrigado."
        chunks = split_transcript_for_map(text, max_chunk_chars=1000)
        assert chunks == [text]

    def test_splits_respecting_sentence_boundary(self) -> None:
        """Junta sentencas ate o limite e quebra ANTES do proximo ponto."""
        sentences = [f"Sentenca numero {i} acabando aqui." for i in range(20)]
        text = " ".join(sentences)
        chunks = split_transcript_for_map(text, max_chunk_chars=200)

        # Cada chunk fica <= max_chars + pequena margem (uma sentenca pode
        # encaixar exato em chunk_chars sem ultrapassar)
        for chunk in chunks:
            assert len(chunk) <= 200

        # Soma do conteudo == texto original (modulo whitespace)
        all_chars = sum(len(c) for c in chunks)
        assert all_chars >= len(text) * 0.95

    def test_hard_split_for_giant_sentence(self) -> None:
        """Sentenca sem pontuacao bem grande -> hard split por palavras."""
        text = "palavra " * 2000  # ~16k chars sem nenhum ponto final
        chunks = split_transcript_for_map(text, max_chunk_chars=1000)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) <= 1000

    def test_preserves_all_content(self) -> None:
        """Sem perder palavras no split."""
        text = (
            "Primeira sentenca. Segunda sentenca aqui. Terceira tambem. "
            "Quarta agora vamos. Quinta finalizando."
        )
        chunks = split_transcript_for_map(text, max_chunk_chars=50)
        joined = " ".join(chunks)
        # Cada palavra do original aparece em algum chunk
        for word in text.split():
            assert word in joined, f"Palavra perdida: {word!r}"


# ============================================================
# FakeLLM helpers
# ============================================================


class _FakeLLMProvider(LLMProvider):
    """LLM fake que devolve resposta de fila — uma por call."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    @property
    def name(self) -> str:
        return "fake-llm"

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
        self.calls.append(
            {
                "messages": list(messages),
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise RuntimeError("FakeLLM sem responses pra retornar")
        payload = self.responses.pop(0)
        return LLMResponse(
            content=payload,
            provider=self.name,
            model=model or self.default_model,
            tokens_input=100,
            tokens_output=200,
            cost_usd=0.001,
        )


def _example_minutes_json() -> str:
    return json.dumps(FEW_SHOT_EXAMPLE_MINUTES)


def _minimal_minutes_json(title: str = "Parte X") -> str:
    """Mini-ata mínima válida (Pydantic) — pra ser MAP output."""
    return json.dumps(
        {
            "title": title,
            "executive_summary": f"Resumo curto de {title}",
            "participants": ["Alice"],
            "topics": [],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        }
    )


# ============================================================
# Map phase
# ============================================================


@pytest.mark.asyncio
async def test_map_reduce_calls_n_maps_plus_one_reduce() -> None:
    """3 chunks => 3 calls de map + 1 call de reduce = 4 calls totais."""
    transcript = (
        "Sentenca curta. " * 5  # ~75 chars
    ) + ("Outra sentenca aqui. " * 50)  # ~1000 chars
    # max_chunk_chars=300 -> ~3-5 chunks dependendo do split
    provider = _FakeLLMProvider(
        responses=[
            _minimal_minutes_json("Parte 1"),
            _minimal_minutes_json("Parte 2"),
            _minimal_minutes_json("Parte 3"),
            _minimal_minutes_json("Parte 4"),
            _minimal_minutes_json("Parte 5"),
            _minimal_minutes_json("Parte 6"),
            _minimal_minutes_json("Parte 7"),
            _example_minutes_json(),  # reduce
        ]
    )
    router = LLMRouter({"fake": provider})

    result = await generate_minutes_map_reduce(
        router,
        transcript,
        max_chunk_chars=300,
    )

    # Pelo menos 2 chunks (transcript > 300)
    assert result.map_calls >= 2
    # Calls = N maps + 1 reduce
    assert len(provider.calls) == result.map_calls + 1
    assert result.minutes.title  # title final veio do reduce


@pytest.mark.asyncio
async def test_map_reduce_survives_single_chunk_failure() -> None:
    """
    Se ALGUNS chunks do map devolverem JSON quebrado, os outros seguem.

    Setup: alternamos respostas válidas e inválidas — metade dos chunks
    falha, metade passa. Como cada chunk tem 2 tentativas, uma resposta
    inválida pode virar válida no retry; pra garantir falha consistente
    intercalamos pares (inválida, inválida) com (válida, _).
    """
    transcript = (
        ("Primeiro trecho aqui. " * 50)
        + ("Segundo trecho diferente. " * 50)
        + ("Terceiro trecho aqui. " * 50)
    )

    # Mistura: pra cada chunk hipotético, fornecemos 2 responses
    # (1ª tentativa + retry). Alternamos chunks ok e chunks ruins.
    # Reduce no fim consome 1 resposta válida.
    responses: list[str] = []
    for i in range(40):  # cobre até 20 chunks teóricos (cada com 2 tentativas)
        if i % 4 < 2:
            responses.append(_minimal_minutes_json(f"Parte {i}"))
        else:
            responses.append("<<< JSON QUEBRADO >>>")
    responses.append(_example_minutes_json())  # reduce

    provider = _FakeLLMProvider(responses=responses)
    router = LLMRouter({"fake": provider})

    result = await generate_minutes_map_reduce(
        router,
        transcript,
        max_chunk_chars=400,
    )
    # Pelo menos 1 chunk sobreviveu — pipeline não levanta
    assert result.map_calls >= 1
    assert result.minutes.title


@pytest.mark.asyncio
async def test_map_reduce_fails_when_all_chunks_fail() -> None:
    """Se TODOS os chunks falharem no map, levanta ValueError."""
    transcript = "Trecho. " * 200
    provider = _FakeLLMProvider(
        responses=["<<< INVALIDO >>>"] * 20  # tudo invalido
    )
    router = LLMRouter({"fake": provider})

    with pytest.raises(ValueError, match="map chunks falharam"):
        await generate_minutes_map_reduce(
            router,
            transcript,
            max_chunk_chars=200,
        )


@pytest.mark.asyncio
async def test_map_reduce_fallback_when_reduce_fails() -> None:
    """
    Reduce falha 2x → fallback deterministico salva o dia.

    Pré-alocamos várias responses válidas pra TODOS os chunks do map
    (não importa quantos sejam), e depois 2 inválidas pro reduce.
    """
    transcript = ("Primeiro chunk. " * 50) + ("Segundo chunk diferente. " * 50)

    # 20 responses válidas pro map (cobre qualquer split razoável),
    # depois 2 inválidas pro reduce
    responses = [_minimal_minutes_json(f"Parte {i}") for i in range(20)]
    responses += ["<<< REDUCE QUEBRADO >>>", "<<< REDUCE QUEBRADO >>>"]

    provider = _FakeLLMProvider(responses=responses)
    router = LLMRouter({"fake": provider})

    result = await generate_minutes_map_reduce(
        router,
        transcript,
        max_chunk_chars=400,
    )
    # Fallback gerou ata valida deterministicamente
    assert result.minutes.title  # title placeholder do deterministic_merge
    assert result.minutes.executive_summary  # union dos partials


# ============================================================
# Deterministic merge
# ============================================================


def test_deterministic_merge_union_of_partials() -> None:
    p1 = MinutesOutput.model_validate(json.loads(_minimal_minutes_json("Parte 1")))
    p2_dict = json.loads(_minimal_minutes_json("Parte 2"))
    p2_dict["participants"] = ["Alice", "Bob"]
    p2 = MinutesOutput.model_validate(p2_dict)

    merged = _deterministic_merge([p1, p2])
    assert "Alice" in merged.participants
    assert "Bob" in merged.participants
    assert merged.title  # placeholder valido


# ============================================================
# Roteamento via generate_minutes
# ============================================================


@pytest.mark.asyncio
async def test_generate_minutes_uses_single_pass_below_threshold() -> None:
    """transcript curto NAO deve disparar map-reduce."""
    transcript = "Reuniao curta sobre projeto X."
    assert len(transcript) < MAP_REDUCE_THRESHOLD_CHARS

    provider = _FakeLLMProvider(responses=[_example_minutes_json()])
    router = LLMRouter({"fake": provider})

    await generate_minutes(router, transcript)
    # Single pass => 1 unica call ao LLM
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_generate_minutes_uses_map_reduce_above_threshold() -> None:
    """transcript longo dispara map-reduce automatico."""
    transcript = "Bla bla bla blz reuniao. " * 2500  # ~60k chars
    assert len(transcript) > MAP_REDUCE_THRESHOLD_CHARS

    # Pre-alocar muitas responses pra map (~ 3 chunks de 20k)
    provider = _FakeLLMProvider(
        responses=[_minimal_minutes_json(f"Parte {i}") for i in range(10)]
        + [_example_minutes_json()]  # reduce
    )
    router = LLMRouter({"fake": provider})

    result = await generate_minutes(router, transcript)

    # Pelo menos 2 calls (≥1 map + 1 reduce)
    assert len(provider.calls) >= 2
    assert result.minutes.title


# ============================================================
# Dedup determinístico (rapidfuzz)
# ============================================================


def _minutes_with(
    *,
    topics: list[str] | None = None,
    decisions: list[str] | None = None,
    actions: list[str] | None = None,
) -> MinutesOutput:
    """Helper pra criar MinutesOutput rápido com items de strings."""
    return MinutesOutput.model_validate(
        {
            "title": "x",
            "executive_summary": "y",
            "participants": [],
            "topics": [
                {
                    "title": t,
                    "summary": "summary",
                    "evidence": {"quote": "q"},
                }
                for t in (topics or [])
            ],
            "decisions": [
                {"description": d, "evidence": {"quote": "q"}} for d in (decisions or [])
            ],
            "action_items": [
                {"description": a, "evidence": {"quote": "q"}} for a in (actions or [])
            ],
            "open_questions": [],
        }
    )


def test_find_duplicates_detects_obvious_pairs() -> None:
    """2 partials com decisões praticamente iguais → 1 par detectado."""
    p1 = _minutes_with(decisions=["Aprovado o orçamento de design em 15 mil reais"])
    p2 = _minutes_with(decisions=["Aprovamos orçamento de design em 15 mil reais"])
    dups = _find_potential_duplicates([p1, p2])
    assert len(dups["decisions"]) == 1
    a, b, sim = dups["decisions"][0]
    assert sim >= 90


def test_find_duplicates_ignores_different_items() -> None:
    """Items diferentes não devem ser flaggados."""
    p1 = _minutes_with(decisions=["Decidir nova arquitetura do backend"])
    p2 = _minutes_with(decisions=["Contratar nova pessoa de marketing"])
    dups = _find_potential_duplicates([p1, p2])
    assert dups["decisions"] == []


def test_find_duplicates_does_not_compare_within_same_partial() -> None:
    """Items duplicados DENTRO de um partial não são reportados — o map
    já fez o trabalho dele, não vamos questionar."""
    p1 = _minutes_with(decisions=["Decisão X exatamente", "Decisão X exatamente"])
    dups = _find_potential_duplicates([p1])
    assert dups["decisions"] == []


# ============================================================
# Preservation report
# ============================================================


def test_preservation_ok_when_close_to_sum() -> None:
    p1 = _minutes_with(topics=["A", "B"], decisions=["X"])
    p2 = _minutes_with(topics=["C"], decisions=["Y"])
    final = _minutes_with(topics=["A", "B", "C"], decisions=["X", "Y"])
    report = _compute_preservation([p1, p2], final)
    assert report.is_ok
    assert not report.has_mutilation
    assert not report.has_hallucination


def test_preservation_mutilation_below_threshold() -> None:
    """Se < 50% dos items foram preservados, flagga mutilação."""
    p1 = _minutes_with(topics=["A", "B", "C", "D"], decisions=["X", "Y", "Z"])
    p2 = _minutes_with(topics=["E", "F"], decisions=["W"])
    # 6 topics → final só 1 (< 50%)
    final = _minutes_with(topics=["A"], decisions=["X", "Y", "Z", "W"])
    report = _compute_preservation([p1, p2], final)
    assert report.has_mutilation is True
    assert report.is_ok is False
    assert report.topics_ratio < PRESERVATION_MIN_RATIO


def test_preservation_hallucination_above_threshold() -> None:
    """Se > 150% dos items, flagga alucinação (inventou)."""
    p1 = _minutes_with(topics=["A"], decisions=["X"])
    # 1 topic → final 3 (300% > 150%)
    final = _minutes_with(topics=["A", "B", "C"], decisions=["X"])
    report = _compute_preservation([p1], final)
    assert report.has_hallucination is True
    assert report.is_ok is False
    assert report.topics_ratio > PRESERVATION_MAX_RATIO


def test_preservation_diagnostics_contains_problem_label() -> None:
    p1 = _minutes_with(topics=["A", "B", "C", "D"])
    final = _minutes_with(topics=["A"])
    report = _compute_preservation([p1], final)
    diag = report.to_diagnostics()
    assert "ESPREMEU" in diag
    assert "Tópicos" in diag


# ============================================================
# Auto-regen via map-reduce
# ============================================================


@pytest.mark.asyncio
async def test_map_reduce_regenerates_when_reduce_mutilates() -> None:
    """1ª tentativa de reduce esprime demais → 2ª regen com prompt corretivo
    devolve ata respeitando preservação. Termina com is_ok."""
    transcript = "Primeiro trecho. " * 30 + "Segundo trecho. " * 30 + "Terceiro trecho. " * 30

    # MAP devolve 3 partials com vários items
    map_response_rich = json.dumps(
        {
            "title": "Parte X",
            "executive_summary": "Resumo da parte",
            "participants": [],
            "topics": [
                {"title": f"Topic {i}", "summary": "s", "evidence": {"quote": "q"}}
                for i in range(3)
            ],
            "decisions": [
                {"description": f"Decisao {i}", "evidence": {"quote": "q"}} for i in range(3)
            ],
            "action_items": [],
            "open_questions": [],
        }
    )

    # 1ª reduce: esprime tudo pra 1 topic (mutilação)
    reduce_bad = json.dumps(
        {
            "title": "Final ruim",
            "executive_summary": "x",
            "participants": [],
            "topics": [{"title": "Único", "summary": "s", "evidence": {"quote": "q"}}],
            "decisions": [{"description": "Uma só", "evidence": {"quote": "q"}}],
            "action_items": [],
            "open_questions": [],
        }
    )

    # 2ª reduce (regen): preserva
    reduce_good = json.dumps(
        {
            "title": "Final boa",
            "executive_summary": "y",
            "participants": [],
            "topics": [
                {"title": f"T{i}", "summary": "s", "evidence": {"quote": "q"}} for i in range(8)
            ],
            "decisions": [{"description": f"D{i}", "evidence": {"quote": "q"}} for i in range(8)],
            "action_items": [],
            "open_questions": [],
        }
    )

    provider = _FakeLLMProvider(responses=[map_response_rich] * 10 + [reduce_bad, reduce_good])
    router = LLMRouter({"fake": provider})

    result = await generate_minutes_map_reduce(router, transcript, max_chunk_chars=400)

    # Resultado final é a 2ª reduce (boa) — pelo menos 5 topics
    assert len(result.minutes.topics) >= 5


@pytest.mark.asyncio
async def test_map_reduce_falls_back_when_regen_does_not_converge() -> None:
    """Se nenhuma das tentativas de reduce alcançar preservation OK,
    cai pro fallback determinístico (que NUNCA inventa)."""
    transcript = "Trecho A. " * 30 + "Trecho B. " * 30

    map_response_rich = json.dumps(
        {
            "title": "Parte X",
            "executive_summary": "Resumo",
            "participants": [],
            "topics": [
                {"title": f"Topic {i}", "summary": "s", "evidence": {"quote": "q"}}
                for i in range(4)
            ],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        }
    )

    # TODAS as tentativas de reduce esprimem demais
    reduce_bad = json.dumps(
        {
            "title": "Ruim",
            "executive_summary": "x",
            "participants": [],
            "topics": [{"title": "1", "summary": "s", "evidence": {"quote": "q"}}],
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        }
    )

    # 10 map responses + 3 reduce bad (1 inicial + 2 regen)
    provider = _FakeLLMProvider(responses=[map_response_rich] * 10 + [reduce_bad] * 3)
    router = LLMRouter({"fake": provider})

    result = await generate_minutes_map_reduce(router, transcript, max_chunk_chars=400)
    # Fallback determinístico — pega TODOS os topics das mini-atas
    # (cada partial tinha 4 topics, mínimo 2 partials = 8+ topics finais)
    assert len(result.minutes.topics) >= 4


# ============================================================
# Constants sanity
# ============================================================


def test_threshold_default_makes_sense() -> None:
    """Threshold tem que ser maior que chunk default — senao map-reduce eh
    o tempo todo."""
    assert MAP_REDUCE_THRESHOLD_CHARS > DEFAULT_MAP_CHUNK_CHARS


def test_preservation_constants_sane() -> None:
    assert 0 < PRESERVATION_MIN_RATIO < 1
    assert PRESERVATION_MAX_RATIO > 1
