"""
Empacota o sidecar Python (FastAPI) em um executável standalone usando
PyInstaller. O binário resultante é consumido pelo Tauri como external
binary (bundle.externalBin no tauri.conf.json).

Saída: src-python/dist/eskuta-sidecar(.exe)

Depois deste script, scripts/build.* renomeia o binário para o target
triple esperado pelo Tauri:
    src-tauri/binaries/eskuta-sidecar-<TARGET_TRIPLE>(.exe)

Como rodar:
    cd src-python
    venv/Scripts/activate   # ou source venv/bin/activate
    pip install -r requirements-build.txt
    python build_sidecar.py
"""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).parent
APP_ENTRY = ROOT / "app" / "main.py"
ALEMBIC_INI = ROOT / "alembic.ini"
MIGRATIONS_DIR = ROOT / "migrations_alembic"

TARGET_NAME = "eskuta-sidecar"
TARGET_NAME_FILE = f"{TARGET_NAME}.exe" if platform.system() == "Windows" else TARGET_NAME


# Hidden imports que PyInstaller não consegue descobrir sozinho via análise
# estática. Esses módulos são importados dinamicamente (uvicorn carrega
# protocolos por nome, keyring resolve backend em runtime, alembic carrega
# revisions por filesystem, etc).
HIDDEN_IMPORTS = [
    # uvicorn — server HTTP
    "uvicorn.logging",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    # keyring — backends por plataforma
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
    "keyring.backends.fail",
    # SQLAlchemy + aiosqlite
    "sqlalchemy.dialects.sqlite.aiosqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    # Alembic — carrega env.py + revisions dinamicamente
    "alembic.config",
    "alembic.script",
    "alembic.runtime.migration",
    # Pydantic v2 — alguns submódulos importados dinamicamente
    "pydantic.deprecated.decorator",
    # SDKs LLM/STT — clientes async carregam HTTP transports dinamicamente
    "anthropic",
    "openai",
    "groq",
    "google.generativeai",
    # httpx HTTP/2 (caso algum SDK ative)
    "h2",
    # Audio
    "librosa",
    "soundfile",
    "pydub",
]


def main() -> None:
    if not APP_ENTRY.exists():
        sys.exit(f"app/main.py não encontrado em {APP_ENTRY}")

    args = [
        str(APP_ENTRY),
        "--name",
        TARGET_NAME_FILE,
        "--onefile",
        "--clean",
        "--noconfirm",
        "--console",  # Sidecar é um servidor HTTP — precisa de stdout/stderr pra logs
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(ROOT / "build"),
    ]

    # Hidden imports
    for mod in HIDDEN_IMPORTS:
        args.extend(["--hidden-import", mod])

    # Recursos: alembic.ini + pasta de migrations precisam ser empacotados
    # como data files (o sidecar roda alembic upgrade na inicialização).
    if ALEMBIC_INI.exists():
        # Sintaxe: <src>;<dest_in_bundle>  (Windows usa ;, outros usam :)
        sep = ";" if platform.system() == "Windows" else ":"
        args.extend(["--add-data", f"{ALEMBIC_INI}{sep}."])
    if MIGRATIONS_DIR.exists():
        sep = ";" if platform.system() == "Windows" else ":"
        args.extend(["--add-data", f"{MIGRATIONS_DIR}{sep}migrations_alembic"])

    PyInstaller.__main__.run(args)

    # Sanity: confirma que o binário existe
    output = ROOT / "dist" / TARGET_NAME_FILE
    if not output.exists():
        sys.exit(f"❌ Build falhou: {output} não foi gerado")

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"\n✅ Sidecar empacotado: {output}")
    print(f"   Tamanho: {size_mb:.1f} MB")


def cleanup_build_artifacts() -> None:
    """Remove pastas intermediárias (build/, *.spec). Útil pra rebuild limpo."""
    for path in [ROOT / "build", ROOT / "dist"]:
        if path.exists():
            shutil.rmtree(path)
            print(f"🗑️  Removido: {path}")


if __name__ == "__main__":
    if "--clean-only" in sys.argv:
        cleanup_build_artifacts()
        sys.exit(0)
    main()
