from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class NormalizedEvent(BaseModel):
    msg_id: Optional[str] = None
    msg_type: Literal["text", "audio", "unknown"] = "unknown"
    raw_text: str = ""
    media_url: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    chat_id: str = ""
    is_group: bool = False


class LeadData(BaseModel):
    nome: Optional[str] = None
    cidade: Optional[str] = None
    segmento: Optional[str] = None
    whatsapp: Optional[str] = None
    instagram: Optional[str] = None
    site: Optional[str] = None


class ActivityData(BaseModel):
    tipo: str = "nota"
    resumo: str = ""


class LLMExtraction(BaseModel):
    intent: Literal["novo", "update", "perdido", "fechado", "corrigir", "vincular", "set"] = "update"
    lead: LeadData = Field(default_factory=LeadData)
    status_sugerido: Optional[str] = None
    followup_em: Optional[str] = None
    activity: ActivityData = Field(default_factory=ActivityData)
