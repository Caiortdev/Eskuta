"""
Pipeline de geração da ata (RELATORIO_TECNICO §1.9.1).

Orquestra TUDO que foi construído nas fases anteriores:

    Meeting (DB) → audio_path
       ↓ Stage 1: convert (ffmpeg → MP3 16kHz mono)
       ↓ Stage 2: VAD (silero)
       ↓ Stage 3: chunk (corta em silêncios, max 10min)
       ↓ Stage 4: transcribe (Groq/AssemblyAI router, paralelo)
       ↓ Stage 5: diarize (pyannote — opcional, gracefully skip se sem HF_TOKEN)
       ↓ Stage 6: generate minutes (LLM router + system/user prompts)
       ↓ Stage 7: validate (rapidfuzz local) + regen até MAX_REGEN_ATTEMPTS
       ↓ Stage 8: persist (Transcript + Minutes + Evidences + status=completed)

Cada estágio atualiza `meeting.status` e commita. Em qualquer falha,
marca `status=failed` com mensagem em `extra_metadata.error`.

Decisões de design:
- LLM-as-judge (stage 8 do relatório) ficou de FORA — validação default
  é local via rapidfuzz (vide AUDIT-FASE-1.7). VALIDATION_PROMPT
  permanece disponível pra escalação V2.
- Estratégia 1.9.2 (3-pass pra reuniões >1h) deferida — modelos
  modernos (Claude 4.5, GPT-4.1, Gemini 2.5) têm 200k+ context, então
  single-pass cobre o MVP. Adicionar threshold de tokens + 3-pass
  como follow-up se aparecer reunião que estoura.
- `process_meeting` recebe `session_factory` opcional pra facilitar
  testes (default = singleton `AsyncSessionLocal`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Final

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import settings
from app.db.database import AsyncSessionLocal
from app.models import Meeting
from app.services.audio.chunker import chunk_audio_smart
from app.services.audio.converter import convert_to_optimized_mp3_async
from app.services.audio.vad import detect_speech_segments
from app.services.llm.router import LLMRouter
from app.services.minutes.generator import (
    GenerationResult,
    generate_minutes,
    regenerate_with_correction,
)
from app.services.minutes.persister import save_minutes, save_transcript
from app.services.minutes.validator import purge_invalid_items, validate_minutes
from app.services.transcription.parallel import (
    merge_chunk_transcriptions,
    transcribe_chunks_parallel,
)
from app.services.transcription.router import TranscriptionRouter

# Lifecycle do status — UI mostra texto correspondente. "diarizing"
# foi removido em v0.1 (diarização tirada do pipeline; manter o
# valor como reservado pra v0.2 quando voltar opt-in).
MEETING_STATUS_VALUES: Final[tuple[str, ...]] = (
    "pending",
    "converting",
    "detecting_speech",
    "chunking",
    "transcribing",
    "diarizing",  # reservado v0.2 (opt-in via AssemblyAI ou GPU local)
    "generating_minutes",
    "validating",
    "completed",
    "failed",
)

DEFAULT_MAX_REGEN_ATTEMPTS: Final[int] = 2  # Princípio do relatório §1.7.2

# Tipo do session factory (default ou injetado pra testes).
SessionFactory = async_sessionmaker[AsyncSession]


# Timeout global pra todo o pipeline. Reuniões longas de até ~4h devem
# completar em 30min real time (chunks paralelos). Acima disso considera
# patológico e aborta — meeting fica em failed.
PIPELINE_TIMEOUT_SEC: int = 30 * 60


async def process_meeting(
    meeting_id: str,
    *,
    session_factory: SessionFactory | None = None,
    transcription_router: TranscriptionRouter | None = None,
    llm_router: LLMRouter | None = None,
    max_regen_attempts: int = DEFAULT_MAX_REGEN_ATTEMPTS,
    timeout_sec: int = PIPELINE_TIMEOUT_SEC,
) -> None:
    """
    Pipeline completo. Carrega meeting do DB, processa, persiste,
    e atualiza `meeting.status` em cada estágio. Erros são capturados
    e marcados como `failed` (não re-raised).

    Args:
        meeting_id: ID da meeting já criada no DB (audio_path preenchido).
        session_factory: factory de sessão; default usa `AsyncSessionLocal`.
        transcription_router: router de STT; default usa `TranscriptionRouter()`.
        llm_router: router de LLM; default usa `LLMRouter()`.
        max_regen_attempts: regen pra validação falha (default 2 por relatório).
        timeout_sec: tempo máximo total; após isso meeting vira failed.
    """
    factory: SessionFactory = session_factory or AsyncSessionLocal
    tx_router = transcription_router or TranscriptionRouter()
    ll_router = llm_router or LLMRouter()

    async with factory() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting is None:
            logger.error("Meeting não encontrada", meeting_id=meeting_id)
            return

        try:
            await asyncio.wait_for(
                _run_pipeline(
                    db=db,
                    meeting=meeting,
                    tx_router=tx_router,
                    llm_router=ll_router,
                    max_regen_attempts=max_regen_attempts,
                ),
                timeout=timeout_sec,
            )
        except TimeoutError:
            logger.error(
                "Pipeline excedeu timeout",
                meeting_id=meeting_id,
                timeout_sec=timeout_sec,
            )
            timeout_exc = TimeoutError(f"Pipeline excedeu {timeout_sec}s")
            await _mark_failed(db, meeting, timeout_exc)
        except Exception as exc:
            logger.exception("Pipeline falhou", meeting_id=meeting_id)
            await _mark_failed(db, meeting, exc)


async def _run_pipeline(
    *,
    db: AsyncSession,
    meeting: Meeting,
    tx_router: TranscriptionRouter,
    llm_router: LLMRouter,
    max_regen_attempts: int,
) -> None:
    """Roda os 8 estágios. Levanta em qualquer falha — caller marca failed."""
    meeting_id = meeting.id
    audio_path = Path(meeting.audio_path)

    # ============================================================
    # Stage 1: Conversão de áudio
    # ============================================================
    await _set_status(db, meeting, "converting")
    settings.ensure_dirs()
    optimized_path = settings.PROCESSED_DIR / f"{meeting_id}.mp3"
    await convert_to_optimized_mp3_async(audio_path, optimized_path)

    # ============================================================
    # Stage 2: VAD (Voice Activity Detection)
    # ============================================================
    await _set_status(db, meeting, "detecting_speech")
    speech_segments = await _to_thread(detect_speech_segments, optimized_path)

    # ============================================================
    # Stage 3: Chunking inteligente
    # ============================================================
    await _set_status(db, meeting, "chunking")
    chunks_dir = settings.PROCESSED_DIR / meeting_id
    chunks = await _to_thread(
        chunk_audio_smart,
        optimized_path,
        speech_segments,
        chunks_dir,
    )

    # ============================================================
    # Stage 4: Transcrição paralela
    # ============================================================
    # Diarização (Stage 5 antigo) foi REMOVIDA do MVP v0.1 — pesa demais
    # em CPU (pyannote leva ~5-10min sem GPU pra reunião de 20min) e
    # adiciona ~1GB no bundle (torch + pyannote + speechbrain). Pra v0.2
    # o plano é oferecer diarização via AssemblyAI (cloud, opt-in) ou
    # download sob demanda do pyannote pra quem tem GPU. Código em
    # app.services.diarization permanece pra reuso futuro.
    await _set_status(db, meeting, "transcribing")

    chunk_results = await transcribe_chunks_parallel(chunks, tx_router)
    transcription = merge_chunk_transcriptions(chunks, chunk_results)
    await save_transcript(db, meeting_id, transcription)

    # Sem diarização, os segments da transcrição não têm speaker_id —
    # a ata vai sair sem rótulos "SPEAKER_00 disse X". Já é um fluxo
    # válido e estável: a maior parte das atas curtas funciona sem
    # diarização.
    transcription_with_speakers = transcription

    # ============================================================
    # Stage 6: Geração da ata
    # ============================================================
    await _set_status(db, meeting, "generating_minutes")
    generation = await generate_minutes(llm_router, transcription_with_speakers.full_text)

    # ============================================================
    # Stage 7: Validação cruzada (local) + regen
    # ============================================================
    # Crítico: se o regen levantar ValidationError (JSON truncado após
    # N tentativas), CAPTURAMOS e seguimos com a generation ORIGINAL
    # — o PURGE da próxima fase vai limpar os items inválidos. Antes
    # esse erro propagava → pipeline morria sem chance do purge agir.
    await _set_status(db, meeting, "validating")
    from pydantic import ValidationError as _PydValidationError

    try:
        generation, validation_report = await _validate_and_regen(
            llm_router=llm_router,
            transcript_text=transcription_with_speakers.full_text,
            initial_generation=generation,
            max_regen_attempts=max_regen_attempts,
        )
    except _PydValidationError as exc:
        logger.warning(
            "Regen esgotou tentativas com JSON invalido — "
            "seguindo com generation original (purge vai filtrar)",
            error=str(exc)[:200],
        )
        # `generation` ainda aponta pra ata original (que parseou OK).
        # Recalcula validation_report a partir dela.
        validation_report = validate_minutes(
            generation.minutes,
            transcription_with_speakers.full_text,
        )

    # ============================================================
    # Stage 7.5: PURGE determinístico (última linha de defesa anti-alucinação)
    # ============================================================
    # Se depois de N regens AINDA tem evidence inválida, o LLM esgotou
    # as chances de corrigir. Em vez de persistir uma ata com items
    # alucinados, REMOVEMOS deterministicamente os items inválidos.
    # Garante que a ata final só contém itens cuja citação está
    # auditavelmente no transcript.
    purged_minutes, purge_report = purge_invalid_items(
        generation.minutes,
        transcription_with_speakers.full_text,
    )
    if purge_report.total_removed > 0:
        logger.info(
            "Items removidos por purge",
            removed_total=purge_report.total_removed,
            topics=purge_report.removed_topics,
            decisions=purge_report.removed_decisions,
            actions=purge_report.removed_action_items,
            kept_topics=len(purged_minutes.topics),
            kept_decisions=len(purged_minutes.decisions),
            kept_actions=len(purged_minutes.action_items),
        )
        # Recalcula validation_report já filtrado — agora is_valid=True
        # (porque tudo que sobrou passa) E o report de problems mostra
        # o que foi removido (pra UI alertar com transparência).
        validation_report = validate_minutes(
            purged_minutes,
            transcription_with_speakers.full_text,
        )

    # ============================================================
    # Stage 8: Persistir ata + marcar completed
    # ============================================================
    await save_minutes(
        db=db,
        meeting_id=meeting_id,
        minutes_output=purged_minutes,
        llm_response=generation.llm_response,
        validation_report=validation_report,
    )
    await _set_status(db, meeting, "completed")
    logger.info(
        "Pipeline concluído",
        meeting_id=meeting_id,
        validation_passed=validation_report.is_valid,
        purged_count=purge_report.total_removed,
        total_cost_usd=round(transcription.cost_usd + generation.llm_response.cost_usd, 6),
    )


# ============================================================
# Stage helpers
# ============================================================


async def _validate_and_regen(
    *,
    llm_router: LLMRouter,
    transcript_text: str,
    initial_generation: GenerationResult,
    max_regen_attempts: int,
):
    """
    Aplica validate_minutes; se falhar, regera com prompt corretivo
    até `max_regen_attempts`. Retorna (último_generation, último_report).

    A ata final é persistida mesmo se ainda inválida — usuário vê com
    badge "atenção" + lista de problemas (campo `validation_issues`).
    """
    generation = initial_generation
    report = validate_minutes(generation.minutes, transcript_text)

    for attempt in range(1, max_regen_attempts + 1):
        if report.is_valid:
            return generation, report
        logger.warning(
            "Validação falhou — regenerando",
            attempt=attempt,
            max_attempts=max_regen_attempts,
            problems=len(report.problems),
        )
        generation = await regenerate_with_correction(
            llm_router,
            transcript_text,
            report,
        )
        report = validate_minutes(generation.minutes, transcript_text)

    if not report.is_valid:
        logger.warning(
            "Validação ainda falha após max regens — entregando com warnings",
            problems=len(report.problems),
        )
    return generation, report


# ============================================================
# DB helpers
# ============================================================


async def _set_status(db: AsyncSession, meeting: Meeting, status: str) -> None:
    """Atualiza meeting.status e commita imediatamente (UI vê progresso)."""
    if status not in MEETING_STATUS_VALUES:
        raise ValueError(f"Status desconhecido: {status!r}")
    meeting.status = status
    await db.commit()
    logger.info("Pipeline stage", meeting_id=meeting.id, status=status)


async def _mark_failed(
    db: AsyncSession,
    meeting: Meeting,
    exc: BaseException,
) -> None:
    """
    Marca meeting como failed com `error` em `extra_metadata`. Usa
    rollback primeiro pra limpar qualquer estado meio-commitado da
    transação atual.
    """
    with contextlib.suppress(Exception):
        await db.rollback()

    refreshed = await db.get(Meeting, meeting.id)
    if refreshed is None:
        return  # meeting sumiu — não tem como persistir o erro

    refreshed.status = "failed"
    metadata = dict(refreshed.extra_metadata or {})
    metadata["error"] = str(exc)[:500]
    metadata["error_type"] = type(exc).__name__
    refreshed.extra_metadata = metadata
    await db.commit()


# ============================================================
# Async helpers
# ============================================================


async def _to_thread(func: Callable, *args, **kwargs):
    """
    Roda função síncrona em thread pool — evita bloquear o event loop
    com I/O pesado (ffmpeg, torch.hub model loading, etc.).
    """
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# Make linter happy (Awaitable imported but used implicitly via async funcs)
_ = Awaitable
