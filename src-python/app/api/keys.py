"""
Endpoints REST pra gerenciar API keys dos providers.

Princípios:
- Nenhum endpoint retorna o valor da chave — só metadata.
- Toda escrita/remoção sincroniza com `api_keys` no DB e grava
  uma entrada em `audit_log` (sem o valor da chave).
- Validação rigorosa do nome do provider (allow-list).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.database import get_db
from app.models import ApiKey, AuditLog
from app.services import key_validator
from app.services import keys as keys_service

router = APIRouter(prefix="/api/keys", tags=["api-keys"])

# Type alias do FastAPI moderno — evita B008 do ruff.
DbSession = Annotated[AsyncSession, Depends(get_db)]


# ============================================================
# Schemas
# ============================================================


class ProviderStatus(BaseModel):
    """Status de um provider — nunca contém o valor da chave."""

    provider: str
    is_configured: bool
    last_validated_at: datetime | None = None
    last_validation_status: Literal["success", "failed", "invalid"] | None = None
    notes: str | None = None


class ProvidersListResponse(BaseModel):
    providers: list[ProviderStatus]


class SaveKeyRequest(BaseModel):
    key: str = Field(min_length=1, max_length=2048, description="Valor da chave (não logado)")


class SimpleStatusResponse(BaseModel):
    provider: str
    is_configured: bool


class TestKeyRequest(BaseModel):
    """
    Testar uma chave SEM persistir.

    Se `key` é omitido, usa a chave atualmente salva no keyring (test
    da configuração atual). Se fornecido, testa o valor novo antes de
    salvar.
    """

    key: str | None = Field(
        default=None,
        max_length=2048,
        description="Valor da chave a testar. Omita pra testar a chave já salva.",
    )


class TestKeyResponse(BaseModel):
    provider: str
    status: Literal["valid", "invalid", "error"]
    message: str | None = None
    http_status: int | None = None
    latency_ms: int


# ============================================================
# Helpers
# ============================================================


def _validate_provider_param(provider: str) -> str:
    """Valida o path param `{provider}` antes de chegar ao service."""
    if provider not in keys_service.KNOWN_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Provider desconhecido: {provider!r}. "
                f"Aceitos: {', '.join(keys_service.KNOWN_PROVIDERS)}"
            ),
        )
    return provider


async def _upsert_api_key_row(db: AsyncSession, *, provider: str, is_configured: bool) -> ApiKey:
    """Cria ou atualiza a linha de metadata na tabela `api_keys`."""
    result = await db.execute(select(ApiKey).where(ApiKey.provider == provider))
    row = result.scalar_one_or_none()
    if row is None:
        row = ApiKey(provider=provider, is_configured=is_configured)
        db.add(row)
    else:
        row.is_configured = is_configured
        row.updated_at = utcnow()
    return row


async def _log_audit(
    db: AsyncSession,
    *,
    action: str,
    provider: str,
) -> None:
    """Adiciona uma entrada em audit_log — NUNCA inclui o valor da chave."""
    db.add(
        AuditLog(
            action=action,
            entity_type="api_key",
            entity_id=provider,
            extra_metadata={"provider": provider},
        )
    )


# ============================================================
# Endpoints
# ============================================================


@router.get("", response_model=ProvidersListResponse)
async def list_providers(db: DbSession) -> ProvidersListResponse:
    """Lista todos os providers conhecidos + status de configuração."""
    configured_in_keyring = keys_service.list_configured_providers()

    rows = (await db.execute(select(ApiKey))).scalars().all()
    by_provider = {row.provider: row for row in rows}

    providers: list[ProviderStatus] = []
    for provider, in_keyring in configured_in_keyring.items():
        row = by_provider.get(provider)
        providers.append(
            ProviderStatus(
                provider=provider,
                is_configured=in_keyring,
                last_validated_at=row.last_validated_at if row else None,
                last_validation_status=row.last_validation_status if row else None,
                notes=row.notes if row else None,
            )
        )
    return ProvidersListResponse(providers=providers)


@router.put("/{provider}", response_model=SimpleStatusResponse)
async def save_provider_key(
    provider: str,
    body: SaveKeyRequest,
    db: DbSession,
) -> SimpleStatusResponse:
    """Salva (ou atualiza) a chave de um provider no keyring + DB + audit."""
    valid = _validate_provider_param(provider)
    try:
        keys_service.save_api_key(valid, body.key)
    except keys_service.EmptyKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await _upsert_api_key_row(db, provider=valid, is_configured=True)
    await _log_audit(db, action="configure_api_key", provider=valid)
    await db.commit()
    logger.info("Provider configurado", provider=valid)

    return SimpleStatusResponse(provider=valid, is_configured=True)


@router.delete("/{provider}", response_model=SimpleStatusResponse)
async def delete_provider_key(
    provider: str,
    db: DbSession,
) -> SimpleStatusResponse:
    """Remove a chave do keyring + atualiza DB + audit. Idempotente."""
    valid = _validate_provider_param(provider)
    keys_service.delete_api_key(valid)

    await _upsert_api_key_row(db, provider=valid, is_configured=False)
    await _log_audit(db, action="delete_api_key", provider=valid)
    await db.commit()
    logger.info("Provider removido", provider=valid)

    return SimpleStatusResponse(provider=valid, is_configured=False)


@router.post("/{provider}/test", response_model=TestKeyResponse)
async def test_provider_key(
    provider: str,
    body: TestKeyRequest,
    db: DbSession,
) -> TestKeyResponse:
    """
    Testa conectividade da chave do provider (chamada cheap GET /models).

    Body com `key` preenchido testa o valor novo SEM salvar (use antes
    de PUT). Body com `key=null` testa a chave já no keyring.

    Resultado é persistido em `api_keys.last_validated_at` +
    `last_validation_status` quando a chave estava no keyring.
    Nunca persiste o valor da chave em si.
    """
    valid = _validate_provider_param(provider)

    # Decidir qual chave testar
    if body.key is not None and body.key.strip():
        key_to_test = body.key.strip()
        from_keyring = False
    else:
        stored = keys_service.get_api_key(valid)
        if not stored:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Nenhuma chave salva pra {valid}. "
                    f"Envie 'key' no body pra testar um valor novo."
                ),
            )
        key_to_test = stored
        from_keyring = True

    result = await key_validator.validate_api_key(valid, key_to_test)

    # Persiste resultado SE a chave testada era a do keyring (test sem
    # body=key). Se foi pré-validação de um valor novo, não toca no DB.
    if from_keyring:
        row = (
            (await db.execute(select(ApiKey).where(ApiKey.provider == valid)))
            .scalars()
            .one_or_none()
        )
        if row is not None:
            row.last_validated_at = utcnow()
            row.last_validation_status = result.status
            row.notes = result.message
        await _log_audit(db, action="test_api_key", provider=valid)
        await db.commit()

    return TestKeyResponse(
        provider=valid,
        status=result.status,
        message=result.message,
        http_status=result.http_status,
        latency_ms=result.latency_ms,
    )
