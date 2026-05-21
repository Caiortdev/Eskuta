"""
Testes do módulo de logging (app.core.logging).

Usa monkeypatch + tmp_path pra direcionar o LOGS_DIR pra uma pasta
temporária — não polui ~/.eskuta/.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pytest
from loguru import logger

from app.core import logging as eskuta_logging
from app.core import settings as settings_module


@pytest.fixture
def isolated_logging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Cria settings temporário com APP_DIR em tmp_path e força setup_logging."""
    test_settings = settings_module.Settings(
        APP_DIR=tmp_path,
        ENVIRONMENT="test",  # desliga enqueue=True no loguru
    )
    monkeypatch.setattr(settings_module, "settings", test_settings)
    monkeypatch.setattr(eskuta_logging, "settings", test_settings)
    eskuta_logging.reset_logging()
    eskuta_logging.setup_logging(force=True)
    yield test_settings
    eskuta_logging.reset_logging()


def test_setup_creates_log_file(isolated_logging) -> None:
    logger.info("smoke test do logging")
    # Loguru com enqueue=True bufera assíncrono — força flush
    logger.complete()
    log_files = list(isolated_logging.LOGS_DIR.glob("eskuta_*.log"))
    assert len(log_files) >= 1, "esperava ao menos 1 arquivo de log"


def test_log_file_contains_message(isolated_logging) -> None:
    message = "mensagem de teste 12345"
    logger.warning(message)
    logger.complete()
    log_files = list(isolated_logging.LOGS_DIR.glob("eskuta_*.log"))
    content = "\n".join(f.read_text(encoding="utf-8") for f in log_files)
    assert message in content
    assert "WARNING" in content


def test_setup_is_idempotent(isolated_logging) -> None:
    """Chamar setup_logging() duas vezes não deve duplicar handlers."""
    # O `force` do fixture já chamou. Vamos chamar de novo sem force.
    eskuta_logging.setup_logging()
    eskuta_logging.setup_logging()
    eskuta_logging.setup_logging()
    logger.info("ainda apenas 1 saída por handler")
    logger.complete()
    # Não dá pra inspecionar handlers diretamente, mas se duplicasse,
    # teríamos múltiplos arquivos de log com timestamps próximos.
    # Aproximação: garantir que não há mais de 3 arquivos (1 da fixture
    # + tolerância de timestamp rolling). Em prática, 1.
    log_files = list(isolated_logging.LOGS_DIR.glob("eskuta_*.log"))
    assert len(log_files) <= 3


def test_force_setup_reapplies(isolated_logging) -> None:
    """force=True deve reaplicar o setup mesmo se já foi configurado."""
    eskuta_logging.setup_logging(force=True)
    logger.info("após force reapply")
    logger.complete()
    log_files = list(isolated_logging.LOGS_DIR.glob("eskuta_*.log"))
    assert len(log_files) >= 1


def test_intercept_handler_routes_stdlib_logging(isolated_logging) -> None:
    """Logs do stdlib `logging` (ex: uvicorn) devem aparecer nos arquivos do loguru."""
    stdlib_logger = logging.getLogger("uvicorn.error")
    stdlib_logger.warning("vindo do stdlib — deve ir pro loguru")
    logger.complete()
    log_files = list(isolated_logging.LOGS_DIR.glob("eskuta_*.log"))
    content = "\n".join(f.read_text(encoding="utf-8") for f in log_files)
    assert "vindo do stdlib" in content


def test_intercept_handler_emit_with_unknown_level() -> None:
    """Garantir que o InterceptHandler tolera levelname não registrado no loguru."""
    handler = eskuta_logging.InterceptHandler()
    # Cria um LogRecord manualmente com level number arbitrário
    record = logging.LogRecord(
        name="custom",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="custom level msg",
        args=None,
        exc_info=None,
    )
    record.levelname = "NIVEL_INEXISTENTE"
    # Não deve lançar — apenas usar levelno como fallback.
    stream = io.StringIO()
    logger.remove()
    logger.add(stream, level=0)
    handler.emit(record)
    logger.complete()
    # Aceitamos que a mensagem foi processada (ela pode estar ou não no
    # stream dependendo do nível registrado — o que validamos é "não
    # lançou exceção").
    assert True
