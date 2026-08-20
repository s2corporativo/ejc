# app/routers/honorarios_calc.py — SHIM pós-consolidação D4 (20/08/2026).
# Consolidado em honorarios_oab.py (prefixo canônico /honorarios).
# Redirect 308 para compatibilidade temporária.

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/honorarios-calc", tags=["Honorários — Cálculo"])

@router.get("/cases/{case_id}/provisionamento")
def _redirect_provisionamento(case_id: str):
    return RedirectResponse(url=f"/api/honorarios-oab/cases/{case_id}/provisionamento", status_code=308)

@router.get("/cases/{case_id}/teto-etico")
def _redirect_teto_etico(case_id: str):
    return RedirectResponse(url=f"/api/honorarios-oab/cases/{case_id}/teto-etico", status_code=308)

# Re-exports de compatibilidade (testes internos; handlers originais
# incorporados ao canônico honorarios_oab.py).
from app.routers.honorarios_oab import provisionamento  # noqa: F401
from app.routers.honorarios_oab import teto_etico  # noqa: F401
