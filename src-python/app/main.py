"""
Eskuta — Sidecar Python (FastAPI)

Backend local empacotado como sidecar do app Tauri. Roda na porta
configurada em Settings (default 8765 em 127.0.0.1) e expõe a API
que o frontend React consome via HTTP.

Demais rotas serão adicionadas conforme as Fases 1.x.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.diagnostics import router as diagnostics_router
from app.api.keys import router as keys_router
from app.api.meetings import router as meetings_router
from app.api.transcription import router as transcription_router
from app.core.logging import setup_logging
from app.core.settings import settings

__version__ = "0.1.0"

# Rate limiter global: chave = IP do remoto (sempre 127.0.0.1 localhost).
# Defesa contra outros processos locais maliciosos que descubram a porta
# e tentem martelar endpoints (drain credito user, DoS).
# Limites permissivos pro uso normal do app, agressivos contra abuso.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute", "30/second"],
)


def _run_migrations_sync() -> None:
    """
    Roda Alembic upgrade head ANTES do FastAPI subir.

    Importante: Alembic internamente chama `asyncio.run()`. Não pode ser
    invocado de dentro de um event loop (@app.on_event("startup") async).
    Por isso rodamos aqui no create_app() — sync, antes de FastAPI montar
    seus event handlers.
    """
    try:
        from app.db.migrations import run_migrations_upgrade_head

        settings.ensure_dirs()
        run_migrations_upgrade_head()
    except Exception as exc:
        logger.exception(
            "Falha rodando migrations no boot. App pode ter erros de DB.",
            err=str(exc),
        )


def create_app() -> FastAPI:
    """Factory do app FastAPI. Garante logging + migrations + Sentry."""
    setup_logging()

    # Sentry no-op se DSN não setado. Antes de qualquer log/route.
    from app.services.observability import init_sentry_if_configured

    init_sentry_if_configured()

    # Migrations ANTES do FastAPI subir — não pode ser dentro de
    # @app.on_event("startup") porque Alembic usa asyncio.run() interno.
    _run_migrations_sync()

    logger.info("Boot do sidecar Eskuta", version=__version__, **settings.safe_summary())

    app = FastAPI(
        title="Eskuta Sidecar",
        version=__version__,
        description=(
            "API local do app Eskuta. Não deve ser exposta na rede pública — "
            "só aceita conexões do frontend Tauri rodando localmente."
        ),
    )

    # Rate limiter — anexa state ao app + handler customizado
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"Rate limit excedido ({exc.detail}). Espere alguns segundos.",
            },
        )

    # NOTA: SlowAPIMiddleware global desabilitado — exige `request: Request`
    # no signature de TODOS os endpoints (api breaking pra MVP). O limiter
    # continua disponível em app.state.limiter pra uso via decorator em
    # endpoints específicos: @limiter.limit("5/minute") (precisa request param).
    # Rate limiting global volta na v0.2 após refactor dos endpoints.
    # app.add_middleware(SlowAPIMiddleware)

    # CORS — Tauri webview no Windows usa schemes variados
    # (http://tauri.localhost, https://tauri.localhost, tauri://localhost,
    # ou ainda http://localhost com porta aleatória do WebView2). Em vez
    # de listar manualmente (e quebrar como aconteceu), usamos regex
    # cobrindo TODOS os schemes/portas locais. Como o sidecar bind em
    # 127.0.0.1 apenas, nenhuma origem fora da máquina alcança.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r"^(https?|tauri)://"
            r"(localhost|127\.0\.0\.1|tauri\.localhost|asset\.localhost)"
            r"(:\d+)?$"
        ),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Smoke test: retorna ok se o sidecar está vivo."""
        return {
            "status": "ok",
            "version": __version__,
            "environment": settings.ENVIRONMENT,
        }

    @app.get("/health/detailed")
    async def health_detailed() -> dict[str, object]:
        """
        Health check granular — verifica DB writable, disco com espaço,
        keyring acessível, dirs do app existem.

        Retorna 200 sempre, com `status` por componente. Útil pra dashboards
        de suporte (export-logs inclui esse output).
        """
        import shutil

        from app.db.database import create_engine_from_settings
        from app.services import keys as keys_service

        checks: dict[str, dict[str, object]] = {}

        # 1. DB writable
        try:
            engine = create_engine_from_settings()
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            await engine.dispose()
            checks["db"] = {"status": "ok"}
        except Exception as exc:
            checks["db"] = {"status": "error", "error": exc.__class__.__name__}

        # 2. Disco com espaço (>= 1GB livre no APP_DIR)
        try:
            total, used, free = shutil.disk_usage(str(settings.APP_DIR))
            free_mb = free // (1024 * 1024)
            checks["disk"] = {
                "status": "ok" if free_mb >= 1024 else "low",
                "free_mb": free_mb,
            }
        except Exception as exc:
            checks["disk"] = {"status": "error", "error": exc.__class__.__name__}

        # 3. Keyring acessível (não revela valores)
        try:
            _ = keys_service.list_configured_providers()
            checks["keyring"] = {"status": "ok"}
        except Exception as exc:
            checks["keyring"] = {"status": "error", "error": exc.__class__.__name__}

        # 4. Dirs do app existem (logs, uploads)
        checks["dirs"] = {
            "status": "ok",
            "app_dir_exists": settings.APP_DIR.exists(),
            "logs_dir_exists": settings.LOGS_DIR.exists(),
            "uploads_dir_exists": settings.UPLOADS_DIR.exists(),
        }

        # Status geral: ok se todos forem ok/low, error caso contrário
        overall = (
            "ok" if all(c.get("status") in ("ok", "low") for c in checks.values()) else "degraded"
        )

        return {
            "status": overall,
            "version": __version__,
            "checks": checks,
        }

    @app.get("/metrics")
    async def metrics() -> dict[str, object]:
        """Counters em memória (reset a cada restart). Útil pra dashboards locais."""
        from app.services.observability import get_counters

        return {
            "counters": get_counters(),
            "version": __version__,
        }

    app.include_router(keys_router)
    app.include_router(meetings_router)
    app.include_router(transcription_router)
    app.include_router(diagnostics_router)

    # Migrations: roda `alembic upgrade head` no startup. CRÍTICO em
    # produção (PyInstaller bundle) — sem isso, DB fica sem tabelas e
    # qualquer query falha com "no such table".
    @app.on_event("startup")
    async def _run_migrations() -> None:
        try:
            from app.db.migrations import run_migrations_upgrade_head

            settings.ensure_dirs()
            run_migrations_upgrade_head()
        except Exception as exc:
            logger.exception("Falha rodando migrations no startup: {err}", err=exc)
            # Não interrompe o boot — algumas rotas podem funcionar sem DB
            # (ex: /health, /api/keys que usa keyring), e usuário pode
            # exportar logs pra diagnóstico

    # Pre-warm: triggera import dos SDKs lazy no startup (não chama a API,
    # só importa o módulo Python). Primeira request fica ~200-500ms mais
    # rápida por não pagar o import.
    @app.on_event("startup")
    async def _prewarm_sdks() -> None:
        try:
            import importlib

            for mod in ("groq", "anthropic", "openai", "httpx"):
                importlib.import_module(mod)
            logger.debug("SDKs pre-warmed")
        except ImportError as exc:
            # Falha silenciosa — SDKs são opcionais (import lazy só pra paths que usam)
            logger.debug("Pre-warm skipped: {err}", err=exc)

    # Reaper: marca meetings travadas em status intermediário (de sessões
    # anteriores que crasharam) como failed pra não ficarem pra sempre.
    @app.on_event("startup")
    async def _reap_stale_meetings() -> None:
        try:
            from app.db.database import AsyncSessionLocal
            from app.services.reaper import reap_stale_meetings

            async with AsyncSessionLocal() as db:
                n = await reap_stale_meetings(db)
                if n > 0:
                    logger.info("Reaper marcou meetings travadas", count=n)
        except Exception as exc:
            # Reaper falhar não impede o app subir
            logger.warning("Reaper falhou no startup: {err}", err=exc)

    return app


# Instância singleton — usada pelo uvicorn quando rodado como módulo.
app = create_app()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eskuta sidecar (FastAPI).")
    parser.add_argument(
        "--host",
        default=settings.HOST,
        help=f"Endereço de escuta (default: {settings.HOST}; nunca expor em 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.PORT,
        help=f"Porta de escuta (default: {settings.PORT}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    # Passamos o objeto `app` direto (não a string "app.main:app").
    # PyInstaller onefile não expõe módulos por import string. Para dev
    # com hot-reload use `uvicorn app.main:app --reload` direto.
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
