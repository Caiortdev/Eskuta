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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.logging import setup_logging
from app.core.settings import settings

__version__ = "0.1.0"


def create_app() -> FastAPI:
    """Factory do app FastAPI. Garante logging configurado antes."""
    setup_logging()
    logger.info("Boot do sidecar Eskuta", version=__version__, **settings.safe_summary())

    app = FastAPI(
        title="Eskuta Sidecar",
        version=__version__,
        description=(
            "API local do app Eskuta. Não deve ser exposta na rede pública — "
            "só aceita conexões do frontend Tauri rodando localmente."
        ),
    )

    # CORS restrito às origens do frontend Tauri (dev: vite em :1420;
    # prod: tauri://localhost). IMPORTANTE: nada de "*" em allow_origins
    # por questão de segurança.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://tauri.localhost",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
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
