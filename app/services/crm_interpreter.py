from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

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
    # Strip spurious leading zero (old PSTN prefix: 0 + DDD + number)
    if digits.startswith("0") and not digits.startswith("00"):
        digits = digits[1:]
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

    if "depois de amanha" in text:
        return (base + timedelta(days=2)).date().isoformat()
    if "amanha" in text:
        return (base + timedelta(days=1)).date().isoformat()
    if "semana que vem" in text:
        return (base + timedelta(days=7)).date().isoformat()

    # "em X dias" ou "X dias"
    m = re.search(r"em\s+(\d+)\s+dias?", text) or re.search(r"^(\d+)\s+dias?", text)
    if m:
        return (base + timedelta(days=int(m.group(1)))).date().isoformat()

    # dias da semana → próxima ocorrência futura
    _WEEKDAYS = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5}
    for nome, wd in _WEEKDAYS.items():
        if nome in text:
            days_ahead = (wd - base.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # já é hoje, vai para a próxima semana
            return (base + timedelta(days=days_ahead)).date().isoformat()

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


# ---------------------------------------------------------------------------
# Followup command detection ("followup [lead] [data]")
# ---------------------------------------------------------------------------

_FOLLOWUP_CMD_RE = re.compile(
    r"^(?:followup|follow[\s\-]?up|lembrar(?:\s+de)?|falar\s+com|ligar\s+(?:pra|para)|contatar)\s+"
    r"(.+?)\s+"
    r"(amanha|depois\s+de\s+amanha|segunda|terca|quarta|quinta|sexta|sabado|semana\s+que\s+vem"
    r"|em\s+\d+\s+dias?|\d+\s+dias?)\s*$",
    re.IGNORECASE,
)


def detect_followup_command(raw_text: str) -> Optional[tuple]:
    """Detecta comando direto de agendamento: 'followup [lead] [data]'.

    Retorna (nome_lead, date_iso) ou None.
    Não usa LLM — processamento local rápido.
    """
    norm = normalize_text(raw_text)
    m = _FOLLOWUP_CMD_RE.match(norm)
    if not m:
        return None
    lead_name = m.group(1).strip()
    date_part = m.group(2).strip()
    if len(lead_name) < 3:
        return None
    date_str = parse_followup_from_text(date_part)
    if not date_str:
        return None
    return lead_name, date_str


# ---------------------------------------------------------------------------
# Auto-sugestão de followup por status
# ---------------------------------------------------------------------------

_STATUS_FOLLOWUP_RULES: dict = {
    "1º contato":   (5,  "aguardar resposta ou fazer follow-up"),
    "em contato":   (2,  "retomar contato"),
    "qualificado":  (2,  "avançar proposta"),
    "em espera":    (5,  "cobrar retorno"),
    "negociando":   (2,  "fechar negociação"),
    "sem resposta": (30, "tentar nova abordagem"),
}


def suggest_followup_from_status(status: str, now: Optional[datetime] = None) -> Optional[tuple]:
    """Sugere (date_iso, contexto) com base no status do lead.

    Retorna None para status sem followup automático (novo, fechado, perdido, etc).
    """
    rule = _STATUS_FOLLOWUP_RULES.get(status)
    if not rule:
        return None
    days, context = rule
    base = now or datetime.utcnow()
    date_str = (base + timedelta(days=days)).date().isoformat()
    return date_str, context


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
    r"\[\s*(novo|1[oº°]\s*contato|em contato|qualificado|em espera|negociando|fechado|perdido|sem resposta|contato inv[aá]lido)\s*\]",
    re.IGNORECASE,
)

_STATUS_NORMALIZE = {
    "contato invalido": "contato inválido",
    "contato inválido": "contato inválido",
    "1o contato": "1º contato",
    "1° contato": "1º contato",
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
    if any(k in text for k in ["numero errado", "numero invalido", "numero incorreto", "nao existe", "nao tem whatsapp", "nao usa whatsapp"]):
        return "contato inválido"

    # Em espera — você enviou proposta/avançou e aguarda retorno (lead estava engajado)
    if any(k in text for k in ["enviei proposta", "mandei proposta", "proposta enviada", "proposta mandada",
                                "aguardando retorno da proposta", "nao respondeu a proposta",
                                "proposta sem resposta", "sem retorno da proposta"]):
        return "em espera"

    # Sem resposta — verificar ANTES de perdido para evitar falso positivo
    if any(k in text for k in ["sem resposta", "nao respondeu", "nao responde", "nenhuma resposta",
                                "ignorando", "sumiu", "ghosting", "nao retornou", "nunca mais",
                                "nao deu retorno", "sem retorno", "ficou de retornar", "nao viu"]):
        return "sem resposta"

    # Perdido — apenas rejeição explícita e ativa
    if any(k in text for k in ["sem interesse", "nao tem interesse", "nao quer", "descartei", "descartado",
                                "caiu fora", "rejeitou", "pode tirar", "nao vai comprar", "nao precisa"]):
        return "perdido"

    # Negociando
    if any(k in text for k in ["negociando", "negociacao", "ajustando proposta", "quer desconto", "pediu desconto", "condicao de pagamento", "parcelamento"]):
        return "negociando"

    # Qualificado
    if any(k in text for k in ["achou interessante", "quer saber mais", "pediu mais info", "quer conhecer", "demonstrou interesse", "interessou", "gostou bastante", "quer ver demo", "pediu demo", "quer demo"]):
        return "qualificado"

    # Em contato
    if any(k in text for k in ["respondeu", "me respondeu", "retornou", "falei com", "liguei", "atendeu",
                                "mandei mensagem", "enviei mensagem", "contatei"]):
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


# ---------------------------------------------------------------------------
# Micro-update detection
# ---------------------------------------------------------------------------

@dataclass
class MicroUpdate:
    """Resultado de detecção de micro-update conversacional."""
    candidate_name: str   # Nome do lead a buscar no DB
    status: str           # Status a aplicar
    activity_type: str    # Tipo de atividade a registrar


# Campos estruturados: presença indica mensagem rica → deve ir pro LLM
_STRUCTURED_FIELD_RE = [
    re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}"),  # telefone
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),       # email
    re.compile(r"https?://"),                                               # URL
    re.compile(r"@[a-zA-Z0-9_]{3,}"),                                      # instagram
]

# (regex, índice do grupo com nome-candidato, status, activity_type)
# Aplicados sobre o texto normalizado (sem acentos, lowercase)
_MICRO_PATTERNS: List[tuple] = [
    # Nome vem antes do verbo
    (re.compile(r"^(.+?)\s+respondeu\b"),                              "em contato",       "respondeu"),
    (re.compile(r"^(.+?)\s+nao\s+(?:usa|tem)\s+whatsapp\b"),          "contato inválido", "número inválido"),
    (re.compile(r"^(.+?)\s+quer\s+(?:demo|apresentacao|apresentação)\b"), "qualificado",  "demo agendada"),
    (re.compile(r"^(.+?)\s+(?:esta\s+|está\s+)?interessad[ao]\b"),    "qualificado",      "respondeu"),
    (re.compile(r"^(.+?)\s+fechou\b"),                                 "fechado",          "venda fechada"),
    (re.compile(r"^(.+?)\s+nao\s+(?:quer|tem)\s+interesse\b"),        "perdido",          "sem interesse"),
    (re.compile(r"^(.+?)\s+sem\s+interesse\b"),                        "perdido",          "sem interesse"),
    (re.compile(r"^(.+?)\s+descartad[ao]\b"),                          "perdido",          "sem interesse"),
    (re.compile(r"^(.+?)\s+numero\s+(?:errado|invalido|incorreto)\b"), "contato inválido", "número inválido"),
    # Primeiro contato (específico: deve aparecer antes do padrão genérico de mensagem)
    (re.compile(r"^(?:mandei|enviei)\s+(?:o\s+)?primeiro\s+contato\s+(?:pra|para)\s+(?:o\s+|a\s+)?(.+)"), "1º contato", "primeiro contato"),
    (re.compile(r"^fiz\s+(?:o\s+)?primeiro\s+contato\s+(?:com|pra|para)\s+(?:o\s+|a\s+)?(.+)"),            "1º contato", "primeiro contato"),
    (re.compile(r"^1[o°º]\.?\s+contato\s+(?:feito\s+)?(?:pra|para|com)\s+(?:o\s+|a\s+)?(.+)"),            "1º contato", "primeiro contato"),
    (re.compile(r"^primeiro\s+contato\s+(?:feito\s+)?(?:pra|para|com)\s+(?:o\s+|a\s+)?(.+)"),             "1º contato", "primeiro contato"),
    # Verbo vem antes, nome segue
    (re.compile(r"^(?:mandei|enviei)\s+mensagem\s+(?:pra|para)\s+(.+)"), "em contato",    "aguardando resposta"),
    (re.compile(r"^contatei\s+(?:o\s+|a\s+)?(.+)"),                   "em contato",       "aguardando resposta"),
    (re.compile(r"^liguei\s+(?:pra|para)\s+(?:o\s+|a\s+)?(.+)"),     "em contato",       "aguardando resposta"),
]


def detect_micro_update(raw_text: str) -> Optional[MicroUpdate]:
    """Detecta mensagem curta de atualização de status de lead existente.

    Baseado em padrão verbal + ausência de campos estruturados.
    NÃO usa tamanho como critério principal — considera o padrão semântico.

    Retorna MicroUpdate ou None se a mensagem não encaixar.
    """
    text = (raw_text or "").strip()
    if not text:
        return None

    # Presença de campos estruturados → mensagem rica, deve ir pro LLM
    for pattern in _STRUCTURED_FIELD_RE:
        if pattern.search(text):
            return None

    norm = normalize_text(text)

    for pattern, status, activity_type in _MICRO_PATTERNS:
        m = pattern.match(norm)
        if m:
            candidate_name = m.group(1).strip()
            # Nome candidato: não muito curto (ruído) nem muito longo (contexto rico)
            if 3 <= len(candidate_name) <= 50:
                return MicroUpdate(
                    candidate_name=candidate_name,
                    status=status,
                    activity_type=activity_type,
                )

    return None


# ---------------------------------------------------------------------------
# Bulk first-contact detection
# ---------------------------------------------------------------------------

_BULK_FIRST_CONTACT_RE = re.compile(
    r"contato\s+inicial\s+realizado|"
    r"primeiro\s+contato\s+realizado|"
    r"1[o°º]\.?\s+contato\s+realizado|"
    r"fiz\s+(?:o\s+)?(?:1[o°º]\.?\s+)?(?:primeiro\s+)?contato\s+(?:inicial\s+)?(?:nesses?|com\s+esses?|nos?)\s+\d",
    re.IGNORECASE,
)

_BULK_COUNT_RE = re.compile(r"\b(\d+)\b")


def detect_bulk_first_contact(raw_text: str) -> Optional[int]:
    """Detecta mensagem de bulk 'contato inicial realizado nesses N contatos'.

    Retorna o número N de leads a atualizar, ou None se não detectado.
    Se detectado sem número explícito, retorna 0 (significa: atualiza todos recentes).
    """
    if not _BULK_FIRST_CONTACT_RE.search(raw_text or ""):
        return None
    norm = normalize_text(raw_text)
    m = _BULK_COUNT_RE.search(norm)
    return int(m.group(1)) if m else 0


# ---------------------------------------------------------------------------
# Query intent detection
# ---------------------------------------------------------------------------

@dataclass
class QueryIntent:
    """Intenção de consulta ao CRM (leitura, não escrita)."""
    type: str                       # "hoje" | "por_atividade" | "followup" | "por_status" | "pipeline"
    activity_type: Optional[str] = None   # para type="por_atividade"
    status: Optional[str] = None          # para type="por_status"
    days: int = 7                         # janela temporal para consultas


# Padrões de query: (regex sobre texto normalizado, QueryIntent)
_QUERY_PATTERNS: List[tuple] = [
    (re.compile(r"\bleads?\s+(de\s+)?hoje\b"),           QueryIntent(type="hoje")),
    (re.compile(r"\bquantos\s+leads?\s+(de\s+)?hoje\b"), QueryIntent(type="hoje")),
    (re.compile(r"\bquem\s+(me\s+)?respondeu\b"),        QueryIntent(type="por_atividade", activity_type="respondeu", days=7)),
    (re.compile(r"\bquem\s+(devo\s+)?contatar\b"),       QueryIntent(type="followup")),
    (re.compile(r"\bfollow[\s-]?up(s)?\b"),              QueryIntent(type="followup")),
    (re.compile(r"\bleads?\s+qualificados?\b"),           QueryIntent(type="por_status", status="qualificado")),
    (re.compile(r"\bleads?\s+novos?\b"),                  QueryIntent(type="por_status", status="novo")),
    (re.compile(r"\bnovos?\s+leads?\b"),                  QueryIntent(type="por_status", status="novo")),
    (re.compile(r"\bleads?\s+em\s+espera\b"),             QueryIntent(type="por_status", status="em espera")),
    (re.compile(r"\bpipeline\b"),                         QueryIntent(type="pipeline")),
]


def detect_query_intent(raw_text: str) -> Optional[QueryIntent]:
    """Detecta se a mensagem é uma consulta ao CRM (leitura, não atualização).

    Só dispara para mensagens sem telefone e sem campos estruturados.
    Retorna QueryIntent ou None.
    """
    text = (raw_text or "").strip()
    if not text:
        return None

    # Presença de telefone indica lead update, não query
    if re.search(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}", text):
        return None

    norm = normalize_text(text)
    for pattern, intent in _QUERY_PATTERNS:
        if pattern.search(norm):
            return intent

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
