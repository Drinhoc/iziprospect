from __future__ import annotations

import json
import logging
import tempfile
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
- Nunca invente nome de clínica, cidade, instagram, whatsapp ou site.
- Se não souber um campo, retorne null.
- Se não houver nome claro do lead, mantenha lead.nome = null.
- Se a mensagem for vaga, ainda assim preencha activity.tipo e activity.resumo com o que for observável.
- Preserve datas relativas quando não for possível resolver com segurança (ex.: "amanhã", "semana que vem").
- Não inferir telefone inexistente.
- Retorne somente JSON válido e sem markdown."""


class OpenAIService:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key) if api_key else None

    async def transcribe_audio_from_url(self, media_url: str) -> str:
        if not self.client:
            return ""

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(media_url)
            response.raise_for_status()
            audio_data = response.content

        if not audio_data:
            logger.warning("Audio download returned empty content")
            return ""

        with tempfile.NamedTemporaryFile(suffix=".ogg") as tmp:
            tmp.write(audio_data)
            tmp.flush()
            with open(tmp.name, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(model="whisper-1", file=audio_file)

        text = (transcript.text or "").strip()
        if not text:
            logger.warning("Whisper returned empty transcript")
        return text

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
        return LLMExtraction.model_validate(data)
