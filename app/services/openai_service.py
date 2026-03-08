from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.hmac import HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from openai import OpenAI

from app.schemas.models import ConversationAnalysis, LLMExtraction

logger = logging.getLogger(__name__)

PROMPT = """Você é um extrator de CRM para prospecção de clínicas (odonto, estética, médica) no Brasil.
Contexto: o usuário envia mensagens rápidas num grupo WhatsApp para registrar leads e interações.
Retorne SOMENTE JSON válido com o schema abaixo. Nunca inclua markdown.

Schema:
{
  "intent": "novo|update|perdido|fechado|corrigir|vincular|set",
  "lead": {
    "nome": null,
    "cidade": null,
    "segmento": null,
    "whatsapp": null,
    "email": null,
    "instagram": null,
    "site": null,
    "responsavel": null,
    "fonte": null
  },
  "status_sugerido": null,
  "followup_em": null,
  "pendencia": null,
  "activity": {"tipo": "", "resumo": ""}
}

Regras:
- Nunca invente dados. Se não souber um campo, retorne null.
- lead.nome: nome da clínica/empresa. Se vier antes do telefone, extraia esse trecho.
- lead.responsavel: nome ou cargo do contato (ex: "Dr. Carlos", "recepcionista", "dono"). null se ausente.
- lead.segmento: tipo de serviço (odonto, estética, médica, nutrição, fisio, etc.). null se ausente.
- lead.fonte: como o lead chegou (cold, indicação, instagram, grupo, evento, etc.). null se ausente.
- lead.email: endereço de e-mail se mencionado. null se ausente.
- followup_em: data/hora de próximo contato se mencionada (ISO 8601 ou texto como "amanhã 10h").
- pendencia: próxima ação comercial concreta. Preencha sempre que houver contexto suficiente.
  Por status: "novo"→"Fazer primeiro contato", "em contato"→"Fazer follow-up",
  "qualificado"→"Enviar proposta", "proposta enviada"→"Aguardar retorno",
  "negociando"→"Fechar contrato", "fechado"→"Emitir contrato/NF".
  null APENAS para mensagens de nota pura sem ação decorrente.
- activity.tipo: contato inicial | respondeu | pediu proposta | sem interesse | número inválido | retorno agendado | aguardando resposta | demo agendada | nota
- activity.resumo: máx 220 chars, factual, sem especulação.
- intent "perdido" → status_sugerido "perdido"; intent "fechado" → status_sugerido "fechado".
- Não corrija ortografia do usuário.
- STATUS OVERRIDE: se o usuário escrever explicitamente um status entre colchetes (ex: [qualificado], [negociando], [sem resposta]), use exatamente esse valor em status_sugerido, sem questionar.

Guia de status_sugerido — escolha o que melhor descreve o ESTÁGIO ATUAL do lead:
- "novo": nunca houve contato real. Lead recém identificado.
- "em contato": já houve contato (ligação, mensagem, email) e o prospect respondeu pelo menos uma vez, mas sem avançar ainda.
- "qualificado": prospect respondeu e demonstrou algum interesse genuíno (fez perguntas, pediu mais info, quer conhecer, achou interessante). Ainda não tem proposta.
- "proposta enviada": proposta formal já foi enviada. Aguardando feedback/aprovação.
- "negociando": prospect está discutindo detalhes de preço, condições, prazo, ajustes. Proposta em aberto com negociação ativa.
- "fechado": venda confirmada, contrato assinado, cliente pagou.
- "perdido": APENAS quando o prospect disse explicitamente que não quer, rejeitou ativamente, ou demonstrou rejeição clara ("não tenho interesse", "não vou comprar", "prefiro outro", "pode tirar meu contato"). NÃO use perdido só porque não respondeu.
- "sem resposta": prospect não respondeu uma ou mais tentativas. Use SEMPRE que há ausência de resposta, mesmo que o vendedor esteja frustrado. Na dúvida entre "perdido" e "sem resposta", use SEMPRE "sem resposta".
- "contato inválido": número errado, email inválido, pessoa não existe nesse contato.

Exemplos:
Entrada: "Clinca sorrisa, 19 998998988 odonto, falar com Dr. Paulo"
Saída: {"intent":"novo","lead":{"nome":"Clinca sorrisa","cidade":null,"segmento":"odonto","whatsapp":"19998998988","email":null,"instagram":null,"site":null,"responsavel":"Dr. Paulo","fonte":null},"status_sugerido":"novo","followup_em":null,"pendencia":"Fazer primeiro contato","activity":{"tipo":"contato inicial","resumo":"Novo lead: Clinca sorrisa, odonto, tel 19998998988, contato Dr. Paulo."}}

Entrada: "Clínica Vida, Campinas, sem interesse por enquanto"
Saída: {"intent":"perdido","lead":{"nome":"Clínica Vida","cidade":"Campinas","segmento":null,"whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":null,"fonte":null},"status_sugerido":"perdido","followup_em":null,"pendencia":null,"activity":{"tipo":"sem interesse","resumo":"Clínica Vida (Campinas) não tem interesse no momento."}}

Entrada: "Clínica Sorrir, vou mandar a proposta amanhã"
Saída: {"intent":"update","lead":{"nome":"Clínica Sorrir","cidade":null,"segmento":null,"whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":null,"fonte":null},"status_sugerido":"proposta enviada","followup_em":"amanhã","pendencia":"Enviar proposta","activity":{"tipo":"pediu proposta","resumo":"Proposta a ser enviada amanhã para Clínica Sorrir."}}

Entrada: "Odonto Sul SP, liguei hoje, vai pensar e me liga semana que vem"
Saída: {"intent":"update","lead":{"nome":"Odonto Sul","cidade":"SP","segmento":"odonto","whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":null,"fonte":null},"status_sugerido":"em contato","followup_em":"semana que vem","pendencia":"Aguardar retorno da clínica","activity":{"tipo":"aguardando resposta","resumo":"Odonto Sul (SP): contato feito, aguardando retorno semana que vem."}}

Entrada: "Studio Beleza BH, falei com a dona hoje, achou interessante, quer saber mais sobre os resultados, vou marcar uma demo"
Saída: {"intent":"update","lead":{"nome":"Studio Beleza","cidade":"BH","segmento":"estética","whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":"dona","fonte":null},"status_sugerido":"qualificado","followup_em":null,"pendencia":"Enviar proposta","activity":{"tipo":"demo agendada","resumo":"Studio Beleza (BH): dona demonstrou interesse genuíno, quer conhecer mais. Demo a agendar."}}

Entrada: "Clínica Premium SP, tô negociando com o Dr. Ricardo, ele quer ajustar o prazo de pagamento pra 3x"
Saída: {"intent":"update","lead":{"nome":"Clínica Premium","cidade":"SP","segmento":null,"whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":"Dr. Ricardo","fonte":null},"status_sugerido":"negociando","followup_em":null,"pendencia":"Fechar contrato","activity":{"tipo":"nota","resumo":"Clínica Premium (SP): negociando com Dr. Ricardo condições de pagamento (3x)."}}

Entrada: "OdontoVida RJ, tentei 3x essa semana, nenhuma resposta, nem viu as mensagens"
Saída: {"intent":"update","lead":{"nome":"OdontoVida","cidade":"RJ","segmento":"odonto","whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":null,"fonte":null},"status_sugerido":"sem resposta","followup_em":null,"pendencia":"Tentar novo contato em canal diferente","activity":{"tipo":"aguardando resposta","resumo":"OdontoVida (RJ): 3 tentativas sem resposta. Prospect inativo."}}

Entrada: "Sorriso Total SP, mandei mensagem semana passada, não deu retorno ainda"
Saída: {"intent":"update","lead":{"nome":"Sorriso Total","cidade":"SP","segmento":null,"whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":null,"fonte":null},"status_sugerido":"sem resposta","followup_em":null,"pendencia":"Tentar novo contato","activity":{"tipo":"aguardando resposta","resumo":"Sorriso Total (SP): mensagem enviada, aguardando retorno."}}

Entrada: "Clínica Amaral BH, falei uma vez, ficou de retornar, nunca mais"
Saída: {"intent":"update","lead":{"nome":"Clínica Amaral","cidade":"BH","segmento":null,"whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":null,"fonte":null},"status_sugerido":"sem resposta","followup_em":null,"pendencia":"Fazer follow-up","activity":{"tipo":"aguardando resposta","resumo":"Clínica Amaral (BH): ficou de retornar mas não retornou. Follow-up necessário."}}

Entrada: "Fisio Ativa SP [negociando], tô ajustando proposta com ela, quer desconto de 10%"
Saída: {"intent":"update","lead":{"nome":"Fisio Ativa","cidade":"SP","segmento":"fisio","whatsapp":null,"email":null,"instagram":null,"site":null,"responsavel":null,"fonte":null},"status_sugerido":"negociando","followup_em":null,"pendencia":"Fechar contrato","activity":{"tipo":"nota","resumo":"Fisio Ativa (SP): negociando desconto de 10%. Proposta em ajuste."}}
"""

LEAD_SUMMARY_PROMPT = """Você é um assistente de CRM para prospecção de clínicas no Brasil.
Com base nos dados do lead e nas últimas interações, escreva um resumo executivo comercial em 1-2 frases (máx 200 chars).
Siga este formato: "[Nome/Tipo] em [cidade] — [último acontecimento relevante] — [próximo passo]."
Exemplos:
- "Clínica Sorrir (odonto) em SP — proposta enviada em mar/26 — aguardar retorno do Dr. Paulo."
- "Studio Estética em BH — qualificado, alta prioridade — enviar proposta esta semana."
- "OdontoVida (odonto) em Campinas — sem interesse no momento — sem ação pendente."
Seja factual, direto e orientado a ação. Não use markdown."""

CONVERSATION_ANALYSIS_PROMPT = """Você é um analista de vendas especializado em prospecção de clínicas no Brasil (odonto, estética, médica, etc).
Recebe uma conversa de WhatsApp (copiada do app) entre o vendedor e o prospect.
Analise com olhar comercial honesto e retorne SOMENTE JSON válido com o schema abaixo.

Schema:
{
  "lead": {
    "nome": null,
    "cidade": null,
    "segmento": null,
    "whatsapp": null,
    "email": null,
    "instagram": null,
    "responsavel": null,
    "fonte": null
  },
  "status_sugerido": "novo|em contato|qualificado|proposta enviada|negociando|fechado|perdido|sem resposta|contato inválido",
  "resumo_conversa": "Resumo factual do fluxo da conversa. Máx 300 chars.",
  "confianca": 6,
  "confianca_razao": "Explicação direta e honesta do score.",
  "sinais_positivos": ["sinal concreto 1", "sinal concreto 2"],
  "sinais_preocupantes": ["risco 1", "risco 2"],
  "proximo_passo": "Ação concreta e específica que o vendedor deve tomar.",
  "followup_em": null
}

Regras:
- lead.nome: nome da clínica/empresa. null se não identificado.
- lead.whatsapp: telefone do prospect se aparecer na conversa. null se não.
- lead.responsavel: nome/cargo do contato (ex: "Dr. João", "recepcionista"). null se ausente.
- status_sugerido: baseado no estágio real da conversa, não no que o vendedor gostaria.
- resumo_conversa: descreve o fluxo — o que foi dito, como evoluiu, onde parou.
- confianca: inteiro de 1 a 10.
  1-3 = baixa (sem resposta, sem interesse, objeções fortes sem resolução)
  4-6 = incerto (engajou mas sem compromisso, resposta fria ou evasiva)
  7-8 = promissor (interesse genuíno, pediu proposta, fez perguntas de qualificação)
  9-10 = quase certo (negociando detalhes, pediu contrato, prazo definido)
- confianca_razao: explicação honesta do score. Use linguagem que reconhece incerteza:
  "Pelo tom...", "Parece que...", "Sinal de que...", "Difícil concluir sem mais contexto...".
  Mencione os principais fatores a favor E os que geraram dúvida.
- sinais_positivos: 1 a 4 comportamentos concretos do prospect que indicam interesse
  (ex: "Perguntou sobre prazo de implementação", "Disse que tem verba aprovada").
  Lista vazia [] se realmente não houver.
- sinais_preocupantes: 0 a 4 riscos reais
  (ex: "Mencionou que está avaliando concorrente", "Deu desculpas vagas para não avançar").
  Lista vazia [] se não houver preocupações.
- proximo_passo: ação concreta e específica (ex: "Enviar proposta com comparativo de preço até sexta").
- followup_em: data se mencionada explicitamente na conversa (ISO 8601 ou "amanhã"), ou null.
- Nunca invente dados. Se a conversa for curta ou ambígua, reflita isso no score e na razão.
"""

ALLOWED_INTENTS = {"novo", "update", "perdido", "fechado", "corrigir", "vincular", "set"}
MIMETYPE_EXTENSION = {
    "audio/ogg": ".ogg",
    "audio/ogg; codecs=opus": ".ogg",
    "audio/mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/flac": ".flac",
    "audio/oga": ".oga",
}
ALLOWED_EXTENSIONS = {".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".oga", ".ogg", ".wav", ".webm"}


@dataclass
class AudioResolveError(Exception):
    reason: str


class OpenAIService:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key) if api_key else None

    def _extension_from_mimetype(self, mimetype: str | None) -> str | None:
        if not mimetype:
            return None
        mt = mimetype.strip().lower()
        return MIMETYPE_EXTENSION.get(mt)

    def _extension_from_url(self, media_url: str) -> str | None:
        lower = (media_url or "").lower().split("?")[0]
        for ext in ALLOWED_EXTENSIONS:
            if lower.endswith(ext):
                return ext
        return None

    @staticmethod
    def _decrypt_whatsapp_enc(enc_bytes: bytes, media_key_b64: str) -> bytes:
        """Descriptografa arquivo .enc do CDN do WhatsApp usando a mediaKey do payload.

        Algoritmo oficial do WhatsApp:
        1. HKDF-SHA256(media_key, info=b"WhatsApp Audio Keys", length=112)
        2. iv = key_material[0:16], aes_key = key_material[16:48], mac_key = key_material[48:80]
        3. ciphertext = enc_bytes[:-10], file_mac = enc_bytes[-10:]
        4. Verifica HMAC-SHA256(mac_key, iv + ciphertext)[:10] == file_mac
        5. Decripta AES-256-CBC(aes_key, iv, ciphertext) e remove padding PKCS7
        """
        media_key = base64.b64decode(media_key_b64 + "==")  # padding seguro

        key_material = HKDF(
            algorithm=SHA256(),
            length=112,
            salt=None,
            info=b"WhatsApp Audio Keys",
        ).derive(media_key)

        iv = key_material[0:16]
        aes_key = key_material[16:48]
        mac_key = key_material[48:80]

        ciphertext = enc_bytes[:-10]
        file_mac = enc_bytes[-10:]

        h = HMAC(mac_key, SHA256())
        h.update(iv + ciphertext)
        expected_mac = h.finalize()[:10]
        if not hmac.compare_digest(expected_mac, file_mac):
            raise AudioResolveError("mac_invalido")

        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()

        # Remove padding PKCS7
        pad_len = padded[-1]
        return padded[:-pad_len]

    async def _download_and_decrypt_enc(self, media_url: str, media_key_b64: str, mimetype: str | None) -> str:
        """Baixa o .enc e descriptografa, retorna path de arquivo temporário."""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.get(media_url)
                response.raise_for_status()
                enc_bytes = response.content
        except Exception:
            logger.exception("falha_download_enc | url=%s", media_url)
            raise AudioResolveError("falha_download_audio")

        try:
            audio_bytes = self._decrypt_whatsapp_enc(enc_bytes, media_key_b64)
        except AudioResolveError:
            raise
        except Exception:
            logger.exception("falha_decriptacao | url=%s", media_url)
            raise AudioResolveError("falha_decriptacao")

        extension = self._extension_from_mimetype(mimetype) or ".ogg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()
        logger.info("audio .enc descriptografado com sucesso | %d bytes | %s", len(audio_bytes), extension)
        return tmp.name

    async def resolve_whatsapp_audio(
        self, media_url: str, mimetype: str | None, media_key: str | None = None
    ) -> str:
        url_path = (media_url or "").lower().split("?")[0]
        if url_path.endswith(".enc"):
            if media_key:
                logger.info("audio_enc_detectado | descriptografando com mediaKey | url=%s", media_url)
                return await self._download_and_decrypt_enc(media_url, media_key, mimetype)
            logger.error("audio_encriptado | mediaKey ausente, nao e possivel descriptografar | url=%s", media_url)
            raise AudioResolveError("audio_encriptado")

        extension = self._extension_from_mimetype(mimetype) or self._extension_from_url(media_url)
        if not extension:
            logger.error("mimetype_invalido | mimetype=%s media_url=%s", mimetype, media_url)
            raise AudioResolveError("mimetype_invalido")

        if extension not in ALLOWED_EXTENSIONS:
            logger.error("midia_nao_suportada | extension=%s mimetype=%s", extension, mimetype)
            raise AudioResolveError("midia_nao_suportada")

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.get(media_url)
                response.raise_for_status()
                audio_data = response.content
        except Exception:
            logger.exception("falha_download_audio | media_url=%s", media_url)
            raise AudioResolveError("falha_download_audio")

        if not audio_data:
            logger.error("falha_download_audio | empty_content media_url=%s", media_url)
            raise AudioResolveError("falha_download_audio")

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
        tmp.write(audio_data)
        tmp.flush()
        tmp.close()
        return tmp.name

    def _save_base64_audio(self, b64_data: str, mimetype: str | None) -> str:
        """Decodifica base64 do Evolution API e salva em arquivo temporário."""
        audio_bytes = base64.b64decode(b64_data)
        extension = self._extension_from_mimetype(mimetype) or ".ogg"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()
        return tmp.name

    async def transcribe_audio_from_url(
        self,
        media_url: str | None,
        mimetype: str | None = None,
        media_base64: str | None = None,
        media_key: str | None = None,
    ) -> str:
        if not self.client:
            return ""

        # Prioridade: base64 direto > descriptografar .enc com mediaKey > URL já descriptografada
        if media_base64:
            logger.info("transcricao via base64 | tamanho=%d bytes", len(media_base64))
            audio_path = self._save_base64_audio(media_base64, mimetype)
        elif media_url:
            audio_path = await self.resolve_whatsapp_audio(
                media_url=media_url, mimetype=mimetype, media_key=media_key
            )
        else:
            raise AudioResolveError("sem_midia")

        try:
            with open(audio_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(model="whisper-1", file=audio_file)
            text = (transcript.text or "").strip()
            if not text:
                logger.warning("Whisper returned empty transcript")
            return text
        finally:
            try:
                os.remove(audio_path)
            except OSError:
                logger.warning("Failed to remove temporary audio file: %s", audio_path)

    def generate_lead_summary(
        self,
        nome: str | None,
        segmento: str | None,
        status: str | None,
        recent_summaries: list[str],
    ) -> str:
        """Gera um resumo cumulativo do lead com base nos dados + últimas atividades.

        Retorna string ≤180 chars. Fallback se OpenAI indisponível.
        """
        if not self.client or not recent_summaries:
            return ""

        summaries_text = "\n- ".join(recent_summaries)
        user_msg = (
            f"Lead: {nome or 'desconhecido'} | Segmento: {segmento or '?'} | Status: {status or '?'}\n"
            f"Últimas interações:\n- {summaries_text}"
        )
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=100,
                messages=[
                    {"role": "system", "content": LEAD_SUMMARY_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            summary = (resp.choices[0].message.content or "").strip()
            return summary[:180]
        except Exception:
            logger.warning("generate_lead_summary falhou", exc_info=True)
            return ""

    def analyze_conversation(self, conv_text: str) -> ConversationAnalysis:
        """Analisa uma conversa de WhatsApp colada e retorna parecer comercial estruturado."""
        if not self.client:
            return ConversationAnalysis(resumo_conversa="OpenAI não configurado.", confianca_razao="Indisponível.")

        # Trunca para evitar exceder contexto (gpt-4o-mini suporta ~128k tokens, mas 15k chars já é suficiente)
        truncated = conv_text[:15000]

        resp = self.client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": CONVERSATION_ANALYSIS_PROMPT},
                {"role": "user", "content": truncated},
            ],
        )
        content: Any = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("analyze_conversation: JSON inválido do LLM | content=%r", content[:200])
            return ConversationAnalysis(resumo_conversa="Erro ao processar análise.", confianca_razao="Falha na leitura do JSON.")

        # Garante que confianca é int no intervalo [1, 10]
        try:
            data["confianca"] = max(1, min(10, int(data.get("confianca", 5))))
        except (TypeError, ValueError):
            data["confianca"] = 5

        try:
            return ConversationAnalysis.model_validate(data)
        except Exception:
            logger.warning("analyze_conversation: model_validate falhou", exc_info=True)
            return ConversationAnalysis(resumo_conversa="Erro ao validar análise.", confianca_razao="Falha na validação.")

    def extract_structured_data(self, raw_text: str) -> LLMExtraction:
        if not self.client:
            return LLMExtraction(activity={"tipo": "nota", "resumo": raw_text[:200]})

        resp = self.client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": raw_text},
            ],
        )
        content: Any = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("extract_structured_data: JSON inválido do LLM | content=%r", content[:200])
            return LLMExtraction(activity={"tipo": "nota", "resumo": raw_text[:200]})
        intent = str(data.get("intent") or "").strip().lower()
        if intent not in ALLOWED_INTENTS:
            data["intent"] = "update"
        try:
            return LLMExtraction.model_validate(data)
        except Exception:
            logger.warning("extract_structured_data: model_validate falhou", exc_info=True)
            return LLMExtraction(activity={"tipo": "nota", "resumo": raw_text[:200]})
