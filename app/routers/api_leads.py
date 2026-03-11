from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


def _get_db():
    from app.main import get_db_service
    return get_db_service()


def _get_sheets():
    from app.main import get_sheets_service
    return get_sheets_service()


@router.get("/stats")
def get_stats():
    db = _get_db()
    return db.get_stats()


@router.get("/analises/stats")
def get_analysis_stats():
    db = _get_db()
    return db.get_analysis_stats()


@router.get("/estatisticas")
def get_estatisticas():
    db = _get_db()
    return db.get_estatisticas()


@router.get("/leads")
def list_leads(
    status: Optional[str] = Query(default=None),
    segmento: Optional[str] = Query(default=None),
    prioridade: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    db = _get_db()
    return db.list_leads(
        status=status or None,
        segmento=segmento or None,
        prioridade=prioridade or None,
        search=search or None,
        page=page,
        page_size=page_size,
    )


@router.get("/leads/{lead_id}")
def get_lead(lead_id: str):
    db = _get_db()
    lead = db.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.get("/leads/{lead_id}/atividades")
def get_lead_activities(lead_id: str):
    db = _get_db()
    if db.get_lead(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return db.get_lead_activities(lead_id)


@router.get("/leads/{lead_id}/perfil")
def get_lead_perfil(lead_id: str):
    """Perfil de comunicação do lead: breakdown de tipos de mensagem e uso de áudio."""
    db = _get_db()
    if db.get_lead(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return db.get_perfil_comunicacao(lead_id)


@router.get("/ia/stats")
def get_ia_stats():
    """Estatísticas da Inteligência IA — independente dos dados dos leads."""
    db = _get_db()
    return db.get_ia_stats()


@router.post("/leads", status_code=201)
def create_lead(body: dict):
    if not body.get("nome"):
        raise HTTPException(status_code=422, detail="Campo 'nome' é obrigatório")
    db = _get_db()
    lead_id = db.create_lead_from_dashboard(body)
    return {"lead_id": lead_id, "ok": True}


@router.put("/leads/{lead_id}")
def update_lead(lead_id: str, body: dict):
    db = _get_db()
    if db.get_lead(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    ok = db.update_lead_from_dashboard(lead_id, body)
    if ok:
        try:
            updated_lead = db.get_lead(lead_id)
            if updated_lead:
                sheets = _get_sheets()
                sheets.sync_lead(updated_lead)
        except Exception:
            logger.warning("sync_lead falhou após update do dashboard | lead_id=%s", lead_id, exc_info=True)
    return {"ok": ok}


@router.delete("/leads/{lead_id}")
def delete_lead(lead_id: str):
    db = _get_db()
    if db.get_lead(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete_lead(lead_id)
    return {"ok": True}


@router.post("/leads/bulk", status_code=200)
def bulk_create_leads(body: dict):
    """Importa múltiplos leads de uma vez.

    Body: {"leads": [{"nome": "...", "cidade": "...", ...}, ...]}
    Cada lead deve ter pelo menos 'nome'.
    Usa upsert com deduplicação — safe para rodar mais de uma vez.
    """
    from datetime import datetime, timezone

    leads_data = body.get("leads")
    if not isinstance(leads_data, list) or not leads_data:
        raise HTTPException(status_code=422, detail="'leads' deve ser uma lista não vazia")

    db = _get_db()
    now = datetime.now(timezone.utc)

    created, updated, needs_review, errors = [], [], [], []

    for i, lead in enumerate(leads_data):
        if not isinstance(lead, dict):
            errors.append({"index": i, "reason": "item não é um objeto"})
            continue
        if not (lead.get("nome") or "").strip():
            errors.append({"index": i, "reason": "campo 'nome' é obrigatório", "data": lead})
            continue
        try:
            lead_id, review_needed, candidates = db.upsert_lead(
                lead=lead,
                status=lead.get("status") or "novo",
                followup_em=lead.get("proximo_followup_em") or None,
                when=now,
            )
            if review_needed:
                needs_review.append({
                    "index": i,
                    "nome": lead.get("nome"),
                    "candidates": [c.get("nome") for c in (candidates or [])],
                })
            elif lead_id:
                created.append({"lead_id": lead_id, "nome": lead.get("nome")})
        except Exception as exc:
            logger.exception("bulk_create_leads error | index=%d nome=%s", i, lead.get("nome"))
            errors.append({"index": i, "nome": lead.get("nome"), "reason": str(exc)})

    return {
        "ok": True,
        "total": len(leads_data),
        "imported": len(created),
        "needs_review": len(needs_review),
        "errors": len(errors),
        "leads": created,
        "review": needs_review,
        "failed": errors,
    }
