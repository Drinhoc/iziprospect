"""Auto-Sender Service — Envio automático de primeiro contato via WhatsApp.

Funcionamento:
- Chamado periodicamente pelo loop _auto_sender_loop() em main.py
- Seleciona 1 lead por ciclo (modelo 1-por-ciclo, não lote)
- Respeita limite diário (AUTO_SEND_DIARIO_MAX, padrão 7)
- Respeita janela horária (AUTO_SEND_HORA_INICIO–AUTO_SEND_HORA_FIM)
- Intervalo aleatório entre envios controlado pelo loop externo

Seleção de leads (ordem de prioridade):
1. status = 'novo'
2. whatsapp preenchido
3. mensagem_enviada_em vazio (nunca recebeu envio automático)
4. origem_primeiro_contato vazio
5. Preferência por leads com segmento preenchido (personalização melhor)
6. FIFO por data_criacao ASC (mais antigos primeiro)

Templates:
  ⚠️  DUPLICADOS intencionalmente de app/static/leads.js (MSG_TEMPLATES).
  Manter em sincronia manual se os textos forem alterados no frontend.
  TODO: Centralizar em app/static/msg_templates.json em futura refatoração.

Para ativar: definir AUTO_SEND_ENABLED=true no arquivo .env
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.db_service import DBService
    from app.services.evolution_service import EvolutionService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Templates — ⚠️ manter em sincronia com app/static/leads.js MSG_TEMPLATES
# Use {{nome}} para o nome da clínica (substituído em render_message).
# Variantes: 0=A (personalização + contexto), 1=B (dor direta), 2=C (resultado primeiro)
# ---------------------------------------------------------------------------
_TEMPLATES: dict[str, list[str]] = {
    "odontologia": [
        (
            "Oi! Vi a {{nome}} pesquisando clínicas odontológicas na região 🙂\n\n"
            "Queria perguntar rápido: vocês costumam perder agendamentos porque alguma mensagem "
            "chegou fora do horário e não foi respondida a tempo?\n\n"
            "Tenho ajudado clínicas por aqui a resolver isso pelo WhatsApp, sem precisar contratar "
            "alguém extra pra ficar de plantão.\n\n"
            "Faz sentido eu te mostrar como em 2 minutos?"
        ),
        (
            "Oi, {{nome}}! Pergunta rápida:\n\n"
            "Já perderam paciente porque a recepção estava ocupada ou fora do horário e a mensagem "
            "no WhatsApp ficou sem resposta?\n\n"
            "Pergunto porque resolvo exatamente isso pra clínicas odontológicas daqui. "
            "Posso te explicar em 2 minutinhos?"
        ),
        (
            "Oi, {{nome}}! Sou o Pedro.\n\n"
            "Tenho ajudado clínicas odontológicas da região a parar de perder agendamentos por "
            "demora no WhatsApp — automatizando respostas e confirmações fora do horário, "
            "sem app novo nem contratação.\n\n"
            "Vale uma conversa rápida de 2 minutos?"
        ),
    ],
    "medicina": [
        (
            "Oi! Vi a {{nome}} pesquisando clínicas médicas na região 🙂\n\n"
            "Queria perguntar rápido: vocês costumam perder consultas porque alguma mensagem "
            "chegou fora do horário ou a recepção não deu conta de responder a tempo?\n\n"
            "Tenho ajudado clínicas por aqui com isso — um assistente no WhatsApp que responde "
            "e confirma consulta mesmo quando a recepção está ocupada.\n\n"
            "Faz sentido eu te mostrar como em 2 minutos?"
        ),
        (
            "Oi, {{nome}}! Pergunta rápida:\n\n"
            "Já perderam consulta porque a recepção não conseguiu responder uma mensagem a tempo "
            "— fora do horário ou no pico do dia?\n\n"
            "Pergunto porque resolvo exatamente isso pra clínicas médicas daqui. "
            "Posso te explicar em 2 minutinhos?"
        ),
        (
            "Oi, {{nome}}! Sou o Pedro.\n\n"
            "Tenho ajudado clínicas médicas da região a não perder mais consulta por falta de "
            "resposta no WhatsApp — automatizando o atendimento fora do horário sem sobrecarregar "
            "a recepção.\n\n"
            "Vale uma conversa rápida de 2 minutos?"
        ),
    ],
    "estetica": [
        (
            "Oi! Vi a {{nome}} pesquisando clínicas de estética na região 🙂\n\n"
            "Queria perguntar rápido: vocês costumam perder clientes porque a mensagem no WhatsApp "
            "demorou a ser respondida ou chegou fora do horário?\n\n"
            "Tenho ajudado clínicas de estética por aqui com isso — respostas automáticas e "
            "agendamento pelo WhatsApp mesmo quando a equipe está em atendimento.\n\n"
            "Faz sentido eu te mostrar como em 2 minutos?"
        ),
        (
            "Oi, {{nome}}! Pergunta rápida:\n\n"
            "Já perderam cliente porque a mensagem ficou sem resposta enquanto a equipe estava "
            "em atendimento ou fora do horário?\n\n"
            "Pergunto porque resolvo exatamente isso pra clínicas de estética daqui. "
            "Posso te explicar em 2 minutinhos?"
        ),
        (
            "Oi, {{nome}}! Sou o Pedro.\n\n"
            "Tenho ajudado clínicas de estética da região a não perder mais cliente por demora "
            "no WhatsApp — respostas automáticas e agendamento mesmo fora do horário, sem precisar "
            "de alguém disponível o tempo todo.\n\n"
            "Vale uma conversa rápida de 2 minutos?"
        ),
    ],
    "default": [
        (
            "Oi! Vi a {{nome}} pesquisando clínicas na região 🙂\n\n"
            "Queria perguntar rápido: vocês costumam perder atendimentos porque alguma mensagem "
            "no WhatsApp chegou fora do horário ou demorou a ser respondida?\n\n"
            "Tenho ajudado clínicas por aqui a resolver isso — respostas automáticas e agendamento "
            "mesmo quando a equipe está ocupada ou fora do horário.\n\n"
            "Faz sentido eu te mostrar como em 2 minutos?"
        ),
        (
            "Oi, {{nome}}! Pergunta rápida:\n\n"
            "Já perderam paciente ou cliente porque a mensagem no WhatsApp ficou sem resposta "
            "enquanto a equipe estava ocupada ou fora do horário?\n\n"
            "Pergunto porque resolvo exatamente isso pra clínicas e consultórios daqui. "
            "Posso te explicar em 2 minutinhos?"
        ),
        (
            "Oi, {{nome}}! Sou o Pedro.\n\n"
            "Tenho ajudado clínicas e consultórios da região a não perder mais atendimento por "
            "demora no WhatsApp — automatizando respostas e agendamentos fora do horário "
            "sem complicação.\n\n"
            "Vale uma conversa rápida de 2 minutos?"
        ),
    ],
}

_VARIANT_LABELS = ["A", "B", "C"]


def _ab_variant(lead_id: str) -> int:
    """Determinístico: mesmo lead sempre recebe mesma variante.

    Mesma lógica do frontend:
      leadId.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % 3
    """
    return sum(ord(c) for c in (lead_id or "")) % 3


def render_message(lead: dict) -> tuple[str, str]:
    """Gera a mensagem personalizada para o lead.

    Retorna: (texto_da_mensagem, variante_label)  ex: ("Oi, tudo bem?...", "A")
    """
    seg = (lead.get("segmento") or "").lower()
    templates = _TEMPLATES.get(seg, _TEMPLATES["default"])
    idx = _ab_variant(lead.get("lead_id", ""))
    nome = (lead.get("nome") or "").strip()
    text = templates[idx].replace("{{nome}}", nome) if nome else templates[idx].replace("{{nome}} ", "").replace("{{nome}}", "")
    return text, _VARIANT_LABELS[idx]


class AutoSender:
    """Orquestra a seleção, envio e registro de leads para auto-send."""

    def __init__(self, db: "DBService", evolution: "EvolutionService", settings: "Settings"):
        self.db = db
        self.evolution = evolution
        self.settings = settings

    async def send_one(self) -> bool:
        """Tenta enviar para 1 lead elegível. Retorna True se enviou, False caso contrário."""
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(self.settings.default_timezone))
        today_iso = now.date().isoformat()

        # Verifica limite diário
        sent_today = await _thread(self.db.count_auto_sent_today, today_iso)
        if sent_today >= self.settings.auto_send_diario_max:
            logger.info(
                "auto_sender | limite diário atingido (%d/%d), aguardando amanhã",
                sent_today, self.settings.auto_send_diario_max,
            )
            return False

        # Busca os próximos leads elegíveis (até 5 para pular falhas permanentes)
        candidates = await _thread(self.db.get_leads_for_auto_send, 5)
        if not candidates:
            logger.info("auto_sender | nenhum lead elegível no momento")
            return False

        lead = None
        ok = False
        mensagem = variante = when_iso = ""
        for candidate in candidates:
            _lead_id = candidate["lead_id"]
            _nome = candidate.get("nome") or _lead_id
            _whatsapp = candidate.get("whatsapp", "")
            _mensagem, _variante = render_message(candidate)
            _when_iso = now.isoformat()

            logger.info(
                "auto_sender | enviando para lead_id=%s nome=%r variante=%s whatsapp=%s",
                _lead_id, _nome, _variante, _whatsapp[:6] + "****",
            )
            _ok = await self.evolution.send_confirmation(_whatsapp, _mensagem)

            if _ok:
                lead = candidate
                lead_id = _lead_id
                nome = _nome
                whatsapp = _whatsapp
                mensagem = _mensagem
                variante = _variante
                when_iso = _when_iso
                ok = True
                break
            else:
                logger.error(
                    "auto_sender | falha no envio | lead_id=%s whatsapp=%s — marcando como erro e tentando próximo",
                    _lead_id, _whatsapp[:6] + "****",
                )
                await _thread(self.db.mark_auto_send_error, _lead_id)

        if not ok:
            return False

        # Persiste no DB
        await _thread(self.db.mark_auto_sent, lead_id, variante, mensagem, when_iso)

        # Registra atividade
        await _thread(
            self.db.add_activity,
            now,                   # data_hora (datetime)
            f"auto_{lead_id}_{today_iso}",  # msg_id único
            lead_id,
            "auto_envio",          # tipo
            "whatsapp_direto",     # canal
            "auto_send_primeiro_contato",  # acao_executada
            1.0,                   # confianca_ia
            None,                  # duracao_audio_s
            mensagem,              # mensagem_bruta (texto enviado)
            f"[Auto] Primeiro contato enviado automaticamente. Variante {variante}.",
            None,                  # followup_em
        )

        # Registra no A/B tracking para métricas
        await _thread(
            self.db.registrar_msg_ab_evento,
            lead_id,
            variante,
            lead.get("segmento", ""),
            "auto_enviada",
            "inicial",
        )

        logger.info(
            "auto_sender | OK | lead_id=%s nome=%r variante=%s (%d/%d hoje)",
            lead_id, nome, variante, sent_today + 1, self.settings.auto_send_diario_max,
        )
        return True


async def _thread(fn, *args):
    """Executa função síncrona em thread pool."""
    import asyncio
    return await asyncio.to_thread(fn, *args)
