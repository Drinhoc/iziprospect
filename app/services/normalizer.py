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
    # Prioriza a URL do Evolution API (já descriptografada) sobre a URL direta
    # do CDN do WhatsApp, que é um arquivo .enc criptografado inutilizável.
    return _first_non_empty(
        data.get("mediaUrl"),
        payload.get("mediaUrl"),
        message.get("audioMessage", {}).get("url"),
        message.get("audio", {}).get("url"),
    )


def _extract_mimetype(message: Dict[str, Any], data: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
    return _first_non_empty(
        message.get("audioMessage", {}).get("mimetype"),
        message.get("audio", {}).get("mimetype"),
        data.get("mimetype"),
        payload.get("mimetype"),
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
    media_mimetype = _extract_mimetype(message, data, payload)
    # "Webhook Based64" do Evolution API: conteúdo do áudio em base64 no payload,
    # evitando a necessidade de baixar o arquivo criptografado do CDN do WhatsApp.
    media_base64 = _first_non_empty(data.get("base64"), payload.get("base64"))
    # mediaKey vem dentro de audioMessage e é necessária para descriptografar o .enc
    # O Evolution serializa bytes como dict {"0": 97, "1": 13, ...} em vez de base64
    audio_msg = message.get("audioMessage", {}) or message.get("audio", {}) or {}
    raw_media_key = audio_msg.get("mediaKey") or data.get("mediaKey")
    import base64 as _b64
    media_key: Optional[str] = None
    if isinstance(raw_media_key, str) and raw_media_key.strip():
        media_key = raw_media_key.strip()
    elif isinstance(raw_media_key, bytes):
        media_key = _b64.b64encode(raw_media_key).decode()
    elif isinstance(raw_media_key, dict) and raw_media_key:
        # {"0": 97, "1": 13, ...} → bytes → base64 (formato protobuf do Evolution)
        try:
            raw_bytes = bytes(raw_media_key[str(i)] for i in range(len(raw_media_key)))
            media_key = _b64.b64encode(raw_bytes).decode()
        except Exception:
            pass
    # Duração do áudio em segundos (presente no audioMessage do WhatsApp)
    audio_seconds: Optional[int] = None
    try:
        raw_seconds = audio_msg.get("seconds") or audio_msg.get("duration")
        if raw_seconds is not None:
            audio_seconds = int(raw_seconds)
    except (ValueError, TypeError):
        pass

    is_audio = bool(
        message.get("audioMessage")
        or message.get("audio")
        or media_url
        or media_base64
    )
    msg_type = "audio" if is_audio else ("text" if raw_text else "unknown")

    # Preserva key e message object para uso como fallback via getBase64FromMediaMessage
    raw_msg_key = dict(data_key) if data_key else (dict(payload_key) if payload_key else None)
    raw_message_obj = dict(message) if message else None

    timestamp = _parse_timestamp(
        data.get("messageTimestamp")
        or payload.get("messageTimestamp")
        or data.get("timestamp")
        or payload.get("timestamp")
    )

    from_me = bool(
        data_key.get("fromMe")
        or payload_key.get("fromMe")
        or data.get("fromMe")
        or payload.get("fromMe")
    )

    return NormalizedEvent(
        msg_id=msg_id,
        msg_type=msg_type,
        raw_text=raw_text,
        media_url=media_url,
        media_mimetype=media_mimetype,
        media_base64=media_base64,
        media_key=media_key if msg_type == "audio" else None,
        audio_seconds=audio_seconds if msg_type == "audio" else None,
        raw_msg_key=raw_msg_key if msg_type == "audio" else None,
        raw_message_obj=raw_message_obj if msg_type == "audio" else None,
        timestamp=timestamp,
        chat_id=remote_jid or "",
        is_group=bool((remote_jid or "").endswith("@g.us") or participant),
        from_me=from_me,
    )
