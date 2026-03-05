from __future__ import annotations

import httpx


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
