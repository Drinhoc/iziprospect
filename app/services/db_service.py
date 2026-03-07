from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import psycopg2.pool
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
    id               SERIAL PRIMARY KEY,
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
# Text helpers
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


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


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
# DBService — PostgreSQL via psycopg2
# ---------------------------------------------------------------------------

class DBService:
    def __init__(self, database_url: str):
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url,
        )
        self._init_db()

    def _conn(self):
        return self._pool.getconn()

    def _put(self, conn) -> None:
        self._pool.putconn(conn)

    def _init_db(self) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLES_SQL)
            conn.commit()
        finally:
            self._put(conn)
        logger.info("db_init OK (PostgreSQL)")

    def _fetchall_dict(self, cur) -> List[Dict[str, Any]]:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _fetchone_dict(self, cur) -> Optional[Dict[str, Any]]:
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

    # ------------------------------------------------------------------
    # Idempotência
    # ------------------------------------------------------------------

    def already_processed(self, msg_id: str) -> bool:
        if not msg_id:
            return False
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM atividades WHERE msg_id = %s", (msg_id,))
                return cur.fetchone() is not None
        finally:
            self._put(conn)

    # ------------------------------------------------------------------
    # Seeding a partir do Sheets
    # ------------------------------------------------------------------

    def is_seeded(self) -> bool:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM leads")
                return cur.fetchone()[0] > 0
        finally:
            self._put(conn)

    def seed(self, leads: List[Dict[str, Any]], activities: List[Dict[str, Any]]) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                for lead in leads:
                    lid = str(lead.get("lead_id", "")).strip()
                    if not lid:
                        continue
                    cur.execute(
                        """INSERT INTO leads (
                            lead_id, nome, cidade, segmento, whatsapp, email,
                            instagram, site, responsavel, fonte, status, prioridade,
                            resumo, pendencia, observacoes, data_criacao,
                            ultima_interacao_em, proximo_followup_em,
                            nome_normalizado, cidade_normalizada, lead_key
                        ) VALUES (
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                        ) ON CONFLICT (lead_id) DO NOTHING""",
                        (
                            lid,
                            lead.get("nome", ""),
                            lead.get("cidade", ""),
                            lead.get("segmento", ""),
                            _norm_phone(lead.get("whatsapp")),
                            (lead.get("email") or "").strip().lower(),
                            lead.get("instagram", ""),
                            lead.get("site", ""),
                            lead.get("responsavel", ""),
                            lead.get("fonte", ""),
                            lead.get("status", "novo"),
                            lead.get("prioridade", "media"),
                            lead.get("resumo", ""),
                            lead.get("pendencia", ""),
                            lead.get("observacoes", ""),
                            lead.get("data_criacao", ""),
                            lead.get("ultima_interacao_em", ""),
                            lead.get("proximo_followup_em", ""),
                            lead.get("nome_normalizado") or _normalize_text(lead.get("nome", "")),
                            lead.get("cidade_normalizada") or _normalize_text(lead.get("cidade", "")),
                            lead.get("lead_key") or f"{_normalize_text(lead.get('cidade',''))}:{_canonicalize_name(lead.get('nome',''))}",
                        ),
                    )

                for act in activities:
                    mid = str(act.get("msg_id", "")).strip()
                    if not mid:
                        continue
                    try:
                        cur.execute(
                            """INSERT INTO atividades (
                                data_hora, msg_id, lead_id, tipo, canal, acao_executada,
                                confianca_ia, duracao_audio_s, mensagem_bruta, resumo, followup_em
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (msg_id) DO NOTHING""",
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
                        conn.rollback()

            conn.commit()
        finally:
            self._put(conn)
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

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # 1. Telefone
                if whatsapp:
                    cur.execute("SELECT * FROM leads WHERE whatsapp = %s LIMIT 1", (whatsapp,))
                    row = self._fetchone_dict(cur)
                    if row:
                        return DBMatchResult(lead_id=row["lead_id"], score=1.0)

                # 2. Email
                if email:
                    cur.execute("SELECT * FROM leads WHERE email = %s AND email != '' LIMIT 1", (email,))
                    row = self._fetchone_dict(cur)
                    if row:
                        return DBMatchResult(lead_id=row["lead_id"], score=0.995)

                # 3. Instagram (comparação normalizada)
                if instagram:
                    cur.execute("SELECT * FROM leads WHERE instagram != ''")
                    rows = self._fetchall_dict(cur)
                    for row in rows:
                        if _normalize_text(row["instagram"]) == instagram:
                            return DBMatchResult(lead_id=row["lead_id"], score=0.99)

                # 4. lead_key exato
                if lead_key:
                    cur.execute("SELECT * FROM leads WHERE lead_key = %s AND lead_key != '' LIMIT 1", (lead_key,))
                    row = self._fetchone_dict(cur)
                    if row:
                        return DBMatchResult(lead_id=row["lead_id"], score=0.98)

                # 5. City + name substring
                if cidade_norm and canonical_name:
                    cur.execute("SELECT * FROM leads WHERE cidade_normalizada = %s", (cidade_norm,))
                    rows = self._fetchall_dict(cur)
                    for row in rows:
                        if canonical_name in _canonicalize_name(row["nome"]):
                            return DBMatchResult(lead_id=row["lead_id"], score=0.9)
                elif canonical_name:
                    cur.execute("SELECT * FROM leads WHERE nome_normalizado != ''")
                    rows = self._fetchall_dict(cur)
                    for row in rows:
                        row_name = _canonicalize_name(row["nome"])
                        if canonical_name in row_name or row_name in canonical_name:
                            return DBMatchResult(lead_id=row["lead_id"], score=0.89)
                    rows = []

                # 6. Fuzzy — pré-filtra por cidade
                if cidade_norm:
                    cur.execute(
                        "SELECT * FROM leads WHERE cidade_normalizada = %s OR cidade_normalizada = ''",
                        (cidade_norm,),
                    )
                else:
                    cur.execute("SELECT * FROM leads")
                candidates = self._fetchall_dict(cur)
        finally:
            self._put(conn)

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
            top3 = [r for _, r in scored[:3]]
            return DBMatchResult(lead_id=None, score=best_score, needs_review=True, candidates=top3)
        return DBMatchResult(lead_id=None, score=best_score)

    def _next_lead_id(self, cur) -> str:
        cur.execute(
            "SELECT lead_id FROM leads WHERE lead_id LIKE 'L%' ORDER BY lead_id DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row:
            try:
                num = int(row[0][1:]) + 1
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

        if phone_in_new and match.score < 0.95:
            if match.needs_review:
                match = DBMatchResult(lead_id=None, score=0)
            elif match.lead_id:
                existing_phone = self._get_phone(match.lead_id)
                if existing_phone and existing_phone != phone_in_new:
                    match = DBMatchResult(lead_id=None, score=0)

        if match.needs_review:
            return ""

        if match.lead_id:
            return self._update_lead(match.lead_id, lead, status, followup_em, when)

        # Double-check + create
        match2 = self._match(lead)
        if match2.lead_id and not match2.needs_review:
            return self._update_lead(match2.lead_id, lead, status, followup_em, when)
        return self._create_lead(lead, status, followup_em, when)

    def _get_phone(self, lead_id: str) -> str:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT whatsapp FROM leads WHERE lead_id = %s", (lead_id,))
                row = cur.fetchone()
                return row[0] if row else ""
        finally:
            self._put(conn)

    def _update_lead(
        self,
        lead_id: str,
        lead: Dict[str, Any],
        status: Optional[str],
        followup_em: Optional[str],
        when: datetime,
    ) -> str:
        fields = {
            k: lead[k] for k in [
                "nome", "cidade", "segmento", "whatsapp", "email",
                "instagram", "site", "responsavel", "fonte",
                "nome_normalizado", "cidade_normalizada", "lead_key",
            ] if lead.get(k)
        }
        fields["ultima_interacao_em"] = when.isoformat()
        if status:
            fields["status"] = status
        if followup_em:
            fields["proximo_followup_em"] = followup_em

        set_clause = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [lead_id]

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE leads SET {set_clause} WHERE lead_id = %s", values)
            conn.commit()
        finally:
            self._put(conn)
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
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                lead_id = self._next_lead_id(cur)
                cur.execute(
                    """INSERT INTO leads (
                        lead_id, nome, cidade, segmento, whatsapp, email, instagram, site,
                        responsavel, fonte, status, prioridade, observacoes, data_criacao,
                        ultima_interacao_em, proximo_followup_em,
                        nome_normalizado, cidade_normalizada, lead_key
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'media','',%s,%s,%s,%s,%s,%s)""",
                    (
                        lead_id,
                        lead.get("nome", ""), lead.get("cidade", ""),
                        lead.get("segmento", ""), lead.get("whatsapp", ""),
                        lead.get("email", ""), lead.get("instagram", ""),
                        lead.get("site", ""), lead.get("responsavel", ""),
                        lead.get("fonte", ""), status or "novo",
                        now_iso, now_iso, followup_em or "",
                        lead.get("nome_normalizado", ""), lead.get("cidade_normalizada", ""),
                        lead.get("lead_key", ""),
                    ),
                )
            conn.commit()
        finally:
            self._put(conn)
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
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO atividades (
                        data_hora, msg_id, lead_id, tipo, canal, acao_executada,
                        confianca_ia, duracao_audio_s, mensagem_bruta, resumo, followup_em
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (msg_id) DO NOTHING""",
                    (
                        when.isoformat(), msg_id, lead_id, tipo, canal, acao_executada,
                        confianca_ia, duracao_audio_s, mensagem_bruta, resumo, followup_em or "",
                    ),
                )
            conn.commit()
        finally:
            self._put(conn)

    # ------------------------------------------------------------------
    # Lead summary / pendencia
    # ------------------------------------------------------------------

    def get_lead_recent_activity_summaries(self, lead_id: str, n: int = 5) -> List[str]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT resumo FROM atividades
                       WHERE lead_id = %s AND resumo != ''
                       ORDER BY data_hora DESC LIMIT %s""",
                    (lead_id, n),
                )
                return [row[0] for row in cur.fetchall()]
        finally:
            self._put(conn)

    def update_lead_resumo_pendencia(
        self,
        lead_id: str,
        resumo: Optional[str],
        pendencia: Optional[str],
    ) -> None:
        fields: Dict[str, Any] = {}
        if resumo is not None:
            fields["resumo"] = resumo
        if pendencia is not None:
            fields["pendencia"] = pendencia
        if not fields:
            return
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [lead_id]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE leads SET {set_clause} WHERE lead_id = %s", values)
            conn.commit()
        finally:
            self._put(conn)

    def get_lead(self, lead_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM leads WHERE lead_id = %s", (lead_id,))
                return self._fetchone_dict(cur)
        finally:
            self._put(conn)

    # ------------------------------------------------------------------
    # Context fallback
    # ------------------------------------------------------------------

    def latest_linked_lead_id(self) -> str:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT lead_id FROM atividades WHERE lead_id != '' ORDER BY data_hora DESC LIMIT 1"
                )
                row = cur.fetchone()
                return row[0] if row else ""
        finally:
            self._put(conn)
