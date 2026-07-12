# ── app/routers/pncp.py ───────────────────────────────────────────────────────
# PNCP — contratações públicas (Lei 14.133/2021). Consulta PÚBLICA, sem chave.
# Integração GATED (PNCP_ENABLED), advogado+, rate limit 20/min por usuário.
#
#   GET /pncp/contratacoes — filtros por período/UF/município/modalidade,
#       paginado. Cache por (dia, filtros). Retorno normalizado.
#   GET /pncp/status       — booleans p/ o gate da UI (sem segredo).
#
# ANTI-SSRF: a base URL vem de settings (host oficial fixo); o usuário só
# fornece filtros (datas/uf/município/modalidade), validados antes da chamada.
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.services import pncp_service

logger = logging.getLogger("ejc.pncp")

router = APIRouter(prefix="/pncp", tags=["PNCP — contratações públicas"])

_ADVOGADO_MAIS = require_roles(["advogado"])


@router.get("/status")
async def status_pncp(cu: User = Depends(get_current_user)):
    """Status da integração PNCP — booleans (sem segredo; PNCP é aberto)."""
    return await pncp_service.status()


@router.get(
    "/contratacoes",
    dependencies=[Depends(rate_limit("pncp_contratacoes", 20))],
)
async def listar_contratacoes(
    data_inicial: date = Query(..., description="Início do período (YYYY-MM-DD)"),
    data_final: date = Query(..., description="Fim do período (YYYY-MM-DD)"),
    uf: str = Query("MG", max_length=2, description="UF (sigla, ex.: MG)"),
    municipio_ibge: str | None = Query(
        None, max_length=7,
        description="Código IBGE do município (Betim = 3106705)"),
    modalidade: int = Query(6, ge=1, le=99,
                            description="Código da modalidade (6 = pregão eletrônico)"),
    pagina: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Contratações públicas do PNCP no período/filtros informados.

    Retorno normalizado (número de controle PNCP, órgão, objeto, valor
    estimado, datas de proposta, link) + paginação. Cache do dia."""
    try:
        return await pncp_service.listar_contratacoes(
            db=db, data_inicial=data_inicial, data_final=data_final,
            uf=uf, municipio_ibge=municipio_ibge, modalidade=modalidade, pagina=pagina,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except (
        pncp_service.IntegracaoDesligadaError,
        pncp_service.PNCPIndisponivelError,
    ) as e:
        status_code, detail = pncp_service.http_status_para_erro(e)
        raise HTTPException(status_code=status_code, detail=detail)
