# app/routers/exito_rateio.py — SHIM pós-consolidação D4 (20/08/2026).
# Consolidado em honorarios_oab.py (prefixo canônico /honorarios).
# Redirect 308 para compatibilidade temporária.

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/honorarios-exito", tags=["Rateio de Êxito"])

@router.get("/{fee_id}/rateio")
def _redirect_rateio_get(fee_id: str):
    return RedirectResponse(url=f"/api/honorarios-oab/{fee_id}/rateio", status_code=308)

@router.post("/{fee_id}/rateio")
def _redirect_rateio_post(fee_id: str):
    return RedirectResponse(url=f"/api/honorarios-oab/{fee_id}/rateio", status_code=308)

# Re-exports de compatibilidade (testes internos; handlers originais
# incorporados ao canônico honorarios_oab.py).
from app.routers.honorarios_oab import preview_rateio  # noqa: F401
from app.routers.honorarios_oab import gerar_rateio  # noqa: F401
