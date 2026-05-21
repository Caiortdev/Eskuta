"""
Empacota o sidecar Python (FastAPI) em um executável standalone usando
PyInstaller. O binário resultante é consumido pelo Tauri como external
binary (bundle.externalBin no tauri.conf.json).

Saída: src-python/dist/eskuta-sidecar(.exe)

Depois deste script, scripts/build.* renomeia o binário para o target
triple esperado pelo Tauri:
    src-tauri/binaries/eskuta-sidecar-<TARGET_TRIPLE>(.exe)
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).parent
APP_ENTRY = ROOT / "app" / "main.py"

TARGET_NAME = "eskuta-sidecar"
if platform.system() == "Windows":
    TARGET_NAME += ".exe"


def main() -> None:
    if not APP_ENTRY.exists():
        sys.exit(f"app/main.py não encontrado em {APP_ENTRY}")

    PyInstaller.__main__.run(
        [
            str(APP_ENTRY),
            "--name",
            TARGET_NAME,
            "--onefile",
            "--clean",
            "--noconfirm",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(ROOT / "build"),
            "--specpath",
            str(ROOT / "build"),
            # uvicorn precisa desses hidden imports pra rodar empacotado
            "--hidden-import",
            "uvicorn.logging",
            "--hidden-import",
            "uvicorn.lifespan.on",
            "--hidden-import",
            "uvicorn.lifespan.off",
            "--hidden-import",
            "uvicorn.protocols.http.auto",
            "--hidden-import",
            "uvicorn.protocols.http.h11_impl",
            "--hidden-import",
            "uvicorn.protocols.websockets.auto",
            "--hidden-import",
            "uvicorn.protocols.websockets.websockets_impl",
            "--hidden-import",
            "uvicorn.loops.auto",
            "--hidden-import",
            "uvicorn.loops.asyncio",
        ]
    )


if __name__ == "__main__":
    main()
