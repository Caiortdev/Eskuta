"""
Router de LLM — escolhe qual provider usar conforme preferência.

Estratégia (RELATORIO_TECNICO §1.6.2):
1. Usa `preferred` passado explicitamente (se informado e disponível).
2. Fallback pra `settings.PREFERRED_LLM` (default "claude").
3. Fallback final pra qualquer provider disponível (configurado).
4. Sem nenhum disponível → `LLMProviderUnavailableError` com mensagem
   acionável (não vaza valor de API key).

Diferença vs `TranscriptionRouter`: aqui não fazemos retry/backoff
inter-provider — o router de LLM é primariamente um seletor, não
orquestrador. Retry de rate limit fica a cargo do caller (pipeline
de ata na Fase 1.9), que pode decidir trocar de provider em caso de
falha persistente.
"""

from __future__ import annotations

from collections.abc import Sequence

from loguru import logger

from app.core.settings import settings
from app.services.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMResponse,
)
from app.services.llm.claude_provider import ClaudeProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.gpt_provider import GPTProvider


def _build_default_providers() -> dict[str, LLMProvider]:
    return {
        "claude": ClaudeProvider(),
        "gpt": GPTProvider(),
        "gemini": GeminiProvider(),
    }


class LLMRouter:
    """Seleciona o LLM a usar e expõe `complete()` como conveniência."""

    def __init__(self, providers: dict[str, LLMProvider] | None = None) -> None:
        self.providers: dict[str, LLMProvider] = (
            dict(providers) if providers is not None else _build_default_providers()
        )

    def get_provider(self, preferred: str | None = None) -> LLMProvider:
        """
        Resolve qual provider usar. `preferred` (se informado) tem
        prioridade sobre `settings.PREFERRED_LLM`. Em qualquer caso,
        se o escolhido não está disponível, faz fallback pra qualquer
        outro disponível.
        """
        wanted = preferred or settings.PREFERRED_LLM
        provider = self.providers.get(wanted)
        if provider is not None and provider.is_available():
            return provider

        # Fallback: qualquer provider configurado
        for p in self.providers.values():
            if p.is_available():
                logger.warning(
                    "LLM preferido indisponível, usando fallback",
                    preferred=wanted,
                    picked=p.name,
                )
                return p

        raise LLMProviderUnavailableError(
            "Nenhum LLM disponível. Configure ao menos uma API key "
            "(Anthropic, OpenAI ou Google) em /api/keys."
        )

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        preferred: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        """Conveniência: seleciona provider e chama `complete()` nele."""
        provider = self.get_provider(preferred)
        return await provider.complete(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
        )
