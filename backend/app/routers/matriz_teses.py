# ── app/routers/matriz_teses.py ──────────────────────────────────────────────
# FASE 3 do Orquestrador Jurídico — Matriz de Teses estruturada.
#
# POST /cases/{case_id}/matriz-teses/montar                → monta matriz (rascunho)
# GET  /cases/{case_id}/matriz-teses                       → matriz persistida
# POST /cases/{case_id}/matriz-teses/teses/{tese_id}/aprovar   → HITL (advogado+)
# POST /cases/{case_id}/matriz-teses/teses/{tese_id}/descartar → HITL (advogado+)
#
# Gates: verificar_acesso_caso (RBAC+ABAC) em TODOS; montar/aprovar exigem
# advogado+ (mesmo limiar de case_intelligence); montar tem rate limit 5/min.
# HITL: a matriz NASCE candidata/rascunho; aprovação é ato humano auditado.
# LGPD: sanitizar_pii roda AQUI antes de qualquer prompt do service.
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, requer_advogado
from app.core.taxonomia import areas_validas, normalizar_area
from app.models.user import User
from app.services import matriz_teses_service as mts
from app.services.sanitizer import sanitizar_pii

logger = logging.getLogger("ejc.matriz_teses")

router = APIRouter(prefix="/cases/{case_id}/matriz-teses",
                   tags=["Matriz de Teses"])


# Gate advogado+ (HITL é ato de advogado): fonte única core.security.requer_advogado.


class MontarMatrizIn(BaseModel):
    """Entrada validada da montagem — nada de dict cru no endpoint."""
    area: Optional[str] = Field(None, max_length=60)
    fatos: Optional[str] = Field(None, max_length=30000)


@router.post(
    "/montar",
    dependencies=[Depends(rate_limit("matriz-teses-montar", 5))],
)
async def montar(
    case_id: str,
    body: Optional[MontarMatrizIn] = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Monta a matriz de teses do caso (RASCUNHO — tudo nasce candidata).

    Decompõe questões (IA + AILog), pesquisa RAG por questão (precedentes só de
    retorno real, nunca inventados) e monta teses candidatas do Banco de Teses
    + sugeridas pela IA, com score determinístico. Advogado+.
    """
    requer_advogado(cu, detail="Montagem da matriz restrita a advogados")
    case = await verificar_acesso_caso(db, cu, case_id)

    body = body or MontarMatrizIn()
    if body.area and body.area.strip():
        # Área SEMPRE passa pela taxonomia canônica antes de qualquer prompt —
        # texto livre nunca é interpolado cru; fora do canônico → 422.
        area = normalizar_area(body.area)
        if area is None:
            raise HTTPException(422, detail={
                "mensagem": (f"área {body.area.strip()!r} não reconhecida na "
                             "taxonomia canônica"),
                "areas_validas": areas_validas(),
            })
    else:
        area = (getattr(case.area, "value", None)
                or str(case.area or "") or None)
    fatos = (body.fatos or case.descricao_fatos or "").strip()
    if len(fatos) < 20:
        raise HTTPException(422, "Caso sem fatos suficientes para montar a matriz")

    # LGPD: sanitiza ANTES de qualquer prompt (contrato do service).
    fatos_limpos, _houve_pii = sanitizar_pii(fatos)
    matriz = await mts.montar_matriz(db, cu.id, case_id, area, fatos_limpos)
    return matriz


@router.get("")
async def obter(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Matriz persistida do caso (questões, teses, precedentes, vínculos)."""
    await verificar_acesso_caso(db, cu, case_id)
    return await mts.obter_matriz(db, case_id)


async def _decidir(case_id: str, tese_id: str, decisao: str,
                   db: AsyncSession, cu: User) -> dict:
    requer_advogado(cu, detail="Decisão sobre tese restrita a advogados")
    await verificar_acesso_caso(db, cu, case_id)
    cand = await mts.aprovar_tese(db, tese_id, cu, decisao=decisao,
                                  case_id=case_id)
    return {"ok": True, "tese": mts._ser_tese(cand)}


@router.post("/teses/{tese_id}/aprovar",
             dependencies=[Depends(rate_limit("matriz-teses-decidir", 15))])
async def aprovar(
    case_id: str,
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """HITL: advogado aprova a tese candidata (AuditLog no service)."""
    return await _decidir(case_id, tese_id, "aprovada", db, cu)


@router.post("/teses/{tese_id}/descartar",
             dependencies=[Depends(rate_limit("matriz-teses-decidir", 15))])
async def descartar(
    case_id: str,
    tese_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """HITL: advogado descarta a tese candidata (AuditLog no service)."""
    return await _decidir(case_id, tese_id, "descartada", db, cu)
