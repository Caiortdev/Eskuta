"""
Camada de geração de ata estruturada (anti-alucinação).

Arquitetura (RELATORIO_TECNICO §1.7):
- `schemas` define os tipos Pydantic que o LLM DEVE retornar (JSON Schema rigoroso).
- `validator` confere se cada `evidence.quote` está REALMENTE na transcrição original
  (fuzzy match), retornando um relatório estruturado que pode virar prompt corretivo
  pra regen.

Os 6 princípios anti-alucinação do MAPA_PROJETO são aplicados em camadas:
1. Temperature baixa            → `LLMRouter.complete(temperature=0.2)` na chamada
2. Citação obrigatória         → schemas exigem `evidence` em todo item afirmativo
3. Output estruturado          → `MinutesOutput` Pydantic + JSON mode (Fase 1.6)
4. Validação cruzada           → `validate_minutes` retorna relatório acionável
5. Few-shot com exemplos       → System prompt (Fase 1.8)
6. Chain-of-thought explícito  → System prompt (Fase 1.8)
"""

from app.services.minutes.schemas import (
    ActionItem,
    Decision,
    Evidence,
    MinutesOutput,
    Topic,
)
from app.services.minutes.validator import (
    DEFAULT_FUZZY_THRESHOLD,
    EvidenceProblem,
    ValidationReport,
    validate_evidence,
    validate_minutes,
)

__all__ = [
    "DEFAULT_FUZZY_THRESHOLD",
    "ActionItem",
    "Decision",
    "Evidence",
    "EvidenceProblem",
    "MinutesOutput",
    "Topic",
    "ValidationReport",
    "validate_evidence",
    "validate_minutes",
]
