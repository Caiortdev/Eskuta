"""
Endpoints REST de meetings (Fase 1.10) — consumidos pelo frontend React.

Rotas:
- POST   /meetings/upload         — multipart upload, cria Meeting + dispatcha pipeline em background
- GET    /meetings                — lista (paginada, soft-deleted excluídos)
- GET    /meetings/{id}           — detail completo (Meeting + Transcript + Minutes se prontos)
- GET    /meetings/{id}/status    — endpoint enxuto de polling pra UI de progresso
- PUT    /meetings/{id}/speaker-map — renomeio de speakers (Fase 1.5.3, consumido por frontend)
- DELETE /meetings/{id}           — soft delete (preenche deleted_at; reutilizável via undelete)

Princípios herdados das fases anteriores:
- Pydantic em todo endpoint (1.4 / 1.7)
- Limites operacionais explícitos: 500MB, extensões whitelist
- BackgroundTasks dispatcha `process_meeting` (1.9) sem bloquear
  o request
- 404 estruturados (não vaza 500 com stacktrace)
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Final

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.settings import settings
from app.db.base import utcnow
from app.db.database import get_db
from app.models import (
    ActionItem,
    Decision,
    Evidence,
    Meeting,
    Minutes,
    Transcript,
)
from app.services.minutes.pipeline import process_meeting

router = APIRouter(prefix="/api/meetings", tags=["meetings"])

DbSession = Annotated[AsyncSession, Depends(get_db)]

# Whitelist de extensões aceitas no upload (corresponde aos formatos
# que o ffmpeg consegue converter pra MP3 16kHz mono).
ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({".mp3", ".mp4", ".m4a", ".wav"})

# Quanto é lido em cada chunk durante upload + hashing. 4MB equilibra
# overhead de syscalls vs uso de memória.
_HASH_READ_CHUNK_BYTES: Final[int] = 4 * 1024 * 1024


# ============================================================
# Schemas
# ============================================================


class MeetingListItem(BaseModel):
    """Item leve pra lista (Home/Dashboard)."""

    id: str
    title: str | None
    original_filename: str | None
    duration_sec: float | None
    file_size_bytes: int | None
    language: str
    source: str
    status: str
    created_at: datetime


class MeetingListResponse(BaseModel):
    meetings: list[MeetingListItem]
    total: int
    limit: int
    offset: int


class MeetingStatusResponse(BaseModel):
    """Endpoint enxuto pra polling — só o que a UI precisa pra animar."""

    id: str
    status: str
    error: str | None = None
    error_type: str | None = None


class EvidenceResponse(BaseModel):
    quote: str
    speaker: str | None = None
    timestamp_sec: float | None = None


class DecisionItemResponse(BaseModel):
    id: str
    description: str
    evidence: EvidenceResponse | None = None


class ActionItemResponse(BaseModel):
    id: str
    description: str
    assigned_to: str | None = None
    deadline_raw: str | None = None
    deadline_parsed: date | None = None
    priority: str
    status: str
    evidence: EvidenceResponse | None = None


class MinutesResponse(BaseModel):
    id: str
    title: str
    date_extracted: date | None = None
    executive_summary: str
    participants: list[str]
    topics: list[dict[str, Any]]
    open_questions: list[str]
    decisions: list[DecisionItemResponse]
    action_items: list[ActionItemResponse]
    llm_provider: str
    llm_model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    validation_passed: bool
    validation_issues: list[dict[str, Any]] | None = None


class TranscriptSegmentResponse(BaseModel):
    start_sec: float
    end_sec: float
    text: str
    speaker_id: str | None = None
    confidence: float | None = None


class TranscriptResponse(BaseModel):
    id: str
    full_text: str
    language_detected: str | None = None
    provider_used: str
    model_used: str
    word_count: int | None = None
    segments: list[TranscriptSegmentResponse]


class MeetingDetailResponse(BaseModel):
    """Detail completo — pra tela de detalhes da reunião."""

    id: str
    title: str | None = None
    original_filename: str | None = None
    audio_path: str
    audio_hash: str
    duration_sec: float | None = None
    file_size_bytes: int | None = None
    language: str
    source: str
    status: str
    speaker_map: dict[str, str] | None = None
    extra_metadata: dict[str, Any] | None = None
    started_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None
    transcript: TranscriptResponse | None = None
    minutes: MinutesResponse | None = None


class MeetingCreatedResponse(BaseModel):
    """Retorno do upload — frontend redireciona pra /processing/{id}."""

    id: str
    status: str
    title: str | None
    original_filename: str
    file_size_bytes: int


class SpeakerMapUpdate(BaseModel):
    """Body do PUT /speaker-map."""

    speaker_map: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapeamento SPEAKER_XX → nome humano. Speakers não incluídos " "preservam ID original."
        ),
    )


class SpeakerMapResponse(BaseModel):
    id: str
    speaker_map: dict[str, str]


class DeleteResponse(BaseModel):
    id: str
    deleted: bool


# ============================================================
# Helpers
# ============================================================


_FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _sanitize_filename(name: str | None) -> str:
    """
    Remove caracteres não-seguros do filename original — usado só na
    coluna `original_filename` (display). O path real usa UUID, então
    não há risco de path traversal mesmo se sanitização falhar.
    """
    if not name:
        return "upload"
    base = Path(name).name  # remove paths
    sanitized = _FILENAME_SANITIZE_RE.sub("_", base)
    return sanitized[:200] or "upload"


def _validate_extension(filename: str | None) -> str:
    """Retorna a extensão lowercase ou levanta 422."""
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Arquivo sem nome.",
        )
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Extensão {ext!r} não suportada. Aceitos: "
                f"{', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )
    return ext


async def _save_upload_streaming(
    upload: UploadFile,
    output_path: Path,
    *,
    max_bytes: int,
) -> tuple[int, str]:
    """
    Persiste o upload em chunks (sem carregar tudo na memória) E calcula
    SHA-256 incrementalmente. Levanta 413 se exceder max_bytes.

    Retorna (size_bytes, sha256_hex).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    total = 0
    with output_path.open("wb") as out:
        while True:
            chunk = await upload.read(_HASH_READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                output_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"Arquivo excede o limite de {max_bytes // (1024 * 1024)}MB. "
                        "Reduza ou divida em partes menores."
                    ),
                )
            hasher.update(chunk)
            out.write(chunk)
    return total, hasher.hexdigest()


def _evidence_payload(evidence: Evidence | None) -> EvidenceResponse | None:
    if evidence is None:
        return None
    return EvidenceResponse(
        quote=evidence.quote,
        speaker=evidence.speaker,
        timestamp_sec=evidence.start_sec,
    )


def _decision_payload(decision: Decision) -> DecisionItemResponse:
    return DecisionItemResponse(
        id=decision.id,
        description=decision.description,
        evidence=_evidence_payload(decision.evidence),
    )


def _action_item_payload(action: ActionItem) -> ActionItemResponse:
    return ActionItemResponse(
        id=action.id,
        description=action.description,
        assigned_to=action.assigned_to,
        deadline_raw=action.deadline_raw,
        deadline_parsed=action.deadline_parsed,
        priority=action.priority,
        status=action.status,
        evidence=_evidence_payload(action.evidence),
    )


def _minutes_payload(minutes: Minutes | None) -> MinutesResponse | None:
    if minutes is None:
        return None
    return MinutesResponse(
        id=minutes.id,
        title=minutes.title,
        date_extracted=minutes.date_extracted,
        executive_summary=minutes.executive_summary,
        participants=list(minutes.participants or []),
        topics=list(minutes.topics or []),
        open_questions=list(minutes.open_questions or []),
        decisions=[_decision_payload(d) for d in (minutes.decisions or [])],
        action_items=[_action_item_payload(a) for a in (minutes.action_items or [])],
        llm_provider=minutes.llm_provider,
        llm_model=minutes.llm_model,
        tokens_input=minutes.tokens_input,
        tokens_output=minutes.tokens_output,
        cost_usd=float(minutes.cost_usd or 0),
        validation_passed=minutes.validation_passed,
        validation_issues=minutes.validation_issues,
    )


def _transcript_payload(transcript: Transcript | None) -> TranscriptResponse | None:
    if transcript is None:
        return None
    segments = sorted(transcript.segments or [], key=lambda s: s.segment_index)
    return TranscriptResponse(
        id=transcript.id,
        full_text=transcript.full_text,
        language_detected=transcript.language_detected,
        provider_used=transcript.provider_used,
        model_used=transcript.model_used,
        word_count=transcript.word_count,
        segments=[
            TranscriptSegmentResponse(
                start_sec=s.start_sec,
                end_sec=s.end_sec,
                text=s.text,
                speaker_id=s.speaker_id,
                confidence=s.confidence,
            )
            for s in segments
        ],
    )


def _meeting_list_item(meeting: Meeting) -> MeetingListItem:
    return MeetingListItem(
        id=meeting.id,
        title=meeting.title,
        original_filename=meeting.original_filename,
        duration_sec=meeting.duration_sec,
        file_size_bytes=meeting.file_size_bytes,
        language=meeting.language,
        source=meeting.source,
        status=meeting.status,
        created_at=meeting.created_at,
    )


def _meeting_detail(
    meeting: Meeting,
    transcript: Transcript | None,
    minutes: Minutes | None,
) -> MeetingDetailResponse:
    return MeetingDetailResponse(
        id=meeting.id,
        title=meeting.title,
        original_filename=meeting.original_filename,
        audio_path=meeting.audio_path,
        audio_hash=meeting.audio_hash,
        duration_sec=meeting.duration_sec,
        file_size_bytes=meeting.file_size_bytes,
        language=meeting.language,
        source=meeting.source,
        status=meeting.status,
        speaker_map=meeting.speaker_map,
        extra_metadata=meeting.extra_metadata,
        started_at=meeting.started_at,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
        transcript=_transcript_payload(transcript),
        minutes=_minutes_payload(minutes),
    )


async def _load_meeting(db: AsyncSession, meeting_id: str) -> Meeting:
    """Carrega Meeting OU levanta 404. Ignora soft-deleted."""
    meeting = await db.get(Meeting, meeting_id)
    if meeting is None or meeting.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meeting_id!r} não encontrada.",
        )
    return meeting


# ============================================================
# Endpoints
# ============================================================


@router.post(
    "/upload",
    response_model=MeetingCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_meeting(
    db: DbSession,
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(...)],
    title: str | None = None,
    language: str = "pt",
) -> MeetingCreatedResponse:
    """
    Upload de arquivo de áudio/vídeo. Cria a Meeting no DB, persiste o
    arquivo em `~/.eskuta/uploads/`, dispatcha `process_meeting` em
    BackgroundTask (não bloqueia).

    Limites:
    - Tamanho: `settings.MAX_AUDIO_MB` MB (default 500)
    - Extensões: .mp3, .mp4, .m4a, .wav
    """
    ext = _validate_extension(file.filename)
    settings.ensure_dirs()

    # Path final: UUID + extensão original. UUID garante unique +
    # zero risco de path traversal (não usamos o filename do user).
    meeting_id = uuid.uuid4().hex
    output_path = settings.UPLOADS_DIR / f"{meeting_id}{ext}"

    max_bytes = settings.MAX_AUDIO_MB * 1024 * 1024
    size_bytes, audio_hash = await _save_upload_streaming(file, output_path, max_bytes=max_bytes)

    original_filename = _sanitize_filename(file.filename)

    meeting = Meeting(
        id=meeting_id,
        title=title.strip() if title else None,
        original_filename=original_filename,
        audio_path=str(output_path),
        audio_hash=audio_hash,
        file_size_bytes=size_bytes,
        language=language,
        source="upload",
        status="pending",
    )
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)

    background.add_task(process_meeting, meeting.id)
    logger.info(
        "Meeting criada e pipeline agendado",
        meeting_id=meeting.id,
        file_size_mb=round(size_bytes / (1024 * 1024), 2),
        original_filename=original_filename,
    )

    return MeetingCreatedResponse(
        id=meeting.id,
        status=meeting.status,
        title=meeting.title,
        original_filename=original_filename,
        file_size_bytes=size_bytes,
    )


@router.get("", response_model=MeetingListResponse)
async def list_meetings(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MeetingListResponse:
    """
    Lista reuniões (mais recentes primeiro). Soft-deleted são omitidas.
    """
    base = select(Meeting).where(Meeting.deleted_at.is_(None))
    total_q = await db.execute(base)
    total = len(total_q.scalars().all())  # count via materialize — SQLite friendly

    q = base.order_by(Meeting.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(q)).scalars().all()
    return MeetingListResponse(
        meetings=[_meeting_list_item(m) for m in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
async def get_meeting(meeting_id: str, db: DbSession) -> MeetingDetailResponse:
    """
    Detail completo. Eager-loads Transcript (com segments) e Minutes
    (com decisions/action_items/evidences) — uma roundtrip.
    """
    q = (
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(
            selectinload(Meeting.transcript).selectinload(Transcript.segments),
            selectinload(Meeting.minutes)
            .selectinload(Minutes.decisions)
            .selectinload(Decision.evidence),
            selectinload(Meeting.minutes)
            .selectinload(Minutes.action_items)
            .selectinload(ActionItem.evidence),
        )
    )
    meeting = (await db.execute(q)).scalar_one_or_none()
    if meeting is None or meeting.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meeting {meeting_id!r} não encontrada.",
        )
    return _meeting_detail(meeting, meeting.transcript, meeting.minutes)


@router.get("/{meeting_id}/status", response_model=MeetingStatusResponse)
async def get_meeting_status(meeting_id: str, db: DbSession) -> MeetingStatusResponse:
    """
    Endpoint enxuto pra polling de progresso pela UI. Retorna só status
    + erro (se houver) — NÃO inclui transcript/minutes pra ficar barato.
    """
    meeting = await _load_meeting(db, meeting_id)
    extra = meeting.extra_metadata or {}
    return MeetingStatusResponse(
        id=meeting.id,
        status=meeting.status,
        error=extra.get("error"),
        error_type=extra.get("error_type"),
    )


@router.put("/{meeting_id}/speaker-map", response_model=SpeakerMapResponse)
async def update_speaker_map(
    meeting_id: str,
    body: SpeakerMapUpdate,
    db: DbSession,
) -> SpeakerMapResponse:
    """
    Atualiza o `speaker_map` da meeting (Fase 1.5.3 — UI de renomeação).
    Substitui inteiramente o mapa anterior.
    """
    meeting = await _load_meeting(db, meeting_id)
    meeting.speaker_map = dict(body.speaker_map) if body.speaker_map else None
    meeting.updated_at = utcnow()
    await db.commit()
    return SpeakerMapResponse(id=meeting.id, speaker_map=meeting.speaker_map or {})


@router.delete("/{meeting_id}", response_model=DeleteResponse)
async def delete_meeting(meeting_id: str, db: DbSession) -> DeleteResponse:
    """
    Soft delete: preenche `deleted_at`. Não remove o arquivo de áudio
    do disco (cleanup fica pra task separada futura).
    """
    meeting = await _load_meeting(db, meeting_id)
    meeting.deleted_at = utcnow()
    await db.commit()
    return DeleteResponse(id=meeting.id, deleted=True)
