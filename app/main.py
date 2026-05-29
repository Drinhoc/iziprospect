from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict

import pathlib

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from openai import APIError, RateLimitError

from app.config import settings
from app.services.crm_interpreter import (
    detect_bulk_first_contact,
    detect_followup_command,
    detect_micro_update,
    detect_query_intent,
    extract_phone,
    extract_status_override,
    interpret_crm_message,
)
from app.services.db_service import DBService, TenantDBService
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

# Static files and UI routers
_STATIC_DIR = pathlib.Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

from app.routers import api_leads, api_prospeccao, api_inbox, dashboard_ui, api_admin, admin_ui  # noqa: E402
app.include_router(api_leads.router)
app.include_router(api_prospeccao.router)
app.include_router(api_inbox.router)
app.include_router(dashboard_ui.router)
app.include_router(api_admin.router)
app.include_router(admin_ui.router)

# Cache de TenantDBService por tenant_id (compartilha pool com db_service global)
_tenant_db_cache: Dict[str, TenantDBService] = {}


def get_tenant_db_service(tenant_id: str) -> TenantDBService:
    if tenant_id not in _tenant_db_cache:
        _tenant_db_cache[tenant_id] = TenantDBService.from_pool(
            get_db_service()._pool, tenant_id
        )
    return _tenant_db_cache[tenant_id]

openai_service = OpenAIService(settings.openai_api_key)
evolution_service = EvolutionService(
    settings.evolution_api_url,
    settings.evolution_api_key,
    settings.evolution_instance_name,
)
sheets_service: SheetsService | None = None
db_service: DBService | None = None

# Limita o número de processamentos simultâneos de webhook para evitar
# sobrecarga no Sheets/OpenAI e prevenir race conditions.
_webhook_semaphore = asyncio.Semaphore(5)

def get_db_service() -> DBService:
    global db_service
    if db_service is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is required")
        db_service = DBService(settings.database_url)
    return db_service


def get_sheets_service() -> SheetsService:
    global sheets_service
    if sheets_service is not None:
        return sheets_service

    if not settings.google_sheets_id:
        raise RuntimeError("GOOGLE_SHEETS_ID is required")

    info = settings.service_account_info()
    sheets_service = SheetsService(info, settings.google_sheets_id)
    return sheets_service


@app.on_event("startup")
async def _create_public_tables() -> None:
    """Cria a tabela public.tenants para multi-tenancy."""
    try:
        db = get_db_service()
        await asyncio.to_thread(db.create_public_tables)
    except Exception:
        logger.warning("create_public_tables falhou — não crítico", exc_info=True)


@app.on_event("startup")
async def _create_inbox_tables() -> None:
    """Garante que as tabelas do MVP 2.0 Inbox existam no banco."""
    try:
        db = get_db_service()
        await asyncio.to_thread(db.create_inbox_tables)
    except Exception:
        logger.warning("create_inbox_tables falhou — não crítico", exc_info=True)


@app.on_event("startup")
async def _migrate_em_contato() -> None:
    """One-time migration: 'em contato' → '1º contato'."""
    try:
        db = get_db_service()
        await asyncio.to_thread(db.migrate_em_contato_to_primeiro_contato)
    except Exception:
        logger.warning("migrate_em_contato falhou — não crítico", exc_info=True)


@app.on_event("startup")
async def _seed_db_from_sheets() -> None:
    """Na primeira subida, importa leads e atividades existentes do Sheets → PostgreSQL."""
    try:
        db = get_db_service()
        if db.is_seeded():
            logger.info("db_seed: já existem dados, seeding ignorado")
            return
        sheets = await asyncio.to_thread(get_sheets_service)
        leads = await asyncio.to_thread(sheets.all_leads)
        activities = await asyncio.to_thread(sheets.all_activities)
        await asyncio.to_thread(db.seed, leads, activities)
    except Exception:
        logger.warning("db_seed falhou — não crítico", exc_info=True)




@app.on_event("startup")
async def _start_daily_summary_loop() -> None:
    asyncio.create_task(_daily_summary_loop())


@app.on_event("startup")
async def _start_followup_reminder_loop() -> None:
    asyncio.create_task(_followup_reminder_loop())


@app.on_event("startup")
async def _start_expire_first_contact_loop() -> None:
    asyncio.create_task(_expire_first_contact_loop())


@app.on_event("startup")
async def _start_auto_sender_loop() -> None:
    asyncio.create_task(_auto_sender_loop())


async def _auto_sender_loop() -> None:
    """Envia 1 lead por ciclo respeitando janela horária e limite diário.

    Ciclo:
    1. Dorme 300s (5 min) base entre verificações — com apenas 7 envios/dia
       e intervalo mínimo de 3 min entre eles, 5 min é mais que suficiente.
    2. Verifica se auto_send está habilitado (DB tem prioridade sobre .env).
    3. Verifica se está dentro da janela horária configurada.
    4. Tenta enviar 1 lead via AutoSender.
    5. Se enviou: dorme intervalo aleatório (MIN–MAX segundos) antes da próxima tentativa.
    """
    from app.services.auto_sender import AutoSender
    import random

    while True:
        await asyncio.sleep(300)
        try:
            # Inbox mode é inbound puro — nunca enviar mensagens ativas
            if settings.inbox_mode_enabled:
                continue

            db = get_db_service()
            # DB tem prioridade: toggle do dashboard sobrescreve .env
            db_flag = db.get_setting("auto_send_enabled")
            if db_flag:
                enabled = db_flag == "true"
            else:
                enabled = settings.auto_send_enabled
            if not enabled:
                continue

            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            now = _dt.now(ZoneInfo(settings.default_timezone))

            if not (settings.auto_send_hora_inicio <= now.hour < settings.auto_send_hora_fim):
                continue

            sender = AutoSender(db, evolution_service, settings)
            sent = await sender.send_one()

            if sent:
                jitter = random.uniform(
                    settings.auto_send_intervalo_min_s,
                    settings.auto_send_intervalo_max_s,
                )
                logger.info("auto_sender_loop | aguardando %.0fs antes do próximo envio", jitter)
                await asyncio.sleep(jitter)

        except Exception:
            logger.exception("auto_sender_loop: erro inesperado")


async def _expire_first_contact_loop() -> None:
    """Diariamente às 3h: baixa temperatura de leads inativos.

    - Leads 'contato feito' sem resposta há 5+ dias → temperatura 'frio'
    - Todos os leads ativos sem interação há 7+ dias → temperatura desce um nível
    """
    last_run_date: str = ""
    while True:
        await asyncio.sleep(60)
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            now = _dt.now(ZoneInfo(settings.default_timezone))

            if now.hour != 3 or now.minute != 0:
                continue

            today_str = now.date().isoformat()
            if last_run_date == today_str:
                continue
            last_run_date = today_str

            db = get_db_service()
            # Marcar frio os 'contato feito' sem resposta há 5+ dias
            expired = await asyncio.to_thread(db.expire_first_contact, 5)
            # Baixar temperatura de qualquer lead ativo sem interação há 7 dias
            cooled = await asyncio.to_thread(db.cool_down_leads, 7)

            total = len(expired) + len(cooled)
            if not total:
                logger.info("cool_down: nenhum lead resfriado")
                continue

            logger.info("cool_down | contato_feito_frio=%d resfriados=%d", len(expired), len(cooled))
            if settings.crm_target_group_id and not settings.disable_evolution_confirmation:
                group_id = _normalize_group_id(settings.crm_target_group_id)
                parts = []
                if expired:
                    parts.append(f"🔵 {len(expired)} lead(s) 'contato feito' sem resposta → temperatura frio")
                if cooled:
                    parts.append(f"❄️ {len(cooled)} lead(s) resfriados por inatividade")
                await evolution_service.send_confirmation(group_id, "\n".join(parts))
        except Exception:
            logger.warning("expire_first_contact_loop falhou", exc_info=True)


async def _followup_reminder_loop() -> None:
    """Envia às 9h a lista de follow-ups do dia para o grupo CRM."""
    if not settings.crm_target_group_id:
        return

    last_sent_date: str = ""
    while True:
        await asyncio.sleep(60)
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            now = _dt.now(ZoneInfo(settings.default_timezone))

            if now.hour != 9 or now.minute != 0:
                continue

            today_str = now.date().isoformat()
            if last_sent_date == today_str:
                continue

            last_sent_date = today_str

            db = get_db_service()
            leads = await asyncio.to_thread(db.get_followups_today_list)
            if not leads:
                continue

            lines = [f". 🔔 *Follow-ups de hoje: {len(leads)}*"]
            for lead in leads:
                acao = lead.get("acao_followup") or ""
                extra = f" — {acao}" if acao else ""
                lines.append(f"• {lead['nome']} ({lead['status']}){extra}")

            group_id = _normalize_group_id(settings.crm_target_group_id)
            await evolution_service.send_confirmation(group_id, "\n".join(lines))
            logger.info("followup_reminder enviado | total=%d", len(leads))
        except Exception:
            logger.warning("followup_reminder_loop falhou", exc_info=True)


def _build_daily_summary_message(data: Dict[str, Any]) -> str:
    """Formats the daily summary WhatsApp message.

    RULE: must start with '.' to avoid the bot's own anti-loop filter.
    """
    lines = [". 📊 *Resumo do dia*", ""]

    if data["leads_novos"]:
        lines.append(f"Leads novos: {data['leads_novos']}")
    lines.append(f"Interações: {data['interacoes']}")
    if data["followups_hoje"]:
        lines.append(f"Follow-ups agendados: {data['followups_hoje']}")

    atividades = data["ultimas_atividades"]
    total = data["total_atividades_hoje"]
    if atividades:
        lines.append("")
        lines.append("Últimas atividades:")
        for a in atividades:
            nome = (a["nome"] or "").strip()
            acao = (a["acao"] or "").strip()
            item = f"• {nome}" + (f" — {acao}" if acao else "")
            lines.append(item)
        extra = total - len(atividades)
        if extra > 0:
            lines.append(f"+{extra} atividade{'s' if extra > 1 else ''}")

    if data["followups_amanha"]:
        lines.append("")
        lines.append(f"📅 Follow-ups amanhã: {data['followups_amanha']}")

    if data["streak_dias"] >= 2:
        lines.append("")
        lines.append(f"📈 Sequência ativa: {data['streak_dias']} dias")

    return "\n".join(lines)


async def _daily_summary_loop() -> None:
    """Sends a daily WhatsApp summary at the configured time.

    Checks once per minute. Skips silently if no activity happened today.
    """
    if settings.disable_daily_summary:
        logger.info("daily_summary: desabilitado via DISABLE_DAILY_SUMMARY")
        return

    if not settings.crm_target_group_id:
        logger.warning("daily_summary: CRM_TARGET_GROUP_ID não configurado, loop não iniciado")
        return

    last_sent_date: str = ""
    logger.info(
        "daily_summary_loop iniciado | hora=%02d:%02d tz=%s",
        settings.daily_summary_hour,
        settings.daily_summary_minute,
        settings.default_timezone,
    )

    while True:
        await asyncio.sleep(60)
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            now = _dt.now(ZoneInfo(settings.default_timezone))

            if now.hour != settings.daily_summary_hour or now.minute != settings.daily_summary_minute:
                continue

            today_str = now.date().isoformat()
            if last_sent_date == today_str:
                continue  # already sent today

            last_sent_date = today_str  # mark before to avoid retry on error

            db = get_db_service()
            data = await asyncio.to_thread(db.get_daily_summary, settings.default_timezone)
            if data is None:
                logger.info("daily_summary: sem atividade hoje, resumo não enviado")
                continue

            msg = _build_daily_summary_message(data)
            group_id = _normalize_group_id(settings.crm_target_group_id)
            await evolution_service.send_confirmation(group_id, msg)
            logger.info(
                "daily_summary enviado | leads_novos=%d interacoes=%d streak=%d",
                data["leads_novos"], data["interacoes"], data["streak_dias"],
            )
        except Exception:
            logger.warning("daily_summary_loop falhou", exc_info=True)


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


@app.post("/sync/sheets-to-db")
async def sync_sheets_to_db(x_webhook_secret: str | None = Header(default=None)):
    """Sincroniza edições manuais do Sheets para o DB imediatamente."""
    if settings.evolution_webhook_secret and x_webhook_secret != settings.evolution_webhook_secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        updated = await _do_sheets_sync()
        return {"ok": True, "updated": updated}
    except Exception as exc:
        logger.exception("sync_sheets_to_db falhou")
        raise HTTPException(status_code=500, detail=str(exc)) from exc



async def _execute_crm_query(intent, db: DBService) -> str:
    """Executa uma query conversacional e retorna texto formatado para WhatsApp."""
    if intent.type == "hoje":
        result = await asyncio.to_thread(db.query_leads_today)
        if not result["leads"]:
            return "Nenhum lead criado hoje."
        lines = [f"Leads criados hoje: {result['count']}"]
        for lead in result["leads"]:
            seg = f" ({lead['segmento']})" if lead.get("segmento") else ""
            lines.append(f"• {lead['lead_id']} {lead['nome'] or '?'}{seg} — {lead['status']}")
        return "\n".join(lines)

    if intent.type == "por_atividade":
        days = intent.days or 7
        leads = await asyncio.to_thread(db.query_leads_by_activity_type, intent.activity_type, days)
        label = intent.activity_type or "atividade"
        if not leads:
            return f"Nenhum lead com '{label}' nos últimos {days} dias."
        lines = [f"Leads com '{label}' nos últimos {days} dias: {len(leads)}"]
        for lead in leads:
            cidade = f" ({lead['cidade']})" if lead.get("cidade") else ""
            lines.append(f"• {lead['lead_id']} {lead['nome'] or '?'}{cidade} — {lead['status']}")
        return "\n".join(lines)

    if intent.type == "followup":
        leads = await asyncio.to_thread(db.query_leads_overdue_followup)
        if not leads:
            return "Nenhum follow-up vencido no momento."
        lines = [f"Follow-ups vencidos: {len(leads)}"]
        for lead in leads:
            data = (lead.get("proximo_followup_em") or "")[:10]
            acao = lead.get("acao_followup") or ""
            extra = f" — {acao}" if acao else ""
            lines.append(f"• {lead['lead_id']} {lead['nome'] or '?'} | {data}{extra}")
        return "\n".join(lines)

    if intent.type == "por_status":
        status = intent.status or ""
        leads = await asyncio.to_thread(db.query_leads_by_status, status)
        if not leads:
            return f"Nenhum lead com status '{status}'."
        lines = [f"Leads {status}: {len(leads)}"]
        for lead in leads:
            cidade = f" ({lead['cidade']})" if lead.get("cidade") else ""
            lines.append(f"• {lead['lead_id']} {lead['nome'] or '?'}{cidade}")
        return "\n".join(lines)

    if intent.type == "pipeline":
        stats = await asyncio.to_thread(db.get_stats)
        by_status = stats.get("by_status", {})
        if not by_status:
            return "Pipeline vazio."
        lines = ["Pipeline atual:"]
        order = ["novo", "1º contato", "qualificado", "negociando", "em espera", "sem resposta", "fechado", "perdido"]
        for st in order:
            if st in by_status:
                lines.append(f"• {st}: {by_status[st]}")
        for st, cnt in by_status.items():
            if st not in order:
                lines.append(f"• {st}: {cnt}")
        return "\n".join(lines)

    return "Consulta não reconhecida."


@app.post("/webhook/evolution")
async def evolution_webhook(payload: dict, x_webhook_secret: str | None = Header(default=None)):
    if settings.evolution_webhook_secret and x_webhook_secret != settings.evolution_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Multi-tenant: identifica tenant pelo instanceName do Evolution
    raw_instance = (
        payload.get("instanceName")
        or payload.get("instance")
        or ""
    )
    if raw_instance and settings.database_url:
        base_db = get_db_service()
        tenant = await asyncio.to_thread(base_db.get_tenant_by_instance, raw_instance)
        if tenant and tenant.get("ativo"):
            event = normalize_evolution_payload(payload)
            if event.from_me:
                return {"ok": True, "ignored": True, "reason": "inbox_from_me"}
            # Busca áudio base64 se necessário
            if event.msg_type == "audio" and not event.media_base64:
                if event.raw_msg_key and event.raw_message_obj:
                    fetched_b64 = await evolution_service.fetch_audio_base64(
                        instance_name=raw_instance,
                        msg_key=event.raw_msg_key,
                        message_obj=event.raw_message_obj,
                    )
                    if fetched_b64:
                        event.media_base64 = fetched_b64
            from app.services.inbox_service import InboxService
            tenant_db  = get_tenant_db_service(tenant["id"])
            tenant_evo = EvolutionService(
                settings.evolution_api_url,
                tenant.get("evolution_api_key") or settings.evolution_api_key,
                raw_instance,
            )
            inbox_svc = InboxService(tenant_db, openai_service, tenant_evo)
            try:
                return await inbox_svc.process_incoming(event)
            except Exception:
                # Falha no processamento não deve virar 500 — isso faria a Evolution
                # reentregar o webhook em loop. A dedupe por msg_id (ON CONFLICT DO NOTHING)
                # já protege contra duplicatas em eventual reprocessamento.
                logger.exception(
                    "inbox_process_falhou | tenant=%s instance=%s msg_id=%s",
                    tenant["id"], raw_instance, event.msg_id,
                )
                return {"ok": False, "reason": "inbox_process_error"}

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
        # MVP 2.0: mensagens individuais (não-grupo) vão para o Inbox
        if reason == "not_group" and settings.inbox_mode_enabled:
            # Ignora mensagens enviadas pelo próprio bot para evitar loops
            if event.from_me:
                logger.info("inbox: ignored from_me | chat_id=%s", event.chat_id)
                return {"ok": True, "ignored": True, "reason": "inbox_from_me"}
            logger.info("inbox: mensagem individual recebida | chat_id=%s tipo=%s", event.chat_id, event.msg_type)
            from app.services.inbox_service import InboxService
            # Busca audio base64 se necessário (mesmo fluxo do CRM)
            if event.msg_type == "audio" and not event.media_base64:
                if settings.evolution_instance_name and event.raw_msg_key and event.raw_message_obj:
                    fetched_b64 = await evolution_service.fetch_audio_base64(
                        instance_name=settings.evolution_instance_name,
                        msg_key=event.raw_msg_key,
                        message_obj=event.raw_message_obj,
                    )
                    if fetched_b64:
                        event.media_base64 = fetched_b64
            inbox_svc = InboxService(get_db_service(), openai_service, evolution_service)
            return await inbox_svc.process_incoming(event)

        if reason == "not_group":
            logger.info("ignored: not_group (inbox desabilitado) | chat_id=%s", event.chat_id)
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

        db = get_db_service()

        if event.msg_id and await asyncio.to_thread(db.already_processed, event.msg_id):
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

        # Query branch: deve vir ANTES do filtro de vagueza porque queries
        # legítimas podem ser curtas (ex: "leads hoje", "followup").
        query_intent = detect_query_intent(raw_text)
        if query_intent:
            logger.info("crm_query | type=%s | msg_id=%s", query_intent.type, event.msg_id)
            try:
                reply = await _execute_crm_query(query_intent, db)
                await evolution_service.send_confirmation(event.chat_id, f". {reply}")
            except Exception:
                logger.warning("crm_query falhou | msg_id=%s", event.msg_id, exc_info=True)
            return {"ok": True, "action": "crm_query", "type": query_intent.type}

        # Followup command branch: "followup [lead] [data]", "falar com X sexta", etc.
        followup_cmd = detect_followup_command(raw_text)
        if followup_cmd:
            lead_name, date_str = followup_cmd
            logger.info("followup_cmd | lead=%r date=%s | msg_id=%s", lead_name, date_str, event.msg_id)
            match = await asyncio.to_thread(db.find_lead_by_name, lead_name)
            if match.is_exact:
                lead = match.lead
                lead_id = lead["lead_id"]
                await asyncio.to_thread(
                    db.update_lead_from_dashboard, lead_id, {"proximo_followup_em": date_str}
                )
                from datetime import date as _date
                d = _date.fromisoformat(date_str)
                _PTBR_DAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
                label = f"{_PTBR_DAYS[d.weekday()]} {d.strftime('%d/%m')}"
                await evolution_service.send_confirmation(
                    event.chat_id,
                    f". ✅ Follow-up de *{lead['nome']}* agendado para {label}",
                )
                return {"ok": True, "action": "followup_cmd", "lead_id": lead_id, "date": date_str}
            else:
                await evolution_service.send_confirmation(
                    event.chat_id,
                    f". Lead '{lead_name}' não encontrado — tente um nome mais próximo.",
                )
                return {"ok": True, "action": "followup_cmd_not_found"}

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

        if upper.startswith("ANALISAR:") or upper.startswith("ANALISAR "):
            # Extrai o texto da conversa (tudo após "ANALISAR:" ou "ANALISAR ")
            sep_idx = raw_text.index(":") if ":" in raw_text[:10] else raw_text.index(" ")
            conv_text = raw_text[sep_idx + 1:].strip()
            if not conv_text:
                await evolution_service.send_confirmation(
                    event.chat_id,
                    ". Cole a conversa logo após ANALISAR: e tente novamente."
                )
                return {"ok": True, "ignored": True, "reason": "analisar_sem_conversa"}

            logger.info("analisar_conversa | msg_id=%s | conv_len=%d", event.msg_id, len(conv_text))
            try:
                analysis = await asyncio.to_thread(openai_service.analyze_conversation, conv_text)
            except Exception:
                logger.exception("analyze_conversation falhou | msg_id=%s", event.msg_id)
                await evolution_service.send_confirmation(
                    event.chat_id, ". Erro ao analisar conversa. Tente novamente."
                )
                return {"ok": False, "reason": "analyze_error"}

            # Upsert do lead se identificado
            conv_lead_id = ""
            has_identity = bool(
                analysis.lead.nome or analysis.lead.whatsapp
                or analysis.lead.email or analysis.lead.instagram
            )
            if has_identity:
                conv_lead_id, _, _ = await asyncio.to_thread(
                    db.upsert_lead,
                    analysis.lead.model_dump(),
                    analysis.status_sugerido,
                    analysis.followup_em,
                    event.timestamp,
                )

            # Registra atividade com confianca_analise persistida para o dashboard
            await asyncio.to_thread(
                db.add_activity,
                event.timestamp,
                event.msg_id or "",
                conv_lead_id,
                "análise de conversa",
                "whatsapp_group",
                "registrar_atividade",
                0.9,
                None,
                f"[ANALISAR] {conv_text[:500]}",
                analysis.resumo_conversa,
                analysis.followup_em,
                analysis.confianca,  # confianca_analise (1-10)
            )

            # Atualiza resumo e pendência do lead com os dados da análise
            if conv_lead_id:
                await asyncio.to_thread(
                    db.update_lead_resumo_acao,
                    conv_lead_id,
                    analysis.resumo_conversa or None,
                    analysis.proximo_passo or None,
                )

            # Sync Sheets
            if conv_lead_id:
                lead_dict = await asyncio.to_thread(db.get_lead, conv_lead_id)
                if lead_dict:
                    await asyncio.to_thread(sheets.sync_lead, lead_dict)
            await asyncio.to_thread(
                sheets.sync_activity,
                event.timestamp,
                event.msg_id or "",
                conv_lead_id,
                "análise de conversa",
                "whatsapp_group",
                "registrar_atividade",
                0.9,
                None,
                f"[ANALISAR] {conv_text[:500]}",
                analysis.resumo_conversa,
                analysis.followup_em,
            )

            # Monta resposta formatada para o WhatsApp
            conf = analysis.confianca
            conf_emoji = "🟢" if conf >= 7 else ("🟡" if conf >= 4 else "🔴")
            lead_label = ""
            if analysis.lead.nome:
                lead_label = f" — {analysis.lead.nome}"
                if conv_lead_id:
                    lead_label += f" ({conv_lead_id})"

            lines = [f". 📊 *Análise de conversa{lead_label}*"]
            if analysis.status_sugerido:
                lines.append(f"📋 Status: {analysis.status_sugerido}")
            lines.append(f"{conf_emoji} Confiança: {conf}/10 — {analysis.confianca_razao}")
            if analysis.resumo_conversa:
                lines.append(f"\n📝 {analysis.resumo_conversa}")
            if analysis.sinais_positivos:
                lines.append("\n✅ *Positivos:*")
                lines.extend(f"• {s}" for s in analysis.sinais_positivos)
            if analysis.sinais_preocupantes:
                lines.append("\n⚠️ *Atenção:*")
                lines.extend(f"• {s}" for s in analysis.sinais_preocupantes)
            if analysis.proximo_passo:
                lines.append(f"\n🚀 *Próximo passo:* {analysis.proximo_passo}")
            if not conv_lead_id:
                lines.append("\n_Lead não identificado — envie nome/telefone para cadastrar._")

            reply = "\n".join(lines)
            try:
                await evolution_service.send_confirmation(event.chat_id, reply)
            except Exception:
                logger.warning("analisar_reply failed | msg_id=%s", event.msg_id, exc_info=True)

            return {
                "ok": True,
                "action": "analisar_conversa",
                "lead_id": conv_lead_id or None,
                "confianca": conf,
                "status_sugerido": analysis.status_sugerido,
            }

        # Bulk first-contact branch: "contato inicial realizado nesses N contatos"
        bulk_count = detect_bulk_first_contact(raw_text)
        if bulk_count is not None:
            limit = bulk_count if bulk_count > 0 else 10
            recent = await asyncio.to_thread(db.get_recent_novo_leads, limit, 60)
            if not recent:
                if not settings.disable_evolution_confirmation:
                    await evolution_service.send_confirmation(
                        event.chat_id,
                        ". Nenhum lead 'novo' encontrado na última hora para atualizar.",
                    )
                return {"ok": True, "action": "bulk_first_contact_no_leads"}
            updated = []
            for lead in recent:
                lead_id = lead["lead_id"]
                await asyncio.to_thread(db.update_lead_status, lead_id, "1º contato", event.timestamp)
                await asyncio.to_thread(
                    db.add_activity,
                    event.timestamp, event.msg_id or "", lead_id,
                    "primeiro contato", "whatsapp_group", "atualizar_lead",
                    0.9, event.audio_seconds, raw_text,
                    "bulk: 1º contato", None,
                )
                lead_dict = await asyncio.to_thread(db.get_lead, lead_id)
                if lead_dict:
                    await asyncio.to_thread(sheets.sync_lead, lead_dict)
                updated.append(f"{lead['nome'] or lead_id} ({lead_id})")
            logger.info("bulk_first_contact_ok | count=%d", len(updated))
            if not settings.disable_evolution_confirmation:
                names = "\n".join(f"• {n}" for n in updated)
                await evolution_service.send_confirmation(
                    event.chat_id,
                    f". {len(updated)} lead(s) → 1º contato:\n{names}",
                )
            return {"ok": True, "action": "bulk_first_contact", "count": len(updated)}

        # Micro-update branch: padrão verbal simples sem campos estruturados.
        # Se detectado mas sem match confiante → encerra aqui (não cria lead novo).
        micro = detect_micro_update(raw_text)
        if micro:
            logger.info(
                "micro_update_detected | candidate=%r status=%s | msg_id=%s",
                micro.candidate_name, micro.status, event.msg_id,
            )
            match = await asyncio.to_thread(db.find_lead_by_name, micro.candidate_name)
            if match.is_exact:
                lead = match.lead
                lead_id = lead["lead_id"]
                await asyncio.to_thread(db.update_lead_status, lead_id, micro.status, event.timestamp)
                await asyncio.to_thread(
                    db.add_activity,
                    event.timestamp, event.msg_id or "", lead_id,
                    micro.activity_type, "whatsapp_group", "atualizar_lead",
                    0.9, event.audio_seconds, raw_text,
                    f"micro-update: {micro.status}", None,
                )
                lead_dict = await asyncio.to_thread(db.get_lead, lead_id)
                if lead_dict:
                    await asyncio.to_thread(sheets.sync_lead, lead_dict)
                await asyncio.to_thread(
                    sheets.sync_activity,
                    event.timestamp, event.msg_id or "", lead_id,
                    micro.activity_type, "whatsapp_group", "atualizar_lead",
                    0.9, event.audio_seconds, raw_text,
                    f"micro-update: {micro.status}", None,
                )
                logger.info("micro_update_ok | lead_id=%s status=%s", lead_id, micro.status)
                if not settings.disable_evolution_confirmation:
                    await evolution_service.send_confirmation(
                        event.chat_id,
                        f". {lead['nome']} ({lead_id}) → {micro.status}",
                    )
                return {"ok": True, "action": "micro_update", "lead_id": lead_id, "status": micro.status}

            if match.is_ambiguous:
                cands = " | ".join(f"{c['lead_id']} {c['nome']}" for c in match.candidates[:3])
                logger.info("micro_update_ambiguous | candidate=%r | msg_id=%s", micro.candidate_name, event.msg_id)
                if not settings.disable_evolution_confirmation:
                    await evolution_service.send_confirmation(
                        event.chat_id,
                        f". Mais de um lead encontrado para '{micro.candidate_name}':\n{cands}\n"
                        f"Use VINCULAR <ID> para confirmar.",
                    )
                return {"ok": True, "action": "micro_ambiguous", "candidate": micro.candidate_name}

            # Sem match confiante → encerra, não cria lead fantasma
            logger.info("micro_update_no_match | candidate=%r score=%.2f | msg_id=%s", micro.candidate_name, match.score, event.msg_id)
            if not settings.disable_evolution_confirmation:
                await evolution_service.send_confirmation(
                    event.chat_id,
                    f". Não encontrei '{micro.candidate_name}' com confiança suficiente para atualizar. "
                    f"Verifique o nome ou use VINCULAR <ID>.",
                )
            return {"ok": True, "action": "micro_no_match", "candidate": micro.candidate_name}

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

        # Status override: usuário pode forçar status entre colchetes, ex: [qualificado]
        # Tem precedência máxima — sobrescreve LLM e interpretador.
        status_override = extract_status_override(raw_text)
        if status_override:
            extracted.status_sugerido = status_override
            logger.info("status_override | lead=%s status=%s", extracted.lead.nome or "?", status_override)

        # Resultado de venda: sobrescreve status e tipo de atividade
        if interpretation.resultado_venda:
            extracted.status_sugerido = "fechado" if interpretation.resultado_venda == "ganho" else "perdido"
            extracted.activity.tipo = (
                "venda fechada" if interpretation.resultado_venda == "ganho"
                else "oportunidade perdida"
            )
            logger.info(
                "sales_result_detected | lead=%s resultado=%s",
                extracted.lead.nome or "?",
                interpretation.resultado_venda,
            )

        summary = factual_summary(
            raw_text=raw_text,
            nome=extracted.lead.nome,
            telefone=extracted.lead.whatsapp,
            segmento=extracted.lead.segmento,
            llm_summary=extracted.activity.resumo,
        )
        extracted.activity.resumo = summary

        # --- 1. DB: upsert lead (matching em PostgreSQL) ---
        # Só tenta upsert se a mensagem tem identidade de lead (nome/tel/email/instagram).
        # Mensagens sem identidade (ex: segundo áudio complementar) vão direto ao fallback de contexto,
        # evitando criação de leads fantasmas.
        has_lead_identity = bool(
            extracted.lead.nome
            or extracted.lead.whatsapp
            or extracted.lead.email
            or extracted.lead.instagram
        )

        needs_review = False
        review_candidates: list = []

        if has_lead_identity:
            lead_id, needs_review, review_candidates = await asyncio.to_thread(
                db.upsert_lead,
                extracted.lead.model_dump(),
                extracted.status_sugerido,
                extracted.followup_em,
                event.timestamp,
            )
        else:
            lead_id = ""
            logger.info("Mensagem sem identidade de lead — usando contexto da conversa | msg_id=%s", event.msg_id)

        # Fallback de contexto: usa o último lead vinculado quando não há match ou identidade
        if not lead_id:
            context_lead_id = await asyncio.to_thread(db.latest_linked_lead_id)
            if context_lead_id:
                logger.info("Lead resolvido por contexto da conversa: %s", context_lead_id)
                lead_id = context_lead_id

        logger.info("Lead resolvido: %s | needs_review=%s", lead_id or "REVISAR", needs_review)

        # --- 2. DB: registrar atividade ---
        await asyncio.to_thread(
            db.add_activity,
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

        # --- 3. DB: gerar resumo cumulativo do lead + pendência ---
        if lead_id:
            recent_summaries = await asyncio.to_thread(
                db.get_lead_recent_activity_summaries, lead_id, 5
            )
            lead_resumo = await asyncio.to_thread(
                openai_service.generate_lead_summary,
                extracted.lead.nome,
                extracted.lead.segmento,
                extracted.status_sugerido,
                recent_summaries,
            )
            # Fallback: se OpenAI falhou, usa o resumo da atividade mais recente
            if not lead_resumo and recent_summaries:
                lead_resumo = recent_summaries[0]
            logger.info(
                "lead_resumo | lead_id=%s resumo=%r acao_followup=%r",
                lead_id, lead_resumo[:60] if lead_resumo else "", extracted.acao_followup,
            )
            await asyncio.to_thread(
                db.update_lead_resumo_acao,
                lead_id,
                lead_resumo or None,
                extracted.acao_followup,
            )

        # --- 4. Sheets: sync lead + atividade (write-only) ---
        if lead_id:
            lead_dict = await asyncio.to_thread(db.get_lead, lead_id)
            if lead_dict:
                await asyncio.to_thread(sheets.sync_lead, lead_dict)

        await asyncio.to_thread(
            sheets.sync_activity,
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
                review_candidates,
                "lead_id_nao_resolvido",
            )

        if settings.disable_evolution_confirmation:
            logger.info("confirmation skipped | disabled by env")
        elif not lead_id and needs_review:
            # Pergunta no grupo quando há dúvida sobre o lead (REGRA: mensagem DEVE começar com ".")
            try:
                if review_candidates:
                    cands = " | ".join(
                        f"{c.get('lead_id','?')} {c.get('nome','?')}" for c in review_candidates[:3]
                    )
                    msg = (
                        f". Dúvida: esta mensagem é sobre qual lead?\n"
                        f"{cands}\n"
                        f"Responda: VINCULAR L0001 (ou o ID correto) — ou ignore se for lead novo."
                    )
                else:
                    nome_hint = f" ({extracted.lead.nome})" if extracted.lead.nome else ""
                    msg = (
                        f". Lead{nome_hint} não identificado com certeza. "
                        f"Se for lead existente, responda: VINCULAR L0001 (substitua pelo ID correto)."
                    )
                await evolution_service.send_confirmation(event.chat_id, msg)
            except Exception:
                logger.warning("duvida_confirmation failed | msg_id=%s", event.msg_id, exc_info=True)
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
