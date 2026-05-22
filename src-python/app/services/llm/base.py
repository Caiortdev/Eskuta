"""
Interfaces e tipos da camada de LLM.

Cada provider concreto (Claude/GPT/Gemini) vive em arquivo separado
e implementa `LLMProvider`. O `LLMRouter` (em `router.py`) escolhe
qual usar conforme a preferência do usuário com fallback pra qualquer
provider disponível.

Convenções:
- `LLMMessage` segue padrão `role / content` (system/user/assistant)
  — cada provider traduz internamente pro formato do SDK dele
  (Anthropic separa system; Gemini usa "model" em vez de "assistant").
- `LLMResponse` é normalizado: tokens contados pelo provider, custo
  estimado a partir de tabela de preços pinada por provider.
- Hierarquia de exceptions paralela à da camada de transcrição —
  permite o pipeline de ata (Fase 1.9) tratar rate limits, falhas
  recuperáveis e providers indisponíveis de forma uniforme.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

KnownLLMProvider = Literal["claude", "gpt", "gemini"]
KNOWN_LLM_PROVIDERS: Final[tuple[KnownLLMProvider, ...]] = (
    "claude",
    "gpt",
    "gemini",
)


@dataclass(frozen=True)
class LLMMessage:
    """Mensagem de chat — role e conteúdo de texto."""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """Resposta normalizada de qualquer LLM provider."""

    content: str
    provider: str  # "claude" | "gpt" | "gemini"
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float = 0.0


# ============================================================
# Hierarquia de exceptions
# ============================================================


class LLMError(RuntimeError):
    """Erro genérico de LLM. Subclasses capturam casos específicos."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        super().__init__(message)
        self.provider = provider


class LLMProviderUnavailableError(LLMError):
    """Provider não pode ser usado agora (sem API key, SDK não instalado)."""


class LLMRateLimitError(LLMError):
    """Provider retornou 429 ou equivalente."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        retry_after_sec: float | None = None,
    ) -> None:
        super().__init__(message, provider=provider)
        self.retry_after_sec = retry_after_sec


class LLMAPIError(LLMError):
    """Provider retornou erro não-recuperável (auth, request inválido, 5xx)."""


class LLMTimeoutError(LLMError):
    """Provider demorou demais."""


# ============================================================
# Interface
# ============================================================


class LLMProvider(ABC):
    """Interface única que TODOS os adapters concretos implementam."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def default_model(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool:
        """True se temos credenciais (não testa rede)."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        response_format: dict | None = None,
    ) -> LLMResponse:
        """
        Gera uma completion a partir de `messages`.

        - `model=None` usa `default_model` do provider.
        - `temperature=0.3` (Etapa 1.7) — baixo o suficiente pra
          reduzir alucinação, alto o suficiente pra fluidez.
        - `response_format={"type": "json_object"}` força JSON output
          (necessário pra ata estruturada na Fase 1.9). Cada provider
          implementa essa garantia do jeito que o SDK dele permite
          (system prompt, response_format nativo, response_mime_type).

        Levanta uma das subclasses de `LLMError`. Nunca retorna `None`.
        """
        ...
