"""api_admin.py — REST API do painel de administração IziDesk.

Autenticação: header X-Admin-Token deve conter o valor de ADMIN_TOKEN.
Todas as rotas retornam JSON.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _require_admin(x_admin_token: Optional[str] = Header(default=None)) -> None:
    from app.config import settings
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden: token inválido ou ausente")


def _db():
    from app.main import get_db_service
    return get_db_service()


def _evo():
    from app.main import evolution_service
    return evolution_service


def _global_key() -> str:
    from app.config import settings
    if not settings.evolution_global_api_key:
        raise HTTPException(status_code=503, detail="EVOLUTION_GLOBAL_API_KEY não configurado")
    return settings.evolution_global_api_key


def _webhook_url() -> str:
    from app.config import settings
    base = (settings.evolution_api_url or "").rstrip("/")
    # A URL do webhook aponta para o nosso próprio servidor
    # O cliente deve configurar WEBHOOK_BASE_URL no .env
    import os
    return os.getenv("WEBHOOK_BASE_URL", "").rstrip("/") + "/webhook/evolution"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TenantCreate(BaseModel):
    id: str                              # slug: letras minúsculas, números, underscore
    nome: str
    plano: str = "basico"
    evolution_instance: str = ""
    evolution_api_key: str = ""
    criar_instancia: bool = False        # se True, cria instância no Evolution automaticamente


class TenantUpdate(BaseModel):
    nome: Optional[str] = None
    plano: Optional[str] = None
    evolution_instance: Optional[str] = None
    evolution_api_key: Optional[str] = None
    ativo: Optional[bool] = None


# ---------------------------------------------------------------------------
# Endpoints — tenants
# ---------------------------------------------------------------------------

@router.get("/tenants", dependencies=[Depends(_require_admin)])
async def list_tenants():
    return await asyncio.to_thread(_db().list_tenants)


@router.post("/tenants", dependencies=[Depends(_require_admin)])
async def create_tenant(body: TenantCreate):
    if not re.match(r'^[a-z0-9_]{1,63}$', body.id):
        raise HTTPException(400, "tenant id deve conter apenas letras minúsculas, números e underscore")

    db = _db()

    # Cria registro na tabela public.tenants
    try:
        tenant = await asyncio.to_thread(
            db.create_tenant,
            body.id, body.nome, body.plano,
            body.evolution_instance, body.evolution_api_key,
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(409, f"Tenant '{body.id}' já existe")
        raise HTTPException(500, str(e))

    # Cria schema isolado no PostgreSQL
    try:
        await asyncio.to_thread(db.create_tenant_schema, body.id)
    except Exception as e:
        logger.warning("create_tenant_schema falhou para %s: %s", body.id, e)

    # Cria instância no Evolution API (opcional)
    if body.criar_instancia and body.evolution_instance:
        try:
            gkey = _global_key()
            await _evo().create_instance(body.evolution_instance, _webhook_url(), gkey)
            logger.info("instância Evolution criada: %s", body.evolution_instance)
        except Exception as e:
            logger.warning("create_instance Evolution falhou: %s", e)

    return tenant


@router.get("/tenants/{tenant_id}", dependencies=[Depends(_require_admin)])
async def get_tenant(tenant_id: str):
    tenant = await asyncio.to_thread(_db().get_tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant não encontrado")
    return tenant


@router.patch("/tenants/{tenant_id}", dependencies=[Depends(_require_admin)])
async def update_tenant(tenant_id: str, body: TenantUpdate):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    tenant = await asyncio.to_thread(_db().update_tenant, tenant_id, fields)
    if not tenant:
        raise HTTPException(404, "Tenant não encontrado")
    return tenant


@router.delete("/tenants/{tenant_id}", dependencies=[Depends(_require_admin)])
async def delete_tenant(tenant_id: str):
    db = _db()
    tenant = await asyncio.to_thread(db.get_tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant não encontrado")

    # Remove instância do Evolution se existir
    if tenant.get("evolution_instance"):
        try:
            gkey = _global_key()
            await _evo().delete_instance(tenant["evolution_instance"], gkey)
        except Exception as e:
            logger.warning("delete_instance Evolution falhou: %s", e)

    await asyncio.to_thread(db.drop_tenant_schema, tenant_id)
    return {"ok": True, "deleted": tenant_id}


# ---------------------------------------------------------------------------
# Endpoints — stats
# ---------------------------------------------------------------------------

@router.get("/overview", dependencies=[Depends(_require_admin)])
async def admin_overview():
    return await asyncio.to_thread(_db().get_admin_overview)


# ---------------------------------------------------------------------------
# Endpoints — Evolution (WhatsApp por tenant)
# ---------------------------------------------------------------------------

async def _get_tenant_or_404(tenant_id: str):
    tenant = await asyncio.to_thread(_db().get_tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant não encontrado")
    return tenant


@router.post("/tenants/{tenant_id}/instance/criar", dependencies=[Depends(_require_admin)])
async def criar_instancia(tenant_id: str):
    tenant = await _get_tenant_or_404(tenant_id)
    if not tenant.get("evolution_instance"):
        raise HTTPException(400, "evolution_instance não configurado no tenant")
    gkey = _global_key()
    result = await _evo().create_instance(tenant["evolution_instance"], _webhook_url(), gkey)
    return {"ok": True, "result": result}


@router.get("/tenants/{tenant_id}/instance/qr", dependencies=[Depends(_require_admin)])
async def get_qr(tenant_id: str):
    tenant = await _get_tenant_or_404(tenant_id)
    if not tenant.get("evolution_instance"):
        raise HTTPException(400, "evolution_instance não configurado")
    gkey = _global_key()
    qr = await _evo().get_qr_code(tenant["evolution_instance"], gkey)
    if not qr:
        return {"qr": None, "mensagem": "Instância já conectada ou QR não disponível"}
    return {"qr": qr}


@router.get("/tenants/{tenant_id}/instance/status", dependencies=[Depends(_require_admin)])
async def get_status(tenant_id: str):
    tenant = await _get_tenant_or_404(tenant_id)
    if not tenant.get("evolution_instance"):
        return {"status": "sem_instancia"}
    gkey = _global_key()
    status = await _evo().get_instance_status(tenant["evolution_instance"], gkey)
    return {"status": status}


@router.post("/tenants/{tenant_id}/instance/reconectar", dependencies=[Depends(_require_admin)])
async def reconectar(tenant_id: str):
    tenant = await _get_tenant_or_404(tenant_id)
    if not tenant.get("evolution_instance"):
        raise HTTPException(400, "evolution_instance não configurado")
    gkey = _global_key()
    ok = await _evo().reconnect_instance(tenant["evolution_instance"], gkey)
    return {"ok": ok}


@router.delete("/tenants/{tenant_id}/instance", dependencies=[Depends(_require_admin)])
async def deletar_instancia(tenant_id: str):
    tenant = await _get_tenant_or_404(tenant_id)
    if not tenant.get("evolution_instance"):
        raise HTTPException(400, "evolution_instance não configurado")
    gkey = _global_key()
    ok = await _evo().delete_instance(tenant["evolution_instance"], gkey)
    return {"ok": ok}
