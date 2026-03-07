from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class NormalizedEvent(BaseModel):
    msg_id: Optional[str] = None
    msg_type: Literal["text", "audio", "unknown"] = "unknown"
    raw_text: str = ""
    media_url: Optional[str] = None
    media_mimetype: Optional[str] = None
    media_base64: Optional[str] = None
    media_key: Optional[str] = None
    audio_seconds: Optional[int] = None       # duração do áudio em segundos (do payload)
    raw_msg_key: Optional[Dict[str, Any]] = None
    raw_message_obj: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    chat_id: str = ""
    is_group: bool = False
    from_me: bool = False  # True quando a mensagem foi enviada pelo próprio bot


class LeadData(BaseModel):
    nome: Optional[str] = None
    cidade: Optional[str] = None
    segmento: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[str] = None
    instagram: Optional[str] = None
    site: Optional[str] = None
    responsavel: Optional[str] = None        # nome/cargo do contato na clínica
    fonte: Optional[str] = None              # como o lead chegou (cold, indicação, etc.)


class ActivityData(BaseModel):
    tipo: str = "nota"
    resumo: str = ""


class LLMExtraction(BaseModel):
    intent: Literal["novo", "update", "perdido", "fechado", "corrigir", "vincular", "set"] = "update"
    lead: LeadData = Field(default_factory=LeadData)
    status_sugerido: Optional[str] = None
    followup_em: Optional[str] = None
    activity: ActivityData = Field(default_factory=ActivityData)
    pendencia: Optional[str] = None          # ação pendente extraída da mensagem
