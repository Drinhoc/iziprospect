from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import httpx
from openai import OpenAI

from app.schemas.models import LLMExtraction

logger = logging.getLogger(__name__)

PROMPT = """Você extrai CRM de mensagens WhatsApp em português. Retorne SOMENTE JSON válido com schema:
{
  "intent": "novo|update|perdido|fechado|corrigir|vincular|set",
  "lead": {"nome":null, "cidade":null, "segmento":null, "whatsapp":null, "instagram":null, "site":null},
  "status_sugerido": null,
  "followup_em": null,
  "activity": {"tipo":"", "resumo":""}
}
Regras obrigatórias:
- Nunca invente nome, cidade, instagram, whatsapp ou site.
- Se não souber um campo, retorne null.
- Se houver texto suficiente para um nome provável no início da mensagem, preencha lead.nome com esse trecho.
- Não corrigir ortografia do usuário.
- Não inferir telefone inexistente.
- Se intent for incerto, use "update" (nunca null).
- activity.resumo deve ser curto, factual e operacional.
- Retorne somente JSON válido e sem markdown.

Exemplo:
Entrada: "Clinca sorrisa, 19 998998988 odonto"
Saída:
{
"intent":"novo",
"lead":{"nome":"Clinca sorrisa","cidade":null,"segmento":"odonto","whatsapp":"19998998988","instagram":null,"site":null},
"status_sugerido":"novo",
"followup_em":null,
"activity":{"tipo":"contato inicial","resumo":"Lead informado com nome provável 'Clinca sorrisa', telefone 19 998998988 e segmento odonto."}
}
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

    async def resolve_whatsapp_audio(self, media_url: str, mimetype: str | None) -> str:
        # Arquivo .enc = CDN do WhatsApp criptografado. O Evolution API precisa estar
        # configurado para baixar e servir a mídia descriptografada (mediaUrl no payload).
        url_path = (media_url or "").lower().split("?")[0]
        if url_path.endswith(".enc"):
            logger.error("audio_encriptado | Evolution nao descriptografou a midia | url=%s", media_url)
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
    ) -> str:
        if not self.client:
            return ""

        # Prefere base64 (Evolution "Webhook Based64") para evitar baixar arquivo
        # criptografado do CDN do WhatsApp.
        if media_base64:
            logger.info("transcricao via base64 | tamanho=%d bytes", len(media_base64))
            audio_path = self._save_base64_audio(media_base64, mimetype)
        elif media_url:
            audio_path = await self.resolve_whatsapp_audio(media_url=media_url, mimetype=mimetype)
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
        data = json.loads(content)
        intent = str(data.get("intent") or "").strip().lower()
        if intent not in ALLOWED_INTENTS:
            data["intent"] = "update"
        return LLMExtraction.model_validate(data)
