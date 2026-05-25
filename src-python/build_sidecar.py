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
    # SQLAlchemy + aiosqlite (package separado precisa ser explícito)
    "aiosqlite",
    "aiosqlite.core",
    "aiosqlite.cursor",
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


# Módulos pesados (>1GB no bundle) — excluídos do MVP. O app já tem
# fallback gracioso em is_available() quando esses módulos não carregam.
# Diarização (pyannote/torch/torchaudio) volta na v0.2 quando otimizarmos.
EXCLUDE_MODULES = [
    "torch",
    "torchaudio",
    "torchvision",
    "pyannote",
    "pyannote.audio",
    "pyannote.core",
    "pyannote.metrics",
    "pyannote.pipeline",
    "tensorflow",
    "tensorboard",
    "matplotlib",
    "pytest",
    "evaluation",  # módulo de benchmarks — não precisa em runtime
    # Nota: scipy / pandas / PIL ficam — librosa depende deles em runtime
]


def main() -> None:
    if not APP_ENTRY.exists():
        sys.exit(f"app/main.py não encontrado em {APP_ENTRY}")

    args = [
        str(APP_ENTRY),
        "--name",
        TARGET_NAME,  # sem .exe — PyInstaller adiciona em --onedir
        # --onedir gera dist/eskuta-sidecar/ com .exe + libs ao lado. Start
        # ~3x mais rápido que --onefile (sem extrair 200MB em temp toda vez).
        # Defender também confia mais (não usa o padrão suspeito de
        # auto-extração).
        "--onedir",
        "--clean",
        "--noconfirm",
        # --windowed: subsystem GUI (sem console window). Sidecar ainda
        # tem stdout/stderr (Tauri captura via Stdio::piped), mas nenhuma
        # janela CMD aparece quando o usuário abre o app. Logs persistentes
        # vão pro loguru file (~/.eskuta/logs/) — não dependemos do stdout.
        "--windowed",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
        "--specpath",
        str(ROOT / "build"),
    ]

    # Version info do exe — faz com que o Defender/SmartScreen confie mais.
    # Antivírus desconfia de executáveis SEM company name, version, etc.
    version_file = ROOT / "build" / "version_info.txt"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(
        """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(0, 1, 0, 0),
    prodvers=(0, 1, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Eskuta'),
        StringStruct('FileDescription', 'Eskuta Sidecar - servidor local de transcricao'),
        StringStruct('FileVersion', '0.1.0'),
        StringStruct('InternalName', 'eskuta-sidecar'),
        StringStruct('LegalCopyright', 'MIT License'),
        StringStruct('OriginalFilename', 'eskuta-sidecar.exe'),
        StringStruct('ProductName', 'Eskuta'),
        StringStruct('ProductVersion', '0.1.0'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
    if platform.system() == "Windows":
        args.extend(["--version-file", str(version_file)])

    # Hidden imports
    for mod in HIDDEN_IMPORTS:
        args.extend(["--hidden-import", mod])

    # --collect-all pega TODOS os submódulos + data files dos packages
    # críticos. Mais robusto que listar submódulos manualmente. Use
    # apenas pra packages que sabemos que precisam de coleta agressiva
    # (databases async, SDKs com plugins, alembic).
    COLLECT_ALL = [
        "aiosqlite",
        "sqlalchemy",
        "alembic",
        "keyring",
        "uvicorn",
        "fastapi",
        "starlette",
        "pydantic",
        "pydantic_settings",
        "loguru",
        # imageio_ffmpeg traz ffmpeg.exe estatico — collect-all é
        # CRITICO porque o binario fica em <pkg>/binaries/ffmpeg.exe
        # e precisa ser copiado pro bundle. Sem isso, conversao de
        # audio falha com "ffmpeg not found" em maquina sem ffmpeg.
        "imageio_ffmpeg",
    ]
    for mod in COLLECT_ALL:
        args.extend(["--collect-all", mod])

    # Exclusões — reduz tamanho do bundle drasticamente (de ~2GB pra ~200MB)
    # ao tirar torch + pyannote + libs científicas pesadas que não usamos
    # em runtime do MVP. Diarização opcional já tem fallback em
    # is_available() do app.services.diarization.
    for mod in EXCLUDE_MODULES:
        args.extend(["--exclude-module", mod])

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

    # Sanity: confirma que o binário existe. Em --onedir, PyInstaller gera
    # dist/<name>/<name>.exe (pasta com .exe + _internal/), não dist/<name>.exe.
    output_dir = ROOT / "dist" / TARGET_NAME
    output_exe = output_dir / TARGET_NAME_FILE
    if not output_exe.exists():
        sys.exit(f"[ERROR] Build falhou: {output_exe} nao foi gerado")

    # Tamanho da pasta inteira (--onedir empacota .exe + libs no _internal/)
    total_bytes = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
    size_mb = total_bytes / (1024 * 1024)
    print(f"\n[OK] Sidecar empacotado em: {output_dir}")
    print(f"     Tamanho total: {size_mb:.1f} MB")


def cleanup_build_artifacts() -> None:
    """Remove pastas intermediárias (build/, *.spec). Útil pra rebuild limpo."""
    for path in [ROOT / "build", ROOT / "dist"]:
        if path.exists():
            shutil.rmtree(path)
            print(f"[clean] Removido: {path}")


if __name__ == "__main__":
    if "--clean-only" in sys.argv:
        cleanup_build_artifacts()
        sys.exit(0)
    main()
