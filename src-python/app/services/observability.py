"""
Observabilidade do sidecar — Sentry (opt-in) + counters básicos.

Sentry: NUNCA enviado por default. Só ativa se a variável de ambiente
`ESKUTA_SENTRY_DSN` está setada (usuário tem que explicitamente
colocar lá). SDK em modo no-op caso contrário.

Counters: dict em memória contando uploads, transcrições, errors, etc.
Resetam a cada restart do sidecar. Pra dashboards externos, push pra
Prometheus depois (fora do MVP).
"""

from __future__ import annotations

import os
from collections import defaultdict
from threading import Lock

from loguru import logger

_counters: dict[str, int] = defaultdict(int)
_lock = Lock()


def incr(name: str, by: int = 1) -> None:
    """Incrementa um counter — thread-safe."""
    with _lock:
        _counters[name] += by


def get_counters() -> dict[str, int]:
    """Snapshot dos counters. Cópia defensiva."""
    with _lock:
        return dict(_counters)


def reset_counters() -> None:
    """Reset (útil pra testes)."""
    with _lock:
        _counters.clear()


# ============================================================
# Sentry (opt-in)
# ============================================================


_SENTRY_INITIALIZED = False


def init_sentry_if_configured() -> bool:
    """
    Inicializa Sentry SE a env var ESKUTA_SENTRY_DSN está setada.
    Retorna True se inicializou, False se ficou desligado.

    Idempotente — chamadas subsequentes são no-op.
    """
    global _SENTRY_INITIALIZED
    if _SENTRY_INITIALIZED:
        return True

    dsn = os.environ.get("ESKUTA_SENTRY_DSN", "").strip()
    if not dsn:
        logger.debug("Sentry desativado (ESKUTA_SENTRY_DSN não setado)")
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            # Apenas erros + 10% de traces. Privacy-first.
            traces_sample_rate=0.1,
            # Não envia PII (nome, email, IP) — defesa contra leak acidental
            send_default_pii=False,
            # Release tag pra correlacionar com versão do app
            release=os.environ.get("ESKUTA_VERSION", "0.1.0"),
            environment=os.environ.get("ESKUTA_ENV", "production"),
            # before_send filtra eventos com possíveis API keys
            before_send=_scrub_event,
        )
        _SENTRY_INITIALIZED = True
        logger.info("Sentry inicializado (telemetria opt-in)")
        return True
    except Exception as exc:
        logger.warning("Falha inicializando Sentry: {err}", err=exc)
        return False


def _scrub_event(event: dict, _hint: dict) -> dict | None:
    """
    Sanitiza events do Sentry — remove possíveis API keys do payload.

    Reusa o `mask_secrets` do log_masking pra consistência.
    """
    try:
        from app.services.log_masking import mask_secrets

        # Mascara message + stack frames
        if "message" in event and isinstance(event["message"], str):
            event["message"] = mask_secrets(event["message"])

        for exc in event.get("exception", {}).get("values", []):
            if isinstance(exc.get("value"), str):
                exc["value"] = mask_secrets(exc["value"])

        # Remove headers que podem conter Authorization
        request = event.get("request", {})
        if "headers" in request:
            headers = request["headers"]
            for k in list(headers.keys()):
                if k.lower() in ("authorization", "cookie", "x-api-key"):
                    headers[k] = "[REDACTED]"

        return event
    except Exception:
        # Se scrubbing falha, melhor não enviar
        return None
