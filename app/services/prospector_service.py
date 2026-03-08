"""ProspectorService — multi-source lead discovery + WhatsApp enrichment.

Sources (all free, no API key required):
  1. OpenStreetMap Overpass API  — structured POI data for Brazilian cities
  2. Telelistas.net              — Brazilian yellow-pages (HTML scraping)
  3. Apontador.com.br            — Brazilian business directory (HTML scraping)

Enrichment:
  - Visits each found website and looks for wa.me / WhatsApp links / cell numbers.
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from uuid import uuid4

import httpx
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from app.services.db_service import DBService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OSM tag mapping: segmento → (key, value)
# ---------------------------------------------------------------------------
_OSM_TAGS: Dict[str, Tuple[str, str]] = {
    "clínica odontológica": ("amenity", "dentist"),
    "clinica odontologica": ("amenity", "dentist"),
    "odontologia": ("amenity", "dentist"),
    "dentista": ("amenity", "dentist"),
    "clínica médica": ("amenity", "clinic"),
    "clinica medica": ("amenity", "clinic"),
    "clínica geral": ("amenity", "clinic"),
    "clinica geral": ("amenity", "clinic"),
    "clínica": ("amenity", "clinic"),
    "clinica": ("amenity", "clinic"),
    "estética": ("shop", "beauty"),
    "estetica": ("shop", "beauty"),
    "clínica estética": ("shop", "beauty"),
    "clinica estetica": ("shop", "beauty"),
    "academia": ("leisure", "fitness_centre"),
    "farmácia": ("amenity", "pharmacy"),
    "farmacia": ("amenity", "pharmacy"),
    "psicólogo": ("amenity", "doctors"),
    "psicologo": ("amenity", "doctors"),
    "nutricionista": ("amenity", "doctors"),
    "médico": ("amenity", "doctors"),
    "medico": ("amenity", "doctors"),
    "fisioterapia": ("amenity", "clinic"),
    "fisioterapeuta": ("amenity", "clinic"),
    "veterinária": ("amenity", "veterinary"),
    "veterinaria": ("amenity", "veterinary"),
    "veterinário": ("amenity", "veterinary"),
}

_DEFAULT_OSM_TAG = ("amenity", "clinic")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_HEADERS = {"User-Agent": _UA}

# Regex: Brazilian mobile number with DDD (starts with 9, 8 digits, with optional DDD)
_CELL_RE = re.compile(r"\(?\d{2}\)?\s*9\d{4}[-\s]?\d{4}")
_WAME_RE = re.compile(r"wa\.me/(?:55)?(\d{10,11})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _slugify(s: str) -> str:
    s = _strip_accents(s).lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[\s_]+", "-", s).strip("-")


def _norm_phone(raw: str) -> str:
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if not digits:
        return ""
    if not digits.startswith("55") and len(digits) >= 10:
        digits = f"55{digits}"
    return f"+{digits}"


def _parse_cidade_estado(cidade: str) -> Tuple[str, str]:
    """'Limeira SP' → ('Limeira', 'SP'); 'São Paulo' → ('São Paulo', '')"""
    parts = cidade.strip().rsplit(None, 1)
    if len(parts) == 2 and len(parts[1]) == 2 and parts[1].isalpha():
        return parts[0].strip(), parts[1].upper()
    return cidade.strip(), ""


def _extract_wame_phone(href: str) -> str:
    m = _WAME_RE.search(href)
    if m:
        digits = m.group(1)
        if len(digits) == 10:
            digits = f"55{digits}"
        elif len(digits) == 11:
            digits = f"55{digits}"
        return f"+{digits}"
    digits = "".join(c for c in href if c.isdigit())
    if len(digits) >= 10:
        if not digits.startswith("55"):
            digits = f"55{digits}"
        return f"+{digits}"
    return ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# ProspectorService
# ---------------------------------------------------------------------------

class ProspectorService:
    def __init__(self, db: "DBService") -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public: search + enrich
    # ------------------------------------------------------------------

    async def search(
        self,
        segmento: str,
        cidade: str,
        fontes: List[str],
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Run discovery across selected sources. Returns busca_id + counts."""
        busca_id = uuid4().hex[:8]
        fonte_busca = f"{segmento} em {cidade}"

        tasks = []
        if "osm" in fontes:
            tasks.append(self._search_osm(segmento, cidade, limit, busca_id, fonte_busca))
        if "telelistas" in fontes:
            tasks.append(self._search_telelistas(segmento, cidade, limit, busca_id, fonte_busca))
        if "apontador" in fontes:
            tasks.append(self._search_apontador(segmento, cidade, limit, busca_id, fonte_busca))

        if not tasks:
            return {"busca_id": busca_id, "total": 0, "por_fonte": {}}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        por_fonte: Dict[str, int] = {}
        total = 0
        fonte_names = [f for f in ["osm", "telelistas", "apontador"] if f in fontes]
        for fonte_name, result in zip(fonte_names, results):
            if isinstance(result, int):
                por_fonte[fonte_name] = result
                total += result
            else:
                logger.warning("prospector_%s falhou: %s", fonte_name, result)
                por_fonte[fonte_name] = 0

        return {"busca_id": busca_id, "total": total, "por_fonte": por_fonte}

    async def enrich_batch(self, busca_id: str) -> None:
        """Background task: visit each prospect website and look for WhatsApp."""
        prospects = await asyncio.to_thread(self.db.get_prospects_to_enrich, busca_id)
        logger.info("enrich_batch | busca_id=%s count=%d", busca_id, len(prospects))
        for p in prospects:
            enriched: Dict[str, Any] = {"enriquecido": 1}
            if p.get("website"):
                try:
                    found = await self._enrich_website(p["website"])
                    enriched.update(found)
                except Exception as exc:
                    logger.debug("enrich_website failed url=%s: %s", p["website"], exc)
            await asyncio.to_thread(self.db.update_prospect, p["id"], enriched)

    # ------------------------------------------------------------------
    # Source 1: OpenStreetMap Overpass API
    # ------------------------------------------------------------------

    async def _search_osm(
        self, segmento: str, cidade: str, limit: int, busca_id: str, fonte_busca: str
    ) -> int:
        seg_lower = _strip_accents(segmento).lower().strip()
        osm_key, osm_val = _OSM_TAGS.get(seg_lower, _DEFAULT_OSM_TAG)

        cidade_nome, estado = _parse_cidade_estado(cidade)

        # Build Overpass query
        query = (
            f'[out:json][timeout:25];'
            f'area[name="{cidade_nome}"]->.a;'
            f'('
            f'  node["{osm_key}"="{osm_val}"](area.a);'
            f'  way["{osm_key}"="{osm_val}"](area.a);'
            f');'
            f'out center {limit};'
        )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    OVERPASS_URL,
                    data={"data": query},
                    headers=_HEADERS,
                )
            r.raise_for_status()
            elements = r.json().get("elements", [])
        except Exception as exc:
            logger.warning("osm_search falhou | cidade=%s: %s", cidade, exc)
            return 0

        inserted = 0
        for el in elements[:limit]:
            tags = el.get("tags", {})
            nome = tags.get("name", "").strip()
            if not nome:
                continue

            tags_addr = (
                tags.get("addr:street", "")
                + " " + tags.get("addr:housenumber", "")
            ).strip()
            endereco = tags_addr or tags.get("addr:full", "")

            phone_raw = tags.get("phone", "") or tags.get("contact:phone", "")
            website = (
                tags.get("website", "")
                or tags.get("contact:website", "")
                or tags.get("url", "")
            ).strip()

            # Build Maps link from coordinates
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            link_maps = f"https://www.openstreetmap.org/node/{el['id']}" if el.get("type") == "node" else ""
            if lat and lon:
                link_maps = f"https://maps.google.com/?q={lat},{lon}"

            ok = await asyncio.to_thread(
                self.db.insert_prospect,
                {
                    "nome": nome,
                    "cidade": cidade_nome,
                    "segmento": segmento,
                    "telefone": _norm_phone(phone_raw),
                    "website": website,
                    "link_maps": link_maps,
                    "fonte": "OpenStreetMap",
                    "fonte_busca": fonte_busca,
                    "data_coleta": _now_iso(),
                    "busca_id": busca_id,
                },
            )
            if ok:
                inserted += 1

        logger.info("osm_search | cidade=%s segmento=%s inseridos=%d", cidade, segmento, inserted)
        return inserted

    # ------------------------------------------------------------------
    # Source 2: Telelistas.net
    # ------------------------------------------------------------------

    async def _search_telelistas(
        self, segmento: str, cidade: str, limit: int, busca_id: str, fonte_busca: str
    ) -> int:
        cidade_nome, estado = _parse_cidade_estado(cidade)
        seg_slug = _slugify(segmento)
        cid_slug = _slugify(cidade_nome)
        estado_lower = estado.lower() if estado else "sp"

        url = f"https://www.telelistas.net/{seg_slug}/{estado_lower}/{cid_slug}/"
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.get(url, headers={**_HEADERS, "Accept-Language": "pt-BR,pt;q=0.9"})
        except Exception as exc:
            logger.debug("telelistas_fetch falhou url=%s: %s", url, exc)
            return 0

        if r.status_code != 200:
            logger.debug("telelistas status=%d url=%s", r.status_code, url)
            return 0

        soup = BeautifulSoup(r.text, "html.parser")
        inserted = 0

        # Try to find listing blocks — Telelistas uses various class names
        items = (
            soup.select(".listing-item")
            or soup.select(".tel-result-item")
            or soup.select("[class*='listing']")
            or soup.select("article")
            or []
        )

        for item in items[:limit]:
            nome_el = (
                item.find(["h2", "h3", "h4"])
                or item.select_one("[class*='name']")
                or item.select_one("[class*='title']")
            )
            if not nome_el:
                continue
            nome = nome_el.get_text(strip=True)
            if not nome or len(nome) < 3:
                continue

            # Phone: look for tel: links or spans with phone-like text
            phone = ""
            tel_link = item.find("a", href=re.compile(r"^tel:"))
            if tel_link:
                phone = _norm_phone(tel_link["href"].replace("tel:", ""))
            else:
                phone_text = item.find(string=_CELL_RE)
                if phone_text:
                    m = _CELL_RE.search(phone_text)
                    if m:
                        phone = _norm_phone(m.group(0))

            # Website
            website = ""
            for a in item.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and "telelistas" not in href:
                    website = href
                    break

            ok = await asyncio.to_thread(
                self.db.insert_prospect,
                {
                    "nome": nome,
                    "cidade": cidade_nome,
                    "segmento": segmento,
                    "telefone": phone,
                    "website": website,
                    "fonte": "Telelistas",
                    "fonte_busca": fonte_busca,
                    "data_coleta": _now_iso(),
                    "busca_id": busca_id,
                },
            )
            if ok:
                inserted += 1

        logger.info("telelistas_search | url=%s inseridos=%d", url, inserted)
        return inserted

    # ------------------------------------------------------------------
    # Source 3: Apontador.com.br
    # ------------------------------------------------------------------

    async def _search_apontador(
        self, segmento: str, cidade: str, limit: int, busca_id: str, fonte_busca: str
    ) -> int:
        cidade_nome, estado = _parse_cidade_estado(cidade)
        estado_lower = estado.lower() if estado else "sp"
        cid_slug = _slugify(cidade_nome)
        seg_slug = _slugify(segmento)

        url = f"https://www.apontador.com.br/local/{estado_lower}/{cid_slug}/{seg_slug}/"
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                r = await client.get(url, headers={**_HEADERS, "Accept-Language": "pt-BR,pt;q=0.9"})
        except Exception as exc:
            logger.debug("apontador_fetch falhou url=%s: %s", url, exc)
            return 0

        if r.status_code != 200:
            logger.debug("apontador status=%d url=%s", r.status_code, url)
            return 0

        soup = BeautifulSoup(r.text, "html.parser")
        inserted = 0

        # Apontador results — look for result cards
        items = (
            soup.select(".place-item")
            or soup.select(".result-item")
            or soup.select("[class*='place']")
            or soup.select("article")
            or []
        )

        for item in items[:limit]:
            nome_el = (
                item.find(["h2", "h3", "h4"])
                or item.select_one("[class*='name']")
                or item.select_one("[class*='title']")
            )
            if not nome_el:
                continue
            nome = nome_el.get_text(strip=True)
            if not nome or len(nome) < 3:
                continue

            phone = ""
            tel_link = item.find("a", href=re.compile(r"^tel:"))
            if tel_link:
                phone = _norm_phone(tel_link["href"].replace("tel:", ""))

            website = ""
            for a in item.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and "apontador" not in href:
                    website = href
                    break

            rating_el = item.select_one("[class*='rating']") or item.select_one("[class*='star']")
            rating = rating_el.get_text(strip=True) if rating_el else ""

            ok = await asyncio.to_thread(
                self.db.insert_prospect,
                {
                    "nome": nome,
                    "cidade": cidade_nome,
                    "segmento": segmento,
                    "telefone": phone,
                    "website": website,
                    "fonte": "Apontador",
                    "fonte_busca": fonte_busca,
                    "data_coleta": _now_iso(),
                    "busca_id": busca_id,
                    "rating": rating,
                },
            )
            if ok:
                inserted += 1

        logger.info("apontador_search | url=%s inseridos=%d", url, inserted)
        return inserted

    # ------------------------------------------------------------------
    # Enrichment: visit website, find WhatsApp
    # ------------------------------------------------------------------

    async def _enrich_website(self, url: str) -> Dict[str, Any]:
        """Returns dict with keys: whatsapp, instagram (both optional)."""
        if not url.startswith("http"):
            url = f"https://{url}"

        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            r = await client.get(url, headers=_HEADERS)

        soup = BeautifulSoup(r.text, "html.parser")
        result: Dict[str, Any] = {}

        # 1. wa.me links (highest priority)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "wa.me" in href or "api.whatsapp.com/send" in href:
                phone = _extract_wame_phone(href)
                if phone:
                    result["whatsapp"] = phone
                    return result

        # 2. WhatsApp button / text with phone number nearby
        text = soup.get_text(separator=" ")
        wa_idx = text.lower().find("whatsapp")
        if wa_idx >= 0:
            snippet = text[max(0, wa_idx - 20): wa_idx + 80]
            m = _CELL_RE.search(snippet)
            if m:
                result["whatsapp"] = _norm_phone(m.group(0))
                return result

        # 3. tel: links — look for mobile numbers (starts with 9)
        for a in soup.find_all("a", href=re.compile(r"^tel:")):
            raw = a["href"].replace("tel:", "").replace("+", "")
            digits = "".join(c for c in raw if c.isdigit())
            # Mobile: last 9 digits start with 9, and total >= 10 digits
            if len(digits) >= 10 and (digits[-9] == "9" if len(digits) >= 9 else False):
                result["whatsapp"] = _norm_phone(raw)
                return result

        # 4. Any cell number in page text
        m = _CELL_RE.search(text)
        if m:
            result["whatsapp"] = _norm_phone(m.group(0))
            return result

        # 5. Instagram link (as a fallback, useful for future enrichment)
        for a in soup.find_all("a", href=True):
            if "instagram.com/" in a["href"] and "instagram.com/p/" not in a["href"]:
                result["instagram"] = a["href"].split("?")[0].rstrip("/")
                break

        return result
