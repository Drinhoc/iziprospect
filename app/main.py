from __future__ import annotations

import logging
import re
from typing import Dict

from fastapi import FastAPI, Header, HTTPException
from openai import APIError, RateLimitError

from app.config import settings
from app.services.evolution_service import EvolutionService
from app.services.normalizer import normalize_evolution_payload
from app.services.openai_service import OpenAIService
from app.services.sheets_service import SheetsService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="IziClinic Invisible CRM")

openai_service = OpenAIService(settings.openai_api_key)
evolution_service = EvolutionService(settings.evolution_api_url, settings.evolution_api_key)
sheets_service: SheetsService | None = None


def get_sheets_service() -> SheetsService:
    global sheets_service
    if sheets_service is not None:
        return sheets_service

    if not settings.google_sheets_id:
        raise RuntimeError("GOOGLE_SHEETS_ID is required")

    info = settings.service_account_info()
    sheets_service = SheetsService(info, settings.google_sheets_id)
    return sheets_service


def parse_kv_pairs(raw: str) -> Dict[str, str]:
    matches = re.findall(r"(\w+)=([^\s]+)", raw)
    return {k.lower(): v for k, v in matches}


@app.get("/health")
def health():
    ready = True
    reason = None
    try:
        get_sheets_service()
    except Exception as exc:
        ready = False
        reason = str(exc)
        logger.warning("Health degraded: Sheets not ready (%s)", exc)
    return {"status": "ok", "sheets_ready": ready, "reason": reason}


@app.post("/webhook/evolution")
async def evolution_webhook(payload: dict, x_webhook_secret: str | None = Header(default=None)):
    if settings.evolution_webhook_secret and x_webhook_secret != settings.evolution_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    event = normalize_evolution_payload(payload)
    logger.info(
        "Mensagem recebida | chat_id=%s is_group=%s msg_id=%s msg_type=%s",
        event.chat_id,
        event.is_group,
        event.msg_id,
        event.msg_type,
    )

    if not event.is_group:
        logger.info("ignored: not_group | chat_id=%s", event.chat_id)
        return {"ok": True, "ignored": True, "reason": "not_group"}

    if settings.crm_target_group_id and event.chat_id != settings.crm_target_group_id:
        logger.info("ignored: wrong_group | chat_id=%s target=%s", event.chat_id, settings.crm_target_group_id)
        return {"ok": True, "ignored": True, "reason": "wrong_group"}

    logger.info("processing: crm_group_message | chat_id=%s", event.chat_id)

    try:
        sheets = get_sheets_service()
    except Exception as exc:
        logger.exception("Falha ao inicializar Google Sheets")
        raise HTTPException(status_code=503, detail=f"Sheets unavailable: {exc}") from exc

    if event.msg_id and sheets.activity_exists_by_msg_id(event.msg_id):
        logger.info("Duplicata ignorada para msg_id=%s", event.msg_id)
        return {"ok": True, "duplicate": True}
    if not event.msg_id:
        logger.warning("Mensagem recebida sem msg_id")

    if event.msg_type == "audio" and event.media_url:
        logger.info("Transcrição iniciada para msg_id=%s", event.msg_id)
        try:
            event.raw_text = await openai_service.transcribe_audio_from_url(event.media_url)
            logger.info("Transcrição finalizada para msg_id=%s", event.msg_id)
        except Exception:
            logger.exception("Erro de transcrição para msg_id=%s", event.msg_id)
            sheets.add_review(
                when=event.timestamp,
                mensagem_bruta="",
                cidade_detectada=None,
                nome_detectado=None,
                candidatos=[],
                acao="falha_transcricao",
            )
            return {"ok": True, "partial": True, "reason": "falha_transcricao"}

        if not event.raw_text.strip():
            logger.warning("Transcrição vazia para msg_id=%s", event.msg_id)
            sheets.add_review(
                when=event.timestamp,
                mensagem_bruta="",
                cidade_detectada=None,
                nome_detectado=None,
                candidatos=[],
                acao="falha_transcricao",
            )
            return {"ok": True, "partial": True, "reason": "transcricao_vazia"}

    raw_text = event.raw_text.strip()
    if event.msg_type == "unknown" or (not raw_text and event.msg_type != "audio"):
        logger.warning("Mensagem não processável (tipo/texto inválido). msg_id=%s", event.msg_id)
        sheets.add_review(
            when=event.timestamp,
            mensagem_bruta=raw_text,
            cidade_detectada=None,
            nome_detectado=None,
            candidatos=[],
            acao="mensagem_nao_processavel",
        )
        return {"ok": True, "ignored": True}

    upper = raw_text.upper()

    if upper.startswith("VINCULAR L"):
        lead_id = raw_text.split()[1].strip().upper()
        ok = sheets.bind_latest_activity_to_lead(lead_id)
        return {"ok": ok, "action": "vincular", "lead_id": lead_id}

    if upper.startswith("CORRIGIR L") or upper.startswith("SET L"):
        parts = raw_text.split(maxsplit=2)
        if len(parts) < 3:
            raise HTTPException(status_code=400, detail="Comando incompleto")
        lead_id = parts[1].upper()
        fields = parse_kv_pairs(parts[2])
        ok = sheets.update_lead_fields(lead_id, fields)
        return {"ok": ok, "action": "update_fields", "lead_id": lead_id, "fields": fields}

    try:
        extracted = openai_service.extract_structured_data(raw_text)
    except RateLimitError:
        logger.exception("OpenAI rate limit ao extrair dados | msg_id=%s", event.msg_id)
        return {"ok": True, "deferred": True, "reason": "openai_unavailable"}
    except APIError:
        logger.exception("OpenAI API error ao extrair dados | msg_id=%s", event.msg_id)
        return {"ok": True, "deferred": True, "reason": "openai_unavailable"}
    except Exception:
        logger.exception("Erro inesperado na OpenAI ao extrair dados | msg_id=%s", event.msg_id)
        return {"ok": True, "deferred": True, "reason": "openai_unavailable"}

    lead_id = sheets.upsert_lead(
        lead=extracted.lead.model_dump(),
        status=extracted.status_sugerido,
        followup_em=extracted.followup_em,
        when=event.timestamp,
    )

    logger.info("Lead resolvido: %s", lead_id or "REVISAR")

    sheets.add_activity(
        when=event.timestamp,
        msg_id=event.msg_id or "",
        lead_id=lead_id,
        tipo=extracted.activity.tipo,
        canal="whatsapp_group" if event.is_group else "whatsapp",
        mensagem_bruta=raw_text,
        resumo=extracted.activity.resumo,
        followup_em=extracted.followup_em,
    )

    if not lead_id:
        logger.info("Lead em revisão para msg_id=%s", event.msg_id)
        sheets.add_review(
            when=event.timestamp,
            mensagem_bruta=raw_text,
            cidade_detectada=extracted.lead.cidade,
            nome_detectado=extracted.lead.nome,
            candidatos=[],
            acao="lead_id_nao_resolvido",
        )

    try:
        await evolution_service.send_confirmation(event.chat_id, f"CRM atualizado para {lead_id or 'REVISAR'}")
    except Exception:
        logger.warning("Erro de confirmação no WhatsApp para msg_id=%s", event.msg_id, exc_info=True)

    return {
        "ok": True,
        "lead_id": lead_id,
        "intent": extracted.intent,
        "msg_type": event.msg_type,
    }
