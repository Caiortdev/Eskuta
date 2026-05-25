"""
Testes do endpoint REST /transcribe (app.api.transcription).

O `process_meeting` real (pipeline da Fase 1.9) é mockado aqui —
testes de pipeline ficam em `test_minutes_pipeline.py`. Aqui só
validamos contrato do endpoint, validação de input, e que o
BackgroundTask agenda a chamada certa.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx


async def test_start_transcription_returns_processing(client: httpx.AsyncClient) -> None:
    with patch(
        "app.api.transcription.process_meeting",
        new=AsyncMock(return_value=None),
    ):
        res = await client.post(
            "/api/transcribe/start",
            json={"meeting_id": "abc123"},
        )
    assert res.status_code == 200
    assert res.json() == {"status": "processing", "meeting_id": "abc123"}


async def test_start_transcription_validates_empty_meeting_id(
    client: httpx.AsyncClient,
) -> None:
    res = await client.post(
        "/api/transcribe/start",
        json={"meeting_id": ""},
    )
    assert res.status_code == 422


async def test_start_transcription_validates_missing_meeting_id(
    client: httpx.AsyncClient,
) -> None:
    res = await client.post(
        "/api/transcribe/start",
        json={},
    )
    assert res.status_code == 422


async def test_start_transcription_schedules_process_meeting(
    client: httpx.AsyncClient,
) -> None:
    """O endpoint deve agendar `process_meeting` via BackgroundTasks."""
    with patch(
        "app.api.transcription.process_meeting",
        new=AsyncMock(return_value=None),
    ) as mock_process:
        res = await client.post(
            "/api/transcribe/start",
            json={"meeting_id": "meet-42"},
        )
    assert res.status_code == 200
    # BackgroundTasks roda em loopback com ASGITransport — chamada
    # acontece dentro do request
    mock_process.assert_awaited_once_with("meet-42")


async def test_start_transcription_validates_too_long_meeting_id(
    client: httpx.AsyncClient,
) -> None:
    res = await client.post(
        "/api/transcribe/start",
        json={"meeting_id": "x" * 65},
    )
    assert res.status_code == 422


async def test_health_still_responds_after_router_mounted(
    client: httpx.AsyncClient,
) -> None:
    """Smoke: incluir o router /transcribe não quebrou /health."""
    res = await client.get("/health")
    assert res.status_code == 200
