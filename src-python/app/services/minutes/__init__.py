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

from app.services.minutes.generator import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    GenerationResult,
    generate_minutes,
    regenerate_with_correction,
)
from app.services.minutes.persister import save_minutes, save_transcript
from app.services.minutes.pipeline import (
    DEFAULT_MAX_REGEN_ATTEMPTS,
    MEETING_STATUS_VALUES,
    process_meeting,
)
from app.services.minutes.prompts import (
    FEW_SHOT_EXAMPLE_MINUTES,
    FEW_SHOT_EXAMPLE_TRANSCRIPT,
    SYSTEM_PROMPT_MINUTES,
    VALIDATION_PROMPT,
    build_user_prompt,
    build_validation_user_prompt,
)
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
    "DEFAULT_MAX_REGEN_ATTEMPTS",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TEMPERATURE",
    "FEW_SHOT_EXAMPLE_MINUTES",
    "FEW_SHOT_EXAMPLE_TRANSCRIPT",
    "MEETING_STATUS_VALUES",
    "SYSTEM_PROMPT_MINUTES",
    "VALIDATION_PROMPT",
    "ActionItem",
    "Decision",
    "Evidence",
    "EvidenceProblem",
    "GenerationResult",
    "MinutesOutput",
    "Topic",
    "ValidationReport",
    "build_user_prompt",
    "build_validation_user_prompt",
    "generate_minutes",
    "process_meeting",
    "regenerate_with_correction",
    "save_minutes",
    "save_transcript",
    "validate_evidence",
    "validate_minutes",
]
