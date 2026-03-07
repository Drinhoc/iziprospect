from __future__ import annotations

import functools
import logging
import re
import threading
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

LEADS_HEADERS = [
    "lead_id",
    "nome",
    "cidade",
    "segmento",
    "whatsapp",
    "email",
    "instagram",
    "site",
    "responsavel",
    "fonte",
    "status",
    "prioridade",
    "data_criacao",
    "ultima_interacao_em",
    "proximo_followup_em",
    "observacoes",
    "resumo",
    "pendencia",
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
    "acao_executada",
    "confianca_ia",
    "duracao_audio_s",
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
    "clinica", "clínica", "consultorio", "consultório",
    "odontologia", "odonto", "estetica", "estética",
}

# Campos gerenciados pelo bot no sync (não inclui campos manuais como observacoes)
LEAD_SYNC_FIELDS = [
    "nome", "cidade", "segmento", "whatsapp", "email",
    "instagram", "site", "responsavel", "fonte",
    "status", "prioridade", "ultima_interacao_em", "proximo_followup_em",
    "resumo", "pendencia",
    "nome_normalizado", "cidade_normalizada", "lead_key",
]

# ---------------------------------------------------------------------------
# Formatação visual — configurações
# ---------------------------------------------------------------------------

# Larguras em pixels por coluna de LEADS (mesma ordem de LEADS_HEADERS)
LEADS_COL_WIDTHS = [75, 200, 110, 110, 140, 180, 130, 150, 130, 100,
                    140, 90, 155, 155, 155, 220, 220, 220, 1, 1, 1]  # últimas 3 ocultas

# Larguras de ATIVIDADES (mesma ordem de ATIV_HEADERS)
ATIV_COL_WIDTHS = [155, 90, 75, 140, 110, 140, 80, 90, 280, 300, 140]

# Larguras de REVISAR
REV_COL_WIDTHS = [155, 300, 110, 180, 260, 160, 140]

# Cores de status (RGB 0-1 float) — fundo da linha inteira
STATUS_COLORS = {
    "novo":             (0.89, 0.95, 1.0),   # azul claro
    "em contato":       (1.0,  0.98, 0.77),  # amarelo
    "qualificado":      (0.91, 0.96, 0.91),  # verde claro
    "proposta enviada": (1.0,  0.88, 0.70),  # laranja claro
    "negociando":       (1.0,  0.95, 0.88),  # âmbar
    "fechado":          (0.78, 0.90, 0.78),  # verde
    "perdido":          (1.0,  0.80, 0.80),  # vermelho claro
    "sem resposta":     (0.93, 0.93, 0.93),  # cinza
    "contato inválido": (0.94, 0.60, 0.60),  # vermelho escuro
}

# Cores de prioridade (aplica só à célula da coluna prioridade)
PRIORITY_COLORS = {
    "alta":  (1.0,  0.80, 0.80),  # vermelho
    "media": (1.0,  0.98, 0.77),  # amarelo
    "baixa": (0.91, 0.96, 0.91),  # verde
}


# ---------------------------------------------------------------------------
# Helpers de schema / range
# ---------------------------------------------------------------------------

def _col_letter(n: int) -> str:
    """Converte número de coluna 1-indexado para letra(s) Excel (1→A, 27→AA)."""
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _row_range(row_idx: int, headers: List[str]) -> str:
    return f"A{row_idx}:{_col_letter(len(headers))}{row_idx}"


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

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
# Formatting helpers — constroem requests da Sheets API v4
# ---------------------------------------------------------------------------

def _rgb(r: float, g: float, b: float) -> Dict[str, float]:
    return {"red": r, "green": g, "blue": b}


def _freeze_row_request(sheet_id: int) -> Dict[str, Any]:
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    }


def _header_style_request(sheet_id: int, num_cols: int) -> Dict[str, Any]:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": num_cols,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": _rgb(0.216, 0.278, 0.310),  # #37474F
                    "textFormat": {
                        "foregroundColor": _rgb(1.0, 1.0, 1.0),
                        "bold": True,
                        "fontSize": 10,
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }
    }


def _header_row_height_request(sheet_id: int) -> Dict[str, Any]:
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 32},
            "fields": "pixelSize",
        }
    }


def _col_width_request(sheet_id: int, col_index: int, pixel_size: int) -> Dict[str, Any]:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": col_index,
                "endIndex": col_index + 1,
            },
            "properties": {"pixelSize": pixel_size},
            "fields": "pixelSize",
        }
    }


def _hide_col_request(sheet_id: int, col_index: int) -> Dict[str, Any]:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": col_index,
                "endIndex": col_index + 1,
            },
            "properties": {"hiddenByUser": True},
            "fields": "hiddenByUser",
        }
    }


def _banded_rows_request(sheet_id: int, num_cols: int) -> Dict[str, Any]:
    return {
        "addBanding": {
            "bandedRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols,
                },
                "rowProperties": {
                    "firstBandColor": _rgb(1.0, 1.0, 1.0),           # branco
                    "secondBandColor": _rgb(0.96, 0.96, 0.97),        # cinza muito claro
                    "headerColor": _rgb(0.216, 0.278, 0.310),         # mesmo do header
                },
            }
        }
    }


def _delete_banding_request(banding_id: int) -> Dict[str, Any]:
    return {"deleteBanding": {"bandedRangeId": banding_id}}


def _delete_cf_request(sheet_id: int, index: int) -> Dict[str, Any]:
    return {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": index}}


def _status_cf_request(sheet_id: int, num_cols: int, status_col_letter: str, status: str, rgb: Tuple) -> Dict[str, Any]:
    """Conditional format que pinta a linha inteira quando status == valor."""
    r, g, b = rgb
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols,
                }],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": f'=${status_col_letter}2="{status}"'}],
                    },
                    "format": {"backgroundColor": _rgb(r, g, b)},
                },
            },
            "index": 0,
        }
    }


def _priority_cf_request(sheet_id: int, prio_col_index: int, priority: str, rgb: Tuple) -> Dict[str, Any]:
    """Conditional format que pinta a célula de prioridade."""
    r, g, b = rgb
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "startColumnIndex": prio_col_index,
                    "endColumnIndex": prio_col_index + 1,
                }],
                "booleanRule": {
                    "condition": {
                        "type": "TEXT_EQ",
                        "values": [{"userEnteredValue": priority}],
                    },
                    "format": {"backgroundColor": _rgb(r, g, b)},
                },
            },
            "index": 0,
        }
    }


def _move_sheet_first_request(sheet_id: int) -> Dict[str, Any]:
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "index": 0},
            "fields": "index",
        }
    }


def _add_chart_pie_request(sheet_id: int, data_sheet_id: int, anchor_row: int, anchor_col: int,
                            title: str, label_range: Dict, value_range: Dict) -> Dict[str, Any]:
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "titleTextFormat": {"bold": True, "fontSize": 11},
                    "pieChart": {
                        "legendPosition": "RIGHT_LEGEND",
                        "domain": {"sourceRange": {"sources": [label_range]}},
                        "series": {"sourceRange": {"sources": [value_range]}},
                        "threeDimensional": False,
                        "pieHole": 0.4,  # donut chart — mais moderno
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": anchor_col},
                        "widthPixels": 440,
                        "heightPixels": 320,
                    }
                },
            }
        }
    }


def _add_chart_bar_request(sheet_id: int, anchor_row: int, anchor_col: int,
                            title: str, label_range: Dict, value_range: Dict) -> Dict[str, Any]:
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "titleTextFormat": {"bold": True, "fontSize": 11},
                    "basicChart": {
                        "chartType": "BAR",
                        "legendPosition": "NO_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "Leads"},
                            {"position": "LEFT_AXIS"},
                        ],
                        "domains": [{"domain": {"sourceRange": {"sources": [label_range]}}}],
                        "series": [{"series": {"sourceRange": {"sources": [value_range]}}}],
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": anchor_col},
                        "widthPixels": 440,
                        "heightPixels": 280,
                    }
                },
            }
        }
    }


def _src_range(sheet_id: int, r1: int, c1: int, r2: int, c2: int) -> Dict[str, Any]:
    """Atalho para um sourceRange da API."""
    return {
        "sheetId": sheet_id,
        "startRowIndex": r1,
        "endRowIndex": r2,
        "startColumnIndex": c1,
        "endColumnIndex": c2,
    }


# ---------------------------------------------------------------------------
# SheetsService
# ---------------------------------------------------------------------------

class SheetsService:
    def __init__(self, service_account_info: dict, sheet_id: str):
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        self.gc = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(sheet_id)
        self.ws_leads, _leads_new = self._get_or_migrate("LEADS", LEADS_HEADERS)
        self.ws_ativ,  _ativ_new  = self._get_or_migrate("ATIVIDADES", ATIV_HEADERS)
        self.ws_rev,   _rev_new   = self._get_or_migrate("REVISAR", REV_HEADERS)
        self._sheets_new = {
            "LEADS": _leads_new,
            "ATIVIDADES": _ativ_new,
            "REVISAR": _rev_new,
        }

        # Aplica formatação visual e Dashboard (não-crítico — falha não interrompe startup)
        try:
            self._build_dashboard()
        except Exception:
            logger.warning("_build_dashboard falhou — não crítico", exc_info=True)
        try:
            self._apply_formatting()
        except Exception:
            logger.warning("_apply_formatting falhou — não crítico", exc_info=True)

    # ------------------------------------------------------------------
    # Sheet management
    # ------------------------------------------------------------------

    def _get_or_migrate(self, title: str, headers: List[str]) -> tuple:
        """Cria a worksheet se não existir; se existir, migra colunas novas sem perder dados.
        Retorna (ws, is_new) onde is_new=True indica sheet recém-criada."""
        try:
            ws = self.sheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title=title, rows=2000, cols=len(headers) + 5)
            ws.append_row(headers, value_input_option="RAW")
            logger.info("sheet_created | title=%s cols=%d", title, len(headers))
            return ws, True

        existing_headers = ws.row_values(1)

        if existing_headers == headers:
            return ws, False  # já está atualizado

        new_cols = [h for h in headers if h not in existing_headers]
        if new_cols:
            merged = list(existing_headers)
            for col in headers:
                if col not in merged:
                    merged.append(col)
            ws.update("A1", [merged], value_input_option="RAW")
            logger.info("sheet_migrated | title=%s new_cols=%s", title, new_cols)
        else:
            logger.warning(
                "sheet_header_mismatch | title=%s existing=%s expected=%s",
                title, existing_headers, headers,
            )

        return ws, False

    def _get_spreadsheet_metadata(self) -> Dict:
        """Busca metadados completos da planilha (inclui conditionalFormats e bandings)."""
        return self.sheet.client.spreadsheets_get(
            self.sheet.id,
            params={"fields": "sheets(properties(sheetId,title),conditionalFormats,bandedRanges,charts)"},
        )

    def _sheet_meta(self, sheet_id: int) -> Dict:
        """Retorna os metadados de uma sheet específica."""
        meta = self._get_spreadsheet_metadata()
        for s in meta.get("sheets", []):
            if s.get("properties", {}).get("sheetId") == sheet_id:
                return s
        return {}

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def _build_dashboard(self) -> None:
        """Cria ou atualiza a aba DASHBOARD com fórmulas e gráficos."""
        # Cria a sheet se não existir
        try:
            ws_dash = self.sheet.worksheet("DASHBOARD")
            is_new = False
        except gspread.WorksheetNotFound:
            ws_dash = self.sheet.add_worksheet(title="DASHBOARD", rows=60, cols=20)
            is_new = True
            logger.info("DASHBOARD criado")

        dash_id = ws_dash.id

        # Move para primeira posição
        self.sheet.batch_update({"requests": [_move_sheet_first_request(dash_id)]})

        # Descobre o índice da coluna status em LEADS (para fórmulas)
        status_col = _col_letter(LEADS_HEADERS.index("status") + 1)       # K
        segmento_col = _col_letter(LEADS_HEADERS.index("segmento") + 1)   # D
        cidade_col = _col_letter(LEADS_HEADERS.index("cidade") + 1)       # C

        # Fórmulas do pipeline por status
        status_list = [
            "novo", "em contato", "qualificado", "proposta enviada",
            "negociando", "fechado", "perdido", "sem resposta", "contato inválido",
        ]

        dash_data = [
            # Linha 1: Título principal
            ["📊 DASHBOARD — IziProspect CRM", "", "", "", "", "", "", "🏙️ Top Cidades", "", ""],
            # Linha 2: Sub-cabeçalho pipeline
            ["📋 Pipeline por Status", "", "", "", "🏥 Por Segmento", "", "", ""],
            # Linha 3: Header tabela status
            ["Status", "Leads", "%", "", "Segmento", "Leads", "", "Cidade", "Leads"],
        ]

        # Linhas 4-12: dados de status (row index 3-11)
        total_formula = f"=SOMA(B4:B12)"
        for s in status_list:
            count_f = f'=COUNTIF(LEADS!{status_col}:{status_col},"{s}")'
            pct_f = f"=SE(B{len(dash_data)+1}=0,\"\",TEXTO(B{len(dash_data)+1}/{total_formula[1:]},\"0%\"))"
            dash_data.append([s, count_f, pct_f, ""])

        # Linha 13: total
        dash_data.append(["TOTAL", total_formula, "100%", ""])

        # Preenche colunas E e F (segmento) e H, I (cidade) nas linhas 4-13
        seg_rows = 10
        for i in range(seg_rows):
            row_n = 4 + i
            seg_f = (
                f'=IFERROR(ÍNDICE(UNIQUE(FILTER(LEADS!{segmento_col}:{segmento_col},LEADS!{segmento_col}:{segmento_col}<>"")),{i+1}),"")'
                if i < seg_rows else ""
            )
            seg_count_f = f'=SE(E{row_n}="","",COUNTIF(LEADS!{segmento_col}:{segmento_col},E{row_n}))'
            cid_f = (
                f'=IFERROR(ÍNDICE(UNIQUE(FILTER(LEADS!{cidade_col}:{cidade_col},LEADS!{cidade_col}:{cidade_col}<>"")),{i+1}),"")'
                if i < seg_rows else ""
            )
            cid_count_f = f'=SE(H{row_n}="","",COUNTIF(LEADS!{cidade_col}:{cidade_col},H{row_n}))'
            # Extende a linha existente com os dados de segmento e cidade
            if row_n - 1 < len(dash_data):
                row = dash_data[row_n - 1]
                # Garante 9 colunas
                while len(row) < 9:
                    row.append("")
                row[4] = seg_f
                row[5] = seg_count_f
                row[7] = cid_f
                row[8] = cid_count_f

        # Linha 14: espaço
        dash_data.append([""])

        # Linha 15+: atividade recente
        dash_data.append(["⏱️ Atividade Recente (últimas 10)", "", "", "", "", "", "", "", ""])
        dash_data.append(["Data/Hora", "Lead", "Tipo", "Resumo", "", "", "", "", ""])

        # QUERY para as últimas 10 atividades ordenadas por data desc
        # QUERY do Sheets: seleciona colunas A, C, D, J de ATIVIDADES ordenado desc por A
        ativ_query = '=IFERROR(QUERY(ATIVIDADES!A:K,"SELECT A,C,D,J ORDER BY A DESC LIMIT 10",1),"")'
        dash_data.append([ativ_query])

        # Escreve tudo no dashboard
        ws_dash.clear()
        ws_dash.update("A1", dash_data, value_input_option="USER_ENTERED")

        # Gráficos: só adiciona se o dashboard for novo OU não tiver gráficos ainda
        meta = self._sheet_meta(dash_id)
        existing_charts = meta.get("charts", [])
        if not existing_charts:
            chart_requests = []

            # Gráfico 1: Donut — Pipeline por Status (dados em B4:B12, labels em A4:A12)
            chart_requests.append(_add_chart_pie_request(
                sheet_id=dash_id,
                data_sheet_id=dash_id,
                anchor_row=2,   # linha 3
                anchor_col=3,   # coluna D
                title="Pipeline por Status",
                label_range=_src_range(dash_id, 3, 0, 12, 1),   # A4:A12
                value_range=_src_range(dash_id, 3, 1, 12, 2),   # B4:B12
            ))

            # Gráfico 2: Barras — Leads por Segmento (dados em E4:F13)
            chart_requests.append(_add_chart_bar_request(
                sheet_id=dash_id,
                anchor_row=16,  # linha 17
                anchor_col=3,   # coluna D
                title="Leads por Segmento",
                label_range=_src_range(dash_id, 3, 4, 13, 5),   # E4:E13
                value_range=_src_range(dash_id, 3, 5, 13, 6),   # F4:F13
            ))

            if chart_requests:
                self.sheet.batch_update({"requests": chart_requests})
                logger.info("DASHBOARD gráficos adicionados")

        logger.info("_build_dashboard OK | is_new=%s", is_new)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def _apply_formatting(self) -> None:
        """Aplica formatação visual completa a todas as sheets via Sheets API v4."""
        requests: List[Dict[str, Any]] = []

        sheets_config = [
            (self.ws_leads, LEADS_HEADERS, LEADS_COL_WIDTHS),
            (self.ws_ativ,  ATIV_HEADERS,  ATIV_COL_WIDTHS),
            (self.ws_rev,   REV_HEADERS,   REV_COL_WIDTHS),
        ]

        # --- Coleta metadados para remover bandings existentes (evita duplicatas) ---
        meta = self._get_spreadsheet_metadata()
        existing_bandings: Dict[int, List[int]] = {}  # sheet_id → [banding_ids]
        for s in meta.get("sheets", []):
            sid = s.get("properties", {}).get("sheetId")
            if sid is not None:
                existing_bandings[sid] = [b["bandedRangeId"] for b in s.get("bandedRanges", [])]

        # --- Coleta contagem de conditional format rules existentes para LEADS ---
        leads_cf_rules = 0
        for s in meta.get("sheets", []):
            if s.get("properties", {}).get("sheetId") == self.ws_leads.id:
                leads_cf_rules = len(s.get("conditionalFormats", []))
                break

        # --- 1. Remove bandings existentes ---
        for ws, _, _ in sheets_config:
            for bid in existing_bandings.get(ws.id, []):
                requests.append(_delete_banding_request(bid))

        # --- 2. Remove conditional formats existentes de LEADS (do último para o primeiro) ---
        for i in range(leads_cf_rules - 1, -1, -1):
            requests.append(_delete_cf_request(self.ws_leads.id, i))

        # --- 3. Aplica formatação base em cada sheet ---
        for ws, headers, col_widths in sheets_config:
            sid = ws.id
            num_cols = len(headers)

            # Freeze + header style + altura do header
            requests.append(_freeze_row_request(sid))
            requests.append(_header_style_request(sid, num_cols))
            requests.append(_header_row_height_request(sid))

            # Larguras de coluna — só aplica em sheets recém-criadas para preservar ajustes manuais
            if self._sheets_new.get(ws.title, False):
                for col_idx, width in enumerate(col_widths):
                    if col_idx >= num_cols:
                        break
                    requests.append(_col_width_request(sid, col_idx, max(width, 1)))
                    if width <= 1:
                        requests.append(_hide_col_request(sid, col_idx))

            # Banded rows (zebra stripes)
            requests.append(_banded_rows_request(sid, num_cols))

        # --- 4. Conditional formatting de status em LEADS (linha inteira) ---
        status_col_idx = LEADS_HEADERS.index("status")
        status_col_letter = _col_letter(status_col_idx + 1)
        for status, rgb in STATUS_COLORS.items():
            requests.append(_status_cf_request(
                self.ws_leads.id, len(LEADS_HEADERS), status_col_letter, status, rgb
            ))

        # --- 5. Conditional formatting de prioridade em LEADS (só a célula) ---
        prio_col_idx = LEADS_HEADERS.index("prioridade")
        for priority, rgb in PRIORITY_COLORS.items():
            requests.append(_priority_cf_request(self.ws_leads.id, prio_col_idx, priority, rgb))

        # --- 6. Formatação do DASHBOARD ---
        try:
            ws_dash = self.sheet.worksheet("DASHBOARD")
            dash_id = ws_dash.id

            # Remove bandings do dashboard se existirem
            for bid in existing_bandings.get(dash_id, []):
                requests.append(_delete_banding_request(bid))

            # Header linha 1 (título)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": dash_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 10,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": _rgb(0.13, 0.19, 0.25),  # azul marinho
                            "textFormat": {
                                "foregroundColor": _rgb(1.0, 1.0, 1.0),
                                "bold": True,
                                "fontSize": 13,
                            },
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)",
                }
            })
            # Altura do título
            requests.append({
                "updateDimensionProperties": {
                    "range": {"sheetId": dash_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                    "properties": {"pixelSize": 40},
                    "fields": "pixelSize",
                }
            })
            # Linha 3 (sub-cabeçalhos das tabelas)
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": dash_id,
                        "startRowIndex": 2,
                        "endRowIndex": 3,
                        "startColumnIndex": 0,
                        "endColumnIndex": 10,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": _rgb(0.216, 0.278, 0.310),
                            "textFormat": {
                                "foregroundColor": _rgb(1.0, 1.0, 1.0),
                                "bold": True,
                                "fontSize": 10,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            })
            # Freeze linha 1 e 3
            requests.append(_freeze_row_request(dash_id))

            # Larguras no DASHBOARD
            dash_widths = [160, 80, 60, 420, 160, 80, 20, 160, 80, 20]
            for i, w in enumerate(dash_widths):
                requests.append(_col_width_request(dash_id, i, w))

            # Conditional format das linhas de status no DASHBOARD (coluna A = nome do status)
            for status, rgb in STATUS_COLORS.items():
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": dash_id,
                                "startRowIndex": 3,
                                "endRowIndex": 12,
                                "startColumnIndex": 0,
                                "endColumnIndex": 3,
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": "TEXT_EQ",
                                    "values": [{"userEnteredValue": status}],
                                },
                                "format": {"backgroundColor": _rgb(*rgb)},
                            },
                        },
                        "index": 0,
                    }
                })
        except gspread.WorksheetNotFound:
            pass

        # Envia tudo em uma única chamada
        self.sheet.batch_update({"requests": requests})
        logger.info("_apply_formatting OK | requests=%d", len(requests))

    # ------------------------------------------------------------------
    # Seeding data — exporta dados existentes para o DB SQLite
    # ------------------------------------------------------------------

    @_gspread_retry()
    def all_leads(self) -> List[Dict[str, str]]:
        return self.ws_leads.get_all_records()

    @_gspread_retry()
    def all_activities(self) -> List[Dict[str, str]]:
        return self.ws_ativ.get_all_records()

    # ------------------------------------------------------------------
    # Sync write-only — DB resolve o matching, Sheets só persiste
    # ------------------------------------------------------------------

    @_gspread_retry()
    def sync_lead(self, lead_dict: Dict[str, Any]) -> None:
        """Sincroniza um lead já resolvido pelo DB para o Sheets.

        Encontra a linha pelo lead_id e atualiza. Se não encontrar, insere.
        Preserva campos manuais (observacoes) que existam na planilha.
        """
        lead_id = lead_dict.get("lead_id", "")
        if not lead_id:
            return

        records = self.ws_leads.get_all_values()
        if not records:
            return
        headers = records[0]

        # Procura linha existente por lead_id
        for row_idx, row in enumerate(records[1:], start=2):
            if row and row[0] == lead_id:
                existing = dict(zip(headers, row))
                # Atualiza apenas os campos gerenciados pelo bot; preserva manuais
                for field in LEAD_SYNC_FIELDS:
                    if field in lead_dict and lead_dict[field] is not None:
                        existing[field] = str(lead_dict[field])
                rng = _row_range(row_idx, headers)
                self.ws_leads.update(rng, [[existing.get(h, "") for h in headers]])
                return

        # Não encontrou — insere nova linha
        row_data = {h: str(lead_dict.get(h, "") or "") for h in headers}
        self.ws_leads.append_row(
            [row_data.get(h, "") for h in headers],
            value_input_option="RAW",
        )
        logger.info("sync_lead: novo lead inserido no Sheets | lead_id=%s", lead_id)

    @_gspread_retry()
    def sync_activity(
        self,
        when: datetime,
        msg_id: str,
        lead_id: str,
        tipo: str,
        canal: str,
        acao_executada: str,
        confianca_ia: float,
        duracao_audio_s: Optional[int],
        mensagem_bruta: str,
        resumo: str,
        followup_em: Optional[str],
    ) -> None:
        actual_headers = self.ws_ativ.row_values(1)
        row_data = {
            "data_hora": when.isoformat(),
            "msg_id": msg_id,
            "lead_id": lead_id,
            "tipo": tipo,
            "canal": canal,
            "acao_executada": acao_executada,
            "confianca_ia": f"{confianca_ia:.2f}" if confianca_ia is not None else "",
            "duracao_audio_s": str(duracao_audio_s) if duracao_audio_s is not None else "",
            "mensagem_bruta": mensagem_bruta,
            "resumo": resumo,
            "followup_em": followup_em or "",
        }
        self.ws_ativ.append_row(
            [row_data.get(h, "") for h in actual_headers],
            value_input_option="RAW",
        )

    @_gspread_retry()
    def add_review(
        self,
        when: datetime,
        mensagem_bruta: str,
        cidade_detectada: Optional[str],
        nome_detectado: Optional[str],
        candidatos: List[Dict[str, str]],
        acao: str,
    ):
        cand = "; ".join(f"{c.get('lead_id')}:{c.get('nome')}" for c in candidatos)
        self.ws_rev.append_row(
            [when.isoformat(), mensagem_bruta, cidade_detectada or "", nome_detectado or "", cand, acao, ""],
            value_input_option="RAW",
        )

    @_gspread_retry()
    def update_lead_fields(self, lead_id: str, fields: Dict[str, str]) -> bool:
        records = self.ws_leads.get_all_values()
        if not records:
            return False
        headers = records[0]
        for idx, row in enumerate(records[1:], start=2):
            if row[0] == lead_id:
                current = dict(zip(headers, row))
                current.update(fields)
                if "nome" in fields:
                    current["nome_normalizado"] = normalize_text(current["nome"])
                if "cidade" in fields:
                    current["cidade_normalizada"] = normalize_text(current["cidade"])
                current["lead_key"] = f"{current.get('cidade_normalizada', '')}:{canonicalize_name(current.get('nome', ''))}"
                rng = _row_range(idx, headers)
                self.ws_leads.update(rng, [[current.get(h, "") for h in headers]])
                return True
        return False

    @_gspread_retry()
    def bind_latest_activity_to_lead(self, lead_id: str) -> bool:
        records = self.ws_ativ.get_all_values()
        if len(records) < 2:
            return False

        headers = records[0]
        try:
            lead_id_col = headers.index("lead_id") + 1
        except ValueError:
            lead_id_col = 3

        for row_idx in range(len(records), 1, -1):
            row = records[row_idx - 1]
            current_lead = row[lead_id_col - 1] if len(row) >= lead_id_col else ""
            if not str(current_lead).strip():
                self.ws_ativ.update(f"{_col_letter(lead_id_col)}{row_idx}", [[lead_id]])
                return True
        return False

    @_gspread_retry()
    def latest_linked_lead_id(self) -> str:
        records = self.ws_ativ.get_all_values()
        if len(records) < 2:
            return ""
        headers = records[0]
        try:
            lead_id_col = headers.index("lead_id")
        except ValueError:
            lead_id_col = 2
        for row_idx in range(len(records) - 1, 0, -1):
            row = records[row_idx]
            lead_id = row[lead_id_col] if len(row) > lead_id_col else ""
            if str(lead_id).strip():
                return str(lead_id).strip()
        return ""
