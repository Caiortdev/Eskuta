"""
Adapter pro Gemini (Google) via SDK oficial `google-genai`.

Modelo default: `gemini-2.5-flash` — escolha do relatório como opção
barata e rápida pra alto volume. `gemini-2.5-pro` é opção mais
qualidade-cara; pode ser sobrescrito via `model=...`.

Particularidades do Gemini:
- API moderna (`google-genai`, substitui `google-generativeai`
  deprecated em 2024): `Client(api_key).aio.models.generate_content(...)`.
- `system` instruction vai em `config.system_instruction` (string única).
- Role `assistant` vira `model`. Mensagens são `contents` em vez de
  `messages`.
- JSON mode via `config.response_mime_type="application/json"`.
- Tokens em `response.usage_metadata.prompt_token_count` /
  `candidates_token_count`.

Preços (USD/1M tokens, jan/2026 — revisar trimestralmente):
- Input:  $0.075
- Output: $0.30
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final

from loguru import logger

from app.services import keys as keys_service
from app.services.llm.base import (
    LLMAPIError,
    LLMMessage,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
)

GEMINI_MODEL: Final[str] = "gemini-2.5-flash"
GEMINI_INPUT_PER_MTOK: Final[float] = 0.075
GEMINI_OUTPUT_PER_MTOK: Final[float] = 0.30

# Regex pra extrair "Please retry in 6.423179713s" da mensagem de erro 429
# do Gemini. O free tier limita a 5 req/min pro modelo flash.
_RETRY_AFTER_RE: Final[re.Pattern[str]] = re.compile(
    r"retry in (\d+(?:\.\d+)?)\s*s",
    re.IGNORECASE,
)


def _extract_retry_after_sec(exc: Exception) -> float | None:
    """
    Extrai retry_after em segundos do erro 429 do Gemini. A API devolve
    em DOIS lugares — tentamos ambos:
    1. String "Please retry in 6.4s" na mensagem
    2. Field `details.retryDelay` (formato "6s") — mais difícil de
       parsear sem acessar campos privados do SDK
    """
    msg = str(exc)
    match = _RETRY_AFTER_RE.search(msg)
    if match:
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            return None
    return None


class GeminiProvider(LLMProvider):
    """Adapter pro Gemini (cliente async via google-genai)."""

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return GEMINI_MODEL

    def is_available(self) -> bool:
        return keys_service.has_api_key("google")

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        api_key = keys_service.get_api_key("google")
        if not api_key:
            raise LLMProviderUnavailableError(
                "Gemini sem API key configurada",
                provider="gemini",
            )

        from google import genai
        from google.genai import errors as genai_errors
        from google.genai import types

        chosen_model = model or self.default_model

        # Mapeia mensagens — system vai pra config, role assistant→model
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
                continue
            role = "model" if m.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system_parts:
            config_kwargs["system_instruction"] = "\n\n".join(system_parts)
        if response_format and response_format.get("type") == "json_object":
            config_kwargs["response_mime_type"] = "application/json"

        client = genai.Client(api_key=api_key)

        try:
            response = await client.aio.models.generate_content(
                model=chosen_model,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except genai_errors.APIError as exc:
            msg = str(exc).lower()
            # 429 e RESOURCE_EXHAUSTED são casos típicos de rate limit
            # do free tier (5 req/min no gemini-2.5-flash). Tem "resource"
            # ou "quota" se for rate, então cobrimos vários jeitos.
            is_rate = (
                ("rate" in msg and "limit" in msg)
                or "resource_exhausted" in msg
                or "quota exceeded" in msg
                or "429" in msg
            )
            if is_rate:
                raise LLMRateLimitError(
                    "Gemini rate limit excedido",
                    provider="gemini",
                    retry_after_sec=_extract_retry_after_sec(exc),
                ) from exc
            if "timeout" in msg or "deadline" in msg:
                raise LLMTimeoutError(
                    f"Gemini timeout: {exc}",
                    provider="gemini",
                ) from exc
            raise LLMAPIError(
                f"Gemini erro de API: {exc}",
                provider="gemini",
            ) from exc

        content = (response.text or "").strip()
        usage = getattr(response, "usage_metadata", None)
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)
        cost = (
            tokens_in / 1_000_000 * GEMINI_INPUT_PER_MTOK
            + tokens_out / 1_000_000 * GEMINI_OUTPUT_PER_MTOK
        )

        logger.info(
            "Gemini completion concluída",
            provider="gemini",
            model=chosen_model,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=round(cost, 6),
        )

        return LLMResponse(
            content=content,
            provider="gemini",
            model=chosen_model,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=cost,
        )
