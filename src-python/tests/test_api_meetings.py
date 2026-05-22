"""
Testes dos endpoints REST de /meetings (Fase 1.10).

- Upload com arquivo válido + inválido (extensão, tamanho)
- List com paginação, exclusão de soft-deleted
- Detail com eager-loading
- Status pra polling
- Speaker map update
- Delete soft + idempotência
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.meetings import ALLOWED_EXTENSIONS
from app.core.settings import settings
from app.db.base import utcnow
from app.models import (
    ActionItem,
    Decision,
    Evidence,
    Meeting,
    Minutes,
    Transcript,
    TranscriptSegment,
)

# ============================================================
# Helpers de fixture
# ============================================================


async def _create_meeting(
    db_session,
    *,
    title: str = "Reunião teste",
    status: str = "pending",
    soft_deleted: bool = False,
    extra_metadata: dict | None = None,
) -> Meeting:
    m = Meeting(
        title=title,
        original_filename="teste.mp3",
        audio_path="/tmp/teste.mp3",
        audio_hash="abc",
        language="pt",
        source="upload",
        status=status,
        deleted_at=utcnow() if soft_deleted else None,
        extra_metadata=extra_metadata,
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    return m


@pytest.fixture
def isolated_uploads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """APP_DIR aponta pra tmp_path — uploads não poluem o disco real."""
    monkeypatch.setattr(settings, "APP_DIR", tmp_path / "eskuta")
    return tmp_path


# ============================================================
# POST /meetings/upload
# ============================================================


async def test_upload_creates_meeting_and_dispatches_pipeline(
    client_with_db,
    isolated_uploads: Path,
) -> None:
    client, session = client_with_db
    audio_bytes = b"FAKE-MP3-CONTENT" * 100

    with patch(
        "app.api.meetings.process_meeting",
        new=AsyncMock(return_value=None),
    ) as mock_pipeline:
        res = await client.post(
            "/api/meetings/upload",
            files={"file": ("reunião.mp3", io.BytesIO(audio_bytes), "audio/mpeg")},
        )

    assert res.status_code == 201
    body = res.json()
    assert body["original_filename"] == "reunia_o.mp3" or "reuni" in body["original_filename"]
    assert body["file_size_bytes"] == len(audio_bytes)
    assert body["status"] == "pending"
    assert len(body["id"]) >= 8

    # Meeting persistida
    row = (await session.execute(select(Meeting).where(Meeting.id == body["id"]))).scalar_one()
    assert row.original_filename
    assert row.audio_path
    assert row.audio_hash
    assert row.source == "upload"
    assert row.status == "pending"
    assert Path(row.audio_path).exists()  # arquivo salvo

    # Pipeline foi agendado
    mock_pipeline.assert_awaited_once_with(body["id"])


async def test_upload_rejects_unsupported_extension(
    client_with_db,
    isolated_uploads: Path,
) -> None:
    client, _ = client_with_db
    res = await client.post(
        "/api/meetings/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"x" * 100), "application/pdf")},
    )
    assert res.status_code == 422
    assert "extens" in res.json()["detail"].lower()


async def test_upload_rejects_no_extension(
    client_with_db,
    isolated_uploads: Path,
) -> None:
    client, _ = client_with_db
    res = await client.post(
        "/api/meetings/upload",
        files={"file": ("noext", io.BytesIO(b"x" * 100), "audio/mpeg")},
    )
    assert res.status_code == 422


async def test_upload_enforces_size_limit(
    client_with_db,
    isolated_uploads: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pequenamos o limite pra forçar o 413 sem subir 500MB."""
    client, _ = client_with_db
    monkeypatch.setattr(settings, "MAX_AUDIO_MB", 1)  # 1MB

    too_big = b"x" * (2 * 1024 * 1024)  # 2MB
    with patch("app.api.meetings.process_meeting", new=AsyncMock()):
        res = await client.post(
            "/api/meetings/upload",
            files={"file": ("big.mp3", io.BytesIO(too_big), "audio/mpeg")},
        )
    assert res.status_code == 413
    assert "limite" in res.json()["detail"].lower()


async def test_upload_accepts_all_whitelisted_extensions(
    client_with_db,
    isolated_uploads: Path,
) -> None:
    client, _ = client_with_db
    with patch("app.api.meetings.process_meeting", new=AsyncMock()):
        for ext in ALLOWED_EXTENSIONS:
            res = await client.post(
                "/api/meetings/upload",
                files={"file": (f"r{ext}", io.BytesIO(b"abc"), "audio/x-test")},
            )
            assert res.status_code == 201, f"{ext} deveria ter sido aceito"


async def test_upload_with_title_param(
    client_with_db,
    isolated_uploads: Path,
) -> None:
    client, session = client_with_db
    with patch("app.api.meetings.process_meeting", new=AsyncMock()):
        res = await client.post(
            "/api/meetings/upload?title=Sprint%20Planning",
            files={"file": ("a.mp3", io.BytesIO(b"x"), "audio/mpeg")},
        )
    body = res.json()
    assert body["title"] == "Sprint Planning"
    row = (await session.execute(select(Meeting).where(Meeting.id == body["id"]))).scalar_one()
    assert row.title == "Sprint Planning"


async def test_upload_sanitizes_dangerous_filename(
    client_with_db,
    isolated_uploads: Path,
) -> None:
    """Filename com path/special chars NÃO vira o path final no disco."""
    client, session = client_with_db
    with patch("app.api.meetings.process_meeting", new=AsyncMock()):
        res = await client.post(
            "/api/meetings/upload",
            files={
                "file": (
                    "../../etc/passwd.mp3",
                    io.BytesIO(b"x"),
                    "audio/mpeg",
                )
            },
        )
    body = res.json()
    row = (await session.execute(select(Meeting).where(Meeting.id == body["id"]))).scalar_one()
    # Path real usa UUID — original fica em original_filename apenas (sanitized)
    assert "etc" in row.original_filename or "passwd" in row.original_filename
    # Path real NÃO contém .. nem etc/passwd
    assert ".." not in row.audio_path
    assert "etc" not in Path(row.audio_path).name


# ============================================================
# GET /meetings (list)
# ============================================================


async def test_list_returns_empty_when_no_meetings(
    client_with_db,
) -> None:
    client, _ = client_with_db
    res = await client.get("/api/meetings")
    assert res.status_code == 200
    assert res.json() == {"meetings": [], "total": 0, "limit": 50, "offset": 0}


async def test_list_orders_by_created_at_desc(
    client_with_db,
) -> None:
    client, session = client_with_db
    m1 = await _create_meeting(session, title="primeira")
    m2 = await _create_meeting(session, title="segunda")
    res = await client.get("/api/meetings")
    body = res.json()
    assert body["total"] == 2
    # Mais recente primeiro
    assert body["meetings"][0]["id"] == m2.id
    assert body["meetings"][1]["id"] == m1.id


async def test_list_excludes_soft_deleted(
    client_with_db,
) -> None:
    client, session = client_with_db
    m_alive = await _create_meeting(session, title="ativa")
    await _create_meeting(session, title="apagada", soft_deleted=True)
    res = await client.get("/api/meetings")
    body = res.json()
    assert body["total"] == 1
    assert body["meetings"][0]["id"] == m_alive.id


async def test_list_pagination(client_with_db) -> None:
    client, session = client_with_db
    for i in range(5):
        await _create_meeting(session, title=f"m{i}")
    res = await client.get("/api/meetings?limit=2&offset=0")
    body = res.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["meetings"]) == 2

    res2 = await client.get("/api/meetings?limit=2&offset=2")
    assert len(res2.json()["meetings"]) == 2


async def test_list_rejects_invalid_limit(client_with_db) -> None:
    client, _ = client_with_db
    assert (await client.get("/api/meetings?limit=0")).status_code == 422
    assert (await client.get("/api/meetings?limit=999")).status_code == 422
    assert (await client.get("/api/meetings?offset=-1")).status_code == 422


# ============================================================
# GET /meetings/{id}
# ============================================================


async def test_get_meeting_returns_detail_with_transcript_and_minutes(
    client_with_db,
) -> None:
    client, session = client_with_db
    meeting = await _create_meeting(session, status="completed")
    transcript = Transcript(
        meeting_id=meeting.id,
        full_text="texto completo aqui",
        language_detected="pt",
        provider_used="groq",
        model_used="whisper-large-v3-turbo",
        cost_usd=0.001,
        word_count=3,
    )
    session.add(transcript)
    await session.flush()
    session.add(
        TranscriptSegment(
            transcript_id=transcript.id,
            meeting_id=meeting.id,
            segment_index=0,
            start_sec=0.0,
            end_sec=2.0,
            text="texto completo",
            speaker_id="SPEAKER_00",
            confidence=0.95,
        )
    )
    minutes = Minutes(
        meeting_id=meeting.id,
        title="Ata X",
        executive_summary="Resumo curto",
        participants=["A", "B"],
        topics=[{"title": "T1", "summary": "S1", "evidence": {"quote": "q"}}],
        open_questions=["Q?"],
        llm_provider="claude",
        llm_model="claude-sonnet-4-5",
        tokens_input=100,
        tokens_output=50,
        cost_usd=0.01,
        validation_passed=True,
    )
    session.add(minutes)
    await session.flush()

    decision = Decision(
        minute_id=minutes.id,
        meeting_id=meeting.id,
        description="Decisão D1",
    )
    session.add(decision)
    await session.flush()
    decision_ev = Evidence(
        meeting_id=meeting.id,
        parent_type="decision",
        parent_id=decision.id,
        quote="trecho decision",
        speaker="A",
        start_sec=10.0,
        validated=True,
    )
    session.add(decision_ev)
    await session.flush()
    decision.evidence_id = decision_ev.id

    action = ActionItem(
        minute_id=minutes.id,
        meeting_id=meeting.id,
        description="Ação A1",
        assigned_to="B",
        deadline_raw="sexta",
    )
    session.add(action)
    await session.flush()
    action_ev = Evidence(
        meeting_id=meeting.id,
        parent_type="action_item",
        parent_id=action.id,
        quote="trecho ação",
    )
    session.add(action_ev)
    await session.flush()
    action.evidence_id = action_ev.id
    await session.commit()

    res = await client.get(f"/api/meetings/{meeting.id}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == meeting.id
    assert body["status"] == "completed"
    assert body["transcript"]["full_text"] == "texto completo aqui"
    assert len(body["transcript"]["segments"]) == 1
    assert body["transcript"]["segments"][0]["speaker_id"] == "SPEAKER_00"
    assert body["minutes"]["title"] == "Ata X"
    assert len(body["minutes"]["decisions"]) == 1
    assert body["minutes"]["decisions"][0]["evidence"]["quote"] == "trecho decision"
    assert len(body["minutes"]["action_items"]) == 1
    assert body["minutes"]["action_items"][0]["assigned_to"] == "B"


async def test_get_meeting_404_when_not_found(client_with_db) -> None:
    client, _ = client_with_db
    res = await client.get("/api/meetings/inexistente123")
    assert res.status_code == 404


async def test_get_meeting_404_when_soft_deleted(client_with_db) -> None:
    client, session = client_with_db
    m = await _create_meeting(session, soft_deleted=True)
    res = await client.get(f"/api/meetings/{m.id}")
    assert res.status_code == 404


async def test_get_meeting_returns_minimal_when_no_transcript_or_minutes(
    client_with_db,
) -> None:
    """Meeting recém-criada (pending) — transcript e minutes vêm None."""
    client, session = client_with_db
    m = await _create_meeting(session, status="pending")
    res = await client.get(f"/api/meetings/{m.id}")
    assert res.status_code == 200
    body = res.json()
    assert body["transcript"] is None
    assert body["minutes"] is None


# ============================================================
# GET /meetings/{id}/status
# ============================================================


async def test_status_returns_meeting_status(client_with_db) -> None:
    client, session = client_with_db
    m = await _create_meeting(session, status="transcribing")
    res = await client.get(f"/api/meetings/{m.id}/status")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "transcribing"
    assert body["error"] is None


async def test_status_includes_error_when_failed(client_with_db) -> None:
    client, session = client_with_db
    m = await _create_meeting(
        session,
        status="failed",
        extra_metadata={"error": "Groq API down", "error_type": "RuntimeError"},
    )
    res = await client.get(f"/api/meetings/{m.id}/status")
    body = res.json()
    assert body["status"] == "failed"
    assert body["error"] == "Groq API down"
    assert body["error_type"] == "RuntimeError"


async def test_status_404_when_not_found(client_with_db) -> None:
    client, _ = client_with_db
    res = await client.get("/api/meetings/nope/status")
    assert res.status_code == 404


# ============================================================
# PUT /meetings/{id}/speaker-map
# ============================================================


async def test_speaker_map_set_and_replace(client_with_db) -> None:
    client, session = client_with_db
    m = await _create_meeting(session)
    res = await client.put(
        f"/api/meetings/{m.id}/speaker-map",
        json={"speaker_map": {"SPEAKER_00": "João", "SPEAKER_01": "Maria"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["speaker_map"]["SPEAKER_00"] == "João"

    # Substitui — não merge
    res2 = await client.put(
        f"/api/meetings/{m.id}/speaker-map",
        json={"speaker_map": {"SPEAKER_00": "Pedro"}},
    )
    body2 = res2.json()
    assert body2["speaker_map"] == {"SPEAKER_00": "Pedro"}
    assert "SPEAKER_01" not in body2["speaker_map"]


async def test_speaker_map_clear_with_empty_dict(client_with_db) -> None:
    client, session = client_with_db
    m = await _create_meeting(session)
    # Setou primeiro
    await client.put(
        f"/api/meetings/{m.id}/speaker-map",
        json={"speaker_map": {"SPEAKER_00": "João"}},
    )
    # Limpa
    res = await client.put(f"/api/meetings/{m.id}/speaker-map", json={"speaker_map": {}})
    assert res.json()["speaker_map"] == {}


async def test_speaker_map_404_when_not_found(client_with_db) -> None:
    client, _ = client_with_db
    res = await client.put(
        "/api/meetings/no/speaker-map",
        json={"speaker_map": {"X": "Y"}},
    )
    assert res.status_code == 404


# ============================================================
# DELETE /meetings/{id}
# ============================================================


async def test_delete_soft_deletes(client_with_db) -> None:
    client, session = client_with_db
    m = await _create_meeting(session)
    res = await client.delete(f"/api/meetings/{m.id}")
    assert res.status_code == 200
    assert res.json() == {"id": m.id, "deleted": True}

    # Refresh assíncrono lê o estado fresco do DB (a mudança veio da
    # request_session, e o identity map da test_session estava stale).
    await session.refresh(m)
    assert m.deleted_at is not None


async def test_delete_404_when_not_found(client_with_db) -> None:
    client, _ = client_with_db
    res = await client.delete("/api/meetings/no")
    assert res.status_code == 404


async def test_delete_idempotent_returns_404_second_time(client_with_db) -> None:
    """Após soft delete, deletar de novo retorna 404 (já foi)."""
    client, session = client_with_db
    m = await _create_meeting(session)
    await client.delete(f"/api/meetings/{m.id}")
    res = await client.delete(f"/api/meetings/{m.id}")
    assert res.status_code == 404
