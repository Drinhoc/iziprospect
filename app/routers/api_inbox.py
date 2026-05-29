"""api_inbox.py — MVP 2.0: endpoints REST para o inbox WhatsApp.

Expõe CRUD de conversas, listagem de mensagens, ações (resolver/arquivar/
re-analisar) e envio de respostas aprovadas pelo operador.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["inbox"])


# ---------------------------------------------------------------------------
# Dependências locais (lazy para evitar importação circular)
# ---------------------------------------------------------------------------

def _get_db():
    from app.main import get_db_service
    return get_db_service()


def _get_inbox_svc():
    from app.main import get_db_service, evolution_service, openai_service
    from app.services.inbox_service import InboxService
    return InboxService(get_db_service(), openai_service, evolution_service)


# ---------------------------------------------------------------------------
# Schemas de request
# ---------------------------------------------------------------------------

class UpdateConversaBody(BaseModel):
    status: Optional[str] = None
    prioridade: Optional[str] = None
    categoria: Optional[str] = None
    atribuido_a: Optional[str] = None
    lead_id: Optional[str] = None
    resposta_sugerida: Optional[str] = None


class ReplyBody(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/inbox/dashboard")
def get_inbox_dashboard():
    """Dados completos do dashboard inbox-first em uma única chamada."""
    from app.config import settings
    db = _get_db()
    inbox = db.get_inbox_dashboard_stats(settings.default_timezone)
    crm   = db.get_stats()
    inbox["crm_resumo"] = {
        "leads_ativos":    crm.get("leads_ativos",    0),
        "followups_hoje":  crm.get("followups_hoje",  0),
        "criados_semana":  crm.get("criados_semana",  0),
        "by_status":       crm.get("by_status",       {}),
    }
    return inbox


@router.get("/api/inbox/stats")
def get_inbox_stats():
    """Retorna contadores do inbox: abertas, urgentes, não lidas, por categoria."""
    return _get_db().get_inbox_stats()


@router.get("/api/inbox/conversas")
def list_conversas(
    status: str = Query("aberto", description="aberto | resolvido | arquivado | todas"),
    categoria: Optional[str] = Query(None),
    prioridade: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
):
    """Lista conversas com filtros e paginação, ordenadas por prioridade + recência."""
    return _get_db().list_conversas(
        status=status,
        categoria=categoria,
        prioridade=prioridade,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/api/inbox/conversas/{conversa_id}")
def get_conversa(conversa_id: int):
    """Retorna conversa + mensagens e zera contador de não lidas."""
    db = _get_db()
    conversa = db.get_conversa(conversa_id)
    if not conversa:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    db.mark_conversa_read(conversa_id)
    mensagens = db.get_conversa_mensagens(conversa_id)
    return {"conversa": conversa, "mensagens": mensagens}


@router.put("/api/inbox/conversas/{conversa_id}")
def update_conversa(conversa_id: int, body: UpdateConversaBody):
    """Atualiza campos da conversa (status, prioridade, categoria, etc.)."""
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    _get_db().update_conversa(conversa_id, fields)
    return {"ok": True}


@router.post("/api/inbox/conversas/{conversa_id}/resolver")
def resolver_conversa(conversa_id: int):
    """Marca conversa como resolvida."""
    _get_db().update_conversa(conversa_id, {"status": "resolvido"})
    return {"ok": True}


@router.post("/api/inbox/conversas/{conversa_id}/arquivar")
def arquivar_conversa(conversa_id: int):
    """Arquiva conversa (remove do inbox ativo)."""
    _get_db().update_conversa(conversa_id, {"status": "arquivado"})
    return {"ok": True}


@router.post("/api/inbox/conversas/{conversa_id}/reabrir")
def reabrir_conversa(conversa_id: int):
    """Reabre conversa resolvida ou arquivada."""
    _get_db().update_conversa(conversa_id, {"status": "aberto"})
    return {"ok": True}


@router.post("/api/inbox/conversas/{conversa_id}/analisar")
async def analisar_conversa(conversa_id: int):
    """Força nova triagem com IA na conversa e retorna estado atualizado."""
    db = _get_db()
    if not db.get_conversa(conversa_id):
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    svc = _get_inbox_svc()
    await svc._triage_conversa(conversa_id)
    return db.get_conversa(conversa_id)


@router.post("/api/inbox/conversas/{conversa_id}/responder")
async def responder_conversa(conversa_id: int, body: ReplyBody):
    """Envia resposta ao contato via WhatsApp (Evolution API)."""
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Texto não pode ser vazio")
    svc = _get_inbox_svc()
    ok = await svc.send_reply(conversa_id, body.text.strip())
    if not ok:
        raise HTTPException(status_code=502, detail="Falha ao enviar via WhatsApp")
    return {"ok": True}
