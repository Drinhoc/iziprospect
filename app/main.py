from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict

from fastapi import FastAPI, Header, HTTPException
from openai import APIError, RateLimitError

from app.config import settings
from app.services.crm_interpreter import extract_phone, interpret_crm_message
from app.services.evolution_service import EvolutionService
from app.services.normalizer import normalize_evolution_payload
from app.services.openai_service import AudioResolveError, OpenAIService
from app.services.sheets_service import SheetsService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)

INTENT_HINTS = {"novo", "update", "perdido", "fechado", "corrigir", "vincular", "set"}
VAGUE_TERMS = {"ok", "oi", "opa", "blz", "teste", "testando", "hello", "ola", "olá"}
PHONE_PATTERN = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}")

app = FastAPI(title="IziClinic Invisible CRM")

openai_service = OpenAIService(settings.openai_api_key)
evolution_service = EvolutionService(
    settings.evolution_api_url,
    settings.evolution_api_key,
    settings.evolution_instance_name,
)
sheets_service: SheetsService | None = None

# Limita o número de processamentos simultâneos de webhook para evitar
# sobrecarga no Google Sheets e no OpenAI e prevenir race conditions.
_webhook_semaphore = asyncio.Semaphore(5)


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


def _normalize_group_id(value: str | None) -> str:
    raw = (value or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    if "@g.us" in raw:
        idx = raw.find("@g.us")
        start = idx
        while start > 0 and raw[start - 1].isdigit():
            start -= 1
        if start < idx:
            return raw[start : idx + len("@g.us")]

    only_digits = "".join(ch for ch in raw if ch.isdigit())
    if only_digits:
        return f"{only_digits}@g.us"
    return ""


def is_authorized_crm_group(chat_id: str, is_group: bool) -> tuple[bool, str]:
    if not is_group:
        return False, "not_group"

    expected = _normalize_group_id(settings.crm_target_group_id)
    current = _normalize_group_id(chat_id)

    if not expected:
        return False, "unauthorized_group_missing_config"
    if current != expected:
        return False, "unauthorized_group"
    return True, "authorized"

def is_message_too_vague(raw_text: str) -> bool:
    text = (raw_text or "").strip().lower()
    if not text:
        return True

    has_phone = bool(PHONE_PATTERN.search(text))
    has_intent_hint = any(h in text for h in INTENT_HINTS)
    short = len(text) < 12

    if has_phone or has_intent_hint:
        return False

    if short:
        compact = re.sub(r"[^a-záéíóúàâêôãõç0-9\s]", "", text).strip()
        if compact in VAGUE_TERMS or len(compact.split()) <= 3:
            return True
    return False


def extract_name_before_phone(raw_text: str) -> str | None:
    text = (raw_text or "").strip()
    match = PHONE_PATTERN.search(text)
    if not match:
        return None
    candidate = text[: match.start()].strip(" ,.;:-")
    candidate = re.sub(r"\s+", " ", candidate)
    if len(candidate) < 3:
        return None
    return candidate


def factual_summary(raw_text: str, nome: str | None, telefone: str | None, segmento: str | None, llm_summary: str) -> str:
    base = (llm_summary or "").strip()
    if base and len(base) <= 220 and not any(x in base.lower() for x in ["provavelmente", "parece que talvez"]):
        return base

    chunks = []
    if nome:
        chunks.append(f"nome provável '{nome}'")
    if telefone:
        chunks.append(f"telefone {telefone}")
    if segmento:
        chunks.append(f"segmento {segmento}")

    if chunks:
        return "Lead informado com " + ", ".join(chunks) + "."

    tiny = re.sub(r"\s+", " ", raw_text).strip()
    return f"Mensagem recebida: {tiny[:180]}"


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
        "Mensagem recebida | chat_id=%s is_group=%s msg_id=%s msg_type=%s mimetype=%s",
        event.chat_id,
        event.is_group,
        event.msg_id,
        event.msg_type,
        event.media_mimetype,
    )

    authorized, reason = is_authorized_crm_group(event.chat_id, event.is_group)
    if not authorized:
        if reason == "not_group":
            logger.info("ignored: not_group | chat_id=%s", event.chat_id)
            return {"ok": True, "ignored": True, "reason": "not_group"}

        expected = _normalize_group_id(settings.crm_target_group_id)
        if reason == "unauthorized_group_missing_config":
            logger.warning(
                "ignored: unauthorized_group | chat_id=%s expected=%s (CRM_TARGET_GROUP_ID missing)",
                event.chat_id,
                expected,
            )
            return {"ok": True, "ignored": True, "reason": "unauthorized_group"}

        logger.info("ignored: unauthorized_group | chat_id=%s expected=%s", event.chat_id, expected)
        return {"ok": True, "ignored": True, "reason": "unauthorized_group"}

    if event.from_me and event.raw_text.startswith("."):
        logger.info("ignored: bot_message | msg_id=%s", event.msg_id)
        return {"ok": True, "ignored": True, "reason": "bot_message"}

    logger.info("processing: crm_group_message | chat_id=%s", _normalize_group_id(event.chat_id))

    # Limita processamentos simultâneos para proteger o Sheets e o OpenAI
    async with _webhook_semaphore:
        try:
            sheets = await asyncio.to_thread(get_sheets_service)
        except Exception as exc:
            logger.exception("Falha ao inicializar Google Sheets")
            raise HTTPException(status_code=503, detail=f"Sheets unavailable: {exc}") from exc

        if event.msg_id and await asyncio.to_thread(sheets.activity_exists_by_msg_id, event.msg_id):
            logger.info("duplicate webhook ignored | msg_id=%s", event.msg_id)
            return {"ok": True, "duplicate": True}
        if not event.msg_id:
            logger.warning("Mensagem recebida sem msg_id")

        # Fallback: quando o toggle "Webhook Based64" do Evolution tem bug e não envia
        # base64 no payload, busca via API getBase64FromMediaMessage antes de tentar
        # baixar o arquivo .enc criptografado (que causaria AudioResolveError).
        if event.msg_type == "audio" and not event.media_base64:
            if not settings.evolution_instance_name:
                logger.warning(
                    "fetch_audio_base64 ignorado: EVOLUTION_INSTANCE_NAME não configurado | msg_id=%s",
                    event.msg_id,
                )
            elif not event.raw_msg_key or not event.raw_message_obj:
                logger.warning(
                    "fetch_audio_base64 ignorado: raw_msg_key=%s raw_message_obj=%s | msg_id=%s",
                    bool(event.raw_msg_key),
                    bool(event.raw_message_obj),
                    event.msg_id,
                )
            else:
                logger.info("Tentando fetch_audio_base64 via API | msg_id=%s", event.msg_id)
                fetched_b64 = await evolution_service.fetch_audio_base64(
                    instance_name=settings.evolution_instance_name,
                    msg_key=event.raw_msg_key,
                    message_obj=event.raw_message_obj,
                )
                if fetched_b64:
                    event.media_base64 = fetched_b64
                    logger.info("fetch_audio_base64 OK | msg_id=%s", event.msg_id)
                else:
                    logger.warning("fetch_audio_base64 falhou, tentará via URL | msg_id=%s", event.msg_id)

        if event.msg_type == "audio" and (event.media_url or event.media_base64):
            if event.media_base64:
                fonte = "base64"
            elif event.media_key:
                fonte = "enc+mediaKey"
            else:
                fonte = "url"
            logger.info(
                "Transcrição iniciada para msg_id=%s | fonte=%s | media_key=%s",
                event.msg_id,
                fonte,
                bool(event.media_key),
            )
            try:
                event.raw_text = await openai_service.transcribe_audio_from_url(
                    event.media_url, event.media_mimetype, event.media_base64, event.media_key
                )
                logger.info("Transcrição finalizada para msg_id=%s", event.msg_id)
            except AudioResolveError as exc:
                logger.exception("falha_transcricao | reason=%s msg_id=%s", exc.reason, event.msg_id)
                await asyncio.to_thread(
                    sheets.add_review,
                    event.timestamp, "", None, None, [], exc.reason,
                )
                return {"ok": True, "partial": True, "reason": exc.reason}
            except Exception:
                logger.exception("falha_transcricao | reason=falha_transcricao msg_id=%s", event.msg_id)
                await asyncio.to_thread(
                    sheets.add_review,
                    event.timestamp, "", None, None, [], "falha_transcricao",
                )
                return {"ok": True, "partial": True, "reason": "falha_transcricao"}

            if not event.raw_text.strip():
                logger.warning("Transcrição vazia para msg_id=%s", event.msg_id)
                await asyncio.to_thread(
                    sheets.add_review,
                    event.timestamp, "", None, None, [], "falha_transcricao",
                )
                return {"ok": True, "partial": True, "reason": "transcricao_vazia"}

        raw_text = event.raw_text.strip()
        if event.msg_type == "unknown" or (not raw_text and event.msg_type != "audio"):
            logger.warning("Mensagem não processável (tipo/texto inválido). msg_id=%s", event.msg_id)
            await asyncio.to_thread(
                sheets.add_review,
                event.timestamp, raw_text, None, None, [], "mensagem_nao_processavel",
            )
            return {"ok": True, "ignored": True}

        if is_message_too_vague(raw_text):
            logger.info("ignored: message_too_vague | msg_id=%s", event.msg_id)
            return {"ok": True, "ignored": True, "reason": "message_too_vague"}

        upper = raw_text.upper()

        if upper.startswith("VINCULAR L"):
            lead_id = raw_text.split()[1].strip().upper()
            ok = await asyncio.to_thread(sheets.bind_latest_activity_to_lead, lead_id)
            return {"ok": ok, "action": "vincular", "lead_id": lead_id}

        if upper.startswith("CORRIGIR L") or upper.startswith("SET L"):
            parts = raw_text.split(maxsplit=2)
            if len(parts) < 3:
                raise HTTPException(status_code=400, detail="Comando incompleto")
            lead_id = parts[1].upper()
            fields = parse_kv_pairs(parts[2])
            ok = await asyncio.to_thread(sheets.update_lead_fields, lead_id, fields)
            return {"ok": ok, "action": "update_fields", "lead_id": lead_id, "fields": fields}

        try:
            extracted = await asyncio.to_thread(openai_service.extract_structured_data, raw_text)
        except RateLimitError:
            logger.exception("openai unavailable | rate_limit | msg_id=%s", event.msg_id)
            return {"ok": True, "deferred": True, "reason": "openai_unavailable"}
        except APIError:
            logger.exception("openai unavailable | api_error | msg_id=%s", event.msg_id)
            return {"ok": True, "deferred": True, "reason": "openai_unavailable"}
        except Exception:
            logger.exception("openai unavailable | unexpected | msg_id=%s", event.msg_id)
            return {"ok": True, "deferred": True, "reason": "openai_unavailable"}

        if not extracted.lead.nome:
            extracted.lead.nome = extract_name_before_phone(raw_text) or None
        if not extracted.intent or extracted.intent not in INTENT_HINTS:
            extracted.intent = "update"

        found_phone = extract_phone(raw_text)
        if found_phone and not extracted.lead.whatsapp:
            extracted.lead.whatsapp = found_phone

        interpretation = interpret_crm_message(
            raw_text=raw_text,
            has_name=bool(extracted.lead.nome),
            has_phone=bool(extracted.lead.whatsapp),
        )
        logger.info(
            "crm_interpretation | action=%s activity=%s confidence=%.2f",
            interpretation.action_type,
            interpretation.activity_type,
            interpretation.confidence,
        )

        if interpretation.followup_em and not extracted.followup_em:
            extracted.followup_em = interpretation.followup_em
        if interpretation.status_sugerido and not extracted.status_sugerido:
            extracted.status_sugerido = interpretation.status_sugerido
        if not extracted.activity.tipo or extracted.activity.tipo == "nota":
            extracted.activity.tipo = interpretation.activity_type

        summary = factual_summary(
            raw_text=raw_text,
            nome=extracted.lead.nome,
            telefone=extracted.lead.whatsapp,
            segmento=extracted.lead.segmento,
            llm_summary=extracted.activity.resumo,
        )
        extracted.activity.resumo = summary

        lead_id = await asyncio.to_thread(
            sheets.upsert_lead,
            extracted.lead.model_dump(),
            extracted.status_sugerido,
            extracted.followup_em,
            event.timestamp,
        )

        if not lead_id and interpretation.action_type in {"registrar_atividade", "registrar_followup", "atualizar_lead"}:
            context_lead_id = await asyncio.to_thread(sheets.latest_linked_lead_id)
            if context_lead_id:
                logger.info("Lead resolvido por contexto da conversa: %s", context_lead_id)
                lead_id = context_lead_id

        logger.info("Lead resolvido: %s", lead_id or "REVISAR")

        await asyncio.to_thread(
            sheets.add_activity,
            event.timestamp,
            event.msg_id or "",
            lead_id,
            extracted.activity.tipo,
            "whatsapp_group" if event.is_group else "whatsapp",
            interpretation.action_type,
            interpretation.confidence,
            event.audio_seconds,
            raw_text,
            extracted.activity.resumo,
            extracted.followup_em,
        )

        if not lead_id:
            logger.info("Lead em revisão para msg_id=%s", event.msg_id)
            await asyncio.to_thread(
                sheets.add_review,
                event.timestamp,
                raw_text,
                extracted.lead.cidade,
                extracted.lead.nome,
                [],
                "lead_id_nao_resolvido",
            )

        if settings.disable_evolution_confirmation:
            logger.info("confirmation skipped | disabled by env")
        else:
            try:
                lead_name = extracted.lead.nome or ""
                lead_label = f"{lead_name} ({lead_id})" if lead_name and lead_id else (lead_id or "REVISAR")
                await evolution_service.send_confirmation(event.chat_id, f". CRM atualizado — {lead_label}")
            except Exception:
                logger.warning("confirmation failed | msg_id=%s", event.msg_id, exc_info=True)

        return {
            "ok": True,
            "lead_id": lead_id,
            "intent": extracted.intent,
            "action_type": interpretation.action_type,
            "msg_type": event.msg_type,
        }
