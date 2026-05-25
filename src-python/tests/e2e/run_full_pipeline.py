"""
Suite E2E: roda o pipeline completo (upload simulado -> ata) com um
áudio/vídeo REAL do usuário e valida cada estágio.

IMPORTANTE: este script roda no console Windows (cp1252) — não usar
caracteres Unicode não-ASCII em mensagens de log/print, senão estoura
UnicodeEncodeError. Usar '->' em vez de '→', '...' em vez de '…', etc.

Uso:
    cd src-python
    .\\venv\\Scripts\\python.exe tests\\e2e\\run_full_pipeline.py \\
        "C:\\Users\\caior\\Downloads\\2026-05-08 15-48-29.mp4"

Critérios de sucesso:
- Stage 1 (convert) — gera MP3 otimizado
- Stage 2 (VAD) — detecta pelo menos 1 segment
- Stage 3 (chunking) — extrai pelo menos 1 chunk
- Stage 4 (transcribe) — full_text não vazio
- Stage 5 (diarize) — se HF_TOKEN: pelo menos 1 speaker segment;
  sem HF_TOKEN, skip OK
- Stage 6 (minutes) — MinutesOutput válido com title + executive_summary
- Stage 7 (validate) — report devolvido (passou ou falhou com problems)
- Stage 8 (persist) — status final = "completed"

Sai com exit code 0 se TODOS os criterios passarem. Senão imprime o
estagio onde falhou + traceback + log tail e exit code 1.

Pré-requisitos:
- Pelo menos 1 STT key (groq OU assemblyai) no keyring
- Pelo menos 1 LLM key (anthropic / openai / google) no keyring
- HF_TOKEN no .env é opcional (sem ele, diarização é skipada)
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.settings import settings  # noqa: E402
from app.db.database import AsyncSessionLocal  # noqa: E402
from app.db.migrations import run_migrations_upgrade_head  # noqa: E402
from app.models import Meeting, Minutes, Transcript  # noqa: E402
from app.services import keys as keys_service  # noqa: E402
from app.services.minutes.pipeline import process_meeting  # noqa: E402

# Cores ANSI básicas — só usadas se stdout é TTY (em CI desabilita).
USE_COLOR = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def green(t: str) -> str:
    return _c(t, "32")


def red(t: str) -> str:
    return _c(t, "31")


def yellow(t: str) -> str:
    return _c(t, "33")


def cyan(t: str) -> str:
    return _c(t, "36")


def bold(t: str) -> str:
    return _c(t, "1")


# ============================================================
# Pré-flight: validar dependências de API keys
# ============================================================


def preflight() -> tuple[list[str], list[str]]:
    """
    Retorna (stt_providers, llm_providers) configurados. Sai com 1 se
    faltar STT ou LLM.
    """
    print(bold(cyan("\n=== PREFLIGHT ===")))

    configured = keys_service.list_configured_providers()
    for provider, ok in configured.items():
        flag = green("OK") if ok else red("FALTA")
        print(f"  [{flag}] {provider}")

    stt = [p for p in ("groq", "assemblyai") if configured.get(p)]
    llm = [p for p in ("anthropic", "openai", "google") if configured.get(p)]

    if not stt:
        print(red("\nERRO: nenhum STT (groq/assemblyai) configurado."))
        print("Configure no app: Configuracoes -> API Keys -> Groq ou AssemblyAI")
        sys.exit(1)
    if not llm:
        print(red("\nERRO: nenhum LLM (anthropic/openai/google) configurado."))
        sys.exit(1)

    hf = bool(settings.HF_TOKEN)
    print(
        f"\n  HF_TOKEN (diarização): {green('OK') if hf else yellow('AUSENTE — diarização será skipada')}"
    )
    print(f"  PREFERRED_STT: {settings.PREFERRED_STT}")
    print(f"  PREFERRED_LLM: {settings.PREFERRED_LLM}")

    # Auto-ajuste: se PREFERRED_LLM não estiver configurado, troca pra
    # primeiro LLM disponível (senão o router vai falhar).
    if settings.PREFERRED_LLM not in llm:
        new_pref = llm[0]
        print(
            yellow(
                f"  ! PREFERRED_LLM '{settings.PREFERRED_LLM}' sem key — usando '{new_pref}' pra esse run"
            )
        )
        settings.PREFERRED_LLM = new_pref  # type: ignore[assignment]
    if settings.PREFERRED_STT not in stt:
        new_pref = stt[0]
        print(
            yellow(
                f"  ! PREFERRED_STT '{settings.PREFERRED_STT}' sem key — usando '{new_pref}' pra esse run"
            )
        )
        settings.PREFERRED_STT = new_pref  # type: ignore[assignment]

    return stt, llm


# ============================================================
# Setup: copia o vídeo pro uploads dir + cria Meeting no DB
# ============================================================


async def create_meeting(input_path: Path) -> str:
    """Cria Meeting record com o arquivo copiado pra uploads_dir."""
    if not input_path.exists():
        print(red(f"ERRO: arquivo não encontrado: {input_path}"))
        sys.exit(1)

    settings.ensure_dirs()
    run_migrations_upgrade_head()

    import hashlib
    import uuid

    meeting_id = uuid.uuid4().hex
    ext = input_path.suffix.lower()
    dest = settings.UPLOADS_DIR / f"{meeting_id}{ext}"
    print(bold(cyan("\n=== SETUP ===")))
    size_bytes = input_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    print(f"  Arquivo de entrada: {input_path.name} ({size_mb:.1f} MB)")
    print(f"  Copiando + calculando SHA-256: {dest}")

    # Copy + hash em streaming pra não carregar 700MB na RAM
    hasher = hashlib.sha256()
    t0 = time.monotonic()
    with input_path.open("rb") as src, dest.open("wb") as out:
        while True:
            chunk = src.read(4 * 1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            out.write(chunk)
    audio_hash = hasher.hexdigest()
    print(f"  Copy+hash levou {time.monotonic() - t0:.1f}s, sha256={audio_hash[:12]}...")

    async with AsyncSessionLocal() as db:
        m = Meeting(
            id=meeting_id,
            title=f"[E2E TEST] {input_path.name}",
            original_filename=input_path.name,
            audio_path=str(dest),
            audio_hash=audio_hash,
            file_size_bytes=size_bytes,
            status="pending",
            language="pt-BR",
            source="upload",
        )
        db.add(m)
        await db.commit()
    print(f"  Meeting criada: {meeting_id}")
    return meeting_id


# ============================================================
# Polling: acompanha status enquanto pipeline roda
# ============================================================


async def watch_progress(meeting_id: str, interval_sec: float = 2.0) -> None:
    """
    Roda em paralelo com process_meeting; imprime cada mudança de status
    com timestamp relativo. Termina quando status entrar em completed/failed.
    """
    started = time.monotonic()
    last_status = None
    terminal = {"completed", "failed"}
    while True:
        await asyncio.sleep(interval_sec)
        async with AsyncSessionLocal() as db:
            m = await db.get(Meeting, meeting_id)
            if m is None:
                print(red("Meeting sumiu do DB"))
                return
            if m.status != last_status:
                elapsed = time.monotonic() - started
                color = (
                    green if m.status == "completed" else (red if m.status == "failed" else cyan)
                )
                print(f"  [{elapsed:6.1f}s] status -> {color(m.status)}")
                last_status = m.status
            if m.status in terminal:
                return


# ============================================================
# Validação dos artefatos finais
# ============================================================


def _section(title: str) -> None:
    print(bold(cyan(f"\n=== {title} ===")))


async def validate_artifacts(meeting_id: str) -> dict[str, Any]:
    """Inspeciona Meeting + Transcript + Minutes no DB. Retorna resumo."""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Meeting)
            .options(
                selectinload(Meeting.transcript).selectinload(Transcript.segments),
                selectinload(Meeting.minutes).selectinload(Minutes.decisions),
                selectinload(Meeting.minutes).selectinload(Minutes.action_items),
            )
            .where(Meeting.id == meeting_id)
        )
        m = (await db.execute(stmt)).scalar_one_or_none()
        if m is None:
            return {"ok": False, "where": "load", "error": "Meeting sumiu"}

        summary: dict[str, Any] = {
            "ok": False,
            "status": m.status,
            "extra_metadata": m.extra_metadata,
        }

        if m.status != "completed":
            return {**summary, "where": "status", "error": f"status={m.status}"}

        tr: Transcript | None = m.transcript
        if tr is None or not tr.full_text or not tr.full_text.strip():
            return {**summary, "where": "transcript", "error": "transcript vazio"}
        segments = list(tr.segments or [])
        summary["transcript_chars"] = len(tr.full_text)
        summary["transcript_segments"] = len(segments)
        summary["provider"] = tr.provider_used
        summary["model_stt"] = tr.model_used

        # Diarização: speaker_id em TranscriptSegment (ORM objects, não dicts)
        unique_speakers = {s.speaker_id for s in segments if s.speaker_id}
        summary["unique_speakers"] = sorted(unique_speakers)

        mn: Minutes | None = m.minutes
        if mn is None:
            return {**summary, "where": "minutes", "error": "minutes não persistido"}

        # Validações de schema mínimas
        if not mn.title or not mn.title.strip():
            return {**summary, "where": "minutes.title", "error": "title vazio"}
        if not mn.executive_summary or not mn.executive_summary.strip():
            return {**summary, "where": "minutes.executive_summary", "error": "summary vazio"}

        summary["minutes_title"] = mn.title
        summary["minutes_summary"] = mn.executive_summary[:500]
        summary["decisions_n"] = len(mn.decisions or [])
        summary["action_items_n"] = len(mn.action_items or [])
        summary["topics_n"] = len(mn.topics or [])
        summary["llm_model"] = mn.llm_model
        summary["validation_passed"] = mn.validation_passed
        summary["validation_problems"] = mn.validation_issues or []

        summary["ok"] = True
        return summary


def print_summary(summary: dict[str, Any]) -> None:
    _section("RESULTADO")
    if not summary.get("ok"):
        print(red(f"  FALHOU em: {summary.get('where')}"))
        print(red(f"  Erro: {summary.get('error')}"))
        if summary.get("extra_metadata"):
            print(f"  meta: {summary['extra_metadata']}")
        return

    print(green("  PIPELINE COMPLETO\n"))
    print(f"  {bold('Status final:')} {green(summary['status'])}")
    print(
        f"  {bold('Transcrição:')} {summary['transcript_chars']:,} chars, "
        f"{summary['transcript_segments']} segments, provider={summary['provider']}, model={summary['model_stt']}"
    )
    if summary["unique_speakers"]:
        print(f"  {bold('Speakers identificados:')} {', '.join(summary['unique_speakers'])}")
    else:
        print(f"  {bold('Speakers:')} sem diarização (HF_TOKEN ausente ou diarização falhou)")
    print()
    print(f"  {bold('Ata gerada:')}")
    print(f"    Título: {summary['minutes_title']}")
    print(f"    Modelo LLM: {summary['llm_model']}")
    print(
        f"    Tópicos: {summary['topics_n']} | Decisões: {summary['decisions_n']} | "
        f"Ações: {summary['action_items_n']}"
    )
    print(
        f"    Validação: {green('PASSOU') if summary['validation_passed'] else yellow('com avisos')}"
    )
    if summary["validation_problems"]:
        print(f"    Problems: {len(summary['validation_problems'])}")
        for p in summary["validation_problems"][:3]:
            print(f"      - {p}")
    print()
    print(f"  {bold('Executive summary:')}")
    for line in summary["minutes_summary"].split("\n"):
        print(f"    {line}")


# ============================================================
# Main
# ============================================================


async def amain(input_path: Path) -> int:
    print(bold(cyan(f"\n=== E2E TEST: {input_path.name} ===")))
    preflight()
    meeting_id = await create_meeting(input_path)

    _section("PIPELINE")
    print(f"  Disparando process_meeting({meeting_id[:8]}...)")
    t0 = time.monotonic()

    progress = asyncio.create_task(watch_progress(meeting_id))
    try:
        await process_meeting(meeting_id)
    finally:
        progress.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await progress

    elapsed = time.monotonic() - t0
    print(f"\n  Pipeline finalizou em {elapsed:.1f}s ({elapsed / 60:.1f} min)")

    summary = await validate_artifacts(meeting_id)
    print_summary(summary)

    return 0 if summary.get("ok") else 1


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python tests/e2e/run_full_pipeline.py <caminho_video>")
        sys.exit(2)
    input_path = Path(sys.argv[1])

    # Sinaliza pro código que tá em e2e (poderia usar pra deep debug)
    os.environ.setdefault("ESKUTA_E2E_RUN", "1")

    try:
        rc = asyncio.run(amain(input_path))
    except KeyboardInterrupt:
        print(red("\n[INTERROMPIDO]"))
        sys.exit(130)
    except Exception:
        print(red("\n[CRASH NÃO TRATADO]"))
        traceback.print_exc()
        sys.exit(1)
    sys.exit(rc)


if __name__ == "__main__":
    main()
