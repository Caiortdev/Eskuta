"""
Cache disco de resultados do VAD (Fase 1.9.5 / Bloco A.3).

Problema atendido: reprocessar uma reunião (ex: usuário regerou ata
mudando LLM) força roda VAD de novo no mesmo áudio com os mesmos
params — desperdício de ~5-10s por hora de áudio.

Solução: cachear o resultado de `detect_speech_segments` em disco
key-ed por (audio_hash, params do VAD). Cache JSON em
`settings.APP_DIR / cache / vad / {key}.json`. TTL default de 30 dias
+ invalidação automática quando params mudam (key inclui hash dos
params, então mismatch força recompute em vez de servir stale).

Decisão de design: o cache é OPT-IN — `detect_speech_segments`
original (sem cache) continua disponível. Caller decide se usa
`detect_speech_segments_cached` ou não. Isso mantém a 1.3 intacta e
facilita comparações de benchmark (com vs sem cache).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Final

from loguru import logger

from app.core.settings import settings
from app.services.audio.vad import (
    DEFAULT_MIN_SILENCE_MS,
    DEFAULT_MIN_SPEECH_MS,
    DEFAULT_THRESHOLD,
    SpeechSegment,
    detect_speech_segments,
)

# TTL default — após 30 dias, recompute. Evita cache crescer
# indefinidamente sem cleanup explícito.
DEFAULT_CACHE_TTL_SEC: Final[int] = 30 * 24 * 60 * 60

# Versão do schema do cache. Se mudarmos o formato no futuro,
# bumpar isso invalida todos os caches antigos automaticamente.
CACHE_SCHEMA_VERSION: Final[int] = 1

# Chunk size pra hashing de áudio (1MB). 4MB são lidos no total p/
# arquivos grandes (head + tail), suficiente pra discriminar áudios
# diferentes sem ler tudo.
_HASH_CHUNK_BYTES: Final[int] = 1024 * 1024


def _audio_fingerprint(audio_path: Path) -> str:
    """
    Fingerprint barato: tamanho + sha256 do primeiro + último 1MB.
    Não é hash criptográfico do arquivo inteiro — ideia é detectar
    "mesmo arquivo" sem ler ~600MB de uma vez.
    """
    stat = audio_path.stat()
    size = stat.st_size
    h = hashlib.sha256()
    h.update(size.to_bytes(8, "big"))
    h.update(str(int(stat.st_mtime)).encode())
    with audio_path.open("rb") as f:
        head = f.read(_HASH_CHUNK_BYTES)
        h.update(head)
        if size > _HASH_CHUNK_BYTES * 2:
            f.seek(-_HASH_CHUNK_BYTES, 2)  # tail
            tail = f.read(_HASH_CHUNK_BYTES)
            h.update(tail)
    return h.hexdigest()[:32]


def _cache_key(
    audio_fp: str,
    *,
    min_speech_ms: int,
    min_silence_ms: int,
    threshold: float,
) -> str:
    """
    Chave determinística que inclui hash dos params — se usuário mudar
    threshold, key muda, cache miss → recompute. Sem stale data.
    """
    params_blob = f"{min_speech_ms}:{min_silence_ms}:{threshold}:{CACHE_SCHEMA_VERSION}"
    params_hash = hashlib.sha256(params_blob.encode()).hexdigest()[:16]
    return f"{audio_fp}__{params_hash}"


def _cache_dir() -> Path:
    """Pasta de cache. Criada lazy."""
    return settings.APP_DIR / "cache" / "vad"


def _serialize_segments(segments: list[SpeechSegment]) -> list[dict]:
    return [{"start_sec": s.start_sec, "end_sec": s.end_sec} for s in segments]


def _deserialize_segments(payload: list[dict]) -> list[SpeechSegment]:
    return [
        SpeechSegment(start_sec=float(s["start_sec"]), end_sec=float(s["end_sec"])) for s in payload
    ]


def _load_from_cache(
    key: str,
    *,
    ttl_sec: int,
) -> list[SpeechSegment] | None:
    """Retorna segments cacheados ou None se cache miss / expirado."""
    cache_file = _cache_dir() / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cache de VAD corrompido, ignorando", file=str(cache_file), error=str(exc))
        return None

    age_sec = time.time() - float(payload.get("cached_at", 0))
    if age_sec >= ttl_sec:
        logger.debug("Cache de VAD expirado", file=str(cache_file), age_sec=round(age_sec, 1))
        return None
    if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
        return None

    return _deserialize_segments(payload.get("segments", []))


def _save_to_cache(
    key: str,
    segments: list[SpeechSegment],
) -> None:
    """Escreve cache de forma atômica (tmp + rename)."""
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.json"
    tmp_file = cache_dir / f"{key}.json.tmp"
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "cached_at": time.time(),
        "segments": _serialize_segments(segments),
    }
    tmp_file.write_text(json.dumps(payload), encoding="utf-8")
    tmp_file.replace(cache_file)  # rename atômico no mesmo filesystem


def detect_speech_segments_cached(
    audio_path: Path,
    *,
    min_speech_duration_ms: int = DEFAULT_MIN_SPEECH_MS,
    min_silence_duration_ms: int = DEFAULT_MIN_SILENCE_MS,
    threshold: float = DEFAULT_THRESHOLD,
    ttl_sec: int = DEFAULT_CACHE_TTL_SEC,
    use_cache: bool = True,
) -> list[SpeechSegment]:
    """
    Wrapper cacheado de `detect_speech_segments`.

    Comportamento:
    - Calcula fingerprint do áudio + hash dos params como key.
    - Se hit + não expirado: retorna cached (rápido).
    - Se miss/expirado: roda VAD real, salva no cache, retorna.
    - `use_cache=False` força recompute (útil pra benchmark / debug).

    O `ttl_sec` default é 30 dias. Não fazemos cleanup automático
    do disco — adicionar `cleanup_expired()` se aparecer pressão de
    espaço (improvável: cada cache JSON tem ~5-20KB).
    """
    if not audio_path.exists():
        raise FileNotFoundError(f"Áudio não encontrado: {audio_path}")

    if use_cache:
        fp = _audio_fingerprint(audio_path)
        key = _cache_key(
            fp,
            min_speech_ms=min_speech_duration_ms,
            min_silence_ms=min_silence_duration_ms,
            threshold=threshold,
        )
        cached = _load_from_cache(key, ttl_sec=ttl_sec)
        if cached is not None:
            logger.info("VAD cache hit", audio=str(audio_path), segments=len(cached))
            return cached

    segments = detect_speech_segments(
        audio_path,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        threshold=threshold,
    )

    if use_cache:
        _save_to_cache(key, segments)
        logger.info("VAD cache write", audio=str(audio_path), segments=len(segments))
    return segments


def cleanup_expired(*, ttl_sec: int = DEFAULT_CACHE_TTL_SEC) -> int:
    """
    Remove caches expirados do disco. Retorna quantos arquivos foram
    removidos. Útil pra rodar periodicamente (ex: scheduled task) ou
    no boot do sidecar.
    """
    cache_dir = _cache_dir()
    if not cache_dir.exists():
        return 0
    removed = 0
    now = time.time()
    for cache_file in cache_dir.glob("*.json"):
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            age = now - float(payload.get("cached_at", 0))
            if age >= ttl_sec:
                cache_file.unlink()
                removed += 1
        except (json.JSONDecodeError, OSError):
            # Cache corrompido — remove também
            cache_file.unlink(missing_ok=True)
            removed += 1
    return removed
