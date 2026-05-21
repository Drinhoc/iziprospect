"""inbox_service.py — MVP 2.0: processamento do inbox WhatsApp completo.

Responsabilidade: receber qualquer mensagem individual (não-grupo) da Evolution
API, criar/atualizar threads de conversa, transcrever áudios e executar triagem
automática com IA para classificar prioridade, categoria e sugerir resposta.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.schemas.models import NormalizedEvent
from app.services.db_service import DBService
from app.services.evolution_service import EvolutionService
from app.services.openai_service import AudioResolveError, OpenAIService

logger = logging.getLogger(__name__)

INBOX_TRIAGE_PROMPT = """Você é um assistente de atendimento ao cliente para um negócio brasileiro no WhatsApp.
Analise a conversa abaixo e retorne SOMENTE JSON válido com o schema:

{
  "categoria": "suporte|vendas|informacao|spam|outro",
  "prioridade": "urgente|alta|normal|baixa",
  "resumo": "Resumo factual em 1-2 frases. Máx 200 chars.",
  "resposta_sugerida": "Rascunho de resposta profissional e contextualizada. Máx 300 chars.",
  "confianca": 7,
  "nome_contato": null
}

Regras:
- categoria:
  * suporte = dúvidas, problemas, reclamações, cancelamentos, suporte técnico
  * vendas = interesse em comprar, pedido de preço, orçamento, agendamento, demonstração
  * informacao = perguntas gerais, horários, endereço, serviços disponíveis
  * spam = promoção não solicitada, bot automático, conteúdo irrelevante
  * outro = qualquer coisa que não se encaixa acima
- prioridade:
  * urgente = problema grave, reclamação forte, cancelamento, emergência médica
  * alta = compra iminente, cliente esperando há horas, pedido urgente do cliente
  * normal = conversa em andamento sem urgência, informação geral
  * baixa = spam detectado, conversa muito antiga, sem urgência clara
- resumo: descreve factualmente o que o contato quer e onde a conversa está agora
- resposta_sugerida: escreva como se fosse o atendente respondendo — profissional, humano, cordial
  Inclua cumprimento se for primeira mensagem. Não use asteriscos ou markdown.
- confianca: 1-10 quão certo você está da triagem com base no contexto disponível
- nome_contato: nome próprio do contato se mencionado claramente, null caso contrário
- Se a conversa for muito curta (1-2 mensagens), confianca deve ser ≤5"""


def _extract_numero_from_jid(jid: str) -> str:
    raw = jid.replace("@s.whatsapp.net", "").replace("@c.us", "")
    return raw.split(":")[0]


class InboxService:
    def __init__(
        self,
        db: DBService,
        openai_svc: OpenAIService,
        evolution_svc: EvolutionService,
    ):
        self.db = db
        self.openai = openai_svc
        self.evolution = evolution_svc

    # ------------------------------------------------------------------
    # Ponto de entrada principal
    # ------------------------------------------------------------------

    async def process_incoming(self, event: NormalizedEvent) -> Dict[str, Any]:
        """Processa uma mensagem individual recebida no inbox.

        Fluxo:
        1. Upsert da conversa (cria ou atualiza thread pelo JID)
        2. Transcrição de áudio se necessário
        3. Persiste mensagem na tabela mensagens_inbox
        4. Dispara triagem por IA de forma assíncrona (não bloqueia o webhook)
        """
        jid = event.chat_id
        numero = _extract_numero_from_jid(jid)

        conversa = await asyncio.to_thread(
            self.db.get_or_create_conversa, jid, "", numero
        )
        conversa_id: int = conversa["id"]

        texto = event.raw_text.strip()
        transcricao = ""

        if event.msg_type == "audio" and (event.media_url or event.media_base64):
            try:
                transcricao = await self.openai.transcribe_audio_from_url(
                    event.media_url,
                    event.media_mimetype,
                    event.media_base64,
                    event.media_key,
                )
                texto = transcricao
                logger.info(
                    "inbox_audio_transcrito | conversa_id=%d chars=%d",
                    conversa_id, len(transcricao),
                )
            except AudioResolveError as exc:
                logger.warning(
                    "inbox_audio_erro | conversa_id=%d reason=%s",
                    conversa_id, exc.reason,
                )
            except Exception:
                logger.warning(
                    "inbox_audio_falha_inesperada | conversa_id=%d",
                    conversa_id, exc_info=True,
                )

        await asyncio.to_thread(
            self.db.add_mensagem_inbox,
            event.msg_id or f"inbox_{conversa_id}_{event.timestamp.timestamp():.0f}",
            conversa_id,
            jid,
            event.from_me,
            event.msg_type,
            texto,
            transcricao,
            event.audio_seconds,
            event.media_url or "",
            event.timestamp,
        )

        # Triagem assíncrona — não bloqueia o retorno do webhook
        asyncio.create_task(self._triage_conversa(conversa_id))

        logger.info(
            "inbox_processado | jid=%s conversa_id=%d tipo=%s from_me=%s",
            jid, conversa_id, event.msg_type, event.from_me,
        )
        return {"ok": True, "conversa_id": conversa_id, "action": "inbox"}

    # ------------------------------------------------------------------
    # Triagem com IA
    # ------------------------------------------------------------------

    async def _triage_conversa(self, conversa_id: int) -> None:
        """Executa triagem com IA e persiste resultado na conversa."""
        try:
            mensagens = await asyncio.to_thread(
                self.db.get_conversa_mensagens, conversa_id
            )
            if not mensagens:
                return

            conv_text = self._format_mensagens(mensagens)
            result = await asyncio.to_thread(self._call_triage_llm, conv_text)
            if not result:
                return

            await asyncio.to_thread(
                self.db.update_conversa_triage,
                conversa_id,
                result.get("categoria", "outro"),
                result.get("prioridade", "normal"),
                result.get("resumo", ""),
                result.get("resposta_sugerida", ""),
                int(result.get("confianca", 5)),
                result.get("nome_contato") or "",
            )
            logger.info(
                "triage_ok | conversa_id=%d cat=%s prio=%s conf=%s",
                conversa_id,
                result.get("categoria"),
                result.get("prioridade"),
                result.get("confianca"),
            )
        except Exception:
            logger.warning(
                "triage_conversa_falhou | conversa_id=%d",
                conversa_id, exc_info=True,
            )

    def _format_mensagens(self, mensagens: list) -> str:
        lines = []
        for m in mensagens[-30:]:
            origem = "Atendente" if m.get("de_mim") else "Contato"
            texto = m.get("transcricao") or m.get("texto") or ""
            if m.get("tipo") == "audio" and not texto:
                texto = "[áudio sem transcrição]"
            elif not texto:
                texto = f"[{m.get('tipo', 'mídia')}]"
            lines.append(f"{origem}: {texto}")
        return "\n".join(lines)

    def _call_triage_llm(self, conv_text: str) -> Optional[Dict[str, Any]]:
        if not self.openai.client:
            return None
        try:
            resp = self.openai.client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": INBOX_TRIAGE_PROMPT},
                    {"role": "user", "content": conv_text[:10000]},
                ],
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            data["confianca"] = max(1, min(10, int(data.get("confianca", 5))))
            return data
        except Exception:
            logger.warning("_call_triage_llm falhou", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Envio de resposta
    # ------------------------------------------------------------------

    async def send_reply(self, conversa_id: int, text: str) -> bool:
        """Envia resposta via Evolution API e registra no inbox."""
        conversa = await asyncio.to_thread(self.db.get_conversa, conversa_id)
        if not conversa:
            return False

        jid = conversa["jid"]
        ok = await self.evolution.send_confirmation(jid, text)

        if ok:
            now = datetime.now(tz=timezone.utc)
            await asyncio.to_thread(
                self.db.add_mensagem_inbox,
                f"sent_{conversa_id}_{now.timestamp():.0f}",
                conversa_id,
                jid,
                True,
                "text",
                text,
                "",
                None,
                "",
                now,
            )

        return ok
