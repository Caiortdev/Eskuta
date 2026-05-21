"""Testes dos endpoints REST de /api/keys."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from app.models import ApiKey, AuditLog


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
