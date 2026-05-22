"""Testes do masking de API keys / segredos em texto."""

from __future__ import annotations

from app.services.log_masking import mask_secrets, mask_secrets_in_file


def test_masks_groq_key() -> None:
    text = "calling groq with gsk_abcdefghijklmnopqrstuvwxyz0123456789"
    masked = mask_secrets(text)
    assert "gsk_abcd" not in masked
    assert "gsk_***REDACTED***" in masked


def test_masks_anthropic_key() -> None:
    text = "Anthropic call with sk-ant-api03-abc123def456ghi789jkl0mno1"
    masked = mask_secrets(text)
    assert "sk-ant-api03" not in masked
    assert "sk-ant-***REDACTED***" in masked


def test_masks_openai_proj_key() -> None:
    text = "key=sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
    masked = mask_secrets(text)
    assert "AbCdEf" not in masked
    assert "sk-proj-***REDACTED***" in masked


def test_masks_openai_legacy_key() -> None:
    # Sem Bearer prefix pra exercitar especificamente o pattern sk-
    text = "openai key sk-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789 then done"
    masked = mask_secrets(text)
    assert "AbCdEf" not in masked
    assert "sk-***REDACTED***" in masked


def test_bearer_with_sk_key_redacted() -> None:
    """
    Quando "Bearer sk-..." aparece, o pattern sk- bate primeiro (vem antes
    do Bearer na ordem). Resultado: "Bearer sk-***REDACTED***". O importante
    é que o valor da chave NÃO vaze.
    """
    text = "Bearer sk-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
    masked = mask_secrets(text)
    assert "AbCdEf" not in masked  # valor real foi removido
    assert "REDACTED" in masked


def test_masks_google_key() -> None:
    text = "google api key: AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz_-123456"
    masked = mask_secrets(text)
    assert "SyAbCdEf" not in masked
    assert "AIza***REDACTED***" in masked


def test_masks_bearer_token() -> None:
    text = "Authorization: Bearer abc123def456ghi789.jkl0mno-pqr_stu/vwx"
    masked = mask_secrets(text)
    assert "abc123def456" not in masked
    assert "Bearer ***REDACTED***" in masked


def test_masks_json_api_key_field() -> None:
    text = '{"api_key": "supersecreto-12345-abcdef-67890-zyxwvut"}'
    masked = mask_secrets(text)
    assert "supersecreto" not in masked
    assert '"api_key": "***REDACTED***"' in masked


def test_masks_json_token_field() -> None:
    text = '{"token": "valor-token-aqui-12345678901234567890"}'
    masked = mask_secrets(text)
    assert "valor-token" not in masked


def test_masks_assemblyai_32hex() -> None:
    # AssemblyAI key real = 32 hex chars (0-9, a-f). O pattern só bate em hex.
    real_hex = "abc123def456abc789012345abcdef01"  # 32 chars [0-9a-f]
    assert len(real_hex) == 32
    text = f"AssemblyAI key {real_hex} usado"
    masked = mask_secrets(text)
    assert real_hex not in masked
    assert "***REDACTED-32HEX***" in masked


def test_preserves_non_secret_text() -> None:
    text = "User uploaded file meeting.mp3 (size: 5MB)"
    masked = mask_secrets(text)
    assert masked == text  # nenhuma key, nada muda


def test_empty_string_passes_through() -> None:
    assert mask_secrets("") == ""


def test_masks_multiple_keys_in_same_string() -> None:
    text = (
        "groq=gsk_abcdefghijklmnopqrstuvwxyz0123456789 " "anthropic=sk-ant-abc123def456ghi789jkl0mn"
    )
    masked = mask_secrets(text)
    assert "abcdef" not in masked
    assert "ghi789" not in masked
    assert masked.count("***REDACTED***") >= 2


def test_mask_secrets_in_file_handles_utf8() -> None:
    content = b"log line com acento: relatorio.mp3 e key gsk_abcdefghijklmnopqrst1234567890"
    masked = mask_secrets_in_file(content)
    assert b"gsk_abcd" not in masked
    assert b"acento" in masked  # preservou texto normal


def test_mask_secrets_in_file_handles_bytes_invalid_utf8() -> None:
    # Bytes inválidos — não pode lançar exception
    content = b"\xff\xfe ruim \x00 token=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
    masked = mask_secrets_in_file(content)
    # Conseguiu mascarar mesmo com encoding ruim
    assert b"abcdef" not in masked


def test_authorization_header_value() -> None:
    text = '"Authorization": "abc123def456ghi789jklmnopqrst"'
    masked = mask_secrets(text)
    assert "abc123def456" not in masked
