from __future__ import annotations

import json
import tempfile
from typing import Any

import httpx
from openai import OpenAI

from app.schemas.models import LLMExtraction

PROMPT = """Você extrai CRM de mensagens WhatsApp em português. Retorne SOMENTE JSON válido com schema:
{
  "intent": "novo|update|perdido|fechado|corrigir|vincular|set",
  "lead": {"nome":null, "cidade":null, "segmento":null, "whatsapp":null, "instagram":null, "site":null},
  "status_sugerido": null,
  "followup_em": null,
  "activity": {"tipo":"", "resumo":""}
}
Sem markdown. Normalize telefones para dígitos+ +55 se óbvio."""


class OpenAIService:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key) if api_key else None

    async def transcribe_audio_from_url(self, media_url: str) -> str:
        if not self.client:
            return ""

        async with httpx.AsyncClient(timeout=60) as client:
            audio_data = (await client.get(media_url)).content

        with tempfile.NamedTemporaryFile(suffix=".ogg") as tmp:
            tmp.write(audio_data)
            tmp.flush()
            with open(tmp.name, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(model="whisper-1", file=audio_file)
        return transcript.text

    def extract_structured_data(self, raw_text: str) -> LLMExtraction:
        if not self.client:
            return LLMExtraction()

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
