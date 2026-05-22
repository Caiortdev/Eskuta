"""
Testes do pipeline (app.services.minutes.pipeline.process_meeting).

Como o pipeline orquestra 6+ serviços externos (ffmpeg, silero, groq,
pyannote, claude/gpt/gemini), todos são mockados via monkeypatch.
Os testes focam em:
- Status updates em cada estágio
- Regen loop quando validate_minutes falha (até max_attempts)
- mark_failed em qualquer exceção
- session_factory injectability (importante pra testes)
- Diarização opcional (sem HF_TOKEN → skip gracefully)
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import Meeting, Minutes, Transcript
from app.services.audio.chunker import AudioChunk
from app.services.audio.vad import SpeechSegment
from app.services.diarization.pyannote_service import SpeakerSegment
from app.services.llm.base import LLMMessage, LLMProvider, LLMResponse
from app.services.llm.router import LLMRouter
from app.services.minutes.pipeline import process_meeting
from app.services.minutes.prompts import (
    FEW_SHOT_EXAMPLE_MINUTES,
    FEW_SHOT_EXAMPLE_TRANSCRIPT,
)
from app.services.transcription.base import (
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptionSegment,
)
from app.services.transcription.router import TranscriptionRouter

# ============================================================
# Fixtures e helpers
# ============================================================


@pytest.fixture
async def session_factory():
    """SQLite in-memory dedicada — passada via session_factory pro process_meeting."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def meeting_row(session_factory, tmp_path) -> Meeting:
    """Cria Meeting com audio_path apontando pra arquivo vazio em tmp_path."""
    audio_file = tmp_path / "audio.mp3"
    audio_file.write_bytes(b"")
    async with session_factory() as db:
        m = Meeting(
            title="Reunião teste",
            audio_path=str(audio_file),
            audio_hash="abc",
            language="pt",
            source="upload",
            status="pending",
        )
        db.add(m)
        await db.commit()
        await db.refresh(m)
        return m


class _FakeTxProvider(TranscriptionProvider):
    """
    Provider de transcrição fake. Por default devolve o
    `FEW_SHOT_EXAMPLE_TRANSCRIPT` — assim quando o LLM fake devolve o
    `FEW_SHOT_EXAMPLE_MINUTES`, todas as evidences batem e a validação
    passa em primeira tentativa (happy path).
    """

    def __init__(self, *, full_text: str | None = None) -> None:
        self.full_text = full_text or FEW_SHOT_EXAMPLE_TRANSCRIPT

    @property
    def name(self) -> str:
        return "fake-tx"

    def is_available(self) -> bool:
        return True

    async def transcribe(self, audio_path: Path, *, language: str = "pt") -> TranscriptionResult:
        return TranscriptionResult(
            full_text=self.full_text,
            segments=[
                TranscriptionSegment(start_sec=0.0, end_sec=2.0, text="primeira parte"),
                TranscriptionSegment(start_sec=2.0, end_sec=3.0, text="segunda parte"),
            ],
            language="pt",
            duration_sec=3.0,
            provider_used="fake-tx",
            model_used="fake-model",
            cost_usd=0.001,
        )


class _FakeLLMProvider(LLMProvider):
    """LLM fake configurável: cada chamada usa próxima resposta da fila."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0

    @property
    def name(self) -> str:
        return "fake-llm"

    @property
    def default_model(self) -> str:
        return "fake-llm-model"

    def is_available(self) -> bool:
        return True

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        if not self.responses:
            raise RuntimeError("FakeLLMProvider sem respostas — caller chamou demais")
        payload = self.responses.pop(0)
        return LLMResponse(
            content=payload,
            provider=self.name,
            model=model or self.default_model,
            tokens_input=1000,
            tokens_output=500,
            cost_usd=0.01,
        )


def _example_minutes_json() -> str:
    return json.dumps(FEW_SHOT_EXAMPLE_MINUTES)


def _patch_audio_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Mocka convert/VAD/chunk pra não tocar em ffmpeg/silero reais."""

    async def fake_convert(input_path, output_path, **kwargs):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"fake-mp3")
        return Path(output_path)

    def fake_vad(audio_path, **kwargs):
        return [SpeechSegment(start_sec=0.0, end_sec=3.0)]

    def fake_chunk(audio_path, segments, output_dir, **kwargs):
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        chunk_file = Path(output_dir) / "chunk_000.mp3"
        chunk_file.write_bytes(b"chunk")
        return [
            AudioChunk(
                index=0,
                start_sec=0.0,
                end_sec=3.0,
                segment_count=1,
                file_path=chunk_file,
            )
        ]

    monkeypatch.setattr(
        "app.services.minutes.pipeline.convert_to_optimized_mp3_async", fake_convert
    )
    monkeypatch.setattr("app.services.minutes.pipeline.detect_speech_segments", fake_vad)
    monkeypatch.setattr("app.services.minutes.pipeline.chunk_audio_smart", fake_chunk)


def _patch_settings_processed_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Aponta PROCESSED_DIR pra tmp_path pra não escrever em ~/.eskuta real."""
    monkeypatch.setattr(
        "app.services.minutes.pipeline.settings.APP_DIR",
        tmp_path / "eskuta-app",
    )


def _patch_diarization_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.minutes.pipeline.diarization_is_available",
        lambda: False,
    )


# ============================================================
# Happy path
# ============================================================


async def test_pipeline_runs_all_stages_and_marks_completed(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    meeting_row,
    tmp_path,
) -> None:
    _patch_audio_pipeline(monkeypatch, tmp_path)
    _patch_settings_processed_dir(monkeypatch, tmp_path)
    _patch_diarization_unavailable(monkeypatch)

    tx_router = TranscriptionRouter([_FakeTxProvider()])
    # Tudo OK na primeira tentativa
    llm_router = LLMRouter({"fake": _FakeLLMProvider([_example_minutes_json()])})

    await process_meeting(
        meeting_row.id,
        session_factory=session_factory,
        transcription_router=tx_router,
        llm_router=llm_router,
    )

    async with session_factory() as db:
        m = await db.get(Meeting, meeting_row.id)
        assert m.status == "completed"

        # Transcript + Minutes persistidos
        transcript = (await db.execute(select(Transcript))).scalar_one()
        assert transcript.meeting_id == meeting_row.id
        assert transcript.provider_used == "fake-tx"

        minutes = (await db.execute(select(Minutes))).scalar_one()
        assert minutes.title == "Alinhamento Projeto Alpha e Orçamento Design"
        assert minutes.llm_provider == "fake-llm"
        assert minutes.validation_passed is True


async def test_pipeline_diarization_runs_when_available(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    meeting_row,
    tmp_path,
) -> None:
    _patch_audio_pipeline(monkeypatch, tmp_path)
    _patch_settings_processed_dir(monkeypatch, tmp_path)

    # Diarização disponível e devolve 1 speaker_segment
    monkeypatch.setattr(
        "app.services.minutes.pipeline.diarization_is_available",
        lambda: True,
    )

    def fake_diarize(audio_path):
        return [SpeakerSegment(start_sec=0.0, end_sec=3.0, speaker_id="SPEAKER_00")]

    monkeypatch.setattr("app.services.minutes.pipeline.diarize", fake_diarize)

    tx_router = TranscriptionRouter([_FakeTxProvider()])
    llm_router = LLMRouter({"fake": _FakeLLMProvider([_example_minutes_json()])})

    await process_meeting(
        meeting_row.id,
        session_factory=session_factory,
        transcription_router=tx_router,
        llm_router=llm_router,
    )

    async with session_factory() as db:
        m = await db.get(Meeting, meeting_row.id)
        assert m.status == "completed"


async def test_pipeline_diarization_failure_does_not_stop(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    meeting_row,
    tmp_path,
) -> None:
    """Se diarização explodir, pipeline segue sem speaker labels."""
    _patch_audio_pipeline(monkeypatch, tmp_path)
    _patch_settings_processed_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.minutes.pipeline.diarization_is_available",
        lambda: True,
    )

    def boom(audio_path):
        raise RuntimeError("pyannote down")

    monkeypatch.setattr("app.services.minutes.pipeline.diarize", boom)

    tx_router = TranscriptionRouter([_FakeTxProvider()])
    llm_router = LLMRouter({"fake": _FakeLLMProvider([_example_minutes_json()])})

    await process_meeting(
        meeting_row.id,
        session_factory=session_factory,
        transcription_router=tx_router,
        llm_router=llm_router,
    )

    async with session_factory() as db:
        m = await db.get(Meeting, meeting_row.id)
        assert m.status == "completed"  # apesar do erro na diarização


# ============================================================
# Regen loop
# ============================================================


async def test_pipeline_regenerates_when_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    meeting_row,
    tmp_path,
) -> None:
    """
    Primeira ata tem quote inventada → validate falha → regen.
    Segunda ata é o exemplo válido. Pipeline deve persistir a segunda.
    """
    _patch_audio_pipeline(monkeypatch, tmp_path)
    _patch_settings_processed_dir(monkeypatch, tmp_path)
    _patch_diarization_unavailable(monkeypatch)

    # Transcript do TX fake é "olá tudo bem maria"
    # Primeira ata: cita "quote inventada que não está no transcript" → falha
    # Segunda ata: cita "olá tudo bem" → válida
    # TX devolve um transcript com a frase "olá tudo bem maria"
    custom_transcript = "olá tudo bem maria"
    invalid_payload = json.dumps(
        {
            "title": "Reunião X",
            "executive_summary": "Resumo",
            "action_items": [
                {
                    "description": "Fazer Y",
                    "evidence": {"quote": "essa frase não existe no transcript"},
                }
            ],
        }
    )
    valid_payload = json.dumps(
        {
            "title": "Reunião X",
            "executive_summary": "Resumo",
            "action_items": [
                {
                    "description": "Fazer Y",
                    "evidence": {"quote": "olá tudo bem"},
                }
            ],
        }
    )
    fake_llm = _FakeLLMProvider([invalid_payload, valid_payload])
    llm_router = LLMRouter({"fake": fake_llm})
    tx_router = TranscriptionRouter([_FakeTxProvider(full_text=custom_transcript)])

    await process_meeting(
        meeting_row.id,
        session_factory=session_factory,
        transcription_router=tx_router,
        llm_router=llm_router,
    )

    async with session_factory() as db:
        m = await db.get(Meeting, meeting_row.id)
        assert m.status == "completed"
        minutes = (await db.execute(select(Minutes))).scalar_one()
        assert minutes.validation_passed is True

    # 2 chamadas ao LLM: 1 gera, 1 regera
    assert fake_llm.call_count == 2


async def test_pipeline_persists_with_warnings_after_max_regens(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    meeting_row,
    tmp_path,
) -> None:
    """
    Mesmo após max_regen_attempts, ata é persistida com
    validation_passed=False — usuário vê warning, não é bloqueado.
    """
    _patch_audio_pipeline(monkeypatch, tmp_path)
    _patch_settings_processed_dir(monkeypatch, tmp_path)
    _patch_diarization_unavailable(monkeypatch)

    invalid_payload = json.dumps(
        {
            "title": "X",
            "executive_summary": "Y",
            "action_items": [
                {
                    "description": "Z",
                    "evidence": {"quote": "esta frase nunca foi dita"},
                }
            ],
        }
    )
    # 3 chamadas (1 inicial + 2 regens) — todas devolvem inválido
    fake_llm = _FakeLLMProvider([invalid_payload] * 3)
    llm_router = LLMRouter({"fake": fake_llm})
    tx_router = TranscriptionRouter([_FakeTxProvider(full_text="texto qualquer")])

    await process_meeting(
        meeting_row.id,
        session_factory=session_factory,
        transcription_router=tx_router,
        llm_router=llm_router,
        max_regen_attempts=2,
    )

    async with session_factory() as db:
        m = await db.get(Meeting, meeting_row.id)
        assert m.status == "completed"  # COMPLETED mesmo com warnings
        minutes = (await db.execute(select(Minutes))).scalar_one()
        assert minutes.validation_passed is False
        assert minutes.validation_issues is not None
        assert len(minutes.validation_issues) == 1

    assert fake_llm.call_count == 3


# ============================================================
# Falhas / mark_failed
# ============================================================


async def test_pipeline_marks_failed_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    meeting_row,
    tmp_path,
) -> None:
    _patch_audio_pipeline(monkeypatch, tmp_path)
    _patch_settings_processed_dir(monkeypatch, tmp_path)
    _patch_diarization_unavailable(monkeypatch)

    class _AlwaysFailLLM(_FakeLLMProvider):
        async def complete(self, *args, **kwargs):
            raise RuntimeError("LLM API down")

    tx_router = TranscriptionRouter([_FakeTxProvider()])
    llm_router = LLMRouter({"fake": _AlwaysFailLLM([])})

    await process_meeting(
        meeting_row.id,
        session_factory=session_factory,
        transcription_router=tx_router,
        llm_router=llm_router,
    )

    async with session_factory() as db:
        m = await db.get(Meeting, meeting_row.id)
        assert m.status == "failed"
        assert m.extra_metadata is not None
        assert "error" in m.extra_metadata
        assert "LLM API down" in m.extra_metadata["error"]
        assert m.extra_metadata["error_type"] == "RuntimeError"


async def test_pipeline_marks_failed_on_invalid_json_after_max_regens(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    meeting_row,
    tmp_path,
) -> None:
    """
    Se LLM devolve JSON malformado (ValidationError no parse), regen
    tentativa por tentativa — eventualmente cai pra mark_failed se
    parse continuar falhando.

    Note: o regen interno em _validate_and_regen só trata problemas
    DE VALIDAÇÃO DE EVIDÊNCIA (ValidationReport), não erros de parse.
    Parse error sobe direto e a pipeline marca failed.
    """
    _patch_audio_pipeline(monkeypatch, tmp_path)
    _patch_settings_processed_dir(monkeypatch, tmp_path)
    _patch_diarization_unavailable(monkeypatch)

    tx_router = TranscriptionRouter([_FakeTxProvider()])
    llm_router = LLMRouter({"fake": _FakeLLMProvider(["not even json"])})

    await process_meeting(
        meeting_row.id,
        session_factory=session_factory,
        transcription_router=tx_router,
        llm_router=llm_router,
    )

    async with session_factory() as db:
        m = await db.get(Meeting, meeting_row.id)
        assert m.status == "failed"
        assert "error" in (m.extra_metadata or {})


async def test_pipeline_missing_meeting_returns_quietly(
    session_factory,
) -> None:
    """meeting_id inexistente: log error mas não levanta."""
    await process_meeting(
        "id-que-nao-existe",
        session_factory=session_factory,
    )
    # Sem exceção; sem mudança no DB (não tinha meeting pra mudar)


# ============================================================
# Lifecycle do status
# ============================================================


async def test_pipeline_default_session_factory_uses_singleton() -> None:
    """Não passa session_factory — usa AsyncSessionLocal singleton."""
    # Validação só do default — quando meeting_id não existe no singleton,
    # process_meeting loga error e retorna. Não levanta.
    # Singleton aponta pra DB real (settings.DB_PATH); se a tabela não existir,
    # o get() vai dar erro. Pra esse teste só verificamos que o default é o
    # AsyncSessionLocal — não rodamos o pipeline.
    from app.db.database import AsyncSessionLocal
    from app.services.minutes import pipeline as pipeline_module

    assert pipeline_module.AsyncSessionLocal is AsyncSessionLocal


async def test_pipeline_status_updates_persist_across_stages(
    monkeypatch: pytest.MonkeyPatch,
    session_factory,
    meeting_row,
    tmp_path,
) -> None:
    """
    Capturamos status visto em meio do pipeline mockando transcribe pra
    inspecionar o DB durante a transição.
    """
    _patch_audio_pipeline(monkeypatch, tmp_path)
    _patch_settings_processed_dir(monkeypatch, tmp_path)
    _patch_diarization_unavailable(monkeypatch)

    seen_status: list[str] = []

    async def spy_transcribe(audio_path, *, language="pt"):
        # Captura o status visível em outra session enquanto transcribing
        async with session_factory() as db:
            m = await db.get(Meeting, meeting_row.id)
            seen_status.append(m.status)
        return TranscriptionResult(
            full_text="olá",
            segments=[TranscriptionSegment(start_sec=0.0, end_sec=1.0, text="olá")],
            language="pt",
            duration_sec=1.0,
            provider_used="fake-tx",
            model_used="m",
            cost_usd=0.0,
        )

    class _SpyProvider(_FakeTxProvider):
        async def transcribe(self, audio_path, *, language="pt"):
            return await spy_transcribe(audio_path, language=language)

    tx_router = TranscriptionRouter([_SpyProvider()])
    llm_router = LLMRouter({"fake": _FakeLLMProvider([_example_minutes_json()])})

    await process_meeting(
        meeting_row.id,
        session_factory=session_factory,
        transcription_router=tx_router,
        llm_router=llm_router,
    )

    # Visto durante o stage de transcribe
    assert "transcribing" in seen_status
