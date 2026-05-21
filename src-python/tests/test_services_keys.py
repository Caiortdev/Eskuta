"""Testes do wrapper de keyring (app.services.keys)."""

from __future__ import annotations

import pytest

from app.services import keys as keys_service


def test_save_and_get_roundtrip(in_memory_keyring) -> None:
    keys_service.save_api_key("groq", "sk_test_123")
    assert keys_service.get_api_key("groq") == "sk_test_123"
    assert keys_service.has_api_key("groq") is True


def test_get_unknown_returns_none(in_memory_keyring) -> None:
    assert keys_service.get_api_key("openai") is None
    assert keys_service.has_api_key("openai") is False


def test_delete_existing_returns_true(in_memory_keyring) -> None:
    keys_service.save_api_key("anthropic", "x")
    assert keys_service.delete_api_key("anthropic") is True
    assert keys_service.has_api_key("anthropic") is False


def test_delete_inexistent_is_idempotent(in_memory_keyring) -> None:
    assert keys_service.delete_api_key("google") is False


def test_list_configured_providers(in_memory_keyring) -> None:
    keys_service.save_api_key("groq", "g1")
    keys_service.save_api_key("openai", "o1")
    result = keys_service.list_configured_providers()
    assert result == {
        "groq": True,
        "assemblyai": False,
        "anthropic": False,
        "openai": True,
        "google": False,
    }


def test_unknown_provider_raises(in_memory_keyring) -> None:
    with pytest.raises(keys_service.UnknownProviderError):
        keys_service.save_api_key("hackerman", "x")
    with pytest.raises(keys_service.UnknownProviderError):
        keys_service.get_api_key("hackerman")
    with pytest.raises(keys_service.UnknownProviderError):
        keys_service.delete_api_key("hackerman")


def test_empty_key_raises(in_memory_keyring) -> None:
    with pytest.raises(keys_service.EmptyKeyError):
        keys_service.save_api_key("groq", "")
    with pytest.raises(keys_service.EmptyKeyError):
        keys_service.save_api_key("groq", "   ")


def test_save_strips_whitespace(in_memory_keyring) -> None:
    keys_service.save_api_key("groq", "  sk_with_spaces  ")
    assert keys_service.get_api_key("groq") == "sk_with_spaces"


def test_save_overwrites(in_memory_keyring) -> None:
    keys_service.save_api_key("groq", "first")
    keys_service.save_api_key("groq", "second")
    assert keys_service.get_api_key("groq") == "second"


def test_log_message_does_not_leak_key_value(
    in_memory_keyring, caplog: pytest.LogCaptureFixture
) -> None:
    """Log de save NUNCA pode conter o valor literal da chave."""
    secret = "super-secret-key-do-not-leak"
    with caplog.at_level("INFO"):
        keys_service.save_api_key("groq", secret)
    assert secret not in caplog.text


def test_mask_function_shows_length_not_value() -> None:
    masked = keys_service._mask("abc12345")
    assert "abc" not in masked
    assert "8" in masked  # comprimento aparece


def test_known_providers_constant_is_complete() -> None:
    """Garantir que mexer em KNOWN_PROVIDERS quebra o teste — protege contra typo."""
    assert keys_service.KNOWN_PROVIDERS == (
        "groq",
        "assemblyai",
        "anthropic",
        "openai",
        "google",
    )
