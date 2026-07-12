# ── app/routers/car.py ────────────────────────────────────────────────────────
# CAR — Cadastro Ambiental Rural (SICAR) via conector Infosimples EXISTENTE.
# NÃO abre novo cliente HTTP: reusa infosimples_service.consultar (gate/teto/
# cache/audit já implementados). Consulta PAGA — advogado+, rate limit 10/min.
#
#   POST /car/imovel        — caminho Infosimples `car-imovel`
#   POST /car/demonstrativo — caminho Infosimples `car-demonstrativo`
#
# CUSTO/segredo: flag/teto/cache e proteção do token ficam no
# infosimples_service. Aqui só validamos o input e normalizamos a saída.
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_roles
from app.models.user import User
from app.services import infosimples_service

logger = logging.getLogger("ejc.car")

router = APIRouter(prefix="/car", tags=["CAR — Cadastro Ambiental Rural"])

_ADVOGADO_MAIS = require_roles(["advogado"])


class CARIn(BaseModel):
    """Consulta de imóvel rural no SICAR pelo número de registro CAR."""
    # TODO(verificar-vps): confirmar o nome do parâmetro do imóvel esperado pela
    # Infosimples (documentado como `car`; pode ser `numero_car`/`registro`).
    car: str = Field(
        min_length=6, max_length=80,
        description="Número de registro CAR (ex.: MG-3106705-XXXX...).")

    @field_validator("car")
    @classmethod
    def _v_car(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Número de registro CAR obrigatório.")
        return v


async def _executar(db: AsyncSession, cu: User, caminho: str, parametros: dict) -> dict:
    try:
        return await infosimples_service.consultar(
            db, caminho, parametros,
            user_id=cu.id, user_role=getattr(cu.role, "value", str(cu.role)),
        )
    except (
        infosimples_service.IntegracaoDesligadaError,
        infosimples_service.LimiteDiarioAtingidoError,
        infosimples_service.InfosimplesConsultaError,
        infosimples_service.InfosimplesIndisponivelError,
    ) as e:
        status_code, detail = infosimples_service.http_status_para_erro(e)
        raise HTTPException(status_code=status_code, detail=detail)


@router.post(
    "/imovel", dependencies=[Depends(rate_limit("car_imovel", 10))],
)
async def consultar_imovel(
    body: CARIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Dados do imóvel rural no SICAR (consulta PAGA via Infosimples).

    Retorna número CAR, área, município/UF, situação, condição do cadastro e
    coordenadas/polígono quando disponíveis. Cache do dia evita cobrança dupla.
    """
    resultado = await _executar(db, cu, "car-imovel", {"car": body.car})
    dados = resultado.get("data") or []
    if not dados:
        raise HTTPException(
            status_code=404,
            detail="Imóvel não localizado no SICAR pela Infosimples "
                   "(confira o número de registro CAR).",
        )
    return {
        **infosimples_service.normalizar_car_imovel(dados[0]),
        "cache": bool(resultado.get("cache")),
        "site_receipts": resultado.get("site_receipts") or [],
        "dados": dados[0],
    }


@router.post(
    "/demonstrativo", dependencies=[Depends(rate_limit("car_demonstrativo", 10))],
)
async def consultar_demonstrativo(
    body: CARIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(_ADVOGADO_MAIS),
):
    """Demonstrativo da situação ambiental do imóvel no SICAR (consulta PAGA).

    Retorna situação, área total, reserva legal, APP, uso restrito e demais
    áreas ambientais (tolerante a campos ausentes). Cache do dia."""
    resultado = await _executar(db, cu, "car-demonstrativo", {"car": body.car})
    dados = resultado.get("data") or []
    if not dados:
        raise HTTPException(
            status_code=404,
            detail="Demonstrativo não localizado no SICAR pela Infosimples.",
        )
    return {
        **infosimples_service.normalizar_car_demonstrativo(dados[0]),
        "cache": bool(resultado.get("cache")),
        "site_receipts": resultado.get("site_receipts") or [],
        "dados": dados[0],
    }
