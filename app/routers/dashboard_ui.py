from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
import pathlib

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["ui"])


@router.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/leads", response_class=HTMLResponse)
def leads_page(request: Request):
    return templates.TemplateResponse("leads.html", {"request": request})


@router.get("/estatisticas", response_class=HTMLResponse)
def estatisticas_page(request: Request):
    return templates.TemplateResponse("estatisticas.html", {"request": request})


@router.get("/prospeccao", response_class=HTMLResponse)
def prospeccao_page(request: Request):
    return templates.TemplateResponse("prospeccao.html", {"request": request})
