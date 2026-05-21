"""
Testes CRUD básicos dos 15 models do Eskuta + comportamentos do schema
(FK cascade, unique constraints, defaults, JSON serialization).

Estratégia: SQLite in-memory via fixture `db_session` (conftest.py).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActionItem,
    ApiKey,
    AuditLog,
    Decision,
    Evidence,
    Meeting,
    MeetingTag,
    Minutes,
    MinuteVersion,
    ProcessingJob,
    Speaker,
    Tag,
    Transcript,
    TranscriptSegment,
    UserPreference,
)

# ============================================================
# Helpers
# ============================================================


async def _make_meeting(db: AsyncSession, **overrides) -> Meeting:
    defaults: dict = {
        "audio_path": "/tmp/meeting.mp3",
        "audio_hash": "deadbeef" * 8,
        "language": "pt",
        "source": "upload",
        "status": "pending",
    }
    defaults.update(overrides)
    m = Meeting(**defaults)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


async def _make_minute(db: AsyncSession, meeting: Meeting, **overrides) -> Minutes:
    defaults = {
        "meeting_id": meeting.id,
        "title": "Reunião teste",
        "executive_summary": "resumo",
        "llm_provider": "claude",
        "llm_model": "claude-sonnet-4-5",
    }
    defaults.update(overrides)
    mn = Minutes(**defaults)
    db.add(mn)
    await db.commit()
    await db.refresh(mn)
    return mn


# ============================================================
# Meeting
# ============================================================


async def test_meeting_create_and_defaults(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    assert m.id and len(m.id) == 32  # uuid hex
    assert m.language == "pt"
    assert m.source == "upload"
    assert m.status == "pending"
    assert m.created_at is not None
    assert m.updated_at is not None
    assert m.deleted_at is None


async def test_meeting_check_constraint_source(db_session: AsyncSession) -> None:
    m = Meeting(
        audio_path="/x.mp3",
        audio_hash="a" * 64,
        source="wat",  # inválido
    )
    db_session.add(m)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_meeting_json_columns_roundtrip(db_session: AsyncSession) -> None:
    m = await _make_meeting(
        db_session,
        speaker_map={"SPEAKER_00": "João", "SPEAKER_01": "Maria"},
        extra_metadata={"foo": "bar", "nested": [1, 2, 3]},
    )
    fetched = await db_session.get(Meeting, m.id)
    assert fetched is not None
    assert fetched.speaker_map == {"SPEAKER_00": "João", "SPEAKER_01": "Maria"}
    assert fetched.extra_metadata == {"foo": "bar", "nested": [1, 2, 3]}


# ============================================================
# Transcript + TranscriptSegment
# ============================================================


async def test_transcript_and_segments_cascade(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    t = Transcript(
        meeting_id=m.id,
        full_text="bom dia",
        provider_used="groq",
        model_used="whisper-large-v3-turbo",
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)

    seg = TranscriptSegment(
        transcript_id=t.id,
        meeting_id=m.id,
        segment_index=0,
        start_sec=0.0,
        end_sec=1.5,
        text="bom dia",
    )
    db_session.add(seg)
    await db_session.commit()

    # Deletar meeting deve cascatear pra transcript e segments
    await db_session.delete(m)
    await db_session.commit()
    assert (
        await db_session.execute(select(Transcript).where(Transcript.id == t.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(select(TranscriptSegment).where(TranscriptSegment.id == seg.id))
    ).scalar_one_or_none() is None


async def test_transcript_meeting_id_unique(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    db_session.add(Transcript(meeting_id=m.id, full_text="a", provider_used="groq", model_used="w"))
    await db_session.commit()
    db_session.add(Transcript(meeting_id=m.id, full_text="b", provider_used="groq", model_used="w"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


# ============================================================
# Minutes + cascade
# ============================================================


async def test_minutes_unique_per_meeting(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    await _make_minute(db_session, m)
    db_session.add(
        Minutes(
            meeting_id=m.id,
            title="dup",
            executive_summary="d",
            llm_provider="gpt",
            llm_model="gpt-5",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_minute_version_history(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    mn = await _make_minute(db_session, m)
    db_session.add_all(
        [
            MinuteVersion(
                minute_id=mn.id,
                version_number=1,
                snapshot_json={"v": 1},
                change_reason="initial",
            ),
            MinuteVersion(
                minute_id=mn.id,
                version_number=2,
                snapshot_json={"v": 2},
                change_reason="user_edit",
            ),
        ]
    )
    await db_session.commit()
    versions = (
        (await db_session.execute(select(MinuteVersion).order_by(MinuteVersion.version_number)))
        .scalars()
        .all()
    )
    assert [v.version_number for v in versions] == [1, 2]


# ============================================================
# ActionItem + Decision + Evidence
# ============================================================


async def test_action_item_with_evidence(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    mn = await _make_minute(db_session, m)
    ev = Evidence(
        meeting_id=m.id,
        parent_type="action_item",
        parent_id="placeholder",
        quote="vou ligar pra ele",
        speaker="João",
    )
    db_session.add(ev)
    await db_session.commit()

    ai = ActionItem(
        minute_id=mn.id,
        meeting_id=m.id,
        description="Ligar pro cliente",
        assigned_to="João",
        deadline_raw="amanhã",
        deadline_parsed=date(2026, 5, 22),
        evidence_id=ev.id,
    )
    db_session.add(ai)
    await db_session.commit()
    await db_session.refresh(ai)

    assert ai.priority == "normal"  # default
    assert ai.status == "pending"  # default
    assert ai.evidence_id == ev.id


async def test_action_item_check_constraints(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    mn = await _make_minute(db_session, m)
    db_session.add(
        ActionItem(
            minute_id=mn.id,
            meeting_id=m.id,
            description="x",
            priority="ULTRA",  # inválido
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_decision_set_null_on_evidence_delete(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    mn = await _make_minute(db_session, m)
    ev = Evidence(
        meeting_id=m.id,
        parent_type="decision",
        parent_id="x",
        quote="aprovado",
    )
    db_session.add(ev)
    await db_session.commit()

    d = Decision(
        minute_id=mn.id,
        meeting_id=m.id,
        description="Aprovamos o orçamento",
        evidence_id=ev.id,
    )
    db_session.add(d)
    await db_session.commit()

    # Apagar a evidence deve setar evidence_id pra NULL (não cascade)
    await db_session.delete(ev)
    await db_session.commit()
    await db_session.refresh(d)
    assert d.evidence_id is None


async def test_evidence_check_parent_type(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    db_session.add(
        Evidence(
            meeting_id=m.id,
            parent_type="WAT",  # inválido
            parent_id="x",
            quote="bla",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


# ============================================================
# Speaker
# ============================================================


async def test_speaker_create(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    s = Speaker(
        meeting_id=m.id,
        speaker_id="SPEAKER_00",
        display_name="João",
        total_speaking_sec=125.5,
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    assert s.id and len(s.id) == 32


# ============================================================
# ApiKey
# ============================================================


async def test_api_key_provider_unique(db_session: AsyncSession) -> None:
    db_session.add(ApiKey(provider="groq", is_configured=True))
    await db_session.commit()
    db_session.add(ApiKey(provider="groq", is_configured=False))
    with pytest.raises(IntegrityError):
        await db_session.commit()


# ============================================================
# ProcessingJob
# ============================================================


async def test_processing_job_progress_constraint(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    db_session.add(
        ProcessingJob(
            meeting_id=m.id,
            job_type="full_pipeline",
            progress_pct=150,  # fora do range 0-100
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_processing_job_defaults(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    j = ProcessingJob(meeting_id=m.id, job_type="full_pipeline")
    db_session.add(j)
    await db_session.commit()
    await db_session.refresh(j)
    assert j.status == "queued"
    assert j.progress_pct == 0
    assert j.retry_count == 0


# ============================================================
# UserPreference
# ============================================================


async def test_user_preference_key_unique(db_session: AsyncSession) -> None:
    db_session.add(UserPreference(key="preferred_llm", value="claude"))
    await db_session.commit()
    db_session.add(UserPreference(key="preferred_llm", value="gpt"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


# ============================================================
# AuditLog
# ============================================================


async def test_audit_log_create(db_session: AsyncSession) -> None:
    db_session.add(
        AuditLog(
            action="create_meeting",
            entity_type="meeting",
            entity_id="abc123",
            extra_metadata={"source": "upload"},
        )
    )
    await db_session.commit()
    row = (await db_session.execute(select(AuditLog))).scalar_one()
    assert row.action == "create_meeting"
    assert row.extra_metadata == {"source": "upload"}


# ============================================================
# Tag + MeetingTag
# ============================================================


async def test_meeting_tags_n_to_n(db_session: AsyncSession) -> None:
    m1 = await _make_meeting(db_session)
    m2 = await _make_meeting(db_session)
    t1 = Tag(name="urgente", color="#ff0000")
    t2 = Tag(name="cliente-x")
    db_session.add_all([t1, t2])
    await db_session.commit()

    db_session.add_all(
        [
            MeetingTag(meeting_id=m1.id, tag_id=t1.id),
            MeetingTag(meeting_id=m1.id, tag_id=t2.id),
            MeetingTag(meeting_id=m2.id, tag_id=t1.id),
        ]
    )
    await db_session.commit()

    rows = (await db_session.execute(select(MeetingTag))).scalars().all()
    assert len(rows) == 3


async def test_tag_name_unique(db_session: AsyncSession) -> None:
    db_session.add_all([Tag(name="urgente"), Tag(name="urgente")])
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_meeting_tag_cascade_on_meeting_delete(db_session: AsyncSession) -> None:
    m = await _make_meeting(db_session)
    t = Tag(name="x")
    db_session.add(t)
    await db_session.commit()
    db_session.add(MeetingTag(meeting_id=m.id, tag_id=t.id))
    await db_session.commit()

    await db_session.delete(m)
    await db_session.commit()

    rows = (await db_session.execute(select(MeetingTag))).scalars().all()
    assert rows == []
