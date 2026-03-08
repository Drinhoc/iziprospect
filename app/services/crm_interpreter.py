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
    if "contato inicial" in text or "novo lead" in text:
        return "contato inicial"
    if any(k in text for k in ["sem interesse", "nao quer", "nao tem interesse", "descartei"]):
        return "sem interesse"
    if any(k in text for k in ["numero errado", "numero invalido", "numero incorreto"]):
        return "número inválido"
    if any(k in text for k in ["demo agendada", "agendei demo", "apresentacao marcada"]):
        return "demo agendada"
    if any(k in text for k in ["proposta enviada", "mandei proposta", "enviei proposta"]):
        return "pediu proposta"
    if "proposta" in text and any(k in text for k in ["vou mandar", "vou enviar", "mandar amanha", "enviar amanha"]):
        return "pediu proposta"
    if any(k in text for k in ["negociando", "ajustando proposta", "quer desconto", "pediu desconto", "parcelamento"]):
        return "nota"
    if "respondeu" in text or "me respondeu" in text:
        return "respondeu"
    if any(k in text for k in ["retornar", "retorno", "semana que vem", "amanha", "ligar depois", "follow"]):
        return "retorno agendado"
    if any(k in text for k in ["falei", "liguei", "mandei mensagem", "tentei contato"]):
        return "aguardando resposta"
    return "registrar atividade"


# Override explícito: usuário pode forçar status entre colchetes, ex: [qualificado]
_STATUS_OVERRIDE_RE = re.compile(
    r"\[\s*(novo|em contato|qualificado|negociando|fechado|perdido|sem resposta|contato inv[aá]lido)\s*\]",
    re.IGNORECASE,
)

_STATUS_NORMALIZE = {
    "contato invalido": "contato inválido",
    "contato inválido": "contato inválido",
}


def extract_status_override(raw_text: str) -> Optional[str]:
    """Retorna o status explicitamente escrito pelo usuário entre colchetes, se houver.

    Exemplo: "Clínica X [qualificado] - tá interessada" → "qualificado"
    """
    m = _STATUS_OVERRIDE_RE.search(raw_text or "")
    if not m:
        return None
    val = m.group(1).lower().strip()
    return _STATUS_NORMALIZE.get(val, val)


def infer_status(raw_text: str) -> Optional[str]:
    text = normalize_text(raw_text)

    # Contato inválido
    if any(k in text for k in ["numero errado", "numero invalido", "numero incorreto", "nao existe", "nao tem whatsapp"]):
        return "contato inválido"

    # Sem resposta — verificar ANTES de perdido para evitar falso positivo
    # "sumiu", "não retornou", "nenhuma resposta" → sem resposta (não perdido)
    if any(k in text for k in ["sem resposta", "nao respondeu", "nao responde", "nenhuma resposta",
                                "ignorando", "sumiu", "ghosting", "nao retornou", "nunca mais",
                                "nao deu retorno", "sem retorno", "ficou de retornar", "nao viu"]):
        return "sem resposta"

    # Perdido — apenas rejeição explícita e ativa
    if any(k in text for k in ["sem interesse", "nao tem interesse", "nao quer", "descartei", "descartado",
                                "caiu fora", "rejeitou", "pode tirar", "nao vai comprar", "nao precisa"]):
        return "sem resposta"

    # Negociando (verificar antes de proposta)
    if any(k in text for k in ["negociando", "negociacao", "ajustando proposta", "quer desconto", "pediu desconto", "condicao de pagamento", "parcelamento"]):
        return "negociando"

    # Proposta enviada
    if any(k in text for k in ["proposta enviada", "mandei proposta", "enviei proposta", "proposta mandada"]):
        return "proposta enviada"

    # Qualificado
    if any(k in text for k in ["achou interessante", "quer saber mais", "pediu mais info", "quer conhecer", "demonstrou interesse", "interessou", "gostou bastante", "quer ver demo", "pediu demo"]):
        return "qualificado"

    # Em contato
    if any(k in text for k in ["respondeu", "me respondeu", "retornou", "falei com", "liguei", "atendeu"]):
        return "em contato"

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
