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


def _title_case(value: str) -> str:
    """Convert to Title Case preserving common abbreviations (SP, RJ, etc.)."""
    if not value:
        return value
    return " ".join(w.capitalize() for w in value.strip().split())


def _priority_from_status(status: str) -> str:
    """Auto-calculate lead priority based on current status."""
    if status in ("negociando", "qualificado"):
        return "alta"
    if status in ("em contato", "novo"):
        return "media"
    return "baixa"


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
                # Migrações idempotentes: ADD COLUMN IF NOT EXISTS é seguro
                cur.execute(
                    "ALTER TABLE atividades ADD COLUMN IF NOT EXISTS confianca_analise INTEGER"
                )
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS valor_venda NUMERIC DEFAULT 0"
                )
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS data_fechamento TEXT DEFAULT ''"
                )
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS motivo_perda TEXT DEFAULT ''"
                )
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
    ) -> Tuple[str, bool, List[Dict[str, Any]]]:
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
            return "", True, match.candidates or []

        if match.lead_id:
            lead_id = self._update_lead(match.lead_id, lead, status, followup_em, when)
            return lead_id, False, []

        # Double-check + create
        match2 = self._match(lead)
        if match2.lead_id and not match2.needs_review:
            lead_id = self._update_lead(match2.lead_id, lead, status, followup_em, when)
            return lead_id, False, []
        if match2.needs_review:
            return "", True, match2.candidates or []
        lead_id = self._create_lead(lead, status, followup_em, when)
        return lead_id, False, []

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
        confianca_analise: Optional[int] = None,
    ) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO atividades (
                        data_hora, msg_id, lead_id, tipo, canal, acao_executada,
                        confianca_ia, duracao_audio_s, mensagem_bruta, resumo, followup_em,
                        confianca_analise
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (msg_id) DO NOTHING""",
                    (
                        when.isoformat(), msg_id, lead_id, tipo, canal, acao_executada,
                        confianca_ia, duracao_audio_s, mensagem_bruta, resumo, followup_em or "",
                        confianca_analise,
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

    # ------------------------------------------------------------------
    # Sync Sheets → DB (edições manuais do usuário)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Dashboard API methods
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Returns aggregated stats for the dashboard."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, COUNT(*) FROM leads WHERE status != 'arquivado' GROUP BY status ORDER BY COUNT(*) DESC"
                )
                by_status = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute(
                    "SELECT segmento, COUNT(*) FROM leads WHERE status != 'arquivado' AND segmento != '' GROUP BY segmento ORDER BY COUNT(*) DESC"
                )
                by_segmento = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute(
                    "SELECT prioridade, COUNT(*) FROM leads WHERE status != 'arquivado' AND prioridade != '' GROUP BY prioridade ORDER BY COUNT(*) DESC"
                )
                by_prioridade = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute(
                    "SELECT COUNT(*) FROM leads WHERE status NOT IN ('arquivado', 'perdido', 'fechado')"
                )
                total_ativos = cur.fetchone()[0]

                cur.execute(
                    """SELECT COUNT(*) FROM leads
                       WHERE proximo_followup_em != '' AND LEFT(proximo_followup_em, 10) < CURRENT_DATE::text
                         AND status NOT IN ('fechado', 'perdido', 'arquivado')"""
                )
                followups_vencidos = cur.fetchone()[0]

                cur.execute(
                    "SELECT COUNT(*) FROM leads WHERE LEFT(proximo_followup_em, 10) = CURRENT_DATE::text"
                )
                followups_hoje = cur.fetchone()[0]

                cur.execute(
                    "SELECT COUNT(*) FROM leads WHERE LEFT(data_criacao, 10) >= (CURRENT_DATE - INTERVAL '7 days')::text"
                )
                criados_semana = cur.fetchone()[0]

                cur.execute(
                    """SELECT lead_id, nome, segmento, status, prioridade, data_criacao FROM leads
                       WHERE status != 'arquivado' ORDER BY data_criacao DESC LIMIT 5"""
                )
                cols = [d[0] for d in cur.description]
                recentes = [dict(zip(cols, r)) for r in cur.fetchall()]

                cur.execute(
                    """SELECT lead_id, nome, segmento, status, prioridade, proximo_followup_em, pendencia
                       FROM leads WHERE proximo_followup_em != ''
                         AND LEFT(proximo_followup_em, 10) >= CURRENT_DATE::text
                         AND status NOT IN ('fechado', 'perdido', 'arquivado')
                       ORDER BY proximo_followup_em ASC LIMIT 5"""
                )
                cols = [d[0] for d in cur.description]
                proximos_followups = [dict(zip(cols, r)) for r in cur.fetchall()]

            return {
                "by_status": by_status,
                "by_segmento": by_segmento,
                "by_prioridade": by_prioridade,
                "total_ativos": total_ativos,
                "followups_vencidos": followups_vencidos,
                "followups_hoje": followups_hoje,
                "criados_semana": criados_semana,
                "recentes": recentes,
                "proximos_followups": proximos_followups,
            }
        finally:
            self._put(conn)

    def get_analysis_stats(self) -> Dict[str, Any]:
        """Agrega estatísticas das análises de conversa (ANALISAR:)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT
                        COUNT(*) as total,
                        ROUND(AVG(confianca_analise)::numeric, 1) as avg_confianca,
                        COUNT(CASE WHEN confianca_analise BETWEEN 1 AND 3 THEN 1 END) as baixa,
                        COUNT(CASE WHEN confianca_analise BETWEEN 4 AND 6 THEN 1 END) as incerta,
                        COUNT(CASE WHEN confianca_analise BETWEEN 7 AND 8 THEN 1 END) as promissora,
                        COUNT(CASE WHEN confianca_analise BETWEEN 9 AND 10 THEN 1 END) as quase_certa
                    FROM atividades
                    WHERE tipo = 'análise de conversa' AND confianca_analise IS NOT NULL"""
                )
                row = cur.fetchone()
                total = row[0] or 0
                avg_confianca = float(row[1]) if row[1] is not None else None
                distribuicao = {
                    "baixa": row[2] or 0,
                    "incerta": row[3] or 0,
                    "promissora": row[4] or 0,
                    "quase_certa": row[5] or 0,
                }

                cur.execute(
                    """SELECT a.data_hora, a.lead_id, l.nome, a.confianca_analise, a.resumo
                    FROM atividades a
                    LEFT JOIN leads l ON a.lead_id = l.lead_id
                    WHERE a.tipo = 'análise de conversa' AND a.confianca_analise IS NOT NULL
                    ORDER BY a.data_hora DESC LIMIT 5"""
                )
                cols = [d[0] for d in cur.description]
                recentes = [dict(zip(cols, r)) for r in cur.fetchall()]

            return {
                "total": total,
                "avg_confianca": avg_confianca,
                "distribuicao": distribuicao,
                "recentes": recentes,
            }
        finally:
            self._put(conn)

    def get_estatisticas(self) -> Dict[str, Any]:
        """Retorna analytics completo para a página /estatisticas."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:

                # Bloco A — KPIs de topo
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE status != 'arquivado') AS total_leads,
                        COUNT(*) FILTER (WHERE status = 'fechado') AS total_fechados,
                        COUNT(*) FILTER (WHERE status = 'perdido') AS total_perdidos,
                        COUNT(*) FILTER (WHERE status = 'sem resposta') AS total_sem_resposta,
                        COALESCE(SUM(valor_venda) FILTER (WHERE status = 'fechado'), 0) AS valor_total_vendas,
                        COUNT(*) FILTER (
                            WHERE proximo_followup_em != '' AND proximo_followup_em < NOW()::text
                            AND status NOT IN ('fechado','perdido','arquivado')
                        ) AS followups_vencidos,
                        ROUND(
                            COUNT(*) FILTER (WHERE status = 'fechado') * 100.0
                            / NULLIF(COUNT(*) FILTER (WHERE status != 'arquivado'), 0), 1
                        ) AS taxa_conversao
                    FROM leads
                """)
                krow = cur.fetchone()
                kpis = {
                    "total_leads": krow[0] or 0,
                    "total_fechados": krow[1] or 0,
                    "total_perdidos": krow[2] or 0,
                    "total_sem_resposta": krow[3] or 0,
                    "valor_total_vendas": float(krow[4] or 0),
                    "followups_vencidos": krow[5] or 0,
                    "taxa_conversao": float(krow[6]) if krow[6] is not None else 0.0,
                }

                # Bloco B — Funil por status
                cur.execute("""
                    SELECT status, COUNT(*) as total
                    FROM leads WHERE status != 'arquivado'
                    GROUP BY status
                """)
                funil_raw = {r[0]: r[1] for r in cur.fetchall()}

                # Bloco C — Ranking por cidade
                cur.execute("""
                    SELECT cidade, COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status='fechado') AS fechados,
                        ROUND(COUNT(*) FILTER (WHERE status='fechado') * 100.0 / COUNT(*), 1) AS taxa
                    FROM leads WHERE cidade != '' AND status != 'arquivado'
                    GROUP BY cidade ORDER BY total DESC LIMIT 15
                """)
                cols = [d[0] for d in cur.description]
                por_cidade = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Bloco D — Ranking por segmento
                cur.execute("""
                    SELECT segmento, COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status='fechado') AS fechados,
                        ROUND(COUNT(*) FILTER (WHERE status='fechado') * 100.0 / COUNT(*), 1) AS taxa
                    FROM leads WHERE segmento != '' AND status != 'arquivado'
                    GROUP BY segmento ORDER BY total DESC LIMIT 15
                """)
                cols = [d[0] for d in cur.description]
                por_segmento = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Bloco E — Ranking por fonte
                cur.execute("""
                    SELECT fonte, COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status='fechado') AS fechados,
                        ROUND(COUNT(*) FILTER (WHERE status='fechado') * 100.0 / COUNT(*), 1) AS taxa
                    FROM leads WHERE fonte != '' AND status != 'arquivado'
                    GROUP BY fonte ORDER BY total DESC LIMIT 10
                """)
                cols = [d[0] for d in cur.description]
                por_fonte = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Bloco F — Ranking por responsável
                cur.execute("""
                    SELECT responsavel, COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status='fechado') AS fechados,
                        ROUND(COUNT(*) FILTER (WHERE status='fechado') * 100.0 / COUNT(*), 1) AS taxa
                    FROM leads WHERE responsavel != '' AND status != 'arquivado'
                    GROUP BY responsavel ORDER BY total DESC LIMIT 10
                """)
                cols = [d[0] for d in cur.description]
                por_responsavel = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Bloco G — Qualidade dos dados
                cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE whatsapp != '') AS com_telefone,
                        COUNT(*) FILTER (WHERE email != '') AS com_email,
                        COUNT(*) FILTER (WHERE cidade != '') AS com_cidade,
                        COUNT(*) FILTER (WHERE segmento != '') AS com_segmento,
                        COUNT(*) FILTER (WHERE fonte != '') AS com_fonte,
                        COUNT(*) FILTER (WHERE responsavel != '') AS com_responsavel
                    FROM leads WHERE status != 'arquivado'
                """)
                qrow = cur.fetchone()
                qtotal = qrow[0] or 1
                qualidade = {
                    "total": qrow[0] or 0,
                    "pct_telefone": round(qrow[1] * 100 / qtotal),
                    "pct_email": round(qrow[2] * 100 / qtotal),
                    "pct_cidade": round(qrow[3] * 100 / qtotal),
                    "pct_segmento": round(qrow[4] * 100 / qtotal),
                    "pct_fonte": round(qrow[5] * 100 / qtotal),
                    "pct_responsavel": round(qrow[6] * 100 / qtotal),
                }

                # Bloco H — Leads problemáticos (sem atividade há 14+ dias)
                cur.execute("""
                    SELECT l.lead_id, l.nome, l.status, MAX(a.data_hora) AS ultima_atividade
                    FROM leads l LEFT JOIN atividades a ON a.lead_id = l.lead_id
                    WHERE l.status NOT IN ('fechado','perdido','arquivado','contato inválido')
                    GROUP BY l.lead_id, l.nome, l.status
                    HAVING MAX(a.data_hora) < (NOW() - INTERVAL '14 days')::text
                        OR MAX(a.data_hora) IS NULL
                    ORDER BY ultima_atividade ASC NULLS FIRST
                    LIMIT 10
                """)
                cols = [d[0] for d in cur.description]
                problematicos = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Bloco I — Timeline de atividades (últimos 30 dias)
                cur.execute("""
                    SELECT LEFT(data_hora, 10) AS dia, COUNT(*) AS total
                    FROM atividades
                    WHERE data_hora >= (NOW() - INTERVAL '30 days')::text AND lead_id != ''
                    GROUP BY dia ORDER BY dia ASC
                """)
                timeline = [{"dia": r[0], "total": r[1]} for r in cur.fetchall()]

                # Bloco J — Análises por segmento
                cur.execute("""
                    SELECT l.segmento,
                        ROUND(AVG(a.confianca_analise)::numeric, 1) AS avg_confianca,
                        COUNT(*) AS total
                    FROM atividades a
                    JOIN leads l ON a.lead_id = l.lead_id
                    WHERE a.tipo = 'análise de conversa'
                        AND a.confianca_analise IS NOT NULL
                        AND l.segmento != ''
                    GROUP BY l.segmento ORDER BY avg_confianca DESC
                """)
                cols = [d[0] for d in cur.description]
                analises_por_segmento = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Distribuição de scores 1-10
                cur.execute("""
                    SELECT confianca_analise, COUNT(*) AS total
                    FROM atividades
                    WHERE tipo = 'análise de conversa' AND confianca_analise IS NOT NULL
                    GROUP BY confianca_analise ORDER BY confianca_analise
                """)
                dist_scores = {str(r[0]): r[1] for r in cur.fetchall()}

                # Bloco K — Últimos fechamentos
                cur.execute("""
                    SELECT lead_id, nome, cidade, segmento,
                        COALESCE(valor_venda, 0) AS valor_venda,
                        data_fechamento, resumo
                    FROM leads WHERE status = 'fechado'
                    ORDER BY
                        CASE WHEN data_fechamento != '' THEN data_fechamento ELSE ultima_interacao_em END
                        DESC NULLS LAST
                    LIMIT 10
                """)
                cols = [d[0] for d in cur.description]
                fechamentos = [dict(zip(cols, r)) for r in cur.fetchall()]
                for f in fechamentos:
                    f["valor_venda"] = float(f["valor_venda"] or 0)

                # Bloco L — Motivos de perda
                cur.execute("""
                    SELECT motivo_perda, COUNT(*) AS total
                    FROM leads
                    WHERE status = 'perdido' AND motivo_perda IS NOT NULL AND motivo_perda != ''
                    GROUP BY motivo_perda ORDER BY total DESC
                """)
                motivos_perda = [{"motivo": r[0], "total": r[1]} for r in cur.fetchall()]

                # Bloco M — Status breakdown por segmento
                cur.execute("""
                    SELECT segmento, status, COUNT(*) AS total
                    FROM leads
                    WHERE segmento != '' AND status != 'arquivado'
                    GROUP BY segmento, status
                    ORDER BY segmento, total DESC
                """)
                seg_status_raw: Dict[str, Any] = {}
                for row in cur.fetchall():
                    seg, st, cnt = row
                    if seg not in seg_status_raw:
                        seg_status_raw[seg] = {"segmento": seg, "status": {}, "total": 0}
                    seg_status_raw[seg]["status"][st] = cnt
                    seg_status_raw[seg]["total"] += cnt
                # Enrich with conversion rate
                segmento_detalhado = []
                for seg_data in sorted(seg_status_raw.values(), key=lambda x: x["total"], reverse=True):
                    fechados = seg_data["status"].get("fechado", 0)
                    total = seg_data["total"]
                    seg_data["taxa_conversao"] = round(fechados * 100 / total, 1) if total > 0 else 0.0
                    segmento_detalhado.append(seg_data)

            return {
                "kpis": kpis,
                "funil": funil_raw,
                "por_cidade": por_cidade,
                "por_segmento": por_segmento,
                "por_fonte": por_fonte,
                "por_responsavel": por_responsavel,
                "qualidade": qualidade,
                "problematicos": problematicos,
                "timeline": timeline,
                "analises_por_segmento": analises_por_segmento,
                "dist_scores": dist_scores,
                "fechamentos": fechamentos,
                "motivos_perda": motivos_perda,
                "segmento_detalhado": segmento_detalhado,
            }
        finally:
            self._put(conn)

    def _auto_transition_em_contato(self) -> None:
        """Automatically transitions 'em contato' leads to 'sem resposta' after 5 days without activity."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE leads SET status = 'sem resposta', prioridade = 'baixa'
                    WHERE status = 'em contato'
                      AND (
                        ultima_interacao_em IS NULL
                        OR ultima_interacao_em = ''
                        OR LEFT(ultima_interacao_em, 10) < (CURRENT_DATE - INTERVAL '5 days')::text
                      )
                """)
                count = cur.rowcount
            conn.commit()
            if count > 0:
                logger.info("auto_transition_em_contato | %d leads → sem resposta", count)
        except Exception:
            conn.rollback()
            logger.warning("auto_transition_em_contato falhou", exc_info=True)
        finally:
            self._put(conn)

    def list_leads(
        self,
        status: Optional[str] = None,
        segmento: Optional[str] = None,
        prioridade: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """Returns paginated leads with optional filters."""
        # Auto-transition stale 'em contato' leads before returning results
        self._auto_transition_em_contato()
        conditions = ["status != 'arquivado'"]
        params: List[Any] = []

        if status:
            conditions.append("status = %s")
            params.append(status)
        if segmento:
            conditions.append("segmento = %s")
            params.append(segmento)
        if prioridade:
            conditions.append("prioridade = %s")
            params.append(prioridade)
        if search:
            conditions.append("(nome ILIKE %s OR cidade ILIKE %s OR responsavel ILIKE %s OR whatsapp ILIKE %s)")
            s = f"%{search}%"
            params.extend([s, s, s, s])

        where = " AND ".join(conditions)
        offset = (page - 1) * page_size

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM leads WHERE {where}", params)
                total = cur.fetchone()[0]

                cur.execute(
                    f"""SELECT * FROM leads WHERE {where}
                        ORDER BY
                            CASE WHEN ultima_interacao_em = '' OR ultima_interacao_em IS NULL THEN '0'
                                 ELSE ultima_interacao_em END DESC
                        LIMIT %s OFFSET %s""",
                    params + [page_size, offset],
                )
                leads = self._fetchall_dict(cur)
            return {"leads": leads, "total": total, "page": page, "page_size": page_size}
        finally:
            self._put(conn)

    def create_lead_from_dashboard(self, data: Dict[str, Any]) -> str:
        """Creates a new lead from dashboard input."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        lead: Dict[str, Any] = {k: (str(v).strip() if v is not None else "") for k, v in data.items()}
        lead["whatsapp"] = _norm_phone(lead.get("whatsapp", ""))
        lead["email"] = lead.get("email", "").strip().lower()
        lead["nome"] = _title_case(lead.get("nome", ""))
        lead["cidade"] = _title_case(lead.get("cidade", ""))
        lead["nome_normalizado"] = _normalize_text(lead.get("nome", ""))
        lead["cidade_normalizada"] = _normalize_text(lead.get("cidade", ""))
        lead["lead_key"] = f"{lead['cidade_normalizada']}:{_canonicalize_name(lead.get('nome', ''))}"
        status = data.get("status", "novo")
        lead["prioridade"] = _priority_from_status(status)
        return self._create_lead(lead, status, data.get("proximo_followup_em") or None, now)

    def update_lead_from_dashboard(self, lead_id: str, data: Dict[str, Any]) -> bool:
        """Updates a lead from dashboard input (allows more fields than Sheets sync)."""
        allowed = {
            "nome", "cidade", "segmento", "whatsapp", "email",
            "instagram", "site", "responsavel", "fonte",
            "status", "observacoes", "proximo_followup_em", "pendencia",
            "valor_venda", "data_fechamento", "motivo_perda", "data_criacao",
        }
        safe_fields: Dict[str, Any] = {
            k: str(v).strip() for k, v in data.items()
            if k in allowed and v is not None
        }
        if not safe_fields:
            return False

        if "whatsapp" in safe_fields:
            safe_fields["whatsapp"] = _norm_phone(safe_fields["whatsapp"])
        if "email" in safe_fields:
            safe_fields["email"] = safe_fields["email"].strip().lower()
        if "nome" in safe_fields:
            safe_fields["nome"] = _title_case(safe_fields["nome"])
            safe_fields["nome_normalizado"] = _normalize_text(safe_fields["nome"])
        if "cidade" in safe_fields:
            safe_fields["cidade"] = _title_case(safe_fields["cidade"])
            safe_fields["cidade_normalizada"] = _normalize_text(safe_fields["cidade"])
        if "nome_normalizado" in safe_fields or "cidade_normalizada" in safe_fields:
            safe_fields["lead_key"] = (
                f"{safe_fields.get('cidade_normalizada', '')}:"
                f"{_canonicalize_name(safe_fields.get('nome', ''))}"
            )
        # Auto-calculate priority from status
        if "status" in safe_fields:
            safe_fields["prioridade"] = _priority_from_status(safe_fields["status"])

        set_clause = ", ".join(f"{k} = %s" for k in safe_fields)
        values = list(safe_fields.values()) + [lead_id]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE leads SET {set_clause} WHERE lead_id = %s", values)
            conn.commit()
        finally:
            self._put(conn)
        logger.info("update_lead_from_dashboard | lead_id=%s", lead_id)
        return True

    def get_daily_summary(self, timezone_name: str = "UTC") -> Optional[Dict[str, Any]]:
        """Returns data for the daily summary message.

        Uses the given timezone to calculate 'today' and 'tomorrow'.
        Returns None if there was no activity today (nothing to report).
        """
        from datetime import date, timedelta
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            tz = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, Exception):
            tz = ZoneInfo("UTC")

        from datetime import datetime as _dt
        today = _dt.now(tz).date()
        tomorrow = today + timedelta(days=1)
        today_str = today.isoformat()
        tomorrow_str = tomorrow.isoformat()

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Interactions today (real activities, not bot noise)
                cur.execute(
                    "SELECT COUNT(*) FROM atividades WHERE LEFT(data_hora, 10) = %s AND lead_id != ''",
                    (today_str,),
                )
                interacoes = cur.fetchone()[0]

                # If nothing happened today, don't send summary
                if interacoes == 0:
                    return None

                # New leads today
                cur.execute(
                    "SELECT COUNT(*) FROM leads WHERE LEFT(data_criacao, 10) = %s",
                    (today_str,),
                )
                leads_novos = cur.fetchone()[0]

                # Follow-ups scheduled for today
                cur.execute(
                    """SELECT COUNT(*) FROM leads
                       WHERE LEFT(proximo_followup_em, 10) = %s
                         AND status NOT IN ('fechado', 'perdido', 'arquivado')""",
                    (today_str,),
                )
                followups_hoje = cur.fetchone()[0]

                # Last activities today (up to 5), with lead name
                cur.execute(
                    """SELECT a.resumo, a.acao_executada, l.nome
                       FROM atividades a
                       LEFT JOIN leads l ON a.lead_id = l.lead_id
                       WHERE LEFT(a.data_hora, 10) = %s AND a.lead_id != ''
                       ORDER BY a.data_hora DESC LIMIT 5""",
                    (today_str,),
                )
                ultimas = [
                    {"nome": r[2] or "?", "acao": r[1] or r[0] or ""}
                    for r in cur.fetchall()
                ]
                # Total activities today (for "+N more" display)
                total_atividades_hoje = interacoes

                # Follow-ups for tomorrow
                cur.execute(
                    """SELECT COUNT(*) FROM leads
                       WHERE LEFT(proximo_followup_em, 10) = %s
                         AND status NOT IN ('fechado', 'perdido', 'arquivado')""",
                    (tomorrow_str,),
                )
                followups_amanha = cur.fetchone()[0]

                # Streak: consecutive days with at least 1 activity
                cur.execute(
                    """SELECT DISTINCT LEFT(data_hora, 10) as dia FROM atividades
                       WHERE lead_id != '' ORDER BY dia DESC LIMIT 90"""
                )
                active_days = sorted(
                    {r[0] for r in cur.fetchall()},
                    reverse=True,
                )
                streak = 0
                expected = today
                for day_str in active_days:
                    try:
                        d = date.fromisoformat(day_str)
                    except ValueError:
                        continue
                    if d == expected:
                        streak += 1
                        from datetime import timedelta as _td
                        expected = expected - _td(days=1)
                    elif d < expected:
                        break

                return {
                    "leads_novos": leads_novos,
                    "interacoes": interacoes,
                    "followups_hoje": followups_hoje,
                    "ultimas_atividades": ultimas,
                    "total_atividades_hoje": total_atividades_hoje,
                    "followups_amanha": followups_amanha,
                    "streak_dias": streak,
                }
        finally:
            self._put(conn)

    def delete_lead(self, lead_id: str) -> bool:
        """Hard-deletes a lead and its activities from the database."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM atividades WHERE lead_id = %s", (lead_id,))
                cur.execute("DELETE FROM leads WHERE lead_id = %s", (lead_id,))
            conn.commit()
            return True
        finally:
            self._put(conn)

    def archive_lead(self, lead_id: str) -> bool:
        """Soft-deletes a lead by setting status to 'arquivado'."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE leads SET status = 'arquivado' WHERE lead_id = %s", (lead_id,))
            conn.commit()
            return True
        finally:
            self._put(conn)

    def update_lead_from_sheets(self, lead_id: str, fields: Dict[str, Any]) -> bool:
        """Atualiza campos editáveis pelo usuário vindos do Sheets.

        Só atualiza campos permitidos (não sobrescreve campos automáticos do bot).
        Recalcula campos derivados (nome_normalizado, cidade_normalizada, lead_key) se necessário.
        """
        allowed = {
            "nome", "cidade", "segmento", "whatsapp", "email",
            "instagram", "site", "responsavel", "fonte",
            "status", "prioridade", "observacoes", "proximo_followup_em",
        }
        safe_fields: Dict[str, Any] = {
            k: str(v).strip() for k, v in fields.items()
            if k in allowed and v is not None and str(v).strip()
        }
        if not safe_fields:
            return False

        if "whatsapp" in safe_fields:
            safe_fields["whatsapp"] = _norm_phone(safe_fields["whatsapp"])
        if "email" in safe_fields:
            safe_fields["email"] = safe_fields["email"].strip().lower()
        if "nome" in safe_fields:
            safe_fields["nome_normalizado"] = _normalize_text(safe_fields["nome"])
        if "cidade" in safe_fields:
            safe_fields["cidade_normalizada"] = _normalize_text(safe_fields["cidade"])
        if "nome_normalizado" in safe_fields or "cidade_normalizada" in safe_fields:
            safe_fields["lead_key"] = (
                f"{safe_fields.get('cidade_normalizada', '')}:"
                f"{_canonicalize_name(safe_fields.get('nome', ''))}"
            )

        set_clause = ", ".join(f"{k} = %s" for k in safe_fields)
        values = list(safe_fields.values()) + [lead_id]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE leads SET {set_clause} WHERE lead_id = %s", values)
            conn.commit()
        finally:
            self._put(conn)
        logger.debug("update_lead_from_sheets | lead_id=%s fields=%s", lead_id, list(safe_fields))
        return True
