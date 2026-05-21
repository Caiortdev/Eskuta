"""
Smoke tests do endpoint /health do sidecar.

Cobre o critério de aceite da Etapa 0.5: "FastAPI sobe sem erro" e
"/health responde".
"""

from __future__ import annotations

import httpx

from app.main import __version__


async def test_health_returns_200(client: httpx.AsyncClient) -> None:
    res = await client.get("/health")
    assert res.status_code == 200


async def test_health_payload_shape(client: httpx.AsyncClient) -> None:
    res = await client.get("/health")
    body = res.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert "environment" in body


async def test_health_content_type_is_json(client: httpx.AsyncClient) -> None:
    res = await client.get("/health")
    assert res.headers["content-type"].startswith("application/json")


async def test_docs_endpoint_available(client: httpx.AsyncClient) -> None:
    """Swagger UI deve carregar pra o usuário inspecionar a API em dev."""
    res = await client.get("/docs")
    assert res.status_code == 200
    assert "swagger" in res.text.lower()


async def test_openapi_schema_available(client: httpx.AsyncClient) -> None:
    res = await client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    assert schema["info"]["title"] == "Eskuta Sidecar"
    assert schema["info"]["version"] == __version__
    assert "/health" in schema["paths"]
