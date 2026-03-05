from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from app.schemas.models import NormalizedEvent


def _parse_timestamp(raw: Any) -> datetime:
    if raw is None:
        return datetime.utcnow()
    if isinstance(raw, (int, float)):
        return datetime.utcfromtimestamp(raw)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.utcnow()
    return datetime.utcnow()


def normalize_evolution_payload(payload: Dict[str, Any]) -> NormalizedEvent:
    data = payload.get("data", payload)
    message = data.get("message", data)

    text = message.get("conversation") or message.get("text") or ""
    audio_url = (
        message.get("audioMessage", {}).get("url")
        or message.get("audio", {}).get("url")
        or data.get("mediaUrl")
    )

    msg_type = "audio" if audio_url else ("text" if text else "unknown")

    return NormalizedEvent(
        msg_type=msg_type,
        raw_text=text,
        media_url=audio_url,
        timestamp=_parse_timestamp(data.get("messageTimestamp") or data.get("timestamp")),
        chat_id=str(data.get("key", {}).get("remoteJid") or data.get("chatId") or ""),
        is_group=bool(data.get("key", {}).get("participant") or str(data.get("chatId", "")).endswith("@g.us")),
    )
