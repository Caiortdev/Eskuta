"""
Persistência dos resultados do pipeline em DB (parte da Fase 1.9).

Funções:
- `save_transcript`: cria 1 row `transcripts` + N rows `transcript_segments`
  a partir de um `TranscriptionResult` (Fase 1.4).
- `save_minutes`: cria 1 row `minutes` + N rows `decisions`/`action_items`
  + M rows `evidences` a partir de um `MinutesOutput` (Fase 1.7) +
  `LLMResponse` (metadata) + `ValidationReport` (auditoria).

Sobre o link bidirecional Evidence ↔ parent:
- Tabela `evidences` tem `parent_type` + `parent_id` (descoberta por índice).
- Tabela `decisions`/`action_items` tem `evidence_id` (FK pra evidence).
- Pra criar os dois com refs corretas, fazemos 3 etapas:
  1. INSERT parent (decision/action) sem evidence_id, flush pra obter id
  2. INSERT evidence com parent_id, flush
  3. UPDATE parent.evidence_id ← evidence.id

Não usamos `commit()` aqui — o caller (pipeline) controla a transação
pra manter o ciclo "stage → commit → status update" coerente.
"""

from __future__ import annotations

from datetime import date, datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionItem, Decision, Evidence, Minutes, Transcript, TranscriptSegment
from app.services.llm.base import LLMResponse
from app.services.minutes.schemas import (
    ActionItem as ActionItemSchema,
)
from app.services.minutes.schemas import (
    Decision as DecisionSchema,
)
from app.services.minutes.schemas import (
    Evidence as EvidenceSchema,
)
from app.services.minutes.schemas import (
    MinutesOutput,
)
from app.services.minutes.schemas import (
    Topic as TopicSchema,
)
from app.services.minutes.validator import ValidationReport
from app.services.transcription.base import TranscriptionResult


async def save_transcript(
    db: AsyncSession,
    meeting_id: str,
    transcription: TranscriptionResult,
) -> Transcript:
    """Persiste a transcrição completa + segments. Retorna o `Transcript`."""
    transcript = Transcript(
        meeting_id=meeting_id,
        full_text=transcription.full_text,
        language_detected=transcription.language,
        provider_used=transcription.provider_used,
        model_used=transcription.model_used,
        cost_usd=transcription.cost_usd,
        word_count=len(transcription.full_text.split()) if transcription.full_text else 0,
    )
    db.add(transcript)
    await db.flush()  # obtém transcript.id

    for i, seg in enumerate(transcription.segments):
        db.add(
            TranscriptSegment(
                transcript_id=transcript.id,
                meeting_id=meeting_id,
                segment_index=i,
                start_sec=seg.start_sec,
                end_sec=seg.end_sec,
                text=seg.text,
                speaker_id=seg.speaker,
                confidence=seg.confidence,
            )
        )
    await db.flush()
    logger.info(
        "Transcrição persistida",
        meeting_id=meeting_id,
        segments=len(transcription.segments),
        word_count=transcript.word_count,
    )
    return transcript


async def save_minutes(
    db: AsyncSession,
    meeting_id: str,
    minutes_output: MinutesOutput,
    llm_response: LLMResponse,
    validation_report: ValidationReport,
) -> Minutes:
    """
    Persiste a ata + decisions + action_items + evidences.

    Topics ficam serializados como JSON em `minutes.topics` (não há
    tabela `topics` separada — modelo MVP).
    """
    minutes = Minutes(
        meeting_id=meeting_id,
        title=minutes_output.title,
        date_extracted=_parse_date(minutes_output.date),
        executive_summary=minutes_output.executive_summary,
        participants=list(minutes_output.participants),
        topics=[_topic_to_jsonable(t) for t in minutes_output.topics],
        open_questions=list(minutes_output.open_questions),
        llm_provider=llm_response.provider,
        llm_model=llm_response.model,
        tokens_input=llm_response.tokens_input,
        tokens_output=llm_response.tokens_output,
        cost_usd=llm_response.cost_usd,
        validation_passed=validation_report.is_valid,
        validation_issues=_validation_issues_to_jsonable(validation_report),
    )
    db.add(minutes)
    await db.flush()

    for decision_schema in minutes_output.decisions:
        await _persist_decision(db, meeting_id, minutes.id, decision_schema)

    for action_schema in minutes_output.action_items:
        await _persist_action_item(db, meeting_id, minutes.id, action_schema)

    await db.flush()
    logger.info(
        "Ata persistida",
        meeting_id=meeting_id,
        topics=len(minutes_output.topics),
        decisions=len(minutes_output.decisions),
        actions=len(minutes_output.action_items),
        validation_passed=validation_report.is_valid,
    )
    return minutes


# ============================================================
# Helpers
# ============================================================


async def _persist_decision(
    db: AsyncSession,
    meeting_id: str,
    minute_id: str,
    schema: DecisionSchema,
) -> Decision:
    """Cria Decision + Evidence com link bidirecional."""
    decision = Decision(
        minute_id=minute_id,
        meeting_id=meeting_id,
        description=schema.description,
    )
    db.add(decision)
    await db.flush()  # obtém decision.id

    evidence = _make_evidence_row(
        meeting_id=meeting_id,
        parent_type="decision",
        parent_id=decision.id,
        schema=schema.evidence,
    )
    db.add(evidence)
    await db.flush()  # obtém evidence.id

    decision.evidence_id = evidence.id
    return decision


async def _persist_action_item(
    db: AsyncSession,
    meeting_id: str,
    minute_id: str,
    schema: ActionItemSchema,
) -> ActionItem:
    """Cria ActionItem + Evidence com link bidirecional."""
    action = ActionItem(
        minute_id=minute_id,
        meeting_id=meeting_id,
        description=schema.description,
        assigned_to=schema.assigned_to,
        deadline_raw=schema.deadline,
        deadline_parsed=_parse_date(schema.deadline),
    )
    db.add(action)
    await db.flush()

    evidence = _make_evidence_row(
        meeting_id=meeting_id,
        parent_type="action_item",
        parent_id=action.id,
        schema=schema.evidence,
    )
    db.add(evidence)
    await db.flush()

    action.evidence_id = evidence.id
    return action


def _make_evidence_row(
    *,
    meeting_id: str,
    parent_type: str,
    parent_id: str,
    schema: EvidenceSchema,
) -> Evidence:
    return Evidence(
        meeting_id=meeting_id,
        parent_type=parent_type,
        parent_id=parent_id,
        quote=schema.quote,
        speaker=schema.speaker,
        start_sec=schema.timestamp_sec,
        end_sec=None,
        validated=False,  # Pipeline marca True após validate_evidence passar
    )


def _topic_to_jsonable(topic: TopicSchema) -> dict:
    """Serializa Topic incluindo evidence pra coluna JSON da `minutes.topics`."""
    return {
        "title": topic.title,
        "summary": topic.summary,
        "evidence": {
            "quote": topic.evidence.quote,
            "speaker": topic.evidence.speaker,
            "timestamp_sec": topic.evidence.timestamp_sec,
        },
    }


def _validation_issues_to_jsonable(report: ValidationReport) -> list[dict] | None:
    if report.is_valid:
        return None
    return [
        {
            "field_path": p.field_path,
            "item_description": p.item_description,
            "quote": p.quote,
        }
        for p in report.problems
    ]


def _parse_date(raw: str | None) -> date | None:
    """
    Tenta parsear `raw` como ISO date (YYYY-MM-DD). Retorna None pra
    qualquer outra coisa — não inventamos datas, e LLM frequentemente
    emite formatos não-estruturados (ex: "sexta-feira") que ficam
    apenas em `deadline_raw`.
    """
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
