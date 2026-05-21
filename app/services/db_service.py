from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from app.services.crm_interpreter import suggest_followup_from_status

import psycopg2
import psycopg2.extras
import psycopg2.pool
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

CREATE_TENANTS_SQL = """
CREATE TABLE IF NOT EXISTS public.tenants (
    id                 TEXT PRIMARY KEY,
    nome               TEXT NOT NULL DEFAULT '',
    plano              TEXT NOT NULL DEFAULT 'basico',
    evolution_instance TEXT UNIQUE,
    evolution_api_key  TEXT DEFAULT '',
    ativo              BOOLEAN DEFAULT true,
    criado_em          TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em      TIMESTAMPTZ DEFAULT NOW()
);
"""

TENANT_SCHEMA_SQL = """
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
    temperatura          TEXT DEFAULT 'frio',
    resumo               TEXT DEFAULT '',
    acao_followup        TEXT DEFAULT '',
    observacoes          TEXT DEFAULT '',
    data_criacao         TEXT,
    ultima_interacao_em  TEXT,
    proximo_followup_em  TEXT DEFAULT '',
    data_recontato       TEXT DEFAULT '',
    nome_normalizado     TEXT DEFAULT '',
    cidade_normalizada   TEXT DEFAULT '',
    lead_key             TEXT DEFAULT '',
    valor_venda          NUMERIC DEFAULT 0,
    data_fechamento      TEXT DEFAULT '',
    motivo_perda         TEXT DEFAULT '',
    status_anterior      TEXT DEFAULT '',
    mensagem_enviada_em  TEXT DEFAULT '',
    auto_send_variante   TEXT DEFAULT '',
    origem_primeiro_contato TEXT DEFAULT ''
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
    confianca_analise INTEGER,
    duracao_audio_s  REAL,
    mensagem_bruta   TEXT DEFAULT '',
    resumo           TEXT DEFAULT '',
    followup_em      TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS lead_prospects (
    id               SERIAL PRIMARY KEY,
    nome             TEXT DEFAULT '',
    cidade           TEXT DEFAULT '',
    segmento         TEXT DEFAULT '',
    telefone         TEXT DEFAULT '',
    whatsapp         TEXT DEFAULT '',
    website          TEXT DEFAULT '',
    instagram        TEXT DEFAULT '',
    link_maps        TEXT DEFAULT '',
    fonte            TEXT DEFAULT '',
    fonte_busca      TEXT DEFAULT '',
    status_revisao   TEXT DEFAULT 'pendente',
    data_coleta      TEXT DEFAULT '',
    enriquecido      INTEGER DEFAULT 0,
    lead_id_aprovado TEXT DEFAULT '',
    busca_id         TEXT DEFAULT '',
    rating           TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS msg_ab_eventos (
    id        SERIAL PRIMARY KEY,
    lead_id   TEXT DEFAULT '',
    variante  TEXT DEFAULT '',
    segmento  TEXT DEFAULT '',
    evento    TEXT DEFAULT '',
    tipo      TEXT DEFAULT 'inicial',
    data_hora TEXT
);
CREATE TABLE IF NOT EXISTS settings_kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS conversas (
    id                SERIAL PRIMARY KEY,
    jid               TEXT NOT NULL UNIQUE,
    nome_contato      TEXT DEFAULT '',
    numero            TEXT DEFAULT '',
    status            TEXT DEFAULT 'aberto',
    prioridade        TEXT DEFAULT 'normal',
    categoria         TEXT DEFAULT 'outro',
    total_mensagens   INT DEFAULT 0,
    nao_lidas         INT DEFAULT 0,
    ultimo_msg_em     TIMESTAMPTZ,
    primeira_msg_em   TIMESTAMPTZ,
    resumo_ia         TEXT DEFAULT '',
    resposta_sugerida TEXT DEFAULT '',
    confianca_ia      INT DEFAULT 0,
    lead_id           TEXT DEFAULT '',
    atribuido_a       TEXT DEFAULT '',
    resolvido_em      TIMESTAMPTZ,
    criado_em         TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS mensagens_inbox (
    id              SERIAL PRIMARY KEY,
    msg_id          TEXT UNIQUE,
    conversa_id     INT NOT NULL,
    jid             TEXT NOT NULL,
    de_mim          BOOLEAN DEFAULT FALSE,
    tipo            TEXT DEFAULT 'text',
    texto           TEXT DEFAULT '',
    transcricao     TEXT DEFAULT '',
    duracao_audio_s REAL,
    media_url       TEXT DEFAULT '',
    status_proc     TEXT DEFAULT 'pendente',
    enviado_em      TIMESTAMPTZ,
    criado_em       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_leads_whatsapp        ON leads(whatsapp);
CREATE INDEX IF NOT EXISTS idx_leads_lead_key         ON leads(lead_key);
CREATE INDEX IF NOT EXISTS idx_leads_nome_normalizado ON leads(nome_normalizado);
CREATE INDEX IF NOT EXISTS idx_leads_email            ON leads(email);
CREATE INDEX IF NOT EXISTS idx_atividades_lead_id     ON atividades(lead_id);
CREATE INDEX IF NOT EXISTS idx_atividades_msg_id      ON atividades(msg_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prospects_nome_cidade ON lead_prospects (lower(nome), lower(cidade));
CREATE INDEX IF NOT EXISTS idx_msg_ab_lead            ON msg_ab_eventos(lead_id);
CREATE INDEX IF NOT EXISTS idx_conversas_jid          ON conversas(jid);
CREATE INDEX IF NOT EXISTS idx_conversas_status       ON conversas(status);
CREATE INDEX IF NOT EXISTS idx_conversas_ultimo       ON conversas(ultimo_msg_em DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_mensagens_conversa     ON mensagens_inbox(conversa_id);
CREATE INDEX IF NOT EXISTS idx_mensagens_msg_id       ON mensagens_inbox(msg_id);
"""

def _safe_schema(tenant_id: str) -> str:
    """Convert tenant_id to a safe PostgreSQL schema name."""
    safe = re.sub(r"[^a-z0-9]", "_", tenant_id.lower())
    return f"tenant_{safe}"


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
    temperatura          TEXT DEFAULT 'frio',
    resumo               TEXT DEFAULT '',
    acao_followup        TEXT DEFAULT '',
    observacoes          TEXT DEFAULT '',
    data_criacao         TEXT,
    ultima_interacao_em  TEXT,
    proximo_followup_em  TEXT DEFAULT '',
    data_recontato       TEXT DEFAULT '',
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

CREATE_INBOX_SQL = """
CREATE TABLE IF NOT EXISTS conversas (
    id                SERIAL PRIMARY KEY,
    jid               TEXT NOT NULL UNIQUE,
    nome_contato      TEXT DEFAULT '',
    numero            TEXT DEFAULT '',
    status            TEXT DEFAULT 'aberto',
    prioridade        TEXT DEFAULT 'normal',
    categoria         TEXT DEFAULT 'outro',
    total_mensagens   INT DEFAULT 0,
    nao_lidas         INT DEFAULT 0,
    ultimo_msg_em     TIMESTAMPTZ,
    primeira_msg_em   TIMESTAMPTZ,
    resumo_ia         TEXT DEFAULT '',
    resposta_sugerida TEXT DEFAULT '',
    confianca_ia      INT DEFAULT 0,
    lead_id           TEXT DEFAULT '',
    atribuido_a       TEXT DEFAULT '',
    resolvido_em      TIMESTAMPTZ,
    criado_em         TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mensagens_inbox (
    id              SERIAL PRIMARY KEY,
    msg_id          TEXT UNIQUE,
    conversa_id     INT NOT NULL,
    jid             TEXT NOT NULL,
    de_mim          BOOLEAN DEFAULT FALSE,
    tipo            TEXT DEFAULT 'text',
    texto           TEXT DEFAULT '',
    transcricao     TEXT DEFAULT '',
    duracao_audio_s REAL,
    media_url       TEXT DEFAULT '',
    status_proc     TEXT DEFAULT 'pendente',
    enviado_em      TIMESTAMPTZ,
    criado_em       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversas_jid      ON conversas(jid);
CREATE INDEX IF NOT EXISTS idx_conversas_status   ON conversas(status);
CREATE INDEX IF NOT EXISTS idx_conversas_ultimo   ON conversas(ultimo_msg_em DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_mensagens_conversa ON mensagens_inbox(conversa_id);
CREATE INDEX IF NOT EXISTS idx_mensagens_msg_id   ON mensagens_inbox(msg_id);
"""

CREATE_PROSPECTS_SQL = """
CREATE TABLE IF NOT EXISTS lead_prospects (
    id               SERIAL PRIMARY KEY,
    nome             TEXT DEFAULT '',
    cidade           TEXT DEFAULT '',
    segmento         TEXT DEFAULT '',
    telefone         TEXT DEFAULT '',
    whatsapp         TEXT DEFAULT '',
    website          TEXT DEFAULT '',
    instagram        TEXT DEFAULT '',
    link_maps        TEXT DEFAULT '',
    fonte            TEXT DEFAULT '',
    fonte_busca      TEXT DEFAULT '',
    status_revisao   TEXT DEFAULT 'pendente',
    data_coleta      TEXT DEFAULT '',
    enriquecido      INTEGER DEFAULT 0,
    lead_id_aprovado TEXT DEFAULT '',
    busca_id         TEXT DEFAULT '',
    rating           TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_prospects_nome_cidade
ON lead_prospects (lower(nome), lower(cidade));
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
    # Strip spurious leading zero (old PSTN prefix: 0 + DDD + number)
    if digits.startswith("0") and not digits.startswith("00"):
        digits = digits[1:]
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
    if status in ("negociando", "qualificado", "em espera"):
        return "alta"
    if status in ("novo", "1º contato"):
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


@dataclass
class FindByNameResult:
    """Resultado de busca de lead por nome (sem criação). Usado por micro-updates."""
    lead: Optional[Dict[str, Any]]
    candidates: List[Dict[str, Any]]
    score: float
    is_exact: bool       # match único e confiante (score >= min_score)
    is_ambiguous: bool   # múltiplos candidatos próximos


# ---------------------------------------------------------------------------
# DBService — PostgreSQL via psycopg2
# ---------------------------------------------------------------------------

class DBService:
    def __init__(self, database_url: str, skip_init: bool = False):
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=database_url,
        )
        if not skip_init:
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
                cur.execute(CREATE_PROSPECTS_SQL)
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
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS status_anterior TEXT DEFAULT ''"
                )
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS temperatura TEXT DEFAULT 'frio'"
                )
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS data_recontato TEXT DEFAULT ''"
                )
                # Migrar leads existentes: prioridade → remove dependência, temperatura = frio (default)
                # Migrar status antigos para novos nomes
                cur.execute(
                    "UPDATE leads SET status = 'contato feito' WHERE status IN ('1º contato', 'em contato')"
                )
                cur.execute(
                    "UPDATE leads SET status = 'conversando' WHERE status IN ('qualificado', 'em espera', 'proposta enviada')"
                )
                cur.execute(
                    "UPDATE leads SET status = 'contato feito', temperatura = 'frio' WHERE status = 'sem resposta'"
                )
                cur.execute(
                    "UPDATE leads SET status = 'perdido' WHERE status = 'arquivado'"
                )
                # Auto-set temperatura = cliente para fechados
                cur.execute(
                    "UPDATE leads SET temperatura = 'cliente' WHERE status = 'fechado' AND temperatura != 'cliente'"
                )
                # Rastreamento A/B de mensagem inicial
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS msg_ab_eventos (
                        id        SERIAL PRIMARY KEY,
                        lead_id   TEXT DEFAULT '',
                        variante  TEXT DEFAULT '',
                        segmento  TEXT DEFAULT '',
                        evento    TEXT DEFAULT '',
                        data_hora TEXT
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_msg_ab_lead ON msg_ab_eventos(lead_id)"
                )
                cur.execute(
                    "ALTER TABLE msg_ab_eventos ADD COLUMN IF NOT EXISTS tipo TEXT DEFAULT 'inicial'"
                )
                # Migrar pendencia → acao_followup
                cur.execute("""
                    DO $$ BEGIN
                      IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='leads' AND column_name='pendencia'
                      ) THEN
                        ALTER TABLE leads RENAME COLUMN pendencia TO acao_followup;
                      END IF;
                    END $$
                """)
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS acao_followup TEXT DEFAULT ''"
                )
                # Tabela de configurações persistentes (chave-valor)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS settings_kv (
                        key   TEXT PRIMARY KEY,
                        value TEXT NOT NULL DEFAULT ''
                    )
                """)
                # Auto-send: rastreamento de envio automático de primeiro contato
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS mensagem_enviada_em TEXT DEFAULT ''"
                )
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS auto_send_variante TEXT DEFAULT ''"
                )
                cur.execute(
                    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS origem_primeiro_contato TEXT DEFAULT ''"
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
                            resumo, acao_followup, observacoes, data_criacao,
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
                            lead.get("acao_followup", "") or lead.get("pendencia", ""),
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
        elif status:
            # Auto-sugerir followup quando status muda e nenhum foi explicitamente definido
            suggestion = suggest_followup_from_status(status, when)
            if suggestion:
                date_str, context = suggestion
                # Só aplica se não há followup futuro já agendado
                conn_peek = self._conn()
                try:
                    with conn_peek.cursor() as cur:
                        cur.execute("SELECT proximo_followup_em FROM leads WHERE lead_id = %s", (lead_id,))
                        row = cur.fetchone()
                        existing = (row[0] or "") if row else ""
                finally:
                    self._put(conn_peek)
                today = when.date().isoformat()
                if not existing or existing < today:
                    fields["proximo_followup_em"] = date_str
                    pass  # acao_followup is set explicitly by the caller, not auto-inferred

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
                final_status = status or "novo"
                # Auto-sugerir followup se não definido explicitamente
                auto_followup = followup_em or ""
                auto_acao = lead.get("acao_followup", "")
                if not auto_followup:
                    suggestion = suggest_followup_from_status(final_status, when)
                    if suggestion:
                        auto_followup, _ = suggestion
                cur.execute(
                    """INSERT INTO leads (
                        lead_id, nome, cidade, segmento, whatsapp, email, instagram, site,
                        responsavel, fonte, status, observacoes, data_criacao,
                        ultima_interacao_em, proximo_followup_em, acao_followup,
                        nome_normalizado, cidade_normalizada, lead_key
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'',%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        lead_id,
                        lead.get("nome", ""), lead.get("cidade", ""),
                        lead.get("segmento", ""), lead.get("whatsapp", ""),
                        lead.get("email", ""), lead.get("instagram", ""),
                        lead.get("site", ""), lead.get("responsavel", ""),
                        lead.get("fonte", ""), final_status,
                        now_iso, now_iso, auto_followup, auto_acao,
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
    # Lead summary / acao_followup
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

    def get_lead_activities(self, lead_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Retorna histórico de atividades de um lead, mais recente primeiro."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT data_hora, tipo, canal, acao_executada, resumo,
                              confianca_ia, duracao_audio_s
                       FROM atividades
                       WHERE lead_id = %s
                       ORDER BY data_hora DESC LIMIT %s""",
                    (lead_id, limit),
                )
                rows = cur.fetchall()
                return [
                    {
                        "data_hora": r[0],
                        "tipo": r[1],
                        "canal": r[2],
                        "acao_executada": r[3],
                        "resumo": r[4],
                        "confianca_ia": float(r[5]) if r[5] is not None else None,
                        "duracao_audio_s": float(r[6]) if r[6] is not None else None,
                    }
                    for r in rows
                ]
        finally:
            self._put(conn)

    def get_perfil_comunicacao(self, lead_id: str) -> Dict[str, Any]:
        """Retorna perfil de comunicação do lead: breakdown de tipos, duração total de áudio."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT
                           tipo,
                           COUNT(*) as total,
                           COALESCE(SUM(duracao_audio_s), 0) as duracao_total,
                           COALESCE(AVG(confianca_ia) FILTER (WHERE confianca_ia > 0), 0) as confianca_media
                       FROM atividades
                       WHERE lead_id = %s AND tipo IS NOT NULL AND tipo != ''
                       GROUP BY tipo
                       ORDER BY total DESC""",
                    (lead_id,),
                )
                rows = cur.fetchall()
                tipos = [
                    {
                        "tipo": r[0],
                        "total": r[1],
                        "duracao_total_s": float(r[2]),
                        "confianca_media": round(float(r[3]), 2),
                    }
                    for r in rows
                ]
                total_msgs = sum(t["total"] for t in tipos)
                total_audio_s = sum(t["duracao_total_s"] for t in tipos if t["tipo"] == "audio")
                return {
                    "tipos": tipos,
                    "total_mensagens": total_msgs,
                    "total_audio_s": total_audio_s,
                }
        finally:
            self._put(conn)

    def update_lead_resumo_acao(
        self,
        lead_id: str,
        resumo: Optional[str],
        acao_followup: Optional[str],
    ) -> None:
        fields: Dict[str, Any] = {}
        if resumo is not None:
            fields["resumo"] = resumo
        if acao_followup is not None:
            fields["acao_followup"] = acao_followup
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

    # ---------------------------------------------------------------------------
    # Auto-send helpers
    # ---------------------------------------------------------------------------

    def reativar_leads_auto_erro(self) -> int:
        """Desbloqueia leads com status='novo' marcados como auto_erro para que sejam
        tentados novamente pelo auto-sender. Retorna quantos leads foram reativados."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE leads
                       SET origem_primeiro_contato = ''
                       WHERE status = 'novo'
                         AND whatsapp != ''
                         AND origem_primeiro_contato = 'auto_erro'"""
                )
                count = cur.rowcount
            conn.commit()
            return count
        finally:
            self._put(conn)

    def get_leads_for_auto_send(self, limit: int = 1) -> List[Dict[str, Any]]:
        """Retorna leads elegíveis para envio automático de primeiro contato.

        Critérios:
        - status = 'novo'
        - whatsapp preenchido
        - mensagem_enviada_em vazio (nunca recebeu envio automático)
        - origem_primeiro_contato vazio (nenhum contato registrado ainda)
        Ordenação: data_criacao ASC (FIFO — leads mais antigos primeiro).
        Leads com segmento preenchido têm prioridade.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT lead_id, nome, segmento, whatsapp, cidade, data_criacao
                       FROM leads
                       WHERE status = 'novo'
                         AND whatsapp != ''
                         AND mensagem_enviada_em = ''
                         AND origem_primeiro_contato = ''
                         AND whatsapp NOT IN (
                           SELECT numero FROM conversas
                           WHERE status != 'arquivado'
                         )
                       ORDER BY
                         CASE WHEN segmento != '' THEN 0 ELSE 1 END,
                         data_criacao ASC
                       LIMIT %s""",
                    (limit,),
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    def mark_auto_sent(
        self,
        lead_id: str,
        variante: str,
        mensagem: str,
        when_iso: str,
    ) -> None:
        """Registra que o envio automático foi feito para este lead.

        Atualiza:
        - mensagem_enviada_em → timestamp do envio
        - auto_send_variante  → 'A', 'B' ou 'C'
        - origem_primeiro_contato → 'automatico'
        - status → 'contato feito'
        - temperatura → 'frio'
        - ultima_interacao_em → agora
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE leads
                       SET mensagem_enviada_em    = %s,
                           auto_send_variante     = %s,
                           origem_primeiro_contato = 'automatico',
                           status                 = 'contato feito',
                           temperatura            = 'frio',
                           ultima_interacao_em    = %s
                       WHERE lead_id = %s""",
                    (when_iso, variante, when_iso, lead_id),
                )
            conn.commit()
        finally:
            self._put(conn)

    def mark_auto_send_error(self, lead_id: str) -> None:
        """Marca lead como erro de envio automático para excluí-lo da fila.

        Seta origem_primeiro_contato = 'auto_erro' — get_leads_for_auto_send
        filtra por origem_primeiro_contato = '', então o lead é ignorado
        em todos os ciclos futuros.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE leads SET origem_primeiro_contato = 'auto_erro' WHERE lead_id = %s",
                    (lead_id,),
                )
            conn.commit()
        finally:
            self._put(conn)

    def count_auto_sent_today(self, today_iso: str) -> int:
        """Quantos envios automáticos já foram feitos hoje (YYYY-MM-DD).

        Conta diretamente na tabela leads pelo mensagem_enviada_em — fonte de
        verdade primária. Mais robusto que contar msg_ab_eventos, que pode
        falhar silenciosamente sem afetar o envio real.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*) FROM leads
                       WHERE origem_primeiro_contato = 'automatico'
                         AND mensagem_enviada_em >= %s""",
                    (today_iso,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
        finally:
            self._put(conn)

    def get_setting(self, key: str, default: str = "") -> str:
        """Lê um valor da tabela settings_kv. Retorna default se não existir."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM settings_kv WHERE key = %s", (key,))
                row = cur.fetchone()
                return row[0] if row else default
        finally:
            self._put(conn)

    def set_setting(self, key: str, value: str) -> None:
        """Grava ou atualiza um valor na tabela settings_kv."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO settings_kv (key, value) VALUES (%s, %s)
                       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                    (key, value),
                )
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
    # Micro-update: busca por nome e atualização pontual de status
    # ------------------------------------------------------------------

    def find_lead_by_name(self, candidate_name: str, min_score: float = 0.85) -> FindByNameResult:
        """Busca lead pelo nome usando fuzzy match. Nunca cria lead novo.

        - is_exact=True: um único match com score >= min_score
        - is_ambiguous=True: múltiplos candidatos próximos (sem match seguro)
        - lead=None + is_exact=False: nenhum match confiante
        """
        canonical = _canonicalize_name(candidate_name)
        _empty = FindByNameResult(lead=None, candidates=[], score=0.0, is_exact=False, is_ambiguous=False)
        if not canonical:
            return _empty

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Exclui leads definitivamente encerrados da busca
                cur.execute(
                    "SELECT * FROM leads WHERE status NOT IN ('perdido', 'fechado', 'contato inválido')"
                )
                rows = self._fetchall_dict(cur)
        finally:
            self._put(conn)

        scored: List[tuple] = []
        for row in rows:
            target = _canonicalize_name(row["nome"])
            if not target:
                continue
            from difflib import SequenceMatcher
            from rapidfuzz import fuzz as _fuzz
            sim = max(
                _fuzz.ratio(canonical, target) / 100.0,
                SequenceMatcher(None, canonical, target).ratio(),
            )
            scored.append((sim, row))

        if not scored:
            return _empty

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_row = scored[0]

        # Verifica ambiguidade: segundo candidato dentro de 0.06 do melhor
        ambiguity_threshold = min_score - 0.06
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        is_ambiguous = (
            best_score >= ambiguity_threshold
            and second_score >= ambiguity_threshold
            and (best_score - second_score) < 0.06
        )

        if is_ambiguous:
            candidates = [r for s, r in scored[:3] if s >= ambiguity_threshold]
            return FindByNameResult(lead=None, candidates=candidates, score=best_score, is_exact=False, is_ambiguous=True)

        if best_score >= min_score:
            return FindByNameResult(lead=best_row, candidates=[], score=best_score, is_exact=True, is_ambiguous=False)

        return _empty

    def update_lead_status(self, lead_id: str, status: str, temperatura: Optional[str] = None, when: Optional[datetime] = None) -> None:
        """Atualiza status e ultima_interacao_em de um lead. Usado por micro-updates."""
        now = (when or datetime.utcnow()).isoformat()
        # Auto-set temperatura = cliente quando fecha
        if status == "fechado":
            temperatura = "cliente"
        fields: Dict[str, Any] = {"status": status, "ultima_interacao_em": now}
        if temperatura:
            fields["temperatura"] = temperatura
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [lead_id]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE leads SET {set_clause} WHERE lead_id = %s", values)
            conn.commit()
        finally:
            self._put(conn)
        logger.info("micro_update_status | lead_id=%s status=%s temperatura=%s", lead_id, status, temperatura)

    # ------------------------------------------------------------------
    # Consultas conversacionais (queries do CRM)
    # ------------------------------------------------------------------

    def query_leads_today(self) -> Dict[str, Any]:
        """Leads criados hoje."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT lead_id, nome, segmento, status
                       FROM leads
                       WHERE LEFT(data_criacao, 10) = CURRENT_DATE::text
                       ORDER BY data_criacao DESC"""
                )
                rows = self._fetchall_dict(cur)
        finally:
            self._put(conn)
        return {"count": len(rows), "leads": rows}

    def query_leads_by_activity_type(self, activity_type: str, days: int = 7) -> List[Dict[str, Any]]:
        """Leads com atividade do tipo especificado nos últimos N dias."""
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT DISTINCT l.lead_id, l.nome, l.segmento, l.status, l.cidade
                       FROM leads l
                       JOIN atividades a ON l.lead_id = a.lead_id
                       WHERE a.tipo = %s AND a.data_hora >= %s
                       ORDER BY l.nome""",
                    (activity_type, cutoff),
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    def query_leads_overdue_followup(self) -> List[Dict[str, Any]]:
        """Leads com follow-up vencido (data <= hoje, não encerrados)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT lead_id, nome, segmento, status, proximo_followup_em, acao_followup
                       FROM leads
                       WHERE proximo_followup_em != ''
                         AND LEFT(proximo_followup_em, 10) <= CURRENT_DATE::text
                         AND status NOT IN ('fechado', 'perdido', 'contato inválido')
                       ORDER BY proximo_followup_em ASC
                       LIMIT 10"""
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    def get_followups_today_list(self) -> List[Dict[str, Any]]:
        """Leads com followup agendado exatamente para hoje (usado no lembrete das 9h)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT lead_id, nome, status, acao_followup, proximo_followup_em
                       FROM leads
                       WHERE LEFT(proximo_followup_em, 10) = CURRENT_DATE::text
                         AND status NOT IN ('fechado', 'perdido', 'contato inválido')
                       ORDER BY nome ASC"""
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    def query_leads_by_status(self, status: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Leads com determinado status."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT lead_id, nome, segmento, cidade, ultima_interacao_em
                       FROM leads
                       WHERE status = %s
                       ORDER BY ultima_interacao_em DESC NULLS LAST
                       LIMIT %s""",
                    (status, limit),
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    def expire_first_contact(self, days: int = 5) -> List[Dict[str, Any]]:
        """Leads com status 'contato feito' sem resposta há mais de `days` dias.

        Marca temperatura como 'frio' — o status não muda (ainda é 'contato feito'),
        mas o lead aparece como frio no funil. Retorna lista afetada para log.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE leads
                       SET temperatura = 'frio',
                           ultima_interacao_em = ultima_interacao_em
                       WHERE status = 'contato feito'
                         AND temperatura != 'frio'
                         AND ultima_interacao_em < NOW() - (%s * INTERVAL '1 day')
                       RETURNING lead_id, nome""",
                    (days,),
                )
                rows = cur.fetchall()
            conn.commit()
            return [{"lead_id": r[0], "nome": r[1]} for r in rows]
        finally:
            self._put(conn)

    def cool_down_leads(self, days: int = 7) -> List[Dict[str, Any]]:
        """Leads ativos sem interação por `days` dias: desce temperatura um nível.

        frio ← morno ← engajado ← quente   (cliente nunca desce)
        Retorna lista de leads afetados.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE leads
                       SET temperatura = CASE temperatura
                           WHEN 'quente'   THEN 'engajado'
                           WHEN 'engajado' THEN 'morno'
                           WHEN 'morno'    THEN 'frio'
                           ELSE temperatura
                       END
                       WHERE ultima_interacao_em IS NOT NULL
                         AND ultima_interacao_em != ''
                         AND ultima_interacao_em < NOW() - (%s * INTERVAL '1 day')
                         AND status NOT IN ('fechado', 'perdido', 'contato inválido')
                         AND temperatura NOT IN ('frio', 'cliente')
                       RETURNING lead_id, nome, temperatura""",
                    (days,),
                )
                rows = cur.fetchall()
            conn.commit()
            return [{"lead_id": r[0], "nome": r[1], "temperatura": r[2]} for r in rows]
        finally:
            self._put(conn)

    def get_recontato_leads(self) -> List[Dict[str, Any]]:
        """Leads perdidos com data_recontato <= hoje — candidatos a recontato."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT lead_id, nome, segmento, cidade, whatsapp, data_recontato, acao_followup, motivo_perda
                       FROM leads
                       WHERE status = 'perdido'
                         AND data_recontato != ''
                         AND LEFT(data_recontato, 10) <= CURRENT_DATE::text
                       ORDER BY data_recontato ASC
                       LIMIT 20"""
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    def get_recent_novo_leads(self, limit: int = 10, minutes: int = 30) -> List[Dict[str, Any]]:
        """Leads criados recentemente ainda com status 'novo', ordenados do mais recente."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT lead_id, nome, segmento, cidade, status
                       FROM leads
                       WHERE status = 'novo'
                         AND criado_em >= NOW() - (%s * INTERVAL '1 minute')
                       ORDER BY criado_em DESC
                       LIMIT %s""",
                    (minutes, limit),
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    # ------------------------------------------------------------------
    # Sync Sheets → DB (edições manuais do usuário)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Rastreamento A/B — Mensagem Inicial
    # ------------------------------------------------------------------

    def registrar_msg_ab_evento(self, lead_id: str, variante: str, segmento: str, evento: str, tipo: str = 'inicial') -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO msg_ab_eventos (lead_id, variante, segmento, evento, data_hora, tipo) VALUES (%s,%s,%s,%s,%s,%s)",
                    (lead_id, variante, segmento, evento, now, tipo),
                )
            conn.commit()
        finally:
            self._put(conn)

    def get_msg_ab_stats(self) -> Dict[str, Any]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Totais por tipo + variante + evento
                cur.execute("""
                    SELECT COALESCE(tipo, 'inicial') AS tipo, variante, evento, COUNT(*) AS n
                    FROM msg_ab_eventos
                    GROUP BY tipo, variante, evento
                    ORDER BY tipo, variante, evento
                """)
                rows = self._fetchall_dict(cur)

                # Por segmento + tipo + variante + evento
                cur.execute("""
                    SELECT COALESCE(tipo, 'inicial') AS tipo, segmento, variante, evento, COUNT(*) AS n
                    FROM msg_ab_eventos
                    WHERE segmento != ''
                    GROUP BY tipo, segmento, variante, evento
                    ORDER BY tipo, segmento, variante, evento
                """)
                seg_rows = self._fetchall_dict(cur)

            # Montar estrutura por tipo → variante
            por_tipo: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                t = r['tipo']
                v = r['variante']
                if t not in por_tipo:
                    por_tipo[t] = {}
                if v not in por_tipo[t]:
                    por_tipo[t][v] = {'copiadas': 0, 'responderam': 0}
                if r['evento'] == 'copiada':
                    por_tipo[t][v]['copiadas'] = r['n']
                elif r['evento'] == 'respondeu':
                    por_tipo[t][v]['responderam'] = r['n']
            for t in por_tipo:
                for v, d in por_tipo[t].items():
                    d['taxa'] = round(d['responderam'] * 100 / d['copiadas'], 1) if d['copiadas'] else 0

            # Backward-compat: variantes = totais da mensagem inicial
            variantes = por_tipo.get('inicial', {})

            # Montar por segmento (grouped by tipo)
            seg_tipo_map: Dict[str, Dict[str, Dict]] = {}
            for r in seg_rows:
                t = r['tipo']
                s = r['segmento']
                v = r['variante']
                if t not in seg_tipo_map:
                    seg_tipo_map[t] = {}
                if s not in seg_tipo_map[t]:
                    seg_tipo_map[t][s] = {}
                key = f"{v}_{'copiadas' if r['evento'] == 'copiada' else 'responderam'}"
                seg_tipo_map[t][s][key] = r['n']

            por_segmento_inicial = [{'segmento': s, **vals} for s, vals in seg_tipo_map.get('inicial', {}).items()]
            por_segmento_fu1 = [{'segmento': s, **vals} for s, vals in seg_tipo_map.get('fu1', {}).items()]
            por_segmento_fu2 = [{'segmento': s, **vals} for s, vals in seg_tipo_map.get('fu2', {}).items()]

            return {
                'variantes': variantes,
                'por_segmento': por_segmento_inicial,
                'por_tipo': por_tipo,
                'followup1': {'variantes': por_tipo.get('fu1', {}), 'por_segmento': por_segmento_fu1},
                'followup2': {'variantes': por_tipo.get('fu2', {}), 'por_segmento': por_segmento_fu2},
            }
        finally:
            self._put(conn)

    # ------------------------------------------------------------------
    # Dashboard API methods
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Returns aggregated stats for the dashboard."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, COUNT(*) FROM leads GROUP BY status ORDER BY COUNT(*) DESC"
                )
                by_status = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute(
                    "SELECT segmento, COUNT(*) FROM leads WHERE segmento != '' GROUP BY segmento ORDER BY COUNT(*) DESC"
                )
                by_segmento = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute(
                    "SELECT temperatura, COUNT(*) FROM leads WHERE temperatura != '' GROUP BY temperatura ORDER BY COUNT(*) DESC"
                )
                by_temperatura = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute(
                    "SELECT COUNT(*) FROM leads WHERE status NOT IN ('perdido', 'fechado')"
                )
                total_ativos = cur.fetchone()[0]

                cur.execute(
                    """SELECT COUNT(*) FROM leads
                       WHERE proximo_followup_em != '' AND LEFT(proximo_followup_em, 10) < CURRENT_DATE::text
                         AND status NOT IN ('fechado', 'perdido')"""
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
                    """SELECT lead_id, nome, segmento, status, temperatura, data_criacao FROM leads
                       ORDER BY data_criacao DESC LIMIT 5"""
                )
                cols = [d[0] for d in cur.description]
                recentes = [dict(zip(cols, r)) for r in cur.fetchall()]

                cur.execute(
                    """SELECT lead_id, nome, segmento, status, temperatura, proximo_followup_em, acao_followup
                       FROM leads WHERE proximo_followup_em != ''
                         AND LEFT(proximo_followup_em, 10) >= CURRENT_DATE::text
                         AND status NOT IN ('fechado', 'perdido')
                       ORDER BY proximo_followup_em ASC LIMIT 5"""
                )
                cols = [d[0] for d in cur.description]
                proximos_followups = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Leads para recontato: perdidos com data_recontato <= hoje
                cur.execute(
                    """SELECT COUNT(*) FROM leads
                       WHERE status = 'perdido'
                         AND data_recontato != ''
                         AND LEFT(data_recontato, 10) <= CURRENT_DATE::text"""
                )
                recontatos_hoje = cur.fetchone()[0]

                # Leads nunca contatados: status 'novo' criados há 7+ dias sem nenhuma atividade
                cur.execute(
                    """SELECT COUNT(*) FROM leads l
                       WHERE l.status = 'novo'
                         AND l.data_criacao < (NOW() - INTERVAL '7 days')::text
                         AND NOT EXISTS (
                             SELECT 1 FROM atividades a WHERE a.lead_id = l.lead_id
                         )"""
                )
                leads_nunca_contatados = cur.fetchone()[0]

            return {
                "by_status": by_status,
                "by_segmento": by_segmento,
                "by_temperatura": by_temperatura,
                "total_ativos": total_ativos,
                "followups_vencidos": followups_vencidos,
                "followups_hoje": followups_hoje,
                "criados_semana": criados_semana,
                "recentes": recentes,
                "proximos_followups": proximos_followups,
                "recontatos_hoje": recontatos_hoje,
                "leads_nunca_contatados": leads_nunca_contatados,
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
                        COUNT(*) AS total_leads,
                        COUNT(*) FILTER (WHERE status = 'fechado') AS total_fechados,
                        COUNT(*) FILTER (WHERE status = 'perdido') AS total_perdidos,
                        COUNT(*) FILTER (WHERE temperatura = 'frio' AND status NOT IN ('fechado','perdido','contato inválido')) AS total_frios,
                        COALESCE(SUM(valor_venda) FILTER (WHERE status = 'fechado'), 0) AS valor_total_vendas,
                        COUNT(*) FILTER (
                            WHERE proximo_followup_em != '' AND proximo_followup_em < NOW()::text
                            AND status NOT IN ('fechado','perdido')
                        ) AS followups_vencidos,
                        ROUND(
                            COUNT(*) FILTER (WHERE status = 'fechado') * 100.0
                            / NULLIF(COUNT(*), 0), 1
                        ) AS taxa_conversao
                    FROM leads
                """)
                krow = cur.fetchone()
                kpis = {
                    "total_leads": krow[0] or 0,
                    "total_fechados": krow[1] or 0,
                    "total_perdidos": krow[2] or 0,
                    "total_frios": krow[3] or 0,
                    "valor_total_vendas": float(krow[4] or 0),
                    "followups_vencidos": krow[5] or 0,
                    "taxa_conversao": float(krow[6]) if krow[6] is not None else 0.0,
                }

                # Bloco B — Funil por status
                cur.execute("""
                    SELECT status, COUNT(*) as total
                    FROM leads
                    GROUP BY status
                """)
                funil_raw = {r[0]: r[1] for r in cur.fetchall()}

                # Bloco B2 — Funil de conversão (o dado mais importante)
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE status != 'arquivado') AS total,
                        COUNT(*) FILTER (WHERE status NOT IN ('arquivado', 'novo')) AS contatados,
                        COUNT(*) FILTER (WHERE status NOT IN ('arquivado', 'novo', 'contato feito', 'contato inválido')) AS responderam,
                        COUNT(*) FILTER (WHERE status IN ('conversando', 'negociando', 'fechado')) AS conversas_reais,
                        COUNT(*) FILTER (WHERE status = 'fechado') AS fechados
                    FROM leads
                """)
                fcrow = cur.fetchone()
                funil_conversao = {
                    "total":          fcrow[0] or 0,
                    "contatados":     fcrow[1] or 0,
                    "responderam":    fcrow[2] or 0,
                    "conversas_reais": fcrow[3] or 0,
                    "fechados":       fcrow[4] or 0,
                }

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
                "funil_conversao": funil_conversao,
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

    def _auto_transition_stale_leads(self) -> None:
        """Auto-baixa temperatura de leads ativos sem interação recente.

        Leads conversando ou negociando sem interação em 5+ dias → temperatura desce.
        Status não muda — a temperatura já comunica o estado de engajamento.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE leads
                    SET temperatura = CASE temperatura
                        WHEN 'quente'   THEN 'engajado'
                        WHEN 'engajado' THEN 'morno'
                        WHEN 'morno'    THEN 'frio'
                        ELSE temperatura
                    END
                    WHERE status IN ('conversando', 'negociando')
                      AND temperatura NOT IN ('frio', 'cliente')
                      AND (
                        ultima_interacao_em IS NULL
                        OR ultima_interacao_em = ''
                        OR LEFT(ultima_interacao_em, 10) < (CURRENT_DATE - INTERVAL '5 days')::text
                      )
                """)
                count = cur.rowcount
            conn.commit()
            if count > 0:
                logger.info("auto_transition | %d leads tiveram temperatura reduzida por inatividade", count)
        except Exception:
            conn.rollback()
            logger.warning("auto_transition_leads falhou", exc_info=True)
        finally:
            self._put(conn)

    def migrate_em_contato_to_primeiro_contato(self) -> int:
        """One-time migration: moves all 'em contato' leads to '1º contato'."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE leads SET status = '1º contato', prioridade = 'media' WHERE status = 'em contato'"
                )
                count = cur.rowcount
            conn.commit()
            if count:
                logger.info("migration | %d leads 'em contato' → '1º contato'", count)
            return count
        finally:
            self._put(conn)

    def list_leads(
        self,
        status: Optional[str] = None,
        segmento: Optional[str] = None,
        temperatura: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """Returns paginated leads with optional filters."""
        # Auto-transition stale leads before returning results
        self._auto_transition_stale_leads()
        conditions: List[str] = []
        params: List[Any] = []

        if status:
            conditions.append("status = %s")
            params.append(status)
        if segmento:
            conditions.append("segmento = %s")
            params.append(segmento)
        if temperatura:
            conditions.append("temperatura = %s")
            params.append(temperatura)
        if search:
            conditions.append("(nome ILIKE %s OR cidade ILIKE %s OR responsavel ILIKE %s OR whatsapp ILIKE %s)")
            s = f"%{search}%"
            params.extend([s, s, s, s])

        where = " AND ".join(conditions) if conditions else "TRUE"
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
        return self._create_lead(lead, status, data.get("proximo_followup_em") or None, now)

    def update_lead_from_dashboard(self, lead_id: str, data: Dict[str, Any]) -> bool:
        """Updates a lead from dashboard input (allows more fields than Sheets sync)."""
        allowed = {
            "nome", "cidade", "segmento", "whatsapp", "email",
            "instagram", "site", "responsavel", "fonte",
            "status", "temperatura", "observacoes", "proximo_followup_em", "acao_followup",
            "valor_venda", "data_fechamento", "motivo_perda", "data_criacao", "data_recontato",
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
        # Stamp ultima_interacao_em on status change; auto-set temperatura for fechado
        if "status" in safe_fields:
            safe_fields["ultima_interacao_em"] = datetime.utcnow().isoformat()
            if safe_fields["status"] == "fechado":
                safe_fields.setdefault("temperatura", "cliente")

        # Convert valor_venda: empty string is invalid for NUMERIC column
        if "valor_venda" in safe_fields:
            v = safe_fields["valor_venda"]
            try:
                safe_fields["valor_venda"] = float(v) if v != "" else 0
            except (ValueError, TypeError):
                safe_fields["valor_venda"] = 0

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

    # ------------------------------------------------------------------
    # Prospecção — lead_prospects (fila de revisão)
    # ------------------------------------------------------------------

    def insert_prospect(self, data: Dict[str, Any]) -> bool:
        """Insert a prospect. Returns True if inserted, False if duplicate (nome+cidade)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO lead_prospects
                        (nome, cidade, segmento, telefone, whatsapp, website, instagram,
                         link_maps, fonte, fonte_busca, data_coleta, busca_id, rating)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (lower(nome), lower(cidade)) DO NOTHING
                       RETURNING id""",
                    (
                        (data.get("nome") or "").strip(),
                        (data.get("cidade") or "").strip(),
                        (data.get("segmento") or "").strip(),
                        (data.get("telefone") or "").strip(),
                        (data.get("whatsapp") or "").strip(),
                        (data.get("website") or "").strip(),
                        (data.get("instagram") or "").strip(),
                        (data.get("link_maps") or "").strip(),
                        (data.get("fonte") or "").strip(),
                        (data.get("fonte_busca") or "").strip(),
                        (data.get("data_coleta") or "").strip(),
                        (data.get("busca_id") or "").strip(),
                        (data.get("rating") or "").strip(),
                    ),
                )
                inserted = cur.fetchone() is not None
            conn.commit()
        finally:
            self._put(conn)
        return inserted

    def list_prospects(
        self,
        status_revisao: Optional[str] = None,
        busca_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        conditions: List[str] = []
        params: List[Any] = []
        if status_revisao:
            conditions.append("status_revisao = %s")
            params.append(status_revisao)
        if busca_id:
            conditions.append("busca_id = %s")
            params.append(busca_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        offset = (page - 1) * page_size
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) FROM lead_prospects {where}", params)
                total = cur.fetchone()[0]
                cur.execute(
                    f"SELECT * FROM lead_prospects {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                    params + [page_size, offset],
                )
                prospects = self._fetchall_dict(cur)
            return {"prospects": prospects, "total": total, "page": page, "page_size": page_size}
        finally:
            self._put(conn)

    def get_prospect(self, prospect_id: int) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM lead_prospects WHERE id = %s", (prospect_id,))
                return self._fetchone_dict(cur)
        finally:
            self._put(conn)

    def update_prospect(self, prospect_id: int, fields: Dict[str, Any]) -> None:
        allowed = {"status_revisao", "whatsapp", "instagram", "enriquecido", "lead_id_aprovado", "website"}
        safe = {k: v for k, v in fields.items() if k in allowed}
        if not safe:
            return
        set_clause = ", ".join(f"{k} = %s" for k in safe)
        values = list(safe.values()) + [prospect_id]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE lead_prospects SET {set_clause} WHERE id = %s", values)
            conn.commit()
        finally:
            self._put(conn)

    def get_prospects_to_enrich(self, busca_id: str) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT * FROM lead_prospects
                       WHERE busca_id = %s AND enriquecido = 0
                       ORDER BY id""",
                    (busca_id,),
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    def get_prospect_enrich_status(self, busca_id: str) -> Dict[str, int]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM lead_prospects WHERE busca_id = %s", (busca_id,)
                )
                total = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM lead_prospects WHERE busca_id = %s AND enriquecido = 1",
                    (busca_id,),
                )
                done = cur.fetchone()[0]
            return {"total": total, "enriquecidos": done, "pendentes": total - done}
        finally:
            self._put(conn)

    def reset_prospects_for_reenrich(self, busca_id: Optional[str] = None) -> List[str]:
        """Reset enriquecido=0 for pendente prospects with no WhatsApp.

        Returns list of distinct busca_ids affected so callers can trigger
        enrich_batch for each one.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                base = """
                    UPDATE lead_prospects
                    SET enriquecido = 0
                    WHERE status_revisao = 'pendente'
                      AND (whatsapp IS NULL OR whatsapp = '')
                      AND enriquecido = 1
                """
                params: list = []
                if busca_id:
                    base += " AND busca_id = %s"
                    params.append(busca_id)
                cur.execute(base, params)

                if busca_id:
                    busca_ids = [busca_id] if cur.rowcount > 0 else []
                else:
                    cur.execute(
                        """SELECT DISTINCT busca_id FROM lead_prospects
                           WHERE status_revisao = 'pendente'
                             AND (whatsapp IS NULL OR whatsapp = '')
                             AND enriquecido = 0"""
                    )
                    busca_ids = [r[0] for r in cur.fetchall() if r[0]]
            conn.commit()
            return busca_ids
        finally:
            self._put(conn)

    def approve_prospect(self, prospect_id: int) -> str:
        """Creates a lead from prospect, updates prospect status. Returns lead_id."""
        p = self.get_prospect(prospect_id)
        if not p:
            raise ValueError(f"Prospect {prospect_id} not found")
        lead_data = {
            "nome": p["nome"],
            "cidade": p["cidade"],
            "segmento": p["segmento"],
            "whatsapp": p["whatsapp"] or p["telefone"],
            "site": p["website"],
            "instagram": p["instagram"],
            "fonte": p["fonte_busca"] or p["fonte"],
            "status": "novo",
        }
        lead_id = self.create_lead_from_dashboard(lead_data)
        self.update_prospect(prospect_id, {"status_revisao": "aprovado", "lead_id_aprovado": lead_id})
        return lead_id

    def delete_discarded_prospects(self) -> int:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM lead_prospects WHERE status_revisao = 'descartado'")
                count = cur.rowcount
            conn.commit()
        finally:
            self._put(conn)
        return count

    def get_prospect_counts(self) -> Dict[str, int]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT status_revisao, COUNT(*) FROM lead_prospects
                       GROUP BY status_revisao"""
                )
                rows = cur.fetchall()
            counts = {"pendente": 0, "aprovado": 0, "descartado": 0}
            for status, cnt in rows:
                if status in counts:
                    counts[status] = cnt
            return counts
        finally:
            self._put(conn)
        return True

    # ---------------------------------------------------------------------------
    # Inbox — tabelas conversas + mensagens_inbox
    # ---------------------------------------------------------------------------

    def create_inbox_tables(self) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(CREATE_INBOX_SQL)
            conn.commit()
            logger.info("Inbox tables ensured")
        except Exception:
            conn.rollback()
            logger.exception("create_inbox_tables falhou")
            raise
        finally:
            self._put(conn)

    def get_or_create_conversa(self, jid: str, nome_contato: str = "", numero: str = "") -> Dict[str, Any]:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """INSERT INTO conversas (jid, nome_contato, numero)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (jid) DO UPDATE SET
                           nome_contato = CASE
                               WHEN EXCLUDED.nome_contato != '' THEN EXCLUDED.nome_contato
                               ELSE conversas.nome_contato END,
                           atualizado_em = NOW()
                       RETURNING *""",
                    (jid, nome_contato, numero),
                )
                row = cur.fetchone()
            conn.commit()
            return dict(row) if row else {}
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def add_mensagem_inbox(
        self,
        msg_id: str,
        conversa_id: int,
        jid: str,
        de_mim: bool,
        tipo: str,
        texto: str,
        transcricao: str = "",
        duracao_audio_s: Optional[float] = None,
        media_url: str = "",
        enviado_em=None,
    ) -> int:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO mensagens_inbox
                       (msg_id, conversa_id, jid, de_mim, tipo, texto, transcricao,
                        duracao_audio_s, media_url, status_proc, enviado_em)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'processado', %s)
                       ON CONFLICT (msg_id) DO NOTHING
                       RETURNING id""",
                    (msg_id, conversa_id, jid, de_mim, tipo, texto, transcricao,
                     duracao_audio_s, media_url, enviado_em),
                )
                row = cur.fetchone()
                msg_db_id = row[0] if row else 0

                if not de_mim:
                    cur.execute(
                        """UPDATE conversas SET
                               total_mensagens = total_mensagens + 1,
                               nao_lidas       = nao_lidas + 1,
                               ultimo_msg_em   = COALESCE(%s, NOW()),
                               primeira_msg_em = COALESCE(primeira_msg_em, %s),
                               atualizado_em   = NOW()
                           WHERE id = %s""",
                        (enviado_em, enviado_em, conversa_id),
                    )
                else:
                    cur.execute(
                        """UPDATE conversas SET
                               total_mensagens = total_mensagens + 1,
                               ultimo_msg_em   = COALESCE(%s, NOW()),
                               atualizado_em   = NOW()
                           WHERE id = %s""",
                        (enviado_em, conversa_id),
                    )
            conn.commit()
            return msg_db_id
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def update_conversa_triage(
        self,
        conversa_id: int,
        categoria: str,
        prioridade: str,
        resumo_ia: str,
        resposta_sugerida: str,
        confianca_ia: int,
        nome_contato: str = "",
    ) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE conversas SET
                           categoria         = %s,
                           prioridade        = %s,
                           resumo_ia         = %s,
                           resposta_sugerida = %s,
                           confianca_ia      = %s,
                           nome_contato      = CASE WHEN %s != '' THEN %s ELSE nome_contato END,
                           atualizado_em     = NOW()
                       WHERE id = %s""",
                    (categoria, prioridade, resumo_ia, resposta_sugerida, confianca_ia,
                     nome_contato, nome_contato, conversa_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def list_conversas(
        self,
        status: str = "aberto",
        categoria: Optional[str] = None,
        prioridade: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        conditions: List[str] = []
        params: List[Any] = []

        if status and status != "todas":
            conditions.append("status = %s")
            params.append(status)
        if categoria:
            conditions.append("categoria = %s")
            params.append(categoria)
        if prioridade:
            conditions.append("prioridade = %s")
            params.append(prioridade)
        if search:
            conditions.append("(nome_contato ILIKE %s OR numero ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        offset = (page - 1) * page_size

        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SELECT COUNT(*) FROM conversas {where}", params)
                total = cur.fetchone()[0]

                cur.execute(
                    f"""SELECT * FROM conversas {where}
                        ORDER BY
                            CASE prioridade
                                WHEN 'urgente' THEN 1
                                WHEN 'alta'    THEN 2
                                WHEN 'normal'  THEN 3
                                ELSE 4
                            END,
                            ultimo_msg_em DESC NULLS LAST
                        LIMIT %s OFFSET %s""",
                    params + [page_size, offset],
                )
                rows = [dict(r) for r in cur.fetchall()]

            return {"conversas": rows, "total": total, "page": page, "page_size": page_size}
        finally:
            self._put(conn)

    def get_conversa(self, conversa_id: int) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM conversas WHERE id = %s", (conversa_id,))
                row = cur.fetchone()
            return dict(row) if row else None
        finally:
            self._put(conn)

    def get_conversa_mensagens(self, conversa_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT * FROM mensagens_inbox
                       WHERE conversa_id = %s
                       ORDER BY enviado_em ASC NULLS LAST, id ASC
                       LIMIT %s""",
                    (conversa_id, limit),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._put(conn)

    def update_conversa(self, conversa_id: int, fields: Dict[str, Any]) -> None:
        ALLOWED = {"status", "prioridade", "categoria", "atribuido_a", "lead_id", "resposta_sugerida"}
        safe = {k: v for k, v in fields.items() if k in ALLOWED}
        if not safe:
            return
        conn = self._conn()
        try:
            set_parts = [f"{k} = %s" for k in safe]
            vals = list(safe.values())
            if "status" in safe and safe["status"] == "resolvido":
                set_parts.append("resolvido_em = NOW()")
            set_parts.append("atualizado_em = NOW()")
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE conversas SET {', '.join(set_parts)} WHERE id = %s",
                    vals + [conversa_id],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def mark_conversa_read(self, conversa_id: int) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE conversas SET nao_lidas = 0 WHERE id = %s", (conversa_id,))
            conn.commit()
        finally:
            self._put(conn)

    def get_inbox_dashboard_stats(self, timezone: str = "America/Sao_Paulo") -> Dict[str, Any]:
        """Retorna todos os dados do dashboard inbox-first em uma única chamada."""
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        today = _dt.now(ZoneInfo(timezone)).date().isoformat()

        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Contadores principais
                cur.execute(
                    """SELECT
                           COUNT(*) FILTER (WHERE status = 'aberto')                                       AS abertas,
                           COUNT(*) FILTER (WHERE prioridade = 'urgente' AND status = 'aberto')             AS urgentes,
                           COALESCE(SUM(nao_lidas) FILTER (WHERE status = 'aberto'), 0)                    AS total_nao_lidas,
                           COUNT(*) FILTER (
                               WHERE status = 'resolvido'
                               AND DATE(resolvido_em AT TIME ZONE %s) = %s::date)                           AS resolvidas_hoje,
                           COUNT(*) FILTER (WHERE status = 'aberto' AND nao_lidas > 0)                     AS conversas_nao_lidas
                       FROM conversas""",
                    (timezone, today),
                )
                row = cur.fetchone()
                stats = {
                    "abertas":              row[0] or 0,
                    "urgentes":             row[1] or 0,
                    "total_nao_lidas":      row[2] or 0,
                    "resolvidas_hoje":      row[3] or 0,
                    "conversas_nao_lidas":  row[4] or 0,
                }

                # Volume por categoria (não arquivadas)
                cur.execute(
                    """SELECT COALESCE(categoria, 'outro'), COUNT(*)
                       FROM conversas
                       WHERE status != 'arquivado'
                       GROUP BY 1 ORDER BY 2 DESC"""
                )
                stats["por_categoria"] = {r[0]: r[1] for r in cur.fetchall()}

                # Volume últimos 7 dias (por data de criação)
                cur.execute(
                    """SELECT DATE(criado_em AT TIME ZONE %s) AS dia, COUNT(*) AS total
                       FROM conversas
                       WHERE criado_em >= NOW() - INTERVAL '7 days'
                       GROUP BY 1 ORDER BY 1 ASC""",
                    (timezone,),
                )
                stats["volume_7d"] = [{"dia": str(r[0]), "total": r[1]} for r in cur.fetchall()]

                # Conversas urgentes/alta com não lidas (lista de ação)
                cur.execute(
                    """SELECT id, nome_contato, numero, prioridade, categoria,
                              nao_lidas, resumo_ia, ultimo_msg_em, status
                       FROM conversas
                       WHERE status = 'aberto' AND prioridade IN ('urgente', 'alta')
                       ORDER BY
                           CASE prioridade WHEN 'urgente' THEN 1 ELSE 2 END,
                           nao_lidas DESC,
                           ultimo_msg_em DESC NULLS LAST
                       LIMIT 5"""
                )
                cols = [d[0] for d in cur.description]
                urgentes = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Conversas normais sem resposta (nao_lidas > 0)
                cur.execute(
                    """SELECT id, nome_contato, numero, prioridade, categoria,
                              nao_lidas, resumo_ia, ultimo_msg_em
                       FROM conversas
                       WHERE status = 'aberto' AND nao_lidas > 0
                         AND prioridade NOT IN ('urgente', 'alta')
                       ORDER BY ultimo_msg_em DESC NULLS LAST
                       LIMIT 5"""
                )
                cols = [d[0] for d in cur.description]
                sem_resposta = [dict(zip(cols, r)) for r in cur.fetchall()]

            return {
                "stats":            stats,
                "urgentes":         urgentes,
                "sem_resposta":     sem_resposta,
            }
        finally:
            self._put(conn)

    def get_inbox_stats(self) -> Dict[str, Any]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT
                           COUNT(*) FILTER (WHERE status = 'aberto')                      AS abertas,
                           COUNT(*) FILTER (WHERE status = 'resolvido')                   AS resolvidas,
                           COUNT(*) FILTER (WHERE status = 'arquivado')                   AS arquivadas,
                           COUNT(*) FILTER (WHERE prioridade = 'urgente' AND status = 'aberto') AS urgentes,
                           COALESCE(SUM(nao_lidas) FILTER (WHERE status = 'aberto'), 0)   AS total_nao_lidas,
                           COUNT(*) FILTER (WHERE categoria = 'suporte')                  AS suporte,
                           COUNT(*) FILTER (WHERE categoria = 'vendas')                   AS vendas,
                           COUNT(*) FILTER (WHERE categoria = 'spam')                     AS spam
                       FROM conversas"""
                )
                row = cur.fetchone()
            return {
                "abertas": row[0] or 0,
                "resolvidas": row[1] or 0,
                "arquivadas": row[2] or 0,
                "urgentes": row[3] or 0,
                "total_nao_lidas": row[4] or 0,
                "suporte": row[5] or 0,
                "vendas": row[6] or 0,
                "spam": row[7] or 0,
            }
        finally:
            self._put(conn)

    def get_ia_stats(self) -> Dict[str, Any]:
        """Estatísticas da Inteligência IA — separado dos dados dos leads.
        Agrega: ações mais executadas, confiança média por tipo de msg,
        volume de processamento por dia e score médio de interpretação.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Top ações executadas pela IA
                cur.execute(
                    """SELECT acao_executada, COUNT(*) as total
                       FROM atividades
                       WHERE acao_executada IS NOT NULL AND acao_executada != ''
                       GROUP BY acao_executada
                       ORDER BY total DESC
                       LIMIT 10"""
                )
                top_acoes = [{"acao": r[0], "total": r[1]} for r in cur.fetchall()]

                # Confiança média da IA por tipo de mensagem
                cur.execute(
                    """SELECT tipo,
                              COUNT(*) as total,
                              ROUND(AVG(confianca_ia)::numeric, 2) as confianca_media,
                              ROUND(MIN(confianca_ia)::numeric, 2) as confianca_min,
                              ROUND(MAX(confianca_ia)::numeric, 2) as confianca_max
                       FROM atividades
                       WHERE confianca_ia > 0 AND tipo IS NOT NULL AND tipo != ''
                       GROUP BY tipo
                       ORDER BY total DESC"""
                )
                confianca_por_tipo = [
                    {
                        "tipo": r[0],
                        "total": r[1],
                        "confianca_media": float(r[2]) if r[2] else 0,
                        "confianca_min": float(r[3]) if r[3] else 0,
                        "confianca_max": float(r[4]) if r[4] else 0,
                    }
                    for r in cur.fetchall()
                ]

                # Volume de processamento por dia (últimos 30 dias)
                cur.execute(
                    """SELECT LEFT(data_hora, 10) as dia, COUNT(*) as total,
                              ROUND(AVG(confianca_ia)::numeric, 2) as confianca_media
                       FROM atividades
                       WHERE data_hora >= (NOW() - INTERVAL '30 days')::text
                         AND lead_id != ''
                       GROUP BY dia
                       ORDER BY dia ASC"""
                )
                volume_por_dia = [
                    {
                        "dia": r[0],
                        "total": r[1],
                        "confianca_media": float(r[2]) if r[2] else 0,
                    }
                    for r in cur.fetchall()
                ]

                # Mensagens com baixa confiança (IA ficou insegura) — para revisão
                cur.execute(
                    """SELECT a.data_hora, a.lead_id, l.nome, a.tipo,
                              a.acao_executada, a.confianca_ia, a.resumo
                       FROM atividades a
                       LEFT JOIN leads l ON a.lead_id = l.lead_id
                       WHERE a.confianca_ia > 0 AND a.confianca_ia < 0.4
                         AND a.lead_id != ''
                       ORDER BY a.data_hora DESC
                       LIMIT 10"""
                )
                cols = [d[0] for d in cur.description]
                baixa_confianca = [dict(zip(cols, r)) for r in cur.fetchall()]

                # Totais gerais de processamento IA
                cur.execute(
                    """SELECT
                           COUNT(*) as total_processadas,
                           COUNT(*) FILTER (WHERE confianca_ia > 0) as com_score,
                           ROUND(AVG(confianca_ia) FILTER (WHERE confianca_ia > 0)::numeric, 2) as confianca_global,
                           COUNT(*) FILTER (WHERE confianca_ia > 0 AND confianca_ia < 0.4) as baixa_confianca_count,
                           COUNT(*) FILTER (WHERE duracao_audio_s IS NOT NULL) as total_audios,
                           ROUND(AVG(duracao_audio_s) FILTER (WHERE duracao_audio_s IS NOT NULL)::numeric, 1) as duracao_audio_media
                       FROM atividades
                       WHERE lead_id != ''"""
                )
                totais_row = cur.fetchone()
                totais = {
                    "total_processadas": totais_row[0] or 0,
                    "com_score": totais_row[1] or 0,
                    "confianca_global": float(totais_row[2]) if totais_row[2] else None,
                    "baixa_confianca_count": totais_row[3] or 0,
                    "total_audios": totais_row[4] or 0,
                    "duracao_audio_media_s": float(totais_row[5]) if totais_row[5] else None,
                }

            return {
                "totais": totais,
                "top_acoes": top_acoes,
                "confianca_por_tipo": confianca_por_tipo,
                "volume_por_dia": volume_por_dia,
                "baixa_confianca": baixa_confianca,
            }
        finally:
            self._put(conn)

    # ------------------------------------------------------------------
    # Multi-tenant — public.tenants table
    # ------------------------------------------------------------------

    def create_public_tables(self) -> None:
        """Cria a tabela public.tenants (idempotente)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(CREATE_TENANTS_SQL)
            conn.commit()
            logger.info("public.tenants criada/verificada OK")
        finally:
            self._put(conn)

    def create_tenant_schema(self, tenant_id: str) -> None:
        """Cria schema tenant_{id} com todas as tabelas do IziDesk."""
        if not re.match(r'^[a-z0-9_]{1,63}$', tenant_id):
            raise ValueError(f"tenant_id inválido: {tenant_id!r}")
        schema = _safe_schema(tenant_id)
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
                cur.execute(f"SET search_path TO {schema}, public")
                cur.execute(TENANT_SCHEMA_SQL)
                cur.execute("SET search_path TO public")
            conn.commit()
            logger.info("schema %s criado OK", schema)
        finally:
            self._put(conn)

    def drop_tenant_schema(self, tenant_id: str) -> None:
        """Remove schema e dados do tenant (CASCADE)."""
        schema = _safe_schema(tenant_id)
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
                cur.execute(
                    "DELETE FROM public.tenants WHERE id = %s", (tenant_id,)
                )
            conn.commit()
            logger.info("schema %s removido OK", schema)
        finally:
            self._put(conn)

    def list_tenants(self) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, nome, plano, evolution_instance, evolution_api_key,
                              ativo, criado_em, atualizado_em
                       FROM public.tenants
                       ORDER BY criado_em DESC"""
                )
                return self._fetchall_dict(cur)
        finally:
            self._put(conn)

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, nome, plano, evolution_instance, evolution_api_key,
                              ativo, criado_em, atualizado_em
                       FROM public.tenants WHERE id = %s""",
                    (tenant_id,),
                )
                return self._fetchone_dict(cur)
        finally:
            self._put(conn)

    def get_tenant_by_instance(self, instance_name: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, nome, plano, evolution_instance, evolution_api_key,
                              ativo, criado_em, atualizado_em
                       FROM public.tenants WHERE evolution_instance = %s""",
                    (instance_name,),
                )
                return self._fetchone_dict(cur)
        finally:
            self._put(conn)

    def create_tenant(
        self,
        tenant_id: str,
        nome: str,
        plano: str = "basico",
        evolution_instance: str = "",
        evolution_api_key: str = "",
    ) -> Dict[str, Any]:
        if not re.match(r'^[a-z0-9_]{1,63}$', tenant_id):
            raise ValueError(f"tenant_id inválido: {tenant_id!r}")
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO public.tenants
                           (id, nome, plano, evolution_instance, evolution_api_key)
                       VALUES (%s, %s, %s, %s, %s)
                       RETURNING id, nome, plano, evolution_instance, evolution_api_key,
                                 ativo, criado_em, atualizado_em""",
                    (tenant_id, nome, plano, evolution_instance or None, evolution_api_key),
                )
                row = self._fetchone_dict(cur)
            conn.commit()
            return row
        finally:
            self._put(conn)

    def update_tenant(self, tenant_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        allowed = {"nome", "plano", "evolution_instance", "evolution_api_key", "ativo"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_tenant(tenant_id)
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [tenant_id]
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""UPDATE public.tenants
                        SET {set_clause}, atualizado_em = NOW()
                        WHERE id = %s
                        RETURNING id, nome, plano, evolution_instance, evolution_api_key,
                                  ativo, criado_em, atualizado_em""",
                    values,
                )
                row = self._fetchone_dict(cur)
            conn.commit()
            return row
        finally:
            self._put(conn)

    def get_admin_overview(self) -> Dict[str, Any]:
        """Estatísticas agregadas de todos os tenants (via schema-qualified SQL)."""
        tenants = self.list_tenants()
        conn = self._conn()
        try:
            stats = []
            with conn.cursor() as cur:
                for t in tenants:
                    schema = _safe_schema(t["id"])
                    try:
                        cur.execute(
                            f"""SELECT
                                (SELECT COUNT(*) FROM {schema}.leads)         AS total_leads,
                                (SELECT COUNT(*) FROM {schema}.conversas
                                  WHERE status = 'aberto')                    AS conversas_abertas,
                                (SELECT COALESCE(SUM(nao_lidas),0)
                                   FROM {schema}.conversas
                                  WHERE status = 'aberto')                    AS nao_lidas
                            """
                        )
                        row = cur.fetchone()
                        stats.append({
                            "tenant_id": t["id"],
                            "nome": t["nome"],
                            "plano": t["plano"],
                            "ativo": t["ativo"],
                            "evolution_instance": t["evolution_instance"],
                            "total_leads": row[0] if row else 0,
                            "conversas_abertas": row[1] if row else 0,
                            "nao_lidas": row[2] if row else 0,
                        })
                    except Exception:
                        stats.append({
                            "tenant_id": t["id"],
                            "nome": t["nome"],
                            "plano": t["plano"],
                            "ativo": t["ativo"],
                            "evolution_instance": t["evolution_instance"],
                            "total_leads": None,
                            "conversas_abertas": None,
                            "nao_lidas": None,
                        })
                        conn.rollback()
            return {"tenants": stats, "total": len(tenants)}
        finally:
            self._put(conn)


# ---------------------------------------------------------------------------
# TenantDBService — DBService com search_path fixado no schema do tenant
# ---------------------------------------------------------------------------

class TenantDBService(DBService):
    """DBService com todas as queries roteadas para o schema do tenant."""

    @classmethod
    def from_pool(cls, pool, tenant_id: str) -> "TenantDBService":
        """Cria TenantDBService compartilhando o pool existente (não abre novas conexões)."""
        if not re.match(r'^[a-z0-9_]{1,63}$', tenant_id):
            raise ValueError(f"tenant_id inválido: {tenant_id!r}")
        obj = object.__new__(cls)
        obj._pool = pool
        obj._tenant_schema = _safe_schema(tenant_id)
        obj._tenant_id = tenant_id
        return obj

    def _conn(self):
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {self._tenant_schema}, public")
        except Exception:
            self._pool.putconn(conn)
            raise
        return conn

    def _put(self, conn) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute("SET search_path TO public")
        except Exception:
            self._pool.putconn(conn, close=True)
            return
        self._pool.putconn(conn)
