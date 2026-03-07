from __future__ import annotations

import logging
import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS leads (
    lead_id              TEXT PRIMARY KEY,
    nome                 TEXT DEFAULT '',
    cidade               TEXT DEFAULT '',
    segmento             TEXT DEFAULT '',
    whatsapp             TEXT DEFAULT '',
    email                TEXT DEFAULT '',
    instagram            TEXT DEFAULT '',
    site                 TEXT DEFAULT '',
    responsavel          TEXT DEFAULT '',
    fonte                TEXT DEFAULT '',
    status               TEXT DEFAULT 'novo',
    prioridade           TEXT DEFAULT 'media',
    resumo               TEXT DEFAULT '',
    pendencia            TEXT DEFAULT '',
    observacoes          TEXT DEFAULT '',
    data_criacao         TEXT,
    ultima_interacao_em  TEXT,
    proximo_followup_em  TEXT DEFAULT '',
    nome_normalizado     TEXT DEFAULT '',
    cidade_normalizada   TEXT DEFAULT '',
    lead_key             TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS atividades (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora        TEXT,
    msg_id           TEXT UNIQUE,
    lead_id          TEXT DEFAULT '',
    tipo             TEXT DEFAULT '',
    canal            TEXT DEFAULT '',
    acao_executada   TEXT DEFAULT '',
    confianca_ia     REAL DEFAULT 0,
    duracao_audio_s  REAL,
    mensagem_bruta   TEXT DEFAULT '',
    resumo           TEXT DEFAULT '',
    followup_em      TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_leads_whatsapp        ON leads(whatsapp);
CREATE INDEX IF NOT EXISTS idx_leads_lead_key         ON leads(lead_key);
CREATE INDEX IF NOT EXISTS idx_leads_nome_normalizado ON leads(nome_normalizado);
CREATE INDEX IF NOT EXISTS idx_leads_email            ON leads(email);
CREATE INDEX IF NOT EXISTS idx_atividades_lead_id     ON atividades(lead_id);
CREATE INDEX IF NOT EXISTS idx_atividades_msg_id      ON atividades(msg_id);
"""

GENERIC_NAME_TOKENS = {
    "clinica", "clínica", "consultorio", "consultório",
    "odontologia", "odonto", "estetica", "estética",
}

# ---------------------------------------------------------------------------
# Text helpers (mesmos de sheets_service para manter consistência)
# ---------------------------------------------------------------------------

def _strip_accents(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", value) if unicodedata.category(ch) != "Mn")


def _normalize_text(value: str) -> str:
    base = _strip_accents(value or "").lower().strip()
    base = re.sub(r"[^\w\s]", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def _canonicalize_name(value: str) -> str:
    normalized = _normalize_text(value)
    tokens = normalized.split()
    while tokens and tokens[0] in GENERIC_NAME_TOKENS:
        tokens = tokens[1:]
    while tokens and tokens[-1] in GENERIC_NAME_TOKENS:
        tokens = tokens[:-1]
    return " ".join(tokens) if tokens else normalized


def _norm_phone(value: Any) -> str:
    if value is None:
        return ""
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


# ---------------------------------------------------------------------------
# Match result
# ---------------------------------------------------------------------------

@dataclass
class DBMatchResult:
    lead_id: Optional[str]
    score: float = 0.0
    needs_review: bool = False
    candidates: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# DBService
# ---------------------------------------------------------------------------

class DBService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(CREATE_TABLES_SQL)
        logger.info("db_init OK | path=%s", self.db_path)

    # ------------------------------------------------------------------
    # Idempotência
    # ------------------------------------------------------------------

    def already_processed(self, msg_id: str) -> bool:
        if not msg_id:
            return False
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM atividades WHERE msg_id = ?", (msg_id,)
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Seeding a partir do Sheets (executado uma vez na primeira subida)
    # ------------------------------------------------------------------

    def is_seeded(self) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) FROM leads").fetchone()
        return row[0] > 0

    def seed(self, leads: List[Dict[str, Any]], activities: List[Dict[str, Any]]) -> None:
        """Importa dados existentes do Sheets para o SQLite (idempotente)."""
        with self._lock, self._conn() as conn:
            for lead in leads:
                lid = str(lead.get("lead_id", "")).strip()
                if not lid:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO leads (
                        lead_id, nome, cidade, segmento, whatsapp, email,
                        instagram, site, responsavel, fonte, status, prioridade,
                        resumo, pendencia, observacoes, data_criacao,
                        ultima_interacao_em, proximo_followup_em,
                        nome_normalizado, cidade_normalizada, lead_key
                    ) VALUES (
                        :lead_id, :nome, :cidade, :segmento, :whatsapp, :email,
                        :instagram, :site, :responsavel, :fonte, :status, :prioridade,
                        :resumo, :pendencia, :observacoes, :data_criacao,
                        :ultima_interacao_em, :proximo_followup_em,
                        :nome_normalizado, :cidade_normalizada, :lead_key
                    )""",
                    {
                        "lead_id": lid,
                        "nome": lead.get("nome", ""),
                        "cidade": lead.get("cidade", ""),
                        "segmento": lead.get("segmento", ""),
                        "whatsapp": _norm_phone(lead.get("whatsapp")),
                        "email": (lead.get("email") or "").strip().lower(),
                        "instagram": lead.get("instagram", ""),
                        "site": lead.get("site", ""),
                        "responsavel": lead.get("responsavel", ""),
                        "fonte": lead.get("fonte", ""),
                        "status": lead.get("status", "novo"),
                        "prioridade": lead.get("prioridade", "media"),
                        "resumo": lead.get("resumo", ""),
                        "pendencia": lead.get("pendencia", ""),
                        "observacoes": lead.get("observacoes", ""),
                        "data_criacao": lead.get("data_criacao", ""),
                        "ultima_interacao_em": lead.get("ultima_interacao_em", ""),
                        "proximo_followup_em": lead.get("proximo_followup_em", ""),
                        "nome_normalizado": lead.get("nome_normalizado")
                            or _normalize_text(lead.get("nome", "")),
                        "cidade_normalizada": lead.get("cidade_normalizada")
                            or _normalize_text(lead.get("cidade", "")),
                        "lead_key": lead.get("lead_key")
                            or f"{_normalize_text(lead.get('cidade',''))}:{_canonicalize_name(lead.get('nome',''))}",
                    },
                )

            for act in activities:
                mid = str(act.get("msg_id", "")).strip()
                if not mid:
                    continue
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO atividades (
                            data_hora, msg_id, lead_id, tipo, canal, acao_executada,
                            confianca_ia, duracao_audio_s, mensagem_bruta, resumo, followup_em
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            act.get("data_hora", ""),
                            mid,
                            act.get("lead_id", ""),
                            act.get("tipo", ""),
                            act.get("canal", ""),
                            act.get("acao_executada", ""),
                            _safe_float(act.get("confianca_ia")),
                            _safe_float(act.get("duracao_audio_s")),
                            act.get("mensagem_bruta", ""),
                            act.get("resumo", ""),
                            act.get("followup_em", ""),
                        ),
                    )
                except Exception:
                    pass  # ignora erros individuais no seeding

            conn.commit()
        logger.info("db_seeded | leads=%d activities=%d", len(leads), len(activities))

    # ------------------------------------------------------------------
    # Lead matching
    # ------------------------------------------------------------------

    def _match(self, lead: Dict[str, Any]) -> DBMatchResult:
        whatsapp = _norm_phone(lead.get("whatsapp"))
        email = (lead.get("email") or "").strip().lower()
        instagram = _normalize_text(lead.get("instagram") or "")
        lead_key = lead.get("lead_key", "")
        cidade_norm = lead.get("cidade_normalizada", "")
        canonical_name = _canonicalize_name(lead.get("nome") or "")

        with self._conn() as conn:
            # 1. Telefone
            if whatsapp:
                row = conn.execute(
                    "SELECT * FROM leads WHERE whatsapp = ?", (whatsapp,)
                ).fetchone()
                if row:
                    return DBMatchResult(lead_id=row["lead_id"], score=1.0)

            # 2. Email
            if email:
                row = conn.execute(
                    "SELECT * FROM leads WHERE email = ? AND email != ''", (email,)
                ).fetchone()
                if row:
                    return DBMatchResult(lead_id=row["lead_id"], score=0.995)

            # 3. Instagram
            if instagram:
                rows = conn.execute(
                    "SELECT * FROM leads WHERE instagram != ''",
                ).fetchall()
                for row in rows:
                    if _normalize_text(row["instagram"]) == instagram:
                        return DBMatchResult(lead_id=row["lead_id"], score=0.99)

            # 4. lead_key
            if lead_key:
                row = conn.execute(
                    "SELECT * FROM leads WHERE lead_key = ? AND lead_key != ''", (lead_key,)
                ).fetchone()
                if row:
                    return DBMatchResult(lead_id=row["lead_id"], score=0.98)

            # 5. City + name substring
            if cidade_norm and canonical_name:
                rows = conn.execute(
                    "SELECT * FROM leads WHERE cidade_normalizada = ?", (cidade_norm,)
                ).fetchall()
                for row in rows:
                    row_name = _canonicalize_name(row["nome"])
                    if canonical_name in row_name:
                        return DBMatchResult(lead_id=row["lead_id"], score=0.9)
            elif canonical_name:
                rows = conn.execute(
                    "SELECT * FROM leads WHERE nome_normalizado != ''",
                ).fetchall()
                for row in rows:
                    row_name = _canonicalize_name(row["nome"])
                    if canonical_name in row_name or row_name in canonical_name:
                        return DBMatchResult(lead_id=row["lead_id"], score=0.89)
                rows = []  # já processados acima

            # 6. Fuzzy matching
            if cidade_norm:
                candidates = conn.execute(
                    "SELECT * FROM leads WHERE cidade_normalizada = ? OR cidade_normalizada = ''",
                    (cidade_norm,),
                ).fetchall()
            else:
                candidates = conn.execute("SELECT * FROM leads").fetchall()

        if not candidates or not canonical_name:
            return DBMatchResult(lead_id=None, score=0)

        scored: List[Tuple[float, Any]] = []
        for row in candidates:
            if cidade_norm and row["cidade_normalizada"] and row["cidade_normalizada"] != cidade_norm:
                continue
            target = _canonicalize_name(row["nome"])
            if not target:
                continue
            sim = max(
                fuzz.ratio(canonical_name, target) / 100.0,
                SequenceMatcher(None, canonical_name, target).ratio(),
            )
            scored.append((sim, row))

        if not scored:
            return DBMatchResult(lead_id=None, score=0)

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_row = scored[0]
        if best_score >= 0.88:
            return DBMatchResult(lead_id=best_row["lead_id"], score=best_score)
        if 0.78 <= best_score < 0.88:
            top3 = [dict(r) for _, r in scored[:3]]
            return DBMatchResult(lead_id=None, score=best_score, needs_review=True, candidates=top3)
        return DBMatchResult(lead_id=None, score=best_score)

    def _next_lead_id(self, conn: sqlite3.Connection) -> str:
        row = conn.execute(
            "SELECT lead_id FROM leads WHERE lead_id LIKE 'L%' ORDER BY lead_id DESC LIMIT 1"
        ).fetchone()
        if row:
            try:
                num = int(row["lead_id"][1:]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        return f"L{num:04d}"

    # ------------------------------------------------------------------
    # Lead upsert
    # ------------------------------------------------------------------

    def upsert_lead(
        self,
        lead: Dict[str, Any],
        status: Optional[str],
        followup_em: Optional[str],
        when: datetime,
    ) -> str:
        lead = {k: (v or "") for k, v in lead.items()}
        lead["whatsapp"] = _norm_phone(lead.get("whatsapp"))
        lead["email"] = lead.get("email", "").strip().lower()
        lead["nome_normalizado"] = _normalize_text(lead.get("nome", ""))
        lead["cidade_normalizada"] = _normalize_text(lead.get("cidade", ""))
        canonical_name = _canonicalize_name(lead.get("nome", ""))
        lead["lead_key"] = f"{lead['cidade_normalizada']}:{canonical_name}"

        match = self._match(lead)
        phone_in_new = lead["whatsapp"]

        # Se tem telefone novo e match por nome com score baixo, cria novo lead
        if phone_in_new and match.score < 0.95:
            if match.needs_review:
                match = DBMatchResult(lead_id=None, score=0)
            elif match.lead_id:
                with self._conn() as conn:
                    row = conn.execute(
                        "SELECT whatsapp FROM leads WHERE lead_id = ?", (match.lead_id,)
                    ).fetchone()
                if row and row["whatsapp"] and row["whatsapp"] != phone_in_new:
                    match = DBMatchResult(lead_id=None, score=0)

        if match.needs_review:
            return ""

        with self._lock:
            # Double-check dentro do lock
            if not match.lead_id:
                match2 = self._match(lead)
                if match2.lead_id and not match2.needs_review:
                    match = match2

            if match.lead_id:
                return self._update_lead(match.lead_id, lead, status, followup_em, when)
            else:
                return self._create_lead(lead, status, followup_em, when)

    def _update_lead(
        self,
        lead_id: str,
        lead: Dict[str, Any],
        status: Optional[str],
        followup_em: Optional[str],
        when: datetime,
    ) -> str:
        fields_to_update = [
            "nome", "cidade", "segmento", "whatsapp", "email",
            "instagram", "site", "responsavel", "fonte",
            "nome_normalizado", "cidade_normalizada", "lead_key",
        ]
        updates: Dict[str, Any] = {"ultima_interacao_em": when.isoformat(), "lead_id": lead_id}
        for k in fields_to_update:
            if lead.get(k):
                updates[k] = lead[k]
        if status:
            updates["status"] = status
        if followup_em:
            updates["proximo_followup_em"] = followup_em

        set_clause = ", ".join(f"{k} = :{k}" for k in updates if k != "lead_id")
        with self._conn() as conn:
            conn.execute(f"UPDATE leads SET {set_clause} WHERE lead_id = :lead_id", updates)
            conn.commit()
        logger.info("lead_atualizado | lead_id=%s", lead_id)
        return lead_id

    def _create_lead(
        self,
        lead: Dict[str, Any],
        status: Optional[str],
        followup_em: Optional[str],
        when: datetime,
    ) -> str:
        now_iso = when.isoformat()
        with self._conn() as conn:
            lead_id = self._next_lead_id(conn)
            conn.execute(
                """INSERT INTO leads (
                    lead_id, nome, cidade, segmento, whatsapp, email, instagram, site,
                    responsavel, fonte, status, prioridade, observacoes, data_criacao,
                    ultima_interacao_em, proximo_followup_em,
                    nome_normalizado, cidade_normalizada, lead_key
                ) VALUES (
                    :lead_id, :nome, :cidade, :segmento, :whatsapp, :email, :instagram, :site,
                    :responsavel, :fonte, :status, 'media', '', :data_criacao,
                    :ultima_interacao_em, :proximo_followup_em,
                    :nome_normalizado, :cidade_normalizada, :lead_key
                )""",
                {
                    "lead_id": lead_id,
                    "nome": lead.get("nome", ""),
                    "cidade": lead.get("cidade", ""),
                    "segmento": lead.get("segmento", ""),
                    "whatsapp": lead.get("whatsapp", ""),
                    "email": lead.get("email", ""),
                    "instagram": lead.get("instagram", ""),
                    "site": lead.get("site", ""),
                    "responsavel": lead.get("responsavel", ""),
                    "fonte": lead.get("fonte", ""),
                    "status": status or "novo",
                    "data_criacao": now_iso,
                    "ultima_interacao_em": now_iso,
                    "proximo_followup_em": followup_em or "",
                    "nome_normalizado": lead.get("nome_normalizado", ""),
                    "cidade_normalizada": lead.get("cidade_normalizada", ""),
                    "lead_key": lead.get("lead_key", ""),
                },
            )
            conn.commit()
        logger.info("novo_lead_criado | lead_id=%s nome=%s", lead_id, lead.get("nome"))
        return lead_id

    # ------------------------------------------------------------------
    # Activity
    # ------------------------------------------------------------------

    def add_activity(
        self,
        when: datetime,
        msg_id: str,
        lead_id: str,
        tipo: str,
        canal: str,
        acao_executada: str,
        confianca_ia: float,
        duracao_audio_s: Optional[float],
        mensagem_bruta: str,
        resumo: str,
        followup_em: Optional[str],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO atividades (
                    data_hora, msg_id, lead_id, tipo, canal, acao_executada,
                    confianca_ia, duracao_audio_s, mensagem_bruta, resumo, followup_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    when.isoformat(), msg_id, lead_id, tipo, canal, acao_executada,
                    confianca_ia, duracao_audio_s, mensagem_bruta, resumo, followup_em or "",
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Lead summary / pendencia
    # ------------------------------------------------------------------

    def get_lead_recent_activity_summaries(self, lead_id: str, n: int = 5) -> List[str]:
        """Retorna os últimos N resumos de atividade do lead para gerar o resumo cumulativo."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT resumo FROM atividades
                   WHERE lead_id = ? AND resumo != ''
                   ORDER BY data_hora DESC LIMIT ?""",
                (lead_id, n),
            ).fetchall()
        return [row["resumo"] for row in rows]

    def update_lead_resumo_pendencia(
        self,
        lead_id: str,
        resumo: Optional[str],
        pendencia: Optional[str],
    ) -> None:
        updates: Dict[str, Any] = {"lead_id": lead_id}
        if resumo is not None:
            updates["resumo"] = resumo
        if pendencia is not None:
            updates["pendencia"] = pendencia
        if len(updates) <= 1:
            return
        set_clause = ", ".join(f"{k} = :{k}" for k in updates if k != "lead_id")
        with self._conn() as conn:
            conn.execute(f"UPDATE leads SET {set_clause} WHERE lead_id = :lead_id", updates)
            conn.commit()

    def get_lead(self, lead_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM leads WHERE lead_id = ?", (lead_id,)
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Context fallback (usado quando lead_id não é resolvido na mensagem)
    # ------------------------------------------------------------------

    def latest_linked_lead_id(self) -> str:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT lead_id FROM atividades
                   WHERE lead_id != ''
                   ORDER BY data_hora DESC LIMIT 1"""
            ).fetchone()
        return row["lead_id"] if row else ""

    # ------------------------------------------------------------------
    # Review candidates (para adicionar ao Sheets REVISAR)
    # ------------------------------------------------------------------

    def match_for_review(self, lead: Dict[str, Any]) -> Tuple[DBMatchResult, List[Dict[str, Any]]]:
        """Retorna match + candidatos para registro em REVISAR."""
        lead = {k: (v or "") for k, v in lead.items()}
        lead["nome_normalizado"] = _normalize_text(lead.get("nome", ""))
        lead["cidade_normalizada"] = _normalize_text(lead.get("cidade", ""))
        lead["lead_key"] = f"{lead['cidade_normalizada']}:{_canonicalize_name(lead.get('nome', ''))}"
        match = self._match(lead)
        candidates = match.candidates or []
        return match, candidates


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None
