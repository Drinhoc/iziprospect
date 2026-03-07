from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class EvolutionService:
    def __init__(self, base_url: str | None, api_key: str | None):
        self.base_url = base_url
        self.api_key = api_key

    async def send_confirmation(self, chat_id: str, text: str) -> bool:
        if not self.base_url or not self.api_key:
            return False
        url = f"{self.base_url.rstrip('/')}/message/sendText"
        headers = {"apikey": self.api_key}
        payload = {"number": chat_id, "textMessage": {"text": text}}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload, headers=headers)
        return resp.is_success

    async def fetch_audio_base64(
        self,
        instance_name: str,
        msg_key: Dict[str, Any],
        message_obj: Dict[str, Any],
    ) -> Optional[str]:
        """Busca o áudio em base64 via Evolution API getBase64FromMediaMessage.

        Fallback necessário quando o toggle 'Webhook Based64' do Evolution tem bug
        e não envia o base64 no payload do webhook.

        Retorna a string base64 do áudio ou None em caso de falha.
        """
        if not self.base_url or not self.api_key:
            logger.warning("fetch_audio_base64 ignorado: base_url ou api_key ausente")
            return None

        url = f"{self.base_url.rstrip('/')}/message/getBase64FromMediaMessage/{instance_name}"
        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        body = {"message": {"key": msg_key, "message": message_obj}, "convertToMp4": False}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=body, headers=headers)
            if not resp.is_success:
                logger.error(
                    "fetch_audio_base64 falhou | status=%s body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                return None
            data = resp.json()
            # Evolution retorna {"base64": "...", "mimetype": "..."}
            b64 = data.get("base64") or data.get("data", {}).get("base64")
            if not b64:
                logger.error("fetch_audio_base64: campo base64 ausente na resposta | keys=%s", list(data.keys()))
                return None
            logger.info("fetch_audio_base64 OK | tamanho=%d chars", len(b64))
            return b64
        except Exception:
            logger.exception("fetch_audio_base64 exception")
            return None
