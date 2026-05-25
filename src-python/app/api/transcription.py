"""
Endpoints REST de transcrição / orquestração de meeting.

`POST /transcribe/start` dispara o pipeline completo da Fase 1.9
(`process_meeting`) em background. Retorna imediatamente com status
`processing`; UI polla `/meetings/{id}/status` (a ser implementado
na Fase 1.10) pra mostrar progresso por estágio.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.minutes.pipeline import process_meeting

router = APIRouter(prefix="/api/transcribe", tags=["transcribe"])


class StartTranscriptionRequest(BaseModel):
    meeting_id: str = Field(min_length=1, max_length=64)


class StartTranscriptionResponse(BaseModel):
    status: str
    meeting_id: str


@router.post("/start", response_model=StartTranscriptionResponse)
async def start_transcription(
    body: StartTranscriptionRequest,
    background: BackgroundTasks,
) -> StartTranscriptionResponse:
    """
    Dispara o pipeline assíncrono de processamento da reunião.

    A reunião precisa já existir no DB (criada por upload — vai entrar
    em Fase 1.10). Esta rota só agenda — o pipeline real (`process_meeting`)
    roda em background e atualiza `meeting.status` em cada estágio.
    """
    background.add_task(process_meeting, body.meeting_id)
    return StartTranscriptionResponse(status="processing", meeting_id=body.meeting_id)
