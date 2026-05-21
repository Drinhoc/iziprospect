"""admin_ui.py — Páginas HTML do painel administrativo IziDesk."""
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/admin", tags=["admin-ui"])

COOKIE_NAME = "izidesk_admin"


def _is_authed(request: Request) -> bool:
    from app.config import settings
    token = request.cookies.get(COOKIE_NAME, "")
    return bool(settings.admin_token) and token == settings.admin_token


def _require_auth(request: Request):
    if not _is_authed(request):
        return RedirectResponse("/admin/login", status_code=302)
    return None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@router.post("/login")
async def login_submit(request: Request, token: str = Form(...)):
    from app.config import settings
    if not settings.admin_token or token != settings.admin_token:
        return templates.TemplateResponse(
            "admin_login.html",
            {"request": request, "erro": "Token inválido"},
        )
    response = RedirectResponse("/admin", status_code=302)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", max_age=86400 * 7)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_root(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    return RedirectResponse("/admin/tenants", status_code=302)


@router.get("/tenants", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    redir = _require_auth(request)
    if redir:
        return redir
    return templates.TemplateResponse("admin_dashboard.html", {"request": request})


# ---------------------------------------------------------------------------
# Tenant detail
# ---------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}", response_class=HTMLResponse)
async def admin_tenant(request: Request, tenant_id: str):
    redir = _require_auth(request)
    if redir:
        return redir
    return templates.TemplateResponse(
        "admin_tenant.html",
        {"request": request, "tenant_id": tenant_id},
    )
