from __future__ import annotations

import functools
import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

LEADS_HEADERS = [
    "lead_id",
    "nome",
    "cidade",
    "segmento",
    "whatsapp",
    "instagram",
    "site",
    "status",
    "ultima_interacao_em",
    "proximo_followup_em",
    "observacoes",
    "nome_normalizado",
    "cidade_normalizada",
    "lead_key",
]

ATIV_HEADERS = [
    "data_hora",
    "msg_id",
    "lead_id",
    "tipo",
    "canal",
    "mensagem_bruta",
    "resumo",
    "followup_em",
]

REV_HEADERS = [
    "data_hora",
    "mensagem_bruta",
    "cidade_detectada",
    "nome_detectado",
    "candidatos",
    "acao",
    "resolvido_em",
]

GENERIC_NAME_TOKENS = {
    "clinica",
    "clínica",
    "consultorio",
    "consultório",
    "odontologia",
    "odonto",
    "estetica",
    "estética",
}


def _gspread_retry(max_retries: int = 3, initial_delay: float = 1.0):
    """Decorator que reprocessa chamadas ao gspread em erros transientes (429, 500, 503)."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except gspread.exceptions.APIError as exc:
                    status = 0
                    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
                        status = exc.response.status_code
                    if attempt == max_retries or status not in (429, 500, 503):
                        raise
                    logger.warning(
                        "gspread transient error | status=%s | retry %d/%d | delay=%.1fs",
                        status, attempt + 1, max_retries, delay,
                    )
                    time.sleep(delay)
                    delay *= 2
        return wrapper
    return decorator


def _strip_accents(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", value) if unicodedata.category(ch) != "Mn")


def normalize_text(value: str) -> str:
    base = _strip_accents(value or "").lower().strip()
    base = re.sub(r"[^\w\s]", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def canonicalize_name(value: str) -> str:
    normalized = normalize_text(value)
    tokens = normalized.split()
    while tokens and tokens[0] in GENERIC_NAME_TOKENS:
        tokens = tokens[1:]
    while tokens and tokens[-1] in GENERIC_NAME_TOKENS:
        tokens = tokens[:-1]
    return " ".join(tokens) if tokens else normalized


def norm_phone(value: Optional[str]) -> str:
    if value is None:
        return ""

    # Google Sheets pode devolver número como int/float em get_all_records.
    if isinstance(value, (int, float)):
        value = str(int(value))
    else:
        value = str(value)

    value = value.strip()
    if not value:
        return ""

    digits = "".join(ch for ch in value if ch.isdigit())
    if digits and not digits.startswith("55") and len(digits) >= 10:
        digits = f"55{digits}"
    return f"+{digits}" if digits else ""


@dataclass
class MatchResult:
    matched: Optional[Dict[str, str]]
    score: float = 0.0
    needs_review: bool = False
    candidates: Optional[List[Dict[str, str]]] = None


class SheetsService:
    def __init__(self, service_account_info: dict, sheet_id: str):
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(sheet_id)
        self.ws_leads = self._get_or_create("LEADS", LEADS_HEADERS)
        self.ws_ativ = self._get_or_create("ATIVIDADES", ATIV_HEADERS)
        self.ws_rev = self._get_or_create("REVISAR", REV_HEADERS)
        # Lock para evitar race condition na geração de lead_id
        self._lock = threading.Lock()

    def _get_or_create(self, title: str, headers: List[str]):
        try:
            ws = self.sheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title=title, rows=1000, cols=len(headers) + 5)
            ws.append_row(headers)
            return ws

        existing = ws.row_values(1)
        if existing != headers:
            ws.clear()
            ws.append_row(headers)
        return ws

    @_gspread_retry()
    def leads(self) -> List[Dict[str, str]]:
        return self.ws_leads.get_all_records()

    def next_lead_id(self) -> str:
        ids = [row.get("lead_id", "") for row in self.leads()]
        numeric = [int(i[1:]) for i in ids if isinstance(i, str) and i.startswith("L") and i[1:].isdigit()]
        return f"L{(max(numeric) + 1) if numeric else 1:04d}"

    @_gspread_retry()
    def activity_exists_by_msg_id(self, msg_id: str) -> bool:
        if not msg_id:
            return False
        records = self.ws_ativ.get_all_records()
        return any(str(row.get("msg_id", "")).strip().lower() == msg_id.strip().lower() for row in records)

    def match_lead(self, lead: Dict[str, str]) -> MatchResult:
        all_leads = self.leads()
        whatsapp = norm_phone(lead.get("whatsapp"))
        insta = normalize_text(lead.get("instagram") or "")

        canonical_name = canonicalize_name(lead.get("nome") or "")
        lead_key = f"{normalize_text(lead.get('cidade') or '')}:{canonical_name}"

        for row in all_leads:
            if whatsapp and norm_phone(row.get("whatsapp")) == whatsapp:
                return MatchResult(matched=row, score=1.0)
        for row in all_leads:
            if insta and normalize_text(row.get("instagram") or "") == insta:
                return MatchResult(matched=row, score=0.99)
        for row in all_leads:
            if lead_key and row.get("lead_key") == lead_key:
                return MatchResult(matched=row, score=0.98)

        cidade_norm = normalize_text(lead.get("cidade") or "")
        nome_norm = canonical_name
        for row in all_leads:
            row_name = canonicalize_name(row.get("nome", ""))
            if cidade_norm and row.get("cidade_normalizada") == cidade_norm and nome_norm and nome_norm in row_name:
                return MatchResult(matched=row, score=0.9)
            if not cidade_norm and nome_norm and (nome_norm in row_name or row_name in nome_norm):
                return MatchResult(matched=row, score=0.89)

        scored: List[Tuple[float, Dict[str, str]]] = []
        for row in all_leads:
            if cidade_norm and row.get("cidade_normalizada") and row.get("cidade_normalizada") != cidade_norm:
                continue
            target = canonicalize_name(row.get("nome", ""))
            if not nome_norm or not target:
                continue
            sim = max(fuzz.ratio(nome_norm, target) / 100.0, SequenceMatcher(None, nome_norm, target).ratio())
            scored.append((sim, row))

        if not scored:
            return MatchResult(matched=None, score=0)

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_row = scored[0]
        if best_score >= 0.88:
            return MatchResult(matched=best_row, score=best_score)
        if 0.78 <= best_score < 0.88:
            top3 = [r for _, r in scored[:3]]
            return MatchResult(matched=None, score=best_score, needs_review=True, candidates=top3)
        return MatchResult(matched=None, score=best_score)

    def _update_lead_row(
        self,
        lead_id: str,
        lead: Dict[str, str],
        status: Optional[str],
        followup_em: Optional[str],
        when: datetime,
    ) -> str:
        """Atualiza os campos de um lead existente pelo seu row index."""
        records = self.ws_leads.get_all_values()
        row_idx = next(i for i, row in enumerate(records, start=1) if i > 1 and row[0] == lead_id)
        existing = dict(zip(LEADS_HEADERS, records[row_idx - 1]))
        for key in ["nome", "cidade", "segmento", "whatsapp", "instagram", "site", "nome_normalizado", "cidade_normalizada", "lead_key"]:
            if lead.get(key):
                existing[key] = lead[key]
        existing["ultima_interacao_em"] = when.isoformat()
        if status:
            existing["status"] = status
        if followup_em:
            existing["proximo_followup_em"] = followup_em
        self.ws_leads.update(f"A{row_idx}:N{row_idx}", [[existing[h] for h in LEADS_HEADERS]])
        return lead_id

    @_gspread_retry()
    def upsert_lead(self, lead: Dict[str, str], status: Optional[str], followup_em: Optional[str], when: datetime) -> str:
        lead = {k: (v or "") for k, v in lead.items()}
        lead["whatsapp"] = norm_phone(lead.get("whatsapp"))
        lead["nome_normalizado"] = normalize_text(lead.get("nome", ""))
        lead["cidade_normalizada"] = normalize_text(lead.get("cidade", ""))
        canonical_name = canonicalize_name(lead.get("nome", ""))
        lead["lead_key"] = f"{lead['cidade_normalizada']}:{canonical_name}"

        match = self.match_lead(lead)
        phone_in_new = lead["whatsapp"]  # já normalizado acima

        # Telefone é identificador único. Se o novo lead tem telefone mas o match
        # foi por similaridade de nome (não por telefone/instagram/lead_key),
        # verifica se há conflito de telefone com o lead encontrado.
        # Leads com telefones distintos são entidades distintas → cria novo lead.
        if phone_in_new and match.score < 0.95:
            if match.needs_review:
                # Candidatos fuzzy têm telefones diferentes → novo lead
                logger.info(
                    "upsert_lead: telefone único detectado, ignorando revisão fuzzy | phone=%s score=%.2f",
                    phone_in_new, match.score,
                )
                match = MatchResult(matched=None, score=0)
            elif match.matched:
                matched_phone = norm_phone(match.matched.get("whatsapp"))
                if matched_phone and matched_phone != phone_in_new:
                    logger.info(
                        "upsert_lead: telefone conflitante no match por nome, criando novo lead | new=%s existing=%s",
                        phone_in_new, matched_phone,
                    )
                    match = MatchResult(matched=None, score=0)

        if match.needs_review:
            self.add_review(when, "", lead.get("cidade"), lead.get("nome"), match.candidates or [], "revisar_match")
            return ""

        if match.matched:
            return self._update_lead_row(match.matched["lead_id"], lead, status, followup_em, when)

        # Sem match – usa lock para evitar race condition na geração do lead_id
        with self._lock:
            # Re-verifica após adquirir o lock: outra thread pode ter criado o lead entre o match acima e o lock
            match2 = self.match_lead(lead)
            if match2.matched:
                return self._update_lead_row(match2.matched["lead_id"], lead, status, followup_em, when)

            lead_id = self.next_lead_id()
            row = {
                "lead_id": lead_id,
                "status": status or "novo",
                "ultima_interacao_em": when.isoformat(),
                "proximo_followup_em": followup_em or "",
                "observacoes": "",
                **{k: lead.get(k, "") for k in ["nome", "cidade", "segmento", "whatsapp", "instagram", "site", "nome_normalizado", "cidade_normalizada", "lead_key"]},
            }
            self.ws_leads.append_row([row.get(h, "") for h in LEADS_HEADERS])
            return lead_id

    @_gspread_retry()
    def add_activity(self, when: datetime, msg_id: str, lead_id: str, tipo: str, canal: str, mensagem_bruta: str, resumo: str, followup_em: Optional[str]):
        self.ws_ativ.append_row([
            when.isoformat(),
            msg_id,
            lead_id,
            tipo,
            canal,
            mensagem_bruta,
            resumo,
            followup_em or "",
        ])

    @_gspread_retry()
    def add_review(self, when: datetime, mensagem_bruta: str, cidade_detectada: Optional[str], nome_detectado: Optional[str], candidatos: List[Dict[str, str]], acao: str):
        cand = "; ".join(f"{c.get('lead_id')}:{c.get('nome')}" for c in candidatos)
        self.ws_rev.append_row([when.isoformat(), mensagem_bruta, cidade_detectada or "", nome_detectado or "", cand, acao, ""])

    @_gspread_retry()
    def update_lead_fields(self, lead_id: str, fields: Dict[str, str]) -> bool:
        records = self.ws_leads.get_all_values()
        for idx, row in enumerate(records[1:], start=2):
            if row[0] == lead_id:
                current = dict(zip(LEADS_HEADERS, row))
                current.update(fields)
                if "nome" in fields:
                    current["nome_normalizado"] = normalize_text(current["nome"])
                if "cidade" in fields:
                    current["cidade_normalizada"] = normalize_text(current["cidade"])
                current["lead_key"] = f"{current['cidade_normalizada']}:{canonicalize_name(current['nome'])}"
                self.ws_leads.update(f"A{idx}:N{idx}", [[current[h] for h in LEADS_HEADERS]])
                return True
        return False

    @_gspread_retry()
    def bind_latest_activity_to_lead(self, lead_id: str) -> bool:
        # MVP: vincula na atividade mais recente que ainda não possui lead_id.
        records = self.ws_ativ.get_all_values()
        if len(records) < 2:
            return False

        for row_idx in range(len(records), 1, -1):
            row = records[row_idx - 1]
            current_lead = row[2] if len(row) > 2 else ""
            if not str(current_lead).strip():
                self.ws_ativ.update(f"C{row_idx}", [[lead_id]])
                return True
        return False

    @_gspread_retry()
    def latest_linked_lead_id(self) -> str:
        records = self.ws_ativ.get_all_values()
        if len(records) < 2:
            return ""
        for row_idx in range(len(records), 1, -1):
            row = records[row_idx - 1]
            lead_id = row[2] if len(row) > 2 else ""
            if str(lead_id).strip():
                return str(lead_id).strip()
        return ""
