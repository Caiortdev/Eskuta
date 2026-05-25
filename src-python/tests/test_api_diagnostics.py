"""Testes do endpoint /api/diagnostics/export-logs."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from app.core.settings import settings


@pytest.fixture
def isolated_app_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Aponta settings.APP_DIR (e logo LOGS_DIR) pra tmp_path durante o teste.
    Evita misturar com logs reais em ~/.eskuta/logs/ na máquina dev.
    """
    monkeypatch.setattr(settings, "APP_DIR", tmp_path)
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    return tmp_path


async def test_export_returns_zip(client, in_memory_keyring, isolated_app_dir) -> None:
    res = await client.get("/api/diagnostics/export-logs")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert "eskuta-diagnostics.zip" in res.headers.get("content-disposition", "")


async def test_export_zip_contains_metadata(client, in_memory_keyring, isolated_app_dir) -> None:
    res = await client.get("/api/diagnostics/export-logs")
    zip_bytes = res.content

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "metadata.json" in names
        metadata = json.loads(zf.read("metadata.json"))

    assert "app_version" in metadata
    assert "python_version" in metadata
    assert "platform" in metadata
    assert "providers_configured" in metadata
    # providers_configured tem apenas booleanos (não chaves)
    for provider, configured in metadata["providers_configured"].items():
        assert provider in ("groq", "assemblyai", "anthropic", "openai", "google")
        assert isinstance(configured, bool)


async def test_export_masks_keys_in_logs(client, in_memory_keyring, isolated_app_dir) -> None:
    """Cria log com chave dentro, exporta, verifica que ZIP NÃO tem a chave."""
    log_file = isolated_app_dir / "logs" / "eskuta_2026-05-22_120000.log"
    log_file.write_text(
        "INFO test gsk_segredo_que_nao_pode_vazar_1234567890\n"
        "INFO call with sk-ant-api03-abc123def456ghi789jkl0mn\n",
        encoding="utf-8",
    )

    res = await client.get("/api/diagnostics/export-logs")
    assert res.status_code == 200

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        log_content = zf.read(f"logs/{log_file.name}").decode("utf-8")

    # A chave NÃO pode aparecer no ZIP
    assert "gsk_segredo" not in log_content
    assert "sk-ant-api03" not in log_content
    assert "abc123def456" not in log_content
    # Placeholders aparecem
    assert "***REDACTED***" in log_content


async def test_export_handles_empty_logs_dir(client, in_memory_keyring, isolated_app_dir) -> None:
    """ZIP é gerado mesmo se não existem logs ainda."""
    res = await client.get("/api/diagnostics/export-logs")
    assert res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        names = zf.namelist()
    assert "metadata.json" in names


async def test_metadata_does_not_leak_actual_keys(
    client, in_memory_keyring, isolated_app_dir
) -> None:
    """Salva uma key no keyring, valida que o ZIP tem o booleano mas não o valor."""
    in_memory_keyring.set_password("eskuta-app", "groq", "SUPER_SECRET_KEY_VALUE_HERE_123456")
    res = await client.get("/api/diagnostics/export-logs")
    assert res.status_code == 200

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        metadata = json.loads(zf.read("metadata.json"))

    # Booleano correto
    assert metadata["providers_configured"]["groq"] is True
    # Valor NÃO aparece em nenhum lugar do JSON
    assert "SUPER_SECRET" not in json.dumps(metadata)
