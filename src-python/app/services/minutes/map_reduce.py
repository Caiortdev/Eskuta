"""
Map-Reduce hierárquico pra geração de ata em reuniões longas (Fase 1.13).

Problema que resolve: reunião de 1h+ gera transcript de 50-200k chars. Em
single-pass:
- O input estoura o context window de modelos mais antigos (Claude 3 / GPT-4)
- O output ultrapassa `max_tokens` (LLM trunca no meio do JSON)
- LLM tende a "espremer" detalhes e perder fatos relevantes

Estratégia map-reduce:
1. **Map (paralelo)**: divide o transcript em macro-chunks de ~10-15min,
   gera uma "mini-ata" pra cada trecho (mesmas categorias: topics,
   decisions, action_items, open_questions). O title/summary de cada
   mini-ata fica como placeholder "Parte N/M".
2. **Reduce**: passa as N mini-atas pro LLM e pede pra consolidar em UMA
   ata final coesa — mesclando tópicos duplicados, agregando decisões e
   action items, escrevendo executive_summary que cobre a reunião toda.

Custo: ~$0.03-0.10 por reunião 3h com Gemini Flash (vs $0.005 single-pass
em reunião curta). Tempo wall-clock: ~30-40s porque map roda em paralelo.

Por que NÃO reusar os AudioChunks da transcrição: eles foram dimensionados
pra latência de STT (~10min cada), o que é grosseiro demais pra um LLM
(50k chars seria ~12k tokens). Map-chunks são finos o suficiente pra LLM
respirar (~20k chars / ~5k tokens cada).
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pydantic import ValidationError

from app.services.llm.base import (
    LLMMessage,
    LLMRateLimitError,
    LLMResponse,
)
from app.services.llm.router import LLMRouter
from app.services.minutes.prompts import SYSTEM_PROMPT_MINUTES
from app.services.minutes.schemas import (
    ActionItem,
    Decision,
    Evidence,
    MinutesOutput,
    Topic,
)

# ============================================================
# Configuração
# ============================================================

# Tamanho-alvo de cada map-chunk em CHARS. ~20k chars ~ 5k tokens (PT-BR
# aproximadamente 4 chars/token). Cabe folgado no input de qualquer LLM
# moderno + deixa espaço pro prompt + output da mini-ata.
DEFAULT_MAP_CHUNK_CHARS: int = 20_000

# Limite acima do qual entramos em modo map-reduce. Abaixo disso, o
# generator default consegue dar conta em single-pass.
MAP_REDUCE_THRESHOLD_CHARS: int = 50_000

# Heurística PT-BR: 1 token ≈ 4 chars (aproximação grosseira mas
# robusta entre tokenizers BPE).
APPROX_CHARS_PER_TOKEN: int = 4

# Quantas calls de LLM em paralelo (limite do map phase). FREE TIER do
# Gemini permite apenas 5 req/min — com latência típica de ~30s/call,
# concorrência=2 dá ~4 req/min, conservadoramente abaixo do limite.
# Concorrência=4 batia 429 consistentemente (todos os chunks paralelos
# disparavam ao mesmo tempo, consumindo a quota inteira de uma vez).
#
# Plano pago do Gemini suporta 1000+ req/min — usuário pode subir via
# `generate_minutes_map_reduce(max_concurrency=4)` ou via env.
DEFAULT_MAP_CONCURRENCY: int = 2

# Quantas tentativas extras se um chunk de LLM retornar 429 (rate limit).
# Subido de 3 → 5 pra cobrir cenários onde múltiplos chunks consomem
# quota e o reset do minuto demora. Cada retry espera `retry_after_sec`
# do provider (~6s default no Gemini) ou nosso default abaixo.
RATE_LIMIT_MAX_RETRIES: int = 5
# Default quando provider não informa retry_after — 13s cobre 1 ciclo
# completo de minuto do Gemini com margem.
RATE_LIMIT_DEFAULT_WAIT_SEC: float = 13.0


@dataclass(frozen=True)
class MapReduceResult:
    """Resultado do pipeline map-reduce — equivalente a GenerationResult."""

    minutes: MinutesOutput
    llm_response: LLMResponse  # response do reduce, mas tokens/cost SOMADOS
    map_calls: int  # quantos chunks foram processados no map
    map_chars_per_chunk: list[int]  # tamanho de cada chunk em chars


# ============================================================
# Prompts específicos pro map-reduce
# ============================================================

_MAP_USER_PROMPT_TEMPLATE = """\
# TRANSCRIÇÃO (TRECHO {chunk_idx}/{total_chunks} DA REUNIÃO)

ATENÇÃO: este é APENAS UM TRECHO de uma reunião maior. Você está na
fase MAP de um pipeline map-reduce — extraia tópicos, decisões e
action items DESTE TRECHO. O título e o executive_summary serão
CONSOLIDADOS depois com os outros trechos, então:

- `title`: coloque "Parte {chunk_idx}/{total_chunks}" como placeholder.
- `executive_summary`: 1-2 frases curtas do que rolou NESTE trecho.
- `participants`: apenas nomes mencionados NESTE trecho.

Pra `topics`, `decisions`, `action_items`, `open_questions` siga as
regras normais do system prompt (cada um com `evidence.quote` LITERAL
da transcrição abaixo).

# TRECHO {chunk_idx}/{total_chunks}

{chunk_text}

# TAREFA

Gere uma ata parcial em JSON válido seguindo o schema documentado no
system prompt. Responda APENAS com JSON — sem texto antes ou depois,
sem markdown fences.
"""


_REDUCE_USER_PROMPT_TEMPLATE = """\
# CONTEXTO

Você recebeu {n_parts} ATAS PARCIAIS de uma única reunião que foi
processada em pedaços (pipeline map-reduce). Sua tarefa: CONSOLIDAR
essas atas parciais em UMA ata final coerente — SEM perder informação
e SEM inventar nada novo.

# PRINCÍPIOS (siga exatamente nesta ordem de prioridade)

## 1. NÃO INVENTAR
Cada `topic`, `decision`, `action_item`, `open_question` e
`participant` da ata final DEVE ter origem em UMA das atas parciais
recebidas. NUNCA crie itens que não estão lá. Se um campo (ex:
`evidence.quote`) está nas parciais, copie LITERALMENTE.

## 2. PRESERVAR > MESCLAR
Quando você ler duas entradas e perguntar "isso é a mesma coisa?", se
a resposta NÃO for um sim óbvio e literal, MANTENHA as duas separadas.
Preferimos uma ata com 12 tópicos (alguns parecidos) do que 4 tópicos
"limpos" mas com informação perdida.

## 3. MESCLAR APENAS quando for evidente
Mescle DOIS itens APENAS se forem ESSENCIALMENTE a mesma coisa:
- ✓ "Decisão X" aparece em 3 partes com paráfrases — mescla em UM com
  evidence agregada.
- ✗ "Segurança pública" + "Reforma fiscal" são tópicos DIFERENTES,
  mesmo que sequenciais.
- ✗ "Atraso do Projeto Alpha" + "Risco do Projeto Alpha" — mesmo
  projeto MAS aspectos distintos. Mantenha SEPARADOS.

# HINTS DE POSSÍVEIS DUPLICATAS

A análise determinística identificou os seguintes pares de itens com
texto MUITO SIMILAR (>90% similaridade) — provavelmente são duplicatas
reais. Use isso como guia, mas confirme caso a caso:

{duplicate_hints}

Itens que NÃO aparecem nessa lista de hints NÃO são duplicatas e
DEVEM ser preservados na ata final (a menos que você identifique uma
duplicata que escapou).

# OUTROS CAMPOS

- **Participants**: união dos nomes mencionados em qualquer parte.
- **Executive summary**: 3-6 frases cobrindo a reunião INTEIRA
  (não copie de uma das partes — sintetize).
- **Title**: título único representativo da reunião toda (NÃO use
  placeholders "Parte N/M" das partes).
- **Evidência**: copie a `evidence.quote` LITERAL como veio na ata
  parcial. Se mesclar duplicatas, escolha a quote mais clara ou
  junte trechos com "[...]" entre eles.

# ATAS PARCIAIS RECEBIDAS ({n_parts} no total)

```json
{parts_json}
```

# TAREFA

Gere a ata final consolidada em JSON válido seguindo o schema do
system prompt. Responda APENAS com JSON — sem texto antes ou depois,
sem markdown fences. Lembre-se da ordem: NÃO INVENTAR → PRESERVAR →
mesclar só o óbvio.
"""


# Prompt extra injetado quando a 1ª tentativa de reduce mutila/infla
# muito conteúdo. Reforça a categoria problemática.
_REDUCE_CORRECTION_INSTRUCTION_TEMPLATE = """\

# CORREÇÃO NECESSÁRIA — TENTATIVA ANTERIOR PROBLEMÁTICA

Sua tentativa anterior teve um problema de PRESERVAÇÃO:

{diagnostics}

Por favor refaça respeitando ESTRITAMENTE:
- Se você espremeu demais (perdeu itens): MANTENHA todos os itens
  das mini-atas, exceto duplicatas ÓBVIAS (mesma descrição literal).
- Se você inflou demais (mais itens que as mini-atas): NÃO INVENTE
  itens — só pode incluir o que está nas mini-atas recebidas.
"""


# ============================================================
# Split do transcript em macro-chunks
# ============================================================


# Pontuação que provavelmente termina uma sentença. Inclui pontos
# múltiplos pra cobrir abreviações (ex: "Sr.") e PT-BR.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])")


def split_transcript_for_map(
    transcript_text: str,
    max_chunk_chars: int = DEFAULT_MAP_CHUNK_CHARS,
) -> list[str]:
    """
    Divide o transcript em chunks de no máximo `max_chunk_chars` chars,
    quebrando preferencialmente em fim de sentença pra não cortar palavras
    no meio.

    Função pura — testável sem LLM. Heurística:
    1. Split por boundaries de sentenças (regex acima)
    2. Greedy: acumula sentenças até passar do limite
    3. Se uma única sentença ultrapassa o limite (raro mas possível em
       transcrições sem pontuação), faz hard-split por chars com
       preferência por espaço em branco

    Garantia: cada chunk tem `<= max_chunk_chars` chars (com pequena
    margem se hard-split for necessário pra não cortar muito agressivo).
    """
    text = transcript_text.strip()
    if not text:
        return []
    if len(text) <= max_chunk_chars:
        return [text]

    sentences = _SENTENCE_END_RE.split(text)
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Sentença gigante (sem pontuação) — hard split
        if len(sentence) > max_chunk_chars:
            if buffer:
                chunks.append(" ".join(buffer))
                buffer, buffer_len = [], 0
            chunks.extend(_hard_split(sentence, max_chunk_chars))
            continue

        # Caberia no buffer atual?
        projected = buffer_len + len(sentence) + (1 if buffer else 0)
        if projected > max_chunk_chars and buffer:
            chunks.append(" ".join(buffer))
            buffer, buffer_len = [sentence], len(sentence)
        else:
            buffer.append(sentence)
            buffer_len = projected

    if buffer:
        chunks.append(" ".join(buffer))

    return chunks


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Fallback: quebra string longa em pedaços, preferindo espaço em branco."""
    pieces: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            # Procura último espaço dentro do trecho pra não cortar palavra
            window_start = max(start, end - 200)
            last_space = text.rfind(" ", window_start, end)
            if last_space > start:
                end = last_space
        pieces.append(text[start:end].strip())
        start = end
    return [p for p in pieces if p]


# ============================================================
# Map phase: gera mini-ata por chunk
# ============================================================


async def _llm_call_with_rate_limit_retry(
    router: LLMRouter,
    *,
    messages: list[LLMMessage],
    preferred: str | None,
    temperature: float,
    max_tokens: int,
    label: str,
) -> LLMResponse:
    """
    Wrap de `router.complete` que retenta em 429 (LLMRateLimitError)
    respeitando o `retry_after_sec` do provider. Usado por ambos os
    estágios (map e reduce).
    """
    for attempt in range(1, RATE_LIMIT_MAX_RETRIES + 2):
        try:
            return await router.complete(
                messages=messages,
                preferred=preferred,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
        except LLMRateLimitError as exc:
            if attempt > RATE_LIMIT_MAX_RETRIES:
                logger.error(
                    "Rate limit persistente após retries — propagando",
                    label=label,
                    attempt=attempt,
                )
                raise
            wait = (
                exc.retry_after_sec
                if exc.retry_after_sec and exc.retry_after_sec > 0
                else RATE_LIMIT_DEFAULT_WAIT_SEC
            )
            logger.warning(
                "Rate limit hit — esperando antes de tentar de novo",
                label=label,
                attempt=attempt,
                wait_sec=round(wait, 2),
            )
            await asyncio.sleep(wait)

    # Inalcançável — o loop ou retorna ou raise
    raise RuntimeError("rate-limit retry loop saiu sem retorno nem raise")


async def _generate_partial(
    router: LLMRouter,
    chunk_text: str,
    *,
    chunk_idx: int,
    total_chunks: int,
    preferred: str | None,
    temperature: float,
    max_tokens: int,
) -> tuple[MinutesOutput, LLMResponse]:
    """
    Gera UMA mini-ata pra um chunk. Faz:
    - Retry com backoff em 429 (rate limit) via _llm_call_with_rate_limit_retry
    - Até 2 tentativas em caso de JSON inválido (mesma estratégia do generator.py)
    """
    user_prompt = _MAP_USER_PROMPT_TEMPLATE.format(
        chunk_idx=chunk_idx,
        total_chunks=total_chunks,
        chunk_text=chunk_text.strip(),
    )

    last_error: ValidationError | None = None
    for attempt in range(1, 3):  # 2 tentativas de PARSE
        response = await _llm_call_with_rate_limit_retry(
            router,
            messages=[
                LLMMessage(role="system", content=SYSTEM_PROMPT_MINUTES),
                LLMMessage(role="user", content=user_prompt),
            ],
            preferred=preferred,
            temperature=temperature,
            max_tokens=max_tokens,
            label=f"map[{chunk_idx}/{total_chunks}]",
        )
        try:
            minutes = MinutesOutput.model_validate_json(response.content)
            return minutes, response
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "Map chunk com JSON invalido — tentando de novo",
                chunk_idx=chunk_idx,
                attempt=attempt,
                error=str(exc)[:200],
            )

    assert last_error is not None
    raise last_error


# ============================================================
# Reduce phase: consolida mini-atas em ata final
# ============================================================


def _minutes_to_dict(minutes: MinutesOutput) -> dict[str, Any]:
    """
    Converte MinutesOutput em dict serializável pro reduce prompt.
    Pra reduzir tokens, omitimos placeholders óbvios e mantemos
    estrutura completa do schema.
    """
    return minutes.model_dump(mode="json", exclude_none=False)


# ============================================================
# Detector determinístico de duplicatas (rapidfuzz)
# ============================================================

# Limiar de similaridade pra considerar dois itens duplicatas. Usa
# fuzz.token_set_ratio (insensível a ordem) — 90 é estrito o suficiente
# pra evitar falsos positivos (≈ 90% das palavras em comum).
DUPLICATE_SIMILARITY_THRESHOLD: int = 90


def _find_potential_duplicates(
    partials: Sequence[MinutesOutput],
) -> dict[str, list[tuple[str, str, int]]]:
    """
    Identifica pares de items (description ou quote similares entre
    si) que provavelmente são DUPLICATAS reais. Útil pra dar hints ao
    LLM de quais consolidar — quem não está na lista NÃO é duplicata.

    Retorna dict por categoria com lista de tuplas:
        {"topics": [(text_a, text_b, similarity), ...],
         "decisions": [...],
         "action_items": [...]}

    Para reuniões grandes (>15 items), pode ficar caro O(N²). Limitamos
    a comparação entre items de partials DIFERENTES (mesmo partial
    raramente terá duplicatas internas — o map já consolida).
    """
    from rapidfuzz import fuzz

    def _scan(extract_texts) -> list[tuple[str, str, int]]:
        """`extract_texts(partial) -> list[str]` por categoria."""
        # Coleta (partial_idx, texto) — só compara items de partials diferentes
        items: list[tuple[int, str]] = []
        for i, p in enumerate(partials):
            for txt in extract_texts(p):
                if txt and txt.strip():
                    items.append((i, txt.strip()))

        pairs: list[tuple[str, str, int]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for a_idx in range(len(items)):
            pi_a, ta = items[a_idx]
            for b_idx in range(a_idx + 1, len(items)):
                pi_b, tb = items[b_idx]
                if pi_a == pi_b:
                    continue  # duplicata interna ao mesmo partial é rara — pula
                sim = int(fuzz.token_set_ratio(ta, tb))
                if sim >= DUPLICATE_SIMILARITY_THRESHOLD:
                    key = tuple(sorted([ta[:80], tb[:80]]))
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    pairs.append((ta, tb, sim))
        return pairs

    return {
        "topics": _scan(lambda p: [t.title + " — " + t.summary for t in p.topics]),
        "decisions": _scan(lambda p: [d.description for d in p.decisions]),
        "action_items": _scan(lambda p: [a.description for a in p.action_items]),
    }


def _format_duplicate_hints(
    duplicates: dict[str, list[tuple[str, str, int]]],
    *,
    max_per_category: int = 10,
    max_text_chars: int = 120,
) -> str:
    """
    Formata os pares de duplicatas detectadas pra injetar no prompt.
    Trunca texto pra não inflar tokens (LLM só precisa da pista, não
    do texto inteiro).
    """
    lines: list[str] = []
    cat_label = {
        "topics": "TÓPICOS",
        "decisions": "DECISÕES",
        "action_items": "ACTION ITEMS",
    }

    total = sum(len(v) for v in duplicates.values())
    if total == 0:
        return (
            "(NENHUMA duplicata detectada automaticamente. Considere TUDO "
            "como item distinto, a menos que você identifique alguma duplicata "
            "óbvia que escapou.)"
        )

    for cat, pairs in duplicates.items():
        if not pairs:
            continue
        lines.append(f"\n## {cat_label[cat]}")
        for a, b, sim in pairs[:max_per_category]:
            a_short = (a[:max_text_chars] + "...") if len(a) > max_text_chars else a
            b_short = (b[:max_text_chars] + "...") if len(b) > max_text_chars else b
            lines.append(f"- [{sim}% similaridade]")
            lines.append(f"  A: {a_short}")
            lines.append(f"  B: {b_short}")
        if len(pairs) > max_per_category:
            lines.append(f"  ... e mais {len(pairs) - max_per_category} pares na categoria.")

    return "\n".join(lines)


def _build_reduce_user_prompt(
    partials: Sequence[MinutesOutput],
    *,
    correction_diagnostics: str | None = None,
) -> str:
    """
    Monta o user prompt do reduce com:
    - JSON das N mini-atas
    - HINTS determinísticos de duplicatas detectadas (rapidfuzz)
    - (Opcional) instrução de correção quando estamos numa auto-regen

    A abordagem é adaptativa por CONTEÚDO, não por números fixos:
    o LLM decide a quantidade baseada no que realmente está nas mini-atas.
    """
    parts_payload = [_minutes_to_dict(p) for p in partials]
    parts_json = json.dumps(parts_payload, ensure_ascii=False, indent=2)

    duplicates = _find_potential_duplicates(partials)
    duplicate_hints = _format_duplicate_hints(duplicates)

    prompt = _REDUCE_USER_PROMPT_TEMPLATE.format(
        n_parts=len(partials),
        parts_json=parts_json,
        duplicate_hints=duplicate_hints,
    )

    if correction_diagnostics:
        prompt += _REDUCE_CORRECTION_INSTRUCTION_TEMPLATE.format(
            diagnostics=correction_diagnostics,
        )

    return prompt


# ============================================================
# Validação adaptativa do output do reduce (anti-mutilação + anti-alucinação)
# ============================================================

# Mínimo de preservação aceitável (final / sum_partials) em cada
# categoria. Abaixo disso: regen com prompt corretivo (mutilação).
PRESERVATION_MIN_RATIO: float = 0.5

# Máximo de "preservation" aceitável. Acima disso significa que o LLM
# INVENTOU items que não estavam nas mini-atas (alucinação).
PRESERVATION_MAX_RATIO: float = 1.5

# Quantas auto-regens do reduce. Depois disso, cai pro fallback
# determinístico que NUNCA inventa.
REDUCE_AUTO_REGEN_MAX: int = 2


@dataclass(frozen=True)
class _PreservationReport:
    """Diagnóstico de preservação do reduce vs sum das mini-atas."""

    topics_ratio: float
    decisions_ratio: float
    actions_ratio: float
    map_topics: int
    map_decisions: int
    map_actions: int
    final_topics: int
    final_decisions: int
    final_actions: int

    @property
    def has_mutilation(self) -> bool:
        """Alguma categoria abaixo do limiar minimo de preservação."""
        return any(
            r < PRESERVATION_MIN_RATIO and total > 0
            for r, total in (
                (self.topics_ratio, self.map_topics),
                (self.decisions_ratio, self.map_decisions),
                (self.actions_ratio, self.map_actions),
            )
        )

    @property
    def has_hallucination(self) -> bool:
        """Alguma categoria acima do limiar máximo (inventou items)."""
        return any(
            r > PRESERVATION_MAX_RATIO and total > 0
            for r, total in (
                (self.topics_ratio, self.map_topics),
                (self.decisions_ratio, self.map_decisions),
                (self.actions_ratio, self.map_actions),
            )
        )

    @property
    def is_ok(self) -> bool:
        return not self.has_mutilation and not self.has_hallucination

    def to_diagnostics(self) -> str:
        """Texto pra injetar no prompt de correção."""
        lines: list[str] = []
        for label, ratio, mapn, finaln in (
            ("Tópicos", self.topics_ratio, self.map_topics, self.final_topics),
            ("Decisões", self.decisions_ratio, self.map_decisions, self.final_decisions),
            ("Action items", self.actions_ratio, self.map_actions, self.final_actions),
        ):
            if mapn == 0:
                continue
            if ratio < PRESERVATION_MIN_RATIO:
                lines.append(
                    f"- {label}: as mini-atas tinham {mapn} no total, "
                    f"mas você gerou apenas {finaln} ({int(ratio * 100)}%). "
                    f"VOCÊ ESPREMEU DEMAIS — preserve mais itens."
                )
            elif ratio > PRESERVATION_MAX_RATIO:
                lines.append(
                    f"- {label}: as mini-atas tinham {mapn} no total, "
                    f"mas você gerou {finaln} ({int(ratio * 100)}%). "
                    f"VOCÊ INVENTOU items — só pode incluir o que está "
                    f"nas mini-atas recebidas."
                )
        return "\n".join(lines) if lines else "(sem problemas detectados)"


def _compute_preservation(
    partials: Sequence[MinutesOutput],
    final: MinutesOutput,
) -> _PreservationReport:
    """Calcula ratios de preservação por categoria."""
    sum_topics = sum(len(p.topics) for p in partials)
    sum_decisions = sum(len(p.decisions) for p in partials)
    sum_actions = sum(len(p.action_items) for p in partials)

    final_topics = len(final.topics)
    final_decisions = len(final.decisions)
    final_actions = len(final.action_items)

    def _r(final_n: int, total_n: int) -> float:
        if total_n == 0:
            return 1.0 if final_n == 0 else float("inf")
        return final_n / total_n

    return _PreservationReport(
        topics_ratio=_r(final_topics, sum_topics),
        decisions_ratio=_r(final_decisions, sum_decisions),
        actions_ratio=_r(final_actions, sum_actions),
        map_topics=sum_topics,
        map_decisions=sum_decisions,
        map_actions=sum_actions,
        final_topics=final_topics,
        final_decisions=final_decisions,
        final_actions=final_actions,
    )


async def _reduce_partials(
    router: LLMRouter,
    partials: Sequence[MinutesOutput],
    *,
    preferred: str | None,
    temperature: float,
    max_tokens: int,
    correction_diagnostics: str | None = None,
    label_suffix: str = "",
) -> tuple[MinutesOutput, LLMResponse]:
    """
    Consolida N mini-atas em UMA ata final. Tenta até 2 vezes se
    devolver JSON inválido. Levanta `pydantic.ValidationError` na
    falha final.

    Se `correction_diagnostics` é fornecido, injeta instrução de
    correção (usado em auto-regen de preservação).
    """
    user_prompt = _build_reduce_user_prompt(
        partials,
        correction_diagnostics=correction_diagnostics,
    )

    last_error: ValidationError | None = None
    for attempt in range(1, 3):
        response = await _llm_call_with_rate_limit_retry(
            router,
            messages=[
                LLMMessage(role="system", content=SYSTEM_PROMPT_MINUTES),
                LLMMessage(role="user", content=user_prompt),
            ],
            preferred=preferred,
            temperature=temperature,
            max_tokens=max_tokens,
            label=f"reduce{label_suffix}",
        )
        try:
            minutes = MinutesOutput.model_validate_json(response.content)
            return minutes, response
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "Reduce com JSON invalido — tentando de novo",
                attempt=attempt,
                label_suffix=label_suffix,
                error=str(exc)[:200],
            )

    assert last_error is not None
    raise last_error


# ============================================================
# Fallback determinístico: usa SÓ a 1ª mini-ata se reduce falhar
# ============================================================


def _deterministic_merge(partials: Sequence[MinutesOutput]) -> MinutesOutput:
    """
    Plano B se o reduce LLM falhar várias vezes: faz a consolidação
    via código puro. Menos elegante (executive_summary fica como
    concatenação literal), mas garante que a reunião não vire `failed`
    por causa do reduce.

    NUNCA inventa dados — só pega o que já está nas mini-atas.
    """
    all_topics: list[Topic] = []
    all_decisions: list[Decision] = []
    all_actions: list[ActionItem] = []
    all_questions: list[str] = []
    all_participants: set[str] = set()
    summaries: list[str] = []

    for p in partials:
        all_topics.extend(p.topics)
        all_decisions.extend(p.decisions)
        all_actions.extend(p.action_items)
        all_questions.extend(p.open_questions)
        all_participants.update(p.participants)
        if p.executive_summary and p.executive_summary.strip():
            summaries.append(p.executive_summary.strip())

    # Mantém Evidence/Topic/Decision/ActionItem intactos — só re-empacota
    return MinutesOutput(
        title="Reunião — consolidação automática",
        date=next((p.date for p in partials if p.date), None),
        participants=sorted(all_participants),
        executive_summary=(
            " ".join(summaries)[:2000]  # limita pra não explodir
            if summaries
            else "Resumo executivo indisponível — consolidação manual."
        ),
        topics=all_topics,
        decisions=all_decisions,
        action_items=all_actions,
        open_questions=all_questions,
    )


# ============================================================
# Orquestrador principal
# ============================================================


def _sum_llm_responses(responses: Sequence[LLMResponse], primary: LLMResponse) -> LLMResponse:
    """
    Cria um LLMResponse consolidado (pro persister salvar): mantém
    provider/model/content do REDUCE (que tem a ata final), mas soma
    tokens/cost de TODAS as calls (map + reduce).
    """
    total_input = sum(r.tokens_input for r in responses) + primary.tokens_input
    total_output = sum(r.tokens_output for r in responses) + primary.tokens_output
    total_cost = sum(r.cost_usd for r in responses) + primary.cost_usd
    return LLMResponse(
        content=primary.content,
        provider=primary.provider,
        model=primary.model,
        tokens_input=total_input,
        tokens_output=total_output,
        cost_usd=total_cost,
    )


async def generate_minutes_map_reduce(
    router: LLMRouter,
    transcript_text: str,
    *,
    preferred: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 16384,
    max_chunk_chars: int = DEFAULT_MAP_CHUNK_CHARS,
    max_concurrency: int = DEFAULT_MAP_CONCURRENCY,
) -> MapReduceResult:
    """
    Pipeline map-reduce completo. Use quando `len(transcript_text)` for
    maior que `MAP_REDUCE_THRESHOLD_CHARS` — pra textos curtos o
    generator default em single-pass é mais barato e mais rápido.

    Estratégia:
    1. Split: divide o transcript em N chunks de até `max_chunk_chars`.
    2. Map paralelo: gera mini-ata por chunk via `asyncio.gather`.
       Falha em 1 chunk individual NÃO mata o pipeline (esse chunk é
       pulado com warning, o reduce trabalha com os que sobreviveram).
    3. Reduce: consolida N mini-atas em UMA ata final.
    4. Se reduce falhar 2x → fallback determinístico que concatena.

    Levanta `pydantic.ValidationError` se:
    - Todos os chunks do map falharem (raro)
    - Fallback determinístico falhar (praticamente impossível)
    """
    chunks = split_transcript_for_map(transcript_text, max_chunk_chars=max_chunk_chars)
    if not chunks:
        raise ValueError("transcript_text vazio — nada pra gerar")
    if len(chunks) == 1:
        # Não vale a pena map-reduce — chamador devia ter usado single-pass.
        # Fazemos só pra robustez, gerando 1 mini-ata e devolvendo direto.
        logger.info("map_reduce com 1 chunk — comportamento degenerado, considerar single-pass")

    logger.info(
        "Iniciando map-reduce de ata",
        n_chunks=len(chunks),
        total_chars=len(transcript_text),
        avg_chunk_chars=sum(len(c) for c in chunks) // max(1, len(chunks)),
        max_concurrency=max_concurrency,
    )

    # ─── MAP em paralelo com limite de concorrência ─────────────
    # Semaphore evita que dispare >max_concurrency calls simultâneas no
    # provider — protege do rate limit do free tier (Gemini = 5 req/min).
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _bounded_partial(idx: int, chunk: str):
        async with semaphore:
            return await _generate_partial(
                router,
                chunk,
                chunk_idx=idx + 1,
                total_chunks=len(chunks),
                preferred=preferred,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    map_results: list[tuple[MinutesOutput, LLMResponse] | BaseException] = await asyncio.gather(
        *[_bounded_partial(i, chunk) for i, chunk in enumerate(chunks)],
        return_exceptions=True,
    )

    partials: list[MinutesOutput] = []
    map_responses: list[LLMResponse] = []
    for i, res in enumerate(map_results):
        if isinstance(res, BaseException):
            logger.warning(
                "Map chunk falhou — pulando",
                chunk_idx=i + 1,
                error=str(res)[:200],
            )
            continue
        minutes, llm_resp = res
        partials.append(minutes)
        map_responses.append(llm_resp)

    if not partials:
        raise ValueError("Todos os map chunks falharam — impossível gerar ata via map-reduce")

    logger.info(
        "Map phase concluida",
        chunks_total=len(chunks),
        chunks_ok=len(partials),
        chunks_failed=len(chunks) - len(partials),
    )

    # ─── REDUCE com auto-regen de preservation ─────────────────────
    # Loop: chama o reduce, mede preservation, se ruim regenera com
    # diagnóstico. Cap em REDUCE_AUTO_REGEN_MAX tentativas. Se nenhuma
    # convergir OU se o LLM falhar parsing 2x, cai pro fallback
    # determinístico que NUNCA inventa.
    all_reduce_responses: list[LLMResponse] = []
    final_minutes: MinutesOutput | None = None
    last_preservation: _PreservationReport | None = None
    last_diagnostics: str | None = None

    for regen_attempt in range(1, REDUCE_AUTO_REGEN_MAX + 2):
        try:
            candidate, reduce_response_i = await _reduce_partials(
                router,
                partials,
                preferred=preferred,
                temperature=temperature,
                max_tokens=max_tokens,
                correction_diagnostics=last_diagnostics,
                label_suffix=f"-r{regen_attempt}" if regen_attempt > 1 else "",
            )
        except ValidationError as exc:
            # Plano B determinístico — não inventa dados, só concatena
            logger.error(
                "Reduce LLM falhou no parsing — usando fallback deterministico",
                attempt=regen_attempt,
                error=str(exc)[:200],
            )
            break

        all_reduce_responses.append(reduce_response_i)
        preservation = _compute_preservation(partials, candidate)
        last_preservation = preservation

        if preservation.is_ok:
            logger.info(
                "Reduce com preservacao OK",
                attempt=regen_attempt,
                topics_ratio=round(preservation.topics_ratio, 2),
                decisions_ratio=round(preservation.decisions_ratio, 2),
                actions_ratio=round(preservation.actions_ratio, 2),
            )
            final_minutes = candidate
            break

        # Não OK — log e prepara correção
        problem = "mutilacao" if preservation.has_mutilation else "alucinacao"
        if regen_attempt > REDUCE_AUTO_REGEN_MAX:
            logger.warning(
                "Reduce esgotou auto-regens com preservacao ruim — usando fallback",
                problem=problem,
                topics_ratio=round(preservation.topics_ratio, 2),
                decisions_ratio=round(preservation.decisions_ratio, 2),
                actions_ratio=round(preservation.actions_ratio, 2),
            )
            # Se a alucinação foi o problema, usa o fallback que só
            # preserva o que está nas partials. Se foi mutilação, idem
            # (o fallback agrega tudo, então cobre mais).
            break

        last_diagnostics = preservation.to_diagnostics()
        logger.warning(
            "Reduce com preservacao ruim — regerando com correcao",
            problem=problem,
            attempt=regen_attempt,
            topics_ratio=round(preservation.topics_ratio, 2),
            decisions_ratio=round(preservation.decisions_ratio, 2),
            actions_ratio=round(preservation.actions_ratio, 2),
        )

    # Se nenhuma das tentativas LLM passou → fallback determinístico
    if final_minutes is None:
        final_minutes = _deterministic_merge(partials)
        reduce_response = LLMResponse(
            content="",  # fallback não tem content de LLM
            provider=(all_reduce_responses[-1].provider if all_reduce_responses else "fallback"),
            model=(all_reduce_responses[-1].model if all_reduce_responses else "deterministic"),
            tokens_input=0,
            tokens_output=0,
            cost_usd=0.0,
        )
    else:
        reduce_response = all_reduce_responses[-1]

    # Soma cost de TODAS as reduce attempts + maps
    consolidated = _sum_llm_responses(map_responses + all_reduce_responses[:-1], reduce_response)

    # Log final: já temos `last_preservation` da última tentativa (ou
    # None se caiu pro fallback determinístico antes de medir).
    final_preservation = last_preservation or _compute_preservation(partials, final_minutes)

    logger.info(
        "Reduce phase concluida",
        provider=consolidated.provider,
        model=consolidated.model,
        regen_attempts=len(all_reduce_responses),
        total_tokens_input=consolidated.tokens_input,
        total_tokens_output=consolidated.tokens_output,
        total_cost_usd=round(consolidated.cost_usd, 6),
        topics=final_preservation.final_topics,
        decisions=final_preservation.final_decisions,
        actions=final_preservation.final_actions,
        map_topics_total=final_preservation.map_topics,
        map_decisions_total=final_preservation.map_decisions,
        map_actions_total=final_preservation.map_actions,
        preservation_topics=round(final_preservation.topics_ratio, 2),
        preservation_decisions=round(final_preservation.decisions_ratio, 2),
        preservation_actions=round(final_preservation.actions_ratio, 2),
        used_fallback=(reduce_response.content == ""),
    )

    return MapReduceResult(
        minutes=final_minutes,
        llm_response=consolidated,
        map_calls=len(partials),
        map_chars_per_chunk=[len(c) for c in chunks],
    )


# Re-export pra simplificar import do __init__
__all__ = [
    "DEFAULT_MAP_CHUNK_CHARS",
    "MAP_REDUCE_THRESHOLD_CHARS",
    "MapReduceResult",
    "generate_minutes_map_reduce",
    "split_transcript_for_map",
]


# Side-effect import (testes mockam isso, garantia de api visível)
_ = (Evidence,)
