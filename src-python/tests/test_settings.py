"""Testes do módulo de configuração (app.core.settings)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.settings import Settings


def test_defaults_paths_under_home() -> None:
    s = Settings()
    home = Path.home()
    assert home / ".eskuta" == s.APP_DIR
    assert home / ".eskuta" / "eskuta.db" == s.DB_PATH
    assert home / ".eskuta" / "uploads" == s.UPLOADS_DIR
    assert home / ".eskuta" / "processed" == s.PROCESSED_DIR
    assert home / ".eskuta" / "logs" == s.LOGS_DIR


def test_default_preferences() -> None:
    s = Settings()
    assert s.PREFERRED_LLM == "claude"
    assert s.PREFERRED_STT == "groq"
    assert s.MINUTE_LANGUAGE == "pt-BR"


def test_default_limits() -> None:
    s = Settings()
    assert s.MAX_AUDIO_MB == 5120  # 5 GB — cobre reuniões longas (1-3h)
    assert s.CHUNK_DURATION_SEC == 600
    # Fase 1.13/C4: 4 → 6. Groq pago aguenta 100+ req/min; AssemblyAI ainda
    # mais. Em free tier, o 429 + retry com backoff segura o lado do provider.
    assert s.MAX_PARALLEL_CHUNKS == 6


def test_default_host_is_loopback() -> None:
    """Bind nunca pode ser default em 0.0.0.0 — só localhost."""
    s = Settings()
    assert s.HOST == "127.0.0.1"


def test_env_prefix_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ESKUTA_PREFERRED_LLM", "gpt")
    monkeypatch.setenv("ESKUTA_MAX_AUDIO_MB", "1024")
    s = Settings()
    assert s.PREFERRED_LLM == "gpt"
    assert s.MAX_AUDIO_MB == 1024


def test_invalid_preferred_llm_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ESKUTA_PREFERRED_LLM", "wat")
    with pytest.raises(ValueError):
        Settings()


def test_ensure_dirs_creates_all(tmp_path: Path) -> None:
    s = Settings(APP_DIR=tmp_path / "eskuta-test")
    assert not s.APP_DIR.exists()
    s.ensure_dirs()
    for p in (s.APP_DIR, s.UPLOADS_DIR, s.PROCESSED_DIR, s.LOGS_DIR, s.RECORDINGS_DIR):
        assert p.is_dir()


def test_ensure_dirs_is_idempotent(tmp_path: Path) -> None:
    s = Settings(APP_DIR=tmp_path / "eskuta-test")
    s.ensure_dirs()
    s.ensure_dirs()  # segunda chamada — não pode lançar
    assert s.UPLOADS_DIR.exists()


def test_is_production_and_test_flags() -> None:
    assert not Settings(ENVIRONMENT="development").is_production
    assert not Settings(ENVIRONMENT="development").is_test
    assert Settings(ENVIRONMENT="production").is_production
    assert Settings(ENVIRONMENT="test").is_test


def test_safe_summary_masks_home_path() -> None:
    s = Settings()
    summary = s.safe_summary()
    home_str = str(Path.home())
    # O path no summary é "~/..." (sem o nome real do usuário)
    assert home_str not in str(summary["app_dir"])
    assert str(summary["app_dir"]).startswith("~")


def test_safe_summary_includes_no_secret_keys() -> None:
    s = Settings()
    summary = s.safe_summary()
    keys = set(summary.keys())
    # nenhuma chave sensível esperada
    forbidden = {"groq_api_key", "anthropic_api_key", "openai_api_key", "api_keys"}
    assert forbidden.isdisjoint(keys)
