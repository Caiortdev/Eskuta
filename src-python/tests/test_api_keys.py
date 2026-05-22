"""Testes dos endpoints REST de /api/keys."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.models import ApiKey, AuditLog
from app.services.key_validator import ValidationResult


async def test_list_returns_all_known_providers(client_with_db, in_memory_keyring) -> None:
    client, _session = client_with_db
    res = await client.get("/api/keys")
    assert res.status_code == 200
    body = res.json()
    providers = {p["provider"]: p for p in body["providers"]}
    # Todos os 5 providers conhecidos aparecem
    assert set(providers.keys()) == {"groq", "assemblyai", "anthropic", "openai", "google"}
    # Nenhum configurado ainda
    for p in providers.values():
        assert p["is_configured"] is False


async def test_save_key_updates_keyring_and_db(client_with_db, in_memory_keyring) -> None:
    client, session = client_with_db
    res = await client.put(
        "/api/keys/groq",
        json={"key": "sk_test_groq_123"},
    )
    assert res.status_code == 200
    assert res.json() == {"provider": "groq", "is_configured": True}

    # Keyring deve ter o valor
    assert in_memory_keyring.get_password("eskuta-app", "groq") == "sk_test_groq_123"

    # Tabela api_keys deve ter a linha
    row = (await session.execute(select(ApiKey).where(ApiKey.provider == "groq"))).scalar_one()
    assert row.is_configured is True

    # AuditLog deve ter uma entrada
    audit = (
        await session.execute(select(AuditLog).where(AuditLog.action == "configure_api_key"))
    ).scalar_one()
    assert audit.entity_id == "groq"
    assert audit.extra_metadata == {"provider": "groq"}


async def test_response_does_not_leak_key_value(client_with_db, in_memory_keyring) -> None:
    client, _session = client_with_db
    secret = "absolutely-do-not-leak"
    res = await client.put("/api/keys/anthropic", json={"key": secret})
    body = res.text
    assert secret not in body


async def test_delete_removes_from_keyring_and_marks_db(client_with_db, in_memory_keyring) -> None:
    client, session = client_with_db
    await client.put("/api/keys/openai", json={"key": "x"})
    assert in_memory_keyring.get_password("eskuta-app", "openai") == "x"

    res = await client.delete("/api/keys/openai")
    assert res.status_code == 200
    assert res.json() == {"provider": "openai", "is_configured": False}
    assert in_memory_keyring.get_password("eskuta-app", "openai") is None

    row = (await session.execute(select(ApiKey).where(ApiKey.provider == "openai"))).scalar_one()
    assert row.is_configured is False

    audit_actions = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    assert [a.action for a in audit_actions] == [
        "configure_api_key",
        "delete_api_key",
    ]


async def test_delete_unknown_provider_returns_404(client_with_db, in_memory_keyring) -> None:
    client, _session = client_with_db
    res = await client.delete("/api/keys/hackerman")
    assert res.status_code == 404


async def test_put_unknown_provider_returns_404(client_with_db, in_memory_keyring) -> None:
    client, _session = client_with_db
    res = await client.put("/api/keys/hackerman", json={"key": "x"})
    assert res.status_code == 404


async def test_put_empty_key_returns_422(client_with_db, in_memory_keyring) -> None:
    client, _session = client_with_db
    res = await client.put("/api/keys/groq", json={"key": ""})
    # FastAPI Pydantic validation rejects min_length=1 antes de chegar no service
    assert res.status_code == 422


async def test_save_updates_existing_row(client_with_db, in_memory_keyring) -> None:
    """Salvar duas vezes deve fazer UPDATE, não INSERT duplicado."""
    client, session = client_with_db
    await client.put("/api/keys/groq", json={"key": "first"})
    await client.put("/api/keys/groq", json={"key": "second"})

    rows = (await session.execute(select(ApiKey).where(ApiKey.provider == "groq"))).scalars().all()
    assert len(rows) == 1  # unique constraint respeitada
    assert in_memory_keyring.get_password("eskuta-app", "groq") == "second"


async def test_list_reflects_keyring_state(client_with_db, in_memory_keyring) -> None:
    client, _session = client_with_db
    in_memory_keyring.set_password("eskuta-app", "google", "g_external")

    res = await client.get("/api/keys")
    providers = {p["provider"]: p for p in res.json()["providers"]}
    assert providers["google"]["is_configured"] is True
    assert providers["groq"]["is_configured"] is False


async def test_health_still_works(client: httpx.AsyncClient) -> None:
    """Smoke: a inclusão do router /api/keys não quebrou nada."""
    res = await client.get("/health")
    assert res.status_code == 200


# ============================================================
# POST /api/keys/{provider}/test
# ============================================================


@pytest.fixture
def mock_validator():
    """Mocka key_validator.validate_api_key pra não bater no provider real."""
    with patch("app.api.keys.key_validator.validate_api_key", new_callable=AsyncMock) as m:
        yield m


async def test_test_endpoint_valid_key_in_body(
    client_with_db, in_memory_keyring, mock_validator
) -> None:
    client, _session = client_with_db
    mock_validator.return_value = ValidationResult(
        status="valid", message=None, http_status=200, latency_ms=42
    )
    res = await client.post("/api/keys/groq/test", json={"key": "novo-valor"})
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "groq"
    assert body["status"] == "valid"
    assert body["latency_ms"] == 42
    # Quando testa um valor novo (não do keyring), NÃO persiste em api_keys
    mock_validator.assert_awaited_once_with("groq", "novo-valor")


async def test_test_endpoint_invalid_key_returns_invalid_status(
    client_with_db, in_memory_keyring, mock_validator
) -> None:
    client, _session = client_with_db
    mock_validator.return_value = ValidationResult(
        status="invalid",
        message="Chave rejeitada pelo provider — verifique se digitou correto.",
        http_status=401,
        latency_ms=120,
    )
    res = await client.post("/api/keys/anthropic/test", json={"key": "errada"})
    assert res.status_code == 200  # 200 com status="invalid", não 401
    body = res.json()
    assert body["status"] == "invalid"
    assert body["http_status"] == 401
    assert "rejeitada" in body["message"]


async def test_test_endpoint_uses_stored_key_when_body_omitted(
    client_with_db, in_memory_keyring, mock_validator
) -> None:
    client, session = client_with_db
    # Salva uma key no keyring + DB primeiro
    await client.put("/api/keys/openai", json={"key": "stored-value"})

    mock_validator.return_value = ValidationResult(
        status="valid", message=None, http_status=200, latency_ms=80
    )
    res = await client.post("/api/keys/openai/test", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "valid"
    mock_validator.assert_awaited_once_with("openai", "stored-value")

    # Resultado deve ter sido persistido em api_keys (last_validated_at +
    # last_validation_status) porque testou a chave do keyring
    await session.refresh(
        (await session.execute(select(ApiKey).where(ApiKey.provider == "openai"))).scalar_one()
    )
    row = (await session.execute(select(ApiKey).where(ApiKey.provider == "openai"))).scalar_one()
    assert row.last_validation_status == "valid"
    assert row.last_validated_at is not None


async def test_test_endpoint_404_when_no_stored_key_and_no_body(
    client_with_db, in_memory_keyring
) -> None:
    client, _session = client_with_db
    res = await client.post("/api/keys/groq/test", json={})
    assert res.status_code == 404
    assert "Nenhuma chave salva" in res.json()["detail"]


async def test_test_endpoint_unknown_provider_returns_404(
    client_with_db, in_memory_keyring
) -> None:
    client, _session = client_with_db
    res = await client.post("/api/keys/bogus/test", json={"key": "x"})
    assert res.status_code == 404


async def test_test_endpoint_response_does_not_leak_key(
    client_with_db, in_memory_keyring, mock_validator
) -> None:
    client, _session = client_with_db
    mock_validator.return_value = ValidationResult(
        status="valid", message=None, http_status=200, latency_ms=10
    )
    secret = "super-secreta-nunca-vaza"
    res = await client.post("/api/keys/groq/test", json={"key": secret})
    assert secret not in res.text


async def test_test_endpoint_persists_invalid_status_for_stored_key(
    client_with_db, in_memory_keyring, mock_validator
) -> None:
    """Quando a chave já salva é testada e dá invalid, o status fica registrado."""
    client, session = client_with_db
    await client.put("/api/keys/google", json={"key": "originalmente-valida"})

    mock_validator.return_value = ValidationResult(
        status="invalid", message="Expirou", http_status=401, latency_ms=70
    )
    res = await client.post("/api/keys/google/test", json={})
    assert res.status_code == 200
    assert res.json()["status"] == "invalid"

    row = (await session.execute(select(ApiKey).where(ApiKey.provider == "google"))).scalar_one()
    assert row.last_validation_status == "invalid"
    assert row.notes == "Expirou"
