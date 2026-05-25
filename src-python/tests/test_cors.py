"""
Testes do middleware CORS. Garante que apenas origens conhecidas do Tauri
são aceitas — wildcard "*" seria vulnerabilidade já que o sidecar escuta
em localhost mas pode ser alvo de DNS rebinding.
"""

from __future__ import annotations

import httpx
import pytest

ALLOWED_ORIGINS = [
    "http://localhost:1420",
    "http://tauri.localhost",
    "tauri://localhost",
    "https://tauri.localhost",
]

REJECTED_ORIGINS = [
    "http://evil.com",
    "https://attacker.example",
    # NOTA: http://localhost:3000 não está mais rejeitado — o regex
    # passou a aceitar qualquer porta localhost (necessário pra Tauri
    # webview que usa porta aleatória do WebView2 + Vite que pode mudar
    # porta). Como o sidecar bind em 127.0.0.1, só processos da própria
    # máquina alcançam — origem cruzada de outra máquina não chega aqui.
    "null",
]


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
async def test_cors_allows_known_origins(client: httpx.AsyncClient, origin: str) -> None:
    res = await client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize("origin", REJECTED_ORIGINS)
async def test_cors_blocks_unknown_origins(client: httpx.AsyncClient, origin: str) -> None:
    res = await client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    # Origem rejeitada não recebe o header allow-origin (FastAPI/Starlette
    # ainda devolve 200, mas sem o header — browser bloqueia o request).
    assert res.headers.get("access-control-allow-origin") is None


async def test_cors_does_not_use_wildcard(client: httpx.AsyncClient) -> None:
    """
    Garante que NUNCA expomos "*" no allow-origin. Se alguém acidentalmente
    trocar pra wildcard no main.py, este teste pega.
    """
    res = await client.options(
        "/health",
        headers={
            "Origin": "http://localhost:1420",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") != "*"
