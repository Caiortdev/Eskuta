"""
Schemas Pydantic que descrevem o output OBRIGATÓRIO do LLM ao gerar
ata (RELATORIO_TECNICO §1.7.2).

Princípios codificados:
- Toda afirmação (decision / action_item / topic) tem `evidence` com
  o trecho exato da transcrição. Se LLM não conseguir citar, NÃO
  deve incluir o item — esquema impede afirmação sem fonte.
- Campos opcionais são `| None = None` (LLM deve emitir `null`, NUNCA
  inventar valor — princípio reforçado no prompt na Fase 1.8).
- Listas opcionais default `[]` (vazio é resposta válida; não inventar).

A validação real acontece em runtime no pipeline da Fase 1.9:
`MinutesOutput.model_validate_json(llm_response.content)` — se LLM
emitir JSON inválido ou faltar campo, levanta `ValidationError`
e o pipeline regera (até 2x) com prompt corretivo.

Decisão de design: `model_config` permite `extra="ignore"` (default
do Pydantic v2) em vez de `forbid` — LLM às vezes adiciona campos
úteis (ex: `notes`); ignoramos sem quebrar. Campos REQUERIDOS sim
vão falhar a validação — é onde a anti-alucinação morde.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Trecho exato da transcrição que justifica uma afirmação."""

    quote: str = Field(
        min_length=1,
        description=(
            "Trecho EXATO da transcrição (copy-paste). Não parafraseie. "
            "Se não conseguir citar literalmente, NÃO inclua o item pai."
        ),
    )
    speaker: str | None = Field(
        default=None,
        description="Quem disse — nome se mencionado, senão null.",
    )
    timestamp_sec: float | None = Field(
        default=None,
        ge=0,
        description="Segundos do início no áudio original, ou null.",
    )


class Topic(BaseModel):
    """Tópico discutido na reunião."""

    title: str = Field(min_length=1)
    summary: str = Field(
        min_length=1,
        description="Resumo em até 3 frases. NUNCA invente — só descreva o que foi dito.",
    )
    evidence: Evidence


class Decision(BaseModel):
    """Algo que foi resolvido durante a reunião."""

    description: str = Field(min_length=1)
    evidence: Evidence


class ActionItem(BaseModel):
    """Algo que ALGUÉM precisa fazer DEPOIS da reunião."""

    description: str = Field(min_length=1)
    assigned_to: str | None = Field(
        default=None,
        description="Nome do responsável, ou null se não atribuído nominalmente.",
    )
    deadline: str | None = Field(
        default=None,
        description="Prazo mencionado (data ou referência temporal), ou null.",
    )
    evidence: Evidence


class MinutesOutput(BaseModel):
    """Schema raiz do output do LLM — toda ata gerada DEVE bater com isso."""

    title: str = Field(min_length=1, description="Título curto e descritivo.")
    date: str | None = Field(
        default=None,
        description="Data se mencionada na conversa, senão null.",
    )
    participants: list[str] = Field(
        default_factory=list,
        description="Apenas nomes EXPLICITAMENTE mencionados.",
    )
    executive_summary: str = Field(
        min_length=1,
        description="2-4 frases sintetizando o essencial da reunião.",
    )
    topics: list[Topic] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    open_questions: list[str] = Field(
        default_factory=list,
        description="Pontos discutidos mas não resolvidos.",
    )
