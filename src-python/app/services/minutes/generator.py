"""
Geração de ata via LLM (parte do pipeline da Fase 1.9).

Função pura: `transcript_text` → `MinutesOutput` via `LLMRouter`.
Não toca em DB nem em arquivo — só monta prompt, chama LLM, parseia
a resposta. A orquestração + retry + persistência mora em
`app.services.minutes.pipeline`.

Decisões de design:
- `temperature=0.2` default (princípio 1 anti-alucinação): baixo
  o suficiente pra reduzir invenção, alto o suficiente pra fluidez.
- `response_format={"type": "json_object"}` (princípio 3): força
  JSON parseável; combinado com Pydantic strict da Fase 1.7
  garante schema.
- `GenerationResult` carrega tanto `MinutesOutput` quanto
  `LLMResponse` — pipeline precisa do `LLMResponse` pra persistir
  metadata (provider, model, tokens, cost) na tabela `minutes`.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.services.llm.base import LLMMessage, LLMResponse
from app.services.llm.router import LLMRouter
from app.services.minutes.prompts import (
    SYSTEM_PROMPT_MINUTES,
    build_user_prompt,
)
from app.services.minutes.schemas import MinutesOutput
from app.services.minutes.validator import ValidationReport

DEFAULT_TEMPERATURE: float = 0.2  # Anti-alucinação (vide MAPA_PROJETO)
DEFAULT_MAX_TOKENS: int = 4096


@dataclass(frozen=True)
class GenerationResult:
    """Resultado de uma chamada de geração de ata."""

    minutes: MinutesOutput
    llm_response: LLMResponse  # tokens, cost, provider, model — pra persistir


async def generate_minutes(
    router: LLMRouter,
    transcript_text: str,
    *,
    preferred: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> GenerationResult:
    """
    Gera ata a partir da transcrição. Levanta `pydantic.ValidationError`
    se LLM emitir JSON inválido — o caller decide se faz retry.
    """
    response = await router.complete(
        messages=[
            LLMMessage(role="system", content=SYSTEM_PROMPT_MINUTES),
            LLMMessage(role="user", content=build_user_prompt(transcript_text)),
        ],
        preferred=preferred,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    minutes = MinutesOutput.model_validate_json(response.content)
    logger.info(
        "Ata gerada pelo LLM",
        provider=response.provider,
        model=response.model,
        tokens_input=response.tokens_input,
        tokens_output=response.tokens_output,
        cost_usd=round(response.cost_usd, 6),
        topics_count=len(minutes.topics),
        decisions_count=len(minutes.decisions),
        actions_count=len(minutes.action_items),
    )
    return GenerationResult(minutes=minutes, llm_response=response)


async def regenerate_with_correction(
    router: LLMRouter,
    transcript_text: str,
    report: ValidationReport,
    *,
    preferred: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> GenerationResult:
    """
    Regera ata corrigindo problemas detectados pela validação cruzada.

    O `ValidationReport.to_prompt_corrections()` (Fase 1.7) já formata
    os problemas de forma acionável pro LLM — aqui apenas injetamos
    no user prompt mantendo o system prompt estático (preserva cache).
    """
    if report.is_valid:
        raise ValueError(
            "regenerate_with_correction chamado com report válido — " "nada pra corrigir"
        )
    user_prompt = (
        f"{build_user_prompt(transcript_text)}\n\n"
        "# CORREÇÕES NECESSÁRIAS DA TENTATIVA ANTERIOR\n\n"
        f"{report.to_prompt_corrections()}"
    )
    response = await router.complete(
        messages=[
            LLMMessage(role="system", content=SYSTEM_PROMPT_MINUTES),
            LLMMessage(role="user", content=user_prompt),
        ],
        preferred=preferred,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    minutes = MinutesOutput.model_validate_json(response.content)
    logger.info(
        "Ata regenerada com correções",
        provider=response.provider,
        problems_in_prior=len(report.problems),
    )
    return GenerationResult(minutes=minutes, llm_response=response)
