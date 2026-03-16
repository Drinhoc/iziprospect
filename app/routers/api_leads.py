from __future__ import annotations

import logging
from typing import Optional

from datetime import date

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
    temperatura: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    db = _get_db()
    return db.list_leads(
        status=status or None,
        segmento=segmento or None,
        temperatura=temperatura or None,
        search=search or None,
        page=page,
        page_size=page_size,
    )


@router.get("/leads/recontato")
def get_recontato_leads():
    """Leads perdidos com data de recontato chegando hoje ou já vencida."""
    db = _get_db()
    return db.get_recontato_leads()


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


@router.post("/msg-ab/evento", status_code=201)
def registrar_msg_ab_evento(body: dict):
    """Registra um evento de A/B (copiada / respondeu)."""
    db = _get_db()
    db.registrar_msg_ab_evento(
        lead_id=body.get("lead_id", ""),
        variante=body.get("variante", ""),
        segmento=body.get("segmento", ""),
        evento=body.get("evento", ""),
        tipo=body.get("tipo", "inicial"),
    )
    return {"ok": True}


@router.get("/msg-ab/stats")
def get_msg_ab_stats():
    """Estatísticas do teste A/B de mensagem inicial."""
    db = _get_db()
    return db.get_msg_ab_stats()


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


# ---------------------------------------------------------------------------
# Auto-send: status e histórico
# ---------------------------------------------------------------------------

@router.post("/auto-send/toggle")
def toggle_auto_send():
    """Liga/desliga o auto-send. O valor persiste no banco (sobrescreve .env)."""
    from app.config import settings as _settings
    db = _get_db()
    current = db.get_setting("auto_send_enabled")
    # Se nunca foi salvo no DB, usa o valor do .env como base
    if current == "":
        current = "true" if _settings.auto_send_enabled else "false"
    new_value = "false" if current == "true" else "true"
    db.set_setting("auto_send_enabled", new_value)
    return {"enabled": new_value == "true"}


@router.get("/auto-send/status")
def get_auto_send_status():
    """Retorna status atual do auto-send: habilitado, limite, enviados hoje, próximos elegíveis."""
    from app.config import settings as _settings
    db = _get_db()
    today = date.today().isoformat()
    db_flag = db.get_setting("auto_send_enabled")
    enabled = (db_flag == "true") if db_flag else _settings.auto_send_enabled
    sent_today = db.count_auto_sent_today(today)
    next_candidates = db.get_leads_for_auto_send(limit=5)
    return {
        "enabled": enabled,
        "diario_max": _settings.auto_send_diario_max,
        "hora_inicio": _settings.auto_send_hora_inicio,
        "hora_fim": _settings.auto_send_hora_fim,
        "intervalo_min_s": _settings.auto_send_intervalo_min_s,
        "intervalo_max_s": _settings.auto_send_intervalo_max_s,
        "enviados_hoje": sent_today,
        "restantes_hoje": max(0, _settings.auto_send_diario_max - sent_today),
        "proximos_leads": [
            {
                "lead_id": l["lead_id"],
                "nome": l.get("nome"),
                "segmento": l.get("segmento"),
                "data_criacao": l.get("data_criacao"),
            }
            for l in next_candidates
        ],
    }


@router.get("/auto-send/historico")
def get_auto_send_historico():
    """Retorna os últimos envios automáticos (via msg_ab_eventos evento=auto_enviada)."""
    db = _get_db()
    conn = db._conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT e.lead_id, l.nome, l.segmento, e.variante, e.data_hora
                   FROM msg_ab_eventos e
                   LEFT JOIN leads l ON l.lead_id = e.lead_id
                   WHERE e.evento = 'auto_enviada'
                   ORDER BY e.data_hora DESC
                   LIMIT 50""",
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        db._put(conn)
    return {"historico": rows, "total": len(rows)}
