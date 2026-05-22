"""
Testes do persister (app.services.minutes.persister).

Usa SQLite in-memory via fixture `db_session`. Valida que rows
são criadas com campos corretos, link bidirecional Evidence ↔
Decision/ActionItem funciona, e serialização de topics/validation_issues.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    ActionItem as ActionItemRow,
)
from app.models import (
    Decision as DecisionRow,
)
from app.models import (
    Evidence as EvidenceRow,
)
from app.models import (
    Meeting,
    TranscriptSegment,
)
from app.services.llm.base import LLMResponse
from app.services.minutes.persister import save_minutes, save_transcript
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
    Topic,
)
from app.services.minutes.validator import (
    EvidenceProblem,
    ValidationReport,
)
from app.services.transcription.base import (
    TranscriptionResult,
    TranscriptionSegment,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
async def meeting(db_session) -> Meeting:
    """Cria uma Meeting padrão pra testes; commitada na session."""
    m = Meeting(
        title="Reunião teste",
        audio_path="/tmp/audio.mp3",
        audio_hash="abc123",
        language="pt",
        source="upload",
        status="pending",
    )
    db_session.add(m)
    await db_session.commit()
    return m


def _transcription(
    *,
    full_text: str = "olá tudo bem maria",
    segments: list[TranscriptionSegment] | None = None,
) -> TranscriptionResult:
    return TranscriptionResult(
        full_text=full_text,
        segments=segments
        or [
            TranscriptionSegment(start_sec=0.0, end_sec=2.0, text="olá tudo bem"),
            TranscriptionSegment(start_sec=2.0, end_sec=4.0, text="maria"),
        ],
        language="pt",
        duration_sec=4.0,
        provider_used="groq",
        model_used="whisper-large-v3-turbo",
        cost_usd=0.00012,
    )


def _llm_response(
    *,
    provider: str = "claude",
    model: str = "claude-sonnet-4-5",
    tokens_input: int = 1500,
    tokens_output: int = 800,
    cost_usd: float = 0.0165,
) -> LLMResponse:
    return LLMResponse(
        content="{}",
        provider=provider,
        model=model,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        cost_usd=cost_usd,
    )


def _minutes_output(*, with_problems: bool = False) -> MinutesOutput:
    return MinutesOutput(
        title="Reunião teste",
        date="2026-05-21",
        participants=["Ana", "Beto"],
        executive_summary="Resumo executivo",
        topics=[
            Topic(
                title="Tópico A",
                summary="Resumo A",
                evidence=EvidenceSchema(quote="trecho A", speaker="Ana", timestamp_sec=10.0),
            )
        ],
        decisions=[
            DecisionSchema(
                description="Decisão X",
                evidence=EvidenceSchema(quote="trecho X", speaker="Beto"),
            )
        ],
        action_items=[
            ActionItemSchema(
                description="Ação Y",
                assigned_to="Ana",
                deadline="sexta",
                evidence=EvidenceSchema(quote="trecho Y"),
            )
        ],
        open_questions=["Quem fecha?"],
    )


def _report(*, with_problems: bool = False) -> ValidationReport:
    if not with_problems:
        return ValidationReport()
    return ValidationReport(
        problems=[
            EvidenceProblem(
                field_path="action_items[0].evidence",
                item_description="Ação Y",
                quote="trecho Y",
            ),
        ]
    )


# ============================================================
# save_transcript
# ============================================================


async def test_save_transcript_creates_row_and_segments(db_session, meeting) -> None:
    tx = _transcription()
    saved = await save_transcript(db_session, meeting.id, tx)
    await db_session.commit()

    assert saved.full_text == "olá tudo bem maria"
    assert saved.provider_used == "groq"
    assert saved.word_count == 4  # split = ['olá', 'tudo', 'bem', 'maria']

    segments = (
        (
            await db_session.execute(
                select(TranscriptSegment).order_by(TranscriptSegment.segment_index)
            )
        )
        .scalars()
        .all()
    )
    assert len(segments) == 2
    assert segments[0].text == "olá tudo bem"
    assert segments[0].segment_index == 0
    assert segments[1].start_sec == 2.0
    assert all(s.meeting_id == meeting.id for s in segments)


async def test_save_transcript_preserves_speaker_and_confidence(db_session, meeting) -> None:
    tx = _transcription(
        segments=[
            TranscriptionSegment(
                start_sec=0.0,
                end_sec=1.0,
                text="oi",
                speaker="SPEAKER_00",
                confidence=0.95,
            )
        ]
    )
    await save_transcript(db_session, meeting.id, tx)
    await db_session.commit()
    seg = (await db_session.execute(select(TranscriptSegment))).scalar_one()
    assert seg.speaker_id == "SPEAKER_00"
    assert seg.confidence == 0.95


async def test_save_transcript_empty_full_text_word_count_zero(db_session, meeting) -> None:
    tx = _transcription(full_text="", segments=[])
    saved = await save_transcript(db_session, meeting.id, tx)
    await db_session.commit()
    assert saved.word_count == 0


# ============================================================
# save_minutes
# ============================================================


async def test_save_minutes_creates_all_rows(db_session, meeting) -> None:
    minutes = _minutes_output()
    saved = await save_minutes(
        db_session,
        meeting.id,
        minutes,
        _llm_response(),
        _report(),
    )
    await db_session.commit()

    assert saved.title == "Reunião teste"
    assert saved.participants == ["Ana", "Beto"]
    assert saved.tokens_input == 1500
    assert saved.cost_usd == 0.0165
    assert saved.validation_passed is True
    assert saved.validation_issues is None
    # date "2026-05-21" parsed
    assert saved.date_extracted is not None
    assert saved.date_extracted.isoformat() == "2026-05-21"

    decisions = (await db_session.execute(select(DecisionRow))).scalars().all()
    actions = (await db_session.execute(select(ActionItemRow))).scalars().all()
    evidences = (await db_session.execute(select(EvidenceRow))).scalars().all()
    assert len(decisions) == 1
    assert len(actions) == 1
    # 1 decision evidence + 1 action_item evidence (topic vai como JSON em minutes.topics)
    assert len(evidences) == 2


async def test_save_minutes_evidence_link_is_bidirectional(db_session, meeting) -> None:
    """Decision/ActionItem têm evidence_id; Evidence tem parent_id apontando de volta."""
    await save_minutes(
        db_session,
        meeting.id,
        _minutes_output(),
        _llm_response(),
        _report(),
    )
    await db_session.commit()

    decision = (await db_session.execute(select(DecisionRow))).scalar_one()
    assert decision.evidence_id is not None
    decision_evidence = (
        await db_session.execute(select(EvidenceRow).where(EvidenceRow.id == decision.evidence_id))
    ).scalar_one()
    assert decision_evidence.parent_type == "decision"
    assert decision_evidence.parent_id == decision.id
    assert decision_evidence.quote == "trecho X"
    assert decision_evidence.speaker == "Beto"

    action = (await db_session.execute(select(ActionItemRow))).scalar_one()
    assert action.evidence_id is not None
    action_evidence = (
        await db_session.execute(select(EvidenceRow).where(EvidenceRow.id == action.evidence_id))
    ).scalar_one()
    assert action_evidence.parent_type == "action_item"
    assert action_evidence.parent_id == action.id
    assert action_evidence.quote == "trecho Y"


async def test_save_minutes_topics_serialized_as_json(db_session, meeting) -> None:
    saved = await save_minutes(
        db_session,
        meeting.id,
        _minutes_output(),
        _llm_response(),
        _report(),
    )
    await db_session.commit()
    assert isinstance(saved.topics, list)
    assert len(saved.topics) == 1
    t = saved.topics[0]
    assert t["title"] == "Tópico A"
    assert t["evidence"]["quote"] == "trecho A"
    assert t["evidence"]["timestamp_sec"] == 10.0


async def test_save_minutes_records_validation_problems(db_session, meeting) -> None:
    saved = await save_minutes(
        db_session,
        meeting.id,
        _minutes_output(),
        _llm_response(),
        _report(with_problems=True),
    )
    await db_session.commit()
    assert saved.validation_passed is False
    assert saved.validation_issues is not None
    assert len(saved.validation_issues) == 1
    assert saved.validation_issues[0]["field_path"] == "action_items[0].evidence"


async def test_save_minutes_action_item_deadline_parsed(db_session, meeting) -> None:
    """Deadline em ISO date deve virar coluna `deadline_parsed`."""
    minutes = _minutes_output()
    minutes = minutes.model_copy(
        update={
            "action_items": [
                ActionItemSchema(
                    description="Y",
                    deadline="2026-06-01",
                    evidence=EvidenceSchema(quote="qq"),
                )
            ]
        }
    )
    await save_minutes(db_session, meeting.id, minutes, _llm_response(), _report())
    await db_session.commit()
    action = (await db_session.execute(select(ActionItemRow))).scalar_one()
    assert action.deadline_raw == "2026-06-01"
    assert action.deadline_parsed is not None
    assert action.deadline_parsed.isoformat() == "2026-06-01"


async def test_save_minutes_action_item_non_iso_deadline_stays_raw(db_session, meeting) -> None:
    """Deadline tipo 'sexta-feira' fica só em raw, parsed = None."""
    await save_minutes(db_session, meeting.id, _minutes_output(), _llm_response(), _report())
    await db_session.commit()
    action = (await db_session.execute(select(ActionItemRow))).scalar_one()
    assert action.deadline_raw == "sexta"
    assert action.deadline_parsed is None


async def test_save_minutes_invalid_date_str_yields_null_date_extracted(
    db_session, meeting
) -> None:
    """LLM emite 'data não mencionada' → date_extracted vira None."""
    minutes = _minutes_output().model_copy(update={"date": "amanhã"})
    saved = await save_minutes(db_session, meeting.id, minutes, _llm_response(), _report())
    await db_session.commit()
    assert saved.date_extracted is None


async def test_save_minutes_null_date(db_session, meeting) -> None:
    minutes = _minutes_output().model_copy(update={"date": None})
    saved = await save_minutes(db_session, meeting.id, minutes, _llm_response(), _report())
    await db_session.commit()
    assert saved.date_extracted is None


async def test_save_minutes_uniqueness_per_meeting(db_session, meeting) -> None:
    """Tabela minutes tem unique constraint em meeting_id."""
    await save_minutes(db_session, meeting.id, _minutes_output(), _llm_response(), _report())
    await db_session.commit()

    # Segunda inserção pra mesma meeting deveria falhar
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await save_minutes(db_session, meeting.id, _minutes_output(), _llm_response(), _report())
        await db_session.commit()
