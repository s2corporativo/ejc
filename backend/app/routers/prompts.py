# app/routers/prompts.py — SHIM pós-consolidação D4 (20/08/2026).
# Biblioteca de prompts consolidada em prompts_juridicos.py (prefixo
# /prompts-juridicos, canônico). Este módulo mantém /prompts-biblioteca apenas
# como compatibilidade com redirect 308 até a migração dos consumidores.

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/prompts-biblioteca", tags=["Prompts Jurídicos"])

_REDIRECT_MAP = {
    "get:/": "/api/prompts-juridicos",
    "post:/": "/api/prompts-juridicos",
}

@router.post("/")
def _redirect_root_post():
    return RedirectResponse(url="/api/prompts-juridicos", status_code=308)

@router.get("/")
def _redirect_root_get():
    return RedirectResponse(url="/api/prompts-juridicos", status_code=308)

@router.post("/{prompt_id}/executar")
def _redirect_executar(prompt_id: str):
    return RedirectResponse(url=f"/api/prompts-juridicos/{prompt_id}/executar", status_code=308)
