from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials
from rapidfuzz import fuzz

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


def normalize_text(value: str) -> str:
    return "".join(c.lower() for c in value.strip() if c.isalnum() or c.isspace()).strip()


def norm_phone(value: Optional[str]) -> str:
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

    def leads(self) -> List[Dict[str, str]]:
        return self.ws_leads.get_all_records()

    def next_lead_id(self) -> str:
        ids = [row.get("lead_id", "") for row in self.leads()]
        numeric = [int(i[1:]) for i in ids if isinstance(i, str) and i.startswith("L") and i[1:].isdigit()]
        return f"L{(max(numeric) + 1) if numeric else 1:04d}"

    def match_lead(self, lead: Dict[str, str]) -> MatchResult:
        all_leads = self.leads()
        whatsapp = norm_phone(lead.get("whatsapp"))
        insta = normalize_text(lead.get("instagram") or "")
        lead_key = f"{normalize_text(lead.get('cidade') or '')}:{normalize_text(lead.get('nome') or '')}"

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
        nome_norm = normalize_text(lead.get("nome") or "")
        for row in all_leads:
            if cidade_norm and row.get("cidade_normalizada") == cidade_norm and nome_norm in row.get("nome_normalizado", ""):
                return MatchResult(matched=row, score=0.9)

        scored: List[Tuple[float, Dict[str, str]]] = []
        for row in all_leads:
            if cidade_norm and row.get("cidade_normalizada") and row.get("cidade_normalizada") != cidade_norm:
                continue
            target = row.get("nome_normalizado", "")
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

    def upsert_lead(self, lead: Dict[str, str], status: Optional[str], followup_em: Optional[str], when: datetime) -> str:
        lead = {k: (v or "") for k, v in lead.items()}
        lead["whatsapp"] = norm_phone(lead.get("whatsapp"))
        lead["nome_normalizado"] = normalize_text(lead.get("nome", ""))
        lead["cidade_normalizada"] = normalize_text(lead.get("cidade", ""))
        lead["lead_key"] = f"{lead['cidade_normalizada']}:{lead['nome_normalizado']}"

        match = self.match_lead(lead)
        if match.needs_review:
            self.add_review(when, "", lead.get("cidade"), lead.get("nome"), match.candidates or [], "revisar_match")
            return ""

        if match.matched:
            lead_id = match.matched["lead_id"]
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

    def add_activity(self, when: datetime, lead_id: str, tipo: str, canal: str, mensagem_bruta: str, resumo: str, followup_em: Optional[str]):
        self.ws_ativ.append_row([
            when.isoformat(),
            lead_id,
            tipo,
            canal,
            mensagem_bruta,
            resumo,
            followup_em or "",
        ])

    def add_review(self, when: datetime, mensagem_bruta: str, cidade_detectada: Optional[str], nome_detectado: Optional[str], candidatos: List[Dict[str, str]], acao: str):
        cand = "; ".join(f"{c.get('lead_id')}:{c.get('nome')}" for c in candidatos)
        self.ws_rev.append_row([when.isoformat(), mensagem_bruta, cidade_detectada or "", nome_detectado or "", cand, acao, ""])

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
                current["lead_key"] = f"{current['cidade_normalizada']}:{current['nome_normalizado']}"
                self.ws_leads.update(f"A{idx}:N{idx}", [[current[h] for h in LEADS_HEADERS]])
                return True
        return False

    def latest_activity_row(self) -> int:
        return len(self.ws_ativ.get_all_values())

    def bind_latest_activity_to_lead(self, lead_id: str) -> bool:
        row = self.latest_activity_row()
        if row < 2:
            return False
        self.ws_ativ.update(f"B{row}", [[lead_id]])
        return True
