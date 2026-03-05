from __future__ import annotations

import re
from typing import Dict

from fastapi import FastAPI, Header, HTTPException

from app.config import settings
from app.services.evolution_service import EvolutionService
from app.services.normalizer import normalize_evolution_payload
from app.services.openai_service import OpenAIService
from app.services.sheets_service import SheetsService

app = FastAPI(title="IziClinic Invisible CRM")

openai_service = OpenAIService(settings.openai_api_key)
sheets_service = SheetsService(settings.service_account_info(), settings.google_sheets_id)
evolution_service = EvolutionService(settings.evolution_api_url, settings.evolution_api_key)


def parse_kv_pairs(raw: str) -> Dict[str, str]:
    matches = re.findall(r"(\w+)=([^\s]+)", raw)
    return {k.lower(): v for k, v in matches}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook/evolution")
async def evolution_webhook(payload: dict, x_webhook_secret: str | None = Header(default=None)):
    if settings.evolution_webhook_secret and x_webhook_secret != settings.evolution_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    event = normalize_evolution_payload(payload)

    if event.msg_type == "audio" and event.media_url:
        event.raw_text = await openai_service.transcribe_audio_from_url(event.media_url)

    raw_text = event.raw_text.strip()
    upper = raw_text.upper()

    if upper.startswith("VINCULAR L"):
        lead_id = raw_text.split()[1].strip().upper()
        ok = sheets_service.bind_latest_activity_to_lead(lead_id)
        return {"ok": ok, "action": "vincular", "lead_id": lead_id}

    if upper.startswith("CORRIGIR L") or upper.startswith("SET L"):
        parts = raw_text.split(maxsplit=2)
        if len(parts) < 3:
            raise HTTPException(status_code=400, detail="Comando incompleto")
        lead_id = parts[1].upper()
        fields = parse_kv_pairs(parts[2])
        ok = sheets_service.update_lead_fields(lead_id, fields)
        return {"ok": ok, "action": "update_fields", "lead_id": lead_id, "fields": fields}

    extracted = openai_service.extract_structured_data(raw_text)

    lead_id = sheets_service.upsert_lead(
        lead=extracted.lead.model_dump(),
        status=extracted.status_sugerido,
        followup_em=extracted.followup_em,
        when=event.timestamp,
    )

    sheets_service.add_activity(
        when=event.timestamp,
        lead_id=lead_id,
        tipo=extracted.activity.tipo,
        canal="whatsapp_group" if event.is_group else "whatsapp",
        mensagem_bruta=raw_text,
        resumo=extracted.activity.resumo,
        followup_em=extracted.followup_em,
    )

    if not lead_id:
        sheets_service.add_review(
            when=event.timestamp,
            mensagem_bruta=raw_text,
            cidade_detectada=extracted.lead.cidade,
            nome_detectado=extracted.lead.nome,
            candidatos=[],
            acao="lead_id_nao_resolvido",
        )

    await evolution_service.send_confirmation(event.chat_id, f"CRM atualizado para {lead_id or 'REVISAR'}")

    return {
        "ok": True,
        "lead_id": lead_id,
        "intent": extracted.intent,
        "msg_type": event.msg_type,
    }
