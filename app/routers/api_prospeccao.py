from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prospeccao", tags=["prospeccao"])

_prospector = None


def _get_db():
    from app.main import get_db_service
    return get_db_service()


def _get_prospector():
    global _prospector
    if _prospector is None:
        from app.services.prospector_service import ProspectorService
        _prospector = ProspectorService(_get_db())
    return _prospector


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BuscarRequest(BaseModel):
    segmento: str
    cidade: str
    fontes: List[str] = ["osm", "telelistas", "apontador"]
    limit: int = 20


class AprovarLoteRequest(BaseModel):
    ids: Optional[List[int]] = None
    apenas_com_whatsapp: bool = False
    busca_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/buscar")
async def buscar_leads(body: BuscarRequest, background_tasks: BackgroundTasks):
    """Start discovery from selected sources. Enrichment runs in background."""
    if not body.segmento.strip():
        raise HTTPException(status_code=422, detail="segmento é obrigatório")
    if not body.cidade.strip():
        raise HTTPException(status_code=422, detail="cidade é obrigatória")

    limit = max(1, min(body.limit, 50))
    fontes = [f for f in body.fontes if f in ("osm", "telelistas", "apontador")]
    if not fontes:
        raise HTTPException(status_code=422, detail="Selecione ao menos uma fonte")

    prospector = _get_prospector()
    result = await prospector.search(body.segmento.strip(), body.cidade.strip(), fontes, limit)

    busca_id = result["busca_id"]
    background_tasks.add_task(prospector.enrich_batch, busca_id)

    return {
        "busca_id": busca_id,
        "total": result["total"],
        "por_fonte": result["por_fonte"],
        "message": f"{result['total']} prospects encontrados. Enriquecimento de WhatsApp em andamento…",
    }


@router.get("/fila")
def list_fila(
    status_revisao: Optional[str] = Query(default=None),
    busca_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    db = _get_db()
    return db.list_prospects(
        status_revisao=status_revisao or None,
        busca_id=busca_id or None,
        page=page,
        page_size=page_size,
    )


@router.get("/contadores")
def get_contadores():
    db = _get_db()
    return db.get_prospect_counts()


@router.get("/status/{busca_id}")
def get_busca_status(busca_id: str):
    """Polling endpoint: returns enrichment progress for a busca."""
    db = _get_db()
    return db.get_prospect_enrich_status(busca_id)


@router.put("/{prospect_id}/aprovar")
def aprovar_prospect(prospect_id: int):
    db = _get_db()
    try:
        lead_id = db.approve_prospect(prospect_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "lead_id": lead_id}


@router.put("/{prospect_id}/descartar")
def descartar_prospect(prospect_id: int):
    db = _get_db()
    p = db.get_prospect(prospect_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Prospect não encontrado")
    db.update_prospect(prospect_id, {"status_revisao": "descartado"})
    return {"ok": True}


@router.post("/aprovar-lote")
def aprovar_lote(body: AprovarLoteRequest):
    db = _get_db()
    aprovados = []
    erros = []

    if body.ids:
        ids = body.ids
    elif body.apenas_com_whatsapp and body.busca_id:
        result = db.list_prospects(status_revisao="pendente", busca_id=body.busca_id, page_size=200)
        ids = [p["id"] for p in result["prospects"] if p.get("whatsapp")]
    else:
        raise HTTPException(status_code=422, detail="Forneça ids ou apenas_com_whatsapp+busca_id")

    for pid in ids:
        try:
            lead_id = db.approve_prospect(pid)
            aprovados.append({"prospect_id": pid, "lead_id": lead_id})
        except Exception as exc:
            erros.append({"prospect_id": pid, "erro": str(exc)})

    return {"aprovados": len(aprovados), "erros": len(erros), "detalhes": aprovados}


class ReEnriquecerRequest(BaseModel):
    busca_id: Optional[str] = None


@router.post("/re-enriquecer")
async def re_enriquecer(body: ReEnriquecerRequest, background_tasks: BackgroundTasks):
    """Re-run WhatsApp enrichment for pending prospects that still have no WhatsApp number.

    Pass busca_id to restrict to a specific search batch, or omit to process all.
    """
    prospector = _get_prospector()
    background_tasks.add_task(prospector.re_enrich_sem_whatsapp, body.busca_id)
    return {
        "ok": True,
        "message": "Varredura de re-enriquecimento iniciada em background.",
        "busca_id": body.busca_id,
    }


@router.delete("/fila/descartados")
def limpar_descartados():
    db = _get_db()
    count = db.delete_discarded_prospects()
    return {"ok": True, "removidos": count}
