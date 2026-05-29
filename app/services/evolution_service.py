from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class EvolutionService:
    def __init__(self, base_url: str | None, api_key: str | None, instance_name: str | None = None):
        self.base_url = base_url
        self.api_key = api_key
        self.instance_name = instance_name

    async def send_confirmation(self, chat_id: str, text: str) -> bool:
        if not self.base_url or not self.api_key or not self.instance_name:
            logger.debug("send_confirmation ignorado: base_url/api_key/instance_name ausente")
            return False
        # Evolution API v1/v2: POST /message/sendText/{instance}
        url = f"{self.base_url.rstrip('/')}/message/sendText/{self.instance_name}"
        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        # v1 usa textMessage.text; v2 usa text direto — tenta v2 primeiro
        payload = {"number": chat_id, "text": text}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 404:
                # Fallback para formato v1
                payload_v1 = {"number": chat_id, "textMessage": {"text": text}}
                resp = await client.post(url, json=payload_v1, headers=headers)
        if not resp.is_success:
            logger.warning("send_confirmation falhou | status=%s url=%s", resp.status_code, url)
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
        """
        if not self.base_url or not self.api_key:
            logger.warning("fetch_audio_base64 ignorado: base_url ou api_key ausente")
            return None

        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        body = {"message": {"key": msg_key, "message": message_obj}, "convertToMp4": False}

        candidate_paths = [
            f"/chat/getBase64FromMedia/{instance_name}",
            f"/message/getBase64FromMediaMessage/{instance_name}",
        ]

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                for path in candidate_paths:
                    url = f"{self.base_url.rstrip('/')}{path}"
                    resp = await client.post(url, json=body, headers=headers)
                    if resp.status_code == 404:
                        logger.warning("fetch_audio_base64 path não encontrado, tentando próximo | path=%s", path)
                        continue
                    if not resp.is_success:
                        logger.error(
                            "fetch_audio_base64 falhou | path=%s status=%s body=%s",
                            path, resp.status_code, resp.text[:300],
                        )
                        return None
                    data = resp.json()
                    b64 = data.get("base64") or data.get("data", {}).get("base64")
                    if not b64:
                        logger.error(
                            "fetch_audio_base64: campo base64 ausente | path=%s keys=%s",
                            path, list(data.keys()),
                        )
                        return None
                    logger.info("fetch_audio_base64 OK | path=%s tamanho=%d chars", path, len(b64))
                    return b64
            logger.error("fetch_audio_base64: todos os paths retornaram 404")
            return None
        except Exception:
            logger.exception("fetch_audio_base64 exception")
            return None

    # ------------------------------------------------------------------
    # Gerenciamento de instâncias (usa global_api_key do servidor)
    # ------------------------------------------------------------------

    async def create_instance(
        self, instance_name: str, webhook_url: str, global_api_key: str
    ) -> Dict[str, Any]:
        if not self.base_url:
            raise ValueError("EVOLUTION_API_URL não configurado")
        url = f"{self.base_url.rstrip('/')}/instance/create"
        headers = {"apikey": global_api_key, "Content-Type": "application/json"}
        body = {
            "instanceName": instance_name,
            "webhook": {
                "url": webhook_url,
                "enabled": True,
                "webhookByEvents": False,
                "events": ["MESSAGES_UPSERT"],
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body, headers=headers)
        if not resp.is_success:
            logger.warning("create_instance falhou | %s %s", resp.status_code, resp.text[:200])
        return resp.json() if resp.is_success else {}

    async def get_qr_code(self, instance_name: str, global_api_key: str) -> Optional[str]:
        """Retorna base64 do QR code ou None se já conectado."""
        url = f"{self.base_url.rstrip('/')}/instance/connect/{instance_name}"
        headers = {"apikey": global_api_key}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
        if not resp.is_success:
            return None
        data = resp.json()
        return (
            data.get("base64")
            or data.get("qrcode", {}).get("base64")
            or data.get("code")
        )

    async def get_instance_status(self, instance_name: str, global_api_key: str) -> str:
        """Retorna 'open', 'close', 'connecting' ou 'unknown'."""
        url = f"{self.base_url.rstrip('/')}/instance/connectionState/{instance_name}"
        headers = {"apikey": global_api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
        if not resp.is_success:
            return "unknown"
        data = resp.json()
        return (
            data.get("instance", {}).get("state")
            or data.get("state")
            or "unknown"
        )

    async def delete_instance(self, instance_name: str, global_api_key: str) -> bool:
        url = f"{self.base_url.rstrip('/')}/instance/delete/{instance_name}"
        headers = {"apikey": global_api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(url, headers=headers)
        return resp.is_success

    async def reconnect_instance(self, instance_name: str, global_api_key: str) -> bool:
        url = f"{self.base_url.rstrip('/')}/instance/restart/{instance_name}"
        headers = {"apikey": global_api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers)
        return resp.is_success
