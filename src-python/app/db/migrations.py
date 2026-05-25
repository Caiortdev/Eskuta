"""
Runner programático de Alembic migrations.

Roda `alembic upgrade head` ao subir o sidecar, sem precisar do CLI
externo. Crítico em produção (PyInstaller bundle) — caso contrário
o DB fica vazio e qualquer query em `meetings`/`transcripts`/etc
levanta `no such table`.

Resolução do path do alembic.ini:
- DEV: usa `<repo>/src-python/alembic.ini`
- BUNDLE PyInstaller --onedir: sys._MEIPASS aponta pro dir do exe;
  alembic.ini + migrations_alembic/ foram adicionados via --add-data.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def _resolve_alembic_paths() -> tuple[Path, Path]:
    """
    Retorna (alembic_ini_path, migrations_dir).
    Funciona tanto em dev (rodando do venv) quanto empacotado.
    """
    # PyInstaller: sys._MEIPASS = pasta de extração temp (--onefile) ou
    # _internal/ (--onedir). alembic.ini foi copiado pra raiz desse dir.
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        base = Path(bundle_dir)
        ini = base / "alembic.ini"
        migrations = base / "migrations_alembic"
        if ini.exists() and migrations.exists():
            return ini, migrations

    # Dev: relativo ao módulo
    # src-python/app/db/migrations.py → src-python/
    src_python = Path(__file__).resolve().parent.parent.parent
    ini = src_python / "alembic.ini"
    migrations = src_python / "migrations_alembic"
    return ini, migrations


def run_migrations_upgrade_head() -> None:
    """
    Roda `alembic upgrade head` programaticamente. Idempotente —
    se o DB já está atualizado, no-op.

    Raises:
        Exception: se Alembic falhar (DB inacessível, migration quebrada).
    """
    from alembic import command
    from alembic.config import Config

    ini_path, migrations_dir = _resolve_alembic_paths()

    if not ini_path.exists():
        raise FileNotFoundError(f"alembic.ini não encontrado em {ini_path}")
    if not migrations_dir.exists():
        raise FileNotFoundError(f"migrations_alembic/ não encontrado em {migrations_dir}")

    logger.info(
        "Rodando migrations Alembic",
        ini=str(ini_path),
        migrations=str(migrations_dir),
    )

    cfg = Config(str(ini_path))
    # Sobrescreve script_location pra apontar pro path correto (em bundle,
    # ini pode estar com path relativo que não resolve)
    cfg.set_main_option("script_location", str(migrations_dir))

    command.upgrade(cfg, "head")
    logger.info("Migrations aplicadas com sucesso")
