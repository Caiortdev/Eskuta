"""
Wrapper sobre `keyring` para armazenar API keys dos providers no OS
keyring nativo (Credential Manager no Windows, Keychain no macOS,
Secret Service / KWallet no Linux).

Princípios:
- **A chave NUNCA é armazenada em disco** — só no keyring do OS.
- **A chave NUNCA aparece em log** — qualquer log mostra só o provider
  e tamanho mascarado (`***`).
- A tabela `api_keys` no DB armazena APENAS metadata (is_configured,
  last_validated_at) — referência ao keyring, nunca o valor.
- Providers inválidos são rejeitados explicitamente.
"""

from __future__ import annotations

from typing import Final, Literal

import keyring
import keyring.errors
from loguru import logger

# Nome do serviço usado no keyring do OS. Em todos os 3 SOs aparece
# como "eskuta-app" na UI nativa de credenciais.
SERVICE_NAME: Final[str] = "eskuta-app"

# Providers conhecidos pelo app — outros são rejeitados.
KnownProvider = Literal["groq", "assemblyai", "anthropic", "openai", "google"]
KNOWN_PROVIDERS: Final[tuple[KnownProvider, ...]] = (
    "groq",
    "assemblyai",
    "anthropic",
    "openai",
    "google",
)


class UnknownProviderError(ValueError):
    """Provider não está na allow-list (KNOWN_PROVIDERS)."""


class EmptyKeyError(ValueError):
    """Valor da chave veio vazio — não vamos salvar string em branco."""


def _validate_provider(provider: str) -> KnownProvider:
    if provider not in KNOWN_PROVIDERS:
        raise UnknownProviderError(
            f"Provider desconhecido: {provider!r}. " f"Aceitos: {', '.join(KNOWN_PROVIDERS)}"
        )
    return provider  # type: ignore[return-value]


def _mask(key: str) -> str:
    """Mascara uma chave pra log — preserva tamanho aproximado, esconde o valor."""
    if not key:
        return "<vazio>"
    return f"***({len(key)} chars)"


def save_api_key(provider: str, key: str) -> None:
    """Salva a chave de um provider no keyring. Substitui se já existia."""
    valid = _validate_provider(provider)
    if not key or not key.strip():
        raise EmptyKeyError("Chave vazia não pode ser salva no keyring.")

    keyring.set_password(SERVICE_NAME, valid, key.strip())
    logger.info("API key salva", provider=valid, key_mask=_mask(key))


def get_api_key(provider: str) -> str | None:
    """Retorna a chave do provider ou None se não estiver configurada."""
    valid = _validate_provider(provider)
    return keyring.get_password(SERVICE_NAME, valid)


def has_api_key(provider: str) -> bool:
    """True se a chave do provider existe e não é vazia."""
    value = get_api_key(provider)
    return bool(value and value.strip())


def delete_api_key(provider: str) -> bool:
    """
    Remove a chave do keyring. Retorna True se removeu, False se já
    não existia (idempotente).
    """
    valid = _validate_provider(provider)
    try:
        keyring.delete_password(SERVICE_NAME, valid)
    except keyring.errors.PasswordDeleteError:
        logger.debug("Tentativa de delete em key inexistente", provider=valid)
        return False
    logger.info("API key removida", provider=valid)
    return True


def list_configured_providers() -> dict[str, bool]:
    """
    Retorna um dict {provider: is_configured} pra todos os providers
    conhecidos. Não revela valores das chaves.
    """
    return {p: has_api_key(p) for p in KNOWN_PROVIDERS}
