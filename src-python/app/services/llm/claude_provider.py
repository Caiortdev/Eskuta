"""
Adapter pro Claude (Anthropic) via SDK oficial.

Modelo default: `claude-sonnet-4-5` — escolha do relatório pelo melhor
custo-benefício em raciocínio (e portanto na geração de ata estruturada
que é o nosso caso de uso principal). Pode ser sobrescrito por chamada
via `model=...`.

Particularidades do Anthropic:
- API separa `system` (string única) das `messages` (user/assistant).
  Nosso `LLMMessage(role="system", ...)` é concatenado num system
  prompt único antes de mandar.
- JSON mode oficial é via tool_use; aqui fazemos via instrução
  explícita no system prompt — é o suficiente pro nosso uso e mantém
  a interface portátil entre providers.
- Tokens vêm em `response.usage.input_tokens` / `output_tokens`.

Preços (USD/1M tokens, jan/2026 — revisar trimestralmente):
- Input:  $3.00
- Output: $15.00
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

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

CLAUDE_MODEL: Final[str] = "claude-sonnet-4-5"
CLAUDE_INPUT_PER_MTOK: Final[float] = 3.0
CLAUDE_OUTPUT_PER_MTOK: Final[float] = 15.0


class ClaudeProvider(LLMProvider):
    """Adapter pro Claude (cliente async)."""

    @property
    def name(self) -> str:
        return "claude"

    @property
    def default_model(self) -> str:
        return CLAUDE_MODEL

    def is_available(self) -> bool:
        return keys_service.has_api_key("anthropic")

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        api_key = keys_service.get_api_key("anthropic")
        if not api_key:
            raise LLMProviderUnavailableError(
                "Claude sem API key configurada",
                provider="claude",
            )

        # Import lazy
        from anthropic import APIError, APITimeoutError, AsyncAnthropic
        from anthropic import RateLimitError as AnthropicRateLimit

        # Anthropic separa system de messages
        system_parts: list[str] = []
        chat_messages: list[dict[str, str]] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        system_prompt = "\n\n".join(system_parts)
        if response_format and response_format.get("type") == "json_object":
            json_instruction = (
                "Responda APENAS com JSON válido, sem texto antes ou depois. "
                "Sem markdown, sem ```json fences."
            )
            system_prompt = (
                f"{system_prompt}\n\n{json_instruction}" if system_prompt else json_instruction
            )

        chosen_model = model or self.default_model
        client = AsyncAnthropic(api_key=api_key)

        try:
            response = await client.messages.create(
                model=chosen_model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=chat_messages,
            )
        except AnthropicRateLimit as exc:
            raise LLMRateLimitError(
                "Claude rate limit excedido",
                provider="claude",
            ) from exc
        except APITimeoutError as exc:
            raise LLMTimeoutError(
                f"Claude timeout: {exc}",
                provider="claude",
            ) from exc
        except APIError as exc:
            raise LLMAPIError(
                f"Claude erro de API: {exc}",
                provider="claude",
            ) from exc

        content = "".join(getattr(block, "text", "") for block in (response.content or [])).strip()

        tokens_in = int(getattr(response.usage, "input_tokens", 0))
        tokens_out = int(getattr(response.usage, "output_tokens", 0))
        cost = (
            tokens_in / 1_000_000 * CLAUDE_INPUT_PER_MTOK
            + tokens_out / 1_000_000 * CLAUDE_OUTPUT_PER_MTOK
        )

        logger.info(
            "Claude completion concluída",
            provider="claude",
            model=chosen_model,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=round(cost, 6),
        )

        return LLMResponse(
            content=content,
            provider="claude",
            model=str(getattr(response, "model", chosen_model)),
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            cost_usd=cost,
        )
