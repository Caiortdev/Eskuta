"""
Validação de conectividade das API keys.

Pra cada provider conhecido, faz uma chamada barata (lista modelos /
ping endpoint) usando a chave fornecida e classifica o resultado em:

- **valid**: chave aceita pelo provider (200 OK na chamada cheap)
- **invalid**: chave rejeitada (401/403 do provider)
- **error**: erro temporário (timeout, 5xx, rede) — não classificamos
  como inválida porque o servidor pode estar indisponível.

Princípios:
- A chave **nunca** é logada — apenas o resultado + status code.
- Timeout agressivo (10s) — usuário não fica esperando.
- Imports lazy dos SDKs — não impactam startup do sidecar.
- A função NÃO salva nada no DB; só roda a chamada e retorna o veredito.
  Quem chama (endpoint) decide se persiste o resultado.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from loguru import logger

from app.services.keys import KNOWN_PROVIDERS, _mask

ValidationStatus = Literal["valid", "invalid", "error"]

# Timeout absoluto pra cada chamada de teste — 10s.
# Suficiente pra qualquer endpoint /models cold, agressivo o bastante
# pra não travar a UI.
_TEST_TIMEOUT_SEC: float = 10.0


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de uma validação de chave."""

    status: ValidationStatus
    # Mensagem amigável pro usuário. None em caso de sucesso.
    message: str | None
    # Status HTTP retornado pelo provider, se aplicável.
    http_status: int | None
    # Latência da chamada em milissegundos.
    latency_ms: int


# ============================================================
# Adapters por provider
# ============================================================


async def _validate_groq(key: str) -> ValidationResult:
    """GET /openai/v1/models via SDK Groq. Custo: zero."""
    from groq import APIStatusError, AsyncGroq

    started = time.perf_counter()
    client = AsyncGroq(api_key=key, timeout=_TEST_TIMEOUT_SEC)
    try:
        await client.models.list()
        latency = int((time.perf_counter() - started) * 1000)
        return ValidationResult(status="valid", message=None, http_status=200, latency_ms=latency)
    except APIStatusError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return _classify_status_error(exc.status_code, str(exc), latency)
    finally:
        await client.close()


async def _validate_assemblyai(key: str) -> ValidationResult:
    """GET /v2/transcript?limit=1 via httpx. Custo: zero (não cria transcript)."""
    import httpx

    started = time.perf_counter()
    headers = {"authorization": key}
    try:
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SEC) as client:
            resp = await client.get(
                "https://api.assemblyai.com/v2/transcript",
                headers=headers,
                params={"limit": 1},
            )
        latency = int((time.perf_counter() - started) * 1000)
        if resp.status_code == 200:
            return ValidationResult(
                status="valid", message=None, http_status=200, latency_ms=latency
            )
        return _classify_status_error(resp.status_code, resp.text[:200], latency)
    except httpx.TimeoutException:
        latency = int((time.perf_counter() - started) * 1000)
        return ValidationResult(
            status="error",
            message="Timeout — AssemblyAI não respondeu em 10s.",
            http_status=None,
            latency_ms=latency,
        )
    except httpx.HTTPError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return ValidationResult(
            status="error",
            message=f"Erro de rede: {exc.__class__.__name__}",
            http_status=None,
            latency_ms=latency,
        )


async def _validate_anthropic(key: str) -> ValidationResult:
    """GET /v1/models via SDK Anthropic. Custo: zero."""
    from anthropic import APIStatusError, AsyncAnthropic

    started = time.perf_counter()
    client = AsyncAnthropic(api_key=key, timeout=_TEST_TIMEOUT_SEC)
    try:
        await client.models.list()
        latency = int((time.perf_counter() - started) * 1000)
        return ValidationResult(status="valid", message=None, http_status=200, latency_ms=latency)
    except APIStatusError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return _classify_status_error(exc.status_code, str(exc), latency)
    finally:
        await client.close()


async def _validate_openai(key: str) -> ValidationResult:
    """GET /v1/models via SDK OpenAI. Custo: zero."""
    from openai import APIStatusError, AsyncOpenAI

    started = time.perf_counter()
    client = AsyncOpenAI(api_key=key, timeout=_TEST_TIMEOUT_SEC)
    try:
        await client.models.list()
        latency = int((time.perf_counter() - started) * 1000)
        return ValidationResult(status="valid", message=None, http_status=200, latency_ms=latency)
    except APIStatusError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return _classify_status_error(exc.status_code, str(exc), latency)
    finally:
        await client.close()


async def _validate_google(key: str) -> ValidationResult:
    """
    GET /v1beta/models via REST (não usa o SDK google-genai pra evitar overhead
    de import; a chamada é só uma listagem barata).
    """
    import httpx

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT_SEC) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": key},
            )
        latency = int((time.perf_counter() - started) * 1000)
        if resp.status_code == 200:
            return ValidationResult(
                status="valid", message=None, http_status=200, latency_ms=latency
            )
        return _classify_status_error(resp.status_code, resp.text[:200], latency)
    except httpx.TimeoutException:
        latency = int((time.perf_counter() - started) * 1000)
        return ValidationResult(
            status="error",
            message="Timeout — Google AI não respondeu em 10s.",
            http_status=None,
            latency_ms=latency,
        )
    except httpx.HTTPError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return ValidationResult(
            status="error",
            message=f"Erro de rede: {exc.__class__.__name__}",
            http_status=None,
            latency_ms=latency,
        )


# ============================================================
# Dispatcher
# ============================================================


_VALIDATORS = {
    "groq": _validate_groq,
    "assemblyai": _validate_assemblyai,
    "anthropic": _validate_anthropic,
    "openai": _validate_openai,
    "google": _validate_google,
}


def _classify_status_error(
    http_status: int, body_excerpt: str, latency_ms: int
) -> ValidationResult:
    """401/403 = inválida, 429/5xx = erro temporário, outros = erro."""
    if http_status in (401, 403):
        return ValidationResult(
            status="invalid",
            message="Chave rejeitada pelo provider — verifique se digitou correto.",
            http_status=http_status,
            latency_ms=latency_ms,
        )
    if http_status == 429:
        return ValidationResult(
            status="error",
            message="Rate limit do provider — espere alguns segundos e tente de novo.",
            http_status=http_status,
            latency_ms=latency_ms,
        )
    if 500 <= http_status < 600:
        return ValidationResult(
            status="error",
            message=f"Provider retornou {http_status} — tente novamente em alguns minutos.",
            http_status=http_status,
            latency_ms=latency_ms,
        )
    return ValidationResult(
        status="error",
        message=f"Resposta inesperada {http_status}: {body_excerpt}",
        http_status=http_status,
        latency_ms=latency_ms,
    )


async def validate_api_key(provider: str, key: str) -> ValidationResult:
    """
    Valida uma chave chamando o provider real (endpoint cheap).

    Raises:
        ValueError: provider desconhecido (não está em KNOWN_PROVIDERS)
    """
    if provider not in KNOWN_PROVIDERS:
        raise ValueError(
            f"Provider desconhecido: {provider!r}. Aceitos: {', '.join(KNOWN_PROVIDERS)}"
        )
    if not key or not key.strip():
        return ValidationResult(
            status="invalid",
            message="Chave vazia.",
            http_status=None,
            latency_ms=0,
        )

    validator = _VALIDATORS[provider]
    logger.debug("Validando key", provider=provider, key_mask=_mask(key))
    result = await validator(key.strip())
    logger.info(
        "Validação de key concluída",
        provider=provider,
        status=result.status,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
    )
    return result
