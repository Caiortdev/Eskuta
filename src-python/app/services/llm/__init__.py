"""
Camada de LLM do Eskuta — geração de texto via Claude / GPT / Gemini.

Implementa padrão adapter pra que o resto do app não dependa
diretamente dos SDKs Anthropic/OpenAI/Google. Use o `LLMRouter` pra
selecionar provider conforme a preferência do usuário com fallback
pra qualquer provider disponível.

Modelos padrão recomendados (revisar a cada 3 meses no
`RELATORIO_TECNICO.md §1.6.1`):

- Claude: `claude-sonnet-4-5` — melhor custo-benefício pra raciocínio
- GPT:    `gpt-4.1`           — equilíbrio qualidade/preço
- Gemini: `gemini-2.5-flash`  — mais barato pra alto volume
"""

from app.services.llm.base import (
    KNOWN_LLM_PROVIDERS,
    LLMAPIError,
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
)
from app.services.llm.claude_provider import CLAUDE_MODEL, ClaudeProvider
from app.services.llm.gemini_provider import GEMINI_MODEL, GeminiProvider
from app.services.llm.gpt_provider import GPT_MODEL, GPTProvider
from app.services.llm.router import LLMRouter

__all__ = [
    "CLAUDE_MODEL",
    "GEMINI_MODEL",
    "GPT_MODEL",
    "KNOWN_LLM_PROVIDERS",
    "ClaudeProvider",
    "GPTProvider",
    "GeminiProvider",
    "LLMAPIError",
    "LLMError",
    "LLMMessage",
    "LLMProvider",
    "LLMProviderUnavailableError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMRouter",
    "LLMTimeoutError",
]
