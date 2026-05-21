"""
Eskuta — Sidecar Python (FastAPI)

Backend local empacotado como sidecar do app Tauri. Roda na porta 8765
(configurável via flag --port) e expõe a API que o frontend React consome
via HTTP.

Etapa 0.5 do RELATORIO_TECNICO.md — endpoint /health para smoke test.
Demais rotas serão adicionadas conforme as Fases 1.x.
"""

from __future__ import annotations

import argparse
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

__version__ = "0.1.0"

app = FastAPI(
    title="Eskuta Sidecar",
    version=__version__,
    description=(
        "API local do app Eskuta. Não deve ser exposta na rede pública — "
        "só aceita conexões do frontend Tauri rodando localmente."
    ),
)

# CORS restrito às origens do frontend Tauri (dev: vite em :1420; prod: tauri://localhost).
# IMPORTANTE: nada de "*" em allow_origins por questão de segurança.
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
    return {"status": "ok", "version": __version__}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eskuta sidecar (FastAPI).")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Endereço de escuta (default: 127.0.0.1; nunca expor em 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Porta de escuta (default: 8765).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    # Importante: passamos o objeto `app` direto (não a string "app.main:app").
    # PyInstaller onefile não expõe módulos por import string. Para dev com
    # hot-reload, use `uvicorn app.main:app --reload` direto na linha de comando.
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
