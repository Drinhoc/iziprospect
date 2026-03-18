"""ProspectorService — multi-source lead discovery + WhatsApp enrichment.

Sources (all free, no API key required):
  1. OpenStreetMap Overpass API  — structured POI data for Brazilian cities
  2. Telelistas.net              — Brazilian yellow-pages (HTML scraping)
  3. Apontador.com.br            — Brazilian business directory (HTML scraping)

Enrichment pipeline (in order):
  1. If source phone is already mobile (9-digit after DDD) → mark as WhatsApp directly
  2. Visit website homepage → look for wa.me links / cell numbers
  3. Visit contact subpages → /contato, /fale-conosco, /contact
  4. DuckDuckGo organic search → "{nome} {cidade} whatsapp" → wa.me in snippets
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus
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
DDG_URL = "https://html.duckduckgo.com/html/"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
}

# Contact subpages to try during enrichment
_CONTACT_PATHS = ["/contato", "/fale-conosco", "/contact", "/contatos", "/fale-com-a-gente", "/atendimento"]

# Regex patterns
_CELL_RE = re.compile(r"\(?\d{2}\)?\s*9\d{4}[-\s]?\d{4}")
_WAME_RE = re.compile(r"wa\.me/(?:55)?(\d{10,11})")
_WA_API_RE = re.compile(r"api\.whatsapp\.com/send\?phone=(?:55)?(\d{10,11})")


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


def _is_mobile_br(phone: str) -> bool:
    """Brazilian mobile: 2-digit DDD + 9-digit subscriber starting with '9'.
    Examples: +55 19 9xxxx-xxxx (13 digits total with country code).
    """
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if digits.startswith("55"):
        digits = digits[2:]
    # Must be exactly 11 digits and 3rd digit (first of subscriber) == '9'
    return len(digits) == 11 and digits[2] == "9"


def _is_valid_br_phone(phone: str) -> bool:
    """Aceita celular (11 dígitos) e fixo (10 dígitos) brasileiros com DDD."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if digits.startswith("55"):
        digits = digits[2:]
    return len(digits) in (10, 11)


def _parse_cidade_estado(cidade: str) -> Tuple[str, str]:
    """'Limeira SP' → ('Limeira', 'SP'); 'São Paulo' → ('São Paulo', '')"""
    parts = cidade.strip().rsplit(None, 1)
    if len(parts) == 2 and len(parts[1]) == 2 and parts[1].isalpha():
        return parts[0].strip(), parts[1].upper()
    return cidade.strip(), ""


def _extract_wame_phone(href: str) -> str:
    """Extract and normalize phone number from wa.me or api.whatsapp.com link."""
    # Try wa.me pattern
    m = _WAME_RE.search(href)
    if m:
        digits = m.group(1)
        if not digits.startswith("55"):
            digits = f"55{digits}"
        return f"+{digits}"
    # Try api.whatsapp.com pattern
    m = _WA_API_RE.search(href)
    if m:
        digits = m.group(1)
        if not digits.startswith("55"):
            digits = f"55{digits}"
        return f"+{digits}"
    # Fallback: extract all digits
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
        fonte_names = []
        if "osm" in fontes:
            tasks.append(self._search_osm(segmento, cidade, limit, busca_id, fonte_busca))
            fonte_names.append("osm")
        if "telelistas" in fontes:
            tasks.append(self._search_telelistas(segmento, cidade, limit, busca_id, fonte_busca))
            fonte_names.append("telelistas")
        if "apontador" in fontes:
            tasks.append(self._search_apontador(segmento, cidade, limit, busca_id, fonte_busca))
            fonte_names.append("apontador")

        if not tasks:
            return {"busca_id": busca_id, "total": 0, "por_fonte": {}}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        por_fonte: Dict[str, int] = {}
        total = 0
        for fonte_name, result in zip(fonte_names, results):
            if isinstance(result, int):
                por_fonte[fonte_name] = result
                total += result
            else:
                logger.warning("prospector_%s falhou: %s", fonte_name, result)
                por_fonte[fonte_name] = 0

        return {"busca_id": busca_id, "total": total, "por_fonte": por_fonte}

    async def enrich_leads_sem_whatsapp(self) -> Dict[str, Any]:
        """Re-run WhatsApp enrichment for leads with status='novo' and no whatsapp.

        Uses the same pipeline as prospect enrichment: website scraping + DDG fallback.
        Updates leads.whatsapp directly when found.
        """
        leads = await asyncio.to_thread(self.db.get_leads_novo_sem_whatsapp)
        logger.info("enrich_leads_sem_whatsapp | total=%d", len(leads))
        found = 0
        for lead in leads:
            whatsapp = None
            try:
                if lead.get("site"):
                    result = await self._enrich_website(lead["site"])
                    if result:
                        whatsapp = result.get("whatsapp")

                if not whatsapp and lead.get("nome"):
                    whatsapp = await self._ddg_search_whatsapp(
                        lead["nome"], lead.get("cidade", "")
                    )
                    if whatsapp:
                        logger.info("ddg_found_wa lead | nome=%s wa=%s", lead["nome"], whatsapp)
            except Exception as exc:
                logger.debug("enrich_lead failed id=%s: %s", lead["lead_id"], exc)

            if whatsapp:
                await asyncio.to_thread(
                    self.db.update_lead_from_dashboard,
                    lead["lead_id"],
                    {"whatsapp": whatsapp},
                )
                found += 1

        return {"total_leads": len(leads), "whatsapp_encontrados": found}

    async def re_enrich_sem_whatsapp(self, busca_id: str | None = None) -> Dict[str, Any]:
        """Re-run enrichment for all pending prospects that have no WhatsApp yet.

        Resets enriquecido=0 for matching records, then fires enrich_batch
        for each affected busca_id.  Returns a summary dict.
        """
        busca_ids = await asyncio.to_thread(
            self.db.reset_prospects_for_reenrich, busca_id
        )
        logger.info("re_enrich_sem_whatsapp | busca_ids=%s", busca_ids)
        for bid in busca_ids:
            await self.enrich_batch(bid)
        return {"busca_ids_processados": busca_ids, "total": len(busca_ids)}

    async def enrich_batch(self, busca_id: str) -> None:
        """Background task: enrich ALL unenriched prospects from a busca.

        Pipeline per prospect:
          1. If source phone is already mobile → already stored as whatsapp (done in search)
          2. Visit website (homepage + contact subpages)
          3. DuckDuckGo search as last resort
        """
        prospects = await asyncio.to_thread(self.db.get_prospects_to_enrich, busca_id)
        logger.info("enrich_batch | busca_id=%s count=%d", busca_id, len(prospects))

        for p in prospects:
            # Skip enrichment if already has WhatsApp (from mobile source phone)
            if p.get("whatsapp"):
                await asyncio.to_thread(
                    self.db.update_prospect, p["id"], {"enriquecido": 1}
                )
                continue

            enriched: Dict[str, Any] = {"enriquecido": 1}
            try:
                if p.get("website"):
                    found = await self._enrich_website(p["website"])
                    if found:
                        enriched.update(found)

                # DuckDuckGo fallback if still no WhatsApp
                if not enriched.get("whatsapp") and p.get("nome"):
                    found_wa = await self._ddg_search_whatsapp(p["nome"], p.get("cidade", ""))
                    if found_wa:
                        enriched["whatsapp"] = found_wa
                        logger.info(
                            "ddg_found_wa | nome=%s wa=%s", p["nome"], found_wa
                        )
            except Exception as exc:
                logger.debug("enrich failed id=%d: %s", p["id"], exc)

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
                r = await client.post(OVERPASS_URL, data={"data": query}, headers=_HEADERS)
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

            phone_raw = (
                tags.get("phone", "")
                or tags.get("contact:phone", "")
                or tags.get("contact:mobile", "")
            ).strip()
            phone = _norm_phone(phone_raw)
            # If OSM has a mobile number, it's likely WhatsApp already
            whatsapp = phone if _is_valid_br_phone(phone) else ""

            website = (
                tags.get("website", "")
                or tags.get("contact:website", "")
                or tags.get("url", "")
            ).strip()

            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            link_maps = ""
            if lat and lon:
                link_maps = f"https://maps.google.com/?q={lat},{lon}"

            ok = await asyncio.to_thread(
                self.db.insert_prospect,
                {
                    "nome": nome,
                    "cidade": cidade_nome,
                    "segmento": segmento,
                    "telefone": phone,
                    "whatsapp": whatsapp,
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
                r = await client.get(url, headers=_HEADERS)
        except Exception as exc:
            logger.debug("telelistas_fetch falhou url=%s: %s", url, exc)
            return 0

        if r.status_code != 200:
            logger.debug("telelistas status=%d url=%s", r.status_code, url)
            return 0

        soup = BeautifulSoup(r.text, "html.parser")
        inserted = 0

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

            whatsapp = phone if _is_valid_br_phone(phone) else ""

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
                    "whatsapp": whatsapp,
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
                r = await client.get(url, headers=_HEADERS)
        except Exception as exc:
            logger.debug("apontador_fetch falhou url=%s: %s", url, exc)
            return 0

        if r.status_code != 200:
            logger.debug("apontador status=%d url=%s", r.status_code, url)
            return 0

        soup = BeautifulSoup(r.text, "html.parser")
        inserted = 0

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

            whatsapp = phone if _is_valid_br_phone(phone) else ""

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
                    "whatsapp": whatsapp,
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
    # Enrichment: website scraping (multi-page) + DuckDuckGo fallback
    # ------------------------------------------------------------------

    async def _enrich_website(self, url: str) -> Dict[str, Any]:
        """Try homepage + contact subpages. Return first WhatsApp found."""
        if not url.startswith("http"):
            url = f"https://{url}"

        # Step 1: homepage
        result = await self._scrape_page_for_wa(url)
        if result.get("whatsapp"):
            return result

        # Step 2: try contact subpages
        base = url.rstrip("/")
        for path in _CONTACT_PATHS:
            try:
                page_result = await self._scrape_page_for_wa(base + path)
                if page_result.get("whatsapp"):
                    return page_result
            except Exception:
                continue  # subpage may 404, that's fine

        # Return whatever we have (may have instagram even without WhatsApp)
        return result

    async def _scrape_page_for_wa(self, url: str) -> Dict[str, Any]:
        """Scrape a single URL for WhatsApp links / mobile numbers."""
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(url, headers=_HEADERS)
        if r.status_code >= 400:
            return {}

        soup = BeautifulSoup(r.text, "html.parser")
        result: Dict[str, Any] = {}

        # 1. wa.me or api.whatsapp.com links in <a href>
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "wa.me" in href or "api.whatsapp.com" in href:
                phone = _extract_wame_phone(href)
                if phone:
                    return {"whatsapp": phone}

        # 2. wa.me anywhere in raw HTML (sometimes in JS variables or data attributes)
        raw_html = r.text
        for m in _WAME_RE.finditer(raw_html):
            digits = m.group(1)
            if not digits.startswith("55"):
                digits = f"55{digits}"
            return {"whatsapp": f"+{digits}"}

        # 3. WhatsApp button/text: look for "whatsapp" text near a phone number
        page_text = soup.get_text(separator=" ")
        wa_idx = page_text.lower().find("whatsapp")
        if wa_idx >= 0:
            snippet = page_text[max(0, wa_idx - 30): wa_idx + 100]
            m = _CELL_RE.search(snippet)
            if m:
                return {"whatsapp": _norm_phone(m.group(0))}

        # 4. tel: links matching mobile pattern
        for a in soup.find_all("a", href=re.compile(r"^tel:")):
            raw = a["href"].replace("tel:", "").replace("+", "").replace(" ", "")
            normalized = _norm_phone(raw)
            if _is_valid_br_phone(normalized):
                return {"whatsapp": normalized}

        # 5. Any cell number in page text (last resort — less reliable)
        m = _CELL_RE.search(page_text)
        if m:
            result["whatsapp"] = _norm_phone(m.group(0))
            return result

        # 6. Instagram link (useful for future enrichment)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "instagram.com/" in href and "/p/" not in href and "/reel" not in href:
                result["instagram"] = href.split("?")[0].rstrip("/")
                break

        return result

    async def _ddg_search_whatsapp(self, nome: str, cidade: str) -> str:
        """Search DuckDuckGo HTML for '{nome} {cidade} whatsapp' → extract wa.me number.

        DuckDuckGo HTML version is scraper-friendly and often shows wa.me links
        directly in result snippets for Brazilian businesses.
        """
        query = f"{nome} {cidade} whatsapp".strip()
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                r = await client.get(
                    DDG_URL,
                    params={"q": query, "kl": "br-pt"},
                    headers={**_HEADERS, "Referer": "https://duckduckgo.com/"},
                )
            if r.status_code != 200:
                return ""

            # Look for wa.me links in results
            for m in _WAME_RE.finditer(r.text):
                digits = m.group(1)
                if not digits.startswith("55"):
                    digits = f"55{digits}"
                return f"+{digits}"

            # Also look for api.whatsapp.com links
            for m in _WA_API_RE.finditer(r.text):
                digits = m.group(1)
                if not digits.startswith("55"):
                    digits = f"55{digits}"
                return f"+{digits}"

        except Exception as exc:
            logger.debug("ddg_search falhou nome=%s: %s", nome, exc)

        return ""
