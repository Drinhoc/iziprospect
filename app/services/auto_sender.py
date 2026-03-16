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
# ---------------------------------------------------------------------------
# Índice de variante: 0=A (apresentação pessoal), 1=B (dor-primeiro), 2=C (prova social)
_TEMPLATES: dict[str, list[str]] = {
    "odontologia": [
        (
            "Oi, tudo bem? Sou o Pedro 🙂\n\n"
            "Tô montando um assistente de atendimento pelo WhatsApp pra clínicas odontológicas aqui da região "
            "— basicamente pra responder rápido e organizar agendamentos sem precisar de alguém na tela o tempo todo.\n\n"
            "Faz sentido te explicar em 2 minutos como funciona?"
        ),
        (
            "Oi! Pergunta rápida: vocês costumam perder agendamentos porque a mensagem chegou fora do horário "
            "ou demorou a ser respondida?\n\n"
            "Pergunto porque estou ajudando algumas clínicas de odontologia aqui na região a resolver exatamente isso pelo WhatsApp.\n\n"
            "Posso te contar como em 2 minutinhos?"
        ),
        (
            "Olá! Tudo bem? 🙂\n\n"
            "Estou conversando com algumas clínicas odontológicas aqui da região sobre automação de atendimento "
            "no WhatsApp (agendamento, confirmação de consultas, etc).\n\n"
            "Posso te explicar rapidinho em 2 minutos como funciona?"
        ),
    ],
    "medicina": [
        (
            "Oi, tudo bem? Sou o Pedro 🙂\n\n"
            "Tô montando um assistente de atendimento pelo WhatsApp pra clínicas médicas aqui da região "
            "— pra responder rápido e confirmar consultas sem sobrecarregar a recepção.\n\n"
            "Faz sentido te explicar em 2 minutos como funciona?"
        ),
        (
            "Oi! Pergunta rápida: vocês costumam perder consultas porque a mensagem chegou fora do horário "
            "ou a recepção não conseguiu responder a tempo?\n\n"
            "Pergunto porque estou ajudando algumas clínicas médicas aqui na região a resolver exatamente isso pelo WhatsApp.\n\n"
            "Posso te contar como em 2 minutinhos?"
        ),
        (
            "Olá! Tudo bem? 🙂\n\n"
            "Estou conversando com algumas clínicas aqui da região sobre automação de atendimento "
            "no WhatsApp (agendamento, confirmação de consultas, etc).\n\n"
            "Posso te explicar rapidinho em 2 minutos como funciona?"
        ),
    ],
    "estetica": [
        (
            "Oi, tudo bem? Sou o Pedro 🙂\n\n"
            "Tô montando um assistente de atendimento pelo WhatsApp pra clínicas de estética aqui da região "
            "— pra responder rápido, agendar e confirmar procedimentos sem depender de alguém disponível o tempo todo.\n\n"
            "Faz sentido te explicar em 2 minutos como funciona?"
        ),
        (
            "Oi! Pergunta rápida: vocês costumam perder clientes porque a mensagem chegou fora do horário "
            "e não foi respondida a tempo?\n\n"
            "Pergunto porque estou ajudando algumas clínicas de estética aqui na região a resolver exatamente isso pelo WhatsApp.\n\n"
            "Posso te contar como em 2 minutinhos?"
        ),
        (
            "Olá! Tudo bem? 🙂\n\n"
            "Estou ajudando algumas clínicas de estética a automatizar o atendimento no WhatsApp "
            "(agendamentos, confirmação de consultas e respostas rápidas).\n\n"
            "Queria saber se vocês já usam algo assim por aí."
        ),
    ],
    "default": [
        (
            "Oi, tudo bem? Sou o Pedro 🙂\n\n"
            "Tô montando um assistente de atendimento pelo WhatsApp — pra responder rápido e organizar "
            "agendamentos sem precisar de alguém disponível o tempo todo.\n\n"
            "Faz sentido te explicar em 2 minutos como funciona?"
        ),
        (
            "Oi! Pergunta rápida: vocês costumam perder clientes porque a mensagem chegou fora do horário "
            "ou demorou a ser respondida?\n\n"
            "Pergunto porque estou ajudando alguns negócios aqui na região a resolver exatamente isso pelo WhatsApp.\n\n"
            "Posso te contar como em 2 minutinhos?"
        ),
        (
            "Olá! Tudo bem? 🙂\n\n"
            "Estou ajudando algumas clínicas a automatizar o atendimento no WhatsApp "
            "(agendamentos, confirmação de consultas e respostas rápidas).\n\n"
            "Queria saber se vocês já usam algo assim por aí."
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
    return templates[idx], _VARIANT_LABELS[idx]


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

        # Busca o próximo lead elegível
        candidates = await _thread(self.db.get_leads_for_auto_send, 1)
        if not candidates:
            logger.info("auto_sender | nenhum lead elegível no momento")
            return False

        lead = candidates[0]
        lead_id = lead["lead_id"]
        nome = lead.get("nome") or lead_id
        whatsapp = lead.get("whatsapp", "")

        # Gera mensagem
        mensagem, variante = render_message(lead)
        when_iso = now.isoformat()

        # Envia via Evolution API
        logger.info(
            "auto_sender | enviando para lead_id=%s nome=%r variante=%s whatsapp=%s",
            lead_id, nome, variante, whatsapp[:6] + "****",
        )
        ok = await self.evolution.send_confirmation(whatsapp, mensagem)

        if not ok:
            logger.error(
                "auto_sender | falha no envio | lead_id=%s whatsapp=%s",
                lead_id, whatsapp[:6] + "****",
            )
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
