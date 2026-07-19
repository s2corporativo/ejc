# ── app/routers/transparencia.py ─────────────────────────────────────────────
# CGU Portal da Transparência — consulta de SANÇÕES a empresas por CNPJ
# (CEIS/CNEP/CEPIM). Integração GATED (TRANSPARENCIA_ENABLED), advogado+,
# rate limit 20/min por usuário.
#
#   POST /transparencia/sancoes — body {cnpj}. Consulta as 3 bases, cache
#        diário por (base, cnpj). Retorno normalizado + tem_sancao.
#   GET  /transparencia/status  — booleans p/ o gate da UI, sem a chave.
#
# ANTI-SSRF/segredo: a base URL vem de settings (host oficial fixo); a chave
# só vai no header (transparencia_service). Só o CNPJ (14 díg.) vem do usuário.
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_roles
from app.models.user import User
from app.services import transparencia_service

logger = logging.getLogger("ejc.transparencia")

router = APIRouter(prefix="/transparencia", tags=["CGU Portal da Transparência"])

_ADVOGADO_MAIS = require_roles(["advogado"])


class SancoesIn(BaseModel):
    """Consulta de sanções por CNPJ (CEIS/CNEP/CEPIM)."""
    cnpj: str = Field(description="CNPJ (14 dígitos, com ou sem máscara)")

    @field_validator("cnpj")
    @classmethod
    def _v_cnpj(cls, v: str) -> str:
        try:
            return transparencia_service.validar_cnpj(v)
        except ValueError as e:
            raise ValueError(str(e))


@router.get("/status")
async def status_transparencia(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Status da integração CGU — booleans, sem a chave de API."""
    return await transparencia_service.status(db)


@router.post(
    "/sancoes",
    dependencies=[Depends(rate_limit("transparencia_sancoes", 20))],
)
async def consultar_sancoes(
    body: SancoesIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Sanções (CEIS/CNEP/CEPIM) de um CNPJ no Portal da Transparência.

    Retorno normalizado por base + `tem_sancao`. Cache do dia evita nova
    chamada à API. A chave de acesso nunca aparece no retorno/erros."""
    try:
        return await transparencia_service.consultar_sancoes(
            db, body.cnpj,
            user_id=cu.id, user_role=getattr(cu.role, "value", str(cu.role)),
        )
    except (
        transparencia_service.IntegracaoDesligadaError,
        transparencia_service.TransparenciaIndisponivelError,
    ) as e:
        status_code, detail = transparencia_service.http_status_para_erro(e)
        raise HTTPException(status_code=status_code, detail=detail)
