"""
Validador de evidências da ata gerada pelo LLM.

Garante que toda `Evidence.quote` está REALMENTE no transcript original
(RELATORIO_TECNICO §1.7.3). Usa `rapidfuzz.fuzz.partial_ratio` —
o LLM pode normalizar pontuação, espaços ou capitalização sem que
isso conte como invenção; só quotes COMPLETAMENTE diferentes do
transcript são flagadas.

A função `validate_minutes` retorna um `ValidationReport` estruturado
(não só lista de strings como no relatório) — facilita o pipeline da
Fase 1.9 montar prompt corretivo de regen apontando exatamente quais
campos falharam.

Evolução do relatório: também validamos `topics[*].evidence`, não só
`action_items` e `decisions` — o princípio "toda afirmação cita" se
aplica a topics também (RELATORIO_TECNICO §1.7.1, item 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger
from rapidfuzz import fuzz

from app.services.minutes.schemas import MinutesOutput

# Threshold default do match fuzzy (0-100). 85 é o equilíbrio
# recomendado no relatório — alto o suficiente pra pegar normalização
# benigna (pontuação, espaços, caixa), baixo o suficiente pra evitar
# falsos positivos de "quase invenção".
DEFAULT_FUZZY_THRESHOLD: int = 85


@dataclass(frozen=True)
class EvidenceProblem:
    """Uma evidência inválida detectada na ata."""

    field_path: str  # ex: "action_items[0].evidence", "topics[2].evidence"
    item_description: str  # texto curto do item dono (description / title)
    quote: str  # a quote que falhou — útil pro prompt corretivo


@dataclass(frozen=True)
class ValidationReport:
    """Resultado da validação cruzada da ata contra a transcrição."""

    problems: list[EvidenceProblem] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.problems

    def to_prompt_corrections(self) -> str:
        """Texto formatado pra injetar num prompt de regen."""
        if self.is_valid:
            return ""
        lines = ["Os seguintes itens têm citação que NÃO existe na transcrição:"]
        for p in self.problems:
            lines.append(f'- {p.field_path} ({p.item_description!r}): "{p.quote}"')
        lines.append(
            "Reescreva a ata removendo esses itens OU substituindo por "
            "citações reais da transcrição. Se não houver evidência, "
            "remova o item — não invente."
        )
        return "\n".join(lines)


def _normalize(text: str) -> str:
    """Lower + collapse whitespace pra match resiliente a formatação."""
    return " ".join(text.lower().split())


def validate_evidence(
    quote: str,
    transcript_text: str,
    *,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> bool:
    """
    True se `quote` aparece (literalmente OU via fuzzy match) em
    `transcript_text`.

    - Quote vazio → False (proteção contra LLM "esquecer" o campo).
    - Match exato (após normalização) → True imediato (rápido).
    - Senão, `partial_ratio` (rapidfuzz) procura a melhor janela —
      score 0-100; >= threshold → True.
    """
    if not quote or not quote.strip():
        return False
    quote_n = _normalize(quote)
    transcript_n = _normalize(transcript_text)
    if quote_n in transcript_n:
        return True
    score = fuzz.partial_ratio(quote_n, transcript_n)
    return int(score) >= threshold


def validate_minutes(
    minutes: MinutesOutput,
    transcript_text: str,
    *,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> ValidationReport:
    """
    Valida TODAS as evidências da ata contra a transcrição.

    Verifica `topics`, `decisions` e `action_items` (todos têm
    `evidence` obrigatório no schema). Cada falha vira um
    `EvidenceProblem` com path estruturado pra regen.
    """
    problems: list[EvidenceProblem] = []

    for i, topic in enumerate(minutes.topics):
        if not validate_evidence(topic.evidence.quote, transcript_text, threshold=threshold):
            problems.append(
                EvidenceProblem(
                    field_path=f"topics[{i}].evidence",
                    item_description=topic.title,
                    quote=topic.evidence.quote,
                )
            )

    for i, decision in enumerate(minutes.decisions):
        if not validate_evidence(decision.evidence.quote, transcript_text, threshold=threshold):
            problems.append(
                EvidenceProblem(
                    field_path=f"decisions[{i}].evidence",
                    item_description=decision.description,
                    quote=decision.evidence.quote,
                )
            )

    for i, action in enumerate(minutes.action_items):
        if not validate_evidence(action.evidence.quote, transcript_text, threshold=threshold):
            problems.append(
                EvidenceProblem(
                    field_path=f"action_items[{i}].evidence",
                    item_description=action.description,
                    quote=action.evidence.quote,
                )
            )

    report = ValidationReport(problems=problems)
    if not report.is_valid:
        logger.warning(
            "Validação de evidências encontrou problemas",
            problem_count=len(report.problems),
            threshold=threshold,
        )
    return report


# ============================================================
# Purge determinístico — última linha de defesa contra alucinação
# ============================================================


@dataclass(frozen=True)
class PurgeReport:
    """Resumo do que foi removido por evidência inválida."""

    removed_topics: int = 0
    removed_decisions: int = 0
    removed_action_items: int = 0

    @property
    def total_removed(self) -> int:
        return self.removed_topics + self.removed_decisions + self.removed_action_items


def purge_invalid_items(
    minutes: MinutesOutput,
    transcript_text: str,
    *,
    threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> tuple[MinutesOutput, PurgeReport]:
    """
    Remove de `minutes` todos os topics/decisions/action_items cuja
    `evidence.quote` NÃO existe na transcrição (similarity < threshold).

    Última camada de defesa contra alucinação — usada DEPOIS de o LLM
    ter esgotado tentativas de regen. Garante que a ata persistida só
    contém itens que podem ser AUDITADOS contra o transcript real.

    Casos típicos pegados aqui:
    - LLM vazou itens do FEW-SHOT EXAMPLE do system prompt
      (ex: "Projeto Alpha" numa reunião que não tem isso)
    - LLM parafraseou tanto que o quote não bate mais
    - LLM inventou item baseado em "interpretação" do conteúdo

    Retorna a ata filtrada + `PurgeReport` com quantos foram removidos
    por categoria (pra log + UI mostrar alerta).
    """
    kept_topics = [
        t
        for t in minutes.topics
        if validate_evidence(t.evidence.quote, transcript_text, threshold=threshold)
    ]
    kept_decisions = [
        d
        for d in minutes.decisions
        if validate_evidence(d.evidence.quote, transcript_text, threshold=threshold)
    ]
    kept_actions = [
        a
        for a in minutes.action_items
        if validate_evidence(a.evidence.quote, transcript_text, threshold=threshold)
    ]

    report = PurgeReport(
        removed_topics=len(minutes.topics) - len(kept_topics),
        removed_decisions=len(minutes.decisions) - len(kept_decisions),
        removed_action_items=len(minutes.action_items) - len(kept_actions),
    )

    if report.total_removed > 0:
        logger.warning(
            "Purge removeu itens com evidence invalida (alucinacao detectada)",
            removed_topics=report.removed_topics,
            removed_decisions=report.removed_decisions,
            removed_action_items=report.removed_action_items,
            kept_topics=len(kept_topics),
            kept_decisions=len(kept_decisions),
            kept_actions=len(kept_actions),
        )

    # Cria ata nova preservando os demais campos
    purged = minutes.model_copy(
        update={
            "topics": kept_topics,
            "decisions": kept_decisions,
            "action_items": kept_actions,
        }
    )
    return purged, report
