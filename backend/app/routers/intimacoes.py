# ── app/routers/intimacoes.py ────────────────────────────────────────────────
# Intimações capturadas do DJEN — tratamento humano obrigatório.
# O job do scheduler captura; aqui o advogado processa.
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.djen import DjenComunicacao
from app.services.djen_service import capturar_para_advogado

router = APIRouter(prefix="/intimacoes", tags=["Intimações DJEN"])


@router.get("/")
async def listar(
    apenas_pendentes: bool = True,
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = select(DjenComunicacao)
    if apenas_pendentes:
        q = q.where(DjenComunicacao.processada == False)
    q = q.order_by(DjenComunicacao.data_disponibilizacao.desc())

    total = (await db.execute(
        select(sqlfunc.count()).select_from(q.subquery()))).scalar()
    rows = (await db.execute(
        q.offset((page-1)*page_size).limit(page_size))).scalars().all()
    return {
        "data": [
            {"id": c.id, "numero_processo": c.numero_processo,
             "tribunal": c.tribunal, "tipo": c.tipo_comunicacao,
             "data": c.data_disponibilizacao,
             "texto": (c.texto_resumo or "")[:500],
             "case_id": c.case_id, "processada": c.processada}
            for c in rows
        ],
        "total": total,
    }


@router.post("/{com_id}/processar")
async def processar(
    com_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Marca como tratada (após o advogado criar o prazo manualmente)."""
    c = (await db.execute(select(DjenComunicacao).where(
        DjenComunicacao.id == com_id
    ))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Comunicação não encontrada")
    c.processada = True
    c.processada_por = cu.id
    c.processada_em = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": "Intimação marcada como tratada"}


@router.post("/capturar-agora")
async def capturar_agora(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """Captura manual imediata para a OAB do usuário logado."""
    if not cu.djen_oab_numero or not cu.djen_oab_uf:
        raise HTTPException(
            status_code=422,
            detail="Configure sua OAB (número e UF) no seu perfil de usuário",
        )
    novas = await capturar_para_advogado(db, cu)
    await db.commit()
    return {"novas": novas, "detail": f"{novas} intimação(ões) nova(s)"}
