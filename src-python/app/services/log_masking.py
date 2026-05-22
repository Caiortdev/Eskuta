"""
Mascaramento de API keys e segredos em strings (textos de log).

Usado pelo endpoint de export de logs (/api/diagnostics/export-logs)
para garantir que nenhuma chave de provider vaze no arquivo entregue
ao usuário pra suporte.

Patterns conhecidos (cobrem os 5 providers + Bearer genérico):
- Groq:        gsk_<chars>
- AssemblyAI:  hex de 32 chars (a "API key" é assim)
- Anthropic:   sk-ant-<chars>
- OpenAI:      sk-proj-<chars>, sk-<chars>
- Google AI:   AIza<chars>
- Bearer generic
"""

from __future__ import annotations

import re
from typing import Final

# Cada pattern é um regex que captura uma chave. Substituímos por uma
# versão mascarada que preserva o prefixo identificador (pra debug
# saber QUAL provider/tipo) mas zera o valor.
#
# Ordem importa: patterns mais específicos vêm primeiro pra não serem
# canibalizados por matchers genéricos.
_KEY_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    # Groq: gsk_ABCdef123... (alphanumérico + underscore, ≥20 chars)
    (re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b"), "gsk_***REDACTED***"),
    # Anthropic: sk-ant-api03-... ou sk-ant-...
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "sk-ant-***REDACTED***"),
    # OpenAI projeto: sk-proj-...
    (re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"), "sk-proj-***REDACTED***"),
    # OpenAI legacy: sk-... (genérico, prefixo sk-)
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "sk-***REDACTED***"),
    # Google AI Studio: AIzaSy<...>
    (re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"), "AIza***REDACTED***"),
    # AssemblyAI: hex de 32 chars (formato típico). Usamos boundary pra não
    # bater em hashes SHA256/MD5 dentro de outros contextos legítimos.
    # CUIDADO: pattern genérico — só aplicamos depois dos específicos.
    (
        re.compile(r"\b[a-f0-9]{32}\b(?!.*sha)"),
        "***REDACTED-32HEX***",
    ),
    # Bearer auth header (cobre qualquer token JWT-like ou api key passada via Authorization)
    (
        re.compile(r"Bearer\s+[A-Za-z0-9._\-/=+]{20,}", re.IGNORECASE),
        "Bearer ***REDACTED***",
    ),
    # Authorization header com api key bruta (sem Bearer)
    (
        re.compile(r'(?i)(authorization["\']?\s*[:=]\s*["\']?)[A-Za-z0-9._\-/=+]{20,}'),
        r"\1***REDACTED***",
    ),
    # Campos comuns em JSON de log: "key": "...", "api_key": "...", "apikey": "...", "token": "..."
    (
        re.compile(r'(?i)("(?:api[_-]?key|apikey|token|secret|password)"\s*:\s*")[^"]+(")'),
        r"\1***REDACTED***\2",
    ),
]


def mask_secrets(text: str) -> str:
    """
    Substitui ocorrências de chaves/tokens em `text` por placeholders.

    Função pura — não consulta variáveis de ambiente nem o keyring.
    Operando estritamente em padrões textuais.
    """
    if not text:
        return text
    result = text
    for pattern, replacement in _KEY_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def mask_secrets_in_file(content_bytes: bytes) -> bytes:
    """Mascarar segredos num arquivo lido como bytes. Tolerante a encoding."""
    try:
        text = content_bytes.decode("utf-8", errors="replace")
    except Exception:
        # Arquivo binário ou encoding muito quebrado — retorna sem alterar
        return content_bytes
    return mask_secrets(text).encode("utf-8")
