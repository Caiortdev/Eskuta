"""
Endpoints REST de transcrição.

Conforme RELATORIO_TECNICO §1.4.2, expomos um `POST /transcribe/start`
que dispara `process_meeting` em background. A função `process_meeting`
é um **stub** nesta fase — a orquestração completa (load meeting → load
audio → preprocess → chunk → transcribe paralelo → persist) é território
da Fase 1.9 (Pipeline de Geração da Ata). Aqui só validamos o contrato
do endpoint e o agendamento em BackgroundTasks.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/transcribe", tags=["transcribe"])


class StartTranscriptionRequest(BaseModel):
    meeting_id: str = Field(min_length=1, max_length=64)


class StartTranscriptionResponse(BaseModel):
    status: str
    meeting_id: str


async def process_meeting(meeting_id: str) -> None:
    """
    STUB — implementação completa virá na Fase 1.9.

    A versão final vai: carregar a meeting do DB, recuperar/preprocessar
    o áudio, VAD + chunking, transcrever em paralelo via TranscriptionRouter
    e persistir `Transcript` + `TranscriptSegment` no DB. Nesta fase apenas
    registramos a chamada — não há side effects.
    """
    logger.warning(
        "process_meeting (STUB) chamado",
        meeting_id=meeting_id,
        note="Orquestração completa será implementada na Fase 1.9",
    )


@router.post("/start", response_model=StartTranscriptionResponse)
async def start_transcription(
    body: StartTranscriptionRequest,
    background: BackgroundTasks,
) -> StartTranscriptionResponse:
    """Dispara transcrição assíncrona de uma reunião identificada por ID."""
    background.add_task(process_meeting, body.meeting_id)
    return StartTranscriptionResponse(status="processing", meeting_id=body.meeting_id)
