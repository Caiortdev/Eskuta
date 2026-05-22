"""
Configurações centralizadas do sidecar Eskuta.

Tudo lido via Pydantic BaseSettings — defaults sensatos com override
opcional via `.env` (apenas dev). Em produção, API keys vêm do OS
keyring (Etapa 1.11), nunca do filesystem.

Uso:

    from app.core.settings import settings

    print(settings.DB_PATH)
    print(settings.MAX_AUDIO_MB)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralizador de configuração do app. Singleton via `settings` abaixo."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="ESKUTA_",
        extra="ignore",
        case_sensitive=False,
    )

    # ============================================================
    # Paths (todos baixo `~/.eskuta/` por padrão; override por env)
    # ============================================================
    APP_DIR: Path = Path.home() / ".eskuta"
    DB_NAME: str = "eskuta.db"
    UPLOADS_DIR_NAME: str = "uploads"
    PROCESSED_DIR_NAME: str = "processed"
    LOGS_DIR_NAME: str = "logs"
    RECORDINGS_DIR_NAME: str = "recordings"  # áudio bruto da Fase 2

    @property
    def DB_PATH(self) -> Path:
        return self.APP_DIR / self.DB_NAME

    @property
    def UPLOADS_DIR(self) -> Path:
        return self.APP_DIR / self.UPLOADS_DIR_NAME

    @property
    def PROCESSED_DIR(self) -> Path:
        return self.APP_DIR / self.PROCESSED_DIR_NAME

    @property
    def LOGS_DIR(self) -> Path:
        return self.APP_DIR / self.LOGS_DIR_NAME

    @property
    def RECORDINGS_DIR(self) -> Path:
        return self.APP_DIR / self.RECORDINGS_DIR_NAME

    # ============================================================
    # Preferências do usuário (defaults; podem ser sobrescritas pela
    # tabela `user_preferences` em runtime — Etapa 1.x)
    # ============================================================
    PREFERRED_LLM: Literal["claude", "gpt", "gemini"] = "claude"
    PREFERRED_STT: Literal["groq", "assemblyai"] = "groq"
    MINUTE_LANGUAGE: str = "pt-BR"

    # ============================================================
    # Limites operacionais
    # ============================================================
    # Limite de upload em MB. Reuniões de 1-3h em MP3 320kbps dão 200-500MB;
    # WAV/FLAC de 1h chegam a 1GB+; gravações multi-track 2-3h podem passar
    # de 3GB. Limite generoso de 5GB cobre a maioria dos casos reais.
    MAX_AUDIO_MB: int = 5120  # 5 GB
    CHUNK_DURATION_SEC: int = 600  # 10 min por chunk de áudio
    MAX_PARALLEL_CHUNKS: int = 4  # respeita free tier do Groq
    HTTP_TIMEOUT_SEC: int = 60

    # ============================================================
    # Sidecar HTTP
    # ============================================================
    HOST: str = "127.0.0.1"  # NUNCA expor em 0.0.0.0
    PORT: int = 8765

    # ============================================================
    # Tokens APP-level (não user-level — vêm do .env / build secret)
    # ============================================================
    # HF_TOKEN: pra baixar o modelo pyannote/speaker-diarization-3.1
    # (Etapa 1.5). É da configuração do APP, NÃO de cada usuário final.
    # Sem token → diarização desabilita gracefully (transcrição segue
    # funcionando sem identificação de speakers).
    HF_TOKEN: str | None = None

    # ============================================================
    # Observabilidade
    # ============================================================
    LOG_LEVEL_CONSOLE: str = "INFO"
    LOG_LEVEL_FILE: str = "DEBUG"
    LOG_FILE_ROTATION: str = "50 MB"
    LOG_FILE_RETENTION: str = "14 days"

    # ============================================================
    # Ambiente
    # ============================================================
    ENVIRONMENT: Literal["development", "production", "test"] = "development"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_test(self) -> bool:
        return self.ENVIRONMENT == "test"

    def ensure_dirs(self) -> None:
        """Cria todos os diretórios do app sob ~/.eskuta/. Idempotente."""
        for d in (
            self.APP_DIR,
            self.UPLOADS_DIR,
            self.PROCESSED_DIR,
            self.LOGS_DIR,
            self.RECORDINGS_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def safe_summary(self) -> dict[str, object]:
        """
        Snapshot mascarado pra logging de boot. Nunca inclui valores
        sensíveis (API keys, paths absolutos contendo nome do usuário,
        etc — paths são relativos a home se possível).
        """
        try:
            home = str(Path.home())
            app_dir = str(self.APP_DIR)
            display_path = app_dir.replace(home, "~") if app_dir.startswith(home) else app_dir
        except (OSError, RuntimeError):
            display_path = "(home indisponível)"

        return {
            "environment": self.ENVIRONMENT,
            "app_dir": display_path,
            "host": self.HOST,
            "port": self.PORT,
            "preferred_llm": self.PREFERRED_LLM,
            "preferred_stt": self.PREFERRED_STT,
            "max_audio_mb": self.MAX_AUDIO_MB,
            "max_parallel_chunks": self.MAX_PARALLEL_CHUNKS,
        }


def _build_settings() -> Settings:
    # Em runs de teste (pytest), permitimos override do APP_DIR via
    # variável ESKUTA_APP_DIR pra evitar lixar o ~/.eskuta real.
    if "ESKUTA_APP_DIR" in os.environ:
        return Settings(APP_DIR=Path(os.environ["ESKUTA_APP_DIR"]))
    return Settings()


settings = _build_settings()
