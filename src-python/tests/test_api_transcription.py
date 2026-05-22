"""
Testes do endpoint REST /transcribe (app.api.transcription).

A `process_meeting` é stub nesta fase — validamos contrato do endpoint,
validação de input e que o BackgroundTask foi agendado. A orquestração
de verdade entra na Fase 1.9.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx


async def test_start_transcription_returns_processing(client: httpx.AsyncClient) -> None:
    res = await client.post(
        "/transcribe/start",
        json={"meeting_id": "abc123"},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "processing", "meeting_id": "abc123"}


async def test_start_transcription_validates_empty_meeting_id(
    client: httpx.AsyncClient,
) -> None:
    res = await client.post(
        "/transcribe/start",
        json={"meeting_id": ""},
    )
    assert res.status_code == 422


async def test_start_transcription_validates_missing_meeting_id(
    client: httpx.AsyncClient,
) -> None:
    res = await client.post(
        "/transcribe/start",
        json={},
    )
    assert res.status_code == 422


async def test_start_transcription_schedules_background_task(
    client: httpx.AsyncClient,
) -> None:
    """O endpoint deve agendar process_meeting via BackgroundTasks."""
    with patch(
        "app.api.transcription.process_meeting",
        new=AsyncMock(return_value=None),
    ) as mock_process:
        res = await client.post(
            "/transcribe/start",
            json={"meeting_id": "meet-42"},
        )
    assert res.status_code == 200
    # BackgroundTasks roda em loopback — chamada acontece dentro do request
    mock_process.assert_awaited_once_with("meet-42")


async def test_process_meeting_stub_logs_warning(
    loguru_messages: list[str],
) -> None:
    from app.api.transcription import process_meeting

    await process_meeting("meeting-stub-123")
    combined = "\n".join(loguru_messages)
    # Deve mencionar STUB ou 1.9 — sinal de que é placeholder
    assert "STUB" in combined or "1.9" in combined
    assert "meeting-stub-123" in combined


async def test_health_still_responds_after_router_mounted(
    client: httpx.AsyncClient,
) -> None:
    """Smoke: incluir o router /transcribe não quebrou /health."""
    res = await client.get("/health")
    assert res.status_code == 200
