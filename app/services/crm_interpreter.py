from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

ACTION_TYPES = {
    "novo_lead",
    "atualizar_lead",
    "registrar_atividade",
    "registrar_followup",
    "revisao_manual",
}

PHONE_PATTERN = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}")


def _strip_accents(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", value) if unicodedata.category(ch) != "Mn")


def normalize_text(value: str) -> str:
    base = _strip_accents(value or "").lower().strip()
    base = re.sub(r"[^\w\s]", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def norm_phone(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits and not digits.startswith("55") and len(digits) >= 10:
        digits = f"55{digits}"
    return f"+{digits}" if digits else ""


@dataclass
class CRMInterpretation:
    action_type: str
    activity_type: str
    status_sugerido: Optional[str] = None
    followup_em: Optional[str] = None
    resultado_venda: Optional[str] = None  # "ganho", "perdido", ou None
    confidence: float = 0.7


def extract_phone(raw_text: str) -> Optional[str]:
    match = PHONE_PATTERN.search(raw_text or "")
    if not match:
        return None
    return norm_phone(match.group(0))


def parse_followup_from_text(raw_text: str, now: Optional[datetime] = None) -> Optional[str]:
    text = normalize_text(raw_text)
    base = now or datetime.utcnow()

    if "amanha" in text:
        return (base + timedelta(days=1)).date().isoformat()
    if "semana que vem" in text:
        return (base + timedelta(days=7)).date().isoformat()

    if "depois das" in text:
        hour_match = re.search(r"depois das\s*(\d{1,2})", text)
        if hour_match:
            hour = min(int(hour_match.group(1)), 23)
            dt = base.replace(hour=hour, minute=0, second=0, microsecond=0)
            if dt < base:
                dt = dt + timedelta(days=1)
            return dt.isoformat()

    if any(k in text for k in ["retornar", "retorno", "falar", "ligar depois"]):
        return base.date().isoformat()

    return None


def infer_activity_type(raw_text: str) -> str:
    text = normalize_text(raw_text)
    if "contato inicial" in text or "novo" in text:
        return "contato inicial"
    if "respondeu" in text:
        return "respondeu"
    if "proposta" in text:
        return "pediu proposta"
    if "sem interesse" in text:
        return "sem interesse"
    if "numero errado" in text or "numero invalido" in text:
        return "número inválido"
    if any(k in text for k in ["retornar", "retorno", "semana que vem", "amanha", "ligar"]):
        return "retorno agendado"
    if "falei com" in text:
        return "aguardando resposta"
    return "registrar atividade"


def infer_status(raw_text: str) -> Optional[str]:
    text = normalize_text(raw_text)
    if "sem interesse" in text:
        return "perdido"
    if "numero errado" in text or "numero invalido" in text:
        return "contato inválido"
    if "respondeu" in text:
        return "em contato"
    if "proposta" in text:
        return "proposta"
    return None


# Pré-compilados para eficiência e uso de word boundaries.
# Perdido é verificado PRIMEIRO para evitar que "nao fechou" (que contém "fechou")
# seja classificado incorretamente como ganho.
_PERDIDO_RE = [
    re.compile(r"\b" + re.escape(p) + r"\b")
    for p in [
        "nao fechou", "nao avancou", "nao deu negocio", "nao vai dar", "nao conseguiu",
        "perdemos", "cliente desistiu", "descartado", "rejeitou", "rejeitada", "caiu fora",
    ]
]

_GANHO_RE = [
    re.compile(r"\b" + re.escape(p) + r"\b")
    for p in [
        "venda fechada", "cliente fechou", "negocio fechado", "contrato assinado",
        "virou cliente", "fechamos", "fechou", "assinado",
    ]
]


def detect_sales_result(raw_text: str) -> Optional[str]:
    """Detecta resultado de venda na mensagem.

    Retorna: "ganho", "perdido", ou None.
    Usa word boundaries para evitar matches parciais e verifica perdido antes
    de ganho para que "nao fechou" não seja classificado como ganho.
    """
    text = normalize_text(raw_text)
    if any(p.search(text) for p in _PERDIDO_RE):
        return "perdido"
    if any(p.search(text) for p in _GANHO_RE):
        return "ganho"
    return None


def interpret_crm_message(raw_text: str, has_name: bool, has_phone: bool) -> CRMInterpretation:
    followup = parse_followup_from_text(raw_text)
    activity_type = infer_activity_type(raw_text)
    status = infer_status(raw_text)
    resultado = detect_sales_result(raw_text)

    # Se detectado resultado de venda, sobrescreve o status sugerido
    if resultado == "ganho":
        status = "fechado"
        activity_type = "venda fechada"
    elif resultado == "perdido":
        status = "perdido"
        activity_type = "oportunidade perdida"

    if has_name and has_phone:
        return CRMInterpretation("novo_lead", activity_type or "contato inicial", status or "novo", followup, resultado, confidence=0.93)
    if has_phone or has_name:
        action = "registrar_followup" if followup else "atualizar_lead"
        return CRMInterpretation(action, activity_type, status, followup, resultado, confidence=0.86)

    if followup or activity_type != "registrar atividade":
        action = "registrar_followup" if followup else "registrar_atividade"
        return CRMInterpretation(action, activity_type, status, followup, resultado, confidence=0.72)

    return CRMInterpretation("revisao_manual", "registrar atividade", status, followup, resultado, confidence=0.45)
