"""
Geração de ata via LLM (parte do pipeline da Fase 1.9).

Função pura: `transcript_text` → `MinutesOutput` via `LLMRouter`.
Não toca em DB nem em arquivo — só monta prompt, chama LLM, parseia
a resposta. A orquestração + retry de validação semântica + persistência
mora em `app.services.minutes.pipeline`.

Decisões de design:
- `temperature=0.2` default (princípio 1 anti-alucinação): baixo
  o suficiente pra reduzir invenção, alto o suficiente pra fluidez.
- `response_format={"type": "json_object"}` (princípio 3): força
  JSON parseável; combinado com Pydantic strict da Fase 1.7
  garante schema.
- `GenerationResult` carrega tanto `MinutesOutput` quanto
  `LLMResponse` — pipeline precisa do `LLMResponse` pra persistir
  metadata (provider, model, tokens, cost) na tabela `minutes`.
- **Retry interno (Fase 1.13)**: se o LLM emitir JSON sintaticamente
  inválido (truncamento por max_tokens, hallucination de fechamento),
  fazemos até `JSON_PARSE_RETRY` tentativas adicionais com prompt
  reforçando concisão e fechamento de aspas. Isso é DIFERENTE do regen
  semântico do pipeline (`_validate_and_regen`), que trata problemas de
  evidência/fidelidade, não de parseabilidade.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from pydantic import ValidationError

from app.services.llm.base import LLMMessage, LLMResponse
from app.services.llm.router import LLMRouter
from app.services.minutes.map_reduce import (
    MAP_REDUCE_THRESHOLD_CHARS,
    generate_minutes_map_reduce,
)
from app.services.minutes.prompts import (
    SYSTEM_PROMPT_MINUTES,
    build_user_prompt,
)
from app.services.minutes.schemas import MinutesOutput
from app.services.minutes.validator import ValidationReport

DEFAULT_TEMPERATURE: float = 0.2  # Anti-alucinação (vide MAPA_PROJETO)
# Histórico:
#   4096 (original) → 8192 (1ª subida) → 16384 → 24576 (atual).
# Reuniões de 2h+ via map-reduce geram regen com 10+ topics, 10+
# decisions, 10+ actions, cada uma com evidence.quote LITERAL — passa
# fácil de 16k tokens. Subindo pra 24576: Gemini 2.5 Flash aguenta
# até 65k, Claude 3.7 Sonnet com extended thinking até 64k, GPT-4o
# 16k (vai limitar mas não trunca silenciosamente, o retry pega).
# Custo zero a mais — só pago pelo que realmente foi emitido.
DEFAULT_MAX_TOKENS: int = 24576

# Quantas vezes tentar reparsear se LLM emitir JSON inválido (truncado /
# aspas não fechadas). 2 tentativas extras = 3 calls totais no pior caso.
# Custo: ~$0.01 a mais por meeting em LLM, vale a robustez.
JSON_PARSE_RETRY: int = 2

# Instrução adicional injetada no retry — fala explicitamente pro LLM
# fechar o JSON corretamente. Mantemos o system prompt inalterado
# (preserva cache de prompt do provider).
#
# IMPORTANTE: a versão anterior limitava a "no máximo 5 tópicos/decisões/
# ações" — isso MUTILOU atas de reuniões longas (uma reunião de 2h30min
# saía com a mesma contagem de itens de uma de 17min, absurdo). O retry
# NÃO deve cortar conteúdo — deve apenas fazer descrições mais enxutas
# e garantir que o JSON está sintaticamente válido.
JSON_RETRY_INSTRUCTION: str = (
    "\n\n# IMPORTANTE - TENTATIVA ANTERIOR FALHOU\n"
    "Sua resposta anterior teve JSON INVÁLIDO (provavelmente foi cortada "
    "no meio de uma string, ou aspas/chaves não foram fechadas).\n"
    "Por favor:\n"
    "1. Seja MAIS CONCISO em descrições e summaries (1-2 frases curtas "
    "por item), MAS preserve TODOS os tópicos, decisões e action items "
    "que você havia identificado.\n"
    "2. NÃO REDUZA a quantidade de itens — só encurte cada descrição "
    "individual.\n"
    "3. Garanta que o JSON está COMPLETO: todas as strings entre aspas "
    "duplas, todos os objetos fechados com }, todos os arrays com ].\n"
    "4. Se a evidence.quote for muito longa, pode usar [...] entre "
    "trechos relevantes ao invés de copiar toda a passagem.\n"
)


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
    map_reduce_threshold_chars: int = MAP_REDUCE_THRESHOLD_CHARS,
) -> GenerationResult:
    """
    Gera ata a partir da transcrição.

    **Roteamento automático por tamanho:**
    - `len(transcript_text) <= map_reduce_threshold_chars` (default 50k):
      single-pass — uma chamada ao LLM (rota original, mais barata e
      rápida pra reuniões curtas).
    - Acima do threshold: pipeline **map-reduce** — divide em chunks,
      gera mini-ata por chunk em paralelo, depois consolida em ata
      única. Cobre reuniões de 1-3h sem estourar context window.

    Em ambos os modos, faz até `JSON_PARSE_RETRY` tentativas extras
    se o LLM emitir JSON sintaticamente inválido. Levanta
    `pydantic.ValidationError` final só se tudo falhar.
    """
    if len(transcript_text) > map_reduce_threshold_chars:
        logger.info(
            "Transcript longo — usando pipeline map-reduce",
            len_chars=len(transcript_text),
            threshold=map_reduce_threshold_chars,
        )
        mr_result = await generate_minutes_map_reduce(
            router,
            transcript_text,
            preferred=preferred,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return GenerationResult(
            minutes=mr_result.minutes,
            llm_response=mr_result.llm_response,
        )

    base_user_prompt = build_user_prompt(transcript_text)
    last_error: ValidationError | None = None

    for attempt in range(1, JSON_PARSE_RETRY + 2):  # 1 + retries
        # Em tentativas após a primeira, adiciona instrução pra fechar
        # JSON corretamente e ser mais conciso.
        user_content = base_user_prompt
        if attempt > 1:
            user_content = base_user_prompt + JSON_RETRY_INSTRUCTION

        response = await router.complete(
            messages=[
                LLMMessage(role="system", content=SYSTEM_PROMPT_MINUTES),
                LLMMessage(role="user", content=user_content),
            ],
            preferred=preferred,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        try:
            minutes = MinutesOutput.model_validate_json(response.content)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "Ata gerada com JSON invalido — vai tentar de novo",
                attempt=attempt,
                max_attempts=JSON_PARSE_RETRY + 1,
                tokens_output=response.tokens_output,
                content_preview=response.content[:200],
                error=str(exc)[:300],
            )
            continue

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
            attempts_used=attempt,
        )
        return GenerationResult(minutes=minutes, llm_response=response)

    # Esgotou tentativas — propaga o erro original pro pipeline marcar failed
    assert last_error is not None
    logger.error(
        "Ata invalida apos todas as tentativas",
        retries=JSON_PARSE_RETRY,
    )
    raise last_error


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
    base_user_prompt = (
        f"{build_user_prompt(transcript_text)}\n\n"
        "# CORREÇÕES NECESSÁRIAS DA TENTATIVA ANTERIOR\n\n"
        f"{report.to_prompt_corrections()}"
    )

    last_error: ValidationError | None = None
    for attempt in range(1, JSON_PARSE_RETRY + 2):
        user_content = base_user_prompt
        if attempt > 1:
            user_content = base_user_prompt + JSON_RETRY_INSTRUCTION

        response = await router.complete(
            messages=[
                LLMMessage(role="system", content=SYSTEM_PROMPT_MINUTES),
                LLMMessage(role="user", content=user_content),
            ],
            preferred=preferred,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            minutes = MinutesOutput.model_validate_json(response.content)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "Regen com JSON invalido — vai tentar de novo",
                attempt=attempt,
                max_attempts=JSON_PARSE_RETRY + 1,
                error=str(exc)[:300],
            )
            continue

        logger.info(
            "Ata regenerada com correções",
            provider=response.provider,
            problems_in_prior=len(report.problems),
            attempts_used=attempt,
        )
        return GenerationResult(minutes=minutes, llm_response=response)

    assert last_error is not None
    raise last_error
