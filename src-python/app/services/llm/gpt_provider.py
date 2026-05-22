"""
Adapter pro GPT (OpenAI) via SDK oficial.

Modelo default: `gpt-4.1` — escolha do relatório como meio-termo
entre qualidade e custo. `gpt-5-mini` também é mencionado como opção
mais barata; pode ser sobrescrito por chamada via `model=...`.

Particularidades do OpenAI:
- Suporta JSON mode nativo via `response_format={"type": "json_object"}`
  (desde nov/2023). Quando ativado, instrução "JSON" no prompt continua
  recomendada pra qualidade.
- Tokens em `response.usage.prompt_tokens` / `completion_tokens`.

Preços (USD/1M tokens, jan/2026 — revisar trimestralmente):
- Input:  $2.00
- Output: $8.00
"""

from __future__ import annotations

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

GPT_MODEL: Final[str] = "gpt-4.1"
GPT_INPUT_PER_MTOK: Final[float] = 2.0
GPT_OUTPUT_PER_MTOK: Final[float] = 8.0


class GPTProvider(LLMProvider):
    """Adapter pro GPT (cliente async)."""

    @property
    def name(self) -> str:
        return "gpt"

    @property
    def default_model(self) -> str:
        return GPT_MODEL

    def is_available(self) -> bool:
        return keys_service.has_api_key("openai")

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        api_key = keys_service.get_api_key("openai")
        if not api_key:
            raise LLMProviderUnavailableError(
                "GPT sem API key configurada",
                provider="gpt",
            )

        from openai import APIError, APITimeoutError, AsyncOpenAI
        from openai import RateLimitError as OpenAIRateLimit

        client = AsyncOpenAI(api_key=api_key)
        chosen_model = model or self.default_model

        openai_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict[str, Any] = {
            "model": chosen_model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format and response_format.get("type") == "json_object":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await client.chat.completions.create(**kwargs)
        except OpenAIRateLimit as exc:
            raise LLMRateLimitError(
                "GPT rate limit excedido",
                provider="gpt",
            ) from exc
        except APITimeoutError as exc:
            raise LLMTimeoutError(
                f"GPT timeout: {exc}",
                provider="gpt",
            ) from exc
        except APIError as exc:
            raise LLMAPIError(
                f"GPT erro de API: {exc}",
                provider="gpt",
            ) from exc

        choice = response.choices[0]
        content = (choice.message.content or "").strip()

        tokens_in = int(getattr(response.usage, "prompt_tokens", 0))
        tokens_out = int(getattr(response.usage, "completion_tokens", 0))
        cost = (
            tokens_in / 1_000_000 * GPT_INPUT_PER_MTOK
            + tokens_out / 1_000_000 * GPT_OUTPUT_PER_MTOK
        )

        logger.info(
            "GPT completion concluída",
            provider="gpt",
            model=chosen_model,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=round(cost, 6),
        )

        return LLMResponse(
            content=content,
            provider="gpt",
            model=str(getattr(response, "model", chosen_model)),
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=cost,
        )
