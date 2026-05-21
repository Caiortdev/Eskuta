"""
Setup do logging do sidecar Eskuta — Loguru com rotação de arquivo.

Dois handlers:
  - stderr (colorido, level INFO por default) para dev
  - arquivo em ~/.eskuta/logs/eskuta_{time}.log (level DEBUG por default,
    rotation 50MB, retention 14 dias, thread-safe)

Também redireciona o stdlib `logging` (uvicorn, fastapi, starlette,
httpx, etc) pra mesma pilha de saída do loguru via InterceptHandler.

Uso:

    from app.core.logging import setup_logging
    from loguru import logger

    setup_logging()
    logger.info("app subiu", port=8765)
"""

from __future__ import annotations

import inspect
import logging
import sys

from loguru import logger

from app.core.settings import settings

# Loggers do ecossistema que devem ser redirecionados pro loguru
_INTERCEPTED_LOGGERS = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "uvicorn.asgi",
    "fastapi",
    "starlette",
    "starlette.access",
    "httpx",
    "httpcore",
    "sqlalchemy.engine",
    "alembic",
)

_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


class InterceptHandler(logging.Handler):
    """Ponte do stdlib logging pro loguru. Preserva nível, mensagem e exc_info."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - I/O
        # Mapeia nível stdlib -> nome do loguru
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Sobe a stack até sair do módulo logging — pra que loguru
        # reporte o file/line do CHAMADOR real, não do próprio logging
        frame = inspect.currentframe()
        depth = 0
        while frame and (
            frame.f_code.co_filename == logging.__file__
            or frame.f_code.co_filename.endswith("logging\\__init__.py")
        ):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


_already_configured = False


def setup_logging(*, force: bool = False) -> None:
    """
    Configura loguru e o stdlib logging. Idempotente — pode ser chamado
    múltiplas vezes (subsequentes são no-op a menos que `force=True`).
    """
    global _already_configured
    if _already_configured and not force:
        return

    settings.ensure_dirs()

    # Limpa handlers padrão do loguru
    logger.remove()

    # 1) Handler de console (stderr, colorido)
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL_CONSOLE,
        format=_LOG_FORMAT,
        colorize=True,
        enqueue=False,  # console: sincrono pra não atrasar boot/erros
        backtrace=True,
        diagnose=settings.ENVIRONMENT != "production",  # diagnose vaza variáveis locais
    )

    # 2) Handler de arquivo (rotativo)
    log_path = settings.LOGS_DIR / "eskuta_{time:YYYY-MM-DD_HHmmss}.log"
    logger.add(
        str(log_path),
        level=settings.LOG_LEVEL_FILE,
        format=_LOG_FORMAT,
        rotation=settings.LOG_FILE_ROTATION,
        retention=settings.LOG_FILE_RETENTION,
        encoding="utf-8",
        # enqueue=True usa thread separada pra escrita (não bloqueia).
        # Desligamos em testes pra que o teardown do tmp_path não esbarre
        # em handle aberto no Windows.
        enqueue=not settings.is_test,
        backtrace=True,
        diagnose=False,  # NUNCA diagnose em arquivo (pode vazar segredos)
    )

    # 3) Intercepta stdlib logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in _INTERCEPTED_LOGGERS:
        std_logger = logging.getLogger(name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False

    _already_configured = True


def reset_logging() -> None:
    """Reseta o estado interno do setup. Útil pra testes."""
    global _already_configured
    _already_configured = False
    logger.remove()
