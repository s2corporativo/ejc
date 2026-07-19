# ── app/routers/utils.py ─────────────────────────────────────────────────────
# Utilidades de cadastro: CEP/CNPJ com fallback público e rate limit.
from fastapi import APIRouter, Depends, HTTPException
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.services.validators_service import (
    consultar_cep, consultar_cnpj, validar_cpf, validar_cnpj,
)

router = APIRouter(prefix="/utils", tags=["Utilidades"])


@router.get(
    "/cep/{cep}",
    dependencies=[Depends(rate_limit("utils_cep", 30))],
)
async def cep(cep: str, cu: User = Depends(get_current_user)):
    data = await consultar_cep(cep)
    if not data:
        raise HTTPException(status_code=404, detail="CEP não encontrado")
    return data


@router.get(
    "/cnpj/{cnpj}",
    dependencies=[Depends(rate_limit("utils_cnpj", 6))],
)
async def cnpj(cnpj: str, cu: User = Depends(get_current_user)):
    if not validar_cnpj(cnpj):
        raise HTTPException(status_code=422, detail="CNPJ inválido (dígito verificador)")
    data = await consultar_cnpj(cnpj)
    if not data:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado na Receita")
    return data


@router.get("/validar-cpf/{cpf}")
async def cpf_check(cpf: str, cu: User = Depends(get_current_user)):
    return {"cpf": cpf, "valido": validar_cpf(cpf)}
