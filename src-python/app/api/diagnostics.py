"""
Endpoint de exportação de logs pra suporte/debug.

GET /api/diagnostics/export-logs

Retorna um ZIP contendo:
- Todos os arquivos `eskuta_*.log` em ~/.eskuta/logs/, MASCARADOS (API keys
  substituídas por placeholders via `app.services.log_masking`)
- `metadata.json` com versão do app, OS, Python version, providers
  configurados (apenas nomes, não valores)

Princípios:
- Nunca inclui o valor real das API keys
- Aplica masking ANTES de zipar (não depois) — se a operação falhar no meio
  do caminho, o arquivo parcial não pode conter segredos
- Limita tamanho total a 50MB pra não estourar memória/disco
"""

from __future__ import annotations

import io
import json
import platform
import sys
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from loguru import logger

from app.core.settings import settings
from app.services import keys as keys_service
from app.services.log_masking import mask_secrets_in_file

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

# Limite hard de tamanho do ZIP final — protege contra colocar 500MB de logs
# acumulados em memória.
_MAX_ZIP_BYTES = 50 * 1024 * 1024


def _collect_metadata() -> dict[str, object]:
    """Metadata do app — sem dados sensíveis."""
    # Import lazy: app.main importa diagnostics, evita circular import
    try:
        from app.main import __version__ as app_version
    except ImportError:
        app_version = "unknown"

    return {
        "app_version": app_version,
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "system": platform.system(),
        # Lista APENAS nomes — has_api_key() retorna bool, nunca o valor
        "providers_configured": keys_service.list_configured_providers(),
        "logs_dir": str(settings.LOGS_DIR),
        "app_dir": str(settings.APP_DIR),
    }


def _build_logs_zip(logs_dir: Path) -> bytes:
    """
    Lê todos os .log do dir, mascarando, e produz ZIP em memória.

    Raises:
        ValueError: se exceder _MAX_ZIP_BYTES após adicionar masked content
    """
    buffer = io.BytesIO()
    total_bytes_in = 0

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1) Metadata primeiro (sempre cabe)
        metadata_json = json.dumps(_collect_metadata(), indent=2, default=str)
        zf.writestr("metadata.json", metadata_json)

        # 2) Logs mascarados
        if logs_dir.exists() and logs_dir.is_dir():
            log_files = sorted(logs_dir.glob("eskuta_*.log"))
            for log_file in log_files:
                try:
                    content = log_file.read_bytes()
                except OSError as exc:
                    logger.warning("Falha lendo log {file}: {err}", file=log_file, err=exc)
                    continue

                total_bytes_in += len(content)
                if total_bytes_in > _MAX_ZIP_BYTES:
                    # Sai sem zipar este arquivo — adiciona um aviso
                    zf.writestr(
                        "TRUNCATED.txt",
                        (
                            "Logs truncados — total excederia "
                            f"{_MAX_ZIP_BYTES} bytes. Os arquivos mais antigos foram omitidos. "
                            "Considere rodar `logger remove + retention` no app."
                        ),
                    )
                    break

                masked = mask_secrets_in_file(content)
                zf.writestr(f"logs/{log_file.name}", masked)
        else:
            zf.writestr("logs/EMPTY.txt", "Diretório de logs não existe ainda.")

    return buffer.getvalue()


@router.get("/export-logs")
async def export_logs() -> StreamingResponse:
    """
    Gera ZIP com logs mascarados + metadata.

    Resposta: application/zip com filename sugerido `eskuta-diagnostics.zip`.
    """
    try:
        zip_bytes = _build_logs_zip(settings.LOGS_DIR)
    except Exception as exc:  # pragma: no cover - falha cataclísmica
        logger.exception("Falha ao gerar ZIP de logs")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao montar export: {exc.__class__.__name__}",
        ) from exc

    logger.info("Logs exportados", size_bytes=len(zip_bytes))

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="eskuta-diagnostics.zip"',
            "Content-Length": str(len(zip_bytes)),
        },
    )
