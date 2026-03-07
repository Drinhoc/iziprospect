from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


def _get_db():
    from app.main import get_db_service
    return get_db_service()


@router.get("/stats")
def get_stats():
    db = _get_db()
    return db.get_stats()


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
    return {"ok": ok}


@router.delete("/leads/{lead_id}")
def delete_lead(lead_id: str):
    db = _get_db()
    if db.get_lead(lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete_lead(lead_id)
    return {"ok": True}
