from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from app.schemas.models import NormalizedEvent


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_timestamp(raw: Any) -> datetime:
    if raw is None:
        return datetime.utcnow()

    if isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            return datetime.utcnow()
        if candidate.isdigit():
            raw = int(candidate)
        else:
            try:
                return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            except ValueError:
                return datetime.utcnow()

    if isinstance(raw, (int, float)):
        ts = float(raw)
        # milliseconds if very large epoch
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.utcfromtimestamp(ts)

    return datetime.utcnow()


def _extract_text(message: Dict[str, Any], data: Dict[str, Any], payload: Dict[str, Any]) -> str:
    return (
        _first_non_empty(
            message.get("conversation"),
            message.get("extendedTextMessage", {}).get("text"),
            message.get("text"),
            data.get("text"),
            payload.get("text"),
        )
        or ""
    )


def _extract_media_url(message: Dict[str, Any], data: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
    return _first_non_empty(
        message.get("audioMessage", {}).get("url"),
        message.get("audio", {}).get("url"),
        data.get("mediaUrl"),
        payload.get("mediaUrl"),
    )


def normalize_evolution_payload(payload: Dict[str, Any]) -> NormalizedEvent:
    data = payload.get("data", payload)
    message = data.get("message", payload.get("message", {}))
    data_key = data.get("key", {})
    payload_key = payload.get("key", {})

    msg_id = _first_non_empty(
        data_key.get("id"),
        payload_key.get("id"),
        data.get("id"),
        payload.get("id"),
        data.get("messageId"),
        payload.get("messageId"),
    )

    remote_jid = _first_non_empty(
        data_key.get("remoteJid"),
        payload_key.get("remoteJid"),
        data.get("chatId"),
        payload.get("chatId"),
    )

    participant = _first_non_empty(
        data_key.get("participant"),
        payload_key.get("participant"),
        data.get("participant"),
        payload.get("participant"),
    )

    raw_text = _extract_text(message, data, payload)
    media_url = _extract_media_url(message, data, payload)
    msg_type = "audio" if media_url else ("text" if raw_text else "unknown")

    timestamp = _parse_timestamp(
        data.get("messageTimestamp")
        or payload.get("messageTimestamp")
        or data.get("timestamp")
        or payload.get("timestamp")
    )

    return NormalizedEvent(
        msg_id=msg_id,
        msg_type=msg_type,
        raw_text=raw_text,
        media_url=media_url,
        timestamp=timestamp,
        chat_id=remote_jid or "",
        is_group=bool((remote_jid or "").endswith("@g.us") or participant),
    )
